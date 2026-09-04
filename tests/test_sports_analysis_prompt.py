import unittest
from datetime import date

from sports_analysis.contract import CONTRACT_ID
from sports_analysis.prompt import build_governor_event, validate_date


class SportsAnalysisPromptTests(unittest.TestCase):
    def test_governor_event_is_bounded_and_contract_bound(self):
        event = build_governor_event(
            analysis_date="2026-08-31",
            max_events=3,
            matchup="Dodgers vs Diamondbacks",
            today=date(2026, 8, 31),
        )
        self.assertEqual(event["role_id"], "R15")
        self.assertEqual(event["action"], "analyze")
        self.assertEqual(event["arguments"]["response_contract"], CONTRACT_ID)
        self.assertIn("DraftKings", event["arguments"]["objective"])
        self.assertIn("DECIMAL STRINGS", event["arguments"]["objective"])
        self.assertIn("analysis-only-no-wager", event["arguments"]["constraints"])

    def test_date_window_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "DATE_OUTSIDE"):
            validate_date("2026-09-15", today=date(2026, 8, 31))


if __name__ == "__main__":
    unittest.main()
