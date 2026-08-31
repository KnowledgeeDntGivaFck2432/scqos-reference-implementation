import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shadow_clone.protocol import (
    RESULT_INVARIANTS,
    evaluate_clone_birth,
    evaluate_result_invariants,
    make_clone_birth,
    role_ids_from_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "supreme_mind/v1/supreme_mind_manifest.json").read_text())
ROLE_IDS = role_ids_from_manifest(MANIFEST)
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class ShadowCloneProtocolTests(unittest.TestCase):
    def proposal(self, **overrides):
        values = dict(
            role_id="R15",
            task_id="sports-live-market-001",
            business_id="supreme-sports",
            objective="Inspect current public sports market evidence.",
            expected_output="A sourced market-state report.",
            evidence_refs=["https://example.com/source"],
            now=NOW,
        )
        values.update(overrides)
        return make_clone_birth(**values)

    def test_all_eight_invariants_and_coherence_permit(self):
        result = evaluate_clone_birth(self.proposal(), valid_role_ids=ROLE_IDS, now=NOW)
        self.assertEqual(result["state"], "PERMIT")
        for name in (*(
            "time", "continuity", "alignment", "genesis", "boundary",
            "reference", "causality", "consciousness",
        ), "coherence"):
            self.assertTrue(result["invariant_proofs"][name]["passed"], name)

    def test_unknown_role_rejects(self):
        proposal = self.proposal(role_id="R99")
        result = evaluate_clone_birth(proposal, valid_role_ids=ROLE_IDS, now=NOW)
        self.assertEqual(result["state"], "REJECT")
        self.assertFalse(result["invariant_proofs"]["boundary"]["passed"])

    def test_stale_birth_holds(self):
        proposal = self.proposal(now=NOW - timedelta(hours=2), ttl_seconds=60)
        result = evaluate_clone_birth(proposal, valid_role_ids=ROLE_IDS, now=NOW)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["invariant_proofs"]["time"]["passed"])

    def test_mutating_child_action_holds(self):
        proposal = self.proposal(requested_action="publish")
        result = evaluate_clone_birth(proposal, valid_role_ids=ROLE_IDS, now=NOW)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["invariant_proofs"]["boundary"]["passed"])

    def test_tampered_birth_identity_holds(self):
        proposal = self.proposal()
        proposal["objective"] = "Silently replaced objective"
        result = evaluate_clone_birth(proposal, valid_role_ids=ROLE_IDS, now=NOW)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["invariant_proofs"]["coherence"]["passed"])

    def test_child_lineage_must_match_parent(self):
        parent = self.proposal()
        child = self.proposal(
            parent_clone_id=parent["clone_id"],
            parent_role_id=parent["role_id"],
            parent_depth=parent["depth"],
            task_id="child-001",
        )
        permit = evaluate_clone_birth(child, valid_role_ids=ROLE_IDS, parent=parent, now=NOW)
        self.assertEqual(permit["state"], "PERMIT")
        child["parent_clone_id"] = "sc:clone:sha256:wrong"
        broken = evaluate_clone_birth(child, valid_role_ids=ROLE_IDS, parent=parent, now=NOW)
        self.assertEqual(broken["state"], "HOLD")

    def test_result_requires_every_invariant_and_coherence(self):
        assessment = {name: "PASS: directly evidenced" for name in RESULT_INVARIANTS}
        result = evaluate_result_invariants(assessment)
        self.assertEqual(result["state"], "PERMIT")

        assessment["causality"] = "HOLD: consequence was not observed"
        held = evaluate_result_invariants(assessment)
        self.assertEqual(held["state"], "HOLD")
        self.assertFalse(held["invariant_proofs"]["causality"]["passed"])

    def test_result_cannot_omit_an_invariant(self):
        assessment = {name: "PASS" for name in RESULT_INVARIANTS if name != "genesis"}
        result = evaluate_result_invariants(assessment)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["invariant_proofs"]["genesis"]["passed"])

    def test_result_identity_and_live_evidence_are_deterministically_bound(self):
        assessment = {name: "PASS" for name in RESULT_INVARIANTS}
        identity = {
            "clone_id": "clone-1",
            "parent_clone_id": "root",
            "role_id": "R15",
            "task_id": "task-1",
            "principal_id": "SOVEREIGN_HUMAN",
        }
        observed = {
            "identity": dict(identity),
            "summary": "Official page observed.",
            "consequence": "One current fact was established.",
            "evidence": [{
                "url": "https://www.mlb.com/schedule",
                "observed_at": NOW.isoformat(),
                "claim": "The official schedule page responded.",
            }],
        }
        permit = evaluate_result_invariants(
            assessment,
            result=observed,
            expected_identity=identity,
            now=NOW,
        )
        self.assertEqual(permit["state"], "PERMIT")

        observed["identity"]["clone_id"] = "different-clone"
        held = evaluate_result_invariants(
            assessment,
            result=observed,
            expected_identity=identity,
            now=NOW,
        )
        self.assertEqual(held["state"], "HOLD")
        self.assertFalse(held["invariant_proofs"]["continuity"]["passed"])


if __name__ == "__main__":
    unittest.main()
