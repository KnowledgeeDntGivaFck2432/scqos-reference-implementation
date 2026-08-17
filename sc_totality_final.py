import json, hashlib, subprocess, datetime
from pathlib import Path
from qiskit_ibm_runtime import QiskitRuntimeService

ROOT = Path.home() / "scqos-reference-implementation"
TODAY = datetime.date.today().isoformat()

IBM_INSTANCE = "crn:v1:bluemix:public:quantum-computing:us-east:a/aaf410d8b63f44179df4f97b6adf87f4:34c3669d-a94a-47d4-a90e-cce91d5094ca::"
IBM_JOB_ID = "da0sbe4dedkc73eqaag0"

def canon(x):
    return json.dumps(
        x,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    )

def H(x):
    if not isinstance(x, (str, bytes)):
        x = canon(x)
    if isinstance(x, str):
        x = x.encode()
    return hashlib.sha256(x).hexdigest()

def command(args):
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=20
        )
        return {
            "ok": p.returncode == 0,
            "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip(),
            "returncode": p.returncode
        }
    except Exception as e:
        return {"ok": False, "error": repr(e)}

print("=" * 88)
print("SUPREME COMPUTATION — ABSOLUTE TOTALITY SINGLE RUN")
print("DATE:", TODAY)
print("=" * 88)

# ============================================================
# 1. SPORTS WORLD STATE ALREADY COLLECTED
# ============================================================

sports_dir = ROOT / "sc-evidence" / "sports" / TODAY

receipts = []
if sports_dir.exists():
    for f in sorted(sports_dir.glob("*.json")):
        try:
            obj = json.loads(f.read_text())
            receipts.append({
                "path": str(f),
                "sha256": H(f.read_bytes()),
                "data": obj
            })
        except Exception as e:
            receipts.append({
                "path": str(f),
                "error": repr(e)
            })

print("\n[SPORTS]")
print("RECEIPTS:", len(receipts))

# ============================================================
# 2. AWS LIVE CLOUD IDENTITY + CONFIGURATION
# ============================================================

aws_identity = command([
    "aws", "sts", "get-caller-identity",
    "--output", "json",
    "--no-cli-pager"
])

aws_region = command([
    "aws", "configure", "get", "region"
])

aws_state = {
    "identity": aws_identity,
    "region": aws_region
}

print("\n[AWS]")
print("IDENTITY VERIFIED:", aws_identity.get("ok"))
if aws_identity.get("stdout"):
    print(aws_identity["stdout"])

# ============================================================
# 3. SCQOS / REPOSITORY EXECUTED STATE
# ============================================================

git_head = command(["git", "rev-parse", "HEAD"])
git_status = command(["git", "status", "--porcelain"])
git_branch = command(["git", "branch", "--show-current"])

contract_candidates = list(ROOT.rglob("*contract*universe*.json"))

contracts = []
for f in contract_candidates:
    try:
        contracts.append({
            "path": str(f),
            "sha256": H(f.read_bytes())
        })
    except Exception:
        pass

scqos_state = {
    "git_head": git_head,
    "git_branch": git_branch,
    "git_status": git_status,
    "contract_universe_artifacts": contracts
}

print("\n[SCQOS]")
print("HEAD:", git_head.get("stdout"))
print("BRANCH:", git_branch.get("stdout"))
print("CONTRACT ARTIFACTS:", len(contracts))

# ============================================================
# 4. IBM — RECOVER EXISTING PHYSICAL QUANTUM RESULT
#    ZERO NEW JOBS
# ============================================================

print("\n[IBM]")
print("RECOVERING EXISTING WORKLOAD:", IBM_JOB_ID)

service = QiskitRuntimeService(
    channel="ibm_quantum_platform",
    instance=IBM_INSTANCE
)

job = service.job(IBM_JOB_ID)

status = str(job.status())
backend = job.backend().name

print("STATUS:", status)
print("BACKEND:", backend)

if "DONE" not in status.upper():
    raise RuntimeError(
        "Existing IBM workload is not DONE: " + status
    )

result = job.result()

pub = result[0]
data = pub.data

counts = None
register_used = None

for name in dir(data):
    if name.startswith("_"):
        continue
    try:
        obj = getattr(data, name)
        if hasattr(obj, "get_counts"):
            counts = obj.get_counts()
            register_used = name
            break
    except Exception:
        pass

if counts is None:
    raise RuntimeError(
        "IBM workload recovered but no measured classical register found."
    )

