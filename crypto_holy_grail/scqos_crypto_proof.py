#!/usr/bin/env python3
"""SCQOS cryptocurrency pre-signing and post-execution proof harness.

This module is deliberately exchange-independent.  An exchange may supply funds or
market evidence, but it is never the authority that decides whether a transaction
may be signed.

The proof boundary is:

    declared intent -> complete evidence -> SCQOS decision -> signer ->
    validated consequence -> signed receipt

Only a PERMIT decision whose canonical transaction hash is still identical at the
signer is executable.  Missing or unhealthy evidence produces HOLD.  A proven
contradiction or policy violation produces REJECT.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Optional


SCHEMA_VERSION = "scqos.crypto-proof.v1"
TESTNET_RPC = "https://s.altnet.rippletest.net:51234/"
SEMANTIC_FIELDS = (
    "network",
    "chain_id",
    "transaction_type",
    "source",
    "destination",
    "destination_tag",
    "asset",
    "issuer",
    "amount",
    "flags",
    "memo",
)


class Decision(str, Enum):
    PERMIT = "PERMIT"
    HOLD = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class Finding:
    gate: str
    code: str
    decision: Decision
    message: str


@dataclass
class Evaluation:
    decision: Decision
    intent_hash: str
    transaction_hash: str
    evidence_hash: str
    policy_hash: str
    gate_status: dict[str, bool]
    findings: list[Finding] = field(default_factory=list)
    root_proof: dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["decision"] = self.decision.value
        for finding in value["findings"]:
            finding["decision"] = finding["decision"].value
        return value


@dataclass(frozen=True)
class FaultCase:
    name: str
    expected: Decision
    expected_code: str
    mutate: Callable[[MutableMapping[str, Any]], None]


def canonical_bytes(value: Any) -> bytes:
    """Stable JSON encoding suitable for hashes and HMAC receipts."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha3_512(canonical_bytes(value)).hexdigest()


def semantic_transaction(transaction: Mapping[str, Any]) -> dict[str, Any]:
    return {key: transaction.get(key) for key in SEMANTIC_FIELDS}


