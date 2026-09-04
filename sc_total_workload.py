import os, json, hashlib, datetime, urllib.request
import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
QUESTION = "Identify the highest-value immediately actionable improvement in this AWS environment using the available evidence. Do not execute destructive changes."

print("\n🧠 SUPREME COMPUTATION — TOTAL WORKLOAD")

# 1. LIVE WORLD EVIDENCE
url = "https://api.github.com/repos/qiskit/qiskit"
req = urllib.request.Request(url, headers={"User-Agent": "SCQOS"})
with urllib.request.urlopen(req, timeout=20) as r:
    public = json.loads(r.read())

# 2. LIVE AWS STATE
session = boto3.Session(region_name=REGION)
sts = session.client("sts")
lam = session.client("lambda")
identity = sts.get_caller_identity()
functions = lam.list_functions().get("Functions", [])

state = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "aws_account": identity["Account"],
    "region": REGION,
    "lambda_functions": [
        {
            "name": f["FunctionName"],
            "runtime": f.get("Runtime"),
            "modified": f.get("LastModified")
        }
        for f in functions
    ],
    "public_evidence": {
        "source": url,
        "repository": public["full_name"],
        "stars": public["stargazers_count"],
        "forks": public["forks_count"],
        "updated_at": public["updated_at"]
    }
}

canonical = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
state_sha = hashlib.sha256(canonical).hexdigest()

# 3. BEDROCK REASONS OVER THE WHOLE STATE
bedrock = session.client("bedrock-runtime")

prompt = f"""
You are operating inside an SCQOS governed decision workload.

GOAL:
{QUESTION}

EVIDENCE:
{json.dumps(state, indent=2)}

Return ONLY JSON:
{{
 "problem": "...",
 "best_action": "...",
 "why": "...",
 "evidence": ["..."],
 "missing_evidence": ["..."],
 "decision": "PERMIT or HOLD or REJECT"
}}

Rules:
Never claim evidence not supplied.
If evidence is insufficient for an external change, HOLD.
Choose the smallest action producing the greatest measurable value.
"""

response = bedrock.converse(
    modelId="amazon.nova-lite-v1:0",
    messages=[{"role":"user","content":[{"text":prompt}]}],
    inferenceConfig={"maxTokens":1200,"temperature":0}
)

analysis = response["output"]["message"]["content"][0]["text"]

try:
    decision = json.loads(analysis)
except Exception:
    decision = {"decision":"HOLD","raw_model_output":analysis}

# 4. GOVERNANCE BOUNDARY
verdict = str(decision.get("decision","HOLD")).upper()
if verdict not in {"PERMIT","HOLD","REJECT"}:
    verdict = "HOLD"

# 5. DURABLE RECEIPT
receipt = {
    "schema": "sc-total-workload-v1",
    "state_sha256": state_sha,
    "state": state,
    "analysis": decision,
    "governance_decision": verdict,
    "external_change_executed": False
}

unsigned = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
receipt["receipt_sha256"] = hashlib.sha256(unsigned).hexdigest()

path = os.path.expanduser("~/sc-total-workload-receipt.json")
with open(path, "w") as f:
    json.dump(receipt, f, indent=2)

print("🌎 LIVE PUBLIC DATA: VERIFIED")
print("☁️ LIVE AWS STATE: VERIFIED")
print("🔐 STATE SHA256:", state_sha)
print("\n🤖 GOVERNED ANALYSIS")
print(json.dumps(decision, indent=2))
print("\n🛡️ FINAL DECISION:", verdict)
print("⚡ EXTERNAL CHANGE EXECUTED: NO")
print("🧾 RECEIPT:", path)
print("🔒 RECEIPT SHA256:", receipt["receipt_sha256"])
print("\n✅ TOTAL LOOP COMPLETE")
print("🌎 EVIDENCE → 🧠 REASON → 🛡️ GOVERN → ⚡ DECIDE → ✅ VERIFY → 🧾 RECEIPT")
