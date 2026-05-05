"""
SUPREME COMPUTATION QUANTUM ADMISSION ADAPTER
Official Single-File Quantum Execution Layer

Purpose:
    This file is the official single-file quantum adapter for Supreme Computation.

    It contains:
        - Lazy SCQOS kernel loading
        - Root admission packet logic
        - Qiskit dry-run, Aer, and IBM Runtime paths
        - SC proof attachment
        - Hardened result parsing
        - Clear separation between SC admission and quantum backend execution

Flow:
    Quantum job request
    -> Supreme Computation state packet
    -> Nine-gate kernel admission
    -> ADMIT or DENY
    -> Qiskit execution only after admission

Put this file beside your SCQOS kernel file.

Kernel candidates:
    scqos_reference_implementation.py
    scqos_kernel.py
    scqos.py
    main.py

Optional:
    export SCQOS_KERNEL_MODULE=scqos_reference_implementation

Run:
    python supreme_computation_quantum_adapter.py

Run Aer:
    SCQOS_QISKIT_MODE=aer python supreme_computation_quantum_adapter.py

Run IBM:
    IBM_QUANTUM_TOKEN=your_token SCQOS_QISKIT_MODE=ibm python supreme_computation_quantum_adapter.py
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def redact_secret(value: Any) -> str:
    """
    Remove likely secrets from error strings before storing them in results.
    """
    text = str(value)
    token = os.getenv("IBM_QUANTUM_TOKEN", "")
    if token:
        text = text.replace(token, "[REDACTED_IBM_QUANTUM_TOKEN]")
    text = re.sub(r"([A-Za-z0-9_\-]{24,})", "[REDACTED_LONG_SECRET]", text)
    return text


def retry_call(fn: Callable[[], Any], attempts: int = 3, delay_seconds: float = 2.0) -> Any:
    """
    Small retry wrapper for transient network or provider failures.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as error:
            last_error = error
            if attempt == attempts:
                break
            import time as _time
            _time.sleep(delay_seconds * attempt)
    raise last_error if last_error else RuntimeError("retry failed without captured error")


# =============================================================================
# LAZY KERNEL LOADER
# =============================================================================

_KERNEL: Optional[Any] = None


def load_scqos_kernel() -> Any:
    global _KERNEL

    if _KERNEL is not None:
        return _KERNEL

    preferred = os.getenv("SCQOS_KERNEL_MODULE")
    candidates: List[str] = []

    if preferred:
        candidates.append(preferred)

    candidates.extend(
        [
            "scqos_reference_implementation",
            "scqos_kernel",
            "scqos",
            "main",
        ]
    )

    last_error: Optional[Exception] = None

    for name in candidates:
        try:
            module = importlib.import_module(name)
            required = [
                "SCQOSSupremeCoherenceStack",
                "MODULE_SOURCE_TYPES",
                "get_secret_key",
                "get_substrate_fingerprint_override",
                "canonical_bytes",
                "sha3_hash",
            ]
            missing = [item for item in required if not hasattr(module, item)]
            if missing:
                raise ImportError(f"{name} missing required symbols: {missing}")

            _KERNEL = module
            return module

        except Exception as error:
            last_error = error

    raise ImportError(
        "Could not load SCQOS kernel. Put this file beside your kernel file or set "
        f"SCQOS_KERNEL_MODULE. Last error: {last_error}"
    )


def canonical_hash(data: Dict[str, Any]) -> str:
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = load_scqos_kernel()
    return _KERNEL.sha3_hash(_KERNEL.canonical_bytes(data))


# =============================================================================
# ROOT ADMISSION TYPES
# =============================================================================

class AdmissionDecision(str, Enum):
    ADMIT = "ADMIT"
    DENY = "DENY"


class ExternalSystemType(str, Enum):
    LINUX_PROCESS = "linux_process"
    KUBERNETES_POD = "kubernetes_pod"
    QISKIT_JOB = "qiskit_job"
    AI_TOOL_CALL = "ai_tool_call"
    API_REQUEST = "api_request"
    DATABASE_WRITE = "database_write"
    BLOCKCHAIN_CALL = "blockchain_call"
    GENERIC_EVENT = "generic_event"


