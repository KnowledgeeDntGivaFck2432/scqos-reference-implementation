"""Deterministic Shadow Clone birth, lineage, and invariant qualification.

This module deliberately contains no model calls and no network calls.  A model
may propose a clone, but only this deterministic protocol can qualify its
identity and place it into the existing SCQOS action plane.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


ARCHITECTURE_ID = "SUPREME-MIND-59-FACULTY-UNIVERSE-V1"
SHADOW_CLONE_PROTOCOL = "SHADOW-CLONE-RECURSIVE-EXECUTION-V1"
CANONICALIZATION_AUTHORITY = "SCQOS-C14N-JCS-NFC-1"
SOVEREIGN_PRINCIPAL = "SOVEREIGN_HUMAN"

INVARIANTS = (
    "time",
    "continuity",
    "alignment",
    "genesis",
    "boundary",
    "reference",
    "causality",
    "consciousness",
)

RESULT_INVARIANTS = (*INVARIANTS, "coherence")

READ_ONLY_ACTIONS = {
    "analyze",
    "classify",
    "draft",
    "forecast",
    "inspect",
    "monitor",
    "prepare",
    "read",
    "recommend",
    "search",
    "summarize",
}

_ROLE_ID = re.compile(r"^R(?:0[1-9]|[1-5][0-9])$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _clone_id(seed: Mapping[str, Any]) -> str:
    return "sc:clone:sha256:" + sha256(seed)


def make_clone_birth(
    *,
    role_id: str,
    task_id: str,
    business_id: str,
    objective: str,
    expected_output: str,
    evidence_refs: Iterable[str],
    parent_clone_id: str = "sc:clone:root:sovereign",
    parent_role_id: str = "R01",
    parent_depth: int = -1,
    requested_action: str = "analyze",
    why_multiply: str = "A separate bounded worker is required for this task.",
    ttl_seconds: int = 900,
    max_children: int = 8,
    spend_limit_usd: str = "0.00",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a canonical clone-birth proposal; this does not admit it."""

    moment = now or utc_now()
    seed = {
        "protocol": SHADOW_CLONE_PROTOCOL,
        "architecture_id": ARCHITECTURE_ID,
        "principal_id": SOVEREIGN_PRINCIPAL,
        "parent_clone_id": parent_clone_id,
        "parent_role_id": parent_role_id,
        "role_id": role_id,
        "task_id": task_id,
        "business_id": business_id,
        "depth": parent_depth + 1,
        "objective": objective.strip(),
        "expected_output": expected_output.strip(),
        "requested_action": requested_action,
        "why_multiply": why_multiply.strip(),
        "requested_at": iso_utc(moment),
    }
    proposal = {
        **seed,
        "clone_id": _clone_id(seed),
        "expires_at": iso_utc(moment + timedelta(seconds=ttl_seconds)),
        "ttl_seconds": ttl_seconds,
        "max_children": max_children,
        "spend_limit_usd": str(spend_limit_usd),
        "evidence_refs": sorted({str(ref) for ref in evidence_refs if str(ref)}),
        "canonicalization_authority": CANONICALIZATION_AUTHORITY,
    }
    proposal["birth_sha256"] = sha256(proposal)
    return proposal


