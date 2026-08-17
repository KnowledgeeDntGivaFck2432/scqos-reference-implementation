import os
import sys
import json
import uuid
import hashlib
import datetime
import urllib.request
import urllib.error
import importlib.metadata as md
import boto3

from scqos_supreme_stack import (
    SCQOSSupremeCoherenceStack,
    get_secret_key,
)

UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC)

print("\n🔥 SUPREME COMPUTATION — ECONOMIC ACTION SETTLEMENT")
print("🌎 LIVE RISK + 💰 LIVE ECONOMICS + 🧠 AI + 🛡️ REAL SCQOS + ✅ CONSEQUENCE + 🧾 PROOF\n")

# ============================================================
# 1. LIVE PUBLIC SECURITY REALITY
# ============================================================

def get_json(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SCQOS-Economic-Settlement/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()

print("🌎 Pulling live CISA exploited-vulnerability evidence...")

CISA_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)

cisa, cisa_sha = get_json(CISA_URL)
kev = cisa.get("vulnerabilities", [])

print("✅ CISA KEV entries:", len(kev))
print("🔐 CISA SHA256:", cisa_sha)

# ============================================================
# 2. LIVE SOFTWARE SUPPLY-CHAIN STATE
# ============================================================

interesting = [
    "boto3",
    "botocore",
    "qiskit",
    "qiskit-ibm-runtime",
    "amazon-braket-sdk",
    "requests",
    "urllib3",
    "cryptography",
]

packages = []

for name in interesting:
    try:
        version = md.version(name)
        packages.append({
            "name": name,
            "version": version,
            "ecosystem": "PyPI"
        })
    except md.PackageNotFoundError:
        pass

print("📦 Installed packages checked:", len(packages))

# ============================================================
# 3. QUERY LIVE OSV DATABASE FOR ACTUAL KNOWN VULNERABILITIES
# ============================================================

OSV_URL = "https://api.osv.dev/v1/querybatch"

payload = {
    "queries": [
        {
            "package": {
                "name": p["name"],
                "ecosystem": "PyPI"
            },
            "version": p["version"]
        }
        for p in packages
    ]
}

encoded = json.dumps(payload).encode()

req = urllib.request.Request(
    OSV_URL,
    data=encoded,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "SCQOS-Economic-Settlement/1.0"
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=30) as r:
    osv_raw = r.read()

osv_sha = hashlib.sha256(osv_raw).hexdigest()
osv = json.loads(osv_raw)

vulnerabilities = []

for pkg, result in zip(packages, osv.get("results", [])):
    for vuln in result.get("vulns", []) or []:
        vulnerabilities.append({
            "package": pkg["name"],
            "version": pkg["version"],
            "osv_id": vuln.get("id"),
            "modified": vuln.get("modified")
        })

print("🛡️ OSV vulnerabilities found:", len(vulnerabilities))
print("🔐 OSV SHA256:", osv_sha)

# ============================================================
# 4. CROSS-REFERENCE CISA KNOWN EXPLOITED CVEs
# ============================================================

kev_ids = {
    x.get("cveID")
    for x in kev
    if x.get("cveID")
}

kev_matches = []

for v in vulnerabilities:
    osv_id = str(v.get("osv_id", ""))
    if osv_id in kev_ids:
        kev_matches.append(v)

print("🚨 Known-exploited matches:", len(kev_matches))

# ============================================================
# 5. LIVE ECONOMIC REALITY FROM AWS
# ============================================================

session = boto3.Session()
region = session.region_name or "us-east-1"

sts = session.client("sts")
ce = session.client("ce", region_name="us-east-1")
bedrock = session.client("bedrock")
runtime = session.client("bedrock-runtime")

identity = sts.get_caller_identity()

start = (NOW.date() - datetime.timedelta(days=30)).isoformat()
end = NOW.date().isoformat()

aws_cost = None
cost_error = None

