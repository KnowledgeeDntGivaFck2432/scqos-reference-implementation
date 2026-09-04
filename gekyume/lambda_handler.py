import json
from gekyume.gekyume_core import Gekyume, new_transaction

_engine = Gekyume()

def lambda_handler(event, context):
    payload = event if isinstance(event, dict) else {}

    if "body" in payload:
        body = payload.get("body")
        if isinstance(body, str):
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
        elif isinstance(body, dict):
            payload = body

    tx = payload.get("transaction")

    if tx is None:
        tx = new_transaction(
            _engine,
            amount=int(payload.get("amount", 1_000_000_000))
        )

    receipt = _engine.execute(tx)

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({
            "system": "GEKYUME",
            "decision": receipt["decision"],
            "reason": receipt["reason"],
            "executed": receipt["consequence"]["executed"],
            "transaction_hash": receipt["transaction_hash"],
            "receipt_hash": receipt["receipt_hash"]
        })
    }
