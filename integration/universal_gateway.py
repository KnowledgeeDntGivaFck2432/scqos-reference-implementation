from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scqos_supreme_stack as sc


CONTRACT_ID = "SCQOS-UNIVERSAL-TRANSITION-v1"
DB_PATH = Path(
    os.getenv(
        "SCQOS_UNIVERSAL_DB",
        str(ROOT / "evidence/universal-integration/receipts.sqlite3")
    )
)

SECRET_FILE = ROOT / ".scqos-universal-secret"
LOCK = RLock()


def _secret() -> str:
    env = os.getenv("SCQOS_SECRET_KEY")
    if env:
        return env

    if os.getenv("SCQOS_PRODUCTION", "0") == "1":
        raise RuntimeError(
            "SCQOS_SECRET_KEY required when SCQOS_PRODUCTION=1"
        )

    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(64) + "\n")
        SECRET_FILE.chmod(0o600)

    return SECRET_FILE.read_text().strip()


def canon(value: Dict[str, Any]) -> bytes:
    return sc.canonical_bytes(value)


def sha(value: Dict[str, Any]) -> str:
    return sc.sha256_hash(canon(value))


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
      CREATE TABLE IF NOT EXISTS receipts (
        transition_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        created_at REAL NOT NULL,
        decision TEXT NOT NULL,
        prior_receipt_hash TEXT,
        receipt_hash TEXT NOT NULL,
        receipt_json TEXT NOT NULL
      )
    """)
    conn.commit()
    return conn


def previous_receipt_hash(tenant_id: str) -> Optional[str]:
    with db() as conn:
        row = conn.execute(
            """
            SELECT receipt_hash
            FROM receipts
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        return row["receipt_hash"] if row else None


class Authority(BaseModel):
    model_config = ConfigDict(extra="allow")

    principal_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    external_system: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    authority: Authority
    intent: str = Field(min_length=1)

    evidence: Dict[str, Any]
    current_state: Dict[str, Any]
    proposed_transition: Dict[str, Any]
    expected_consequence: Dict[str, Any]

    metadata: Dict[str, Any] = Field(default_factory=dict)


class TransitionResponse(BaseModel):
    contract_id: str
    transition_id: str
    decision: Literal["PERMIT", "HOLD", "REJECT"]
    execution_authorized: bool

    request_hash: str
    contract_hash: str
    prior_receipt_hash: Optional[str]

    gate_proofs: Dict[str, str]
    final_proof: Optional[str]

    reason: str
    receipt_hash: str
    receipt: Dict[str, Any]


def reject_response(
    request: TransitionRequest,
    transition_id: str,
    request_hash: str,
    contract_hash: str,
    prior_hash: Optional[str],
    reason: str,
) -> TransitionResponse:

    receipt = {
        "contract_id": CONTRACT_ID,
        "transition_id": transition_id,
        "tenant_id": request.tenant_id,
        "external_system": request.external_system,
        "decision": "REJECT",
        "execution_authorized": False,
        "request_hash": request_hash,
        "contract_hash": contract_hash,
        "prior_receipt_hash": prior_hash,
        "gate_proofs": {},
        "final_proof": None,
        "reason": reason,
        "created_at": time.time(),
    }

    receipt_hash = sha(receipt)

    return TransitionResponse(
        **receipt,
        receipt_hash=receipt_hash,
        receipt=receipt,
    )


