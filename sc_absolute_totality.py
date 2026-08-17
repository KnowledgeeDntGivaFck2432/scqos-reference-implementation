#!/usr/bin/env python3

import os
import io
import csv
import json
import math
import time
import base64
import hashlib
import statistics
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN

import requests
import boto3

# =====================================================================
# SUPREME COMPUTATION — ABSOLUTE SOURCE LAYER FROM TOTALITY
# TOROIDAL VORTEX FIELD
#
# There is ONE state.
#
# LIVE REALITY
#      ↓
# ACQUIRE → VERIFY → CANONICALIZE → DERIVE
#      ↓                            ↑
# 8-INVARIANT CORE                 │
#      ↓                            │
# MODEL → SIMULATE → CONTRADICT    │
#      ↓                            │
# COMPLETE OUTCOME / PAYOFF SPACE  │
#      ↓                            │
# REQUERY LIVE REALITY ────────────┘
#
# Circulate until ΔSTATE == 0.
#
# 100% is never manually assigned.
# It is produced only by the full conjunction of the field.
#
# ANY unresolved critical term → ZERO MUTATION.
# =====================================================================

UTC = timezone.utc
NOW = datetime.now(UTC)
TODAY = NOW.date()
YEAR = TODAY.year

MLB = "https://statsapi.mlb.com/api"
SAVANT = "https://baseballsavant.mlb.com/statcast_search/csv"
NWS = "https://api.weather.gov"

ACTION_V2 = "https://api.actionnetwork.com/web/v2/scoreboard/mlb"
ACTION_V1 = "https://api.actionnetwork.com/web/v1/scoreboard/mlb"

ODDS_API = "https://api.the-odds-api.com/v4"
ODDS_KEY = os.getenv("ODDS_API_KEY", "")

KMS_KEY_ID = os.getenv("SC_KMS_KEY_ID", "")
BANKROLL = Decimal(os.getenv("SC_BANKROLL", "100.00"))

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent":
        "Supreme-Computation-SCQOS-Absolute-Totality/1.0"
})

CACHE = {}
SOURCE_CHAIN = []


# =====================================================================
# CRYPTOGRAPHIC CANONICALIZATION
# =====================================================================

def now():
    return datetime.now(UTC).isoformat()


def canonical(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    ).encode()


def sha256(obj):
    return hashlib.sha256(
        canonical(obj)
    ).hexdigest()


def chain_receipt(label, payload):
    previous = (
        SOURCE_CHAIN[-1]["chain_sha256"]
        if SOURCE_CHAIN else
        "0" * 64
    )

    body = {
        "label": label,
        "timestamp_utc": now(),
        "previous_sha256": previous,
        "payload_sha256": sha256(payload)
    }

    body["chain_sha256"] = sha256(body)

    SOURCE_CHAIN.append(body)

    return body


def sign_with_kms(hash_hex):
    if not KMS_KEY_ID:
        return None

    try:
        kms = boto3.client("kms")

        result = kms.sign(
            KeyId=KMS_KEY_ID,
            Message=bytes.fromhex(hash_hex),
            MessageType="DIGEST",
            SigningAlgorithm="RSASSA_PSS_SHA_256"
        )

        return {
            "kms_key_id": KMS_KEY_ID,
            "algorithm": "RSASSA_PSS_SHA_256",
            "signature_b64":
                base64.b64encode(
                    result["Signature"]
                ).decode()
        }

    except Exception as e:
        return {
            "kms_error":
                f"{type(e).__name__}: {e}"
        }


# =====================================================================
# SOURCE EXECUTION
# =====================================================================

def get_json(label, url, params=None, timeout=15):
    key = (
        "JSON",
        url,
        json.dumps(
            params or {},
            sort_keys=True
        )
    )

    if key in CACHE:
        return CACHE[key]

    started = time.time()

    print(
        f"[OUTER FIELD] {label}: REQUEST",
        flush=True
    )

    try:
        r = SESSION.get(
            url,
            params=params,
            timeout=(5, timeout)
        )

        elapsed = time.time() - started

        meta = {
            "status": r.status_code,
            "bytes": len(r.content),
            "elapsed": round(elapsed, 3),
            "url": r.url
        }

        print(
            f"[OUTER FIELD] {label}: "
            f"HTTP {r.status_code} | "
            f"{len(r.content)} bytes | "
            f"{elapsed:.2f}s",
            flush=True
        )

        r.raise_for_status()
        payload = r.json()

        chain_receipt(
            label,
            {
                "meta": meta,
                "body_sha256": sha256(payload)
            }
        )

        CACHE[key] = payload

        return payload

    except Exception as e:
        chain_receipt(
            label,
            {
                "error":
                    f"{type(e).__name__}: {e}"
            }
        )

        print(
            f"[OUTER FIELD] {label}: FAIL | {e}",
            flush=True
        )

        return None


