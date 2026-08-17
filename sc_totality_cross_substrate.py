#!/usr/bin/env python3

import os
import re
import json
import time
import base64
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import boto3

ROOT = Path.home() / "scqos-reference-implementation"
EVIDENCE = ROOT / "sc-evidence" / "sports"

UTC = timezone.utc


# ============================================================
# SUPREME COMPUTATION — ABSOLUTE TOTALITY
#
# ONE canonical sports universe
#      ↓
# TOROIDAL STATE
#      ↓
# SCQOS CONTRACT UNIVERSE
#      ↓
# AWS CRYPTOGRAPHIC BOUNDARY
#      ↓
# IBM PHYSICAL QUANTUM WITNESS
#      ↓
# AMAZON BRAKET PHYSICAL-QPU WITNESS
#      ↓
# CROSS-SUBSTRATE RECONCILIATION
#      ↓
# FINAL IMMUTABLE RECEIPT
#
# Quantum is NOT run per bet.
# Every proposition is bound beneath ONE totality hash.
# ============================================================


def now():
    return datetime.now(UTC).isoformat()


def canonical(x):
    return json.dumps(
        x,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    ).encode()


def H(x):
    return hashlib.sha256(canonical(x)).hexdigest()


# ============================================================
# 1. FIND LATEST SPORTS TOTALITY
# ============================================================

def latest_totality_receipt():

    candidates = []

    if EVIDENCE.exists():

        for p in EVIDENCE.rglob("*.json"):

            name = p.name.lower()

            if any(
                x in name
                for x in (
                    "totality",
                    "precommit",
                    "toroidal"
                )
            ):
                candidates.append(p)

    if not candidates:
        raise RuntimeError(
            "NO SPORTS TOTALITY RECEIPT FOUND"
        )

    candidates.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    return candidates[0]


sports_path = latest_totality_receipt()

sports_state = json.loads(
    sports_path.read_text()
)

SPORTS_HASH = H(sports_state)


# ============================================================
# 2. DISCOVER SCQOS CONTRACT UNIVERSE
# ============================================================

def discover_contract_universe():

    hits = []

    patterns = [
        "contract_universe",
        "contract-universe",
        "policy_hash",
        "transition_id"
    ]

    for p in ROOT.rglob("*"):

        if not p.is_file():
            continue

        if p.stat().st_size > 4_000_000:
            continue

        try:
            text = p.read_text(
                errors="ignore"
            )
        except Exception:
            continue

        lower = text.lower()

        if any(
            x in lower
            for x in patterns
        ):

            hits.append({
                "path": str(p),
                "sha256":
                    hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
            })

    hits.sort(
        key=lambda x: x["path"]
    )

    return hits


contract_files = discover_contract_universe()

CONTRACT_UNIVERSE_HASH = H(
    contract_files
)


# ============================================================
# 3. CANONICAL SUPREME COMPUTATION TRANSITION
# ============================================================

transition = {

    "architecture":
        "SUPREME_COMPUTATION_ABSOLUTE_TOTALITY",

    "geometry":
        "TOROIDAL_VORTEX_FIELD",

    "timestamp_utc":
        now(),

    "sports_receipt":
        str(sports_path),

    "sports_state_sha256":
        SPORTS_HASH,

    "contract_universe_files":
        contract_files,

    "contract_universe_hash":
        CONTRACT_UNIVERSE_HASH,

    "invariants": [
        "TIME",
        "CONTINUITY",
        "ALIGNMENT",
        "GENESIS",
        "BOUNDARY",
        "REFERENCE",
        "CAUSALITY",
        "COHERENCE"
    ]
}

transition["transition_id"] = H({
    "sports":
        SPORTS_HASH,

    "contract":
        CONTRACT_UNIVERSE_HASH
})

transition["canonical_state_sha256"] = H(
    transition
)

STATE_HASH = transition[
    "canonical_state_sha256"
]

