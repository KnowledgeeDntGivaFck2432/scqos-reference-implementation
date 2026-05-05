"""
SCQOS ROOT ADAPTER
Universal Pre-Execution Admission Layer

External reality -> SC Universal State Packet -> Nine Gates -> ADMIT or DENY

Put this file beside your SCQOS kernel file.

By default it tries to import one of:
    scqos_reference_implementation.py
    scqos_kernel.py
    scqos.py
    main.py

Or set:
    SCQOS_KERNEL_MODULE=scqos_reference_implementation

Run:
    python scqos_root_adapter.py
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------
# KERNEL LOADER
# ---------------------------------------------------------------------

def load_scqos_kernel():
    preferred = os.getenv("SCQOS_KERNEL_MODULE")
    candidates = []

    if preferred:
        candidates.append(preferred)

    candidates.extend([
        "scqos_reference_implementation",
        "scqos_kernel",
        "scqos",
        "main",
    ])

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
            return module
        except Exception as error:
            last_error = error

    raise ImportError(
        "Could not load SCQOS kernel. Put this file beside your kernel or set "
        "SCQOS_KERNEL_MODULE. Last error: "
        f"{last_error}"
    )


KERNEL = load_scqos_kernel()


# ---------------------------------------------------------------------
# UNIVERSAL STATE PACKET
# ---------------------------------------------------------------------

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
    """
    Universal root packet.

    Every outside system must be translated into this shape before SCQOS
    decides whether execution is admitted or denied.
    """

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

    created_at: float = field(default_factory=time.time)
    sequence: int = 0

    external_reference: Optional[str] = None
    external_signature: Optional[str] = None

    def canonical(self) -> Dict[str, Any]:
        return asdict(self)

    def hash(self) -> str:
        return KERNEL.sha3_hash(KERNEL.canonical_bytes(self.canonical()))


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
    admitted_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


# ---------------------------------------------------------------------
# ROOT ADAPTER
# ---------------------------------------------------------------------

class SCQOSRootAdmissionAdapter:
    """
    Root authority.

    The seed proves the nine gates.
    The root forces external state through the nine gates.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        node_id: Optional[str] = None,
        session_id: Optional[str] = None,
        observer_id: str = "scqos_root_observer",
        substrate_id: str = "scqos_root_substrate",
        enforce_substrate: Optional[bool] = None,
    ):
        self.secret_key = secret_key or KERNEL.get_secret_key(required=False)
        self.node_id = node_id or os.getenv("SCQOS_NODE_ID", "node-alpha")
        self.session_id = session_id or f"scqos_root_session_{uuid.uuid4().hex}"

        if enforce_substrate is None:
            enforce_substrate = os.getenv("SCQOS_ENFORCE_SUBSTRATE", "0") == "1"

        self.stack = KERNEL.SCQOSSupremeCoherenceStack(
            secret_key=self.secret_key,
            node_id=self.node_id,
            session_id=self.session_id,
            observer_id=observer_id,
            substrate_id=substrate_id,
            substrate_fingerprint_override=KERNEL.get_substrate_fingerprint_override(),
            enforce_substrate=enforce_substrate,
        )

        self._sequence = 0

    def make_packet(
        self,
        system_type: str,
        action: str,
        actor: str,
        source: str,
        target: str,
        declared_objective: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        observer_id: str = "scqos_root_observer",
        boundary_domain: str = "scqos_boot",
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
        """
        Force external state through the nine gates.

        Any failed gate returns DENY with a reason.
        """

        try:
            module_id = SYSTEM_TO_MODULE[packet.system_type]
            packet_hash = packet.hash()

            root_payload = {
                "root": "scqos_universal_admission",
                "packet": packet.canonical(),
                "packet_hash": packet_hash,
                "platform": {
                    "python": platform.python_version(),
                    "system": platform.system(),
                    "machine": platform.machine(),
                },
            }

            # 1. TIME
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

            # 2. CONTINUITY
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

            # 3. ALIGNMENT
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
                    "previous_module_hash": self.stack._previous_module_hash,
                },
                payload={**root_payload, "gate": "alignment"},
            )
            alignment_hash = alignment_result.state_hash

            # 4. GENESIS
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

            source_type = KERNEL.MODULE_SOURCE_TYPES[module_id]
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

            # 5. BOUNDARY
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

            # 6. REFERENCE
            reference_anchor = KERNEL.sha3_hash(
                KERNEL.canonical_bytes(
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

            # 7. CAUSALITY
            cause_hash = KERNEL.sha3_hash(
                KERNEL.canonical_bytes(
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

            # 8. CONSCIOUSNESS / SUBSTRATE
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

            # 9. COHERENCE
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

            self.stack._previous_module_hash = coherence_hash

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
                reason="external state admitted after nine-gate coherence",
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

    def require_admission(self, packet: SCUniversalStatePacket) -> SCAdmissionProof:
        proof = self.admit(packet)
        if proof.decision != AdmissionDecision.ADMIT:
            raise RuntimeError(f"SCQOS ROOT DENIED EXECUTION: {proof.reason}")
        return proof


# ---------------------------------------------------------------------
# SAFE DEMO EXECUTION ADAPTER
# ---------------------------------------------------------------------

class PrintOnlyExecutionAdapter:
    """
    Safe demo adapter.

    It does not actually run external commands.
    It proves the root can admit or deny before execution.
    """

    def execute(self, packet: SCUniversalStatePacket, proof: SCAdmissionProof) -> Dict[str, Any]:
        return {
            "executed": True,
            "system_type": packet.system_type,
            "action": packet.action,
            "target": packet.target,
            "proof": proof.final_proof,
            "decision": proof.decision.value,
        }


def demo() -> Tuple[SCAdmissionProof, Dict[str, Any]]:
    root = SCQOSRootAdmissionAdapter()

    packet = root.make_packet(
        system_type=ExternalSystemType.API_REQUEST.value,
        action="admit_request",
        actor="scqos_architect",
        source="external_client",
        target="protected_api",
        declared_objective="verify_access",
        payload={
            "method": "POST",
            "path": "/execute",
            "body_hash": "demo_body_hash",
        },
        external_reference="demo_reference",
    )

    proof = root.require_admission(packet)
    result = PrintOnlyExecutionAdapter().execute(packet, proof)

    return proof, result


if __name__ == "__main__":
    proof, result = demo()
    print("SCQOS ROOT ADMISSION PROOF")
    print(proof.to_json())
    print("\nEXECUTION ADAPTER RESULT")
    print(json.dumps(result, indent=2, sort_keys=True))