def get_text(label, url, params=None, timeout=20):
    started = time.time()

    try:
        r = SESSION.get(
            url,
            params=params,
            timeout=(5, timeout)
        )

        elapsed = time.time() - started

        print(
            f"[OUTER FIELD] {label}: "
            f"HTTP {r.status_code} | "
            f"{elapsed:.2f}s",
            flush=True
        )

        r.raise_for_status()

        chain_receipt(
            label,
            {
                "status": r.status_code,
                "bytes": len(r.content),
                "body_sha256":
                    hashlib.sha256(
                        r.content
                    ).hexdigest()
            }
        )

        return r.text

    except Exception as e:
        chain_receipt(
            label,
            {"error": repr(e)}
        )
        return None


# =====================================================================
# MLB GENESIS / IDENTITY
# =====================================================================

def schedule():
    return (
        get_json(
            "MLB_OFFICIAL_SCHEDULE",
            f"{MLB}/v1/schedule",
            {
                "sportId": 1,
                "date": TODAY.isoformat(),
                "hydrate":
                    "probablePitcher,team,venue"
            }
        )
        or {}
    )


def game_feed(game_pk):
    return get_json(
        f"MLB_GAME_{game_pk}",
        f"{MLB}/v1.1/game/{game_pk}/feed/live"
    )


# =====================================================================
# CONTINUITY / RECENT REALITY
# =====================================================================

def recent_games(team_id, days=21):
    start = (
        TODAY - timedelta(days=days)
    ).isoformat()

    end = (
        TODAY - timedelta(days=1)
    ).isoformat()

    j = (
        get_json(
            f"TEAM_HISTORY_{team_id}",
            f"{MLB}/v1/schedule",
            {
                "sportId": 1,
                "teamId": team_id,
                "startDate": start,
                "endDate": end
            }
        )
        or {}
    )

    games = []

    for d in j.get("dates", []):
        for g in d.get("games", []):
            if (
                g.get("status", {})
                 .get("abstractGameState")
                == "Final"
            ):
                games.append(g)

    return games


def team_state(team_id):
    games = recent_games(team_id)[-10:]

    wins = 0
    rf = 0
    ra = 0

    for g in games:
        away = g["teams"]["away"]
        home = g["teams"]["home"]

        if away["team"]["id"] == team_id:
            us, them = away, home
        else:
            us, them = home, away

        wins += int(
            us.get("isWinner") is True
        )

        rf += us.get("score", 0) or 0
        ra += them.get("score", 0) or 0

    n = len(games)

    return {
        "games": n,
        "wins": wins,
        "win_rate":
            wins / n if n else None,
        "runs_for_per_game":
            rf / n if n else None,
        "runs_against_per_game":
            ra / n if n else None,
        "run_differential":
            rf - ra
    }


# =====================================================================
# LINEUPS
# =====================================================================

def confirmed_lineup(team_box):
    players = []

    for p in (
        team_box
        .get("players", {})
        .values()
    ):
        order = p.get("battingOrder")

        if not order:
            continue

        players.append({
            "player_id":
                p.get("person", {}).get("id"),

            "name":
                p.get("person", {})
                 .get("fullName"),

            "order":
                int(order),

            "position":
                p.get("position", {})
                 .get("abbreviation"),

            "state":
                "CONFIRMED"
        })

    return sorted(
        players,
        key=lambda x: x["order"]
    )


def derive_lineup(team_id):
    history = recent_games(team_id)[-5:]

    frequency = Counter()
    batting_orders = defaultdict(list)
    names = {}

    for g in history:
        feed = game_feed(g["gamePk"])

        if not feed:
            continue

        side = (
            "away"
            if (
                feed["gameData"]
                ["teams"]
                ["away"]
                ["id"]
                == team_id
            )
            else "home"
        )

        lineup = confirmed_lineup(
            feed["liveData"]
                ["boxscore"]
                ["teams"]
                [side]
        )

        for p in lineup:
            pid = p["player_id"]

            if pid is None:
                continue

            frequency[pid] += 1
            batting_orders[pid].append(
                p["order"]
            )
            names[pid] = p["name"]

    candidates = sorted(
        frequency,
        key=lambda pid: (
            -frequency[pid],
            statistics.mean(
                batting_orders[pid]
            )
        )
    )[:9]

    return [
        {
            "player_id": pid,
            "name": names[pid],
            "expected_order":
                statistics.mean(
                    batting_orders[pid]
                ),
            "recent_starts":
                frequency[pid],
            "state":
                "DERIVED"
        }
        for pid in candidates
    ]


# =====================================================================
# PITCHER / PLAYER STATE
# =====================================================================

