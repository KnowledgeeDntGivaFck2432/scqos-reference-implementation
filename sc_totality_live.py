import json, hashlib, math, statistics, requests
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now().strftime("%Y%m%d")
TODAY_ISO = datetime.now().strftime("%Y-%m-%d")

MLB = "https://statsapi.mlb.com/api"
ACTION = "https://api.actionnetwork.com/web/v2/scoreboard/mlb"

BOOK_IDS = "15,30,75,123,69,68,972,71,247,79"

S = requests.Session()
S.headers.update({"User-Agent":"SCQOS-Supreme-Computation/2.0"})

def GET(url, params=None, label="SOURCE"):
    import time
    t=time.time()
    print(f"[LIVE] {label}: REQUEST", flush=True)
    try:
        r=S.get(url, params=params, timeout=(5,12))
        print(
            f"[LIVE] {label}: HTTP {r.status_code} | "
            f"{len(r.content)} bytes | {time.time()-t:.2f}s",
            flush=True
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(
            f"[LIVE] {label}: FAIL | {type(e).__name__}: {e}",
            flush=True
        )
        raise

def H(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",",":"), default=str).encode()
    ).hexdigest()

def american_implied(x):
    if x is None: return None
    x=float(x)
    return 100/(x+100) if x>0 else (-x)/((-x)+100)

def novig(a,b):
    if a is None or b is None: return (None,None)
    s=a+b
    return (a/s,b/s) if s else (None,None)

def mlb_schedule():
    return GET(
        f"{MLB}/v1/schedule",
        {
            "sportId":1,
            "date":TODAY_ISO,
            "hydrate":"probablePitcher,team,venue"
        },
        label="MLB_SCHEDULE"
    )

def mlb_feed(gamepk):
    return GET(f"{MLB}/v1.1/game/{gamepk}/feed/live")

def recent(team_id, n=10):
    j=GET(f"{MLB}/v1/schedule",{
        "sportId":1,
        "teamId":team_id,
        "startDate":(datetime.now().date()).replace(day=max(1,datetime.now().day-20)).isoformat(),
        "endDate":TODAY_ISO
    })
    out=[]
    for d in j.get("dates",[]):
        for g in d.get("games",[]):
            if g.get("status",{}).get("abstractGameState")=="Final":
                out.append(g)
    out=out[-n:]
    w=rf=ra=0
    for g in out:
        A,Hm=g["teams"]["away"],g["teams"]["home"]
        us,them=(A,Hm) if A["team"]["id"]==team_id else (Hm,A)
        w += int(us.get("isWinner") is True)
        rf += us.get("score",0) or 0
        ra += them.get("score",0) or 0
    return {
        "games":len(out),
        "wins":w,
        "win_rate":w/len(out) if out else None,
        "run_diff":rf-ra
    }

def lineup(team):
    out=[]
    for p in team.get("players",{}).values():
        bo=p.get("battingOrder")
        if bo:
            out.append({
                "order":int(bo),
                "id":p.get("person",{}).get("id"),
                "name":p.get("person",{}).get("fullName"),
                "pos":p.get("position",{}).get("abbreviation")
            })
    return sorted(out,key=lambda x:x["order"])

def bullpen(team, feed):
    ids=team.get("pitchers",[])
    total=0
    for pid in ids[1:]:
        p=team.get("players",{}).get(f"ID{pid}",{})
        st=p.get("stats",{}).get("pitching",{})
        total += st.get("numberOfPitches",0) or 0
    return {"listed_pitchers":len(ids),"relief_pitches_current_box":total}

def action():
    params={
        "bookIds":BOOK_IDS,
        "date":TODAY_ISO
    }

    endpoints=[
        ("ACTION_V2",
         "https://api.actionnetwork.com/web/v2/scoreboard/mlb"),
        ("ACTION_V1",
         "https://api.actionnetwork.com/web/v1/scoreboard/mlb"),
    ]

    failures=[]

    for label,url in endpoints:
        try:
            data=GET(url, params, label=label)

            games=action_games(data)

            print(
                f"[LIVE] {label}: {len(games)} EVENTS RECOVERED",
                flush=True
            )

            return data

        except Exception as e:
            failures.append(f"{label}:{type(e).__name__}")

    print(
        "[LIVE] MARKET SOURCE UNRESOLVED: "
        + ", ".join(failures),
        flush=True
    )

    return {"games":[]}

