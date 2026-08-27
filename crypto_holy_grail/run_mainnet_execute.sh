#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "execute the frozen SCQOS XRPL Mainnet causal proof" \
  --expected-effect "reject the bound wrong transaction, validate its explicit control bypass, permit and validate the correct transaction, and close signed evidence" \
  --timeout 600 \
  -- .venv-crypto-proof/bin/python crypto_holy_grail/xrpl_mainnet_supreme_proof.py --execute --confirm-mainnet