def _decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _is_xrpl_address(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        from xrpl.core.addresscodec import is_valid_classic_address

        return bool(is_valid_classic_address(value))
    except ImportError:
        # Fail closed when the chain-specific verifier is unavailable.
        return False


def _set_path(value: MutableMapping[str, Any], path: str, replacement: Any) -> None:
    cursor: MutableMapping[str, Any] = value
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = replacement


class SCQOSCryptoGovernor:
    """Chain-independent semantic governor placed immediately before signing."""

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

    def __init__(self, root_adapter: Any | None = None):
        self.root_adapter = root_adapter

    def evaluate(self, state: Mapping[str, Any]) -> Evaluation:
        state = copy.deepcopy(dict(state))
        intent = state.get("intent", {})
        tx = state.get("transaction", {})
        evidence = state.get("evidence", {})
        policy = state.get("policy", {})
        findings: list[Finding] = []

        def hold(gate: str, code: str, message: str) -> None:
            findings.append(Finding(gate, code, Decision.HOLD, message))

        def reject(gate: str, code: str, message: str) -> None:
            findings.append(Finding(gate, code, Decision.REJECT, message))

        # 1. TIME: the decision, ledger, approval, oracle and expiry must be current.
        now = _decimal(evidence.get("now"))
        created = _decimal(intent.get("created_at"))
        expires = _decimal(intent.get("expires_at"))
        ledger_closed = _decimal(evidence.get("ledger_closed_at"))
        max_ledger_age = _decimal(policy.get("max_ledger_age_seconds"))
        if None in (now, created, expires):
            hold("time", "TIME_MISSING", "decision time evidence is incomplete")
        else:
            if created > now + Decimal("5"):
                reject("time", "CREATED_IN_FUTURE", "intent claims a future creation time")
            if now > expires:
                reject("time", "INTENT_EXPIRED", "intent expired before admission")
        if evidence.get("ledger_validated") is not True:
            hold("time", "LEDGER_NOT_VALIDATED", "chain state is not from a validated ledger")
        if None in (now, ledger_closed, max_ledger_age):
            hold("time", "LEDGER_TIME_MISSING", "ledger freshness cannot be proven")
        elif now - ledger_closed > max_ledger_age:
            hold("time", "LEDGER_STALE", "validated ledger evidence is too old")
        if policy.get("price_required"):
            oracle_at = _decimal(evidence.get("oracle_observed_at"))
            max_oracle_age = _decimal(policy.get("max_oracle_age_seconds"))
            if None in (now, oracle_at, max_oracle_age):
                hold("time", "ORACLE_TIME_MISSING", "oracle freshness cannot be proven")
            elif now - oracle_at > max_oracle_age:
                hold("time", "ORACLE_STALE", "price evidence is too old")

        # 2. CONTINUITY: no replay, silent replacement, stale sequence or mutation.
        intent_id = intent.get("intent_id")
        if not intent_id:
            hold("continuity", "INTENT_ID_MISSING", "intent has no immutable identity")
        elif intent_id in set(evidence.get("consumed_intent_ids", [])):
            reject("continuity", "INTENT_REPLAY", "intent identity has already been consumed")
        if tx.get("sequence") != evidence.get("account_sequence"):
            reject("continuity", "SEQUENCE_MISMATCH", "transaction sequence does not match live account state")
        if evidence.get("previous_receipt_required") and (
            evidence.get("previous_receipt_hash") != intent.get("previous_receipt_hash")
        ):
            reject("continuity", "RECEIPT_CHAIN_BROKEN", "prior governed state was replaced or omitted")
        pre_hash = evidence.get("pre_autofill_semantic_hash")
        post_hash = digest(semantic_transaction(tx))
        if not pre_hash:
            hold("continuity", "PRE_AUTOFILL_HASH_MISSING", "pre-autofill transaction was not bound")
        elif pre_hash != post_hash:
            reject("continuity", "AUTOFILL_SEMANTIC_MUTATION", "semantic fields changed during transaction preparation")
        admitted_hash = evidence.get("admitted_transaction_hash")
        if admitted_hash and admitted_hash != digest(tx):
            reject("continuity", "POST_ADMISSION_MUTATION", "transaction changed after admission")
        if evidence.get("transaction_hash") in set(evidence.get("submitted_transaction_hashes", [])):
            reject("continuity", "DUPLICATE_SUBMISSION", "transaction hash was already submitted")

        # 3. ALIGNMENT: the exact transaction must still express declared intent.
        comparisons = {
            "network": "NETWORK_MISMATCH",
            "chain_id": "CHAIN_ID_MISMATCH",
            "transaction_type": "TRANSACTION_TYPE_MISMATCH",
            "source": "SOURCE_MISMATCH",
            "destination": "DESTINATION_MISMATCH",
            "destination_tag": "DESTINATION_TAG_MISMATCH",
            "asset": "ASSET_MISMATCH",
            "issuer": "ISSUER_MISMATCH",
            "amount": "AMOUNT_MISMATCH",
        }
        for key, code in comparisons.items():
            if str(tx.get(key)) != str(intent.get(key)):
                reject("alignment", code, f"transaction {key} contradicts declared intent")
        expected_effect = intent.get("expected_effect_hash")
        calculated_effect = digest(
            {
                "network": tx.get("network"),
                "source": tx.get("source"),
                "destination": tx.get("destination"),
                "destination_tag": tx.get("destination_tag"),
                "asset": tx.get("asset"),
                "issuer": tx.get("issuer"),
                "amount": tx.get("amount"),
            }
        )
        if not expected_effect:
            hold("alignment", "EXPECTED_EFFECT_MISSING", "intent does not bind its expected consequence")
        elif expected_effect != calculated_effect:
            reject("alignment", "EXPECTED_EFFECT_MISMATCH", "proposed consequence differs from declared consequence")

        # 4. GENESIS: origin, authority, evidence and policy must be attributable.
        actor = intent.get("actor_id")
        signer = evidence.get("signer_id")
        approver = intent.get("approver_id")
        if actor not in set(policy.get("authorized_actors", [])):
            reject("genesis", "ACTOR_UNAUTHORIZED", "request actor is outside policy authority")
        if signer not in set(policy.get("authorized_signers", [])):
            reject("genesis", "SIGNER_UNAUTHORIZED", "signing identity is outside policy authority")
        if approver not in set(policy.get("authorized_approvers", [])):
            reject("genesis", "APPROVER_UNAUTHORIZED", "approval origin is outside policy authority")
        if evidence.get("source_wallet_verified") is not True:
            hold("genesis", "SOURCE_PROVENANCE_UNVERIFIED", "source wallet ownership is not proven")
        if evidence.get("evidence_signature_valid") is not True:
            hold("genesis", "EVIDENCE_SIGNATURE_INVALID", "live evidence origin cannot be verified")
        if intent.get("policy_hash") != policy.get("policy_hash"):
            reject("genesis", "POLICY_HASH_MISMATCH", "intent is governed by a different policy")
        if evidence.get("policy_engine_healthy") is not True:
            hold("genesis", "POLICY_ENGINE_FAILURE", "policy engine health is not proven")
        if evidence.get("verifier_healthy") is not True:
            hold("genesis", "VERIFIER_FAILURE", "evidence verifier health is not proven")

        # 5. BOUNDARY: value, cost, balance, network and dangerous flags.
        amount = _decimal(tx.get("amount"))
        fee = _decimal(tx.get("fee_drops"))
        max_amount = _decimal(policy.get("max_amount"))
        max_fee = _decimal(policy.get("max_fee_drops"))
        balance = _decimal(evidence.get("balance_drops"))
        reserve = _decimal(evidence.get("reserve_drops"))
        if amount is None:
            hold("boundary", "AMOUNT_INVALID", "amount is not a valid decimal")
        else:
            if amount <= 0:
                reject("boundary", "AMOUNT_NONPOSITIVE", "amount must be positive")
            if max_amount is None:
                hold("boundary", "AMOUNT_LIMIT_MISSING", "maximum authorized amount is unknown")
            elif amount > max_amount:
                reject("boundary", "AMOUNT_LIMIT_EXCEEDED", "amount exceeds the authorized boundary")
            precision = max(0, -amount.as_tuple().exponent)
            if precision > int(policy.get("asset_precision", 6)):
                reject("boundary", "AMOUNT_PRECISION_EXCEEDED", "amount exceeds asset precision")
        if fee is None or max_fee is None:
            hold("boundary", "FEE_EVIDENCE_MISSING", "fee boundary cannot be evaluated")
        elif fee > max_fee:
            reject("boundary", "FEE_LIMIT_EXCEEDED", "network fee exceeds the authorized boundary")
        if None in (amount, fee, balance, reserve):
            hold("boundary", "BALANCE_EVIDENCE_MISSING", "available spend cannot be proven")
        elif balance - reserve < amount + fee:
            reject("boundary", "INSUFFICIENT_SPENDABLE_BALANCE", "amount plus fee would violate balance or reserve")
        if tx.get("network") not in set(policy.get("allowed_networks", [])):
            reject("boundary", "NETWORK_NOT_ALLOWED", "network is outside the execution boundary")
        if tx.get("transaction_type") not in set(policy.get("allowed_transaction_types", [])):
            reject("boundary", "TRANSACTION_TYPE_NOT_ALLOWED", "transaction type is outside the execution boundary")
        if tx.get("asset") not in set(policy.get("allowed_assets", [])):
            reject("boundary", "ASSET_NOT_ALLOWED", "asset is outside the execution boundary")
        flags = set(tx.get("flags") or [])
        if flags.intersection(set(policy.get("forbidden_flags", []))):
            reject("boundary", "DANGEROUS_FLAG", "transaction enables a forbidden execution behavior")
        slippage = _decimal(evidence.get("quoted_slippage_bps"))
        max_slippage = _decimal(policy.get("max_slippage_bps"))
        if policy.get("price_required") and None in (slippage, max_slippage):
            hold("boundary", "SLIPPAGE_EVIDENCE_MISSING", "price impact cannot be bounded")
        elif policy.get("price_required") and slippage > max_slippage:
            reject("boundary", "SLIPPAGE_LIMIT_EXCEEDED", "quoted price impact exceeds policy")

        # 6. REFERENCE: each address, account, asset and destination meaning is exact.
        if not _is_xrpl_address(tx.get("source")):
            reject("reference", "SOURCE_ADDRESS_INVALID", "source is not a valid XRPL classic address")
        if not _is_xrpl_address(tx.get("destination")):
            reject("reference", "DESTINATION_ADDRESS_INVALID", "destination is not a valid XRPL classic address")
        if evidence.get("destination_exists") is not True:
            hold("reference", "DESTINATION_NOT_VERIFIED", "destination account existence is not proven")
        if evidence.get("destination_requires_tag") and tx.get("destination_tag") is None:
            reject("reference", "DESTINATION_TAG_REQUIRED", "destination requires a tag")
        if evidence.get("destination_disallows_asset"):
            reject("reference", "DESTINATION_DISALLOWS_ASSET", "destination refuses this asset")
        if tx.get("issuer") and evidence.get("trustline_exists") is not True:
            reject("reference", "TRUSTLINE_MISSING", "token trust line is not proven")
        if tx.get("issuer") and evidence.get("issuer_frozen") is True:
            reject("reference", "ISSUER_FROZEN", "token issuer or trust line is frozen")
        if evidence.get("endpoint_network") != tx.get("network"):
            reject("reference", "ENDPOINT_NETWORK_MISMATCH", "RPC endpoint belongs to a different network")
        if evidence.get("asset_metadata_verified") is not True:
            hold("reference", "ASSET_METADATA_UNVERIFIED", "asset identity and precision are not proven")

        # 7. CAUSALITY: live preflight must support the predicted consequence.
        if evidence.get("simulation_ok") is not True:
            hold("causality", "SIMULATION_FAILED", "transaction preflight did not prove executable")
        if evidence.get("preflight_result") != "tesSUCCESS":
            hold("causality", "PREFLIGHT_NOT_SUCCESS", "network preflight did not return success")
        if evidence.get("signer_binding_hash") != digest(tx):
            reject("causality", "SIGNER_BINDING_MISMATCH", "signer is not bound to the admitted transaction")
        if evidence.get("executor_healthy") is not True:
            hold("causality", "EXECUTOR_FAILURE", "execution adapter health is not proven")
        if evidence.get("receipt_writer_healthy") is not True:
            hold("causality", "RECEIPT_WRITER_FAILURE", "durable evidence cannot be guaranteed")

        # 8. CONSCIOUSNESS / ACCOUNTABILITY: explicit, scoped authorization.
        if not intent.get("approval_id"):
            hold("consciousness", "APPROVAL_MISSING", "no approval identity is attached")
        if evidence.get("approval_valid") is not True:
            hold("consciousness", "APPROVAL_INVALID", "approval is missing, expired, or unverifiable")
        if evidence.get("approval_scope_hash") != intent.get("approval_scope_hash"):
            reject("consciousness", "APPROVAL_SCOPE_MISMATCH", "approval does not cover this exact intent")
        if not intent.get("accountability_id"):
            hold("consciousness", "ACCOUNTABILITY_MISSING", "no responsible observer is identified")
        if evidence.get("human_confirmation_required") and evidence.get("human_confirmed") is not True:
            hold("consciousness", "HUMAN_CONFIRMATION_MISSING", "required human confirmation is absent")
        if evidence.get("memo_controls_execution") is True:
            reject("consciousness", "UNTRUSTED_MEMO_CONTROL", "untrusted transaction memo attempted to control execution")

        # 9. COHERENCE: no isolated pass can override a contradiction elsewhere.
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

        evaluation = Evaluation(
            decision=decision,
            intent_hash=digest(intent),
            transaction_hash=digest(tx),
            evidence_hash=digest(evidence),
            policy_hash=digest(policy),
            gate_status=gate_status,
            findings=findings,
        )
        evaluation.root_proof = self._root_proof(state, evaluation)
        if not evaluation.root_proof.get("admitted", False):
            evaluation.findings.append(
                Finding("coherence", "ROOT_PROOF_FAILURE", Decision.HOLD, "SCQOS root proof was not admitted")
            )
            evaluation.gate_status["coherence"] = False
            if evaluation.decision == Decision.PERMIT:
                evaluation.decision = Decision.HOLD
        return evaluation

    def _root_proof(self, state: Mapping[str, Any], evaluation: Evaluation) -> dict[str, Any]:
        if self.root_adapter is None:
            return {"admitted": True, "mode": "domain-only"}
        try:
            root = self.root_adapter
            packet = root.make_packet(
                system_type="blockchain_call",
                action="evaluate_before_signing",
                actor=str(state.get("intent", {}).get("actor_id", "UNKNOWN")),
                source=str(state.get("transaction", {}).get("source", "UNKNOWN")),
                target=str(state.get("transaction", {}).get("destination", "UNKNOWN")),
                # The public Root Adapter maps blockchain calls to its frozen
                # "enforce_policy" objective. The domain purpose remains bound
                # inside the payload so we do not mutate that frozen contract.
                declared_objective="enforce_policy",
                boundary_domain="trusted_runtime",
                payload={
                    "schema": SCHEMA_VERSION,
                    "state_hash": digest(state),
                    "domain_decision": evaluation.decision.value,
                    "intent_hash": evaluation.intent_hash,
                    "transaction_hash": evaluation.transaction_hash,
                    "evidence_hash": evaluation.evidence_hash,
                    "finding_codes": [item.code for item in evaluation.findings],
                },
                external_reference=str(state.get("intent", {}).get("intent_id", "")),
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


def expected_effect_hash(transaction: Mapping[str, Any]) -> str:
    return digest(
        {
            "network": transaction.get("network"),
            "source": transaction.get("source"),
            "destination": transaction.get("destination"),
            "destination_tag": transaction.get("destination_tag"),
            "asset": transaction.get("asset"),
            "issuer": transaction.get("issuer"),
            "amount": transaction.get("amount"),
        }
    )


def baseline_state(now: Optional[float] = None) -> dict[str, Any]:
    now = float(now if now is not None else time.time())
    tx = {
        "network": "xrpl_testnet",
        "chain_id": "xrpl:testnet",
        "transaction_type": "Payment",
        "source": "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
        "destination": "rUCzEr6jrEyMpjhs4wSdQdz4g8Y382NxfM",
        "destination_tag": None,
        "asset": "XRP",
        "issuer": None,
        "amount": "1",
        "fee_drops": "12",
        "sequence": 100,
        "last_ledger_sequence": 1010,
        "flags": [],
        "memo": None,
    }
    policy_core = {
        "version": "1.0.0",
        "allowed_networks": ["xrpl_testnet"],
        "allowed_transaction_types": ["Payment"],
        "allowed_assets": ["XRP"],
        "authorized_actors": ["scqos_test_actor"],
        "authorized_signers": ["scqos_test_signer"],
        "authorized_approvers": ["scqos_test_approver"],
        "max_amount": "10",
        "max_fee_drops": "100",
        "asset_precision": 6,
        "max_ledger_age_seconds": "30",
        "max_oracle_age_seconds": "30",
        "max_slippage_bps": "50",
        "price_required": False,
        "forbidden_flags": ["tfPartialPayment"],
    }
    policy_core["policy_hash"] = digest(policy_core)
    approval_scope_hash = digest(
        {
            "actor_id": "scqos_test_actor",
            "network": tx["network"],
            "source": tx["source"],
            "destination": tx["destination"],
            "asset": tx["asset"],
            "amount": tx["amount"],
        }
    )
    state = {
        "schema": SCHEMA_VERSION,
        "intent": {
            "intent_id": "intent-baseline-001",
            "actor_id": "scqos_test_actor",
            "approver_id": "scqos_test_approver",
            "approval_id": "approval-baseline-001",
            "approval_scope_hash": approval_scope_hash,
            "accountability_id": "scqos_test_observer",
            "policy_hash": policy_core["policy_hash"],
            "previous_receipt_hash": "receipt-genesis",
            "created_at": now - 1,
            "expires_at": now + 120,
            **{key: tx.get(key) for key in SEMANTIC_FIELDS if key not in {"flags", "memo"}},
            "expected_effect_hash": expected_effect_hash(tx),
        },
        "transaction": tx,
        "evidence": {
            "now": now,
            "ledger_validated": True,
            "ledger_closed_at": now - 2,
            "ledger_index": 1000,
            "endpoint_network": "xrpl_testnet",
            "account_sequence": 100,
            "balance_drops": "100000000",
            "reserve_drops": "10000000",
            "destination_exists": True,
            "destination_requires_tag": False,
            "destination_disallows_asset": False,
            "asset_metadata_verified": True,
            "trustline_exists": True,
            "issuer_frozen": False,
            "source_wallet_verified": True,
            "signer_id": "scqos_test_signer",
            "evidence_signature_valid": True,
            "policy_engine_healthy": True,
            "verifier_healthy": True,
            "executor_healthy": True,
            "receipt_writer_healthy": True,
            "simulation_ok": True,
            "preflight_result": "tesSUCCESS",
            "quoted_slippage_bps": "0",
            "approval_valid": True,
            "approval_scope_hash": approval_scope_hash,
            "human_confirmation_required": True,
            "human_confirmed": True,
            "memo_controls_execution": False,
            "previous_receipt_required": True,
            "previous_receipt_hash": "receipt-genesis",
            "consumed_intent_ids": [],
            "submitted_transaction_hashes": [],
            "transaction_hash": "not-submitted",
        },
        "policy": policy_core,
    }
    state["evidence"]["pre_autofill_semantic_hash"] = digest(semantic_transaction(tx))
    state["evidence"]["signer_binding_hash"] = digest(tx)
    return state


def _fault(path: str, value: Any) -> Callable[[MutableMapping[str, Any]], None]:
    return lambda state: _set_path(state, path, value)


def fault_universe(now: Optional[float] = None) -> list[FaultCase]:
    """Closed, named mutation universe for the v1 payment proof claim."""
    now = float(now if now is not None else time.time())
    cases = [
        FaultCase("missing decision time", Decision.HOLD, "TIME_MISSING", _fault("evidence.now", None)),
        FaultCase("future-dated intent", Decision.REJECT, "CREATED_IN_FUTURE", _fault("intent.created_at", now + 60)),
        FaultCase("expired intent", Decision.REJECT, "INTENT_EXPIRED", _fault("intent.expires_at", now - 60)),
        FaultCase("unvalidated ledger", Decision.HOLD, "LEDGER_NOT_VALIDATED", _fault("evidence.ledger_validated", False)),
        FaultCase("stale ledger", Decision.HOLD, "LEDGER_STALE", _fault("evidence.ledger_closed_at", now - 300)),
        FaultCase("stale oracle", Decision.HOLD, "ORACLE_STALE", lambda s: (s["policy"].update({"price_required": True}), s["evidence"].update({"oracle_observed_at": now - 300}))),
        FaultCase("missing intent identity", Decision.HOLD, "INTENT_ID_MISSING", _fault("intent.intent_id", "")),
        FaultCase("replayed intent", Decision.REJECT, "INTENT_REPLAY", _fault("evidence.consumed_intent_ids", ["intent-baseline-001"])),
        FaultCase("stale or future sequence", Decision.REJECT, "SEQUENCE_MISMATCH", _fault("transaction.sequence", 99)),
        FaultCase("broken prior receipt", Decision.REJECT, "RECEIPT_CHAIN_BROKEN", _fault("evidence.previous_receipt_hash", "wrong")),
        FaultCase("semantic autofill mutation", Decision.REJECT, "AUTOFILL_SEMANTIC_MUTATION", _fault("transaction.memo", "mutated")),
        FaultCase("post-admission mutation", Decision.REJECT, "POST_ADMISSION_MUTATION", _fault("evidence.admitted_transaction_hash", "wrong")),
        FaultCase("duplicate submission", Decision.REJECT, "DUPLICATE_SUBMISSION", lambda s: s["evidence"].update({"transaction_hash": "seen", "submitted_transaction_hashes": ["seen"]})),
        FaultCase("wrong network", Decision.REJECT, "NETWORK_MISMATCH", _fault("transaction.network", "xrpl_mainnet")),
        FaultCase("wrong chain identity", Decision.REJECT, "CHAIN_ID_MISMATCH", _fault("transaction.chain_id", "ethereum:1")),
        FaultCase("wrong transaction type", Decision.REJECT, "TRANSACTION_TYPE_MISMATCH", _fault("transaction.transaction_type", "AccountDelete")),
        FaultCase("wrong source wallet", Decision.REJECT, "SOURCE_MISMATCH", _fault("transaction.source", "rMCcNuTcajgw7YTgBy1sys3b89QqjUrMpH")),
        FaultCase("valid but wrong destination", Decision.REJECT, "DESTINATION_MISMATCH", _fault("transaction.destination", "rMCcNuTcajgw7YTgBy1sys3b89QqjUrMpH")),
        FaultCase("wrong destination tag", Decision.REJECT, "DESTINATION_TAG_MISMATCH", _fault("transaction.destination_tag", 999)),
        FaultCase("wrong asset", Decision.REJECT, "ASSET_MISMATCH", _fault("transaction.asset", "USD")),
        FaultCase("wrong issuer", Decision.REJECT, "ISSUER_MISMATCH", _fault("transaction.issuer", "rMCcNuTcajgw7YTgBy1sys3b89QqjUrMpH")),
        FaultCase("wrong amount", Decision.REJECT, "AMOUNT_MISMATCH", _fault("transaction.amount", "2")),
        FaultCase("missing expected consequence", Decision.HOLD, "EXPECTED_EFFECT_MISSING", _fault("intent.expected_effect_hash", "")),
        FaultCase("wrong expected consequence", Decision.REJECT, "EXPECTED_EFFECT_MISMATCH", _fault("intent.expected_effect_hash", "wrong")),
        FaultCase("unauthorized actor", Decision.REJECT, "ACTOR_UNAUTHORIZED", _fault("intent.actor_id", "attacker")),
        FaultCase("unauthorized signer", Decision.REJECT, "SIGNER_UNAUTHORIZED", _fault("evidence.signer_id", "attacker-key")),
        FaultCase("unauthorized approver", Decision.REJECT, "APPROVER_UNAUTHORIZED", _fault("intent.approver_id", "attacker")),
        FaultCase("unverified source wallet", Decision.HOLD, "SOURCE_PROVENANCE_UNVERIFIED", _fault("evidence.source_wallet_verified", False)),
        FaultCase("unverifiable evidence", Decision.HOLD, "EVIDENCE_SIGNATURE_INVALID", _fault("evidence.evidence_signature_valid", False)),
        FaultCase("wrong policy version", Decision.REJECT, "POLICY_HASH_MISMATCH", _fault("intent.policy_hash", "old-policy")),
        FaultCase("policy engine failure", Decision.HOLD, "POLICY_ENGINE_FAILURE", _fault("evidence.policy_engine_healthy", False)),
        FaultCase("verifier failure", Decision.HOLD, "VERIFIER_FAILURE", _fault("evidence.verifier_healthy", False)),
        FaultCase("zero amount", Decision.REJECT, "AMOUNT_NONPOSITIVE", lambda s: (s["transaction"].update({"amount": "0"}), s["intent"].update({"amount": "0", "expected_effect_hash": expected_effect_hash({**s["transaction"], "amount": "0"})}), s["evidence"].update({"pre_autofill_semantic_hash": digest(semantic_transaction({**s["transaction"], "amount": "0"})), "signer_binding_hash": digest({**s["transaction"], "amount": "0"})}))),
        FaultCase("amount above policy", Decision.REJECT, "AMOUNT_LIMIT_EXCEEDED", _fault("policy.max_amount", "0.5")),
        FaultCase("excess precision", Decision.REJECT, "AMOUNT_PRECISION_EXCEEDED", lambda s: (s["transaction"].update({"amount": "1.0000001"}), s["intent"].update({"amount": "1.0000001"}))),
        FaultCase("excess fee", Decision.REJECT, "FEE_LIMIT_EXCEEDED", _fault("transaction.fee_drops", "1000")),
        FaultCase("insufficient spendable balance", Decision.REJECT, "INSUFFICIENT_SPENDABLE_BALANCE", _fault("evidence.balance_drops", "10")),
        FaultCase("network outside boundary", Decision.REJECT, "NETWORK_NOT_ALLOWED", _fault("policy.allowed_networks", [])),
        FaultCase("transaction type outside boundary", Decision.REJECT, "TRANSACTION_TYPE_NOT_ALLOWED", _fault("policy.allowed_transaction_types", [])),
        FaultCase("asset outside boundary", Decision.REJECT, "ASSET_NOT_ALLOWED", _fault("policy.allowed_assets", [])),
        FaultCase("partial-payment flag", Decision.REJECT, "DANGEROUS_FLAG", _fault("transaction.flags", ["tfPartialPayment"])),
        FaultCase("excess slippage", Decision.REJECT, "SLIPPAGE_LIMIT_EXCEEDED", lambda s: (s["policy"].update({"price_required": True}), s["evidence"].update({"oracle_observed_at": now, "quoted_slippage_bps": "500"}))),
        FaultCase("invalid source address", Decision.REJECT, "SOURCE_ADDRESS_INVALID", _fault("transaction.source", "not-an-address")),
        FaultCase("invalid destination address", Decision.REJECT, "DESTINATION_ADDRESS_INVALID", _fault("transaction.destination", "not-an-address")),
        FaultCase("destination not verified", Decision.HOLD, "DESTINATION_NOT_VERIFIED", _fault("evidence.destination_exists", False)),
        FaultCase("required destination tag absent", Decision.REJECT, "DESTINATION_TAG_REQUIRED", _fault("evidence.destination_requires_tag", True)),
        FaultCase("destination rejects asset", Decision.REJECT, "DESTINATION_DISALLOWS_ASSET", _fault("evidence.destination_disallows_asset", True)),
        FaultCase("token trustline absent", Decision.REJECT, "TRUSTLINE_MISSING", lambda s: (s["transaction"].update({"issuer": s["transaction"]["destination"]}), s["intent"].update({"issuer": s["transaction"]["destination"]}), s["evidence"].update({"trustline_exists": False}))),
        FaultCase("token issuer frozen", Decision.REJECT, "ISSUER_FROZEN", lambda s: (s["transaction"].update({"issuer": s["transaction"]["destination"]}), s["intent"].update({"issuer": s["transaction"]["destination"]}), s["evidence"].update({"issuer_frozen": True}))),
        FaultCase("wrong RPC network", Decision.REJECT, "ENDPOINT_NETWORK_MISMATCH", _fault("evidence.endpoint_network", "xrpl_mainnet")),
        FaultCase("asset metadata absent", Decision.HOLD, "ASSET_METADATA_UNVERIFIED", _fault("evidence.asset_metadata_verified", False)),
        FaultCase("simulation failure", Decision.HOLD, "SIMULATION_FAILED", _fault("evidence.simulation_ok", False)),
        FaultCase("preflight failure", Decision.HOLD, "PREFLIGHT_NOT_SUCCESS", _fault("evidence.preflight_result", "tecUNFUNDED_PAYMENT")),
        FaultCase("signer bound to different bytes", Decision.REJECT, "SIGNER_BINDING_MISMATCH", _fault("evidence.signer_binding_hash", "wrong")),
        FaultCase("executor failure", Decision.HOLD, "EXECUTOR_FAILURE", _fault("evidence.executor_healthy", False)),
        FaultCase("receipt writer failure", Decision.HOLD, "RECEIPT_WRITER_FAILURE", _fault("evidence.receipt_writer_healthy", False)),
        FaultCase("approval absent", Decision.HOLD, "APPROVAL_MISSING", _fault("intent.approval_id", "")),
        FaultCase("approval invalid or expired", Decision.HOLD, "APPROVAL_INVALID", _fault("evidence.approval_valid", False)),
        FaultCase("approval scope mismatch", Decision.REJECT, "APPROVAL_SCOPE_MISMATCH", _fault("evidence.approval_scope_hash", "wrong")),
        FaultCase("accountability absent", Decision.HOLD, "ACCOUNTABILITY_MISSING", _fault("intent.accountability_id", "")),
        FaultCase("required human confirmation absent", Decision.HOLD, "HUMAN_CONFIRMATION_MISSING", _fault("evidence.human_confirmed", False)),
        FaultCase("memo prompt injection", Decision.REJECT, "UNTRUSTED_MEMO_CONTROL", _fault("evidence.memo_controls_execution", True)),
    ]
    return cases


def sign_receipt(payload: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    public = copy.deepcopy(dict(payload))
    body = canonical_bytes(public)
    return {
        **public,
        "receipt_hash": hashlib.sha3_512(body).hexdigest(),
        "receipt_hmac_sha256": hmac.new(key, body, hashlib.sha256).hexdigest(),
    }


def load_or_create_receipt_key(path: Path) -> bytes:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(secrets.token_hex(32))
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PermissionError(f"receipt key permissions must be 600, found {mode:o}")
    return bytes.fromhex(path.read_text(encoding="ascii").strip())


def load_root_adapter(repo_root: Path) -> Any:
    os.environ.setdefault("SCQOS_KERNEL_MODULE", "scqos_supreme_stack")
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "Root Adapter.py"
    spec = importlib.util.spec_from_file_location("scqos_root_adapter", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SCQOSRootAdmissionAdapter()


def run_matrix(governor: SCQOSCryptoGovernor, evidence_dir: Path, receipt_key: bytes) -> dict[str, Any]:
    now = time.time()
    baseline = baseline_state(now)
    baseline_result = governor.evaluate(baseline)
    results: list[dict[str, Any]] = []
    if baseline_result.decision != Decision.PERMIT:
        raise AssertionError(f"baseline did not PERMIT: {baseline_result.public()}")
    for case in fault_universe(now):
        state = copy.deepcopy(baseline)
        case.mutate(state)
        result = governor.evaluate(state)
        codes = {item.code for item in result.findings}
        passed = result.decision == case.expected and case.expected_code in codes
        results.append(
            {
                "case": case.name,
                "expected": case.expected.value,
                "observed": result.decision.value,
                "expected_code": case.expected_code,
                "finding_codes": sorted(codes),
                "passed": passed,
                "transaction_hash": result.transaction_hash,
                "root_proof": result.root_proof.get("final_proof", "domain-only"),
            }
        )
    summary = {
        "schema": SCHEMA_VERSION,
        "mode": "closed_fault_universe",
        "claim_scope": "XRPL Payment pre-signing safety v1",
        "executed_at": time.time(),
        "baseline": baseline_result.public(),
        "total_cases": len(results),
        "passed_cases": sum(1 for row in results if row["passed"]),
        "failed_cases": sum(1 for row in results if not row["passed"]),
        "all_faults_fail_closed": all(row["passed"] and row["observed"] != Decision.PERMIT.value for row in results),
        "results": results,
    }
    signed = sign_receipt(summary, receipt_key)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output = evidence_dir / f"matrix_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**summary, "receipt_path": str(output), "receipt_hash": signed["receipt_hash"]}


def verify_consequence(
    intent: Mapping[str, Any],
    admitted_transaction_hash: str,
    consequence: Mapping[str, Any],
) -> Evaluation:
    """Close the circuit after submission; provisional success is never enough."""
    findings: list[Finding] = []
    if consequence.get("validated") is not True:
        findings.append(Finding("time", "RESULT_NOT_VALIDATED", Decision.HOLD, "result is not final"))
    if consequence.get("engine_result") != "tesSUCCESS":
        findings.append(Finding("causality", "ENGINE_RESULT_FAILURE", Decision.REJECT, "ledger did not apply the intended effect"))
    if consequence.get("transaction_hash") != admitted_transaction_hash:
        findings.append(Finding("continuity", "RESULT_HASH_MISMATCH", Decision.REJECT, "observed result is not the admitted transaction"))
    for key in ("network", "source", "destination", "destination_tag", "asset", "amount"):
        if str(consequence.get(key)) != str(intent.get(key)):
            findings.append(Finding("causality", f"RESULT_{key.upper()}_MISMATCH", Decision.REJECT, f"observed {key} differs from intent"))
    if consequence.get("duplicate_effect"):
        findings.append(Finding("continuity", "DUPLICATE_EFFECT", Decision.REJECT, "the intended consequence occurred more than once"))
    decision = Decision.REJECT if any(f.decision == Decision.REJECT for f in findings) else (Decision.HOLD if findings else Decision.PERMIT)
    gate_status = {gate: True for gate in SCQOSCryptoGovernor.GATES}
    for finding in findings:
        gate_status[finding.gate] = False
    gate_status["coherence"] = not findings
    return Evaluation(
        decision=decision,
        intent_hash=digest(intent),
        transaction_hash=admitted_transaction_hash,
        evidence_hash=digest(consequence),
        policy_hash=str(intent.get("policy_hash", "")),
        gate_status=gate_status,
        findings=findings,
        root_proof={"admitted": True, "mode": "consequence-closure"},
    )


def print_matrix_summary(summary: Mapping[str, Any]) -> None:
    print(json.dumps({
        "SCQOS_CRYPTO_PROOF": "COMPLETE",
        "claim_scope": summary["claim_scope"],
        "valid_control": summary["baseline"]["decision"],
        "faults_tested": summary["total_cases"],
        "faults_blocked": summary["passed_cases"],
        "faults_missed": summary["failed_cases"],
        "all_faults_fail_closed": summary["all_faults_fail_closed"],
        "receipt_hash": summary["receipt_hash"],
        "receipt_path": summary["receipt_path"],
    }, indent=2, sort_keys=True))


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SCQOS cryptocurrency Holy Grail proof harness")
    parser.add_argument("--matrix", action="store_true", help="run the complete deterministic fault universe")
    parser.add_argument("--domain-only", action="store_true", help="skip the existing Root Adapter integration")
    parser.add_argument("--evidence-dir", default="evidence/crypto_holy_grail")
    parser.add_argument("--receipt-key", default="~/.config/scqos/crypto_proof_hmac.key")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.matrix:
        parser.error("select --matrix (live testnet runner is added after this matrix closes cleanly)")
    repo_root = Path(__file__).resolve().parents[1]
    key = load_or_create_receipt_key(Path(args.receipt_key))
    # Bind the existing Root Adapter to the same durable local proof authority.
    # setdefault preserves an explicitly supplied production/KMS value.
    os.environ.setdefault("SCQOS_SECRET_KEY", key.hex())
    root = None if args.domain_only else load_root_adapter(repo_root)
    governor = SCQOSCryptoGovernor(root)
    summary = run_matrix(governor, repo_root / args.evidence_dir, key)
    print_matrix_summary(summary)
    return 0 if summary["all_faults_fail_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