def persist(result: TransitionResponse) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO receipts (
              transition_id,
              tenant_id,
              created_at,
              decision,
              prior_receipt_hash,
              receipt_hash,
              receipt_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.transition_id,
                result.receipt["tenant_id"],
                result.receipt["created_at"],
                result.decision,
                result.prior_receipt_hash,
                result.receipt_hash,
                json.dumps(
                    result.receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()


def govern_transition(req: TransitionRequest) -> TransitionResponse:
    """
    Transport-independent universal SCQOS entry point.

    Business-specific meaning stays OUTSIDE SCQOS.
    Every connector translates into this one contract.
    """

    with LOCK:

        raw = req.model_dump(mode="python")

        # Canonical identity of exact outside proposition.
        request_hash = sha(raw)

        contract_schema = json.loads(
            (
                ROOT /
                "integration/SCQOS-UNIVERSAL-TRANSITION-v1.schema.json"
            ).read_text()
        )
        contract_hash = sha(contract_schema)

        prior_hash = previous_receipt_hash(req.tenant_id)

        transition_material = {
            "contract_id": CONTRACT_ID,
            "request_hash": request_hash,
            "contract_hash": contract_hash,
            "prior_receipt_hash": prior_hash,
        }

        transition_id = sha(transition_material)

        # Basic authority proposition.
        if req.authority.scope.strip().lower() in {
            "",
            "none",
            "unauthorized",
            "deny",
        }:
            result = reject_response(
                req,
                transition_id,
                request_hash,
                contract_hash,
                prior_hash,
                "authority scope does not authorize execution",
            )
            persist(result)
            return result

        # We use the existing generic control surface as the universal
        # business-independent execution boundary.
        module = "control_surface"
        secret = _secret()

        try:
            time_gate = sc.TimeGate(max_drift_ms=5000.0)
            continuity = sc.ContinuityGate(secret, "universal-node")
            alignment = sc.AlignmentGate(
                secret,
                "universal-node",
                enforce_substrate=False,
            )
            genesis = sc.GenesisGate(secret, "universal-node")
            boundary = sc.BoundaryGate(secret, "universal-node")
            reference = sc.ReferenceGate(secret, "universal-node")
            causality = sc.CausalityGate(secret, "universal-node")
            consciousness = sc.ConsciousnessGate(
                secret,
                "universal-node",
                observer_id="universal-observer",
                substrate_id="universal-integration-plane",
                enforce_substrate=False,
            )
            coherence = sc.CoherenceGate(secret, "universal-node")

            session = transition_id

            common_payload = {
                "contract_id": CONTRACT_ID,
                "transition_id": transition_id,
                "tenant_id": req.tenant_id,
                "external_system": req.external_system,
                "subject": req.subject,
                "authority": req.authority.model_dump(mode="python"),
                "request_hash": request_hash,
                "contract_hash": contract_hash,
                "prior_receipt_hash": prior_hash,
                "evidence": req.evidence,
                "current_state": req.current_state,
                "proposed_transition": req.proposed_transition,
                "expected_consequence": req.expected_consequence,
                "metadata": req.metadata,
            }

            # 1. TIME
            ts = time_gate.next_state(module, common_payload)
            tr = time_gate.check(ts)
            if not tr.coherent:
                raise RuntimeError(f"TIME: {tr.reason}")

            # 2. CONTINUITY
            cr = continuity.gate(
                session,
                "universal-continuity",
                module,
                {
                    **common_payload,
                    "time_hash": tr.state_hash,
                },
            )

            # 3. ALIGNMENT
            ar = alignment.gate(
                session,
                "universal-alignment",
                module,
                intent=req.intent,
                declared_objective="operate_control_surface",
                causal_trigger_hash=cr.state_hash,
                boundary_domain="trusted_runtime",
                reference_context={
                    "tenant_id": req.tenant_id,
                    "external_system": req.external_system,
                    "prior_receipt_hash": prior_hash,
                },
                payload=common_payload,
            )

            # 4. GENESIS
            source = {
                "external_system": req.external_system,
                "subject": req.subject,
                "authority": req.authority.model_dump(mode="python"),
                "evidence": req.evidence,
                "current_state": req.current_state,
                "request_hash": request_hash,
            }
            source_hash = genesis.source_hash(source)

            gr = genesis.gate(
                session,
                "universal-genesis",
                module,
                origin_id=f"{req.tenant_id}:{req.external_system}:{req.subject}",
                creator_id=req.authority.principal_id,
                source_type="system",
                source_hash=source_hash,
                payload=common_payload,
            )

            # 5. BOUNDARY
            br = boundary.gate(
                session,
                "universal-boundary",
                module,
                common_payload,
            )

            # 6. REFERENCE
            reference_material = {
                "evidence": req.evidence,
                "current_state": req.current_state,
                "authority": req.authority.model_dump(mode="python"),
            }
            reference_hash = sha(reference_material)

            rr = reference.gate(
                session,
                "universal-reference",
                module,
                reference_hash=reference_hash,
                reference_type="module_state",
                payload=common_payload,
            )

            # 7. CAUSALITY
            cause_material = {
                "intent": req.intent,
                "current_state": req.current_state,
                "proposed_transition": req.proposed_transition,
                "reference_hash": rr.state_hash,
            }
            cause_hash = sha(cause_material)

            car = causality.gate(
                session,
                "universal-causality",
                module,
                cause_id=f"{transition_id}:cause",
                cause_hash=cause_hash,
                effect_id=f"{transition_id}:effect",
                payload=common_payload,
            )

            # 8. CONSCIOUSNESS / OBSERVATION
            observation = {
                **common_payload,
                "time_hash": tr.state_hash,
                "continuity_hash": cr.state_hash,
                "alignment_hash": ar.state_hash,
                "genesis_hash": gr.state_hash,
                "boundary_hash": br.state_hash,
                "reference_hash": rr.state_hash,
                "causality_hash": car.state_hash,
            }

            observation_hash = consciousness.observation_hash(
                observation
            )

            conr = consciousness.gate(
                session,
                "universal-consciousness",
                module,
                observation_hash=observation_hash,
                payload=observation,
            )

            # 9. COHERENCE
            cor = coherence.gate(
                session,
                "universal-coherence",
                module,
                time_hash=tr.state_hash,
                continuity_hash=cr.state_hash,
                alignment_hash=ar.state_hash,
                genesis_hash=gr.state_hash,
                boundary_hash=br.state_hash,
                reference_hash=rr.state_hash,
                causality_hash=car.state_hash,
                consciousness_hash=conr.state_hash,
                payload=common_payload,
            )

            gate_proofs = {
                "time": tr.state_hash,
                "continuity": cr.state_hash,
                "alignment": ar.state_hash,
                "genesis": gr.state_hash,
                "boundary": br.state_hash,
                "reference": rr.state_hash,
                "causality": car.state_hash,
                "consciousness": conr.state_hash,
                "coherence": cor.state_hash,
            }

            if not all(gate_proofs.values()):
                raise RuntimeError(
                    "one or more governance proofs are empty"
                )

            receipt = {
                "contract_id": CONTRACT_ID,
                "transition_id": transition_id,
                "tenant_id": req.tenant_id,
                "external_system": req.external_system,
                "subject": req.subject,

                "decision": "PERMIT",
                "execution_authorized": True,

                "request_hash": request_hash,
                "contract_hash": contract_hash,
                "prior_receipt_hash": prior_hash,

                "gate_proofs": gate_proofs,
                "final_proof": cor.state_hash,

                "proposed_transition_hash":
                    sha(req.proposed_transition),

                "expected_consequence_hash":
                    sha(req.expected_consequence),

                "reason":
                    "all SCQOS universal transition proofs coherent",

                "created_at": time.time(),
            }

            receipt_hash = sha(receipt)

            result = TransitionResponse(
                contract_id=CONTRACT_ID,
                transition_id=transition_id,
                decision="PERMIT",
                execution_authorized=True,
                request_hash=request_hash,
                contract_hash=contract_hash,
                prior_receipt_hash=prior_hash,
                gate_proofs=gate_proofs,
                final_proof=cor.state_hash,
                reason=receipt["reason"],
                receipt_hash=receipt_hash,
                receipt=receipt,
            )

            persist(result)
            return result

        except (
            ValueError,
            TypeError,
            sc.SCQOSCanonicalizationError,
        ) as exc:

            result = reject_response(
                req,
                transition_id,
                request_hash,
                contract_hash,
                prior_hash,
                f"contract rejected: {exc}",
            )

            persist(result)
            return result

        except Exception as exc:

            receipt = {
                "contract_id": CONTRACT_ID,
                "transition_id": transition_id,
                "tenant_id": req.tenant_id,
                "external_system": req.external_system,
                "decision": "HOLD",
                "execution_authorized": False,
                "request_hash": request_hash,
                "contract_hash": contract_hash,
                "prior_receipt_hash": prior_hash,
                "gate_proofs": {},
                "final_proof": None,
                "reason": f"governance hold: {exc}",
                "created_at": time.time(),
            }

            receipt_hash = sha(receipt)

            result = TransitionResponse(
                **receipt,
                receipt_hash=receipt_hash,
                receipt=receipt,
            )

            persist(result)
            return result


app = FastAPI(
    title="SCQOS Universal Integration Plane",
    version="1.0.0",
    description=(
        "Business-agnostic governed transition interface. "
        "External systems translate their workflow into one "
        "SCQOS universal transition contract."
    ),
)


@app.get("/v1/health")
def health():
    return {
        "status": "ONLINE",
        "contract_id": CONTRACT_ID,
        "canonicalization_id": sc.SCQOS_CANONICALIZATION_ID,
        "transport": "HTTP",
        "core": "SCQOS",
    }


@app.post("/v1/transition", response_model=TransitionResponse)
def transition(request: TransitionRequest):
    return govern_transition(request)


@app.get("/v1/receipt/{transition_id}")
def receipt(transition_id: str):
    with db() as conn:
        row = conn.execute(
            """
            SELECT receipt_json, receipt_hash
            FROM receipts
            WHERE transition_id = ?
            """,
            (transition_id,),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="receipt not found",
            )

        return {
            "receipt_hash": row["receipt_hash"],
            "receipt": json.loads(row["receipt_json"]),
        }