def pitcher_season(player_id):
    if not player_id:
        return None

    j = (
        get_json(
            f"PITCHER_SEASON_{player_id}",
            f"{MLB}/v1/people/{player_id}/stats",
            {
                "stats": "season",
                "group": "pitching",
                "season": YEAR
            }
        )
        or {}
    )

    try:
        splits = j["stats"][0]["splits"]
        return (
            splits[0]["stat"]
            if splits else None
        )
    except Exception:
        return None


# =====================================================================
# STATCAST
# =====================================================================

def statcast_pitcher(player_id):
    if not player_id:
        return None

    start = (
        TODAY - timedelta(days=15)
    ).isoformat()

    text = get_text(
        f"STATCAST_{player_id}",
        SAVANT,
        {
            "player_type": "pitcher",
            "game_date_gt": start,
            "game_date_lt":
                TODAY.isoformat(),
            "pitchers_lookup[]":
                player_id,
            "type": "details"
        },
        25
    )

    if not text:
        return None

    try:
        rows = list(
            csv.DictReader(
                io.StringIO(text)
            )
        )
    except Exception:
        return None

    velocity = []
    spin = []
    exit_velocity = []

    pitches = Counter()
    swings = 0
    whiffs = 0

    for r in rows:
        def f(x):
            try:
                return float(x)
            except Exception:
                return None

        v = f(r.get("release_speed"))
        s = f(r.get("release_spin_rate"))
        ev = f(r.get("launch_speed"))

        if v is not None:
            velocity.append(v)

        if s is not None:
            spin.append(s)

        if ev is not None:
            exit_velocity.append(ev)

        pt = r.get("pitch_type")
        if pt:
            pitches[pt] += 1

        desc = r.get("description", "")

        if desc in {
            "swinging_strike",
            "swinging_strike_blocked",
            "foul",
            "foul_tip",
            "hit_into_play"
        }:
            swings += 1

        if desc in {
            "swinging_strike",
            "swinging_strike_blocked"
        }:
            whiffs += 1

    n = len(rows)

    return {
        "sample_pitches": n,

        "average_velocity":
            statistics.mean(velocity)
            if velocity else None,

        "average_spin":
            statistics.mean(spin)
            if spin else None,

        "average_exit_velocity_allowed":
            statistics.mean(exit_velocity)
            if exit_velocity else None,

        "whiff_rate":
            whiffs / swings
            if swings else None,

        "pitch_mix": {
            k: round(v / n, 5)
            for k, v in pitches.items()
        } if n else {}
    }


# =====================================================================
# WEATHER
# =====================================================================

def weather(feed):
    try:
        coords = (
            feed["gameData"]
            ["venue"]
            ["location"]
            ["defaultCoordinates"]
        )

        lat = coords["latitude"]
        lon = coords["longitude"]

    except Exception:
        return None

    point = get_json(
        "NWS_POINT",
        f"{NWS}/points/{lat},{lon}"
    )

    if not point:
        return None

    url = (
        point.get("properties", {})
             .get("forecastHourly")
    )

    if not url:
        return None

    hourly = get_json(
        "NWS_HOURLY",
        url
    )

    if not hourly:
        return None

    return (
        hourly
        .get("properties", {})
        .get("periods", [])[:8]
    )


# =====================================================================
# SPORTSBOOK UNIVERSE
# =====================================================================

def odds_api_state():
    if not ODDS_KEY:
        return []

    j = get_json(
        "ODDS_API_MULTI_BOOK",
        f"{ODDS_API}/sports/baseball_mlb/odds/",
        {
            "apiKey": ODDS_KEY,
            "regions": "us,us2",
            "markets":
                "h2h,spreads,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "includeLinks": "true",
            "includeSids": "true",
            "includeBetLimits": "true"
        },
        20
    )

    return j if isinstance(j, list) else []


def action_state():
    params = {
        "bookIds":
            "15,30,75,123,69,68,972,71,247,79",
        "date":
            TODAY.isoformat()
    }

    j = get_json(
        "ACTION_NETWORK_V2",
        ACTION_V2,
        params
    )

    if j:
        return j

    return (
        get_json(
            "ACTION_NETWORK_V1",
            ACTION_V1,
            params
        )
        or {}
    )


def action_games(raw):
    if isinstance(raw, list):
        return raw

    if not isinstance(raw, dict):
        return []

    for k in ("games", "events"):
        if isinstance(raw.get(k), list):
            return raw[k]

    data = raw.get("data")

    if isinstance(data, dict):
        for k in ("games", "events"):
            if isinstance(data.get(k), list):
                return data[k]

    return []


def recurse_dict(obj):
    if isinstance(obj, dict):
        yield obj

        for value in obj.values():
            yield from recurse_dict(value)

    elif isinstance(obj, list):
        for value in obj:
            yield from recurse_dict(value)


