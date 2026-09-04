#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
python3 -m venv .venv-crypto-proof
.venv-crypto-proof/bin/python -m pip install -q --upgrade pip
.venv-crypto-proof/bin/python -m pip install -q -r crypto_holy_grail/requirements.txt
SCQOS_SECRET_KEY=mainnet-proof-test-only \
  .venv-crypto-proof/bin/python -m pytest -q \
  crypto_holy_grail/test_scqos_full_terminal.py \
  crypto_holy_grail/test_scqos_crypto_proof.py \
  crypto_holy_grail/test_xrpl_mainnet_supreme_proof.py
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "prepare the frozen SCQOS XRPL Mainnet causal proof" \
  --expected-effect "create protected proof wallets and calculate the exact funding requirement from live Mainnet reserve and fee data" \
  --timeout 300 \
  -- .venv-crypto-proof/bin/python crypto_holy_grail/xrpl_mainnet_supreme_proof.py --prepare