def action_games(raw):
    # tolerate v1/v2 response shapes
    if isinstance(raw,list): return raw
    for k in ("games","events","data"):
        v=raw.get(k) if isinstance(raw,dict) else None
        if isinstance(v,list): return v
        if isinstance(v,dict):
            for kk in ("games","events"):
                if isinstance(v.get(kk),list): return v[kk]
    return []

def team_name(x):
    if isinstance(x,str): return x
    if isinstance(x,dict):
        return x.get("full_name") or x.get("display_name") or x.get("name")
    return None

def extract_market(g):
    away=team_name(g.get("away_team") or g.get("away"))
    home=team_name(g.get("home_team") or g.get("home"))
    books=[]

    # common Action Network shapes
    candidates=[]
    for k in ("odds","books","bookmakers"):
        if isinstance(g.get(k),list): candidates += g[k]

    markets=g.get("markets")
    if isinstance(markets,dict):
        for v in markets.values():
            if isinstance(v,list): candidates += v

    # recursive fallback
    def walk(x):
        if isinstance(x,dict):
            keys=set(x)
            if ("book_id" in keys or "bookId" in keys) and any(
                z in keys for z in ("moneyline","ml","away_moneyline","home_moneyline")
            ):
                candidates.append(x)
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)

    walk(g)

    seen=set()
    for b in candidates:
        if not isinstance(b,dict): continue
        bid=b.get("book_id",b.get("bookId",b.get("id")))
        if bid in seen: continue

        aml=b.get("away_moneyline")
        hml=b.get("home_moneyline")

        if aml is None or hml is None:
            ml=b.get("moneyline") or b.get("ml")
            if isinstance(ml,dict):
                aml=ml.get("away")
                hml=ml.get("home")

        if aml is None or hml is None:
            continue

        pa,pb=novig(american_implied(aml),american_implied(hml))
        books.append({
            "book_id":bid,
            "book_name":b.get("book_name") or b.get("bookName"),
            "away_ml":aml,
            "home_ml":hml,
            "away_no_vig":pa,
            "home_no_vig":pb,
            "num_bets":b.get("num_bets") or g.get("num_bets")
        })
        seen.add(bid)

    return away,home,books

def match_action(raw,away,home):
    for g in action_games(raw):
        a,h,b=extract_market(g)
        if a and h and a.lower()==away.lower() and h.lower()==home.lower():
            return b,g
    return [],None

def pitcher_stats(pid):
    if not pid:return None
    try:
        j=GET(f"{MLB}/v1/people/{pid}/stats",{
            "stats":"season",
            "group":"pitching",
            "season":datetime.now().year
        })
        s=j.get("stats",[{}])[0].get("splits",[])
        return s[0].get("stat") if s else None
    except:
        return None

def model(recent_state,pitch):
    p=.5
    wr=recent_state.get("win_rate")
    if wr is not None:
        p+=(wr-.5)*.25
    try:
        era=float(pitch.get("era"))
        p+=max(-.08,min(.08,(4.20-era)*.015))
    except:
        pass
    return max(.05,min(.95,p))

