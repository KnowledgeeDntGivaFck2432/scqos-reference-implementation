from __future__ import annotations

import copy
import time

from scqos_crypto_proof import (
    Decision,
    SCQOSCryptoGovernor,
    baseline_state,
    fault_universe,
    verify_consequence,
)


def test_valid_control_permits() -> None:
    result = SCQOSCryptoGovernor().evaluate(baseline_state())
    assert result.decision == Decision.PERMIT
    assert all(result.gate_status.values())


def test_complete_fault_universe_fails_closed() -> None:
    now = time.time()
    baseline = baseline_state(now)
    governor = SCQOSCryptoGovernor()
    for case in fault_universe(now):
        state = copy.deepcopy(baseline)
        case.mutate(state)
        result = governor.evaluate(state)
        assert result.decision == case.expected, (case.name, result.public())
        assert case.expected_code in {finding.code for finding in result.findings}, case.name
        assert result.decision != Decision.PERMIT, case.name


def test_post_execution_requires_final_exact_consequence() -> None:
    state = baseline_state()
    tx_hash = "ABC123"
    consequence = {
        "validated": True,
        "engine_result": "tesSUCCESS",
        "transaction_hash": tx_hash,
        "network": state["intent"]["network"],
        "source": state["intent"]["source"],
        "destination": state["intent"]["destination"],
        "destination_tag": state["intent"]["destination_tag"],
        "asset": state["intent"]["asset"],
        "amount": state["intent"]["amount"],
        "duplicate_effect": False,
    }
    assert verify_consequence(state["intent"], tx_hash, consequence).decision == Decision.PERMIT
    consequence["validated"] = False
    assert verify_consequence(state["intent"], tx_hash, consequence).decision == Decision.HOLD
    consequence["validated"] = True
    consequence["destination"] = "wrong"
    assert verify_consequence(state["intent"], tx_hash, consequence).decision == Decision.REJECT
