import json
import hashlib
import uuid
import os
import datetime
import urllib.request
import urllib.error
import boto3

from scqos_supreme_stack import SCQOSSupremeCoherenceStack, get_secret_key

UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC)
TODAY = NOW.date()
START = TODAY - datetime.timedelta(days=365)

USASPENDING = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

SEARCHES = [
    "artificial intelligence",
    "AI governance",
    "cybersecurity artificial intelligence",
    "zero trust",
    "machine learning cybersecurity",
    "cloud security",
    "identity access management",
    "autonomous systems cybersecurity",
]

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Description",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Start Date",
    "End Date",
]

print("\n🔥 SUPREME COMPUTATION — LIVE ECONOMIC DISCOVERY")
print("🌎 LIVE MONEY → 🧠 COLLAPSE → 💰 OFFER → 🛡️ SCQOS → 🧾 RECEIPT\n")

# ============================================================
# 1. PULL REAL, CURRENT FEDERAL SPENDING
# ============================================================

def post_json(url, payload, timeout=45):
    raw = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SCQOS-Economic-Discovery/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return json.loads(body), hashlib.sha256(body).hexdigest()

all_awards = {}
query_receipts = []

for term in SEARCHES:
    payload = {
        "filters": {
            "keywords": [term],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{
                "start_date": START.isoformat(),
                "end_date": TODAY.isoformat(),
            }],
        },
        "fields": FIELDS,
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    try:
        result, body_sha = post_json(USASPENDING, payload)

        rows = result.get("results", [])

        query_receipts.append({
            "query": term,
            "results": len(rows),
            "response_sha256": body_sha,
        })

        for row in rows:
            award_id = str(row.get("Award ID") or "")
            if not award_id:
                award_id = hashlib.sha256(
                    json.dumps(row, sort_keys=True).encode()
                ).hexdigest()

            existing = all_awards.get(award_id)

            amount = row.get("Award Amount") or 0
            try:
                amount = float(amount)
            except:
                amount = 0

            normalized = {
                "award_id": award_id,
                "recipient": row.get("Recipient Name"),
                "award_amount": amount,
                "description": row.get("Description"),
                "awarding_agency": row.get("Awarding Agency"),
                "awarding_subagency": row.get("Awarding Sub Agency"),
                "start_date": row.get("Start Date"),
                "end_date": row.get("End Date"),
                "matched_queries": [term],
            }

            if existing:
                if term not in existing["matched_queries"]:
                    existing["matched_queries"].append(term)
            else:
                all_awards[award_id] = normalized

    except Exception as e:
        query_receipts.append({
            "query": term,
            "error": f"{type(e).__name__}: {e}",
        })

awards = list(all_awards.values())
awards.sort(key=lambda x: x["award_amount"], reverse=True)

if not awards:
    raise SystemExit(
        "HOLD: USAspending returned no usable award evidence. "
        "No economic conclusion will be invented."
    )

sampled_dollars = sum(x["award_amount"] for x in awards)

print("✅ LIVE FEDERAL AWARDS:", len(awards))
print("💰 SAMPLED AWARD VALUE: ${:,.2f}".format(sampled_dollars))

# ============================================================
# 2. COMPRESS THE LIVE MARKET INTO EVIDENCE
# ============================================================

agency_totals = {}
recipient_totals = {}
query_totals = {}

for a in awards:
    agency = a["awarding_agency"] or "Unknown"
    recipient = a["recipient"] or "Unknown"

    agency_totals[agency] = agency_totals.get(agency, 0) + a["award_amount"]
    recipient_totals[recipient] = recipient_totals.get(recipient, 0) + a["award_amount"]

    for q in a["matched_queries"]:
        query_totals[q] = query_totals.get(q, 0) + a["award_amount"]

top_agencies = sorted(
    agency_totals.items(),
    key=lambda x: x[1],
    reverse=True
)[:10]

top_recipients = sorted(
    recipient_totals.items(),
    key=lambda x: x[1],
    reverse=True
)[:10]

top_themes = sorted(
    query_totals.items(),
    key=lambda x: x[1],
    reverse=True
)

