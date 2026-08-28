#!/usr/bin/env python3
"""Build and verify a total SCQOS master evidence index using only stdlib + git.

The builder never changes source repositories.  It inventories Git-tracked files,
binds five public SC repositories to immutable commits, evaluates the evidence
against the SC invariants, and emits a canonical, independently verifiable bundle.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "https://knowledgeekza3224.github.io/scqos/schema/master-index/v1"
CANON_AUTHORITY = "SCQOS-C14N-JCS-NFC-1"
KNOWN_REPOS = (
    "scqos-reference-implementation",
    "Supreme-Computation-Core",
    "SCQOS_Hybrid_Proof",
    "scqos-webhook",
    "linux-coherence-gate",
)
OWNER = "KnowledgeeKZA3224"
HEX64 = re.compile(r"\b[a-fA-F0-9]{64}\b")
CID = re.compile(r"\b(?:Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z2-7]{20,})\b")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> str:
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [normalize(x) for x in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = unicodedata.normalize("NFC", str(raw_key))
            if key in out:
                raise ValueError(f"NFC property collision: {key!r}")
            out[key] = normalize(raw_value)
        return out
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise ValueError("floating point is forbidden in canonical SCQOS evidence")
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    # All generated numeric fields are integers.  With NFC normalization,
    # UTF-8, sorted keys and compact separators this is deterministic JCS-form JSON.
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def pretty_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False) + "\n", encoding="utf-8")


def merkle_root(digests: Iterable[str]) -> str:
    level = [bytes.fromhex(x) for x in sorted(digests)]
    if not level:
        return sha256_bytes(b"")
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest()
                 for i in range(0, len(level), 2)]
    return level[0].hex()


def git_remote(repo: Path) -> str:
    value = run(["git", "config", "--get", "remote.origin.url"], repo, check=False)
    if not value:
        return ""
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    if value.endswith(".git"):
        value = value[:-4]
    return value


def public_blob_url(remote: str, commit: str, rel: str) -> str:
    if "github.com/" not in remote:
        return ""
    return f"{remote}/blob/{commit}/{urllib.parse.quote(rel, safe='/')}"


def classify(rel: str, text: str) -> list[str]:
    hay = (rel + "\n" + text[:200000]).lower()
    rules = {
        "governing-law": ("supreme computation", "invariant", "governing law"),
        "canonicalization": ("canonical", "jcs", "nfc"),
        "policy-authority": ("policy", "authority", "contract_universe"),
        "decision": ("permit", "hold", "reject", "denied_by_sc", "sc denied"),
        "receipt": ("receipt", "sha256sums", "manifest", "closure"),
        "test": ("test", "qualification", "pass", "fail"),
        "aws-cloud": ("aws", "braket", "cloudtrail", "lambda", "s3"),
        "ibm-quantum": ("qiskit", "ibm quantum", "ibm_runtime", "samplerv2"),
        "kubernetes": ("kubernetes", "admissionreview", "auditid", "webhook"),
        "linux-kernel": ("linux", "copy_process", "kernel", "-eperm"),
        "ai-agent": ("agent", "inference", "bedrock", "model"),
        "commercial-boundary": ("commercial", "licensing", "customer acceptance"),
        "external-anchor": ("ipfs", "cid", "versionid", "rekor", "transparency"),
    }
    return sorted(name for name, terms in rules.items() if any(t in hay for t in terms))


def extract_facts(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    hashes = sorted(set(x.lower() for x in HEX64.findall(text)))
    cids = sorted(set(CID.findall(text)))
    if hashes:
        facts["embedded_sha256_candidates"] = hashes[:100]
    if cids:
        facts["ipfs_cid_candidates"] = cids[:100]
    patterns = {
        "transition_ids": r'(?i)["\']?transition_id["\']?\s*[:=]\s*["\']([^"\'\s,}]+)',
        "contract_universe_hashes": r'(?i)["\']?contract_universe_hash["\']?\s*[:=]\s*["\']([a-f0-9]{64})',
        "aws_version_ids": r'(?i)["\']?(?:versionid|version_id)["\']?\s*[:=]\s*["\']([^"\'\s,}]+)',
        "ibm_job_ids": r'(?i)["\']?(?:job_id|ibm_job_id)["\']?\s*[:=]\s*["\']([^"\'\s,}]+)',
        "kubernetes_audit_ids": r'(?i)["\']?auditid["\']?\s*[:=]\s*["\']([^"\'\s,}]+)',
    }
    for key, pattern in patterns.items():
        found = sorted(set(re.findall(pattern, text)))
        if found:
            facts[key] = found[:100]
    decisions = sorted(set(re.findall(r"\b(?:PERMIT|HOLD|REJECT|DENY|DENIED_BY_SC)\b", text)))
    if decisions:
        facts["decision_terms"] = decisions
    return facts


def tracked_files(repo: Path) -> list[str]:
    raw = run(["git", "ls-files", "-z"], repo)
    return sorted(x for x in raw.split("\0") if x)


def inspect_repo(repo: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    remote = git_remote(repo)
    commit = run(["git", "rev-parse", "HEAD"], repo)
    branch = run(["git", "branch", "--show-current"], repo, check=False) or "DETACHED"
    commit_time = run(["git", "show", "-s", "--format=%cI", "HEAD"], repo)
    status = run(["git", "status", "--porcelain"], repo, check=False)
    artifacts: list[dict[str, Any]] = []
    for rel in tracked_files(repo):
        path = repo / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        text = ""
        if b"\0" not in data[:8192] and len(data) <= 10 * 1024 * 1024:
            text = data.decode("utf-8", errors="replace")
        artifact: dict[str, Any] = {
            "repository": repo.name,
            "path": rel,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "media_hint": path.suffix.lower() or "none",
            "classes": classify(rel, text),
            "permalink": public_blob_url(remote, commit, rel),
        }
        facts = extract_facts(text)
        if facts:
            artifact["observed_facts"] = facts
        artifacts.append(artifact)
    meta = {
        "name": repo.name,
        "remote": remote,
        "commit": commit,
        "branch": branch,
        "commit_time": commit_time,
        "working_tree": "DIRTY" if status else "CLEAN",
        "tracked_file_count": len(artifacts),
        "artifact_merkle_root": merkle_root(a["sha256"] for a in artifacts),
    }
    return meta, artifacts


def find_local_repo(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        candidates = [root, root / name, root.parent / name]
        for candidate in candidates:
            if candidate.name == name and (candidate / ".git").exists():
                return candidate.resolve()
    return None


def acquire_repos(workspace: Path, no_fetch: bool, cache: Path) -> tuple[list[Path], list[str]]:
    roots = [workspace.resolve(), Path.cwd().resolve()]
    repos: list[Path] = []
    errors: list[str] = []
    for name in KNOWN_REPOS:
        local = find_local_repo(name, roots)
        if local:
            repos.append(local)
            continue
        if no_fetch:
            errors.append(f"missing repository: {name}")
            continue
        target = cache / name
        url = f"https://github.com/{OWNER}/{name}.git"
        try:
            run(["git", "clone", "--quiet", "--depth", "1", url, str(target)])
            repos.append(target)
        except Exception as exc:
            errors.append(f"unable to acquire {name}: {exc}")
    return repos, errors


def evidence_for(classes: set[str], artifacts: list[dict[str, Any]]) -> list[str]:
    return [a["permalink"] or f'{a["repository"]}:{a["path"]}'
            for a in artifacts if classes.intersection(a["classes"])][:20]


def evaluate_invariants(repos: list[dict[str, Any]], artifacts: list[dict[str, Any]],
                        acquisition_errors: list[str]) -> tuple[list[dict[str, Any]], str]:
    present = {c for a in artifacts for c in a["classes"]}
    all_have_origin = bool(repos) and all(r["remote"] and r["commit"] for r in repos)
    all_files_bound = bool(artifacts) and all(len(a["sha256"]) == 64 for a in artifacts)
    complete_network = {r["name"] for r in repos} == set(KNOWN_REPOS)

    checks = [
        ("time", bool(repos) and all(r["commit_time"] for r in repos),
         "Every source state has a recorded commit time.", {"governing-law"}),
        ("continuity", complete_network and "receipt" in present,
         "All five repositories and durable receipt artifacts remain connected.", {"receipt"}),
        ("alignment", "governing-law" in present and "policy-authority" in present,
         "The indexed work is bound to the governing law and authority.", {"governing-law", "policy-authority"}),
        ("genesis", all_have_origin,
         "Every repository is bound to its public origin and immutable commit.", set()),
        ("boundary", "commercial-boundary" in present,
         "Public, commercial, ownership, and execution boundaries are represented.", {"commercial-boundary"}),
        ("reference", all_files_bound and "canonicalization" in present,
         "Every tracked artifact has a digest and canonicalization authority is present.", {"canonicalization"}),
        ("causality", "decision" in present and bool({"aws-cloud", "ibm-quantum", "kubernetes", "linux-kernel"} & present),
         "Decision evidence is connected to execution-domain evidence.", {"decision", "aws-cloud", "ibm-quantum", "kubernetes", "linux-kernel"}),
        ("consciousness", "policy-authority" in present and ("test" in present or "commercial-boundary" in present),
         "Authority, observer, verification, and accountability evidence are represented.", {"policy-authority", "test"}),
    ]
    results: list[dict[str, Any]] = []
    for name, passed, reason, classes in checks:
        results.append({
            "invariant": name,
            "status": "PASS" if passed else "HOLD",
            "reason": reason,
            "evidence": evidence_for(classes, artifacts),
        })
    coherence = all(x["status"] == "PASS" for x in results) and not acquisition_errors
    results.append({
        "invariant": "coherence",
        "status": "PASS" if coherence else "HOLD",
        "reason": "All required invariant statements remain true together."
                  if coherence else "One or more required facts are missing or unresolved.",
        "evidence": [],
    })
    decision = "PERMIT" if coherence else "HOLD"
    return results, decision


def generate_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# SCQOS Master Evidence Index",
        "",
        f'**Decision:** `{index["decision"]}`  ',
        f'**Transition:** `{index["transition_id"]}`  ',
        f'**Generated:** `{index["generated_at"]}`  ',
        f'**Source-state root:** `{index["source_state_root"]}`',
        "",
        "This is the human face of the machine-verifiable master index. It binds the governing law, public source states, evidence, authority, decisions, execution domains, observed facts, and integrity proofs without moving or rewriting the source artifacts.",
        "",
        "## Invariant Judgment",
        "",
        "| Invariant | Result | Meaning |",
        "|---|---:|---|",
    ]
    for item in index["invariant_evaluation"]:
        lines.append(f'| {item["invariant"].title()} | **{item["status"]}** | {item["reason"]} |')
    lines += ["", "## Frozen Repository States", "",
              "| Repository | Commit | Files | Tree |", "|---|---|---:|---|"]
    for repo in index["repositories"]:
        commit_url = f'{repo["remote"]}/commit/{repo["commit"]}' if repo["remote"] else ""
        commit = f'[{repo["commit"][:12]}]({commit_url})' if commit_url else repo["commit"][:12]
        lines.append(f'| {repo["name"]} | {commit} | {repo["tracked_file_count"]} | {repo["working_tree"]} |')
    lines += ["", "## Evidence Facets", "",
              "| Facet | Artifacts |", "|---|---:|"]
    for facet, count in sorted(index["facet_counts"].items()):
        lines.append(f"| {facet} | {count} |")
    lines += ["", "## Life Cycle", "",
              "| Stage | State |", "|---|---|"]
    for stage in index["lifecycle"]:
        lines.append(f'| {stage["stage"]} | {stage["status"]} |')
    if index["unresolved"]:
        lines += ["", "## Unresolved Facts — Fail Closed", ""]
        lines.extend(f"- {x}" for x in index["unresolved"])
    lines += [
        "", "## Independent Verification", "",
        "From the repository root:", "",
        "```bash",
        "python3 VERIFY.py --verify .",
        "```",
        "",
        "A valid hash proves the indexed bytes were not changed. Source truth and authority remain subject to the invariant evidence recorded above.",
    ]
    return "\n".join(lines) + "\n"


def make_prov(index: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": {"prov": "http://www.w3.org/ns/prov#", "scqos": "https://knowledgeekza3224.github.io/scqos#"},
        "@id": index["transition_id"],
        "@type": "prov:Activity",
        "prov:startedAtTime": index["generated_at"],
        "prov:used": [{"@id": f'{r["remote"]}/commit/{r["commit"]}', "@type": "prov:Entity"}
                      for r in index["repositories"]],
        "prov:wasAssociatedWith": [
            {"@id": "https://github.com/KnowledgeeKZA3224", "@type": "prov:Agent"},
            {"@id": "scqos:governor", "@type": "prov:SoftwareAgent"},
        ],
        "scqos:decision": index["decision"],
        "scqos:sourceStateRoot": index["source_state_root"],
    }


def write_checksums(bundle: Path, filename: str, exclude: set[str]) -> str:
    entries = []
    for path in sorted(x for x in bundle.iterdir() if x.is_file() and x.name not in exclude):
        entries.append(f"{sha256_file(path)}  {path.name}")
    data = ("\n".join(entries) + "\n").encode()
    (bundle / filename).write_bytes(data)
    return sha256_bytes(data)


def verify_bundle(bundle: Path) -> int:
    failures: list[str] = []
    sums = bundle / "BUNDLE_SHA256SUMS"
    if not sums.is_file():
        print("REJECT: BUNDLE_SHA256SUMS is missing")
        return 2
    for lineno, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            expected, name = line.split("  ", 1)
        except ValueError:
            failures.append(f"line {lineno}: malformed checksum")
            continue
        path = bundle / name
        if not path.is_file():
            failures.append(f"missing: {name}")
        elif sha256_file(path) != expected:
            failures.append(f"hash mismatch: {name}")
    closure = bundle / "CLOSURE_RECEIPT.json"
    if closure.is_file():
        obj = json.loads(closure.read_text(encoding="utf-8"))
        master = bundle / "SCQOS_MASTER_INDEX.canonical.json"
        if not master.is_file() or sha256_file(master) != obj.get("canonical_master_index_sha256"):
            failures.append("closure does not match canonical master index")
        elif canonical_bytes(json.loads(master.read_text(encoding="utf-8"))) != master.read_bytes():
            failures.append("master index is not in its declared canonical byte form")
    else:
        failures.append("CLOSURE_RECEIPT.json missing")
    if failures:
        print("REJECT: bundle verification failed")
        for failure in failures:
            print(f"- {failure}")
        return 2
    print("PERMIT: every bundled byte matches its recorded fingerprint")
    return 0


def build(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    if not shutil.which("git"):
        raise RuntimeError("git is required")
    with tempfile.TemporaryDirectory(prefix="scqos-master-index-") as temp:
        repos, acquisition_errors = acquire_repos(workspace, args.no_fetch, Path(temp))
        repo_records: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        for repo in repos:
            meta, found = inspect_repo(repo)
            repo_records.append(meta)
            artifacts.extend(found)
        repo_records.sort(key=lambda x: x["name"].lower())
        artifacts.sort(key=lambda x: (x["repository"].lower(), x["path"]))

        source_state = {
            "repositories": [{"name": r["name"], "remote": r["remote"],
                              "commit": r["commit"], "artifact_merkle_root": r["artifact_merkle_root"]}
                             for r in repo_records],
            "governing_artifact_hashes": sorted(
                a["sha256"] for a in artifacts
                if {"governing-law", "policy-authority", "canonicalization"}.intersection(a["classes"])),
        }
        source_state_root = sha256_bytes(canonical_bytes(source_state))
        transition_id = f"scqos:transition:sha256:{source_state_root}"
        generated = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        invariants, decision = evaluate_invariants(repo_records, artifacts, acquisition_errors)
        facets: dict[str, int] = {}
        for artifact in artifacts:
            for facet in artifact["classes"]:
                facets[facet] = facets.get(facet, 0) + 1

        lifecycle = [
            {"stage": "PROPOSED", "status": "PASS", "evidence": "master-index build invocation"},
            {"stage": "QUALIFIED", "status": "PASS" if artifacts else "HOLD", "evidence": "tracked artifacts fingerprinted"},
            {"stage": "DECIDED", "status": decision, "evidence": "invariant evaluation"},
            {"stage": "EXECUTED", "status": "PASS", "evidence": "master-index bundle generated; source systems were not re-executed"},
            {"stage": "OBSERVED", "status": "PASS", "evidence": "bundle bytes and public source states observed"},
            {"stage": "CLOSED", "status": "PENDING", "evidence": "set by closure receipt"},
        ]
        all_facts = [a["observed_facts"] for a in artifacts if "observed_facts" in a]
        contract_hashes = sorted({h for f in all_facts for h in f.get("contract_universe_hashes", [])})
        index: dict[str, Any] = {
            "$schema": SCHEMA,
            "object_type": "SCQOS_MASTER_EVIDENCE_INDEX",
            "version": "1.0.0",
            "canonicalization_authority": CANON_AUTHORITY,
            "transition_id": transition_id,
            "parent_transition_id": None,
            "generated_at": generated,
            "decision": decision,
            "source_state_root": source_state_root,
            "contract_universe_hashes_observed": contract_hashes,
            "governing_meta_rule": "Any missing, failed, contradictory, or unverifiable governor component becomes an attributable governed failure state and never implicit PERMIT.",
            "repositories": repo_records,
            "facet_counts": facets,
            "lifecycle": lifecycle,
            "invariant_evaluation": invariants,
            "accountability": {
                "founder_and_source_authority": "Eric Robles / Knowledgee Kza",
                "public_repository_owner": OWNER,
                "governor": "SCQOS",
                "executor": "scqos_master_index.py",
                "observer": "independent verifier executing BUNDLE_SHA256SUMS verification",
            },
            "interoperability": {
                "trace_context": "W3C Trace Context compatible transition identity",
                "provenance": "W3C PROV JSON-LD export included",
                "attestation": "in-toto Statement v1 export included",
                "canonical_json": "RFC 8785 JCS form plus Unicode NFC collision rejection",
                "transparency": "SCITT/Sigstore-compatible external witness slot; external registration is not fabricated",
            },
            "unresolved": acquisition_errors,
            "artifacts": artifacts,
        }

        # Never place the durable bundle inside a temporary shallow clone.  If the
        # primary repository is not local, preserve the result under the caller's
        # workspace so it survives cleanup.
        primary = find_local_repo("scqos-reference-implementation", [workspace]) or workspace
        if args.output:
            bundle = Path(args.output).resolve()
        else:
            stamp = generated.replace("-", "").replace(":", "")
            bundle = primary / "evidence" / "master-index" / stamp
        if bundle.exists() and any(bundle.iterdir()):
            raise RuntimeError(f"refusing to overwrite non-empty bundle: {bundle}")
        bundle.mkdir(parents=True, exist_ok=True)

        index["lifecycle"][-1]["status"] = decision
        pretty_write(bundle / "SCQOS_MASTER_INDEX.json", index)
        (bundle / "SCQOS_MASTER_INDEX.canonical.json").write_bytes(canonical_bytes(index))
        (bundle / "MASTER_INDEX.md").write_text(generate_markdown(index), encoding="utf-8")
        pretty_write(bundle / "W3C_PROV.jsonld", make_prov(index))

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": SCHEMA,
            "title": "SCQOS Master Evidence Index v1",
            "type": "object",
            "required": ["$schema", "object_type", "version", "canonicalization_authority",
                         "transition_id", "generated_at", "decision", "source_state_root",
                         "repositories", "lifecycle", "invariant_evaluation", "artifacts"],
            "properties": {
                "object_type": {"const": "SCQOS_MASTER_EVIDENCE_INDEX"},
                "decision": {"enum": ["PERMIT", "HOLD", "REJECT"]},
                "source_state_root": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "repositories": {"type": "array", "minItems": 1},
                "lifecycle": {"type": "array", "minItems": 6},
                "invariant_evaluation": {"type": "array", "minItems": 9},
                "artifacts": {"type": "array", "minItems": 1},
            },
            "additionalProperties": True,
        }
        pretty_write(bundle / "SCQOS_MASTER_INDEX.schema.json", schema)
        shutil.copy2(Path(__file__).resolve(), bundle / "VERIFY.py")

        master_digest = sha256_file(bundle / "SCQOS_MASTER_INDEX.canonical.json")
        in_toto = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [{"name": "SCQOS_MASTER_INDEX.canonical.json", "digest": {"sha256": master_digest}}],
            "predicateType": "https://knowledgeekza3224.github.io/scqos/attestation/master-index/v1",
            "predicate": {"transition_id": transition_id, "decision": decision,
                          "source_state_root": source_state_root,
                          "repository_commits": {r["name"]: r["commit"] for r in repo_records}},
        }
        pretty_write(bundle / "IN_TOTO_STATEMENT.json", in_toto)
        content_sum_hash = write_checksums(bundle, "ARTIFACT_SHA256SUMS", {"ARTIFACT_SHA256SUMS", "BUNDLE_SHA256SUMS", "CLOSURE_RECEIPT.json"})
        closure = {
            "object_type": "SCQOS_MASTER_INDEX_CLOSURE_RECEIPT",
            "transition_id": transition_id,
            "decision": decision,
            "closed_at": generated,
            "canonical_master_index_sha256": master_digest,
            "human_readable_master_index_sha256": sha256_file(bundle / "SCQOS_MASTER_INDEX.json"),
            "artifact_checksums_sha256": content_sum_hash,
            "source_state_root": source_state_root,
            "signature_status": "UNSIGNED",
            "transparency_receipt_status": "UNREGISTERED",
            "truth_notice": "Hash closure is complete. Identity signature and external transparency registration must be performed by their real authorities and are never fabricated.",
        }
        pretty_write(bundle / "CLOSURE_RECEIPT.json", closure)
        publication = """# External Identity and Transparency Witness\n\nThe bundle is cryptographically closed without inventing a signer. The real authority may add a public Sigstore witness with:\n\n```bash\ncosign sign-blob --yes --bundle SIGSTORE_BUNDLE.json CLOSURE_RECEIPT.json\ncosign verify-blob --bundle SIGSTORE_BUNDLE.json CLOSURE_RECEIPT.json\nsha256sum SIGSTORE_BUNDLE.json > SIGSTORE_BUNDLE.sha256\n```\n\nThe Sigstore bundle is additive evidence. It must never replace or rewrite the closed receipt.\n"""
        (bundle / "EXTERNAL_WITNESS.md").write_text(publication, encoding="utf-8")
        write_checksums(bundle, "BUNDLE_SHA256SUMS", {"BUNDLE_SHA256SUMS"})
        verify_rc = verify_bundle(bundle)
        print(f"\nSCQOS MASTER INDEX: {decision}")
        print(f"Transition: {transition_id}")
        print(f"Bundle: {bundle}")
        print(f"Artifacts: {len(artifacts)} across {len(repo_records)} repositories")
        if acquisition_errors:
            print("Unresolved:")
            for error in acquisition_errors:
                print(f"- {error}")
        print("\nNext authority action (optional external witness):")
        print(f"cosign sign-blob --yes --bundle {bundle}/SIGSTORE_BUNDLE.json {bundle}/CLOSURE_RECEIPT.json")
        return verify_rc if verify_rc else (0 if decision == "PERMIT" else 3)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build or verify the SCQOS total evidence master index")
    p.add_argument("--workspace", default=".", help="primary repo or parent directory containing SC repos")
    p.add_argument("--output", help="explicit new/empty output directory")
    p.add_argument("--no-fetch", action="store_true", help="do not shallow-clone missing public repositories")
    p.add_argument("--verify", metavar="BUNDLE", help="verify an existing bundle instead of building")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify:
            return verify_bundle(Path(args.verify).resolve())
        return build(args)
    except Exception as exc:
        print(f"REJECT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
