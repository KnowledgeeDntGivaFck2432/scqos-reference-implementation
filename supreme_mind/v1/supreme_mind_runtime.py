
from __future__ import annotations

import os
import json
import time
import uuid
import hashlib
from datetime import datetime, timezone

import boto3

TABLE = os.environ["SUPREME_MIND_TABLE"]
RECEIPT_TABLE = os.environ["SUPREME_MIND_RECEIPT_TABLE"]
QUEUE_URL = os.environ["SUPREME_MIND_QUEUE_URL"]
MANIFEST_BUCKET = os.environ["SUPREME_MIND_MANIFEST_BUCKET"]
MANIFEST_KEY = os.environ["SUPREME_MIND_MANIFEST_KEY"]
EXPECTED_MANIFEST_SHA256 = os.environ["SUPREME_MIND_MANIFEST_SHA256"]
AUTHORITY = os.environ["SCQOS_CANONICALIZATION_AUTHORITY"]

ddb = boto3.resource("dynamodb")
state_table = ddb.Table(TABLE)
receipt_table = ddb.Table(RECEIPT_TABLE)
s3 = boto3.client("s3")
sqs = boto3.client("sqs")

_manifest_cache = None

def utc():
    return datetime.now(timezone.utc).isoformat()

def load_manifest():
    global _manifest_cache

    if _manifest_cache is not None:
        return _manifest_cache

    obj = s3.get_object(Bucket=MANIFEST_BUCKET, Key=MANIFEST_KEY)
    raw = obj["Body"].read()

    # Artifact integrity is checked against the exact uploaded bytes.
    digest = hashlib.sha256(raw).hexdigest()

    uploaded_digest_obj = s3.get_object(
        Bucket=MANIFEST_BUCKET,
        Key=MANIFEST_KEY + ".raw.sha256"
    )
    uploaded_digest = uploaded_digest_obj["Body"].read().decode().strip()

    if digest != uploaded_digest:
        raise RuntimeError(
            "MANIFEST_RAW_INTEGRITY_FAILURE:"
            + digest + "!=" + uploaded_digest
        )

    manifest = json.loads(raw.decode("utf-8"))

    if manifest["constitutional_rules"]["canonicalization_authority"] != AUTHORITY:
        raise RuntimeError("CANONICALIZATION_AUTHORITY_MISMATCH")

    _manifest_cache = manifest
    return manifest

def receipt(event, state, reason, role=None):
    rid = str(uuid.uuid4())

    body = {
        "receipt_id": rid,
        "timestamp": utc(),
        "architecture_id": load_manifest()["architecture_id"],
        "role_id": role["role_id"] if role else event.get("role_id"),
        "role_name": role["name"] if role else None,
        "business_id": event.get("business_id", "default"),
        "principal_id": event.get("principal_id", "SOVEREIGN_HUMAN"),
        "intent": event.get("intent"),
        "action": event.get("action"),
        "tool": event.get("tool"),
        "state": state,
        "reason": reason,
        "evidence_refs": event.get("evidence_refs", []),
        "request_sha256": hashlib.sha256(
            json.dumps(
                event,
                sort_keys=True,
                separators=(",",":"),
                ensure_ascii=False,
                default=str
            ).encode("utf-8")
        ).hexdigest(),
    }

    receipt_table.put_item(Item=body)
    return body

def find_role(manifest, role_id):
    for role in manifest["roles"]:
        if role["role_id"] == role_id:
            return role
    return None

def admit(event):
    manifest = load_manifest()

    role = find_role(manifest, event.get("role_id",""))
    if role is None:
        return receipt(event, "REJECT", "UNKNOWN_ROLE")

    if event.get("principal_id", "SOVEREIGN_HUMAN") != role["principal"]:
        return receipt(event, "REJECT", "PRINCIPAL_AUTHORITY_MISMATCH", role)

    action = event.get("action")
    if not action:
        return receipt(event, "REJECT", "ACTION_MISSING", role)

    evidence = event.get("evidence_refs", [])
    human_authorization = event.get("human_authorization")

    # Pure cognitive work can execute autonomously.
    if action in manifest["read_only_actions"]:
        return receipt(event, "PERMIT", "READ_ONLY_AUTONOMY", role)

    # High-consequence execution requires explicit attributable authorization.
    if action in manifest["high_consequence_actions"]:
        if not human_authorization:
            return receipt(event, "HOLD", "HUMAN_AUTHORIZATION_REQUIRED", role)

        if not human_authorization.get("authorized_by"):
            return receipt(event, "HOLD", "AUTHORIZATION_IDENTITY_MISSING", role)

        if not human_authorization.get("scope"):
            return receipt(event, "HOLD", "AUTHORIZATION_SCOPE_MISSING", role)

        if not evidence:
            return receipt(event, "HOLD", "EVIDENCE_REQUIRED", role)

        return receipt(event, "PERMIT", "HIGH_CONSEQUENCE_AUTHORIZED", role)

    # Unknown mutating actions are never silently promoted.
    if not event.get("tool"):
        return receipt(event, "HOLD", "TOOL_CONTRACT_REQUIRED", role)

    if not evidence:
        return receipt(event, "HOLD", "EVIDENCE_REQUIRED", role)

    if role["autonomy"] == "human_required" and not human_authorization:
        return receipt(event, "HOLD", "ROLE_REQUIRES_HUMAN_AUTHORIZATION", role)

    return receipt(event, "PERMIT", "BOUNDED_MUTATION_ADMITTED", role)