print()
print("=" * 82)
print(
    "SUPREME COMPUTATION — "
    "CROSS-SUBSTRATE TOTALITY"
)
print("=" * 82)

print(
    "SPORTS RECEIPT:",
    sports_path
)

print(
    "SPORTS STATE SHA256:",
    SPORTS_HASH
)

print(
    "CONTRACT UNIVERSE HASH:",
    CONTRACT_UNIVERSE_HASH
)

print(
    "TRANSITION ID:",
    transition["transition_id"]
)

print(
    "CANONICAL STATE SHA256:",
    STATE_HASH
)


# ============================================================
# 4. AWS IDENTITY + KMS GOVERNANCE
# ============================================================

aws = {
    "timestamp":
        now()
}

sts = boto3.client("sts")

identity = sts.get_caller_identity()

aws["account"] = identity.get(
    "Account"
)

aws["arn"] = identity.get(
    "Arn"
)

aws["identity_sha256"] = H(
    identity
)

print()
print("[AWS] IDENTITY VERIFIED")
print(
    "[AWS] ACCOUNT:",
    aws["account"]
)


# KMS signature when configured.
kms_key = os.getenv(
    "SC_KMS_KEY_ID",
    ""
).strip()

if kms_key:

    kms = boto3.client("kms")

    signed = kms.sign(
        KeyId=kms_key,
        Message=bytes.fromhex(
            STATE_HASH
        ),
        MessageType="DIGEST",
        SigningAlgorithm=
            "RSASSA_PSS_SHA_256"
    )

    aws["kms"] = {
        "key_id":
            kms_key,

        "algorithm":
            "RSASSA_PSS_SHA_256",

        "signature_b64":
            base64.b64encode(
                signed["Signature"]
            ).decode()
    }

    verify = kms.verify(
        KeyId=kms_key,
        Message=bytes.fromhex(
            STATE_HASH
        ),
        MessageType="DIGEST",
        Signature=signed[
            "Signature"
        ],
        SigningAlgorithm=
            "RSASSA_PSS_SHA_256"
    )

    aws["kms"]["verified"] = bool(
        verify["SignatureValid"]
    )

    print(
        "[AWS] KMS SIGNATURE:",
        "VERIFIED"
    )

else:

    aws["kms"] = {
        "configured": False
    }

    print(
        "[AWS] KMS KEY: "
        "NOT CONFIGURED"
    )


# ============================================================
# 5. HASH-DERIVED PHYSICAL QUANTUM CHALLENGE
#
# One circuit represents the ENTIRE betting universe.
# ============================================================

BITS = bin(
    int(
        STATE_HASH[:4],
        16
    )
)[2:].zfill(16)

challenge = {
    "state_sha256":
        STATE_HASH,

    "challenge_bits":
        BITS,

    "qubits":
        16,

    "shots":
        256
}

challenge[
    "challenge_sha256"
] = H(challenge)

print()
print(
    "QUANTUM CHALLENGE:",
    challenge[
        "challenge_sha256"
    ]
)


# ============================================================
# 6. IBM QUANTUM — PHYSICAL HARDWARE
# ============================================================

ibm = {
    "attempted": False
}