market = {
    "retrieved_utc": NOW.isoformat(),
    "window": {
        "start": START.isoformat(),
        "end": TODAY.isoformat(),
    },
    "source": USASPENDING,
    "queries": query_receipts,
    "unique_awards": len(awards),
    "sampled_award_value_usd": round(sampled_dollars, 2),
    "top_agencies": [
        {"agency": k, "sampled_value_usd": round(v, 2)}
        for k, v in top_agencies
    ],
    "top_recipients": [
        {"recipient": k, "sampled_value_usd": round(v, 2)}
        for k, v in top_recipients
    ],
    "themes": [
        {"theme": k, "sampled_value_usd": round(v, 2)}
        for k, v in top_themes
    ],
    "largest_awards": awards[:25],
    "public_market_context": [
        {
            "source": "OWASP GenAI Security Project",
            "fact":
                "OWASP maintains a 2026 Top 10 specifically for "
                "security risks in autonomous and agentic AI applications."
        },
        {
            "source": "FinOps Foundation State of FinOps 2026",
            "fact":
                "98% of respondents report managing AI spend and "
                "FinOps for AI is a top forward-looking priority."
        }
    ]
}

market_bytes = json.dumps(
    market,
    sort_keys=True,
    separators=(",", ":")
).encode()

market_sha = hashlib.sha256(market_bytes).hexdigest()

# ============================================================
# 3. BEDROCK MUST COLLAPSE EVERYTHING INTO ONE PROBLEM + OFFER
# ============================================================

session = boto3.Session()
bedrock = session.client("bedrock")
runtime = session.client("bedrock-runtime")

models = bedrock.list_foundation_models()["modelSummaries"]

preferred = [
    "amazon.nova-lite",
    "amazon.nova-micro",
    "anthropic.claude",
    "meta.llama",
    "mistral",
]

model_ids = [m.get("modelId", "") for m in models]

model_ids.sort(
    key=lambda x: next(
        (i for i, p in enumerate(preferred) if p in x.lower()),
        999
    )
)

prompt = f"""
You are the economic-discovery intelligence inside Supreme Computation.

The objective has already been fixed:

Find the SINGLE highest-value real-world economic problem supported by
the live public evidence where SCQOS's defining capability has maximum
commercial leverage:

An AI/software action must remain authorized from evidence and intent,
through execution, confirmed consequence, and durable receipt.

Do NOT fragment cybersecurity, cloud cost, AI governance, authorization,
operational reliability, or auditability into separate problems.
Collapse them to the deepest common economic failure.

LIVE PUBLIC MARKET EVIDENCE:
{json.dumps(market, indent=2)}

REQUIREMENTS:

1. Use the actual public-dollar evidence supplied.
2. Do NOT claim the sampled award total equals the whole market.
3. Do NOT invent savings or revenue.
4. Identify ONE total economic problem only.
5. Identify ONE buyer class.
6. Identify ONE paid pilot that can be sold immediately.
7. The pilot must use SCQOS's actual differentiator:
   authorization must survive through consequence, not merely decision time.
8. Explain why existing point solutions leave the deeper boundary unresolved.
9. State a concrete measurable customer success condition.
10. Produce a pilot price RANGE only if defensible as a commercial proposal,
    clearly labeling it as proposed pricing rather than observed market pricing.
11. No generic cloud optimization.
12. No package vulnerability scanning.
13. No self-analysis of our own AWS environment.
14. No speculation that this is globally unprecedented.
15. Return JSON only.

Schema:

{{
  "total_problem": "...",
  "economic_failure": "...",
  "live_dollar_signal": {{
    "sampled_award_value_usd": 0,
    "strongest_theme": "...",
    "top_buyer_signals": ["..."]
  }},
  "buyer": "...",
  "supreme_solution": "...",
  "why_point_solutions_fail": "...",
  "pilot": {{
    "name": "...",
    "customer_workflow": "...",
    "what_scqos_governs": "...",
    "success_condition": "...",
    "proposed_price_range_usd": ["...", "..."]
  }},
  "immediate_sales_statement": "...",
  "decision": "PERMIT|HOLD|REJECT"
}}
"""

answer = None
model_used = None
last_error = None

for model_id in model_ids[:30]:
    try:
        response = runtime.converse(
            modelId=model_id,
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 2200,
            }
        )

        text = "".join(
            b.get("text", "")
            for b in response["output"]["message"]["content"]
            if "text" in b
        ).strip()

        text = text.replace("```json", "").replace("```", "").strip()
        candidate = json.loads(text)

        required = [
            "total_problem",
            "economic_failure",
            "buyer",
            "supreme_solution",
            "pilot",
            "decision",
        ]

        if all(candidate.get(k) for k in required):
            answer = candidate
            model_used = model_id
            break

    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"

