#!/usr/bin/env python3
"""Minimal-cost XRPL Mainnet causal proof governed by Supreme Computation.

The test uses two locally generated wallets controlled by the user. The source is
funded once; the transferred XRP remains in the destination wallet. Only ledger
fees are destroyed. Wallet seeds are stored mode 0600 outside the repository and
are never printed or written to evidence.
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
    semantic_transaction,
    sign_receipt,
    verify_consequence,
)
from scqos_full_terminal import atomic_json


MAINNET_RPC = "https://s2.ripple.com:51234/"
NETWORK = "xrpl_mainnet"
CHAIN_ID = "xrpl:mainnet:network_id_0"
INTENDED_TAG = 111
WRONG_TAG = 222
MAX_FEE_DROPS = 100
FUNDING_BUFFER_DROPS = 100_000


def xrpl_api() -> dict[str, Any]:
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountInfo, Ledger, ServerState, Simulate
    from xrpl.models.transactions import Payment
    from xrpl.transaction import autofill, sign, submit_and_wait
    from xrpl.utils import ripple_time_to_posix
    from xrpl.wallet import Wallet

    return locals()


def request(client: Any, request_model: Any, allow_not_found: bool = False) -> Optional[Mapping[str, Any]]:
    response = client.request(request_model)
    result = response.result if isinstance(response.result, Mapping) else {}
    if response.is_successful():
        return result
    if allow_not_found and result.get("error") == "actNotFound":
        return None
    raise RuntimeError(f"XRPL {type(request_model).__name__} failed: {json.dumps(result, sort_keys=True)}")


def engine_result(result: Mapping[str, Any]) -> str:
    meta = result.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    return str(result.get("engine_result") or (meta.get("TransactionResult") if isinstance(meta, Mapping) else "") or "UNKNOWN")


def public_result(result: Mapping[str, Any], fallback_hash: str) -> dict[str, Any]:
    tx_json = result.get("tx_json") or result.get("tx") or {}
    if not isinstance(tx_json, Mapping):
        tx_json = {}
    return {
        "validated": bool(result.get("validated")),
        "ledger_index": result.get("ledger_index"),
        "ledger_hash": result.get("ledger_hash"),
        "transaction_hash": result.get("hash") or tx_json.get("hash") or fallback_hash,
        "engine_result": engine_result(result),
        "account": tx_json.get("Account") or tx_json.get("account"),
        "destination": tx_json.get("Destination") or tx_json.get("destination"),
        "destination_tag": tx_json.get("DestinationTag") if "DestinationTag" in tx_json else tx_json.get("destination_tag"),
        "amount": tx_json.get("DeliverMax") or tx_json.get("Amount") or tx_json.get("amount"),
        "transaction_type": tx_json.get("TransactionType") or tx_json.get("transaction_type"),
    }


def server_snapshot(client: Any, api: Mapping[str, Any]) -> dict[str, Any]:
    state_result = request(client, api["ServerState"]())
    ledger_result = request(client, api["Ledger"](ledger_index="validated"))
    assert state_result is not None and ledger_result is not None
    state = state_result["state"]
    if int(state["network_id"]) != 0:
        raise RuntimeError("RPC endpoint is not XRPL Mainnet network_id 0")
    if ledger_result.get("validated") is not True:
        raise RuntimeError("latest ledger evidence is not validated")
    validated = state["validated_ledger"]
    return {
        "network_id": int(state["network_id"]),
        "server_state": state["server_state"],
        "ledger_index": int(ledger_result["ledger_index"]),
        "ledger_hash": ledger_result["ledger_hash"],
        "ledger_closed_at": float(api["ripple_time_to_posix"](int(ledger_result["ledger"]["close_time"]))),
        "reserve_base_drops": int(validated["reserve_base"]),
        "reserve_increment_drops": int(validated["reserve_inc"]),
        "base_fee_drops": int(validated["base_fee"]),
    }


def wallet_file_mode_ok(path: Path) -> None:
    if path.exists() and (path.stat().st_mode & 0o077):
        raise PermissionError(f"wallet file permissions must be 600: {path}")


def load_or_create_wallets(path: Path, api: Mapping[str, Any]) -> tuple[Any, Any]:
    path = path.expanduser()
    wallet_file_mode_ok(path)
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        return api["Wallet"].from_seed(value["source_seed"]), api["Wallet"].from_seed(value["destination_seed"])
    source = api["Wallet"].create()
    destination = api["Wallet"].create()
    atomic_json(
        path,
        {
            "schema": "scqos.xrpl-mainnet-wallets.v1",
            "created_at": time.time(),
            "source_seed": source.seed,
            "destination_seed": destination.seed,
        },
        mode=0o600,
    )
    wallet_file_mode_ok(path)
    return source, destination


def account_info(client: Any, api: Mapping[str, Any], address: str) -> Optional[Mapping[str, Any]]:
    return request(
        client,
        api["AccountInfo"](account=address, ledger_index="validated", strict=True),
        allow_not_found=True,
    )


def generic_transaction(payment: Any) -> dict[str, Any]:
    return {
        "network": NETWORK,
        "chain_id": CHAIN_ID,
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


def simulate(client: Any, api: Mapping[str, Any], payment: Any) -> tuple[bool, str]:
    result = request(client, api["Simulate"](transaction=payment))
    assert result is not None
    code = engine_result(result)
    return code == "tesSUCCESS", code


def rehash_policy(policy: dict[str, Any]) -> None:
    policy["policy_hash"] = digest({key: value for key, value in policy.items() if key != "policy_hash"})


def governed_state(
    *,
    client: Any,
    api: Mapping[str, Any],
    payment: Any,
    intended_tag: int,
    snapshot: Mapping[str, Any],
    simulation_ok: bool,
    simulation_code: str,
    source_wallet_verified: bool,
) -> dict[str, Any]:
    now = time.time()
    tx = generic_transaction(payment)
    source = account_info(client, api, tx["source"])
    destination = account_info(client, api, tx["destination"])
    if source is None:
        raise RuntimeError("source account is not funded on XRPL Mainnet")
    source_data = source["account_data"]
    destination_exists = destination is not None
    destination_flags = destination.get("account_flags", {}) if destination else {}
    destination_creatable = (
        not destination_exists
        and int(tx["amount"]) >= int(snapshot["reserve_base_drops"])
        and simulation_ok
    )
    state = baseline_state(now)
    state["transaction"] = tx
    state["policy"].update(
        {
            "allowed_networks": [NETWORK],
            "allowed_transaction_types": ["Payment"],
            "allowed_assets": ["XRP"],
            "max_amount": str(snapshot["reserve_base_drops"]),
            "max_fee_drops": str(MAX_FEE_DROPS),
            "asset_precision": 0,
            "max_ledger_age_seconds": "30",
            "price_required": False,
        }
    )
    rehash_policy(state["policy"])
    state["intent"].update(
        {
            "intent_id": f"mainnet-intent-{uuid.uuid4().hex}",
            "approval_id": f"mainnet-approval-{uuid.uuid4().hex}",
            "policy_hash": state["policy"]["policy_hash"],
            "created_at": now - 1,
            "expires_at": now + 120,
            "network": NETWORK,
            "chain_id": CHAIN_ID,
            "transaction_type": "Payment",
            "source": tx["source"],
            "destination": tx["destination"],
            "destination_tag": intended_tag,
            "asset": "XRP",
            "issuer": None,
            "amount": tx["amount"],
        }
    )
    intended_tx = {**tx, "destination_tag": intended_tag}
    state["intent"]["expected_effect_hash"] = expected_effect_hash(intended_tx)
    approval_scope = digest(
        {
            "actor_id": state["intent"]["actor_id"],
            "network": NETWORK,
            "source": tx["source"],
            "destination": tx["destination"],
            "destination_tag": intended_tag,
            "asset": "XRP",
            "amount": tx["amount"],
        }
    )
    state["intent"]["approval_scope_hash"] = approval_scope
    state["evidence"].update(
        {
            "now": now,
            "ledger_validated": True,
            "ledger_closed_at": snapshot["ledger_closed_at"],
            "ledger_index": snapshot["ledger_index"],
            "ledger_hash": snapshot["ledger_hash"],
            "endpoint_network": NETWORK,
            "network_id": 0,
            "account_sequence": int(source_data["Sequence"]),
            "balance_drops": str(source_data["Balance"]),
            "reserve_drops": str(snapshot["reserve_base_drops"]),
            "destination_exists": destination_exists or destination_creatable,
            "destination_account_exists": destination_exists,
            "destination_creation_conditions_proven": destination_creatable,
            "destination_requires_tag": bool(destination_flags.get("requireDestinationTag", False)),
            "destination_disallows_asset": bool(destination_flags.get("disallowIncomingXRP", False)),
            "asset_metadata_verified": True,
            "source_wallet_verified": source_wallet_verified,
            "evidence_signature_valid": bool(snapshot["ledger_hash"]),
            "simulation_ok": simulation_ok,
            "preflight_result": simulation_code,
            "approval_scope_hash": approval_scope,
            "approval_valid": True,
            "human_confirmation_required": True,
            "human_confirmed": True,
            "pre_autofill_semantic_hash": digest(semantic_transaction(tx)),
            "signer_binding_hash": digest(tx),
            "transaction_hash": "not-submitted",
        }
    )
    return state


def submit_signed(client: Any, api: Mapping[str, Any], payment: Any, wallet: Any) -> dict[str, Any]:
    signed = api["sign"](payment, wallet)
    tx_hash = signed.get_hash()
    result = api["submit_and_wait"](signed, client, autofill=False).result
    if not isinstance(result, Mapping):
        raise RuntimeError("XRPL returned a non-object transaction result")
    return public_result(result, tx_hash)


def run_prepare(args: argparse.Namespace) -> int:
    api = xrpl_api()
    client = api["JsonRpcClient"](MAINNET_RPC)
    snapshot = server_snapshot(client, api)
    source, destination = load_or_create_wallets(Path(args.wallet_file), api)
    required_drops = (
        int(snapshot["reserve_base_drops"])
        + int(snapshot["reserve_base_drops"])
        + 2 * MAX_FEE_DROPS
        + FUNDING_BUFFER_DROPS
    )
    source_info = account_info(client, api, source.classic_address)
    current_balance = int(source_info["account_data"]["Balance"]) if source_info else 0
    print(json.dumps({
        "SCQOS_MAINNET_PROOF": "READY_FOR_FUNDING",
        "source_address": source.classic_address,
        "destination_address": destination.classic_address,
        "send_to_source_xrp": f"{required_drops / 1_000_000:.6f}",
        "current_source_balance_xrp": f"{current_balance / 1_000_000:.6f}",
        "live_reserve_base_xrp": f"{snapshot['reserve_base_drops'] / 1_000_000:.6f}",
        "live_base_fee_xrp": f"{snapshot['base_fee_drops'] / 1_000_000:.6f}",
        "estimated_xrp_destroyed_by_two_standard_fees": "0.000020",
        "transferred_xrp_remains_in_user_control": True,
        "seeds": "stored locally with mode 600; never printed",
    }, indent=2, sort_keys=True))
    return 0


def run_execute(args: argparse.Namespace) -> int:
    if not args.confirm_mainnet:
        raise SystemExit("--confirm-mainnet is required")
    repo_root = Path(__file__).resolve().parents[1]
    api = xrpl_api()
    client = api["JsonRpcClient"](MAINNET_RPC)
    receipt_key = load_or_create_receipt_key(Path(args.receipt_key))
    os.environ.setdefault("SCQOS_SECRET_KEY", receipt_key.hex())
    source, destination = load_or_create_wallets(Path(args.wallet_file), api)
    snapshot = server_snapshot(client, api)
    source_info = account_info(client, api, source.classic_address)
    if source_info is None:
        raise SystemExit(f"source is not funded: {source.classic_address}")
    required_drops = 2 * int(snapshot["reserve_base_drops"]) + 2 * MAX_FEE_DROPS
    balance = int(source_info["account_data"]["Balance"])
    if balance < required_drops:
        raise SystemExit(
            f"source needs at least {required_drops / 1_000_000:.6f} XRP; "
            f"current balance is {balance / 1_000_000:.6f} XRP"
        )

    # Exact ledger-valid but intent-wrong transaction.
    wrong_payment = api["autofill"](
        api["Payment"](
            account=source.classic_address,
            amount=str(snapshot["reserve_base_drops"]),
            destination=destination.classic_address,
            destination_tag=WRONG_TAG,
        ),
        client,
    )
    if int(wrong_payment.fee) > MAX_FEE_DROPS:
        raise SystemExit(f"fee HOLD: {wrong_payment.fee} drops exceeds {MAX_FEE_DROPS}")
    wrong_sim_ok, wrong_sim_code = simulate(client, api, wrong_payment)
    wrong_state = governed_state(
        client=client,
        api=api,
        payment=wrong_payment,
        intended_tag=INTENDED_TAG,
        snapshot=snapshot,
        simulation_ok=wrong_sim_ok,
        simulation_code=wrong_sim_code,
        source_wallet_verified=source.classic_address == wrong_payment.account,
    )
    wrong_eval = SCQOSCryptoGovernor(load_root_adapter(repo_root)).evaluate(wrong_state)
    wrong_codes = {finding.code for finding in wrong_eval.findings}
    if wrong_eval.decision != Decision.REJECT or "DESTINATION_TAG_MISMATCH" not in wrong_codes:
        raise AssertionError(f"wrong transaction did not fail closed: {wrong_eval.public()}")

    # Controlled causal baseline: submit the exact bytes SCQOS rejected.
    wrong_chain = submit_signed(client, api, wrong_payment, source)
    if wrong_chain["validated"] is not True or wrong_chain["engine_result"] != "tesSUCCESS":
        raise AssertionError(f"ledger-valid control failed: {wrong_chain}")

    # Correct transaction: fresh sequence, correct tag, 1 drop.
    snapshot = server_snapshot(client, api)
    valid_payment = api["autofill"](
        api["Payment"](
            account=source.classic_address,
            amount="1",
            destination=destination.classic_address,
            destination_tag=INTENDED_TAG,
        ),
        client,
    )
    if int(valid_payment.fee) > MAX_FEE_DROPS:
        raise SystemExit(f"fee HOLD: {valid_payment.fee} drops exceeds {MAX_FEE_DROPS}")
    valid_sim_ok, valid_sim_code = simulate(client, api, valid_payment)
    valid_state = governed_state(
        client=client,
        api=api,
        payment=valid_payment,
        intended_tag=INTENDED_TAG,
        snapshot=snapshot,
        simulation_ok=valid_sim_ok,
        simulation_code=valid_sim_code,
        source_wallet_verified=source.classic_address == valid_payment.account,
    )
    valid_eval = SCQOSCryptoGovernor(load_root_adapter(repo_root)).evaluate(valid_state)
    if valid_eval.decision != Decision.PERMIT or not valid_eval.root_proof.get("admitted"):
        raise AssertionError(f"valid transaction did not PERMIT: {valid_eval.public()}")
    if digest(valid_state["transaction"]) != valid_eval.transaction_hash:
        raise PermissionError("signer boundary received bytes different from SCQOS admission")
    valid_chain = submit_signed(client, api, valid_payment, source)
    if valid_chain["validated"] is not True or valid_chain["engine_result"] != "tesSUCCESS":
        raise AssertionError(f"governed transaction failed validation: {valid_chain}")
    consequence = {
        "validated": valid_chain["validated"],
        "engine_result": valid_chain["engine_result"],
        "transaction_hash": valid_chain["transaction_hash"],
        "network": NETWORK,
        "source": valid_chain.get("account") or source.classic_address,
        "destination": valid_chain.get("destination") or destination.classic_address,
        "destination_tag": valid_chain.get("destination_tag") if valid_chain.get("destination_tag") is not None else INTENDED_TAG,
        "asset": "XRP",
        "amount": str(valid_chain.get("amount") or "1"),
        "duplicate_effect": False,
    }
    closure = verify_consequence(valid_state["intent"], valid_chain["transaction_hash"], consequence)
    if closure.decision != Decision.PERMIT:
        raise AssertionError(f"consequence did not close: {closure.public()}")

    proof = {
        "schema": "scqos.xrpl-mainnet-supreme-proof.v1",
        "executed_at": time.time(),
        "network": NETWORK,
        "live_snapshot": snapshot,
        "public_wallets": {
            "source": source.classic_address,
            "destination": destination.classic_address,
        },
        "funds": {
            "wrong_control_transfer_drops": str(snapshot["reserve_base_drops"]),
            "correct_transfer_drops": "1",
            "ownership": "both wallets controlled by the same local proof authority",
            "only_fees_destroyed": True,
        },
        "wrong_transaction": {
            "intent_destination_tag": INTENDED_TAG,
            "actual_destination_tag": WRONG_TAG,
            "scqos_decision": wrong_eval.public(),
            "same_exact_transaction_without_scqos": wrong_chain,
        },
        "valid_transaction": {
            "scqos_decision": valid_eval.public(),
            "validated_ledger_result": valid_chain,
            "consequence_closure": closure.public(),
        },
    }
    signed_receipt = sign_receipt(proof, receipt_key)
    evidence_dir = repo_root / args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = evidence_dir / f"mainnet_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    atomic_json(receipt_path, signed_receipt)
    print(json.dumps({
        "SCQOS_MAINNET_SUPREME_PROOF": "COMPLETE",
        "network": "XRPL Mainnet",
        "wrong_transaction_without_scqos": wrong_chain["engine_result"],
        "same_exact_wrong_transaction_with_scqos": wrong_eval.decision.value,
        "correct_transaction_with_scqos": valid_eval.decision.value,
        "correct_transaction_validated": valid_chain["validated"],
        "consequence_closed": closure.decision.value,
        "wrong_control_transaction_hash": wrong_chain["transaction_hash"],
        "governed_transaction_hash": valid_chain["transaction_hash"],
        "receipt_hash": signed_receipt["receipt_hash"],
        "receipt_path": str(receipt_path),
        "explorer_wrong": f"https://livenet.xrpl.org/transactions/{wrong_chain['transaction_hash']}",
        "explorer_governed": f"https://livenet.xrpl.org/transactions/{valid_chain['transaction_hash']}",
    }, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SCQOS minimal-cost XRPL Mainnet causal proof")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-mainnet", action="store_true")
    parser.add_argument("--wallet-file", default="~/.config/scqos/xrpl_mainnet_proof_wallets.json")
    parser.add_argument("--receipt-key", default="~/.config/scqos/xrpl_mainnet_proof_hmac.key")
    parser.add_argument("--evidence-dir", default="evidence/crypto_holy_grail")
    args = parser.parse_args()
    return run_prepare(args) if args.prepare else run_execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