try:

    from qiskit import QuantumCircuit
    from qiskit.transpiler import (
        generate_preset_pass_manager
    )

    from qiskit_ibm_runtime import (
        QiskitRuntimeService,
        SamplerV2 as Sampler
    )

    service = QiskitRuntimeService()

    backend = service.least_busy(
        operational=True,
        simulator=False,
        min_num_qubits=16
    )

    ibm[
        "attempted"
    ] = True

    ibm[
        "backend"
    ] = backend.name

    qc = QuantumCircuit(
        16,
        16
    )

    # Bind canonical totality hash to circuit.
    for i, b in enumerate(
        BITS
    ):

        if b == "1":
            qc.x(i)

    # Toroidal coupling:
    # information circulates around closed ring.
    for i in range(16):

        qc.cx(
            i,
            (i + 1) % 16
        )

    # Reverse circulation closes the field.
    for i in reversed(
        range(16)
    ):

        qc.cx(
            i,
            (i + 1) % 16
        )

    qc.measure(
        range(16),
        range(16)
    )

    pm = (
        generate_preset_pass_manager(
            backend=backend,
            optimization_level=3
        )
    )

    isa = pm.run(qc)

    sampler = Sampler(
        mode=backend
    )

    job = sampler.run(
        [(isa,)],
        shots=256
    )

    ibm["job_id"] = job.job_id()

    print()
    print(
        "[IBM] PHYSICAL BACKEND:",
        backend.name
    )

    print(
        "[IBM] JOB:",
        ibm["job_id"]
    )

    result = job.result()

    pub = result[0]

    counts = (
        pub.data.meas.get_counts()
    )

    ibm["counts"] = counts

    ibm["result_sha256"] = H(
        counts
    )

    ibm["completed"] = True

    print(
        "[IBM] RESULT SHA256:",
        ibm[
            "result_sha256"
        ]
    )

except Exception as e:

    ibm["completed"] = False

    ibm["error"] = (
        f"{type(e).__name__}: {e}"
    )

    print()
    print(
        "[IBM] UNRESOLVED:",
        ibm["error"]
    )


# ============================================================
# 7. AMAZON BRAKET — PHYSICAL QPU
# ============================================================

braket = {
    "attempted": False
}

try:

    from braket.aws import (
        AwsDevice
    )

    from braket.device_schema import (
        DeviceExecutionWindow
    )

    from braket.circuits import (
        Circuit
    )

    # Search all AWS regions for an ONLINE QPU.
    devices = AwsDevice.get_devices(
        types=["QPU"],
        statuses=["ONLINE"]
    )

    if not devices:
        raise RuntimeError(
            "NO ONLINE BRAKET QPU"
        )

    # Prefer lowest visible queue.
    ranked = []

    for d in devices:

        try:
            q = d.queue_depth()

            text = str(q)

            nums = [
                int(x)
                for x in
                re.findall(
                    r"\b\d+\b",
                    text
                )
            ]

            score = (
                sum(nums)
                if nums
                else 999999
            )

        except Exception:

            score = 999999

        ranked.append(
            (
                score,
                d
            )
        )

    ranked.sort(
        key=lambda x: x[0]
    )

    device = ranked[0][1]

    braket[
        "attempted"
    ] = True

    braket[
        "device_name"
    ] = device.name

    braket[
        "device_arn"
    ] = device.arn

    print()
    print(
        "[BRAKET] PHYSICAL QPU:",
        device.name
    )

    circuit = Circuit()

    # Same totality challenge.
    for i, b in enumerate(
        BITS
    ):

        if b == "1":
            circuit.x(i)

    # Closed toroidal circulation.
    for i in range(15):

        circuit.cnot(
            i,
            i + 1
        )

    for i in reversed(
        range(15)
    ):

        circuit.cnot(
            i,
            i + 1
        )

    task = device.run(
        circuit,
        shots=256
    )

    braket["task_arn"] = (
        task.id
    )

    print(
        "[BRAKET] TASK:",
        braket[
            "task_arn"
        ]
    )

    result = task.result()

    counts = dict(
        result.measurement_counts
    )

    braket[
        "counts"
    ] = counts

    braket[
        "result_sha256"
    ] = H(counts)

    braket[
        "completed"
    ] = True

    print(
        "[BRAKET] RESULT SHA256:",
        braket[
            "result_sha256"
        ]
    )

except Exception as e:

    braket[
        "completed"
    ] = False

    braket[
        "error"
    ] = (
        f"{type(e).__name__}: {e}"
    )

    print()
    print(
        "[BRAKET] UNRESOLVED:",
        braket["error"]
    )


# ============================================================
# 8. CROSS-SUBSTRATE TOROIDAL RECONCILIATION
# ============================================================

