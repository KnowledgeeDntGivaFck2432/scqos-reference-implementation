#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 -m venv .venv-crypto-proof
.venv-crypto-proof/bin/python -m pip install -q --upgrade pip
.venv-crypto-proof/bin/python -m pip install -q -r crypto_holy_grail/requirements.txt
SCQOS_SECRET_KEY=public-proof-prepublication-test \
  .venv-crypto-proof/bin/python -m pytest -q crypto_holy_grail

SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "freeze, hash, publicly sign, independently verify, commit, and publish the completed live SCQOS XRPL Mainnet causal proof" \
  --expected-effect "publish a secret-free immutable evidence package whose Ed25519 signature, file hashes, receipt claims, live-ledger facts, Git commit, and remote GitHub branch all verify" \
  --timeout 900 \
  -- .venv-crypto-proof/bin/python crypto_holy_grail/scqos_freeze_publish.py publish