try:
    cost_result = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"]
    )

    aws_cost = round(
        sum(
            float(x["Total"]["UnblendedCost"]["Amount"])
            for x in cost_result["ResultsByTime"]
        ),
        4
    )
except Exception as e:
    cost_error = str(e)

print("💰 AWS 30-day spend:",
      f"${aws_cost}" if aws_cost is not None else "UNAVAILABLE")

# ============================================================
# 6. BUILD ONE TOTAL ECONOMIC TRANSACTION
# ============================================================

transaction_id = str(uuid.uuid4())

state = {
    "transaction_id": transaction_id,
    "timestamp_utc": NOW.isoformat(),
    "objective":
        "Determine whether an AI-proposed software action is justified, "
        "authorized, economically rational, and safe enough to cross into execution.",
    "aws": {
        "account": identity["Account"],
        "region": region,
        "cost_30d_usd": aws_cost,
        "cost_error": cost_error
    },
    "public_evidence": {
        "cisa_kev_count": len(kev),
        "cisa_sha256": cisa_sha,
        "osv_sha256": osv_sha,
        "packages_checked": packages,
        "known_vulnerabilities": vulnerabilities,
        "known_exploited_matches": kev_matches
    }
}

state_bytes = json.dumps(
    state,
    sort_keys=True,
    separators=(",", ":")
).encode()

state_sha = hashlib.sha256(state_bytes).hexdigest()

# ============================================================
# 7. BEDROCK PROPOSES — BUT DOES NOT AUTHORIZE
# ============================================================

models = bedrock.list_foundation_models()["modelSummaries"]

preferred = [
    "amazon.nova-lite",
    "amazon.nova-micro",
    "anthropic.claude",
    "meta.llama",
    "mistral"
]

model_ids = [x.get("modelId", "") for x in models]

model_ids.sort(
    key=lambda m: next(
        (i for i, p in enumerate(preferred) if p in m.lower()),
        999
    )
)

prompt = f"""
You are the PROPOSAL layer of a governed economic transaction.

You have ZERO execution authority.

QUESTION:
What single software action has the highest defensible economic value
given the supplied live evidence?

LIVE STATE:
{json.dumps(state, indent=2)}

RULES:
1. Do not invent vulnerabilities.
2. Do not invent financial savings.
3. Known exploited vulnerabilities outrank ordinary vulnerabilities.
4. Security risk, downtime risk, AI/cloud cost, reversibility,
   and operational continuity must be considered simultaneously.
5. If no change is justified, say HOLD.
6. Return ONE action only.
7. Define a measurable post-condition proving whether the action worked.

Return JSON only:

{{
  "problem": "...",
  "proposed_action": "...",
  "target": "...",
  "economic_value": "...",
  "security_evidence": ["..."],
  "economic_evidence": ["..."],
  "risk_if_ignored": "...",
  "risk_if_executed": "...",
  "reversible": true,
  "verification_predicate": "...",
  "decision": "PERMIT|HOLD|REJECT"
}}
"""

proposal = None
model_used = None
last_error = None

for model_id in model_ids[:25]:
    try:
        response = runtime.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 1500
            }
        )

        text = "".join(
            block.get("text", "")
            for block in response["output"]["message"]["content"]
            if "text" in block
        ).strip()

        text = text.replace("```json", "").replace("```", "").strip()

        proposal = json.loads(text)
        model_used = model_id
        break

    except Exception as e:
        last_error = str(e)

if proposal is None:
    proposal = {
        "problem": "AI proposal layer unavailable",
        "proposed_action": "NONE",
        "target": "NONE",
        "economic_value": "UNKNOWN",
        "security_evidence": [],
        "economic_evidence": [],
        "risk_if_ignored": "UNKNOWN",
        "risk_if_executed": "UNKNOWN",
        "reversible": False,
        "verification_predicate": "NONE",
        "decision": "HOLD",
        "error": last_error
    }

# ============================================================
# 8. DETERMINISTIC AUTHORITY GATE
# ============================================================

security_proof = bool(
    vulnerabilities or kev_matches
)