def queue_action(event, admission):
    if admission["state"] != "PERMIT":
        return None

    payload = {
        "architecture_id": admission["architecture_id"],
        "receipt_id": admission["receipt_id"],
        "business_id": admission["business_id"],
        "role_id": admission["role_id"],
        "action": event.get("action"),
        "tool": event.get("tool"),
        "arguments": event.get("arguments", {}),
        "queued_at": utc(),
    }

    result = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(payload, separators=(",",":")),
        MessageGroupId=admission["business_id"] if QUEUE_URL.endswith(".fifo") else None
    ) if QUEUE_URL.endswith(".fifo") else sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(payload, separators=(",",":"))
    )

    return result.get("MessageId")

def heartbeat():
    manifest = load_manifest()

    state_table.put_item(
        Item={
            "pk": "SYSTEM",
            "sk": "HEARTBEAT",
            "architecture_id": manifest["architecture_id"],
            "role_count": len(manifest["roles"]),
            "canonicalization_authority":
                manifest["constitutional_rules"]["canonicalization_authority"],
            "updated_at": utc(),
            "state": "PERMIT",
        }
    )

    return {
        "state": "PERMIT",
        "architecture_id": manifest["architecture_id"],
        "role_count": len(manifest["roles"]),
        "updated_at": utc(),
    }

def lambda_handler(event, context):
    try:
        # EventBridge health tick.
        if event.get("source") == "aws.events":
            return heartbeat()

        # SQS events are intentionally NOT executed here yet.
        # They represent admitted work waiting for a separately registered
        # business tool adapter. Unknown side effects remain HOLD-by-design.
        if "Records" in event:
            results = []
            for record in event["Records"]:
                if record.get("eventSource") == "aws:sqs":
                    payload = json.loads(record["body"])

                    receipt_table.put_item(
                        Item={
                            "receipt_id": str(uuid.uuid4()),
                            "timestamp": utc(),
                            "architecture_id": payload["architecture_id"],
                            "role_id": payload["role_id"],
                            "business_id": payload["business_id"],
                            "action": payload["action"],
                            "tool": payload.get("tool"),
                            "state": "HOLD",
                            "reason": "EXECUTOR_ADAPTER_NOT_REGISTERED",
                            "parent_receipt_id": payload["receipt_id"],
                        }
                    )

                    results.append({
                        "state": "HOLD",
                        "reason": "EXECUTOR_ADAPTER_NOT_REGISTERED",
                        "parent_receipt_id": payload["receipt_id"],
                    })

            return {"results": results}

        # Function URLs often deliver request body as a string.
        if "body" in event and isinstance(event["body"], str):
            try:
                event = json.loads(event["body"])
            except Exception:
                return {
                    "statusCode": 400,
                    "body": json.dumps({
                        "state":"REJECT",
                        "reason":"INVALID_JSON"
                    })
                }

        if event.get("operation") == "health":
            result = heartbeat()
            return {
                "statusCode": 200,
                "body": json.dumps(result)
            }

        admission = admit(event)
        message_id = queue_action(event, admission)

        response = dict(admission)
        response["queue_message_id"] = message_id

        return {
            "statusCode": 200,
            "body": json.dumps(response, default=str),
        }

    except Exception as exc:
        # Governance/runtime failure must become attributable failure state.
        failure = {
            "receipt_id": str(uuid.uuid4()),
            "timestamp": utc(),
            "architecture_id": "SUPREME-MIND-59-FACULTY-UNIVERSE-V1",
            "state": "HOLD",
            "reason": "GOVERNOR_FAILURE",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

        try:
            receipt_table.put_item(Item=failure)
        except Exception:
            pass

        return {
            "statusCode": 503,
            "body": json.dumps(failure),
        }