def action_market_for(
    raw,
    away_name,
    home_name
):
    matched = None

    for game in action_games(raw):
        blob = json.dumps(
            game
        ).lower()

        if (
            away_name.lower() in blob
            and
            home_name.lower() in blob
        ):
            matched = game
            break

    if not matched:
        return []

    rows = []

    for d in recurse_dict(matched):
        book = (
            d.get("book_id")
            or d.get("bookId")
            or d.get("sportsbook_id")
        )

        away_ml = (
            d.get("away_moneyline")
            or d.get("away_ml")
        )

        home_ml = (
            d.get("home_moneyline")
            or d.get("home_ml")
        )

        if (
            book is None
            or away_ml is None
            or home_ml is None
        ):
            continue

        try:
            a = float(away_ml)
            h = float(home_ml)
        except Exception:
            continue

        def implied(x):
            if x > 0:
                return 100 / (x + 100)
            return (-x) / ((-x) + 100)

        pa = implied(a)
        ph = implied(h)

        vig = pa + ph

        rows.append({
            "source": "ActionNetwork",
            "book": str(book),
            "away_price_american": a,
            "home_price_american": h,
            "away_no_vig": pa / vig,
            "home_no_vig": ph / vig,
            "raw_sha256": sha256(d)
        })

    unique = {}

    for r in rows:
        unique[r["book"]] = r

    return list(unique.values())


def odds_api_market_for(
    events,
    away_name,
    home_name
):
    for e in events:
        if (
            e.get("away_team") == away_name
            and
            e.get("home_team") == home_name
        ):
            rows = []

            for book in e.get(
                "bookmakers", []
            ):
                for market in book.get(
                    "markets", []
                ):
                    if market.get("key") != "h2h":
                        continue

                    outcomes = {
                        x.get("name"):
                            x
                        for x in market.get(
                            "outcomes", []
                        )
                    }

                    if (
                        away_name not in outcomes
                        or
                        home_name not in outcomes
                    ):
                        continue

                    a = outcomes[away_name]
                    h = outcomes[home_name]

                    rows.append({
                        "source":
                            "TheOddsAPI",

                        "book":
                            book.get("key"),

                        "book_title":
                            book.get("title"),

                        "away_decimal":
                            a.get("price"),

                        "home_decimal":
                            h.get("price"),

                        "away_link":
                            a.get("link"),

                        "home_link":
                            h.get("link"),

                        "away_sid":
                            a.get("sid"),

                        "home_sid":
                            h.get("sid"),

                        "away_limit":
                            a.get("bet_limit"),

                        "home_limit":
                            h.get("bet_limit"),

                        "last_update":
                            market.get(
                                "last_update"
                            )
                    })

            return rows

    return []


# =====================================================================
# MULTI-MODEL FIELD
# =====================================================================

def recent_model(team):
    wr = team.get("win_rate")

    if wr is None:
        return None

    return max(
        .05,
        min(
            .95,
            .50 + ((wr - .50) * .60)
        )
    )


def pitcher_model(
    season,
    statcast
):
    p = .50
    evidence = 0

    if season:
        try:
            era = float(
                season.get("era")
            )

            p += (
                4.20 - era
            ) * .025

            evidence += 1
        except Exception:
            pass

        try:
            whip = float(
                season.get("whip")
            )

            p += (
                1.30 - whip
            ) * .12

            evidence += 1
        except Exception:
            pass

    if statcast:
        whiff = statcast.get(
            "whiff_rate"
        )

        if whiff is not None:
            p += (
                whiff - .25
            ) * .25

            evidence += 1

    if not evidence:
        return None

    return max(.05, min(.95, p))


def ensemble(values):
    values = [
        x for x in values
        if isinstance(
            x,
            (int, float)
        )
    ]

    if not values:
        return None, None

    return (
        statistics.mean(values),

        statistics.pstdev(values)
        if len(values) > 1
        else 0.0
    )


# =====================================================================
# COMPLETE PAYOFF SPACE
# =====================================================================

