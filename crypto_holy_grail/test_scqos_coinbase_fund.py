from decimal import Decimal
from uuid import UUID

from scqos_coinbase_fund import (
    AMOUNT,
    DESTINATION,
    IDEMPOTENCY,
    find_xrp_account,
    validate_transition,
)


def xrp_account(balance: str = "13.358969") -> dict:
    return {"id": "xrp-account", "currency": {"code": "XRP"}, "balance": {"amount": balance, "currency": "XRP"}}


def test_frozen_transition_permits_only_exact_send() -> None:
    result = validate_transition(
        confirmation="SEND-2.100200-XRP",
        destination=DESTINATION,
        permissions={"can_transfer": True},
        account=xrp_account(),
    )
    assert result["decision"] == "PERMIT"
    assert Decimal(result["amount"]) == AMOUNT
    assert result["destination_tag"] is None


def test_view_only_key_holds() -> None:
    result = validate_transition(
        confirmation="SEND-2.100200-XRP",
        destination=DESTINATION,
        permissions={"can_transfer": False},
        account=xrp_account(),
    )
    assert result["decision"] == "HOLD"
    assert "COINBASE_KEY_CANNOT_TRANSFER" in result["findings"]


def test_wrong_destination_or_confirmation_holds() -> None:
    result = validate_transition(
        confirmation="wrong",
        destination="rWrong",
        permissions={"can_transfer": True},
        account=xrp_account(),
    )
    assert result["decision"] == "HOLD"
    assert {"OWNER_CONFIRMATION_MISMATCH", "DESTINATION_MISMATCH"} <= set(result["findings"])


def test_insufficient_balance_holds() -> None:
    result = validate_transition(
        confirmation="SEND-2.100200-XRP",
        destination=DESTINATION,
        permissions={"can_transfer": True},
        account=xrp_account("2.0"),
    )
    assert result["decision"] == "HOLD"
    assert "INSUFFICIENT_XRP" in result["findings"]


def test_xrp_account_selection_and_idempotency_are_stable() -> None:
    selected = find_xrp_account({"data": [xrp_account("1"), xrp_account("13.358969"), {"currency": {"code": "USD"}, "balance": {"amount": "100"}}]})
    assert selected["balance"]["amount"] == "13.358969"
    assert IDEMPOTENCY == "b4c88ec3-0279-4489-98f0-5a0ca015d32a"
    assert UUID(IDEMPOTENCY).version == 4