def evaluate_clone_birth(
    proposal: Mapping[str, Any],
    *,
    valid_role_ids: Iterable[str],
    parent: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    max_depth: int = 8,
    max_ttl_seconds: int = 3600,
    max_children: int = 32,
) -> dict[str, Any]:
    """Evaluate all eight invariants and coherence for a clone birth.

    Structural contradictions are REJECT.  Missing or presently insufficient
    evidence is HOLD.  Only a fully coherent proposal is PERMIT.
    """

    valid_roles = set(valid_role_ids)
    moment = now or utc_now()
    proofs: dict[str, dict[str, Any]] = {}
    structural_failure = False

    def proof(name: str, passed: bool, reason: str, evidence: Any = None) -> None:
        nonlocal structural_failure
        proofs[name] = {
            "passed": bool(passed),
            "reason": reason,
            "evidence": evidence,
        }

    try:
        requested_at = parse_utc(str(proposal.get("requested_at", "")))
        expires_at = parse_utc(str(proposal.get("expires_at", "")))
        ttl = int(proposal.get("ttl_seconds", 0))
        clock_skew = abs((moment - requested_at).total_seconds())
        time_ok = (
            0 < ttl <= max_ttl_seconds
            and expires_at > moment
            and expires_at >= requested_at
            and clock_skew <= max_ttl_seconds
        )
        proof(
            "time",
            time_ok,
            "CURRENT_BOUNDED_LIFETIME" if time_ok else "STALE_OR_INVALID_LIFETIME",
            {"requested_at": iso_utc(requested_at), "expires_at": iso_utc(expires_at)},
        )
    except (TypeError, ValueError):
        proof("time", False, "TIME_PROOF_INVALID")

    parent_id = str(proposal.get("parent_clone_id", ""))
    depth = proposal.get("depth")
    expected_depth = 0 if parent is None else int(parent.get("depth", -1)) + 1
    continuity_ok = bool(parent_id) and isinstance(depth, int) and depth == expected_depth
    if parent is not None:
        continuity_ok = continuity_ok and parent_id == parent.get("clone_id")
    proof(
        "continuity",
        continuity_ok,
        "PARENT_LINEAGE_CONTINUOUS" if continuity_ok else "PARENT_LINEAGE_BROKEN",
        {"parent_clone_id": parent_id, "depth": depth, "expected_depth": expected_depth},
    )

    objective = str(proposal.get("objective", "")).strip()
    expected_output = str(proposal.get("expected_output", "")).strip()
    alignment_ok = bool(objective and expected_output)
    proof(
        "alignment",
        alignment_ok,
        "OBJECTIVE_AND_OUTPUT_EXPLICIT" if alignment_ok else "OBJECTIVE_OR_OUTPUT_MISSING",
    )

    genesis_ok = (
        proposal.get("protocol") == SHADOW_CLONE_PROTOCOL
        and proposal.get("architecture_id") == ARCHITECTURE_ID
        and proposal.get("canonicalization_authority") == CANONICALIZATION_AUTHORITY
        and bool(proposal.get("birth_sha256"))
    )
    proof(
        "genesis",
        genesis_ok,
        "SOURCE_ARCHITECTURE_BOUND" if genesis_ok else "SOURCE_ARCHITECTURE_MISMATCH",
        proposal.get("architecture_id"),
    )
    structural_failure = structural_failure or proposal.get("architecture_id") not in (None, ARCHITECTURE_ID)

    role_id = str(proposal.get("role_id", ""))
    action = str(proposal.get("requested_action", ""))
    child_limit = proposal.get("max_children")
    boundary_ok = (
        bool(_ROLE_ID.fullmatch(role_id))
        and role_id in valid_roles
        and action in READ_ONLY_ACTIONS
        and isinstance(depth, int)
        and 0 <= depth <= max_depth
        and isinstance(child_limit, int)
        and 0 <= child_limit <= max_children
    )
    proof(
        "boundary",
        boundary_ok,
        "ROLE_ACTION_AND_RECURSION_BOUNDED" if boundary_ok else "ROLE_ACTION_OR_RECURSION_OUTSIDE_BOUNDARY",
        {"role_id": role_id, "action": action, "depth": depth, "max_children": child_limit},
    )
    structural_failure = structural_failure or (bool(role_id) and role_id not in valid_roles)

    references_ok = all(
        bool(str(proposal.get(field, "")).strip())
        for field in ("clone_id", "task_id", "business_id", "parent_role_id")
    )
    proof(
        "reference",
        references_ok,
        "IDENTITIES_EXPLICIT" if references_ok else "IDENTITY_REFERENCE_MISSING",
    )

    why = str(proposal.get("why_multiply", "")).strip()
    causal_ok = bool(why and expected_output)
    proof(
        "causality",
        causal_ok,
        "MULTIPLICATION_HAS_EXPECTED_CONSEQUENCE" if causal_ok else "MULTIPLICATION_CAUSE_UNPROVEN",
        why or None,
    )

    consciousness_ok = (
        proposal.get("principal_id") == SOVEREIGN_PRINCIPAL
        and bool(proposal.get("parent_role_id"))
    )
    proof(
        "consciousness",
        consciousness_ok,
        "SOVEREIGN_AND_PARENT_ACCOUNTABLE" if consciousness_ok else "ACCOUNTABILITY_MISSING",
        proposal.get("principal_id"),
    )
    structural_failure = structural_failure or proposal.get("principal_id") not in (None, SOVEREIGN_PRINCIPAL)

    expected_birth_hash = sha256({k: v for k, v in proposal.items() if k != "birth_sha256"})
    hash_ok = proposal.get("birth_sha256") == expected_birth_hash
    all_pass = all(proofs.get(name, {}).get("passed") for name in INVARIANTS)
    coherence_ok = all_pass and hash_ok
    proofs["coherence"] = {
        "passed": coherence_ok,
        "reason": "ALL_INVARIANTS_SIMULTANEOUSLY_TRUE" if coherence_ok else "INVARIANTS_OR_CANONICAL_IDENTITY_CONFLICT",
        "evidence": {"birth_sha256_matches": hash_ok},
    }

    if coherence_ok:
        state, reason = "PERMIT", "CLONE_BIRTH_QUALIFIED"
    elif structural_failure:
        state, reason = "REJECT", "CLONE_BIRTH_CONTRADICTS_CONSTITUTION"
    else:
        state, reason = "HOLD", "CLONE_BIRTH_REQUIRES_REQUALIFICATION"

    result = {
        "receipt_id": str(uuid.uuid4()),
        "timestamp": iso_utc(moment),
        "protocol": SHADOW_CLONE_PROTOCOL,
        "architecture_id": ARCHITECTURE_ID,
        "clone_id": proposal.get("clone_id"),
        "parent_clone_id": proposal.get("parent_clone_id"),
        "role_id": proposal.get("role_id"),
        "task_id": proposal.get("task_id"),
        "state": state,
        "reason": reason,
        "invariant_proofs": proofs,
        "proposal_sha256": sha256(proposal),
    }
    result["receipt_sha256"] = sha256(result)
    return result


