from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import scqos_freeze_publish as publication
from scqos_crypto_proof import canonical_bytes


def synthetic_receipt() -> tuple[dict, bytes]:
    key = bytes.fromhex("11" * 32)
    body = {
        "schema": "scqos.xrpl-mainnet-supreme-proof.v1",
        "network": "xrpl_mainnet",
        "public_wallets": {"source": "rSource", "destination": "rDestination"},
        "wrong_transaction": {
            "intent_destination_tag": 111,
            "actual_destination_tag": 222,
            "scqos_decision": {
                "decision": "REJECT",
                "findings": [{"code": "DESTINATION_TAG_MISMATCH"}],
            },
            "same_exact_transaction_without_scqos": {
                "transaction_hash": publication.WRONG_TX,
                "engine_result": "tesSUCCESS",
                "validated": True,
                "account": "rSource",
                "destination": "rDestination",
                "destination_tag": 222,
                "amount": "2100000",
                "transaction_type": "Payment",
            },
        },
        "valid_transaction": {
            "scqos_decision": {"decision": "PERMIT"},
            "validated_ledger_result": {
                "transaction_hash": publication.GOVERNED_TX,
                "engine_result": "tesSUCCESS",
                "validated": True,
                "account": "rSource",
                "destination": "rDestination",
                "destination_tag": 111,
                "amount": "1",
                "transaction_type": "Payment",
            },
            "consequence_closure": {"decision": "PERMIT"},
        },
    }
    encoded = canonical_bytes(body)
    receipt = {
        **body,
        "receipt_hash": hashlib.sha3_512(encoded).hexdigest(),
        "receipt_hmac_sha256": hmac.new(key, encoded, hashlib.sha256).hexdigest(),
    }
    return receipt, key


def test_receipt_hmac_and_claims_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt, key = synthetic_receipt()
    monkeypatch.setattr(publication, "EXPECTED_RECEIPT_HASH", receipt["receipt_hash"])
    publication.verify_local_receipt(receipt, key)
    publication.assert_receipt_claims(receipt)


def test_receipt_mutation_fails_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt, key = synthetic_receipt()
    monkeypatch.setattr(publication, "EXPECTED_RECEIPT_HASH", receipt["receipt_hash"])
    mutated = copy.deepcopy(receipt)
    mutated["wrong_transaction"]["actual_destination_tag"] = 999
    with pytest.raises(ValueError, match="hash is invalid"):
        publication.verify_local_receipt(mutated, key)


def test_ed25519_manifest_signature_is_publicly_verifiable() -> None:
    private_key = Ed25519PrivateKey.generate()
    manifest = {"schema": publication.SCHEMA, "proof_status": "COMPLETE"}
    signature = publication.manifest_signature(manifest, private_key)
    publication.verify_manifest_signature(manifest, signature, private_key.public_key())
    with pytest.raises(Exception):
        publication.verify_manifest_signature(
            {**manifest, "proof_status": "MUTATED"}, signature, private_key.public_key()
        )


def test_public_secret_scanner_rejects_wallet_seed(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"source_seed": "sNotPublic"}), encoding="utf-8")
    with pytest.raises(PermissionError, match="private JSON field"):
        publication.assert_public_files_secret_free([path])


def test_live_pair_semantics_require_exact_tags() -> None:
    common = {
        "account": "rSource",
        "destination": "rDestination",
        "transaction_type": "Payment",
        "validated": True,
        "engine_result": "tesSUCCESS",
    }
    publication.assert_live_causal_pair(
        {**common, "destination_tag": 222},
        {**common, "destination_tag": 111},
    )


def test_complete_frozen_release_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, _ = synthetic_receipt()
    monkeypatch.setattr(publication, "EXPECTED_RECEIPT_HASH", receipt["receipt_hash"])
    release = tmp_path / publication.PUBLIC_DIR
    source = tmp_path / "crypto_holy_grail/proof.py"
    source.parent.mkdir(parents=True)
    source.write_text("PROOF = 'SCQOS'\n", encoding="utf-8")
    release.mkdir(parents=True)
    publication.atomic_json(release / "authenticated_scqos_receipt.json", receipt)
    live_common = {
        "account": "rSource",
        "destination": "rDestination",
        "transaction_type": "Payment",
        "validated": True,
        "engine_result": "tesSUCCESS",
    }
    publication.atomic_json(
        release / "live_xrpl_revalidation.json",
        {
            "network_id": 0,
            "wrong_control_transaction": {
                **live_common,
                "transaction_hash": publication.WRONG_TX,
                "destination_tag": 222,
                "amount": "2100000",
            },
            "governed_transaction": {
                **live_common,
                "transaction_hash": publication.GOVERNED_TX,
                "destination_tag": 111,
                "amount": "1",
            },
        },
    )
    (release / "README.md").write_text("frozen proof\n", encoding="utf-8")
    key = Ed25519PrivateKey.generate()
    (release / "ed25519_public_key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    evidence_names = [
        "authenticated_scqos_receipt.json",
        "live_xrpl_revalidation.json",
        "README.md",
        "ed25519_public_key.pem",
    ]
    manifest = {
        "schema": publication.SCHEMA,
        "proof_status": "COMPLETE",
        "evidence_files_sha256": {
            name: publication.sha256_file(release / name) for name in evidence_names
        },
        "implementation_files_sha256": {
            "crypto_holy_grail/proof.py": publication.sha256_file(source)
        },
    }
    publication.atomic_json(release / "manifest.json", manifest)
    (release / "manifest.ed25519.sig").write_text(
        publication.manifest_signature(manifest, key) + "\n", encoding="ascii"
    )
    (release / "manifest.sha256").write_text(
        f"{publication.sha256_file(release / 'manifest.json')}  manifest.json\n",
        encoding="ascii",
    )
    result = publication.verify_release(tmp_path, publication.PUBLIC_DIR, live=False)
    assert result["SCQOS_PUBLIC_PROOF"] == "VERIFIED"
    assert result["ed25519_signature_valid"] is True


def test_publication_preserves_current_named_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    branch = "scqos-c14n-jcs-rfc1-conformance-migration"

    def fake_run(command, repo_root, capture=True):
        assert repo_root == tmp_path
        if command == ["git", "branch", "--show-current"]:
            return branch
        if command == ["git", "remote", "get-url", "origin"]:
            return "https://github.com/KnowledgeeKZA3224/scqos-reference-implementation.git"
        if command == ["git", "check-ref-format", "--branch", branch]:
            return ""
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(publication, "run", fake_run)
    monkeypatch.setattr(publication, "remote_branch_exists", lambda root, name: False)
    assert publication.assert_publishable_repo(tmp_path) == branch
