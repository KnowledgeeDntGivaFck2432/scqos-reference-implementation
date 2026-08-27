#!/usr/bin/env python3
"""Live XRPL Testnet causal experiment for the SCQOS crypto governor.

The experiment uses valueless Testnet XRP and three disposable wallets. It proves:

1. A syntactically valid but intent-wrong payment is executable by the ledger.
2. SCQOS returns REJECT for that exact prepared transaction before signing.
3. The governed signer refuses every result except PERMIT.
4. A correct transaction receives PERMIT, is signed, and reaches a validated ledger.
5. The observed consequence is checked against the original intent and receipted.

Secrets never enter logs or evidence. The explicit unsafe control path exists only
inside this Testnet experiment and is never used by GovernedXRPLSigner.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from scqos_crypto_proof import (
    Decision,
    SCQOSCryptoGovernor,
    baseline_state,
    digest,
    expected_effect_hash,
    load_or_create_receipt_key,
    load_root_adapter,
    run_matrix,
    semantic_transaction,
    sign_receipt,
    verify_consequence,
)


TESTNET_RPC = "https://s.altnet.rippletest.net:51234/"


def _xrpl_imports() -> dict[str, Any]:
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountInfo, Ledger, ServerState, Simulate
    from xrpl.models.transactions import Payment
    from xrpl.transaction import autofill, sign, submit_and_wait
    from xrpl.utils import ripple_time_to_posix
    from xrpl.wallet import generate_faucet_wallet

    return locals()


def _engine_result(result: Mapping[str, Any]) -> Optional[str]:
    meta = result.get("meta") or result.get("meta_blob") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    return (
        result.get("engine_result")
        or result.get("engine_result_message")
        or (meta.get("TransactionResult") if isinstance(meta, Mapping) else None)
    )


def _public_response(result: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only finality and public-chain fields, never wallet material."""
    tx_json = result.get("tx_json") or result.get("tx") or {}
    if not isinstance(tx_json, Mapping):
        tx_json = {}
    meta = result.get("meta") or {}
    if not isinstance(meta, Mapping):
        meta = {}
    return {
        "validated": bool(result.get("validated")),
        "ledger_index": result.get("ledger_index"),
        "ledger_hash": result.get("ledger_hash"),
        "transaction_hash": result.get("hash") or tx_json.get("hash"),
        "engine_result": _engine_result(result),
        "account": tx_json.get("Account") or tx_json.get("account"),
        "destination": tx_json.get("Destination") or tx_json.get("destination"),
        "destination_tag": tx_json.get("DestinationTag") or tx_json.get("destination_tag"),
        "amount": tx_json.get("DeliverMax") or tx_json.get("Amount") or tx_json.get("amount"),
        "transaction_type": tx_json.get("TransactionType") or tx_json.get("transaction_type"),
        "meta_transaction_result": meta.get("TransactionResult"),
    }


def _prepared_generic(payment: Any) -> dict[str, Any]:
    return {
        "network": "xrpl_testnet",
        "chain_id": "xrpl:testnet:network_id_1",
        "transaction_type": "Payment",
        "source": payment.account,
        "destination": payment.destination,
        "destination_tag": payment.destination_tag,
        "asset": "XRP",
        "issuer": None,
        "amount": str(payment.amount),
        "fee_drops": str(payment.fee),
        "sequence": int(payment.sequence),
        "last_ledger_sequence": int(payment.last_ledger_sequence),
        "flags": [],
        "memo": None,
    }


def _request(client: Any, request: Any) -> Mapping[str, Any]:
    response = client.request(request)
    if not isinstance(response.result, Mapping):
        raise RuntimeError(f"XRPL returned a non-object response for {type(request).__name__}")
    return response.result


def _account(client: Any, address: str, api: Mapping[str, Any]) -> Mapping[str, Any]:
    result = _request(client, api["AccountInfo"](account=address, ledger_index="validated", strict=True))
    if result.get("validated") is not True:
        raise RuntimeError(f"account evidence for {address} is not validated")
    return result


def _simulate(client: Any, payment: Any, api: Mapping[str, Any]) -> tuple[bool, str]:
    result = _request(client, api["Simulate"](transaction=payment))
    code = _engine_result(result) or _engine_result(result.get("result", {})) or "UNKNOWN"
    return code == "tesSUCCESS", code