def role_ids_from_manifest(manifest: Mapping[str, Any]) -> set[str]:
    return {str(role["role_id"]) for role in manifest.get("roles", [])}


def evaluate_result_invariants(
    assessment: Any,
    *,
    result: Mapping[str, Any] | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    max_evidence_age_seconds: int = 3600,
) -> dict[str, Any]:
    """Turn a model's invariant report into a deterministic consequence state.

    The model supplies observations, but it cannot award itself PERMIT.  Every
    invariant and coherence must be present and explicitly begin with PASS.
    Anything else is a fail-closed HOLD.
    """

    values = assessment if isinstance(assessment, Mapping) else {}
    proofs: dict[str, dict[str, Any]] = {}
    for name in RESULT_INVARIANTS:
        value = values.get(name)
        passed = isinstance(value, str) and value.strip().upper().startswith("PASS")
        proofs[name] = {
            "passed": passed,
            "reported": value,
            "reason": "RESULT_INVARIANT_PASS" if passed else "RESULT_INVARIANT_MISSING_OR_HOLD",
        }

    if result is not None and expected_identity is not None:
        moment = now or utc_now()
        identity = result.get("identity") if isinstance(result.get("identity"), Mapping) else {}
        evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
        valid_evidence: list[dict[str, Any]] = []
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url", ""))
            parsed = urlparse(url)
            claim_ok = bool(str(item.get("claim", "")).strip())
            url_ok = parsed.scheme == "https" and bool(parsed.netloc)
            time_ok = False
            try:
                observed = parse_utc(str(item.get("observed_at", "")))
                age = (moment - observed).total_seconds()
                time_ok = -300 <= age <= max_evidence_age_seconds
            except ValueError:
                pass
            valid_evidence.append({
                "url": url,
                "url_ok": url_ok,
                "claim_ok": claim_ok,
                "time_ok": time_ok,
            })

        all_evidence_current = bool(valid_evidence) and all(item["time_ok"] for item in valid_evidence)
        all_evidence_referenced = bool(valid_evidence) and all(
            item["url_ok"] and item["claim_ok"] for item in valid_evidence
        )
        identity_matches = {
            field: identity.get(field) == value
            for field, value in expected_identity.items()
        }
        all_identity_matches = bool(identity_matches) and all(identity_matches.values())
        summary_ok = bool(str(result.get("summary", "")).strip())
        consequence_ok = bool(str(result.get("consequence", "")).strip())

        deterministic = {
            "time": (all_evidence_current, {"evidence": valid_evidence}),
            "continuity": (all_identity_matches, {"identity_matches": identity_matches}),
            "alignment": (summary_ok and consequence_ok, {"summary": summary_ok, "consequence": consequence_ok}),
            "genesis": (all_evidence_referenced, {"evidence": valid_evidence}),
            "boundary": (True, {"enforced_before_harness": True}),
            "reference": (all_evidence_referenced, {"evidence": valid_evidence}),
            "causality": (consequence_ok and bool(valid_evidence), {"consequence": consequence_ok, "evidence_count": len(valid_evidence)}),
            "consciousness": (all_identity_matches, {"identity_matches": identity_matches}),
        }
        for name, (passed, evidence_value) in deterministic.items():
            proofs[name]["deterministic_passed"] = passed
            proofs[name]["deterministic_evidence"] = evidence_value
            proofs[name]["passed"] = proofs[name]["passed"] and passed
            if not passed:
                proofs[name]["reason"] = "RESULT_INVARIANT_DETERMINISTIC_PROOF_FAILED"

        pre_coherence = all(proofs[name]["passed"] for name in INVARIANTS)
        proofs["coherence"]["deterministic_passed"] = pre_coherence
        proofs["coherence"]["passed"] = proofs["coherence"]["passed"] and pre_coherence
        if not pre_coherence:
            proofs["coherence"]["reason"] = "RESULT_INVARIANTS_NOT_SIMULTANEOUSLY_TRUE"

    coherent = all(proof["passed"] for proof in proofs.values())
    result = {
        "state": "PERMIT" if coherent else "HOLD",
        "reason": (
            "ALL_RESULT_INVARIANTS_SIMULTANEOUSLY_TRUE"
            if coherent
            else "RESULT_INVARIANTS_NOT_COHERENT"
        ),
        "invariant_proofs": proofs,
    }
    result["assessment_sha256"] = sha256(result)
    return result
