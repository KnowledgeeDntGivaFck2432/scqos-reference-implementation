"""Build the exact governed task sent from the sports UI to Supreme Mind."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .contract import CONTRACT_ID


MLB_MARKET_URL = "https://sportsbook.draftkings.com/leagues/baseball/mlb"


def validate_date(value: str, *, today: date | None = None) -> str:
    try:
        selected = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("DATE_MUST_BE_YYYY_MM_DD") from None
    anchor = today or datetime.now(timezone.utc).date()
    if selected < anchor - timedelta(days=1) or selected > anchor + timedelta(days=7):
        raise ValueError("DATE_OUTSIDE_LIVE_ANALYSIS_WINDOW")
    return selected.isoformat()


def build_governor_event(
    *,
    analysis_date: str,
    max_events: int = 5,
    matchup: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    selected_date = validate_date(analysis_date, today=today)
    if not isinstance(max_events, int) or not 1 <= max_events <= 5:
        raise ValueError("MAX_EVENTS_MUST_BE_BETWEEN_1_AND_5")
    matchup = str(matchup).strip()[:120]
    schedule_url = (
        "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date="
        + selected_date
        + "&hydrate=probablePitcher,team,linescore"
    )
    filter_instruction = (
        f"Analyze only the matchup matching {matchup!r}."
        if matchup
        else f"Analyze at most {max_events} upcoming games with the strongest complete evidence."
    )
    objective = f"""
Build a LIVE MLB pregame moneyline analysis for {selected_date} from direct sources only.
{filter_instruction}

Use the AgentCore browser. Observe the current DraftKings MLB moneyline page at
{MLB_MARKET_URL} and the official MLB schedule at {schedule_url}. For each event, gather
five evidence categories: schedule, market, team_form, starting_pitchers, and availability.
Every category must contain the exact event_id, direct HTTPS URL, UTC observed_at timestamp,
and a concrete claim. Never fill an inaccessible category from memory. Put every missing,
blocked, stale, contradictory, postponed, started, or unconfirmed fact in collection_holds.

For every fully researched event, produce five separately named probability estimates:
season_record, run_differential, recent_form, starting_pitchers, and offense_bullpen.
Each model must state its method, the observed numerical inputs it used, and exactly two
outcome probabilities encoded as DECIMAL STRINGS that sum to 1. Do not use JSON floats.
Do not copy DraftKings implied probability as one of the five performance estimates.

Return the normal Shadow Clone result contract and also include a top-level
"sports_analysis" object in exactly this shape:
{{
  "contract": "{CONTRACT_ID}",
  "collection_holds": [],
  "markets": [
    {{
      "event_id": "official MLB gamePk as a string",
      "league": "MLB",
      "market_type": "moneyline",
      "sportsbook": "DraftKings",
      "starts_at": "UTC ISO-8601",
      "principal_id": "SOVEREIGN_HUMAN",
      "role_id": "R15",
      "task_id": "copy clone_birth.task_id exactly",
      "analysis_only": true,
      "outcomes": [
        {{"name": "exact away team", "american_odds": "signed integer string"}},
        {{"name": "exact home team", "american_odds": "signed integer string"}}
      ],
      "evidence": [
        {{"category": "schedule|market|team_form|starting_pitchers|availability",
          "event_id": "same official gamePk", "url": "direct HTTPS source",
          "observed_at": "UTC ISO-8601", "claim": "directly observed fact"}}
      ],
      "models": [
        {{"name": "one of the five required names", "method": "transparent method",
          "inputs": {{"observed_input": "value and source meaning"}},
          "probabilities": {{"exact away team": "0.xxxx", "exact home team": "0.xxxx"}}}}
      ],
      "risk_flags": []
    }}
  ]
}}

The deterministic executor—not you—will calculate no-vig probability, ensemble probability,
edge, evidence completeness, model agreement, all eight invariant proofs, and the final
EXECUTE/HOLD/REJECT sports verdict. EXECUTE means analysis candidate only. Never place,
prepare, submit, or imply that you placed a wager. If no event satisfies the source contract,
return an empty markets list and explain the exact live obstruction in collection_holds.
""".strip()
    return {
        "principal_id": "SOVEREIGN_HUMAN",
        "business_id": "supreme-sports-analysis",
        "role_id": "R15",
        "intent": (
            "Produce a current, attributable MLB moneyline analysis whose final sports "
            "verdict is calculated deterministically under the eight-invariant framework."
        ),
        "action": "analyze",
        "tool": "shadow-clone-internet-body",
        "evidence_refs": [schedule_url, MLB_MARKET_URL, f"sc:sports:{selected_date}"],
        "arguments": {
            "objective": objective,
            "expected_output": (
                "Receipt-backed SCQOS sports analysis containing live sources, five model "
                "estimates, deterministic thresholds, eight invariant proofs, and an "
                "EXECUTE/HOLD/REJECT analysis verdict."
            ),
            "response_contract": CONTRACT_ID,
            "analysis_date": selected_date,
            "league": "MLB",
            "sportsbook": "DraftKings",
            "market_type": "moneyline",
            "max_events": max_events,
            "matchup": matchup,
            "constraints": [
                "read-only",
                "analysis-only-no-wager",
                "direct-live-sources",
                "no-guesses",
                "decimal-strings-only",
                "maximum-five-events",
            ],
        },
    }