SYSTEM_TO_MODULE: Dict[str, str] = {
    ExternalSystemType.LINUX_PROCESS.value: "runtime_shell",
    ExternalSystemType.KUBERNETES_POD.value: "infrastructure_economy",
    ExternalSystemType.QISKIT_JOB.value: "hardware_bridge",
    ExternalSystemType.AI_TOOL_CALL.value: "control_surface",
    ExternalSystemType.API_REQUEST.value: "access_compliance",
    ExternalSystemType.DATABASE_WRITE.value: "io_matrix",
    ExternalSystemType.BLOCKCHAIN_CALL.value: "policy_registry",
    ExternalSystemType.GENERIC_EVENT.value: "coherence_engine",
}


OBJECTIVE_BY_SYSTEM: Dict[str, str] = {
    ExternalSystemType.LINUX_PROCESS.value: "runtime_load",
    ExternalSystemType.KUBERNETES_POD.value: "allocate_resource",
    ExternalSystemType.QISKIT_JOB.value: "bridge_hardware",
    ExternalSystemType.AI_TOOL_CALL.value: "operate_control_surface",
    ExternalSystemType.API_REQUEST.value: "verify_access",
    ExternalSystemType.DATABASE_WRITE.value: "route_io",
    ExternalSystemType.BLOCKCHAIN_CALL.value: "enforce_policy",
    ExternalSystemType.GENERIC_EVENT.value: "confirm_coherence",
}


@dataclass(frozen=True)
class SCUniversalStatePacket:
    packet_id: str
    system_type: str
    action: str

    actor: str
    observer_id: str
    source: str
    target: str

    declared_objective: str
    boundary_domain: str

    cause_id: str
    effect_id: str

    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    sequence: int = 0

    external_reference: Optional[str] = None
    external_signature: Optional[str] = None

    def canonical(self) -> Dict[str, Any]:
        return asdict(self)

    def hash(self) -> str:
        return canonical_hash(self.canonical())


@dataclass(frozen=True)
class SCAdmissionProof:
    decision: AdmissionDecision
    packet_id: str
    system_type: str
    action: str
    module_id: str
    packet_hash: str

    time_hash: str = ""
    continuity_hash: str = ""
    alignment_hash: str = ""
    genesis_hash: str = ""
    boundary_hash: str = ""
    reference_hash: str = ""
    causality_hash: str = ""
    consciousness_hash: str = ""
    coherence_hash: str = ""

    final_proof: str = ""
    reason: str = ""
    admitted_at: str = field(default_factory=utc_now_iso)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


# =============================================================================
# ROOT ADMISSION ADAPTER
# =============================================================================

