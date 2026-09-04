import copy
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sports_analysis.canonical import receipt_sha256
from sports_analysis.contract import (
    CONTRACT_ID,
    american_implied_probability,
    evaluate_sports_analysis,
)


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def market():
    event_id = "777777"
    observed = (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    outcomes = ["Arizona Diamondbacks", "Los Angeles Dodgers"]
    models = []
    for name, away in (
        ("season_record", "0.61"),
        ("run_differential", "0.59"),
        ("recent_form", "0.60"),
        ("starting_pitchers", "0.62"),
        ("offense_bullpen", "0.58"),
    ):
        models.append(
            {
                "name": name,
                "method": "bounded deterministic estimate",
                "inputs": {"observed_input": "direct source fact"},
                "probabilities": {outcomes[0]: away, outcomes[1]: str(Decimal(1) - Decimal(away))},
            }
        )
    return {
        "event_id": event_id,
        "league": "MLB",
        "market_type": "moneyline",
        "sportsbook": "DraftKings",
        "starts_at": (NOW + timedelta(hours=4)).isoformat().replace("+00:00", "Z"),
        "principal_id": "SOVEREIGN_HUMAN",
        "role_id": "R15",
        "task_id": "0f01a605-d858-4218-b6c2-7372d6b14dc9",
        "analysis_only": True,
        "outcomes": [
            {"name": outcomes[0], "american_odds": "+110"},
            {"name": outcomes[1], "american_odds": "-130"},
        ],
        "evidence": [
            {
                "category": category,
                "event_id": event_id,
                "url": (
                    "https://statsapi.mlb.com/api/v1/schedule"
                    if category == "schedule"
                    else "https://sportsbook.draftkings.com/leagues/baseball/mlb"
                    if category == "market"
                    else "https://www.mlb.com/evidence/" + category
                ),
                "observed_at": observed,
                "claim": category + " observed",
            }
            for category in ("schedule", "market", "team_form", "starting_pitchers", "availability")
        ],
        "models": models,
        "risk_flags": [],
    }


class SportsAnalysisContractTests(unittest.TestCase):
    def evaluate(self, item):
        return evaluate_sports_analysis(
            {"contract": CONTRACT_ID, "collection_holds": [], "markets": [item]},
            now=NOW,
        )

    def test_american_odds(self):
        self.assertEqual(str(american_implied_probability("+150")), "0.4000")
        self.assertEqual(str(american_implied_probability("-150")), "0.6000")

    def test_complete_market_executes_analysis_only(self):
        result = self.evaluate(market())
        decision = result["markets"][0]
        self.assertEqual(result["decision"], "EXECUTE")
        self.assertGreaterEqual(float(decision["edge"]), 0.07)
        self.assertEqual(decision["model_agreement"], "1.0000")
        self.assertTrue(all(value["passed"] for value in decision["invariant_proofs"].values()))
        self.assertEqual(decision["action_boundary"], "ANALYSIS_ONLY_NO_WAGER")

    def test_low_edge_holds(self):
        item = market()
        for model in item["models"]:
            model["probabilities"] = {
                "Arizona Diamondbacks": "0.52",
                "Los Angeles Dodgers": "0.48",
            }
        decision = self.evaluate(item)["markets"][0]
        self.assertEqual(decision["decision"], "HOLD")
        self.assertIn("EDGE_BELOW_7_PERCENT", decision["reasons"])

    def test_stale_market_holds_time_invariant(self):
        item = market()
        item["evidence"][1]["observed_at"] = (NOW - timedelta(minutes=11)).isoformat()
        decision = self.evaluate(item)["markets"][0]
        self.assertEqual(decision["decision"], "HOLD")
        self.assertFalse(decision["invariant_proofs"]["time"]["passed"])

    def test_json_float_is_rejected(self):
        item = market()
        item["models"][0]["probabilities"]["Arizona Diamondbacks"] = 0.61
        decision = self.evaluate(item)["markets"][0]
        self.assertEqual(decision["decision"], "REJECT")
        self.assertIn("FLOAT_FORBIDDEN", decision["reasons"][0])

    def test_live_collection_hold_is_not_a_pick(self):
        result = evaluate_sports_analysis(
            {"contract": CONTRACT_ID, "collection_holds": ["MARKET_BLOCKED"], "markets": []},
            now=NOW,
        )
        self.assertEqual(result["decision"], "HOLD")

    def test_receipt_hash_survives_integral_decimal_roundtrip(self):
        from decimal import Decimal

        original = {"count": 5, "value": "0.61"}
        stored = copy.deepcopy(original)
        stored["count"] = Decimal("5")
        self.assertEqual(receipt_sha256(original), receipt_sha256(stored))


if __name__ == "__main__":
    unittest.main()
