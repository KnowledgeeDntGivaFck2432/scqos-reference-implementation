"""SCQOS Public Execution Challenge v1 — AWS Lambda runtime.

The public endpoint is shadow-only: PERMIT means a proposed transition is
admissible under the frozen contract. This service never performs the proposed
external action. Every decision is canonicalized, KMS-signed, and persisted.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Tuple

import scqos_supreme_stack as sc

BASE = Path(__file__).resolve().parent
CONTRACT = json.loads((BASE / "contract.json").read_text())
CONTRACT_ID = CONTRACT["contract_id"]
CONTRACT_HASH = hashlib.sha256(sc.canonical_bytes(CONTRACT)).hexdigest()
SECRET = os.environ.get("SCQOS_KERNEL_SECRET", "local-test-only")
TABLE = os.environ.get("SCQOS_RECEIPTS_TABLE", "")
KMS_KEY = os.environ.get("SCQOS_KMS_KEY_ID", "")
TEST_MODE = os.environ.get("SCQOS_TEST_MODE") == "1"
SOURCE_COMMIT = os.environ.get("SCQOS_SOURCE_COMMIT", "unknown")
XRPL_URLS = ("https://xrplcluster.com/", "https://s1.ripple.com:51234/")

CASES = (
    ("valid", "PERMIT"),
    ("authority_mismatch", "REJECT"),
    ("missing_evidence", "HOLD"),
    ("stale_evidence", "HOLD"),
    ("reference_mismatch", "REJECT"),
    ("effect_mismatch", "REJECT"),
)


def _sha(value: Dict[str, Any]) -> str:
    return hashlib.sha256(sc.canonical_bytes(value)).hexdigest()


def _base_transition(now: float | None = None) -> Dict[str, Any]:
    now = now or time.time()
    return {
        "tenant_id": "public-challenge",
        "external_system": "ai_tool_call",
        "subject": "production/change-control/api-v1",
        "authority": {"principal_id": "challenge-operator", "scope": "challenge:execute"},
        "intent": {"action": "deploy", "target": "api-v1", "expected_effect": "version:v2"},
        "evidence": {"observed_at": now, "source": "signed-ci", "reference_id": "build-7f3", "target": "api-v1"},
        "current_state": {"version": "v1", "healthy": True},
        "proposed_transition": {"action": "deploy", "target": "api-v1", "effect": "version:v2", "reference_id": "build-7f3"},
        "expected_consequence": {"effect": "version:v2"},
    }


def case_transition(case_id: str, now: float | None = None) -> Dict[str, Any]:
    value = _base_transition(now)
    if case_id == "authority_mismatch":
        value["authority"]["scope"] = "read:only"
    elif case_id == "missing_evidence":
        value["evidence"] = {}
    elif case_id == "stale_evidence":
        value["evidence"]["observed_at"] -= 3600
    elif case_id == "reference_mismatch":
        value["proposed_transition"]["reference_id"] = "build-unknown"
    elif case_id == "effect_mismatch":
        value["proposed_transition"]["effect"] = "version:v3"
    elif case_id != "valid":
        raise ValueError("unknown case_id")
    return value


def _contract_decision(req: Dict[str, Any], now: float) -> Tuple[str, str, str]:
    required = ("tenant_id", "external_system", "subject", "authority", "intent", "evidence", "current_state", "proposed_transition", "expected_consequence")
    if any(k not in req for k in required):
        return "HOLD", "CONTRACT", "required proposition field missing"
    authority, intent, evidence, proposal = req["authority"], req["intent"], req["evidence"], req["proposed_transition"]
    if authority.get("scope") != CONTRACT["required_authority_scope"]:
        return "REJECT", "AUTHORITY", "authority scope does not authorize execution"
    if any(k not in evidence for k in ("observed_at", "source", "reference_id", "target")):
        return "HOLD", "EVIDENCE", "required evidence is incomplete"
    try:
        age = now - float(evidence["observed_at"])
    except (TypeError, ValueError):
        return "HOLD", "TIME", "evidence timestamp is not usable"
    if age < -CONTRACT["maximum_clock_skew_seconds"] or age > CONTRACT["maximum_evidence_age_seconds"]:
        return "HOLD", "TIME", "evidence is outside the admissible time window"
    if proposal.get("target") != intent.get("target") or proposal.get("target") != evidence.get("target"):
        return "REJECT", "REFERENCE", "proposed target does not match intent and evidence"
    if proposal.get("reference_id") != evidence.get("reference_id"):
        return "REJECT", "REFERENCE", "proposed reference is not evidenced"
    if proposal.get("action") != intent.get("action"):
        return "REJECT", "ALIGNMENT", "proposed action does not match declared intent"
    if proposal.get("effect") != intent.get("expected_effect") or proposal.get("effect") != req["expected_consequence"].get("effect"):
        return "REJECT", "CAUSALITY", "proposed effect does not match expected consequence"
    return "PERMIT", "KERNEL", "proposition is admissible for nine-gate evaluation"


def _kernel(req: Dict[str, Any], transition_id: str) -> Dict[str, str]:
    module, node = "control_surface", "public-challenge-node"
    common = {"contract_id": CONTRACT_ID, "transition_id": transition_id, **req}
    tg = sc.TimeGate(max_drift_ms=5000.0); tr = tg.check(tg.next_state(module, common))
    if not tr.coherent: raise RuntimeError("TIME: " + tr.reason)
    cont = sc.ContinuityGate(SECRET, node).gate(transition_id, "continuity", module, {**common, "time_hash": tr.state_hash})
    align = sc.AlignmentGate(SECRET, node, enforce_substrate=False).gate(transition_id, "alignment", module, intent=json.dumps(req["intent"], sort_keys=True), declared_objective="operate_control_surface", causal_trigger_hash=cont.state_hash, boundary_domain="trusted_runtime", reference_context=req["evidence"], payload=common)
    genesis_gate = sc.GenesisGate(SECRET, node)
    genesis = genesis_gate.gate(transition_id, "genesis", module, origin_id=f'{req["tenant_id"]}:{req["subject"]}', creator_id=req["authority"]["principal_id"], source_type="system", source_hash=genesis_gate.source_hash(req["evidence"]), payload=common)
    boundary = sc.BoundaryGate(SECRET, node).gate(transition_id, "boundary", module, common)
    reference = sc.ReferenceGate(SECRET, node).gate(transition_id, "reference", module, reference_hash=_sha({"evidence": req["evidence"], "current_state": req["current_state"]}), payload=common)
    cause_hash = _sha({"intent": req["intent"], "current_state": req["current_state"], "proposal": req["proposed_transition"], "reference_hash": reference.state_hash})
    causality = sc.CausalityGate(SECRET, node).gate(transition_id, "causality", module, cause_id=transition_id + ":cause", cause_hash=cause_hash, effect_id=transition_id + ":effect", payload=common)
    cg = sc.ConsciousnessGate(SECRET, node, observer_id="public-observer", substrate_id="aws-lambda", enforce_substrate=False)
    observation = {"request": common, "proofs": [tr.state_hash, cont.state_hash, align.state_hash, genesis.state_hash, boundary.state_hash, reference.state_hash, causality.state_hash]}
    conscious = cg.gate(transition_id, "consciousness", module, observation_hash=cg.observation_hash(observation), payload=observation)
    coherent = sc.CoherenceGate(SECRET, node).gate(transition_id, "coherence", module, time_hash=tr.state_hash, continuity_hash=cont.state_hash, alignment_hash=align.state_hash, genesis_hash=genesis.state_hash, boundary_hash=boundary.state_hash, reference_hash=reference.state_hash, causality_hash=causality.state_hash, consciousness_hash=conscious.state_hash, payload=common)
    return {"time": tr.state_hash, "continuity": cont.state_hash, "alignment": align.state_hash, "genesis": genesis.state_hash, "boundary": boundary.state_hash, "reference": reference.state_hash, "causality": causality.state_hash, "consciousness": conscious.state_hash, "coherence": coherent.state_hash}


def _aws():
    import boto3
    return boto3


def _sign_and_store(receipt: Dict[str, Any]) -> Dict[str, Any]:
    body = sc.canonical_bytes(receipt)
    receipt_id = hashlib.sha256(body).hexdigest()
    if TEST_MODE:
        signature = base64.b64encode(hashlib.sha256(b"TEST-ONLY" + body).digest()).decode()
        algorithm = "TEST_ONLY_SHA256"
    else:
        if not KMS_KEY or not TABLE:
            raise RuntimeError("KMS signing key and receipt table are required")
        kms = _aws().client("kms")
        result = kms.sign(KeyId=KMS_KEY, Message=hashlib.sha256(body).digest(), MessageType="DIGEST", SigningAlgorithm="ECDSA_SHA_256")
        signature, algorithm = base64.b64encode(result["Signature"]).decode(), "ECDSA_SHA_256"
    envelope = {**receipt, "receipt_id": receipt_id, "canonicalization": "RFC8785-JCS+SCQOS-NFC1", "signature": signature, "signature_algorithm": algorithm}
    if not TEST_MODE:
        _aws().resource("dynamodb").Table(TABLE).put_item(Item={"receipt_id": receipt_id, "created_at": str(receipt["created_at"]), "decision": receipt["decision"], "receipt_json": json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)})
    return envelope


def evaluate(req: Dict[str, Any], now: float | None = None) -> Dict[str, Any]:
    now = now or time.time()
    request_hash = _sha(req)
    transition_id = _sha({"contract_hash": CONTRACT_HASH, "request_hash": request_hash, "nonce": uuid.uuid4().hex})
    decision, boundary, reason = _contract_decision(req, now)
    proofs: Dict[str, str] = {}
    if decision == "PERMIT":
        try:
            proofs = _kernel(req, transition_id)
        except Exception as exc:
            decision, boundary, reason = "HOLD", "KERNEL", f"kernel could not establish coherence: {exc}"
    receipt = {
        "schema": "scqos.public-execution-challenge.receipt.v1", "contract_id": CONTRACT_ID,
        "contract_hash": CONTRACT_HASH, "source_commit": SOURCE_COMMIT, "transition_id": transition_id,
        "request_hash": request_hash, "decision": decision, "release_authorized": decision == "PERMIT",
        "execution_mode": "SHADOW_ONLY", "external_side_effects": False, "decision_boundary": boundary,
        "reason": reason, "gate_proofs": proofs, "created_at": now,
    }
    return _sign_and_store(receipt)


def run_matrix() -> Dict[str, Any]:
    started = time.time()
    results = []
    for case_id, expected in CASES:
        receipt = evaluate(case_transition(case_id, started), started)
        results.append({"case_id": case_id, "expected": expected, "actual": receipt["decision"], "pass": receipt["decision"] == expected, "receipt_id": receipt["receipt_id"]})
    return {"challenge": CONTRACT_ID, "all_pass": all(r["pass"] for r in results), "passed": sum(r["pass"] for r in results), "total": len(results), "results": results, "source_commit": SOURCE_COMMIT, "contract_hash": CONTRACT_HASH}


def _xrpl(tx_hash: str) -> Dict[str, Any]:
    payload = json.dumps({"method": "tx", "params": [{"transaction": tx_hash, "binary": False}]}).encode()
    last_error = "no XRPL endpoint attempted"
    for endpoint in XRPL_URLS:
        try:
            request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=4) as response:
                result = json.loads(response.read())["result"]
            return {"hash": tx_hash, "validated": result.get("validated"), "ledger_index": result.get("ledger_index"), "result": result.get("meta", {}).get("TransactionResult"), "source": endpoint}
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error)


def evidence() -> Dict[str, Any]:
    txs = ["C474989DFE4354CBB9A1F0B977BAF473EE91345DC6387F84C80F5A3B5F1110F9", "D13EDAED96354DD2CF16382BA815367A37F5408D64B362FC24C19DEDF6775AD7"]
    out: Dict[str, Any] = {"checked_at": time.time(), "source_commit": SOURCE_COMMIT, "contract_hash": CONTRACT_HASH, "xrpl": [], "standards": CONTRACT["live_reference_sources"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {tx: pool.submit(_xrpl, tx) for tx in txs}
        for tx in txs:
            try: out["xrpl"].append(futures[tx].result())
            except Exception as exc: out["xrpl"].append({"hash": tx, "error": str(exc)})
    if not TEST_MODE:
        try:
            ident = _aws().client("sts").get_caller_identity()
            out["aws"] = {"account_fingerprint": hashlib.sha256(ident["Account"].encode()).hexdigest()[:16], "region": os.environ.get("AWS_REGION"), "runtime": os.environ.get("AWS_EXECUTION_ENV")}
        except Exception as exc: out["aws"] = {"error": str(exc)}
    return out


def _response(status: int, body: Any, content_type: str = "application/json") -> Dict[str, Any]:
    payload = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    return {"statusCode": status, "headers": {"content-type": content_type, "cache-control": "no-store", "access-control-allow-origin": "*"}, "body": payload}


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    path = event.get("rawPath", "/"); method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    try:
        if method == "GET" and path == "/": return _response(200, (BASE / "index.html").read_text(), "text/html; charset=utf-8")
        if method == "GET" and path == "/v1/health": return _response(200, {"status": "operational", "contract_id": CONTRACT_ID, "contract_hash": CONTRACT_HASH, "source_commit": SOURCE_COMMIT, "mode": "SHADOW_ONLY"})
        if method == "GET" and path == "/v1/evidence": return _response(200, evidence())
        if method == "GET" and path.startswith("/v1/receipt/"):
            receipt_id = path.rsplit("/", 1)[-1]
            if len(receipt_id) != 64 or any(c not in "0123456789abcdef" for c in receipt_id):
                return _response(400, {"error": "invalid receipt id"})
            if TEST_MODE: return _response(404, {"error": "test receipts are not persisted"})
            item = _aws().resource("dynamodb").Table(TABLE).get_item(Key={"receipt_id": receipt_id}, ConsistentRead=True).get("Item")
            return _response(200, json.loads(item["receipt_json"])) if item else _response(404, {"error": "receipt not found"})
        if method == "GET" and path == "/v1/public-key":
            if TEST_MODE: return _response(200, {"algorithm": "TEST_ONLY_SHA256"})
            key = _aws().client("kms").get_public_key(KeyId=KMS_KEY)
            return _response(200, {"algorithm": "ECDSA_SHA_256", "key_spec": key["KeySpec"], "public_key_der_base64": base64.b64encode(key["PublicKey"]).decode()})
        if method == "POST" and path == "/v1/challenge":
            body = json.loads(event.get("body") or "{}")
            req = case_transition(body["case_id"]) if "case_id" in body else body.get("transition", body)
            return _response(200, evaluate(req))
        if method == "POST" and path == "/v1/run-matrix": return _response(200, run_matrix())
        return _response(404, {"error": "route not found"})
    except (ValueError, KeyError, json.JSONDecodeError) as exc: return _response(400, {"error": str(exc)})
    except Exception as exc: return _response(500, {"error": "fail-closed", "detail": str(exc)})