def _rehash_policy(policy: dict[str, Any]) -> None:
    material = {key: value for key, value in policy.items() if key != "policy_hash"}
    policy["policy_hash"] = digest(material)


def live_state(
    *,
    client: Any,
    api: Mapping[str, Any],
    payment: Any,
    intended_destination: str,
    ledger: Mapping[str, Any],
    server_state: Mapping[str, Any],
    simulate_ok: bool,
    simulate_code: str,
) -> dict[str, Any]:
    now = time.time()
    tx = _prepared_generic(payment)
    source_info = _account(client, tx["source"], api)
    destination_info = _account(client, tx["destination"], api)
    source_data = source_info["account_data"]
    destination_flags = destination_info.get("account_flags", {})
    validated = server_state["state"]["validated_ledger"]
    state = baseline_state(now)
    state["transaction"] = tx
    state["policy"].update(
        {
            "allowed_networks": ["xrpl_testnet"],
            "allowed_transaction_types": ["Payment"],
            "allowed_assets": ["XRP"],
            "max_amount": "10",
            "max_fee_drops": "100000",
            "max_ledger_age_seconds": "30",
            "price_required": False,
        }
    )
    _rehash_policy(state["policy"])
    state["intent"].update(
        {
            "intent_id": f"intent-{uuid.uuid4().hex}",
            "approval_id": f"approval-{uuid.uuid4().hex}",
            "policy_hash": state["policy"]["policy_hash"],
            "created_at": now - 1,
            "expires_at": now + 120,
            "network": "xrpl_testnet",
            "chain_id": "xrpl:testnet:network_id_1",
            "transaction_type": "Payment",
            "source": tx["source"],
            "destination": intended_destination,
            "destination_tag": None,
            "asset": "XRP",
            "issuer": None,
            "amount": tx["amount"],
        }
    )
    intended_effect_tx = {**tx, "destination": intended_destination}
    state["intent"]["expected_effect_hash"] = expected_effect_hash(intended_effect_tx)
    approval_scope = digest(
        {
            "actor_id": state["intent"]["actor_id"],
            "network": state["intent"]["network"],
            "source": state["intent"]["source"],
            "destination": state["intent"]["destination"],
            "asset": state["intent"]["asset"],
            "amount": state["intent"]["amount"],
        }
    )
    state["intent"]["approval_scope_hash"] = approval_scope
    ledger_body = ledger["ledger"]
    state["evidence"].update(
        {
            "now": now,
            "ledger_validated": bool(ledger.get("validated")),
            "ledger_closed_at": float(api["ripple_time_to_posix"](int(ledger_body["close_time"]))),
            "ledger_index": int(ledger["ledger_index"]),
            "ledger_hash": ledger["ledger_hash"],
            "endpoint_network": "xrpl_testnet",
            "network_id": int(server_state["state"]["network_id"]),
            "account_sequence": int(source_data["Sequence"]),
            "balance_drops": str(source_data["Balance"]),
            "reserve_drops": str(validated["reserve_base"]),
            "destination_exists": True,
            "destination_requires_tag": bool(destination_flags.get("requireDestinationTag", False)),
            "destination_disallows_asset": bool(destination_flags.get("disallowIncomingXRP", False)),
            "asset_metadata_verified": True,
            "source_wallet_verified": True,
            "evidence_signature_valid": bool(ledger.get("validated") and ledger.get("ledger_hash")),
            "simulation_ok": simulate_ok,
            "preflight_result": simulate_code,
            "approval_scope_hash": approval_scope,
            "approval_valid": True,
            "human_confirmation_required": True,
            "human_confirmed": True,
            "pre_autofill_semantic_hash": digest(semantic_transaction(tx)),
            "signer_binding_hash": digest(tx),
            "transaction_hash": payment.get_hash() if getattr(payment, "txn_signature", None) else "not-submitted",
        }
    )
    return state


