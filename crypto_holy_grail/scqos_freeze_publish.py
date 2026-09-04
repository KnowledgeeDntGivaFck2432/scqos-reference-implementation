#!/usr/bin/env python3
"""Freeze, sign, verify, and publish the completed live SCQOS causal proof.

No transaction is created or submitted here. The two already-validated XRPL
Mainnet transactions are queried from public ledger nodes and compared with the
locally authenticated SCQOS receipt. The resulting public package is hashed,
signed with Ed25519, independently verifiable, and committed without secrets.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from scqos_crypto_proof import canonical_bytes
from xrpl_mainnet_supreme_proof import MAINNET_RPC, public_result, request, server_snapshot


SCHEMA = "scqos.public-mainnet-proof.v1"
WRONG_TX = "C474989DFE4354CBB9A1F0B977BAF473EE91345DC6387F84C80F5A3B5F1110F9"
GOVERNED_TX = "D13EDAED96354DD2CF16382BA815367A37F5408D64B362FC24C19DEDF6775AD7"
EXPECTED_RECEIPT_HASH = (
    "ad27efd38fcc1ecbe2a6724283c316936d84f23ef71f35c71d2fa3e96f6234899"
    "e4d42b5753529614f131616f979de038296e0571d4ae41cde262761e96d975c"
)
PUBLIC_DIR = Path("evidence/crypto_holy_grail/public_mainnet_v1")
REPO_URL = "https://github.com/KnowledgeeKZA3224/scqos-reference-implementation"
PRIVATE_JSON_KEYS = {
    "api_secret",
    "destination_seed",
    "mnemonic",
    "passphrase",
    "private_key",
    "privatekey",
    "receipt_key",
    "secret",
    "seed",
    "source_seed",
}


def canonical(value: Any) -> bytes:
    return rfc8785.dumps(value)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def atomic_bytes(path: Path, value: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    atomic_bytes(path, (rendered + "\n").encode("utf-8"))


def run(command: Iterable[str], repo_root: Path, capture: bool = True) -> str:
    process = subprocess.run(
        list(command),
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if process.returncode:
        detail = ((process.stdout or "") + (process.stderr or "")).strip()
        raise RuntimeError(f"command failed ({process.returncode}): {detail}")
    return (process.stdout or "").strip()


def load_hmac_key(path: Path) -> bytes:
    path = path.expanduser()
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PermissionError(f"receipt HMAC key must be mode 600, found {mode:o}")
    return bytes.fromhex(path.read_text(encoding="ascii").strip())


def receipt_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in receipt.items()
        if key not in {"receipt_hash", "receipt_hmac_sha256"}
    }


def verify_local_receipt(receipt: Mapping[str, Any], key: bytes) -> None:
    body = receipt_body(receipt)
    encoded = canonical_bytes(body)
    observed_hash = hashlib.sha3_512(encoded).hexdigest()
    observed_hmac = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(receipt.get("receipt_hash", "")), observed_hash):
        raise ValueError("local SCQOS receipt hash is invalid")
    if not hmac.compare_digest(str(receipt.get("receipt_hmac_sha256", "")), observed_hmac):
        raise ValueError("local SCQOS receipt HMAC is invalid")
    if observed_hash != EXPECTED_RECEIPT_HASH:
        raise ValueError("receipt is authentic but is not the completed public Mainnet proof")


def receipt_transaction_hashes(receipt: Mapping[str, Any]) -> tuple[str, str]:
    wrong = receipt["wrong_transaction"]["same_exact_transaction_without_scqos"]
    valid = receipt["valid_transaction"]["validated_ledger_result"]
    return str(wrong["transaction_hash"]).upper(), str(valid["transaction_hash"]).upper()


def assert_receipt_claims(receipt: Mapping[str, Any]) -> None:
    wrong_hash, valid_hash = receipt_transaction_hashes(receipt)
    wrong = receipt["wrong_transaction"]
    valid = receipt["valid_transaction"]
    wrong_finding_codes = {
        finding.get("code") for finding in wrong["scqos_decision"].get("findings", [])
    }
    checks = {
        "schema": receipt.get("schema") == "scqos.xrpl-mainnet-supreme-proof.v1",
        "network": receipt.get("network") == "xrpl_mainnet",
        "wrong_hash": wrong_hash == WRONG_TX,
        "governed_hash": valid_hash == GOVERNED_TX,
        "wrong_intent_tag": wrong.get("intent_destination_tag") == 111,
        "wrong_actual_tag": wrong.get("actual_destination_tag") == 222,
        "wrong_scqos_reject": wrong["scqos_decision"].get("decision") == "REJECT",
        "wrong_reason": "DESTINATION_TAG_MISMATCH" in wrong_finding_codes,
        "wrong_ledger_success": (
            wrong["same_exact_transaction_without_scqos"].get("engine_result")
            == "tesSUCCESS"
        ),
        "wrong_validated": wrong["same_exact_transaction_without_scqos"].get("validated") is True,
        "valid_scqos_permit": valid["scqos_decision"].get("decision") == "PERMIT",
        "valid_ledger_success": (
            valid["validated_ledger_result"].get("engine_result") == "tesSUCCESS"
        ),
        "valid_validated": valid["validated_ledger_result"].get("validated") is True,
        "consequence_closed": valid["consequence_closure"].get("decision") == "PERMIT",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise AssertionError("receipt claims failed: " + ", ".join(failures))


def find_receipt(evidence_dir: Path, key: bytes) -> tuple[Path, dict[str, Any]]:
    errors: list[str] = []
    for path in sorted(evidence_dir.glob("mainnet_*.json"), reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            verify_local_receipt(value, key)
            assert_receipt_claims(value)
            return path, value
        except (KeyError, TypeError, ValueError, AssertionError, json.JSONDecodeError) as error:
            errors.append(f"{path.name}: {error}")
    detail = "; ".join(errors) if errors else "no mainnet_*.json receipts found"
    raise FileNotFoundError(f"completed Mainnet receipt not found: {detail}")


def live_transaction(client: Any, transaction_hash: str) -> dict[str, Any]:
    from xrpl.models.requests import Tx

    result = request(client, Tx(transaction=transaction_hash))
    if result is None:
        raise RuntimeError(f"transaction not found: {transaction_hash}")
    value = public_result(result, transaction_hash)
    if value["validated"] is not True or value["engine_result"] != "tesSUCCESS":
        raise AssertionError(f"transaction is not validated tesSUCCESS: {transaction_hash}")
    if str(value["transaction_hash"]).upper() != transaction_hash:
        raise AssertionError(f"XRPL returned the wrong transaction for {transaction_hash}")
    return value


def assert_live_causal_pair(wrong: Mapping[str, Any], governed: Mapping[str, Any]) -> None:
    checks = {
        "source_present": bool(wrong.get("account")),
        "destination_present": bool(wrong.get("destination")),
        "same_source": wrong.get("account") == governed.get("account"),
        "same_destination": wrong.get("destination") == governed.get("destination"),
        "wrong_tag_222": wrong.get("destination_tag") == 222,
        "governed_tag_111": governed.get("destination_tag") == 111,
        "both_payments": (
            wrong.get("transaction_type")
            == governed.get("transaction_type")
            == "Payment"
        ),
        "both_validated": (
            wrong.get("validated") is True and governed.get("validated") is True
        ),
        "both_ledger_success": (
            wrong.get("engine_result")
            == governed.get("engine_result")
            == "tesSUCCESS"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise AssertionError("live causal pair failed: " + ", ".join(failures))


def assert_live_matches_receipt(
    receipt: Mapping[str, Any], wrong: Mapping[str, Any], governed: Mapping[str, Any]
) -> None:
    receipt_wrong = receipt["wrong_transaction"]["same_exact_transaction_without_scqos"]
    receipt_governed = receipt["valid_transaction"]["validated_ledger_result"]
    wallets = receipt["public_wallets"]
    checks = {
        "source_matches_receipt": (
            wrong.get("account") == governed.get("account") == wallets.get("source")
        ),
        "destination_matches_receipt": (
            wrong.get("destination")
            == governed.get("destination")
            == wallets.get("destination")
        ),
        "wrong_hash_matches_receipt": (
            str(wrong.get("transaction_hash", "")).upper()
            == str(receipt_wrong.get("transaction_hash", "")).upper()
        ),
        "governed_hash_matches_receipt": (
            str(governed.get("transaction_hash", "")).upper()
            == str(receipt_governed.get("transaction_hash", "")).upper()
        ),
        "wrong_amount_matches_receipt": (
            str(wrong.get("amount")) == str(receipt_wrong.get("amount"))
        ),
        "governed_amount_matches_receipt": (
            str(governed.get("amount")) == str(receipt_governed.get("amount"))
        ),
        "wrong_tag_matches_receipt": (
            wrong.get("destination_tag") == receipt_wrong.get("destination_tag")
        ),
        "governed_tag_matches_receipt": (
            governed.get("destination_tag") == receipt_governed.get("destination_tag")
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise AssertionError("live data does not match receipt: " + ", ".join(failures))


def load_or_create_signing_key(path: Path) -> Ed25519PrivateKey:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise PermissionError(f"signing key must be mode 600: {path}")
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("configured evidence key is not Ed25519")
        return key
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    atomic_bytes(path, pem, mode=0o600)
    return key


def public_key_pem(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _find_private_json_key(value: Any, path: str = "$") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in PRIVATE_JSON_KEYS:
                return f"{path}.{key_text}"
            found = _find_private_json_key(item, f"{path}.{key_text}")
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_private_json_key(item, f"{path}[{index}]")
            if found:
                return found
    return None


def assert_public_files_secret_free(paths: Iterable[Path]) -> None:
    private_pem = re.compile(br"-----BEGIN (?:EC |RSA |OPENSSH )?PRIVATE KEY-----")
    for path in paths:
        raw = path.read_bytes()
        if private_pem.search(raw):
            raise PermissionError(f"private key material found in public file: {path}")
        if path.suffix.lower() == ".json":
            found = _find_private_json_key(json.loads(raw.decode("utf-8")))
            if found:
                raise PermissionError(f"private JSON field {found} found in {path}")


def manifest_signature(manifest: Mapping[str, Any], private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(canonical(manifest))).decode("ascii")


def verify_manifest_signature(
    manifest: Mapping[str, Any], signature_b64: str, public_key: Ed25519PublicKey
) -> None:
    public_key.verify(base64.b64decode(signature_b64, validate=True), canonical(manifest))


def build_readme(receipt: Mapping[str, Any]) -> str:
    source = receipt["public_wallets"]["source"]
    destination = receipt["public_wallets"]["destination"]
    return f"""# Frozen SCQOS XRPL Mainnet Causal Proof v1

