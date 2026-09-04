"""Deterministic SCQOS sports-analysis decision contract.

The internet model gathers attributable facts and five bounded estimates.  This
module, not the model, computes implied probability, no-vig probability,
agreement, edge, evidence completeness, the eight invariant states, and the
final EXECUTE/HOLD/REJECT analysis verdict.  EXECUTE is an analysis candidate;
this package never places a wager.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping
from urllib.parse import urlparse

from .canonical import sha256


CONTRACT_ID = "SCQOS-SPORTS-ANALYSIS-V1"
ARCHITECTURE_ID = "SUPREME-MIND-59-FACULTY-UNIVERSE-V1"
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
REQUIRED_EVIDENCE = (
    "schedule",
    "market",
    "team_form",
    "starting_pitchers",
    "availability",
)
MIN_EDGE = Decimal("0.07")
MIN_EVIDENCE_COMPLETENESS = Decimal("0.85")
MIN_MODEL_AGREEMENT = Decimal("0.80")
MIN_MODELS = 5
MAX_MARKET_AGE_SECONDS = 600
MAX_FACT_AGE_SECONDS = 21600
Q = Decimal("0.0001")


class ContractError(ValueError):
    """A structural contradiction that cannot become a betting candidate."""


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, float):
        raise ContractError(f"{label}_FLOAT_FORBIDDEN")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ContractError(f"{label}_NOT_DECIMAL") from None
    if not result.is_finite():
        raise ContractError(f"{label}_NOT_FINITE")
    return result


def _probability(value: Any, label: str) -> Decimal:
    result = _decimal(value, label)
    if result <= 0 or result >= 1:
        raise ContractError(f"{label}_OUTSIDE_OPEN_UNIT_INTERVAL")
    return result


def _iso(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label}_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError(f"{label}_INVALID") from None
    if parsed.tzinfo is None:
        raise ContractError(f"{label}_TIMEZONE_MISSING")
    return parsed.astimezone(timezone.utc)


def _url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{label}_MISSING")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ContractError(f"{label}_NOT_DIRECT_HTTPS")
    return value


def american_implied_probability(odds: Any) -> Decimal:
    price = _decimal(odds, "AMERICAN_ODDS")
    if price == 0 or -100 < price < 100:
        raise ContractError("AMERICAN_ODDS_INVALID")
    if price > 0:
        probability = Decimal(100) / (price + Decimal(100))
    else:
        probability = (-price) / ((-price) + Decimal(100))
    return probability.quantize(Q, rounding=ROUND_HALF_UP)


def no_vig_probabilities(outcomes: list[Mapping[str, Any]]) -> dict[str, Decimal]:
    if len(outcomes) != 2:
        raise ContractError("MONEYLINE_REQUIRES_TWO_OUTCOMES")
    implied: dict[str, Decimal] = {}
    for outcome in outcomes:
        name = str(outcome.get("name", "")).strip()
        if not name or name in implied:
            raise ContractError("OUTCOME_NAMES_INVALID")
        implied[name] = american_implied_probability(outcome.get("american_odds"))
    total = sum(implied.values(), Decimal(0))
    if total <= 1 or total >= Decimal("1.30"):
        raise ContractError("MARKET_VIG_OUTSIDE_BOUNDARY")
    return {
        name: (probability / total).quantize(Q, rounding=ROUND_HALF_UP)
        for name, probability in implied.items()
    }


def _source_map(
    sources: Any,
    *,
    event_id: str,
    now: datetime,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    if not isinstance(sources, list):
        raise ContractError("EVIDENCE_NOT_LIST")
    valid: dict[str, Mapping[str, Any]] = {}
    stale: list[str] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        category = str(source.get("category", "")).strip()
        if category not in REQUIRED_EVIDENCE:
            continue
        if category in valid:
            raise ContractError("DUPLICATE_EVIDENCE_CATEGORY")
        direct_url = _url(source.get("url"), f"{category.upper()}_URL")
        source_host = (urlparse(direct_url).hostname or "").lower()
        if category == "schedule" and source_host != "statsapi.mlb.com":
            raise ContractError("SCHEDULE_SOURCE_NOT_OFFICIAL_MLB")
        if category == "market" and source_host != "sportsbook.draftkings.com":
            raise ContractError("MARKET_SOURCE_NOT_DRAFTKINGS")
        observed = _iso(source.get("observed_at"), f"{category.upper()}_OBSERVED_AT")
        if str(source.get("event_id", "")) != event_id:
            raise ContractError(f"{category.upper()}_EVENT_REFERENCE_MISMATCH")
        if not str(source.get("claim", "")).strip():
            raise ContractError(f"{category.upper()}_CLAIM_MISSING")
        max_age = MAX_MARKET_AGE_SECONDS if category == "market" else MAX_FACT_AGE_SECONDS
        age = (now - observed).total_seconds()
        if age < -60 or age > max_age:
            stale.append(category)
        valid[category] = source
    return valid, stale


def _model_consensus(
    models: Any,
    outcome_names: set[str],
) -> tuple[str, Decimal, Decimal, list[dict[str, Any]]]:
    if not isinstance(models, list):
        raise ContractError("MODELS_NOT_LIST")
    if len(models) < MIN_MODELS:
        raise ContractError("FEWER_THAN_FIVE_MODELS")
    normalized: list[dict[str, Any]] = []
    selections: dict[str, int] = {name: 0 for name in outcome_names}
    probabilities: dict[str, list[Decimal]] = {name: [] for name in outcome_names}
    names: set[str] = set()
    for model in models:
        if not isinstance(model, Mapping):
            raise ContractError("MODEL_NOT_OBJECT")
        name = str(model.get("name", "")).strip()
        method = str(model.get("method", "")).strip()
        if not name or name in names or not method:
            raise ContractError("MODEL_IDENTITY_OR_METHOD_INVALID")
        names.add(name)
        raw = model.get("probabilities")
        if not isinstance(raw, Mapping) or set(raw.keys()) != outcome_names:
            raise ContractError("MODEL_OUTCOME_REFERENCES_MISMATCH")
        parsed = {
            outcome: _probability(raw[outcome], f"MODEL_{name}_{outcome}")
            for outcome in outcome_names
        }
        if abs(sum(parsed.values(), Decimal(0)) - Decimal(1)) > Decimal("0.01"):
            raise ContractError("MODEL_PROBABILITIES_DO_NOT_SUM_TO_ONE")
        selected = max(sorted(parsed), key=lambda outcome: parsed[outcome])
        selections[selected] += 1
        for outcome, probability in parsed.items():
            probabilities[outcome].append(probability)
        normalized.append({
            "name": name,
            "method": method,
            "inputs": model.get("inputs", {}),
            "probabilities": {key: str(value) for key, value in parsed.items()},
            "selected": selected,
        })
    selected = max(sorted(selections), key=lambda outcome: selections[outcome])
    agreement = (Decimal(selections[selected]) / Decimal(len(normalized))).quantize(
        Q, rounding=ROUND_HALF_UP
    )
    ensemble = (
        sum(probabilities[selected], Decimal(0)) / Decimal(len(normalized))
    ).quantize(Q, rounding=ROUND_HALF_UP)
    return selected, ensemble, agreement, normalized


def _reject(event: Any, reason: str) -> dict[str, Any]:
    event_id = event.get("event_id") if isinstance(event, Mapping) else None
    return {
        "event_id": event_id,
        "decision": "REJECT",
        "reasons": [reason],
        "action_boundary": "ANALYSIS_ONLY_NO_WAGER",
    }


def evaluate_market(event: Any, *, now: datetime) -> dict[str, Any]:
    try:
        if not isinstance(event, Mapping):
            raise ContractError("EVENT_NOT_OBJECT")
        event_id = str(event.get("event_id", "")).strip()
        league = str(event.get("league", "")).upper()
        market_type = str(event.get("market_type", "")).lower()
        sportsbook = str(event.get("sportsbook", "")).strip()
        principal_id = str(event.get("principal_id", "")).strip()
        role_id = str(event.get("role_id", "")).strip()
        task_id = str(event.get("task_id", "")).strip()
        if not event_id:
            raise ContractError("EVENT_ID_MISSING")
        if league != "MLB" or market_type != "moneyline":
            raise ContractError("UNSUPPORTED_LEAGUE_OR_MARKET")
        if sportsbook != "DraftKings":
            raise ContractError("SPORTSBOOK_REFERENCE_MISMATCH")
        if not principal_id or not role_id or not task_id:
            raise ContractError("ACCOUNTABILITY_IDENTITY_MISSING")
        starts_at = _iso(event.get("starts_at"), "STARTS_AT")
        outcomes = event.get("outcomes")
        if not isinstance(outcomes, list):
            raise ContractError("OUTCOMES_NOT_LIST")
        no_vig = no_vig_probabilities(outcomes)
        outcome_names = set(no_vig)
        selected, ensemble, agreement, models = _model_consensus(
            event.get("models"), outcome_names
        )
        sources, stale_categories = _source_map(
            event.get("evidence"), event_id=event_id, now=now
        )
        completeness = (
            Decimal(len(sources)) / Decimal(len(REQUIRED_EVIDENCE))
        ).quantize(Q, rounding=ROUND_HALF_UP)
        edge = (ensemble - no_vig[selected]).quantize(Q, rounding=ROUND_HALF_UP)
        risk_flags = event.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            raise ContractError("RISK_FLAGS_NOT_LIST")

        invariant_proofs = {
            "time": {
                "passed": starts_at > now and not stale_categories,
                "evidence": {
                    "starts_at": starts_at.isoformat(),
                    "stale_categories": stale_categories,
                },
            },
            "continuity": {
                "passed": all(
                    str(source.get("event_id")) == event_id
                    for source in sources.values()
                ),
                "evidence": {"event_id": event_id, "categories": sorted(sources)},
            },
            "alignment": {
                "passed": league == "MLB" and market_type == "moneyline",
                "evidence": {"league": league, "market_type": market_type},
            },
            "genesis": {
                "passed": "schedule" in sources and "market" in sources,
                "evidence": {
                    "official_url": sources.get("schedule", {}).get("url"),
                    "market_url": sources.get("market", {}).get("url"),
                },
            },
            "boundary": {
                "passed": event.get("analysis_only") is True,
                "evidence": "ANALYSIS_ONLY_NO_WAGER",
            },
            "reference": {
                "passed": len(outcome_names) == 2 and all(outcome_names),
                "evidence": sorted(outcome_names),
            },
            "causality": {
                "passed": len(models) >= MIN_MODELS and all(model["inputs"] for model in models),
                "evidence": [model["name"] for model in models],
            },
            "consciousness": {
                "passed": principal_id == "SOVEREIGN_HUMAN" and role_id == "R15",
                "evidence": {
                    "principal_id": principal_id,
                    "role_id": role_id,
                    "task_id": task_id,
                },
            },
        }
        invariants_pass = all(proof["passed"] for proof in invariant_proofs.values())
        reasons: list[str] = []
        if not invariants_pass:
            reasons.extend(
                f"INVARIANT_{name.upper()}_NOT_PROVEN"
                for name, proof in invariant_proofs.items()
                if not proof["passed"]
            )
        if completeness < MIN_EVIDENCE_COMPLETENESS:
            reasons.append("EVIDENCE_COMPLETENESS_BELOW_85_PERCENT")
        if agreement < MIN_MODEL_AGREEMENT:
            reasons.append("MODEL_AGREEMENT_BELOW_80_PERCENT")
        if edge < MIN_EDGE:
            reasons.append("EDGE_BELOW_7_PERCENT")
        if risk_flags:
            reasons.append("UNRESOLVED_RISK_FLAGS")
        decision = "EXECUTE" if not reasons else "HOLD"
        result = {
            "event_id": event_id,
            "league": league,
            "market_type": market_type,
            "sportsbook": sportsbook,
            "starts_at": starts_at.isoformat().replace("+00:00", "Z"),
            "selected_outcome": selected,
            "market_no_vig_probability": str(no_vig[selected]),
            "ensemble_probability": str(ensemble),
            "edge": str(edge),
            "evidence_completeness": str(completeness),
            "model_agreement": str(agreement),
            "decision": decision,
            "reasons": reasons or ["ALL_SPORTS_THRESHOLDS_AND_INVARIANTS_PROVEN"],
            "risk_flags": risk_flags,
            "invariant_proofs": invariant_proofs,
            "action_boundary": "ANALYSIS_ONLY_NO_WAGER",
        }
        result["decision_sha256"] = sha256(result)
        return result
    except ContractError as exc:
        return _reject(event, str(exc))


def evaluate_sports_analysis(
    payload: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(payload, Mapping):
        result = {
            "contract": CONTRACT_ID,
            "decision": "REJECT",
            "reason": "SPORTS_ANALYSIS_OBJECT_MISSING",
            "markets": [],
            "action_boundary": "ANALYSIS_ONLY_NO_WAGER",
        }
        result["receipt_sha256"] = sha256(result)
        return result
    if payload.get("contract") != CONTRACT_ID:
        result = {
            "contract": CONTRACT_ID,
            "decision": "REJECT",
            "reason": "SPORTS_CONTRACT_ID_MISMATCH",
            "markets": [],
            "action_boundary": "ANALYSIS_ONLY_NO_WAGER",
        }
        result["receipt_sha256"] = sha256(result)
        return result
    markets = payload.get("markets")
    if not isinstance(markets, list) or not markets:
        evaluated: list[dict[str, Any]] = []
        overall = "HOLD" if payload.get("collection_holds") else "REJECT"
        reason = "LIVE_COLLECTION_HOLD" if overall == "HOLD" else "NO_MARKETS_RETURNED"
    else:
        evaluated = [evaluate_market(market, now=moment) for market in markets]
        decisions = {market["decision"] for market in evaluated}
        overall = "EXECUTE" if "EXECUTE" in decisions else ("HOLD" if "HOLD" in decisions else "REJECT")
        reason = (
            "AT_LEAST_ONE_MARKET_PROVED_EXECUTE"
            if overall == "EXECUTE"
            else "NO_MARKET_PROVED_EXECUTE"
        )
    result = {
        "contract": CONTRACT_ID,
        "architecture_id": ARCHITECTURE_ID,
        "evaluated_at": moment.isoformat().replace("+00:00", "Z"),
        "decision": overall,
        "reason": reason,
        "thresholds": {
            "minimum_edge": str(MIN_EDGE),
            "minimum_evidence_completeness": str(MIN_EVIDENCE_COMPLETENESS),
            "minimum_model_agreement": str(MIN_MODEL_AGREEMENT),
            "minimum_models": MIN_MODELS,
        },
        "markets": evaluated,
        "collection_holds": payload.get("collection_holds", []),
        "action_boundary": "ANALYSIS_ONLY_NO_WAGER",
    }
    result["receipt_sha256"] = sha256(result)
    return result
