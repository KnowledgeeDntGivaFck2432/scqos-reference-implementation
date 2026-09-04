#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 -m venv .venv-crypto-proof
.venv-crypto-proof/bin/python -m pip install -q --upgrade pip
.venv-crypto-proof/bin/python -m pip install -q -r crypto_holy_grail/requirements.txt
.venv-crypto-proof/bin/python -m pytest -q crypto_holy_grail/test_scqos_crypto_proof.py
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/xrpl_live_testnet.py \
  --confirm-testnet-control
