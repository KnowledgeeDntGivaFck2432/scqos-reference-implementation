from __future__ import annotations

from pathlib import Path

from xrpl.wallet import Wallet

from xrpl_mainnet_supreme_proof import (
    generic_transaction,
    load_or_create_wallets,
    public_result,
    wallet_file_mode_ok,
)


class PaymentStub:
    account = "rSource"
    destination = "rDestination"
    destination_tag = 222
    amount = "1000000"
    fee = "10"
    sequence = 7
    last_ledger_sequence = 20


def test_wallets_are_persisted_mode_600_without_console_output(tmp_path: Path, capsys) -> None:
    path = tmp_path / "wallets.json"
    api = {"Wallet": Wallet}
    source1, destination1 = load_or_create_wallets(path, api)
    assert path.stat().st_mode & 0o777 == 0o600
    assert capsys.readouterr().out == ""
    source2, destination2 = load_or_create_wallets(path, api)
    assert source1.classic_address == source2.classic_address
    assert destination1.classic_address == destination2.classic_address


def test_insecure_wallet_permissions_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "wallets.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o644)
    try:
        wallet_file_mode_ok(path)
    except PermissionError:
        pass
    else:
        raise AssertionError("insecure wallet file was not rejected")


def test_exact_mainnet_transaction_semantics_are_bound() -> None:
    value = generic_transaction(PaymentStub())
    assert value["network"] == "xrpl_mainnet"
    assert value["chain_id"] == "xrpl:mainnet:network_id_0"
    assert value["destination_tag"] == 222
    assert value["amount"] == "1000000"
    assert value["fee_drops"] == "10"


def test_public_result_excludes_secrets() -> None:
    result = public_result(
        {
            "validated": True,
            "ledger_index": 1,
            "hash": "ABC",
            "meta": {"TransactionResult": "tesSUCCESS"},
            "tx_json": {
                "Account": "rSource",
                "Destination": "rDestination",
                "DestinationTag": 111,
                "DeliverMax": "1",
                "TransactionType": "Payment",
            },
        },
        "fallback",
    )
    assert result["validated"] is True
    assert result["engine_result"] == "tesSUCCESS"
    assert "seed" not in result
    assert "private_key" not in result