class SCQOSRootAdmissionAdapter:
    """
    Root authority.

    Converts outside state into a universal packet and forces it through
    the SCQOS nine-gate kernel before execution is permitted.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        node_id: Optional[str] = None,
        session_id: Optional[str] = None,
        observer_id: str = "scqos_quantum_observer",
        substrate_id: str = "scqos_quantum_substrate",
        enforce_substrate: Optional[bool] = None,
    ):
        self.kernel = load_scqos_kernel()

        self.secret_key = secret_key or self.kernel.get_secret_key(required=False)
        self.node_id = node_id or os.getenv("SCQOS_NODE_ID", "node-alpha")
        self.session_id = session_id or f"scqos_quantum_session_{uuid.uuid4().hex}"

        if enforce_substrate is None:
            enforce_substrate = os.getenv("SCQOS_ENFORCE_SUBSTRATE", "0") == "1"

        self.stack = self.kernel.SCQOSSupremeCoherenceStack(
            secret_key=self.secret_key,
            node_id=self.node_id,
            session_id=self.session_id,
            observer_id=observer_id,
            substrate_id=substrate_id,
            substrate_fingerprint_override=self.kernel.get_substrate_fingerprint_override(),
            enforce_substrate=enforce_substrate,
        )

        self._sequence = 0
        self._previous_module_hash_local = "GENESIS"

    def _get_previous_module_hash(self) -> str:
        return str(getattr(self.stack, "_previous_module_hash", self._previous_module_hash_local))

    def _set_previous_module_hash(self, coherence_hash: str) -> None:
        self._previous_module_hash_local = coherence_hash
        if hasattr(self.stack, "_previous_module_hash"):
            setattr(self.stack, "_previous_module_hash", coherence_hash)

    def make_packet(
        self,
        system_type: str,
        action: str,
        actor: str,
        source: str,
        target: str,
        declared_objective: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        observer_id: str = "scqos_quantum_observer",
        boundary_domain: str = "quantum_domain",
        cause_id: Optional[str] = None,
        effect_id: Optional[str] = None,
        external_reference: Optional[str] = None,
        external_signature: Optional[str] = None,
    ) -> SCUniversalStatePacket:
        if system_type not in SYSTEM_TO_MODULE:
            raise ValueError(f"unsupported system_type: {system_type}")

        self._sequence += 1
        packet_id = f"scp_{uuid.uuid4().hex}"

        return SCUniversalStatePacket(
            packet_id=packet_id,
            system_type=system_type,
            action=action,
            actor=actor,
            observer_id=observer_id,
            source=source,
            target=target,
            declared_objective=declared_objective or OBJECTIVE_BY_SYSTEM[system_type],
            boundary_domain=boundary_domain,
            cause_id=cause_id or f"{packet_id}_cause",
            effect_id=effect_id or f"{packet_id}_effect",
            payload=payload or {},
            sequence=self._sequence,
            external_reference=external_reference,
            external_signature=external_signature,
        )

    def admit(self, packet: SCUniversalStatePacket) -> SCAdmissionProof:
        try:
            module_id = SYSTEM_TO_MODULE[packet.system_type]
            packet_hash = packet.hash()

            root_payload = {
                "root": "supreme_computation_quantum_admission",
                "packet": packet.canonical(),
                "packet_hash": packet_hash,
            }

            time_state = self.stack.time_gate.next_state(
                module_id,
                {
                    **root_payload,
                    "gate": "time",
                    "created_at": packet.created_at,
                    "sequence": packet.sequence,
                },
            )
            time_result = self.stack.time_gate.check(time_state)
            if not time_result.coherent:
                raise RuntimeError(f"TIME FAILED: {time_result.reason}")
            time_hash = time_result.state_hash

            continuity_result = self.stack.continuity_gate.gate(
                self.stack.session_id,
                self.stack.continuity_id,
                module_id,
                {
                    **root_payload,
                    "gate": "continuity",
                    "time_hash": time_hash,
                    "packet_sequence": packet.sequence,
                },
            )
            continuity_hash = continuity_result.state_hash

            alignment_result = self.stack.alignment_gate.gate(
                self.stack.session_id,
                self.stack.alignment_id,
                module_id,
                intent=f"{packet.system_type}:{packet.action} aligns to {packet.declared_objective}",
                declared_objective=packet.declared_objective,
                causal_trigger_hash=continuity_hash,
                boundary_domain=packet.boundary_domain,
                reference_context={
                    "packet_hash": packet_hash,
                    "source": packet.source,
                    "target": packet.target,
                    "actor": packet.actor,
                    "external_reference": packet.external_reference,
                    "previous_module_hash": self._get_previous_module_hash(),
                },
                payload={**root_payload, "gate": "alignment"},
            )
            alignment_hash = alignment_result.state_hash

            source_payload = {
                **root_payload,
                "gate": "genesis",
                "source": packet.source,
                "actor": packet.actor,
                "system_type": packet.system_type,
                "action": packet.action,
                "packet_hash": packet_hash,
                "time_hash": time_hash,
                "continuity_hash": continuity_hash,
                "alignment_hash": alignment_hash,
            }
            source_hash = self.stack.genesis_gate.source_hash(source_payload)
            if module_id not in self.kernel.MODULE_SOURCE_TYPES:
                raise KeyError(
                    f"Kernel MODULE_SOURCE_TYPES does not contain an entry for '{module_id}'. "
                    f"Available keys: {list(self.kernel.MODULE_SOURCE_TYPES.keys())}"
                )
            source_type = self.kernel.MODULE_SOURCE_TYPES[module_id]

            genesis_result = self.stack.genesis_gate.gate(
                self.stack.session_id,
                self.stack.genesis_id,
                module_id,
                origin_id=f"{packet.packet_id}_origin",
                creator_id=packet.actor,
                source_type=source_type,
                source_hash=source_hash,
                payload=source_payload,
            )
            genesis_hash = genesis_result.state_hash

            boundary_result = self.stack.boundary_gate.gate(
                self.stack.session_id,
                self.stack.boundary_id,
                module_id,
                {
                    **root_payload,
                    "gate": "boundary",
                    "source": packet.source,
                    "target": packet.target,
                    "boundary_domain": packet.boundary_domain,
                    "genesis_hash": genesis_hash,
                },
            )
            boundary_hash = boundary_result.state_hash

            reference_anchor = self.kernel.sha3_hash(
                self.kernel.canonical_bytes(
                    {
                        "packet_hash": packet_hash,
                        "external_reference": packet.external_reference,
                        "external_signature": packet.external_signature,
                        "boundary_hash": boundary_hash,
                    }
                )
            )
            reference_result = self.stack.reference_gate.gate(
                self.stack.session_id,
                self.stack.reference_id,
                module_id,
                reference_hash=reference_anchor,
                reference_type="module_state",
                payload={**root_payload, "gate": "reference"},
            )
            reference_hash = reference_result.state_hash

            cause_hash = self.kernel.sha3_hash(
                self.kernel.canonical_bytes(
                    {
                        "cause_id": packet.cause_id,
                        "packet_hash": packet_hash,
                        "reference_hash": reference_hash,
                        "alignment_hash": alignment_hash,
                    }
                )
            )
            causality_result = self.stack.causality_gate.gate(
                self.stack.session_id,
                self.stack.causality_id,
                module_id,
                cause_id=packet.cause_id,
                cause_hash=cause_hash,
                effect_id=packet.effect_id,
                payload={**root_payload, "gate": "causality"},
            )
            causality_hash = causality_result.state_hash

            observation_payload = {
                **root_payload,
                "gate": "consciousness",
                "observer_id": packet.observer_id,
                "time_hash": time_hash,
                "continuity_hash": continuity_hash,
                "alignment_hash": alignment_hash,
                "genesis_hash": genesis_hash,
                "boundary_hash": boundary_hash,
                "reference_hash": reference_hash,
                "causality_hash": causality_hash,
            }
            observation_hash = self.stack.consciousness_gate.observation_hash(observation_payload)
            consciousness_result = self.stack.consciousness_gate.gate(
                self.stack.session_id,
                self.stack.consciousness_id,
                module_id,
                observation_hash=observation_hash,
                payload=observation_payload,
            )
            consciousness_hash = consciousness_result.state_hash

            coherence_result = self.stack.coherence_gate.gate(
                self.stack.session_id,
                self.stack.coherence_id,
                module_id,
                time_hash=time_hash,
                continuity_hash=continuity_hash,
                alignment_hash=alignment_hash,
                genesis_hash=genesis_hash,
                boundary_hash=boundary_hash,
                reference_hash=reference_hash,
                causality_hash=causality_hash,
                consciousness_hash=consciousness_hash,
                payload={**root_payload, "gate": "coherence"},
            )
            coherence_hash = coherence_result.state_hash
            self._set_previous_module_hash(coherence_hash)

            return SCAdmissionProof(
                decision=AdmissionDecision.ADMIT,
                packet_id=packet.packet_id,
                system_type=packet.system_type,
                action=packet.action,
                module_id=module_id,
                packet_hash=packet_hash,
                time_hash=time_hash,
                continuity_hash=continuity_hash,
                alignment_hash=alignment_hash,
                genesis_hash=genesis_hash,
                boundary_hash=boundary_hash,
                reference_hash=reference_hash,
                causality_hash=causality_hash,
                consciousness_hash=consciousness_hash,
                coherence_hash=coherence_hash,
                final_proof=coherence_result.display_hash,
                reason="quantum state admitted after nine-gate coherence",
            )

        except Exception as error:
            return SCAdmissionProof(
                decision=AdmissionDecision.DENY,
                packet_id=getattr(packet, "packet_id", "UNKNOWN"),
                system_type=getattr(packet, "system_type", "UNKNOWN"),
                action=getattr(packet, "action", "UNKNOWN"),
                module_id=SYSTEM_TO_MODULE.get(getattr(packet, "system_type", ""), "UNKNOWN"),
                packet_hash=packet.hash() if isinstance(packet, SCUniversalStatePacket) else "",
                reason=str(error),
            )


# =============================================================================
# QUANTUM EXECUTION TYPES
# =============================================================================

class QuantumBackendMode(str, Enum):
    DRY_RUN = "dry_run"
    AER = "aer"
    IBM = "ibm"


class QuantumJobDecision(str, Enum):
    DENIED_BY_SC = "DENIED_BY_SC"
    ADMITTED_DRY_RUN = "ADMITTED_DRY_RUN"
    ADMITTED_SIMULATED = "ADMITTED_SIMULATED"
    ADMITTED_SUBMITTED = "ADMITTED_SUBMITTED"
    ADMITTED_BACKEND_FAILED = "ADMITTED_BACKEND_FAILED"
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"


@dataclass(frozen=True)
class SCQiskitJobRequest:
    job_id: str = field(default_factory=lambda: f"qjob_{uuid.uuid4().hex}")
    actor: str = "quantum_operator"
    backend_name: str = "local_aer_simulator"
    backend_mode: str = QuantumBackendMode.DRY_RUN.value

    shots: int = 1024
    optimization_level: int = 1
    timeout_seconds: int = 300
    retry_attempts: int = 3
    retry_delay_seconds: float = 2.0

    qasm_text: Optional[str] = None
    circuit_name: str = "scqos_bell_demo"
    circuit_qubits: int = 2
    circuit_depth: int = 2
    circuit_operations: List[str] = field(default_factory=lambda: ["h", "cx", "measure"])

    declared_objective: str = "bridge_hardware"
    intent: str = "quantum job must prove coherence before backend submission"

    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def canonical(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SCQiskitJobResult:
    decision: QuantumJobDecision

    sc_admitted: bool
    backend_executed: bool

    job_id: str
    backend_mode: str
    backend_name: str

    sc_packet_id: str = ""
    sc_proof: str = ""
    sc_reason: str = ""

    qiskit_job_id: str = ""
    counts: Dict[str, int] = field(default_factory=dict)

    parse_status: str = ""
    raw_result_summary: Dict[str, Any] = field(default_factory=dict)

    error: str = ""
    executed_at: str = field(default_factory=utc_now_iso)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


# =============================================================================
# QUANTUM ADAPTER
# =============================================================================

class SupremeComputationQiskitAdapter:
    """
    Quantum execution authority.

    SC admission and Qiskit execution are separate facts:
        sc_admitted means the nine gates admitted the state.
        backend_executed means Qiskit or IBM actually ran after admission.
    """

    def __init__(
        self,
        root: Optional[SCQOSRootAdmissionAdapter] = None,
        observer_id: str = "scqos_quantum_observer",
        substrate_id: str = "scqos_quantum_substrate",
        max_history: int = 1000,
    ):
        self.root = root or SCQOSRootAdmissionAdapter(
            observer_id=observer_id,
            substrate_id=substrate_id,
        )
        self.history: Deque[SCQiskitJobResult] = deque(maxlen=max_history)

    def admit_quantum_job(self, request: SCQiskitJobRequest) -> SCAdmissionProof:
        packet = self.root.make_packet(
            system_type=ExternalSystemType.QISKIT_JOB.value,
            action=f"quantum_submit:{request.backend_mode}:{request.backend_name}",
            actor=request.actor,
            source="supreme_computation_quantum_adapter",
            target=request.backend_name,
            declared_objective=request.declared_objective,
            payload={
                "job_id": request.job_id,
                "intent": request.intent,
                "backend_mode": request.backend_mode,
                "backend_name": request.backend_name,
                "shots": request.shots,
                "optimization_level": request.optimization_level,
                "timeout_seconds": request.timeout_seconds,
                "retry_attempts": request.retry_attempts,
                "retry_delay_seconds": request.retry_delay_seconds,
                "circuit_name": request.circuit_name,
                "circuit_qubits": request.circuit_qubits,
                "circuit_depth": request.circuit_depth,
                "circuit_operations": request.circuit_operations,
                "qasm_hash_present": bool(request.qasm_text),
                "payload": request.payload,
                "created_at": request.created_at,
            },
            boundary_domain="quantum_domain",
            external_reference=request.job_id,
            external_signature=self._job_signature(request),
        )
        return self.root.admit(packet)

    def run(self, request: SCQiskitJobRequest, circuit: Optional[Any] = None) -> SCQiskitJobResult:
        proof = self.admit_quantum_job(request)

        if proof.decision != AdmissionDecision.ADMIT:
            result = SCQiskitJobResult(
                decision=QuantumJobDecision.DENIED_BY_SC,
                sc_admitted=False,
                backend_executed=False,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
            )
            self.history.append(result)
            return result

        mode = request.backend_mode.lower().strip()

        if mode == QuantumBackendMode.DRY_RUN.value:
            result = SCQiskitJobResult(
                decision=QuantumJobDecision.ADMITTED_DRY_RUN,
                sc_admitted=True,
                backend_executed=False,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
                parse_status="not_applicable_dry_run",
                raw_result_summary={
                    "message": "SC admitted quantum job. Dry run selected. No quantum backend touched.",
                    "circuit_name": request.circuit_name,
                    "shots": request.shots,
                },
            )
            self.history.append(result)
            return result

        if mode == QuantumBackendMode.AER.value:
            result = self._run_aer(request, proof, circuit)
            self.history.append(result)
            return result

        if mode == QuantumBackendMode.IBM.value:
            result = self._run_ibm_runtime(request, proof, circuit)
            self.history.append(result)
            return result

        result = SCQiskitJobResult(
            decision=QuantumJobDecision.UNSUPPORTED_MODE,
            sc_admitted=True,
            backend_executed=False,
            job_id=request.job_id,
            backend_mode=request.backend_mode,
            backend_name=request.backend_name,
            sc_packet_id=proof.packet_id,
            sc_proof=proof.final_proof,
            sc_reason=proof.reason,
            parse_status="not_applicable",
            error=f"unsupported backend mode: {request.backend_mode}",
        )
        self.history.append(result)
        return result

    def _run_aer(self, request: SCQiskitJobRequest, proof: SCAdmissionProof, circuit: Optional[Any]) -> SCQiskitJobResult:
        try:
            try:
                from qiskit import QuantumCircuit, transpile
                from qiskit_aer import AerSimulator
            except ImportError as import_error:
                raise ImportError(
                    "Qiskit Aer dependencies missing. Install with: pip install qiskit qiskit-aer"
                ) from import_error

            qc = circuit or self._build_default_bell_circuit(QuantumCircuit)
            simulator = AerSimulator()
            compiled = transpile(qc, simulator, optimization_level=request.optimization_level)
            job = simulator.run(compiled, shots=request.shots)
            result = job.result()
            counts = result.get_counts(compiled)

            job_id_attr = getattr(job, "job_id", None)
            qiskit_job_id = str(job_id_attr() if callable(job_id_attr) else job_id_attr or "")

            return SCQiskitJobResult(
                decision=QuantumJobDecision.ADMITTED_SIMULATED,
                sc_admitted=True,
                backend_executed=True,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
                qiskit_job_id=qiskit_job_id,
                counts={str(k): int(v) for k, v in counts.items()},
                parse_status="counts_parsed",
                raw_result_summary={
                    "backend": "AerSimulator",
                    "shots": request.shots,
                    "operations": request.circuit_operations,
                },
            )

        except Exception as error:
            return SCQiskitJobResult(
                decision=QuantumJobDecision.ADMITTED_BACKEND_FAILED,
                sc_admitted=True,
                backend_executed=False,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
                parse_status="backend_failed_before_counts",
                error=redact_secret(error),
            )

    def _run_ibm_runtime(self, request: SCQiskitJobRequest, proof: SCAdmissionProof, circuit: Optional[Any]) -> SCQiskitJobResult:
        try:
            token = os.getenv("IBM_QUANTUM_TOKEN")
            if not token:
                raise RuntimeError("IBM_QUANTUM_TOKEN is not set")

            try:
                from qiskit import QuantumCircuit
                from qiskit_ibm_runtime import QiskitRuntimeService
                try:
                    from qiskit_ibm_runtime import SamplerV2 as Sampler
                except ImportError as version_error:
                    raise ImportError(
                        "SamplerV2 not found in qiskit-ibm-runtime. "
                        "SamplerV2 requires qiskit-ibm-runtime >= 0.20.0. "
                        "Update with: pip install -U qiskit-ibm-runtime"
                    ) from version_error
            except ImportError as import_error:
                raise ImportError(
                    "IBM Runtime dependencies missing or outdated. Install/update with: pip install -U qiskit qiskit-ibm-runtime"
                ) from import_error

            service = retry_call(
                lambda: QiskitRuntimeService(channel="ibm_quantum", token=token),
                attempts=request.retry_attempts,
                delay_seconds=request.retry_delay_seconds,
            )
            backend = retry_call(
                lambda: service.backend(request.backend_name),
                attempts=request.retry_attempts,
                delay_seconds=request.retry_delay_seconds,
            )

            status = self._safe_backend_status(backend)
            if status.get("operational") is False:
                raise RuntimeError(f"IBM backend not operational: {request.backend_name} status={status}")

            qc = circuit or self._build_default_bell_circuit(QuantumCircuit)

            sampler = Sampler(mode=backend)
            job = retry_call(
                lambda: sampler.run([qc], shots=request.shots),
                attempts=request.retry_attempts,
                delay_seconds=request.retry_delay_seconds,
            )
            job_result = job.result(timeout=request.timeout_seconds)

            summary = self._summarize_sampler_v2_result(job_result)
            summary["backend_status"] = status
            job_id_attr = getattr(job, "job_id", None)
            qiskit_job_id = str(job_id_attr() if callable(job_id_attr) else job_id_attr or "")

            counts = summary.get("counts", {})
            parse_status = summary.get("parse_status", "unknown")

            return SCQiskitJobResult(
                decision=QuantumJobDecision.ADMITTED_SUBMITTED,
                sc_admitted=True,
                backend_executed=True,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
                qiskit_job_id=qiskit_job_id,
                counts=counts,
                parse_status=parse_status,
                raw_result_summary=summary,
            )

        except Exception as error:
            return SCQiskitJobResult(
                decision=QuantumJobDecision.ADMITTED_BACKEND_FAILED,
                sc_admitted=True,
                backend_executed=False,
                job_id=request.job_id,
                backend_mode=request.backend_mode,
                backend_name=request.backend_name,
                sc_packet_id=proof.packet_id,
                sc_proof=proof.final_proof,
                sc_reason=proof.reason,
                parse_status="backend_failed_before_counts",
                error=redact_secret(error),
            )

    def _safe_backend_status(self, backend: Any) -> Dict[str, Any]:
        """
        Safely extract IBM backend operational status without crashing.

        Returns operational=True, False, or None when unknown.
        """
        try:
            status_attr = getattr(backend, "status", None)
            if status_attr is None:
                return {"operational": None, "reason": "backend_has_no_status_method"}

            status_obj = status_attr() if callable(status_attr) else status_attr

            data: Dict[str, Any] = {
                "type": type(status_obj).__name__,
                "operational": None,
            }

            if hasattr(status_obj, "operational"):
                value = getattr(status_obj, "operational")
                data["operational"] = bool(value() if callable(value) else value)
                return data

            if hasattr(status_obj, "status"):
                value = getattr(status_obj, "status")
                raw_status = value() if callable(value) else value
                data["status"] = str(raw_status)
                data["operational"] = str(raw_status).lower() in {"active", "online", "available", "operational"}
                return data

            for key in ("pending_jobs", "status_msg", "message"):
                try:
                    value = getattr(status_obj, key, None)
                    if value is None:
                        continue
                    data[key] = value() if callable(value) else value
                except Exception as error:
                    data[f"{key}_error"] = redact_secret(error)

            return data

        except Exception as error:
            return {"operational": None, "error": redact_secret(error)}

    def _build_default_bell_circuit(self, circuit_class: Any) -> Any:
        qc = circuit_class(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])
        return qc

    def _summarize_sampler_v2_result(self, job_result: Any) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "type": type(job_result).__name__,
            "counts": {},
            "parse_status": "counts_not_found",
            "repr": repr(job_result)[:2000],
        }

        try:
            first = job_result[0]
            data = getattr(first, "data", None)

            if data is None:
                summary["parse_status"] = "no_data_attribute"
                return summary

            c_register = getattr(data, "c", None)
            if c_register is not None and hasattr(c_register, "get_counts"):
                counts = c_register.get_counts()
                summary["counts"] = {str(k): int(v) for k, v in counts.items()}
                summary["parse_status"] = "counts_parsed_register_c"
                return summary

            for name in dir(data):
                if name.startswith("_"):
                    continue
                obj = getattr(data, name, None)
                if hasattr(obj, "get_counts"):
                    counts = obj.get_counts()
                    summary["counts"] = {str(k): int(v) for k, v in counts.items()}
                    summary["register"] = name
                    summary["parse_status"] = f"counts_parsed_register_{name}"
                    return summary

            summary["parse_status"] = "no_counts_provider_found"
            return summary

        except Exception as error:
            summary["parse_status"] = "parse_error"
            summary["parse_error"] = str(error)
            return summary

    def _job_signature(self, request: SCQiskitJobRequest) -> str:
        raw = json.dumps(request.canonical(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha3_512(raw).hexdigest()

    def report(self) -> None:
        total = len(self.history)
        sc_admitted = sum(1 for r in self.history if r.sc_admitted)
        backend_executed = sum(1 for r in self.history if r.backend_executed)
        sc_denied = sum(1 for r in self.history if not r.sc_admitted)
        unsupported = sum(1 for r in self.history if r.decision == QuantumJobDecision.UNSUPPORTED_MODE)

        print("\nSUPREME COMPUTATION QUANTUM ADAPTER REPORT")
        print("=" * 88)
        print(f"Total quantum requests : {total}")
        print(f"SC admitted            : {sc_admitted}")
        print(f"SC denied              : {sc_denied}")
        print(f"Backend executed       : {backend_executed}")
        print(f"Unsupported mode       : {unsupported}")
        print("-" * 88)

        for item in self.history:
            print(
                f"{item.decision.value:26s} | "
                f"{item.backend_mode:8s} | "
                f"{item.backend_name:24s} | "
                f"proof={item.sc_proof or '—'} | "
                f"parse={item.parse_status or '—'}"
            )

        print("=" * 88)


# =============================================================================
# REQUEST HELPERS
# =============================================================================

def bell_dry_run_request(actor: str = "quantum_operator") -> SCQiskitJobRequest:
    return SCQiskitJobRequest(
        actor=actor,
        backend_mode=QuantumBackendMode.DRY_RUN.value,
        backend_name="dry_run_backend",
        shots=1024,
        circuit_name="bell_state_demo",
        circuit_qubits=2,
        circuit_depth=2,
        circuit_operations=["h", "cx", "measure"],
    )


def bell_aer_request(actor: str = "quantum_operator") -> SCQiskitJobRequest:
    return SCQiskitJobRequest(
        actor=actor,
        backend_mode=QuantumBackendMode.AER.value,
        backend_name="AerSimulator",
        shots=1024,
        circuit_name="bell_state_demo",
        circuit_qubits=2,
        circuit_depth=2,
        circuit_operations=["h", "cx", "measure"],
    )


def bell_ibm_request(
    backend_name: Optional[str] = None,
    actor: str = "quantum_operator",
) -> SCQiskitJobRequest:
    return SCQiskitJobRequest(
        actor=actor,
        backend_mode=QuantumBackendMode.IBM.value,
        backend_name=backend_name or os.getenv("IBM_QUANTUM_BACKEND", "ibm_brisbane"),
        shots=int(os.getenv("SCQOS_QISKIT_SHOTS", "1024")),
        circuit_name="bell_state_demo",
        circuit_qubits=2,
        circuit_depth=2,
        circuit_operations=["h", "cx", "measure"],
    )


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    mode = os.getenv("SCQOS_QISKIT_MODE", "dry_run").lower().strip()

    print("=" * 88)
    print("SUPREME COMPUTATION QUANTUM ADAPTER")
    print("Quantum request -> nine gates -> ADMIT or DENY -> Qiskit only after admission")
    print("=" * 88)

    adapter = SupremeComputationQiskitAdapter()

    if mode == QuantumBackendMode.AER.value:
        request = bell_aer_request()
    elif mode == QuantumBackendMode.IBM.value:
        request = bell_ibm_request()
    else:
        request = bell_dry_run_request()

    result = adapter.run(request)

    print(result.to_json())
    adapter.report()


if __name__ == "__main__":
    demo()