if answer is None:
    raise SystemExit(
        "HOLD: No valid Bedrock economic conclusion. "
        f"Last error: {last_error}"
    )

# ============================================================
# 4. DETERMINISTIC EVIDENCE / AUTHORITY CHECK
# ============================================================

decision = str(answer.get("decision", "HOLD")).upper()

if decision not in {"PERMIT", "HOLD", "REJECT"}:
    decision = "HOLD"

live_money_proven = sampled_dollars > 0
buyer_proven = len(top_agencies) > 0
problem_present = bool(answer.get("total_problem"))
pilot_present = bool(answer.get("pilot", {}).get("success_condition"))

if not (
    live_money_proven
    and buyer_proven
    and problem_present
    and pilot_present
):
    decision = "HOLD"

# ============================================================
# 5. RUN THE ACTUAL SCQOS NINE-GATE STACK
# ============================================================

print("\n🛡️ RUNNING ACTUAL SCQOS NINE-GATE STACK")

transaction_id = str(uuid.uuid4())

stack = SCQOSSupremeCoherenceStack(
    secret_key=get_secret_key(required=False),
    node_id="economic-discovery-node",
    session_id=f"economic-discovery-{transaction_id}",
)

scqos_cleared = stack.boot_all_modules()

if not scqos_cleared:
    decision = "HOLD"

# ============================================================
# 6. FINAL COMMERCIAL RECEIPT
# ============================================================

receipt = {
    "schema": "sc-economic-discovery-v1",
    "transaction_id": transaction_id,
    "timestamp_utc": NOW.isoformat(),
    "market_sha256": market_sha,
    "market": market,
    "bedrock_model": model_used,
    "economic_conclusion": answer,
    "proof": {
        "live_public_money_present": live_money_proven,
        "live_buyer_signal_present": buyer_proven,
        "single_problem_present": problem_present,
        "pilot_success_condition_present": pilot_present,
        "scqos_nine_gate_coherence": scqos_cleared,
    },
    "final_decision": decision,
}

unsigned = json.dumps(
    receipt,
    sort_keys=True,
    separators=(",", ":")
).encode()

receipt["receipt_sha256"] = hashlib.sha256(unsigned).hexdigest()

path = os.path.expanduser(
    "~/sc-final-economic-discovery-receipt.json"
)

with open(path, "w") as f:
    json.dump(receipt, f, indent=2)

# ============================================================
# 7. PRINT ONLY THE END RESULT THAT MATTERS
# ============================================================

print("\n======================================================")
print("💰 LIVE PUBLIC DOLLAR SIGNAL")
print("${:,.2f} sampled across {} unique awards".format(
    sampled_dollars,
    len(awards)
))

print("\n🌎 ONE TOTAL REAL-WORLD PROBLEM")
print(answer.get("total_problem"))

print("\n💸 ECONOMIC FAILURE")
print(answer.get("economic_failure"))

print("\n🎯 BUYER")
print(answer.get("buyer"))

print("\n🧠 SUPREME SOLUTION")
print(answer.get("supreme_solution"))

print("\n🔥 PAID PILOT")
pilot = answer.get("pilot", {})
print("Name:", pilot.get("name"))
print("Workflow:", pilot.get("customer_workflow"))
print("SCQOS governs:", pilot.get("what_scqos_governs"))
print("Success:", pilot.get("success_condition"))
print("Proposed price:", pilot.get("proposed_price_range_usd"))

print("\n📣 IMMEDIATE SALES STATEMENT")
print(answer.get("immediate_sales_statement"))

print("\n🛡️ FINAL SCQOS DECISION:", decision)
print("🧾 RECEIPT:", path)
print("🔐 RECEIPT SHA256:", receipt["receipt_sha256"])

print("\n✅ FINAL ECONOMIC DISCOVERY COMPLETE")
print(
    "🌎 LIVE PUBLIC MONEY → 🧠 ONE PROBLEM → 💰 ONE OFFER → "
    "🛡️ SCQOS → 🧾 PROOF"
)
print("======================================================")