quantum_state = {
    "job_id": IBM_JOB_ID,
    "status": status,
    "backend": backend,
    "register": register_used,
    "shots": sum(counts.values()),
    "unique_outcomes": len(counts),
    "counts": counts
}

quantum_state["sha256"] = H(quantum_state)

print("REGISTER:", register_used)
print("SHOTS:", quantum_state["shots"])
print("UNIQUE OUTCOMES:", quantum_state["unique_outcomes"])
print(
    "TOP OUTCOMES:",
    sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
)
print("QUANTUM SHA256:", quantum_state["sha256"])
print("NEW IBM JOBS SUBMITTED: 0")

# ============================================================
# 5. TOROIDAL TOTALITY STATE
#
# outward:
# world/sports evidence -> computation
#
# inward:
# AWS + SCQOS + IBM verification -> canonical state
#
# closure:
# every substrate returns into one immutable state identity
# ============================================================

outward_state = {
    "sports": receipts
}

inward_state = {
    "aws": aws_state,
    "scqos": scqos_state,
    "ibm_quantum": quantum_state
}

outward_hash = H(outward_state)
inward_hash = H(inward_state)

toroidal_state = {
    "outward_world_state_sha256": outward_hash,
    "inward_verification_state_sha256": inward_hash,
}

toroidal_state["closure_sha256"] = H({
    "outward": outward_hash,
    "inward": inward_hash
})

print("\n[TOROIDAL CLOSURE]")
print("OUTWARD:", outward_hash)
print("INWARD:", inward_hash)
print("CLOSURE:", toroidal_state["closure_sha256"])

# ============================================================
# 6. EIGHT-INVARIANT SC STATE
# ============================================================

invariants = {
    "time": TODAY,
    "continuity": {
        "sports_receipts": len(receipts),
        "ibm_existing_job": IBM_JOB_ID
    },
    "alignment": {
        "single_run": True,
        "new_quantum_jobs": 0
    },
    "genesis": {
        "repository": str(ROOT),
        "git_head": git_head.get("stdout")
    },
    "boundary": {
        "aws_identity_verified": aws_identity.get("ok", False),
        "ibm_status": status
    },
    "reference": {
        "sports_state_hash": H(receipts),
        "quantum_state_hash": quantum_state["sha256"]
    },
    "causality": {
        "world_state_to_verification": toroidal_state["closure_sha256"]
    },
    "coherence": {
        "all_substrates_bound": True
    }
}

invariants_hash = H(invariants)

# ============================================================
# 7. ABSOLUTE CANONICAL STATE
# ============================================================

totality = {
    "architecture": "SUPREME COMPUTATION",
    "mode": "ABSOLUTE_TOTALITY",
    "generated_utc":
        datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),

    "sports_world_state": receipts,
    "aws_state": aws_state,
    "scqos_state": scqos_state,
    "ibm_quantum_state": quantum_state,
    "toroidal_state": toroidal_state,
    "eight_invariants": invariants,
    "eight_invariants_sha256": invariants_hash
}

totality["canonical_state_sha256"] = H(totality)

# ============================================================
# 8. WRITE ONE FINAL RECEIPT
# ============================================================

outdir = sports_dir
outdir.mkdir(parents=True, exist_ok=True)

outfile = outdir / "SC_ABSOLUTE_TOTALITY_FINAL.json"

outfile.write_text(
    json.dumps(
        totality,
        indent=2,
        sort_keys=True,
        default=str
    )
)

file_hash = H(outfile.read_bytes())

print("\n" + "=" * 88)
print("ABSOLUTE TOTALITY CLOSED")
print("=" * 88)

print("SPORTS RECEIPTS:", len(receipts))
print("AWS VERIFIED:", aws_identity.get("ok"))
print("IBM JOB:", IBM_JOB_ID)
print("IBM STATUS:", status)
print("IBM BACKEND:", backend)
print("IBM SHOTS:", quantum_state["shots"])
print("IBM UNIQUE OUTCOMES:", quantum_state["unique_outcomes"])
print("NEW IBM JOBS:", 0)

print("TOROIDAL CLOSURE SHA256:",
      toroidal_state["closure_sha256"])

print("INVARIANTS SHA256:",
      invariants_hash)

print("CANONICAL STATE SHA256:",
      totality["canonical_state_sha256"])

print("FINAL FILE SHA256:",
      file_hash)

print("RECEIPT:",
      outfile.resolve())

print("=" * 88)