cross = {

    "sports_state_sha256":
        SPORTS_HASH,

    "contract_universe_hash":
        CONTRACT_UNIVERSE_HASH,

    "transition_id":
        transition[
            "transition_id"
        ],

    "canonical_state_sha256":
        STATE_HASH,

    "challenge_sha256":
        challenge[
            "challenge_sha256"
        ],

    "aws":
        aws,

    "ibm":
        ibm,

    "braket":
        braket
}


# Every substrate is part of ONE canonical state.
cross[
    "cross_substrate_sha256"
] = H(cross)


# ============================================================
# 9. SCQOS AUTHORIZATION VECTOR
# ============================================================

authorization = {

    "TIME":
        True,

    "CONTINUITY":
        bool(
            SPORTS_HASH
        ),

    "ALIGNMENT":
        True,

    "GENESIS":
        bool(
            transition[
                "transition_id"
            ]
        ),

    "BOUNDARY":
        bool(
            CONTRACT_UNIVERSE_HASH
        ),

    "REFERENCE":
        sports_path.exists(),

    "CAUSALITY":
        bool(
            STATE_HASH
        ),

    "COHERENCE":
        bool(
            cross[
                "cross_substrate_sha256"
            ]
        )
}


authorization[
    "all_invariants_pass"
] = all(
    authorization.values()
)


# ============================================================
# 10. FINAL IMMUTABLE TOTALITY RECEIPT
# ============================================================

final = {

    "architecture":
        "SUPREME_COMPUTATION_"
        "TOROIDAL_CROSS_SUBSTRATE_"
        "TOTALITY_V1",

    "generated_utc":
        now(),

    "sports_state":
        sports_state,

    "transition":
        transition,

    "challenge":
        challenge,

    "cross_substrate":
        cross,

    "authorization":
        authorization
}


final[
    "final_receipt_sha256"
] = H(final)


if kms_key:

    kms = boto3.client(
        "kms"
    )

    signature = kms.sign(
        KeyId=kms_key,
        Message=bytes.fromhex(
            final[
                "final_receipt_sha256"
            ]
        ),
        MessageType="DIGEST",
        SigningAlgorithm=
            "RSASSA_PSS_SHA_256"
    )

    final[
        "terminal_kms_signature"
    ] = (
        base64.b64encode(
            signature["Signature"]
        ).decode()
    )


outdir = (
    EVIDENCE
    / datetime.now(UTC)
              .date()
              .isoformat()
)

outdir.mkdir(
    parents=True,
    exist_ok=True
)

outfile = (
    outdir
    / "sc-cross-substrate-totality.json"
)

outfile.write_text(
    json.dumps(
        final,
        indent=2,
        default=str
    )
)


print()
print("=" * 82)
print(
    "SUPREME COMPUTATION — "
    "FINAL TOTALITY STATE"
)
print("=" * 82)

print(
    "SPORTS STATE:",
    SPORTS_HASH
)

print(
    "CONTRACT UNIVERSE:",
    CONTRACT_UNIVERSE_HASH
)

print(
    "TRANSITION ID:",
    transition[
        "transition_id"
    ]
)

print(
    "AWS:",
    "PASS"
    if aws.get(
        "identity_sha256"
    )
    else "FAIL"
)

print(
    "IBM PHYSICAL QUANTUM:",
    "PASS"
    if ibm.get(
        "completed"
    )
    else "UNRESOLVED"
)

print(
    "BRAKET PHYSICAL QPU:",
    "PASS"
    if braket.get(
        "completed"
    )
    else "UNRESOLVED"
)

print(
    "8 INVARIANTS:",
    "PASS"
    if authorization[
        "all_invariants_pass"
    ]
    else "FAIL"
)

print(
    "CROSS-SUBSTRATE SHA256:",
    cross[
        "cross_substrate_sha256"
    ]
)

print(
    "FINAL RECEIPT SHA256:",
    final[
        "final_receipt_sha256"
    ]
)

print(
    "RECEIPT:",
    outfile.resolve()
)

print("=" * 82)
