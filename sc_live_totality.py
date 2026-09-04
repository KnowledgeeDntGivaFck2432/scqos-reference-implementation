import os, json, hashlib, statistics, requests
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now().date().isoformat()
MLB = "https://statsapi.mlb.com/api"
ODDS = "https://api.the-odds-api.com/v4"
ODDS_KEY = os.getenv("ODDS_API_KEY", "")

S = requests.Session()
S.headers.update({"User-Agent":"SCQOS-Supreme-Computation/1.0"})

def get(url, params=None):
    r = S.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def sha(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def schedule():
    return get(f"{MLB}/v1/schedule",{
        "sportId":1,
        "date":TODAY,
        "hydrate":"probablePitcher,team,venue"
    })

def live(gamepk):
    return get(f"{MLB}/v1.1/game/{gamepk}/feed/live")

def lineup(team):
    out=[]
    for p in team.get("players",{}).values():
        if p.get("battingOrder"):
            out.append({
                "order":int(p["battingOrder"]),
                "name":p.get("person",{}).get("fullName"),
                "id":p.get("person",{}).get("id")
            })
    return sorted(out,key=lambda x:x["order"])

def odds():
    if not ODDS_KEY:
        return []
    return get(f"{ODDS}/sports/baseball_mlb/odds",{
        "apiKey":ODDS_KEY,
        "regions":"us",
        "markets":"h2h",
        "oddsFormat":"decimal",
        "dateFormat":"iso"
    })

def find_market(events,away,home):
    for e in events:
        names={e.get("away_team"),e.get("home_team")}
        if away in names and home in names:
            return e
    return None

def market_state(event,away,home):
    rows=[]
    if event:
        for b in event.get("bookmakers",[]):
            for m in b.get("markets",[]):
                if m.get("key")!="h2h":
                    continue
                o={x["name"]:x["price"] for x in m.get("outcomes",[])}
                if away in o and home in o:
                    pa,pb=1/o[away],1/o[home]
                    z=pa+pb
                    rows.append({
                        "book":b.get("title"),
                        "away_prob":pa/z,
                        "home_prob":pb/z,
                        "away_odds":o[away],
                        "home_odds":o[home],
                        "updated":m.get("last_update")
                    })
    return rows

def analyze(g, odds_events):
    gp=g["gamePk"]
    f=live(gp)
    gd=f["gameData"]
    box=f["liveData"]["boxscore"]

    away=gd["teams"]["away"]["name"]
    home=gd["teams"]["home"]["name"]

    aps=gd.get("probablePitchers",{}).get("away")
    hps=gd.get("probablePitchers",{}).get("home")

    al=lineup(box["teams"]["away"])
    hl=lineup(box["teams"]["home"])

    mk=market_state(find_market(odds_events,away,home),away,home)

    gates={
        "event_identity":bool(gp),
        "official_start_time":bool(gd.get("datetime",{}).get("dateTime")),
        "away_pitcher":bool(aps),
        "home_pitcher":bool(hps),
        "away_lineup_complete":len(al)>=9,
        "home_lineup_complete":len(hl)>=9,
        "multi_book_market":len(mk)>=2,
    }

    totality=1
    for v in gates.values():
        totality*=int(bool(v))

    failed=[k for k,v in gates.items() if not v]

    state={
        "gamePk":gp,
        "event":f"{away} @ {home}",
        "start":gd.get("datetime",{}).get("dateTime"),
        "status":gd.get("status",{}).get("detailedState"),
        "away_pitcher":aps,
        "home_pitcher":hps,
        "away_lineup":al,
        "home_lineup":hl,
        "market":mk,
        "gates":gates,
        "failed_gates":failed,
        "totality_product":totality,
        "decision":"PASS_TO_NEXT_LAYER" if totality==1 else "HOLD",
        "timestamp":datetime.now(timezone.utc).isoformat()
    }
    state["sha256"]=sha(state)
    return state

def main():
    print("="*70)
    print("SUPREME COMPUTATION — LIVE MLB TOTALITY")
    print("DATE:",TODAY)
    print("="*70)

    odds_events=odds()

    if not ODDS_KEY:
        print("ODDS_API_KEY: NOT PRESENT → MARKET GATE WILL HOLD")
    else:
        print("LIVE ODDS EVENTS:",len(odds_events))

    sched=schedule()
    games=[g for d in sched.get("dates",[]) for g in d.get("games",[])]

    results=[]

    for g in games:
        try:
            r=analyze(g,odds_events)
            results.append(r)

            print()
            print(r["event"])
            print("STATUS:",r["status"])
            print("TOTALITY:",r["totality_product"])

            if r["failed_gates"]:
                print("FAILED:",", ".join(r["failed_gates"]))

            print("DECISION:",r["decision"])
            print("SHA256:",r["sha256"])

        except Exception as e:
            print("ERROR",g.get("gamePk"),repr(e))

    receipt={
        "generated":datetime.now(timezone.utc).isoformat(),
        "date":TODAY,
        "events":results
    }
    receipt["receipt_sha256"]=sha(receipt)

    p=Path("sc-evidence/sports")/TODAY
    p.mkdir(parents=True,exist_ok=True)

    out=p/"live-mlb-totality.json"
    out.write_text(json.dumps(receipt,indent=2,default=str))

    print()
    print("="*70)
    print("RECEIPT:",out.resolve())
    print("RECEIPT SHA256:",receipt["receipt_sha256"])
    print("="*70)

main()