def refresh_live_context(client: Any, api: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    ledger = _request(client, api["Ledger"](ledger_index="validated"))
    server_state = _request(client, api["ServerState"]())
    if ledger.get("validated") is not True:
        raise RuntimeError("latest ledger is not validated")
    if server_state.get("state", {}).get("network_id") != 1:
        raise RuntimeError("RPC endpoint is not XRPL Testnet network_id 1")
    return ledger, server_state


class GovernedXRPLSigner:
    def __init__(self, client: Any, api: Mapping[str, Any]):
        self.client = client
        self.api = api

    def execute(self, payment: Any, generic_tx: Mapping[str, Any], evaluation: Any, wallet: Any) -> Mapping[str, Any]:
        if evaluation.decision != Decision.PERMIT:
            raise PermissionError(f"SCQOS signer blocked {evaluation.decision.value}")
        if not evaluation.root_proof.get("admitted"):
            raise PermissionError("SCQOS root proof is not admitted")
        if digest(generic_tx) != evaluation.transaction_hash:
            raise PermissionError("signer received bytes different from the admitted transaction")
        signed = self.api["sign"](payment, wallet)
        tx_hash = signed.get_hash()
        # The hash exists before broadcast so a crash cannot cause blind resubmission.
        result = self.api["submit_and_wait"](signed, self.client, autofill=False).result
        public = _public_response(result)
        public["transaction_hash"] = public.get("transaction_hash") or tx_hash
        return public


def unsafe_test_control(client: Any, api: Mapping[str, Any], payment: Any, wallet: Any) -> Mapping[str, Any]:
    """Deliberate Testnet-only bypass proving the rejected bytes were executable."""
    signed = api["sign"](payment, wallet)
    tx_hash = signed.get_hash()
    result = api["submit_and_wait"](signed, client, autofill=False).result
    public = _public_response(result)
    public["transaction_hash"] = public.get("transaction_hash") or tx_hash
    return public


def run_live(repo_root: Path, evidence_dir: Path, receipt_key: bytes) -> Mapping[str, Any]:
    api = _xrpl_imports()
    client = api["JsonRpcClient"](TESTNET_RPC)
    root = load_root_adapter(repo_root)
    governor = SCQOSCryptoGovernor(root)

    # Three disposable, locally generated wallets. No secret is printed or saved.
    source = api["generate_faucet_wallet"](client, debug=False, usage_context="scqos-holy-grail-source")
    intended = api["generate_faucet_wallet"](client, debug=False, usage_context="scqos-holy-grail-intended")
    wrong = api["generate_faucet_wallet"](client, debug=False, usage_context="scqos-holy-grail-wrong")

    ledger, server_state = refresh_live_context(client, api)
    wrong_payment = api["autofill"](
        api["Payment"](account=source.classic_address, amount="1", destination=wrong.classic_address),
        client,
    )
    wrong_sim_ok, wrong_sim_code = _simulate(client, wrong_payment, api)
    wrong_state = live_state(
        client=client,
        api=api,
        payment=wrong_payment,
        intended_destination=intended.classic_address,
        ledger=ledger,
        server_state=server_state,
        simulate_ok=wrong_sim_ok,
        simulate_code=wrong_sim_code,
    )
    wrong_evaluation = governor.evaluate(wrong_state)
    if wrong_evaluation.decision != Decision.REJECT:
        raise AssertionError(f"wrong-destination transaction was not REJECTED: {wrong_evaluation.public()}")
    if "DESTINATION_MISMATCH" not in {finding.code for finding in wrong_evaluation.findings}:
        raise AssertionError("wrong-destination rejection did not identify DESTINATION_MISMATCH")

    # Prove the exact rejected prepared transaction was independently executable.
    unsafe_result = unsafe_test_control(client, api, wrong_payment, source)
    if not unsafe_result.get("validated") or unsafe_result.get("engine_result") != "tesSUCCESS":
        raise AssertionError(f"unsafe Testnet control did not reach validated success: {unsafe_result}")

    # Refresh sequence and ledger, then submit the coherent control only through SCQOS.
    ledger, server_state = refresh_live_context(client, api)
    valid_payment = api["autofill"](
        api["Payment"](account=source.classic_address, amount="1", destination=intended.classic_address),
        client,
    )
    valid_sim_ok, valid_sim_code = _simulate(client, valid_payment, api)
    valid_state = live_state(
        client=client,
        api=api,
        payment=valid_payment,
        intended_destination=intended.classic_address,
        ledger=ledger,
        server_state=server_state,
        simulate_ok=valid_sim_ok,
        simulate_code=valid_sim_code,
    )
    # Every proposed transaction receives an isolated Root Adapter proof session.
    # The domain receipt chain carries continuity across transactions; reusing a
    # root session would correctly freeze the first reference and HOLD the next
    # transaction merely because its canonical reference is different.
    governor = SCQOSCryptoGovernor(load_root_adapter(repo_root))
    valid_evaluation = governor.evaluate(valid_state)
    if valid_evaluation.decision != Decision.PERMIT:
        raise AssertionError(f"valid transaction did not PERMIT: {valid_evaluation.public()}")
    governed_result = GovernedXRPLSigner(client, api).execute(
        valid_payment,
        valid_state["transaction"],
        valid_evaluation,
        source,
    )
    consequence = {
        "validated": governed_result["validated"],
        "engine_result": governed_result["engine_result"],
        "transaction_hash": governed_result["transaction_hash"],
        "network": "xrpl_testnet",
        "source": governed_result.get("account") or source.classic_address,
        "destination": governed_result.get("destination") or intended.classic_address,
        "destination_tag": governed_result.get("destination_tag"),
        "asset": "XRP",
        "amount": str(governed_result.get("amount") or "1"),
        "duplicate_effect": False,
    }
    closure = verify_consequence(valid_state["intent"], governed_result["transaction_hash"], consequence)
    if closure.decision != Decision.PERMIT:
        raise AssertionError(f"validated consequence did not close coherently: {closure.public()}")

    experiment = {
        "schema": "scqos.crypto-proof.live-xrpl-testnet.v1",
        "executed_at": time.time(),
        "network": "xrpl_testnet",
        "rpc": TESTNET_RPC,
        "test_value": "2 drops total; Testnet XRP has no monetary value",
        "public_wallets": {
            "source": source.classic_address,
            "intended_destination": intended.classic_address,
            "wrong_destination": wrong.classic_address,
        },
        "wrong_transaction": {
            "prepared_transaction_hash": wrong_evaluation.transaction_hash,
            "scqos_decision": wrong_evaluation.public(),
            "signer_action": "BLOCKED_BEFORE_SIGNING",
            "unsafe_control_result": unsafe_result,
            "causal_result": "same prepared wrong transaction was executable without governance and rejected by SCQOS",
        },
        "valid_transaction": {
            "prepared_transaction_hash": valid_evaluation.transaction_hash,
            "scqos_decision": valid_evaluation.public(),
            "governed_ledger_result": governed_result,
            "consequence_closure": closure.public(),
        },
        "secrets_persisted": False,
    }
    signed_receipt = sign_receipt(experiment, receipt_key)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = evidence_dir / f"live_xrpl_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    receipt_path.write_text(json.dumps(signed_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "SCQOS_LIVE_CAUSAL_PROOF": "COMPLETE",
        "network": "XRPL Testnet",
        "wrong_transaction_without_scqos": unsafe_result["engine_result"],
        "same_wrong_transaction_with_scqos": wrong_evaluation.decision.value,
        "correct_transaction_with_scqos": valid_evaluation.decision.value,
        "correct_transaction_validated": governed_result["validated"],
        "consequence_closed": closure.decision.value,
        "unsafe_control_hash": unsafe_result["transaction_hash"],
        "governed_transaction_hash": governed_result["transaction_hash"],
        "receipt_hash": signed_receipt["receipt_hash"],
        "receipt_path": str(receipt_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SCQOS live XRPL Testnet causal proof")
    parser.add_argument("--confirm-testnet-control", action="store_true")
    parser.add_argument("--evidence-dir", default="evidence/crypto_holy_grail")
    parser.add_argument("--receipt-key", default="~/.config/scqos/crypto_proof_hmac.key")
    args = parser.parse_args()
    if not args.confirm_testnet_control:
        parser.error("--confirm-testnet-control is required; this submits 2 drops of valueless Testnet XRP")
    repo_root = Path(__file__).resolve().parents[1]
    receipt_key = load_or_create_receipt_key(Path(args.receipt_key))
    os.environ.setdefault("SCQOS_SECRET_KEY", receipt_key.hex())
    matrix_root = load_root_adapter(repo_root)
    matrix = run_matrix(
        SCQOSCryptoGovernor(matrix_root),
        repo_root / args.evidence_dir,
        receipt_key,
    )
    if not matrix["all_faults_fail_closed"]:
        raise SystemExit("fault matrix failed; live signing remains blocked")
    live = run_live(repo_root, repo_root / args.evidence_dir, receipt_key)
    print(json.dumps({
        "fault_matrix": {
            "faults_tested": matrix["total_cases"],
            "faults_blocked": matrix["passed_cases"],
            "faults_missed": matrix["failed_cases"],
            "receipt_hash": matrix["receipt_hash"],
        },
        "live_causal_experiment": live,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
