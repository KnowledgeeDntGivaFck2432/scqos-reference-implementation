import boto3, json, hashlib, os, datetime, uuid
from datetime import timezone, timedelta

REGION = boto3.Session().region_name or "us-east-1"
OUT = os.path.expanduser("~/sc-value-settlement-receipt.json")

print("\n🧠 SC VALUE SETTLEMENT GOVERNOR")
print("🌎 REALITY → 💰 VALUE → 🛡️ AUTHORITY → 🧠 COMPETE → ⚡ AUTHORIZE → ✅ SETTLE → 🧾 RECEIPT\n")

session = boto3.Session(region_name=REGION)
sts = session.client("sts")
lam = session.client("lambda")
cw = session.client("cloudwatch")
ce = session.client("ce", region_name="us-east-1")
bedrock_ctl = session.client("bedrock")
bedrock_rt = session.client("bedrock-runtime")

now = datetime.datetime.now(timezone.utc)
account = sts.get_caller_identity()
functions = lam.list_functions()["Functions"]

# ─────────────────────────────────────────────
# 1. CAPTURE LIVE CONSEQUENCE SURFACE
# ─────────────────────────────────────────────
def metric(fn, name, stat):
    r = cw.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName=name,
        Dimensions=[{"Name":"FunctionName","Value":fn}],
        StartTime=now-timedelta(days=7),
        EndTime=now,
        Period=604800,
        Statistics=[stat]
    )
    pts = r.get("Datapoints", [])
    return pts[0].get(stat, 0) if pts else 0

surface = []

for f in functions:
    name = f["FunctionName"]

    inv = metric(name, "Invocations", "Sum")
    err = metric(name, "Errors", "Sum")
    dur = metric(name, "Duration", "Average")

    try:
        tags = lam.list_tags(Resource=f["FunctionArn"]).get("Tags", {})
    except:
        tags = {}

    try:
        mappings = lam.list_event_source_mappings(
            FunctionName=name
        ).get("EventSourceMappings", [])
    except:
        mappings = []

    surface.append({
        "function": name,
        "runtime": f.get("Runtime"),
        "memory_mb": f.get("MemorySize"),
        "timeout_s": f.get("Timeout"),
        "last_modified": f.get("LastModified"),
        "invocations_7d": int(inv),
        "errors_7d": int(err),
        "error_rate": round(err/inv, 6) if inv else 0,
        "avg_duration_ms": round(dur, 2),
        "tags": tags,
        "event_source_count": len(mappings)
    })

# ─────────────────────────────────────────────
# 2. CAPTURE REAL ECONOMIC STATE
# ─────────────────────────────────────────────
start = (now.date() - timedelta(days=30)).isoformat()
end = now.date().isoformat()