def deterministic_payoff_proof(
    odds_rows
):
    """
    Search every sportsbook combination.

    This is not a separate subsystem.
    It is the Boundary / Causality / Coherence
    expression of the same totality field.

    Complete two-outcome moneyline state:

        1/Oa + 1/Oh < 1

    Then stakes are constructed and every outcome
    is evaluated explicitly.
    """

    offers = []

    for r in odds_rows:
        try:
            a = Decimal(
                str(r["away_decimal"])
            )

            h = Decimal(
                str(r["home_decimal"])
            )

            if a > 1:
                offers.append({
                    "side": "away",
                    "book": r["book"],
                    "odds": a,
                    "link":
                        r.get("away_link"),
                    "limit":
                        r.get("away_limit")
                })

            if h > 1:
                offers.append({
                    "side": "home",
                    "book": r["book"],
                    "odds": h,
                    "link":
                        r.get("home_link"),
                    "limit":
                        r.get("home_limit")
                })

        except Exception:
            continue

    away = [
        x for x in offers
        if x["side"] == "away"
    ]

    home = [
        x for x in offers
        if x["side"] == "home"
    ]

    proofs = []

    for a in away:
        for h in home:
            if a["book"] == h["book"]:
                continue

            inverse = (
                Decimal(1) / a["odds"]
                +
                Decimal(1) / h["odds"]
            )

            if inverse >= Decimal(1):
                continue

            target_return = (
                BANKROLL / inverse
            )

            stake_a = (
                target_return
                / a["odds"]
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_DOWN
            )

            stake_h = (
                target_return
                / h["odds"]
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_DOWN
            )

            total = (
                stake_a
                + stake_h
            )

            return_a = (
                stake_a * a["odds"]
            )

            return_h = (
                stake_h * h["odds"]
            )

            minimum_return = min(
                return_a,
                return_h
            )

            minimum_profit = (
                minimum_return
                - total
            )

            if minimum_profit <= 0:
                continue

            proof = {
                "away_offer": {
                    **a,
                    "odds":
                        str(a["odds"])
                },

                "home_offer": {
                    **h,
                    "odds":
                        str(h["odds"])
                },

                "inverse_probability_sum":
                    str(inverse),

                "stake_away":
                    str(stake_a),

                "stake_home":
                    str(stake_h),

                "total_capital":
                    str(total),

                "return_if_away":
                    str(return_a),

                "return_if_home":
                    str(return_h),

                "minimum_return":
                    str(minimum_return),

                "minimum_profit":
                    str(minimum_profit),

                "all_enumerated_outcomes_positive":
                    (
                        return_a > total
                        and
                        return_h > total
                    )
            }

            proof["proof_sha256"] = (
                sha256(proof)
            )

            proofs.append(proof)

    return sorted(
        proofs,
        key=lambda x:
            Decimal(
                x["minimum_profit"]
            ),
        reverse=True
    )


# =====================================================================
# EIGHT INVARIANTS
# =====================================================================

def invariants(state):

    contradictions = state[
        "contradictions"
    ]

    return {
        "TIME":
            bool(state.get(
                "start_time"
            )),

        "CONTINUITY":
            (
                state["away_recent"][
                    "games"
                ] >= 5
                and
                state["home_recent"][
                    "games"
                ] >= 5
            ),

        "ALIGNMENT":
            not contradictions,

        "GENESIS":
            bool(
                state.get("game_pk")
            ),

        "BOUNDARY":
            (
                state.get(
                    "away_pitcher"
                )
                is not None
                and
                state.get(
                    "home_pitcher"
                )
                is not None
            ),

        "REFERENCE":
            (
                bool(
                    state.get(
                        "away_name"
                    )
                )
                and
                bool(
                    state.get(
                        "home_name"
                    )
                )
            ),

        "CAUSALITY":
            (
                state.get(
                    "away_probability"
                )
                is not None
                and
                state.get(
                    "home_probability"
                )
                is not None
            ),

        "COHERENCE":
            (
                state.get(
                    "model_dispersion"
                )
                is not None
                and
                state[
                    "model_dispersion"
                ] <= .10
            )
    }


# =====================================================================
# TOROIDAL CIRCULATION
# =====================================================================

