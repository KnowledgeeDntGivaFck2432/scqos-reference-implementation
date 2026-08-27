#!/usr/bin/env python3
"""One-purpose Coinbase-to-XRPL funding transition for the Mainnet proof.

The transition is frozen to one amount, asset, and destination. It checks the
local proof wallet, Coinbase transfer permission, available XRP, and an explicit
confirmation token before it can call Coinbase's send endpoint. A stable UUIDv5
idempotency key prevents a retry from creating a second send.
"""

from __future__ import annotations

import argparse
import json
import stat
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


AMOUNT = Decimal("2.100200")
CURRENCY = "XRP"
DESTINATION = "rwEZsqSjFHR3Q6cxUefCA5WRfVe6HsjrNL"
CONFIRMATION = "SEND-2.100200-XRP"
# Coinbase requires an RFC 4122 UUID *version 4*. This frozen v4 value is kept
# stable across retries so the exact one-time funding transition cannot duplicate.
IDEMPOTENCY = "b4c88ec3-0279-4489-98f0-5a0ca015d32a"


def public_json(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return value


def require_private_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{label} not found: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(f"{label} must have mode 600: chmod 600 {path}")
    return path


def proof_source_address(wallet_file: Path) -> str:
    from xrpl.wallet import Wallet

    wallet_file = require_private_file(wallet_file, "proof wallet file")
    value = json.loads(wallet_file.read_text(encoding="utf-8"))
    seed = value.get("source_seed")
    if not isinstance(seed, str) or not seed:
        raise RuntimeError("proof wallet file has no source seed")
    return Wallet.from_seed(seed).classic_address


def find_xrp_account(accounts_response: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates: list[Mapping[str, Any]] = []
    for account in accounts_response.get("data", []):
        if not isinstance(account, Mapping):
            continue
        currency = account.get("currency") or {}
        code = currency.get("code") if isinstance(currency, Mapping) else currency
        balance = account.get("balance") or {}
        balance_currency = balance.get("currency") if isinstance(balance, Mapping) else None
        if str(code or balance_currency).upper() == CURRENCY:
            candidates.append(account)
    if not candidates:
        raise RuntimeError("Coinbase returned no XRP account")
    return max(candidates, key=lambda item: Decimal(str((item.get("balance") or {}).get("amount", "0"))))


def validate_transition(
    *,
    confirmation: str,
    destination: str,
    permissions: Mapping[str, Any],
    account: Mapping[str, Any],
) -> dict[str, Any]:
    findings: list[str] = []
    if confirmation != CONFIRMATION:
        findings.append("OWNER_CONFIRMATION_MISMATCH")
    if destination != DESTINATION:
        findings.append("DESTINATION_MISMATCH")
    if permissions.get("can_transfer") is not True:
        findings.append("COINBASE_KEY_CANNOT_TRANSFER")
    balance = Decimal(str((account.get("balance") or {}).get("amount", "0")))
    if balance < AMOUNT:
        findings.append("INSUFFICIENT_XRP")
    decision = "PERMIT" if not findings else "HOLD"
    return {
        "decision": decision,
        "findings": findings,
        "currency": CURRENCY,
        "amount": format(AMOUNT, "f"),
        "destination": destination,
        "destination_tag": None,
        "idempotency_key": IDEMPOTENCY,
        "coinbase_xrp_balance": format(balance, "f"),
        "can_transfer": permissions.get("can_transfer") is True,
    }


def request(client: Any, method: str, path: str, *, data: dict[str, Any] | None = None) -> Mapping[str, Any]:
    result = client.prepare_and_send_request(method, path, data=data)
    value = public_json(result)
    if not isinstance(value, Mapping):
        raise RuntimeError(f"Coinbase returned a non-object response for {path}")
    return value


def wait_for_destination(address: str, minimum_drops: int, timeout: int) -> Mapping[str, Any] | None:
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountInfo

    client = JsonRpcClient("https://s2.ripple.com:51234/")
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.request(AccountInfo(account=address, ledger_index="validated", strict=True))
        result = response.result if isinstance(response.result, Mapping) else {}
        if response.is_successful():
            account_data = result.get("account_data") or {}
            balance = int(account_data.get("Balance", "0"))
            if balance >= minimum_drops:
                return {
                    "address": address,
                    "validated_ledger_index": result.get("ledger_index"),
                    "balance_drops": str(balance),
                    "balance_xrp": f"{balance / 1_000_000:.6f}",
                }
        time.sleep(3)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="SCQOS exact Coinbase funding transition")
    parser.add_argument("--key-file", default="~/Downloads/coinbase_transfer_key.json")
    parser.add_argument("--wallet-file", default="~/.config/scqos/xrpl_mainnet_proof_wallets.json")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--wait-seconds", type=int, default=180)
    args = parser.parse_args()

    key_file = require_private_file(Path(args.key_file), "Coinbase transfer key")
    destination = proof_source_address(Path(args.wallet_file))
    if destination != DESTINATION:
        raise RuntimeError(f"proof wallet changed; expected {DESTINATION}, observed {destination}")

    from coinbase.rest import RESTClient

    client = RESTClient(key_file=str(key_file), timeout=30)
    permissions = request(client, "GET", "/api/v3/brokerage/key_permissions")
    accounts = request(client, "GET", "/v2/accounts")
    account = find_xrp_account(accounts)
    evaluation = validate_transition(
        confirmation=args.confirm,
        destination=destination,
        permissions=permissions,
        account=account,
    )
    if evaluation["decision"] != "PERMIT":
        print(json.dumps({"SCQOS_COINBASE_FUNDING": "HOLD", **evaluation}, indent=2, sort_keys=True))
        return 2

    account_id = str(account.get("id", ""))
    if not account_id:
        raise RuntimeError("Coinbase XRP account has no account ID")
    payload = {
        "type": "send",
        "to": destination,
        "amount": format(AMOUNT, "f"),
        "currency": CURRENCY,
        "idem": IDEMPOTENCY,
        "description": "SCQOS XRPL Mainnet causal proof funding",
    }
    transaction = request(client, "POST", f"/v2/accounts/{account_id}/transactions", data=payload)
    transaction_data = transaction.get("data") or {}
    transaction_id = transaction_data.get("id") if isinstance(transaction_data, Mapping) else None
    validated = wait_for_destination(destination, int(AMOUNT * 1_000_000), args.wait_seconds)
    if validated is None:
        print(json.dumps({
            "SCQOS_COINBASE_FUNDING": "PENDING",
            "coinbase_transaction_id": transaction_id,
            "destination": destination,
            "amount_xrp": format(AMOUNT, "f"),
            "idempotency_key": IDEMPOTENCY,
            "instruction": "Coinbase accepted the idempotent send; rerun this same command to recheck without duplicating it.",
        }, indent=2, sort_keys=True))
        return 3

    print(json.dumps({
        "SCQOS_COINBASE_FUNDING": "COMPLETE",
        "coinbase_transaction_id": transaction_id,
        "destination": destination,
        "amount_xrp": format(AMOUNT, "f"),
        "destination_tag": None,
        "validated_destination": validated,
        "idempotency_key": IDEMPOTENCY,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