cost = None
try:
    r = ce.get_cost_and_usage(
        TimePeriod={"Start":start,"End":end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"]
    )
    cost = sum(
        float(x["Total"]["UnblendedCost"]["Amount"])
        for x in r["ResultsByTime"]
    )
except Exception:
    pass

state = {
    "transaction_id": str(uuid.uuid4()),
    "timestamp_utc": now.isoformat(),
    "account": account["Account"],
    "region": REGION,
    "aws_cost_30d_usd": round(cost, 4) if cost is not None else None,
    "consequence_surface": surface
}

state_bytes = json.dumps(
    state, sort_keys=True, separators=(",",":")
).encode()

state_sha = hashlib.sha256(state_bytes).hexdigest()

print("✅ LIVE ENVIRONMENT:", len(surface), "functions")
print("💰 30-DAY AWS COST:", state["aws_cost_30d_usd"])
print("🔐 STATE:", state_sha)

# ─────────────────────────────────────────────
# 3. CREATE COMPETING ACTIONS
#    Intelligence proposes — intelligence does NOT authorize.
# ─────────────────────────────────────────────
models = bedrock_ctl.list_foundation_models()["modelSummaries"]

preferred = [
    "amazon.nova-lite",
    "amazon.nova-micro",
    "anthropic.claude",
    "meta.llama",
    "mistral"
]

ids = [m.get("modelId","") for m in models]
ids.sort(
    key=lambda x: next(
        (i for i,p in enumerate(preferred) if p in x.lower()),
        999
    )
)

prompt = f"""
You are proposing actions, NOT authorizing them.

BUSINESS OBJECTIVE:
Find the single highest-economic-value improvement supported by
this real environment while preserving existing consequences.

LIVE EVIDENCE:
{json.dumps(state, indent=2)}

Generate exactly 3 competing options.

For every option return:
- action
- target
- evidence
- expected_value
- downside
- reversibility
- missing_evidence

Rules:
- Never invent dollar savings.
- Zero usage does not mean unused.
- Prefer measurable reliability, security, or cost value.
- A model recommendation has ZERO execution authority.

Return JSON only:
{{
 "options":[...]
}}
"""

proposal = None
model_used = None

for model in ids[:25]:
    try:
        r = bedrock_rt.converse(
            modelId=model,
            messages=[{
                "role":"user",
                "content":[{"text":prompt}]
            }],
            inferenceConfig={
                "temperature":0,
                "maxTokens":1800
            }
        )

        text = "".join(
            x.get("text","")
            for x in r["output"]["message"]["content"]
            if "text" in x
        ).strip()

        text = text.replace("```json","").replace("```","").strip()
        proposal = json.loads(text)

        if len(proposal.get("options", [])) == 3:
            model_used = model
            break

    except Exception:
        pass

if proposal is None:
    proposal = {"options":[]}

# ─────────────────────────────────────────────
# 4. SC DETERMINISTIC AUTHORITY BOUNDARY
# ─────────────────────────────────────────────
ranked = []

for option in proposal.get("options", []):
    evidence = option.get("evidence", [])
    missing = option.get("missing_evidence", [])
    reversible = str(option.get("reversibility","")).lower()

    evidence_present = bool(evidence)
    uncertainty = bool(missing)
    reversible_ok = any(
        word in reversible
        for word in ["yes","high","reversible","full"]
    )

    # NO production mutation solely because an LLM recommends it.
    authorized = (
        evidence_present
        and not uncertainty
        and reversible_ok
        and False
    )

    ranked.append({
        **option,
        "sc_authorized": authorized,
        "sc_boundary":
            "PERMIT" if authorized else "HOLD"
    })

# Find highest observed reliability anomaly as an objective signal.
anomalies = sorted(
    [
        x for x in surface
        if x["invocations_7d"] > 0
        and x["error_rate"] > 0
    ],
    key=lambda x: x["error_rate"],
    reverse=True
)

objective_signal = anomalies[0] if anomalies else None

# ─────────────────────────────────────────────
# 5. SETTLEMENT CONTRACT
# ─────────────────────────────────────────────
settlement = {
    "before_state_sha256": state_sha,

    "authority": {
        "model_can_propose": True,
        "model_can_authorize": False,
        "model_can_execute": False,
        "production_mutation_authorized": False
    },

    "objective_signal": objective_signal,

    "competing_actions": ranked,

    "required_before_execution": [
        "specific consequence to change",
        "evidence proving necessity",
        "bounded authority",
        "reversible execution plan",
        "expected consequence",
        "verification predicate"
    ],

    "decision": "HOLD",

    "reason":
        "No external consequence may change until one option proves "
        "necessity, authority, reversibility and a measurable "
        "post-condition."
}

# ─────────────────────────────────────────────
# 6. CRYPTOGRAPHIC RECEIPT
# ─────────────────────────────────────────────
receipt = {
    "schema": "sc-value-settlement-v1",
    "transaction": state["transaction_id"],
    "model": model_used,
    "state": state,
    "proposal": proposal,
    "settlement": settlement
}

unsigned = json.dumps(
    receipt, sort_keys=True, separators=(",",":")
).encode()

receipt["receipt_sha256"] = hashlib.sha256(unsigned).hexdigest()

with open(OUT,"w") as f:
    json.dump(receipt,f,indent=2)

# ─────────────────────────────────────────────
# 7. CUSTOMER-FACING RESULT
# ─────────────────────────────────────────────
print("\n🌎 REALITY CAPTURED")
print("💰 ECONOMIC STATE CAPTURED")
print("🧠 3 OPTIONS COMPETED")
print("🛡️ MODEL AUTHORITY: NONE")

if objective_signal:
    print("\n🎯 STRONGEST OBJECTIVE SIGNAL")
    print(
        objective_signal["function"],
        "| error rate:",
        f'{objective_signal["error_rate"]:.1%}'
    )
else:
    print("\n🎯 STRONGEST OBJECTIVE SIGNAL: NONE")

print("\n🏆 COMPETING ACTIONS")

for i,o in enumerate(ranked,1):
    print(f"\n{i}. {o.get('action')}")
    print("   Target:", o.get("target"))
    print("   Value:", o.get("expected_value"))
    print("   Boundary:", o["sc_boundary"])

print("\n🛡️ FINAL AUTHORITY: HOLD")
print("⚡ PRODUCTION MUTATION: NONE")
print("🧾 SETTLEMENT RECEIPT:", OUT)
print("🔐 RECEIPT SHA256:", receipt["receipt_sha256"])

print("\n✅ SC VALUE TRANSACTION COMPLETE")
print(
    "🌎 EVIDENCE → 💰 VALUE → 🧠 COMPETITION → "
    "🛡️ AUTHORITY → ⚡ CONSEQUENCE → ✅ SETTLEMENT → 🧾 PROOF"
)