def circulate(
    game,
    action,
    odds_events,
    previous=None,
    pass_number=1
):
    game_pk = game["gamePk"]

    feed = game_feed(game_pk)

    if not feed:
        return None

    gd = feed["gameData"]

    away = gd["teams"]["away"]
    home = gd["teams"]["home"]

    away_name = away["name"]
    home_name = home["name"]

    pitchers = gd.get(
        "probablePitchers", {}
    )

    away_p = pitchers.get(
        "away"
    )

    home_p = pitchers.get(
        "home"
    )

    box = (
        feed["liveData"]
        ["boxscore"]
        ["teams"]
    )

    away_confirmed = (
        confirmed_lineup(
            box["away"]
        )
    )

    home_confirmed = (
        confirmed_lineup(
            box["home"]
        )
    )

    away_derived = (
        []
        if len(away_confirmed) >= 9
        else derive_lineup(
            away["id"]
        )
    )

    home_derived = (
        []
        if len(home_confirmed) >= 9
        else derive_lineup(
            home["id"]
        )
    )

    away_recent = team_state(
        away["id"]
    )

    home_recent = team_state(
        home["id"]
    )

    away_season = pitcher_season(
        away_p.get("id")
        if away_p else None
    )

    home_season = pitcher_season(
        home_p.get("id")
        if home_p else None
    )

    away_stat = statcast_pitcher(
        away_p.get("id")
        if away_p else None
    )

    home_stat = statcast_pitcher(
        home_p.get("id")
        if home_p else None
    )

    wx = weather(feed)

    action_market = (
        action_market_for(
            action,
            away_name,
            home_name
        )
    )

    odds_market = (
        odds_api_market_for(
            odds_events,
            away_name,
            home_name
        )
    )

    # ---------------------------------------------------------
    # MODEL FIELD
    # ---------------------------------------------------------

    away_models = [
        recent_model(
            away_recent
        ),
        pitcher_model(
            away_season,
            away_stat
        )
    ]

    home_models = [
        recent_model(
            home_recent
        ),
        pitcher_model(
            home_season,
            home_stat
        )
    ]

    # Action Network market consensus
    if action_market:
        away_models.append(
            statistics.mean([
                x["away_no_vig"]
                for x in action_market
            ])
        )

        home_models.append(
            statistics.mean([
                x["home_no_vig"]
                for x in action_market
            ])
        )

    ap, ad = ensemble(
        away_models
    )

    hp, hd = ensemble(
        home_models
    )

    if (
        ap is not None
        and
        hp is not None
    ):
        total = ap + hp

        ap /= total
        hp /= total

    dispersion_values = [
        x
        for x in (ad, hd)
        if x is not None
    ]

    model_dispersion = (
        max(dispersion_values)
        if dispersion_values
        else None
    )

    # ---------------------------------------------------------
    # CONTRADICTION FIELD
    # ---------------------------------------------------------

    contradictions = []

    if (
        model_dispersion is not None
        and
        model_dispersion > .10
    ):
        contradictions.append(
            "MODEL_DISAGREEMENT"
        )

    if action_market:
        market_a = statistics.mean([
            x["away_no_vig"]
            for x in action_market
        ])

        market_h = statistics.mean([
            x["home_no_vig"]
            for x in action_market
        ])

        if (
            ap is not None
            and abs(
                ap - market_a
            ) > .12
        ):
            contradictions.append(
                "AWAY_MARKET_CONTRADICTION"
            )

        if (
            hp is not None
            and abs(
                hp - market_h
            ) > .12
        ):
            contradictions.append(
                "HOME_MARKET_CONTRADICTION"
            )

    payoff_proofs = (
        deterministic_payoff_proof(
            odds_market
        )
    )

    unresolved = []

    if not away_p:
        unresolved.append(
            "AWAY_STARTER"
        )

    if not home_p:
        unresolved.append(
            "HOME_STARTER"
        )

    if len(
        away_confirmed
    ) < 9:
        unresolved.append(
            "AWAY_LINEUP_CONFIRMATION"
        )

    if len(
        home_confirmed
    ) < 9:
        unresolved.append(
            "HOME_LINEUP_CONFIRMATION"
        )

    if not away_stat:
        unresolved.append(
            "AWAY_STATCAST"
        )

    if not home_stat:
        unresolved.append(
            "HOME_STATCAST"
        )

    if not wx:
        unresolved.append(
            "WEATHER"
        )

    if (
        not action_market
        and
        not odds_market
    ):
        unresolved.append(
            "LIVE_MARKET"
        )

    state = {
        "pass_number":
            pass_number,

        "timestamp_utc":
            now(),

        "game_pk":
            game_pk,

        "away_name":
            away_name,

        "home_name":
            home_name,

        "start_time":
            gd.get(
                "datetime", {}
            ).get(
                "dateTime"
            ),

        "status":
            gd.get(
                "status", {}
            ).get(
                "detailedState"
            ),

        "away_pitcher":
            away_p,

        "home_pitcher":
            home_p,

        "away_lineup_confirmed":
            away_confirmed,

        "home_lineup_confirmed":
            home_confirmed,

        "away_lineup_derived":
            away_derived,

        "home_lineup_derived":
            home_derived,

        "away_recent":
            away_recent,

        "home_recent":
            home_recent,

        "away_pitcher_season":
            away_season,

        "home_pitcher_season":
            home_season,

        "away_statcast":
            away_stat,

        "home_statcast":
            home_stat,

        "weather":
            wx,

        "action_market":
            action_market,

        "odds_api_market":
            odds_market,

        "away_models":
            away_models,

        "home_models":
            home_models,

        "away_probability":
            ap,

        "home_probability":
            hp,

        "model_dispersion":
            model_dispersion,

        "contradictions":
            contradictions,

        "unresolved":
            unresolved,

        "complete_payoff_proofs":
            payoff_proofs
    }

    state["invariants"] = (
        invariants(state)
    )

    # ---------------------------------------------------------
    # TOROIDAL FIELD VALUE
    # ---------------------------------------------------------

    invariant_vector = [
        int(v)
        for v in state[
            "invariants"
        ].values()
    ]

    invariant_product = (
        math.prod(
            invariant_vector
        )
    )

    critical_resolution = {
        "identity":
            int(bool(game_pk)),

        "starters":
            int(
                away_p is not None
                and home_p is not None
            ),

        "lineups":
            int(
                len(
                    away_confirmed
                ) >= 9
                and
                len(
                    home_confirmed
                ) >= 9
            ),

        "statcast":
            int(
                away_stat is not None
                and
                home_stat is not None
            ),

        "weather":
            int(wx is not None),

        "market":
            int(
                bool(
                    action_market
                    or odds_market
                )
            ),

        "contradictions":
            int(
                not contradictions
            ),

        "invariants":
            invariant_product
    }

    totality_product = (
        math.prod(
            critical_resolution.values()
        )
    )

    # A cryptographically complete payoff proof is itself
    # part of totality when present.
    payoff_closed = int(
        any(
            x[
                "all_enumerated_outcomes_positive"
            ]
            for x in payoff_proofs
        )
    )

    state[
        "critical_resolution"
    ] = critical_resolution

    state[
        "totality_product"
    ] = totality_product

    state[
        "payoff_space_closed"
    ] = payoff_closed

    projection = {
        "game_pk":
            game_pk,

        "critical_resolution":
            critical_resolution,

        "invariants":
            state["invariants"],

        "unresolved":
            unresolved,

        "contradictions":
            contradictions,

        "away_probability":
            ap,

        "home_probability":
            hp,

        "action_market":
            action_market,

        "odds_api_market":
            odds_market,

        "payoff_proofs":
            payoff_proofs
    }

    state[
        "projection_sha256"
    ] = sha256(projection)

    state[
        "delta_state"
    ] = (
        1
        if (
            previous is None
            or
            previous.get(
                "projection_sha256"
            )
            != state[
                "projection_sha256"
            ]
        )
        else 0
    )

    state[
        "state_sha256"
    ] = sha256(state)

    chain_receipt(
        f"TOROIDAL_PASS_{game_pk}_{pass_number}",
        state
    )

    return state