This package records one controlled, minimal-cost experiment on XRPL Mainnet.
The public ledger accepted a cryptographically valid transaction whose destination
tag contradicted the declared intent. SCQOS rejected those exact transaction
semantics before signing. SCQOS then permitted the corrected transaction, which
the public ledger validated. Both wallets were controlled by the same operator;
the transferred XRP remained under that operator's control and only network fees
were destroyed.

This proves the narrow tested claim: for this Payment error class, the ledger's
cryptographic validity did not protect intent, while the SCQOS pre-signing gate
detected the contradiction and prevented its governed execution. It is not, by
itself, proof that all cryptocurrency error classes are solved.

- Source: `{source}`
- Destination: `{destination}`
- Wrong control (ledger accepted): https://livenet.xrpl.org/transactions/{WRONG_TX}
- Correct governed transaction: https://livenet.xrpl.org/transactions/{GOVERNED_TX}

Independent local verification:

```bash
.venv-crypto-proof/bin/python crypto_holy_grail/scqos_freeze_publish.py verify --live
```

Verification checks the Ed25519 signature, every frozen file hash, both immutable
transaction hashes against a live XRPL Mainnet node, and the causal assertions in
the authenticated SCQOS receipt. No private key is required.
"""


def freeze(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    release_dir = repo_root / args.public_dir
    manifest_path = release_dir / "manifest.json"
    if manifest_path.exists():
        result = verify_release(repo_root, args.public_dir, live=True)
        return {"status": "REUSED_VERIFIED_FREEZE", **result}

    receipt_key = load_hmac_key(Path(args.receipt_key))
    receipt_path, receipt = find_receipt(repo_root / args.evidence_dir, receipt_key)

    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import Ledger, ServerState
    from xrpl.utils import ripple_time_to_posix

    api = {
        "Ledger": Ledger,
        "ServerState": ServerState,
        "ripple_time_to_posix": ripple_time_to_posix,
    }
    client = JsonRpcClient(args.rpc)
    snapshot = server_snapshot(client, api)
    wrong_live = live_transaction(client, WRONG_TX)
    governed_live = live_transaction(client, GOVERNED_TX)
    assert_live_causal_pair(wrong_live, governed_live)
    assert_live_matches_receipt(receipt, wrong_live, governed_live)

    release_dir.mkdir(parents=True, exist_ok=False)
    public_receipt = release_dir / "authenticated_scqos_receipt.json"
    live_snapshot = release_dir / "live_xrpl_revalidation.json"
    readme_path = release_dir / "README.md"
    public_key_path = release_dir / "ed25519_public_key.pem"

    atomic_json(public_receipt, receipt)
    live_value = {
        "schema": "scqos.xrpl-live-revalidation.v1",
        "observed_at": time.time(),
        "rpc": args.rpc,
        "network": "xrpl_mainnet",
        "network_id": snapshot["network_id"],
        "validated_ledger": {
            "index": snapshot["ledger_index"],
            "hash": snapshot["ledger_hash"],
            "closed_at": snapshot["ledger_closed_at"],
        },
        "wrong_control_transaction": wrong_live,
        "governed_transaction": governed_live,
    }
    atomic_json(live_snapshot, live_value)
    atomic_bytes(readme_path, build_readme(receipt).encode("utf-8"))

    signing_key = load_or_create_signing_key(Path(args.signing_key))
    atomic_bytes(public_key_path, public_key_pem(signing_key.public_key()))
    frozen_files = [public_receipt, live_snapshot, readme_path, public_key_path]
    assert_public_files_secret_free(frozen_files)
    implementation_files = sorted((repo_root / "crypto_holy_grail").glob("*.py"))
    implementation_files += sorted((repo_root / "crypto_holy_grail").glob("*.sh"))
    implementation_files += [
        repo_root / "crypto_holy_grail/README.md",
        repo_root / "crypto_holy_grail/requirements.txt",
    ]

    manifest = {
        "schema": SCHEMA,
        "proof_status": "COMPLETE",
        "frozen_at": time.time(),
        "network": "XRPL Mainnet",
        "network_id": 0,
        "claim_boundary": (
            "SCQOS prevented the governed execution of the tested destination-tag "
            "intent contradiction while XRPL Mainnet accepted the exact ungoverned control."
        ),
        "causal_result": {
            "wrong_transaction_without_scqos": "tesSUCCESS",
            "same_exact_wrong_transaction_with_scqos": "REJECT",
            "correct_transaction_with_scqos": "PERMIT",
            "correct_transaction_validated": True,
            "consequence_closed": "PERMIT",
        },
        "transactions": {
            "wrong_control": {
                "hash": WRONG_TX,
                "explorer": f"https://livenet.xrpl.org/transactions/{WRONG_TX}",
            },
            "governed_correct": {
                "hash": GOVERNED_TX,
                "explorer": f"https://livenet.xrpl.org/transactions/{GOVERNED_TX}",
            },
        },
        "local_authentication": {
            "hmac_verified_before_publication": True,
            "receipt_hash_sha3_512": receipt["receipt_hash"],
            "private_hmac_key_published": False,
            "source_receipt_filename": receipt_path.name,
        },
        "public_authentication": {
            "algorithm": "Ed25519",
            "signature_encoding": "base64",
            "canonicalization": "RFC 8785 JCS",
        },
        "evidence_files_sha256": {
            path.relative_to(release_dir).as_posix(): sha256_file(path) for path in frozen_files
        },
        "implementation_files_sha256": {
            path.relative_to(repo_root).as_posix(): sha256_file(path)
            for path in implementation_files
        },
        "repository": REPO_URL,
    }
    atomic_json(manifest_path, manifest)
    signature = manifest_signature(manifest, signing_key)
    atomic_bytes(release_dir / "manifest.ed25519.sig", (signature + "\n").encode("ascii"))
    atomic_bytes(
        release_dir / "manifest.sha256",
        f"{sha256_file(manifest_path)}  manifest.json\n".encode("ascii"),
    )
    all_public_files = sorted(path for path in release_dir.iterdir() if path.is_file())
    assert_public_files_secret_free(all_public_files)
    verification = verify_release(repo_root, args.public_dir, live=False)
    return {"status": "CREATED_VERIFIED_FREEZE", **verification}


def verify_release(repo_root: Path, public_dir: Path, live: bool) -> dict[str, Any]:
    release_dir = repo_root / public_dir
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("proof_status") != "COMPLETE":
        raise AssertionError("manifest schema or completion status is invalid")
    signature = (release_dir / "manifest.ed25519.sig").read_text(encoding="ascii").strip()
    public_key = serialization.load_pem_public_key((release_dir / "ed25519_public_key.pem").read_bytes())
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("public evidence key is not Ed25519")
    verify_manifest_signature(manifest, signature, public_key)
    for relative, expected in manifest["evidence_files_sha256"].items():
        path = release_dir / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise AssertionError(f"frozen file hash mismatch: {relative}")
    for relative, expected in manifest["implementation_files_sha256"].items():
        path = repo_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise AssertionError(f"implementation file hash mismatch: {relative}")
    checksum_line = (release_dir / "manifest.sha256").read_text(encoding="ascii").strip()
    if checksum_line != f"{sha256_file(release_dir / 'manifest.json')}  manifest.json":
        raise AssertionError("manifest SHA-256 mismatch")
    expected_release_files = {
        "README.md",
        "authenticated_scqos_receipt.json",
        "ed25519_public_key.pem",
        "live_xrpl_revalidation.json",
        "manifest.ed25519.sig",
        "manifest.json",
        "manifest.sha256",
    }
    observed_release_files = {
        path.name for path in release_dir.iterdir() if path.is_file()
    }
    if observed_release_files != expected_release_files:
        raise AssertionError("public release contains missing or unexpected files")
    receipt = json.loads(
        (release_dir / "authenticated_scqos_receipt.json").read_text(encoding="utf-8")
    )
    if receipt.get("receipt_hash") != EXPECTED_RECEIPT_HASH:
        raise AssertionError("frozen receipt is not the expected Mainnet receipt")
    assert_receipt_claims(receipt)
    frozen_live = json.loads(
        (release_dir / "live_xrpl_revalidation.json").read_text(encoding="utf-8")
    )
    frozen_wrong = frozen_live["wrong_control_transaction"]
    frozen_governed = frozen_live["governed_transaction"]
    assert_live_causal_pair(frozen_wrong, frozen_governed)
    assert_live_matches_receipt(receipt, frozen_wrong, frozen_governed)
    if live:
        from xrpl.clients import JsonRpcClient

        client = JsonRpcClient(MAINNET_RPC)
        wrong = live_transaction(client, WRONG_TX)
        governed = live_transaction(client, GOVERNED_TX)
        assert_live_causal_pair(wrong, governed)
        assert_live_matches_receipt(receipt, wrong, governed)
    return {
        "SCQOS_PUBLIC_PROOF": "VERIFIED",
        "manifest_sha256": sha256_file(release_dir / "manifest.json"),
        "ed25519_signature_valid": True,
        "all_frozen_file_hashes_valid": True,
        "receipt_claims_valid": True,
        "live_ledger_revalidated": live,
        "wrong_control_transaction": WRONG_TX,
        "governed_transaction": GOVERNED_TX,
    }


def remote_branch_exists(repo_root: Path, branch: str) -> bool:
    process = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode not in {0, 2}:
        detail = (process.stdout + process.stderr).strip()
        raise RuntimeError(f"could not inspect remote branch: {detail}")
    return process.returncode == 0


def assert_publishable_repo(repo_root: Path) -> str:
    branch = run(["git", "branch", "--show-current"], repo_root)
    if not branch:
        raise RuntimeError("publication requires a named branch; detached HEAD is blocked")
    run(["git", "check-ref-format", "--branch", branch], repo_root)
    origin = run(["git", "remote", "get-url", "origin"], repo_root)
    accepted = {
        "https://github.com/KnowledgeeKZA3224/scqos-reference-implementation.git",
        "git@github.com:KnowledgeeKZA3224/scqos-reference-implementation.git",
    }
    if origin not in accepted:
        raise RuntimeError(f"unexpected origin; publication blocked: {origin}")
    if remote_branch_exists(repo_root, branch):
        run(["git", "fetch", "origin", branch], repo_root)
        behind = int(
            run(
                ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
                repo_root,
            )
            or "0"
        )
        if behind:
            raise RuntimeError(
                f"local {branch} is {behind} commit(s) behind origin/{branch}; "
                "publication held"
            )
    return branch


def publish(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    branch = assert_publishable_repo(repo_root)
    freeze_result = freeze(repo_root, args)
    release_dir = repo_root / args.public_dir
    source_paths = sorted((repo_root / "crypto_holy_grail").glob("*.py"))
    source_paths += sorted((repo_root / "crypto_holy_grail").glob("*.sh"))
    source_paths += [
        repo_root / "crypto_holy_grail/README.md",
        repo_root / "crypto_holy_grail/requirements.txt",
    ]
    public_paths = sorted(path for path in release_dir.iterdir() if path.is_file())
    assert_public_files_secret_free(public_paths)
    stage = [repo_root / ".gitignore", *source_paths, *public_paths]
    relative = [path.relative_to(repo_root).as_posix() for path in stage if path.exists()]
    run(["git", "add", "--", *relative], repo_root)
    staged = run(["git", "diff", "--cached", "--name-only"], repo_root).splitlines()
    permitted = set(relative)
    unexpected = sorted(set(staged) - permitted)
    if unexpected:
        raise PermissionError("unexpected staged paths blocked: " + ", ".join(unexpected))
    if staged:
        run(["git", "commit", "-m", "Publish live XRPL Mainnet SCQOS causal proof"], repo_root)
    commit = run(["git", "rev-parse", "HEAD"], repo_root)
    run(
        ["git", "push", "--set-upstream", "origin", f"HEAD:{branch}"],
        repo_root,
        capture=False,
    )
    remote_commit = run(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"], repo_root
    ).split()[0]
    if remote_commit != commit:
        raise AssertionError("remote branch does not match the frozen publication commit")
    return {
        "SCQOS_FREEZE_HASH_PUBLISH": "COMPLETE",
        "git_branch": branch,
        "git_commit": commit,
        "github_commit": f"{REPO_URL}/commit/{commit}",
        "github_evidence": f"{REPO_URL}/tree/{commit}/{args.public_dir.as_posix()}",
        **freeze_result,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Freeze and publish the live SCQOS proof")
    value.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    value.add_argument("--evidence-dir", type=Path, default=Path("evidence/crypto_holy_grail"))
    value.add_argument("--receipt-key", default="~/.config/scqos/xrpl_mainnet_proof_hmac.key")
    value.add_argument("--signing-key", default="~/.config/scqos/evidence_signing_ed25519.pem")
    value.add_argument("--rpc", default=MAINNET_RPC)
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze")
    verify = commands.add_parser("verify")
    verify.add_argument("--live", action="store_true")
    commands.add_parser("publish")
    return value


def main() -> int:
    args = parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if args.command == "freeze":
        result = freeze(repo_root, args)
    elif args.command == "verify":
        result = verify_release(repo_root, args.public_dir, live=args.live)
    else:
        result = publish(repo_root, args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