economic_proof = (
    aws_cost is not None
)

verification_defined = bool(
    str(proposal.get("verification_predicate", "")).strip()
    and proposal.get("verification_predicate") != "NONE"
)

reversible = proposal.get("reversible") is True

model_decision = str(
    proposal.get("decision", "HOLD")
).upper()

# AI NEVER grants itself authority.
# External execution is only admissible if evidence,
# economics, reversibility and verification all exist.
admissible = (
    model_decision == "PERMIT"
    and security_proof
    and economic_proof
    and reversible
    and verification_defined
)

authority_decision = "PERMIT" if admissible else "HOLD"

# ============================================================
# 9. RUN THE ACTUAL SCQOS NINE-GATE STACK
# ============================================================

print("\n🛡️ RUNNING REAL SCQOS NINE-GATE COHERENCE STACK")

stack = SCQOSSupremeCoherenceStack(
    secret_key=get_secret_key(required=False),
    node_id="economic-settlement-node",
    session_id=f"economic-{transaction_id}"
)

scqos_cleared = stack.boot_all_modules()

if not scqos_cleared:
    authority_decision = "HOLD"

print("🛡️ SCQOS:", "CLEARED" if scqos_cleared else "BLOCKED")

# ============================================================
# 10. CONSEQUENCE BOUNDARY
# ============================================================

# This prototype deliberately DOES NOT silently modify production.
#
# The economic consequence being authorized here is the transaction
# itself becoming eligible for execution.
#
# Once PERMIT exists, an enterprise executor can bind this exact
# receipt to a real deployment / purchase / API / infrastructure action.

external_change_executed = False

settlement = {
    "transaction_id": transaction_id,
    "state_sha256": state_sha,
    "model": model_used,
    "proposal": proposal,
    "proof": {
        "live_public_security_evidence": True,
        "security_signal_present": security_proof,
        "economic_state_present": economic_proof,
        "reversible": reversible,
        "verification_predicate_present": verification_defined,
        "scqos_nine_gate_coherence": scqos_cleared
    },
    "authority_decision": authority_decision,
    "external_change_executed": external_change_executed
}

# ============================================================
# 11. DURABLE SETTLEMENT RECEIPT
# ============================================================

receipt_bytes = json.dumps(
    settlement,
    sort_keys=True,
    separators=(",", ":")
).encode()

settlement["receipt_sha256"] = hashlib.sha256(
    receipt_bytes
).hexdigest()

receipt_path = os.path.expanduser(
    "~/sc-economic-action-settlement.json"
)

with open(receipt_path, "w") as f:
    json.dump(settlement, f, indent=2)

# ============================================================
# 12. CUSTOMER-FACING ANSWER
# ============================================================

print("\n====================================================")
print("💰 ECONOMIC PROBLEM")
print(proposal.get("problem"))

print("\n🎯 SINGLE HIGHEST-VALUE ACTION")
print(proposal.get("proposed_action"))

print("\n📍 TARGET")
print(proposal.get("target"))

print("\n💵 ECONOMIC VALUE")
print(proposal.get("economic_value"))

print("\n🚨 RISK IF IGNORED")
print(proposal.get("risk_if_ignored"))

print("\n⚠️ RISK IF EXECUTED")
print(proposal.get("risk_if_executed"))

print("\n✅ PROOF OF SUCCESS")
print(proposal.get("verification_predicate"))

print("\n🛡️ FINAL AUTHORITY:", authority_decision)
print("⚡ EXTERNAL CHANGE EXECUTED:", external_change_executed)

print("\n🧾 SETTLEMENT RECEIPT:", receipt_path)
print("🔐 RECEIPT SHA256:", settlement["receipt_sha256"])

print("\n🔥 FINAL RESULT")
print(
    "LIVE PUBLIC RISK → LIVE ECONOMIC STATE → AI PROPOSAL → "
    "SCQOS NINE-GATE PROOF → AUTHORITY → CONSEQUENCE BOUNDARY → RECEIPT"
)
print("====================================================")
