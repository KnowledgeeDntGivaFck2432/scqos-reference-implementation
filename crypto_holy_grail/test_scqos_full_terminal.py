from __future__ import annotations

import copy
import hashlib
import os
import sys
from pathlib import Path

from scqos_full_terminal import (
    Decision,
    FullTerminalGovernor,
    execute_governed,
    make_intent,
)


def _intent(tmp_path: Path):
    state = {"sequence": 0, "previous_receipt_hash": "GENESIS"}
    output = b"SCQOS_FULL_TERMINAL_OK\n"
    intent = make_intent(
        command=[sys.executable, "-c", "print('SCQOS_FULL_TERMINAL_OK')"],
        shell_command=None,
        objective="prove full terminal execution",
        expected_effect="exact controlled output and exit zero",
        expected_exit_code=0,
        cwd=tmp_path,
        timeout=30,
        stdin_value=None,
        chain_state=state,
    )
    return state, intent, hashlib.sha256(output).hexdigest()


def test_full_authority_valid_command_executes(tmp_path: Path) -> None:
    state, intent, output_hash = _intent(tmp_path)
    evaluation, consequence, stdout, _ = execute_governed(
        repo_root=Path(__file__).resolve().parents[1],
        intent=intent,
        chain_state=state,
        stdin_value=None,
        expected_stdout_sha256=output_hash,
        file_expectations=[],
    )
    assert evaluation.decision == Decision.PERMIT
    assert evaluation.root_proof["admitted"] is True
    assert consequence["consequence_decision"] == Decision.PERMIT.value
    assert stdout == b"SCQOS_FULL_TERMINAL_OK\n"


def test_command_mutation_rejects_before_execution(tmp_path: Path) -> None:
    state, intent, _ = _intent(tmp_path)
    intent["command"]["argv"][-1] = "print('MUTATED')"
    evaluation = FullTerminalGovernor(Path(__file__).resolve().parents[1]).evaluate(intent, state)
    assert evaluation.decision == Decision.REJECT
    assert "COMMAND_MUTATED" in {finding.code for finding in evaluation.findings}


def test_stale_receipt_chain_rejects(tmp_path: Path) -> None:
    state, intent, _ = _intent(tmp_path)
    broken_state = copy.deepcopy(state)
    broken_state["previous_receipt_hash"] = "OTHER"
    evaluation = FullTerminalGovernor(Path(__file__).resolve().parents[1]).evaluate(intent, broken_state)
    assert evaluation.decision == Decision.REJECT
    assert "RECEIPT_CHAIN_MISMATCH" in {finding.code for finding in evaluation.findings}


def test_wrong_expected_consequence_rejects_after_execution(tmp_path: Path) -> None:
    state, intent, _ = _intent(tmp_path)
    evaluation, consequence, _, _ = execute_governed(
        repo_root=Path(__file__).resolve().parents[1],
        intent=intent,
        chain_state=state,
        stdin_value=None,
        expected_stdout_sha256="wrong",
        file_expectations=[],
    )
    assert evaluation.decision == Decision.PERMIT
    assert consequence["consequence_decision"] == Decision.REJECT.value