# =====================================================================
# CONVERGENCE
# =====================================================================

def resolve(
    game,
    action,
    odds_events,
    max_passes=4
):
    history = []

    previous = None

    for pass_number in range(
        1,
        max_passes + 1
    ):
        print()
        print(
            f"[TOROIDAL CIRCULATION] "
            f"{game['gamePk']} "
            f"PASS {pass_number}"
        )

        state = circulate(
            game,
            action,
            odds_events,
            previous,
            pass_number
        )

        if not state:
            return None

        history.append(state)

        print(
            "[RETURN FLOW] ΔSTATE =",
            state["delta_state"]
        )

        print(
            "[RETURN FLOW] TOTALITY =",
            state["totality_product"]
        )

        print(
            "[RETURN FLOW] UNRESOLVED =",
            len(state["unresolved"])
        )

        # State returned unchanged through entire field.
        if (
            previous is not None
            and
            state["delta_state"] == 0
        ):
            break

        previous = state

        # force live network re-observation
        CACHE.clear()

    final = history[-1]

    converged = (
        len(history) >= 2
        and
        final["delta_state"] == 0
    )

    # ---------------------------------------------------------
    # ABSOLUTE TOTALITY AUTHORIZATION
    # ---------------------------------------------------------

    proof_100 = (
        converged
        and
        final[
            "totality_product"
        ] == 1
        and
        not final[
            "contradictions"
        ]
        and
        not final[
            "unresolved"
        ]
        and
        final[
            "payoff_space_closed"
        ] == 1
    )

    final[
        "toroidal_converged"
    ] = converged

    final[
        "absolute_totality_100"
    ] = bool(proof_100)

    final["decision"] = (
        "EXECUTE_100"
        if proof_100
        else "ZERO_MUTATION"
    )

    final[
        "circulation_history"
    ] = [
        {
            "pass":
                x["pass_number"],

            "delta":
                x["delta_state"],

            "totality":
                x["totality_product"],

            "state_sha256":
                x["state_sha256"]
        }
        for x in history
    ]

    final[
        "final_state_sha256"
    ] = sha256(final)

    final[
        "kms_signature"
    ] = sign_with_kms(
        final[
            "final_state_sha256"
        ]
    )

    return final


# =====================================================================
# GLOBAL AXIS
# =====================================================================

