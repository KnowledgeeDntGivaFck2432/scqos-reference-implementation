#!/usr/bin/env python3
"""Full-authority SCQOS terminal gateway.

This gateway does not impose a read-only policy or an application allowlist. It
can execute every command the current operating-system identity is authorized to
execute. SCQOS governs the transition by binding the exact intent, command,
actor, runtime, references, expected consequence and receipt chain before the
process starts, then closes the circuit against the observed consequence.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from scqos_crypto_proof import (
    Decision,
    digest,
    load_or_create_receipt_key,
    load_root_adapter,
    sign_receipt,
)


SCHEMA = "scqos.full-terminal.v1"


@dataclass(frozen=True)
class TerminalFinding:
    gate: str
    code: str
    decision: Decision
    message: str


@dataclass
class TerminalEvaluation:
    decision: Decision
    transition_id: str
    intent_hash: str
    command_hash: str
    runtime_hash: str
    gate_status: dict[str, bool]
    findings: list[TerminalFinding] = field(default_factory=list)
    root_proof: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["decision"] = self.decision.value
        for finding in value["findings"]:
            finding["decision"] = finding["decision"].value
        return value


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_chain_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sequence": 0, "previous_receipt_hash": "GENESIS"}
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        "sequence": int(value.get("sequence", 0)),
        "previous_receipt_hash": str(value.get("previous_receipt_hash", "GENESIS")),
    }


def atomic_json(path: Path, value: Mapping[str, Any], mode: int = 0o600) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def environment_fingerprint() -> str:
    # Values are never placed in a receipt. Only their one-way aggregate is bound.
    return digest(sorted((str(key), str(value)) for key, value in os.environ.items()))


def resolve_runtime(command: list[str], shell_command: Optional[str]) -> Path:
    executable = "/bin/bash" if shell_command is not None else (command[0] if command else "")
    resolved = shutil.which(executable)
    return Path(resolved).resolve() if resolved else Path("")


def make_intent(
    *,
    command: list[str],
    shell_command: Optional[str],
    objective: str,
    expected_effect: str,
    expected_exit_code: int,
    cwd: Path,
    timeout: float,
    stdin_value: Optional[str],
    chain_state: Mapping[str, Any],
) -> dict[str, Any]:
    now = time.time()
    runtime = resolve_runtime(command, shell_command)
    runtime_hash = sha256_file(runtime) if runtime.is_file() else ""
    command_spec = {
        "mode": "bash" if shell_command is not None else "argv",
        "argv": command if shell_command is None else [],
        "shell_command": shell_command,
    }
    return {
        "schema": SCHEMA,
        "transition_id": f"terminal-{uuid.uuid4().hex}",
        "sequence": int(chain_state["sequence"]) + 1,
        "previous_receipt_hash": chain_state["previous_receipt_hash"],
        "created_at": now,
        "expires_at": now + 120,
        "actor": getpass.getuser(),
        "uid": os.getuid(),
        "effective_uid": os.geteuid(),
        "authority_mode": "owner_full_control",
        "authorization": "explicit_terminal_invocation",
        "objective": objective,
        "expected_effect": expected_effect,
        "expected_exit_code": expected_exit_code,
        "command": command_spec,
        "command_hash": digest(command_spec),
        "cwd": str(cwd.resolve()),
        "runtime": str(runtime),
        "runtime_sha256": runtime_hash,
        "environment_hash": environment_fingerprint(),
        "stdin_hash": hashlib.sha256((stdin_value or "").encode("utf-8")).hexdigest(),
        "timeout_seconds": timeout,
    }


class FullTerminalGovernor:
    GATES = (
        "time",
        "continuity",
        "alignment",
        "genesis",
        "boundary",
        "reference",
        "causality",
        "consciousness",
        "coherence",
    )

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def evaluate(self, intent: Mapping[str, Any], chain_state: Mapping[str, Any]) -> TerminalEvaluation:
        findings: list[TerminalFinding] = []

        def hold(gate: str, code: str, message: str) -> None:
            findings.append(TerminalFinding(gate, code, Decision.HOLD, message))

        def reject(gate: str, code: str, message: str) -> None:
            findings.append(TerminalFinding(gate, code, Decision.REJECT, message))

        # TIME
        now = time.time()
        created = intent.get("created_at")
        expires = intent.get("expires_at")
        if not isinstance(created, (int, float)) or not isinstance(expires, (int, float)):
            hold("time", "TIME_EVIDENCE_MISSING", "intent timing is incomplete")
        else:
            if created > now + 5:
                reject("time", "FUTURE_INTENT", "intent claims a future origin")
            if now > expires:
                reject("time", "EXPIRED_INTENT", "intent expired before execution")

        # CONTINUITY
        if intent.get("sequence") != int(chain_state.get("sequence", 0)) + 1:
            reject("continuity", "SEQUENCE_MISMATCH", "transition sequence is stale or replaced")
        if intent.get("previous_receipt_hash") != chain_state.get("previous_receipt_hash"):
            reject("continuity", "RECEIPT_CHAIN_MISMATCH", "previous consequence is not connected")
        command_spec = intent.get("command") or {}
        if intent.get("command_hash") != digest(command_spec):
            reject("continuity", "COMMAND_MUTATED", "command changed after intent formation")

        # ALIGNMENT
        if not str(intent.get("objective", "")).strip():
            hold("alignment", "OBJECTIVE_MISSING", "the command has no declared purpose")
        if not str(intent.get("expected_effect", "")).strip():
            hold("alignment", "EXPECTED_EFFECT_MISSING", "the intended consequence is unspecified")
        if command_spec.get("mode") == "argv" and not command_spec.get("argv"):
            hold("alignment", "COMMAND_MISSING", "no command was supplied")
        if command_spec.get("mode") == "bash" and not str(command_spec.get("shell_command", "")).strip():
            hold("alignment", "COMMAND_MISSING", "no shell command was supplied")

        # GENESIS
        if intent.get("actor") != getpass.getuser():
            reject("genesis", "ACTOR_MISMATCH", "current operating-system actor differs from intent")
        if intent.get("uid") != os.getuid() or intent.get("effective_uid") != os.geteuid():
            reject("genesis", "IDENTITY_MISMATCH", "process authority changed after intent formation")
        if intent.get("environment_hash") != environment_fingerprint():
            reject("genesis", "ENVIRONMENT_CHANGED", "execution environment changed after intent formation")

        # BOUNDARY: full authority means no artificial application allowlist.
        if intent.get("authority_mode") != "owner_full_control":
            reject("boundary", "AUTHORITY_MODE_MISMATCH", "terminal is not operating under owner authority")
        if intent.get("authorization") != "explicit_terminal_invocation":
            hold("boundary", "AUTHORIZATION_MISSING", "the owner did not explicitly invoke execution")
        timeout = intent.get("timeout_seconds")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            hold("boundary", "TIMEOUT_INVALID", "execution timeout is missing or invalid")

        # REFERENCE
        cwd = Path(str(intent.get("cwd", "")))
        runtime = Path(str(intent.get("runtime", "")))
        if not cwd.is_dir():
            hold("reference", "CWD_NOT_FOUND", "working directory does not exist")
        if not runtime.is_file():
            hold("reference", "RUNTIME_NOT_FOUND", "command runtime cannot be resolved")
        elif intent.get("runtime_sha256") != sha256_file(runtime):
            reject("reference", "RUNTIME_CHANGED", "runtime bytes changed before execution")

        # CAUSALITY
        if not isinstance(intent.get("expected_exit_code"), int):
            hold("causality", "EXPECTED_EXIT_MISSING", "success criteria lack an exit code")
        if not intent.get("stdin_hash"):
            hold("causality", "STDIN_BINDING_MISSING", "standard input is not bound")

        # CONSCIOUSNESS / ACCOUNTABILITY
        if not str(intent.get("transition_id", "")).strip():
            hold("consciousness", "TRANSITION_ID_MISSING", "accountable transition identity is absent")
        if intent.get("authorization") != "explicit_terminal_invocation":
            hold("consciousness", "OWNER_CONFIRMATION_MISSING", "owner invocation is not proven")

        gate_status = {gate: True for gate in self.GATES}
        for finding in findings:
            gate_status[finding.gate] = False
        gate_status["coherence"] = not findings
        if any(item.decision == Decision.REJECT for item in findings):
            decision = Decision.REJECT
        elif findings:
            decision = Decision.HOLD
        else:
            decision = Decision.PERMIT

        evaluation = TerminalEvaluation(
            decision=decision,
            transition_id=str(intent.get("transition_id", "UNKNOWN")),
            intent_hash=digest(intent),
            command_hash=str(intent.get("command_hash", "")),
            runtime_hash=str(intent.get("runtime_sha256", "")),
            gate_status=gate_status,
            findings=findings,
        )
        evaluation.root_proof = self._root_proof(intent, evaluation)
        if not evaluation.root_proof.get("admitted"):
            evaluation.findings.append(
                TerminalFinding("coherence", "ROOT_PROOF_FAILURE", Decision.HOLD, "SCQOS Root Adapter did not admit the proof")
            )
            evaluation.gate_status["coherence"] = False
            if evaluation.decision == Decision.PERMIT:
                evaluation.decision = Decision.HOLD
        return evaluation

    def _root_proof(self, intent: Mapping[str, Any], evaluation: TerminalEvaluation) -> dict[str, Any]:
        try:
            root = load_root_adapter(self.repo_root)
            packet = root.make_packet(
                system_type="linux_process",
                action="execute_terminal_command",
                actor=str(intent.get("actor", "UNKNOWN")),
                source=str(intent.get("runtime", "UNKNOWN")),
                target=str(intent.get("cwd", "UNKNOWN")),
                declared_objective="runtime_load",
                boundary_domain="trusted_runtime",
                payload={
                    "schema": SCHEMA,
                    "transition_id": evaluation.transition_id,
                    "intent_hash": evaluation.intent_hash,
                    "command_hash": evaluation.command_hash,
                    "runtime_hash": evaluation.runtime_hash,
                    "authority_mode": "owner_full_control",
                },
                external_reference=evaluation.transition_id,
            )
            proof = root.admit(packet)
            return {
                "admitted": getattr(proof.decision, "value", str(proof.decision)) == "ADMIT",
                "packet_hash": proof.packet_hash,
                "final_proof": proof.final_proof,
                "time_hash": proof.time_hash,
                "continuity_hash": proof.continuity_hash,
                "alignment_hash": proof.alignment_hash,
                "genesis_hash": proof.genesis_hash,
                "boundary_hash": proof.boundary_hash,
                "reference_hash": proof.reference_hash,
                "causality_hash": proof.causality_hash,
                "consciousness_hash": proof.consciousness_hash,
                "coherence_hash": proof.coherence_hash,
                "reason": proof.reason,
            }
        except Exception as error:
            return {"admitted": False, "error": f"{type(error).__name__}: {error}"}


def verify_file_expectations(expectations: Iterable[str]) -> list[dict[str, Any]]:
    results = []
    for specification in expectations:
        if "=" in specification:
            raw_path, expected_hash = specification.split("=", 1)
        else:
            raw_path, expected_hash = specification, ""
        path = Path(raw_path).expanduser().resolve()
        exists = path.exists()
        observed_hash = sha256_file(path) if exists and path.is_file() else ""
        passed = exists and (not expected_hash or observed_hash == expected_hash)
        results.append(
            {
                "path": str(path),
                "exists": exists,
                "expected_sha256": expected_hash,
                "observed_sha256": observed_hash,
                "passed": passed,
            }
        )
    return results


def execute_governed(
    *,
    repo_root: Path,
    intent: Mapping[str, Any],
    chain_state: Mapping[str, Any],
    stdin_value: Optional[str],
    expected_stdout_sha256: str,
    file_expectations: Iterable[str],
) -> tuple[TerminalEvaluation, dict[str, Any], bytes, bytes]:
    governor = FullTerminalGovernor(repo_root)
    evaluation = governor.evaluate(intent, chain_state)
    if evaluation.decision != Decision.PERMIT:
        return evaluation, {"executed": False, "consequence_decision": evaluation.decision.value}, b"", b""

    # Final byte-binding check at the exact signer/executor boundary.
    if digest(intent["command"]) != evaluation.command_hash:
        raise PermissionError("SCQOS blocked command mutation at the executor boundary")
    runtime = Path(intent["runtime"])
    if not runtime.is_file() or sha256_file(runtime) != evaluation.runtime_hash:
        raise PermissionError("SCQOS blocked runtime mutation at the executor boundary")

    command_spec = intent["command"]
    argv = (
        ["/bin/bash", "-lc", command_spec["shell_command"]]
        if command_spec["mode"] == "bash"
        else list(command_spec["argv"])
    )
    started = time.time()
    try:
        process = subprocess.run(
            argv,
            cwd=intent["cwd"],
            input=(stdin_value or "").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(intent["timeout_seconds"]),
            check=False,
        )
        timed_out = False
        return_code: Optional[int] = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        return_code = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    file_results = verify_file_expectations(file_expectations)
    stdout_hash = hashlib.sha256(stdout).hexdigest()
    exit_matches = return_code == intent["expected_exit_code"]
    stdout_matches = not expected_stdout_sha256 or stdout_hash == expected_stdout_sha256
    files_match = all(item["passed"] for item in file_results)
    consequence_decision = Decision.PERMIT if (not timed_out and exit_matches and stdout_matches and files_match) else Decision.REJECT
    consequence = {
        "executed": True,
        "started_at": started,
        "finished_at": time.time(),
        "timed_out": timed_out,
        "return_code": return_code,
        "expected_exit_code": intent["expected_exit_code"],
        "exit_matches": exit_matches,
        "stdout_sha256": stdout_hash,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_matches": stdout_matches,
        "file_expectations": file_results,
        "files_match": files_match,
        "consequence_decision": consequence_decision.value,
    }
    return evaluation, consequence, stdout, stderr


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Full-authority SCQOS governed terminal")
    parser.add_argument("--objective", required=True, help="why this exact command is being executed")
    parser.add_argument("--expected-effect", required=True, help="the consequence that must follow")
    parser.add_argument("--expected-exit-code", type=int, default=0)
    parser.add_argument("--expected-stdout-sha256", default="")
    parser.add_argument("--expect-file", action="append", default=[], help="PATH or PATH=EXPECTED_SHA256")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--stdin", default=None)
    parser.add_argument("--shell", default=None, help="execute an exact Bash command, including pipes/redirection")
    parser.add_argument("--state-file", default="~/.config/scqos/full_terminal_state.json")
    parser.add_argument("--receipt-key", default="~/.config/scqos/full_terminal_hmac.key")
    parser.add_argument("--evidence-dir", default="evidence/scqos_full_terminal")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if bool(args.shell) == bool(command):
        parser.error("provide exactly one of --shell COMMAND or -- ARGV...")

    repo_root = Path(__file__).resolve().parents[1]
    state_path = Path(args.state_file).expanduser()
    key = load_or_create_receipt_key(Path(args.receipt_key))
    os.environ.setdefault("SCQOS_SECRET_KEY", key.hex())
    chain_state = load_chain_state(state_path)
    intent = make_intent(
        command=command,
        shell_command=args.shell,
        objective=args.objective,
        expected_effect=args.expected_effect,
        expected_exit_code=args.expected_exit_code,
        cwd=Path(args.cwd),
        timeout=args.timeout,
        stdin_value=args.stdin,
        chain_state=chain_state,
    )
    evaluation, consequence, stdout, stderr = execute_governed(
        repo_root=repo_root,
        intent=intent,
        chain_state=chain_state,
        stdin_value=args.stdin,
        expected_stdout_sha256=args.expected_stdout_sha256,
        file_expectations=args.expect_file,
    )
    receipt = sign_receipt(
        {
            "schema": SCHEMA,
            "intent": intent,
            "pre_execution": evaluation.public(),
            "consequence": consequence,
        },
        key,
    )
    evidence_dir = repo_root / args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = evidence_dir / f"{intent['sequence']:08d}_{intent['transition_id']}.json"
    atomic_json(receipt_path, receipt)
    atomic_json(
        state_path,
        {"sequence": intent["sequence"], "previous_receipt_hash": receipt["receipt_hash"]},
    )
    if stdout:
        sys.stdout.buffer.write(stdout)
    if stderr:
        sys.stderr.buffer.write(stderr)
    print(json.dumps({
        "SCQOS_FULL_TERMINAL": "COMPLETE",
        "pre_execution_decision": evaluation.decision.value,
        "executed": consequence.get("executed", False),
        "consequence_decision": consequence.get("consequence_decision"),
        "command_hash": evaluation.command_hash,
        "root_proof": evaluation.root_proof.get("final_proof", ""),
        "receipt_hash": receipt["receipt_hash"],
        "receipt_path": str(receipt_path),
    }, indent=2, sort_keys=True))
    return 0 if evaluation.decision == Decision.PERMIT and consequence.get("consequence_decision") == Decision.PERMIT.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
