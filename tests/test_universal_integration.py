import os
import tempfile

tmp = tempfile.NamedTemporaryFile(
    suffix=".sqlite3",
    delete=False,
)
tmp.close()

os.environ["SCQOS_UNIVERSAL_DB"] = tmp.name
os.environ["SCQOS_SECRET_KEY"] = (
    "universal-test-key-" + "a" * 64
)

from integration.universal_gateway import (
    TransitionRequest,
    govern_transition,
)


def run(payload):
    return govern_transition(
        TransitionRequest.model_validate(payload)
    )


def test_auto_repair_business():
    result = run({
        "tenant_id": "collision-shop-A",
        "external_system": "repair-management-system",
        "subject": "repair-order-18422",
        "authority": {
            "principal_id": "estimator-7",
            "scope": "repair-order:update"
        },
        "intent": "approve supplement change",
        "evidence": {
            "estimate_version": 7,
            "photos_verified": True
        },
        "current_state": {
            "repair_status": "disassembly",
            "estimate_total": 4821.32
        },
        "proposed_transition": {
            "operation": "update_estimate",
            "new_total": 5310.88
        },
        "expected_consequence": {
            "repair_order_version": 8
        }
    })

    assert result.decision == "PERMIT"
    assert result.execution_authorized is True
    assert len(result.gate_proofs) == 9


def test_completely_different_business_same_contract():
    result = run({
        "tenant_id": "logistics-company-B",
        "external_system": "warehouse-orchestrator",
        "subject": "shipment-992771",
        "authority": {
            "principal_id": "dispatch-agent-12",
            "scope": "shipment:reroute"
        },
        "intent": "reroute delayed shipment",
        "evidence": {
            "delay_minutes": 145,
            "alternate_route_verified": True
        },
        "current_state": {
            "warehouse": "PHX-1",
            "route": "AZ-NM-TX"
        },
        "proposed_transition": {
            "operation": "reroute",
            "route": "AZ-CO-TX"
        },
        "expected_consequence": {
            "eta_reduction_minutes": 82
        }
    })

    assert result.decision == "PERMIT"
    assert result.execution_authorized is True
    assert len(result.gate_proofs) == 9


def test_unauthorized_transition_rejects():
    result = run({
        "tenant_id": "business-C",
        "external_system": "erp",
        "subject": "payment-88",
        "authority": {
            "principal_id": "unknown",
            "scope": "unauthorized"
        },
        "intent": "release payment",
        "evidence": {},
        "current_state": {},
        "proposed_transition": {
            "operation": "release"
        },
        "expected_consequence": {
            "status": "paid"
        }
    })

    assert result.decision == "REJECT"
    assert result.execution_authorized is False
