#!/usr/bin/env python3
import boto3, json, hashlib, os, sys, datetime, subprocess

REGION = os.getenv("AWS_REGION", "us-east-1")
OUT = os.path.expanduser("~/sc-final-workload-receipt.json")

print("\n🧠 SUPREME COMPUTATION — GOVERNED REAL-WORLD EXECUTION")
print("🌎 EVIDENCE → 🛡️ GOVERN → 🧠 REASON → ⚡ DECIDE → ✅ VERIFY → 🧾 RECEIPT\n")

# ── 1. OBSERVE LIVE REALITY ───────────────────────────────────────────────
sts = boto3.client("sts", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

identity = sts.get_caller_identity()
functions = lam.list_functions()["Functions"]

evidence = []
for f in functions:
    name = f["FunctionName"]
    cfg = lam.get_function_configuration(FunctionName=name)

    evidence.append({
        "function": name,
        "runtime": cfg.get("Runtime"),
        "state": cfg.get("State"),
        "last_update_status": cfg.get("LastUpdateStatus"),
        "modified": cfg.get("LastModified"),
        "memory": cfg.get("MemorySize"),
        "timeout": cfg.get("Timeout")
    })

state = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "aws_account": identity["Account"],
    "region": REGION,
    "functions": evidence
}

canonical = json.dumps(
    state, sort_keys=True, separators=(",", ":")
).encode()

state_sha256 = hashlib.sha256(canonical).hexdigest()

print("✅ LIVE AWS STATE CAPTURED")
print("⚙️ FUNCTIONS:", len(evidence))
print("🔐 STATE SHA256:", state_sha256)

# ── 2. GOVERNED REASONING ────────────────────────────────────────────────
prompt = f"""
You are the reasoning component inside a fail-closed governance system.

Analyze ONLY the supplied evidence.

Goal:
Identify the single highest-value operational action supported by the evidence.

Rules:
1. Never invent missing evidence.
2. Observation is not authorization.
3. Correlation is not causation.
4. Do not authorize destructive or external change unless evidence proves necessity.
5. If evidence is insufficient, HOLD.
6. Return JSON only.

Required schema:
{{
  "problem": "...",
  "evidence": ["..."],
  "missing_evidence": ["..."],
  "decision": "EXECUTE|HOLD|REJECT",
  "proposed_action": "...",
  "reason": "..."
}}

LIVE STATE:
{json.dumps(state)}
"""

models = [
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0"
]

analysis = None
used_model = None

for model in models:
    try:
        response = bedrock.converse(
            modelId=model,
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 1200
            }
        )

        text = response["output"]["message"]["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        analysis = json.loads(text)
        used_model = model
        break
    except Exception:
        continue

if analysis is None:
    analysis = {
        "problem": "Reasoning layer unavailable",
        "evidence": [],
        "missing_evidence": ["No successful governed model response"],
        "decision": "HOLD",
        "proposed_action": "None",
        "reason": "Fail-closed boundary activated."
    }

# ── 3. ENFORCE BOUNDARY ─────────────────────────────────────────────────
allowed = {"EXECUTE", "HOLD", "REJECT"}
decision = str(analysis.get("decision", "HOLD")).upper()

if decision not in allowed:
    decision = "HOLD"

analysis["decision"] = decision

# This workload observes/reasons only.
# EXECUTE means the proposal passed reasoning — NOT permission to mutate AWS.
external_change_executed = False

# ── 4. OPTIONAL LOCAL QUANTUM CHALLENGE ─────────────────────────────────
quantum = {"executed": False}

try:
    from qiskit import QuantumCircuit
    from qiskit.primitives import StatevectorSampler

    bit = int(state_sha256[-1], 16) & 1

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)

    if bit:
        qc.x(0)

    qc.measure_all()

    result = StatevectorSampler().run([qc], shots=256).result()
    counts = result[0].data.meas.get_counts()

    quantum = {
        "executed": True,
        "state_hash_bit": bit,
        "counts": counts
    }
except Exception as e:
    quantum = {
        "executed": False,
        "reason": str(e)
    }

# ── 5. CREATE IMMUTABLE-STYLE RECEIPT ───────────────────────────────────
receipt = {
    "schema": "sc-governed-workload-v1",
    "timestamp": state["timestamp"],
    "state_sha256": state_sha256,
    "model": used_model,
    "analysis": analysis,
    "quantum_challenge": quantum,
    "external_change_executed": external_change_executed
}

unsigned = json.dumps(
    receipt, sort_keys=True, separators=(",", ":")
).encode()

receipt["receipt_sha256"] = hashlib.sha256(unsigned).hexdigest()

with open(OUT, "w") as f:
    json.dump(receipt, f, indent=2)

# ── 6. VERIFY RECEIPT EXISTS ─────────────────────────────────────────────
verified = os.path.isfile(OUT) and os.path.getsize(OUT) > 0

print("\n🧠 GOVERNED ANALYSIS")
print(json.dumps(analysis, indent=2))

print("\n⚛️ QUANTUM CHALLENGE")
print(json.dumps(quantum, indent=2))

print("\n🛡️ FINAL DECISION:", decision)
print("⚡ EXTERNAL CHANGE EXECUTED:", external_change_executed)
print("🧾 RECEIPT:", OUT)
print("🔐 RECEIPT SHA256:", receipt["receipt_sha256"])
print("✅ RECEIPT VERIFIED:", verified)

print("\n🏁 TOTAL LOOP COMPLETE")
print("🌎 OBSERVE → 🛡️ GOVERN → 🧠 REASON → ⚡ DECIDE → ⚛️ CHALLENGE → ✅ VERIFY → 🧾 RECEIPT")