def analyze(game, action_raw):
    gp=game["gamePk"]
    f=mlb_feed(gp)
    gd=f["gameData"]
    box=f["liveData"]["boxscore"]["teams"]

    away_obj=gd["teams"]["away"]
    home_obj=gd["teams"]["home"]
    away,home=away_obj["name"],home_obj["name"]

    ap=gd.get("probablePitchers",{}).get("away")
    hp=gd.get("probablePitchers",{}).get("home")

    al=lineup(box["away"])
    hl=lineup(box["home"])

    ar=recent(away_obj["id"])
    hr=recent(home_obj["id"])

    aps=pitcher_stats(ap.get("id") if ap else None)
    hps=pitcher_stats(hp.get("id") if hp else None)

    books,action_game=match_action(action_raw,away,home)

    market_a=statistics.mean([x["away_no_vig"] for x in books]) if books else None
    market_h=statistics.mean([x["home_no_vig"] for x in books]) if books else None

    ma=model(ar,aps)
    mh=model(hr,hps)
    z=ma+mh
    ma,mh=ma/z,mh/z

    contradictions=[]

    if market_a is not None:
        if abs(ma-market_a)>.12:
            contradictions.append("AWAY_MODEL_MARKET_DIVERGENCE")
        if abs(mh-market_h)>.12:
            contradictions.append("HOME_MODEL_MARKET_DIVERGENCE")

    if ar["games"]>=5 and hr["games"]>=5:
        if ar["win_rate"]>.70 and hr["win_rate"]>.70:
            contradictions.append("BOTH_SIDES_RECENTLY_STRONG")

    gates={
        "time":bool(gd.get("datetime",{}).get("dateTime")),
        "continuity":ar["games"]>=5 and hr["games"]>=5,
        "alignment":len(contradictions)==0,
        "genesis":True,
        "boundary":bool(ap and hp),
        "reference":bool(gp and away_obj["id"] and home_obj["id"]),
        "causality":bool(aps and hps),
        "coherence":len(contradictions)==0,

        "away_lineup_complete":len(al)>=9,
        "home_lineup_complete":len(hl)>=9,
        "multi_book_market":len(books)>=2,
        "market_consensus":market_a is not None and market_h is not None,
    }

    totality=math.prod(int(bool(v)) for v in gates.values())

    edge_a=(ma-market_a) if market_a is not None else None
    edge_h=(mh-market_h) if market_h is not None else None

    best=None
    if edge_a is not None:
        best=("AWAY",edge_a) if edge_a>=edge_h else ("HOME",edge_h)

    decision="HOLD"
    if totality==1:
        decision="EXECUTE" if best and best[1]>=.07 else "REJECT"

    state={
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "gamePk":gp,
        "event":f"{away} @ {home}",
        "status":gd.get("status",{}).get("detailedState"),
        "start":gd.get("datetime",{}).get("dateTime"),
        "venue":gd.get("venue",{}).get("name"),

        "probable_pitchers":{"away":ap,"home":hp},
        "lineups":{"away":al,"home":hl},
        "recent":{"away":ar,"home":hr},
        "pitching":{"away":aps,"home":hps},

        "market":{
            "books":books,
            "book_count":len(books),
            "away_consensus":market_a,
            "home_consensus":market_h
        },

        "model":{
            "away":ma,
            "home":mh
        },

        "edge":{
            "away":edge_a,
            "home":edge_h
        },

        "contradictions":contradictions,
        "gates":gates,
        "totality_product":totality,
        "decision":decision,
    }

    state["state_sha256"]=H(state)
    return state

print("="*78)
print("SUPREME COMPUTATION — LIVE TOTALITY COLLAPSE")
print("DATE:",TODAY_ISO)
print("="*78)

sched=mlb_schedule()
act=action()

games=[
    g
    for d in sched.get("dates",[])
    for g in d.get("games",[])
]

results=[]

for g in games:
    try:
        r=analyze(g,act)
        results.append(r)

        print()
        print(r["event"])
        print("STATUS:",r["status"])
        print("BOOKS:",r["market"]["book_count"])
        print("TOTALITY:",r["totality_product"])

        failed=[k for k,v in r["gates"].items() if not v]
        print("FAILED:",", ".join(failed) if failed else "NONE")

        print("CONTRADICTIONS:",r["contradictions"] or "NONE")

        if r["edge"]["away"] is not None:
            print("EDGE AWAY:",f'{r["edge"]["away"]:+.2%}')
            print("EDGE HOME:",f'{r["edge"]["home"]:+.2%}')

        print("DECISION:",r["decision"])
        print("SHA256:",r["state_sha256"])

    except Exception as e:
        print()
        print("EVENT FAILURE:",g.get("gamePk"),repr(e))

receipt={
    "architecture":"SUPREME_COMPUTATION_LIVE_TOTALITY_V2",
    "generated_utc":datetime.now(timezone.utc).isoformat(),
    "date":TODAY_ISO,
    "event_count":len(results),
    "execute":sum(x["decision"]=="EXECUTE" for x in results),
    "hold":sum(x["decision"]=="HOLD" for x in results),
    "reject":sum(x["decision"]=="REJECT" for x in results),
    "results":results,
}

receipt["receipt_sha256"]=H(receipt)

outdir=Path("sc-evidence/sports")/TODAY_ISO
outdir.mkdir(parents=True,exist_ok=True)
outfile=outdir/"sc-live-totality-v2.json"
outfile.write_text(json.dumps(receipt,indent=2,default=str))

print()
print("="*78)
print("FINAL STATE")
print("EVENTS:",receipt["event_count"])
print("EXECUTE:",receipt["execute"])
print("HOLD:",receipt["hold"])
print("REJECT:",receipt["reject"])
print("RECEIPT:",outfile.resolve())
print("RECEIPT SHA256:",receipt["receipt_sha256"])
print("="*78)
