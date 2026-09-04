"""Lambda Function URL API for the SCQOS live sports analysis product."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

try:
    import boto3
except ImportError:  # Pure contract/UI tests do not require the AWS SDK.
    boto3 = None

from .canonical import receipt_sha256, sha256
from .contract import CONTRACT_ID
from .prompt import build_governor_event


REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
TASK_ID = re.compile(r"^[0-9a-fA-F-]{36}$")
HTML = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")

_lambda = None
_state = None
_receipts = None


def _env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError("CONFIGURATION_MISSING:" + name)
    return value


def _clients():
    global _lambda, _state, _receipts
    if _lambda is None:
        if boto3 is None:
            raise RuntimeError("BOTO3_NOT_AVAILABLE")
        _lambda = boto3.client("lambda", region_name=REGION)
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _state = ddb.Table(_env("SUPREME_MIND_TABLE"))
        _receipts = ddb.Table(_env("SUPREME_MIND_RECEIPT_TABLE"))
    return _lambda, _state, _receipts


def _response(status: int, body: Any, *, content_type: str = "application/json") -> dict[str, Any]:
    encoded = body if isinstance(body, str) else json.dumps(body, default=str, ensure_ascii=False)
    return {
        "statusCode": status,
        "headers": {
            "content-type": content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""),
            "cache-control": "no-store",
            "content-security-policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
            "referrer-policy": "no-referrer",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
        },
        "body": encoded,
    }


def _headers(event: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in (event.get("headers") or {}).items()}


def _authorized(event: Mapping[str, Any]) -> bool:
    supplied = _headers(event).get("x-scqos-key", "")
    expected = os.getenv("SCQOS_SPORTS_ACCESS_KEY_SHA256", "")
    actual = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
    return bool(supplied and expected and hmac.compare_digest(actual, expected))


def _json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _submit(event: Mapping[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
        analysis_date = str(body.get("analysis_date", ""))
        matchup = str(body.get("matchup", ""))
        max_events = int(body.get("max_events", 5))
        governor_event = build_governor_event(
            analysis_date=analysis_date,
            max_events=max_events,
            matchup=matchup,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc) or "INVALID_REQUEST"})
    lambda_client, _, _ = _clients()
    response = lambda_client.invoke(
        FunctionName=_env("SUPREME_MIND_GOVERNOR_FUNCTION"),
        InvocationType="RequestResponse",
        Payload=json.dumps(governor_event).encode("utf-8"),
    )
    envelope = json.loads(response["Payload"].read())
    governor_body = _json_field(envelope.get("body")) or {}
    if governor_body.get("state") != "PERMIT" or not governor_body.get("receipt_id"):
        return _response(409, {"error": "GOVERNOR_DID_NOT_ADMIT", "admission": governor_body})
    return _response(
        202,
        {
            "state": "QUEUED",
            "task_id": governor_body["receipt_id"],
            "admission_receipt_id": governor_body["receipt_id"],
            "contract": CONTRACT_ID,
        },
    )


def _task(task_id: str) -> dict[str, Any]:
    if not TASK_ID.fullmatch(task_id):
        return _response(400, {"error": "INVALID_TASK_ID"})
    _, state, receipts = _clients()
    rows = state.query(
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": "TASK#" + task_id},
        ConsistentRead=True,
    ).get("Items", [])
    if not rows:
        return _response(200, {"state": "QUEUED", "task_id": task_id})
    terminal = [row for row in rows if row.get("state") in ("COMPLETED", "FAILED", "REJECT")]
    row = max(terminal or rows, key=lambda item: str(item.get("completed_at") or item.get("started_at") or ""))
    public = {
        "state": row.get("state"),
        "task_id": task_id,
        "decision_state": row.get("decision_state"),
        "decision_reason": row.get("decision_reason"),
        "summary": row.get("summary"),
        "error_type": row.get("error_type"),
        "error": row.get("error"),
    }
    receipt_id = row.get("consequence_receipt_id")
    if row.get("state") != "COMPLETED" or not receipt_id:
        return _response(200, public)
    receipt = receipts.get_item(
        Key={"receipt_id": receipt_id}, ConsistentRead=True
    ).get("Item")
    if not receipt:
        return _response(502, {"error": "CONSEQUENCE_RECEIPT_MISSING", **public})
    claimed = receipt.get("receipt_sha256")
    actual = receipt_sha256(receipt)
    if not claimed or not hmac.compare_digest(str(claimed), actual):
        return _response(502, {"error": "CONSEQUENCE_RECEIPT_HASH_MISMATCH", **public})
    sports_decision = _json_field(receipt.get("sports_decision")) or {}
    internal_claim = sports_decision.get("receipt_sha256")
    internal_actual = sha256({key: value for key, value in sports_decision.items() if key != "receipt_sha256"})
    if not internal_claim or not hmac.compare_digest(str(internal_claim), internal_actual):
        return _response(502, {"error": "SPORTS_DECISION_HASH_MISMATCH", **public})
    public.update(
        {
            "receipt_verified": True,
            "consequence_receipt_id": receipt_id,
            "consequence_receipt_sha256": claimed,
            "sports_analysis": _json_field(receipt.get("sports_analysis")) or {},
            "sports_decision": sports_decision,
        }
    )
    return _response(200, public)


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    request = event.get("requestContext") or {}
    http = request.get("http") or {}
    method = str(http.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(event.get("rawPath") or event.get("path") or "/")
    if method == "GET" and path == "/":
        return _response(200, HTML, content_type="text/html")
    if method == "GET" and path == "/api/health":
        return _response(200, {"state": "READY", "contract": CONTRACT_ID})
    if not _authorized(event):
        return _response(401, {"error": "ACCESS_KEY_REQUIRED"})
    try:
        if method == "POST" and path == "/api/analyze":
            return _submit(event)
        if method == "GET" and path.startswith("/api/analysis/"):
            return _task(path.rsplit("/", 1)[-1])
        return _response(404, {"error": "NOT_FOUND"})
    except Exception as exc:
        return _response(500, {"error": "SERVER_FAILURE", "detail": type(exc).__name__})
