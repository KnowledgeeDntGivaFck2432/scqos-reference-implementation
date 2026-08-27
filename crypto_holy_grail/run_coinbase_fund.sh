#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
key_file="${1:-/home/knowledgee-kza/Downloads/coinbase_transfer_key.json}"
.venv-crypto-proof/bin/python -m pip install -q -r crypto_holy_grail/requirements.txt
SCQOS_SECRET_KEY=coinbase-funding-test-only \
  .venv-crypto-proof/bin/python -m pytest -q \
  crypto_holy_grail/test_scqos_full_terminal.py \
  crypto_holy_grail/test_scqos_crypto_proof.py \
  crypto_holy_grail/test_xrpl_mainnet_supreme_proof.py \
  crypto_holy_grail/test_scqos_coinbase_fund.py
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "fund the frozen SCQOS XRPL Mainnet proof source from the owner's Coinbase XRP account" \
  --expected-effect "exactly 2.100200 XRP reaches the bound locally controlled XRPL Mainnet proof address with no destination tag and durable evidence" \
  --timeout 300 \
  -- .venv-crypto-proof/bin/python crypto_holy_grail/scqos_coinbase_fund.py \
  --key-file "$key_file" --confirm SEND-2.100200-XRP