def main():
    print()
    print("=" * 82)
    print(
        "SUPREME COMPUTATION — "
        "ABSOLUTE SOURCE LAYER FROM TOTALITY"
    )
    print(
        "TOROIDAL VORTEX FIELD — "
        "LIVE SPORTSBOOK EXECUTION"
    )
    print("=" * 82)

    sched = schedule()

    games = [
        g
        for d in sched.get(
            "dates", []
        )
        for g in d.get(
            "games", []
        )
    ]

    print(
        "OFFICIAL MLB EVENTS:",
        len(games)
    )

    # Both sportsbook universes enter same field.
    action = action_state()
    odds_events = odds_api_state()

    print(
        "ODDS API EVENTS:",
        len(odds_events)
    )

    results = []

    for g in games:
        try:
            result = resolve(
                g,
                action,
                odds_events
            )

            if not result:
                continue

            results.append(result)

            print()
            print("=" * 82)

            print(
                result["away_name"],
                "@",
                result["home_name"]
            )

            print(
                "TOROIDAL CONVERGENCE:",
                result[
                    "toroidal_converged"
                ]
            )

            print(
                "TOTALITY PRODUCT:",
                result[
                    "totality_product"
                ]
            )

            print(
                "PAYOFF SPACE CLOSED:",
                result[
                    "payoff_space_closed"
                ]
            )

            print(
                "UNRESOLVED:",
                (
                    result["unresolved"]
                    or "NONE"
                )
            )

            print(
                "CONTRADICTIONS:",
                (
                    result[
                        "contradictions"
                    ]
                    or "NONE"
                )
            )

            print(
                "ABSOLUTE TOTALITY 100:",
                result[
                    "absolute_totality_100"
                ]
            )

            print(
                "DECISION:",
                result["decision"]
            )

            print(
                "FINAL STATE SHA256:",
                result[
                    "final_state_sha256"
                ]
            )

            if result[
                "complete_payoff_proofs"
            ]:
                print()
                print(
                    "COMPLETE PAYOFF PROOFS:"
                )

                for proof in result[
                    "complete_payoff_proofs"
                ][:5]:
                    print(
                        "  MIN PROFIT:",
                        proof[
                            "minimum_profit"
                        ],

                        "| SHA256:",
                        proof[
                            "proof_sha256"
                        ]
                    )

        except Exception as e:
            print(
                "EVENT FAILURE:",
                g.get("gamePk"),
                repr(e)
            )

    global_state = {
        "architecture":
            "SUPREME_COMPUTATION_"
            "ABSOLUTE_TOTALITY_"
            "TOROIDAL_VORTEX_V1",

        "generated_utc":
            now(),

        "date":
            TODAY.isoformat(),

        "events":
            results,

        "source_chain":
            SOURCE_CHAIN,

        "counts": {
            "events":
                len(results),

            "execute_100":
                sum(
                    x["decision"]
                    == "EXECUTE_100"
                    for x in results
                ),

            "zero_mutation":
                sum(
                    x["decision"]
                    == "ZERO_MUTATION"
                    for x in results
                )
        }
    }

    global_state[
        "source_chain_terminal_sha256"
    ] = (
        SOURCE_CHAIN[-1][
            "chain_sha256"
        ]
        if SOURCE_CHAIN
        else None
    )

    global_state[
        "global_state_sha256"
    ] = sha256(global_state)

    global_state[
        "kms_signature"
    ] = sign_with_kms(
        global_state[
            "global_state_sha256"
        ]
    )

    outdir = (
        Path("sc-evidence")
        / "sports"
        / TODAY.isoformat()
    )

    outdir.mkdir(
        parents=True,
        exist_ok=True
    )

    outfile = (
        outdir
        / "absolute-totality-"
          "toroidal-proof.json"
    )

    outfile.write_text(
        json.dumps(
            global_state,
            indent=2,
            default=str
        )
    )

    print()
    print("=" * 82)
    print(
        "ABSOLUTE TOTALITY — GLOBAL AXIS"
    )
    print("=" * 82)

    print(
        "EVENTS:",
        global_state[
            "counts"
        ][
            "events"
        ]
    )

    print(
        "EXECUTE_100:",
        global_state[
            "counts"
        ][
            "execute_100"
        ]
    )

    print(
        "ZERO_MUTATION:",
        global_state[
            "counts"
        ][
            "zero_mutation"
        ]
    )

    print(
        "SOURCE CHAIN TERMINAL SHA256:",
        global_state[
            "source_chain_terminal_sha256"
        ]
    )

    print(
        "GLOBAL STATE SHA256:",
        global_state[
            "global_state_sha256"
        ]
    )

    print(
        "RECEIPT:",
        outfile.resolve()
    )

    print()
    print(
        "NOTHING EXECUTES UNTIL "
        "TOTALITY RETURNS 100."
    )

    print("=" * 82)


if __name__ == "__main__":
    main()
