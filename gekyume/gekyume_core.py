#!/usr/bin/env python3

import json
import time
import uuid
import hashlib
import sys
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scqos_supreme_stack as sc


ROOT = Path(__file__).resolve().parent

import os
RECEIPTS = Path(
    os.environ.get(
        "GEKYUME_RECEIPTS_DIR",
        str(ROOT / "receipts")
    )
)
RECEIPTS.mkdir(parents=True, exist_ok=True)


def canonical(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode()


def sha256(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


class Gekyume:
    """
    GEKYUME
    Provable Financial Execution Infrastructure
    """

    def __init__(self):
        self.secret_key = sc.get_secret_key()

        self.scqos = sc.SCQOSSupremeCoherenceStack(
            secret_key=self.secret_key,
            node_id="gekyume-financial-execution-node",
            session_id="gekyume-session",
            continuity_id="gekyume-continuity",
            alignment_id="gekyume-alignment",
            genesis_id="gekyume-genesis",
            boundary_id="gekyume-boundary",
            reference_id="gekyume-reference",
            causality_id="gekyume-causality",
            consciousness_id="gekyume-consciousness",
            coherence_id="gekyume-coherence",
            creator_id="gekyume",
            observer_id="gekyume-observer",
            substrate_id="aws-scqos-financial-substrate",
        )

        boot = self.scqos.boot_all_modules()

        if boot is False:
            raise RuntimeError("SCQOS refused to boot")

        self.ledger = {
            "TREASURY_A": 10_000_000_000,
            "BANK_B": 0,
            "BANK_C": 0,
        }

        self.executed_transition_ids = set()

    def invariant_check(self, tx):
        now = time.time()

        checks = {
            "TIME":
                tx["expires_at"] > now,

            "CONTINUITY":
                tx["prior_state_hash"] == sha256(self.ledger),

            "ALIGNMENT":
                tx["purpose"] == "AUTHORIZED_INSTITUTIONAL_TRANSFER",

            "GENESIS":
                tx["origin"] == "GEKYUME_AUTHORIZED_BANK",

            "BOUNDARY":
                0 < tx["amount"] <= 2_000_000_000,

            "REFERENCE":
                tx["source"] in self.ledger
                and tx["destination"] in self.ledger
                and tx["source"] != tx["destination"],

            "CAUSALITY":
                self.ledger.get(tx["source"], 0) >= tx["amount"],

            "CONSCIOUSNESS":
                bool(tx["authorized_by"])
                and tx["authority_status"] == "ACTIVE",
        }

        return checks

    def qualify(self, tx):
        checks = self.invariant_check(tx)

        duplicate = tx["transition_id"] in self.executed_transition_ids

        if duplicate:
            return "REJECT", checks, "REPLAY_DETECTED"

        failed = [name for name, value in checks.items() if not value]

        if failed:
            return "HOLD", checks, "INVARIANT_FAILURE:" + ",".join(failed)

        return "PERMIT", checks, "ALL_INVARIANTS_PROVED"

    def execute(self, tx):
        before = deepcopy(self.ledger)
        before_hash = sha256(before)

        decision, checks, reason = self.qualify(tx)

        consequence = {
            "executed": False,
            "before_hash": before_hash,
            "after_hash": before_hash,
        }

        if decision == "PERMIT":
            self.ledger[tx["source"]] -= tx["amount"]
            self.ledger[tx["destination"]] += tx["amount"]

            self.executed_transition_ids.add(tx["transition_id"])

            consequence = {
                "executed": True,
                "source": tx["source"],
                "destination": tx["destination"],
                "amount": tx["amount"],
                "before_hash": before_hash,
                "after_hash": sha256(self.ledger),
            }

        receipt = {
            "system": "GEKYUME",
            "version": "0.1.0",
            "timestamp": time.time(),
            "transaction": tx,
            "transaction_hash": sha256(tx),
            "invariants": checks,
            "decision": decision,
            "reason": reason,
            "consequence": consequence,
            "ledger_after": deepcopy(self.ledger),
        }

        receipt["receipt_hash"] = sha256(receipt)

        path = RECEIPTS / f'{tx["transition_id"]}.json'
        path.write_text(json.dumps(receipt, indent=2))

        return receipt


def new_transaction(g, amount=1_000_000_000):
    return {
        "transition_id": str(uuid.uuid4()),
        "source": "TREASURY_A",
        "destination": "BANK_B",
        "amount": amount,
        "currency": "USD",
        "purpose": "AUTHORIZED_INSTITUTIONAL_TRANSFER",
        "origin": "GEKYUME_AUTHORIZED_BANK",
        "authorized_by": "TREASURY_AUTHORITY_001",
        "authority_status": "ACTIVE",
        "created_at": time.time(),
        "expires_at": time.time() + 300,
        "prior_state_hash": sha256(g.ledger),
    }


if __name__ == "__main__":

    print()
    print("=" * 72)
    print(" GEKYUME FINANCIAL EXECUTION ACCEPTANCE — PHASE 1")
    print("=" * 72)

    g = Gekyume()

    results = []

    # ------------------------------------------------------
    # TEST 1 — legitimate $1B transaction
    # ------------------------------------------------------
    tx = new_transaction(g)
    r = g.execute(tx)

    results.append((
        "VALID $1B TRANSFER",
        r["decision"] == "PERMIT"
        and r["consequence"]["executed"]
    ))

    print("\n[01] VALID $1B TRANSFER")
    print("Decision:", r["decision"])
    print("Executed:", r["consequence"]["executed"])

    # ------------------------------------------------------
    # TEST 2 — beneficiary mutation
    # ------------------------------------------------------
    tx = new_transaction(g)
    tx["destination"] = "UNKNOWN_BANK"

    r = g.execute(tx)

    results.append((
        "BENEFICIARY MUTATION",
        r["decision"] != "PERMIT"
        and not r["consequence"]["executed"]
    ))

    print("\n[02] BENEFICIARY MUTATION")
    print("Decision:", r["decision"])
    print("Executed:", r["consequence"]["executed"])

    # ------------------------------------------------------
    # TEST 3 — expired authority
    # ------------------------------------------------------
    tx = new_transaction(g)
    tx["authority_status"] = "EXPIRED"

    r = g.execute(tx)

    results.append((
        "EXPIRED AUTHORITY",
        r["decision"] != "PERMIT"
        and not r["consequence"]["executed"]
    ))

    print("\n[03] EXPIRED AUTHORITY")
    print("Decision:", r["decision"])
    print("Executed:", r["consequence"]["executed"])

    # ------------------------------------------------------
    # TEST 4 — stale state / continuity attack
    # ------------------------------------------------------
    tx = new_transaction(g)
    tx["prior_state_hash"] = "0" * 64

    r = g.execute(tx)

    results.append((
        "STALE STATE ATTACK",
        r["decision"] != "PERMIT"
        and not r["consequence"]["executed"]
    ))

    print("\n[04] STALE STATE ATTACK")
    print("Decision:", r["decision"])
    print("Executed:", r["consequence"]["executed"])

    # ------------------------------------------------------
    # TEST 5 — replay attack
    # ------------------------------------------------------
    tx = new_transaction(g, amount=100_000_000)

    first = g.execute(tx)
    second = g.execute(tx)

    results.append((
        "REPLAY ATTACK",
        first["decision"] == "PERMIT"
        and second["decision"] == "REJECT"
        and not second["consequence"]["executed"]
    ))

    print("\n[05] REPLAY ATTACK")
    print("First:", first["decision"])
    print("Replay:", second["decision"])

    # ------------------------------------------------------
    # RESULT
    # ------------------------------------------------------

    print()
    print("=" * 72)

    failures = 0

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status:4}  {name}")
        if not passed:
            failures += 1

    print("=" * 72)
    print("TREASURY_A:", f'${g.ledger["TREASURY_A"]:,}')
    print("BANK_B:    ", f'${g.ledger["BANK_B"]:,}')
    print("BANK_C:    ", f'${g.ledger["BANK_C"]:,}')
    print("RECEIPTS:   ", RECEIPTS.resolve())

    if failures:
        print("\nGEKYUME PHASE 1 RESULT: FAIL")
        raise SystemExit(1)

    print("\nGEKYUME PHASE 1 RESULT: PASS")
    print("Unauthorized financial executions: 0")
    print("Replay executions: 0")
    print("=" * 72)
