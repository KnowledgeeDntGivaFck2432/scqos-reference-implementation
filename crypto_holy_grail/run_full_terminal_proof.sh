#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 -m venv .venv-crypto-proof
.venv-crypto-proof/bin/python -m pip install -q --upgrade pip
.venv-crypto-proof/bin/python -m pip install -q -r crypto_holy_grail/requirements.txt
SCQOS_SECRET_KEY=full-terminal-test-only \
  .venv-crypto-proof/bin/python -m pytest -q crypto_holy_grail/test_scqos_full_terminal.py
expected_hash="$(printf 'SCQOS_FULL_TERMINAL_OK\n' | sha256sum | cut -d' ' -f1)"
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "prove unrestricted owner-authorized terminal execution" \
  --expected-effect "exact command executes and returns the bound output" \
  --expected-stdout-sha256 "$expected_hash" \
  -- .venv-crypto-proof/bin/python -c "print('SCQOS_FULL_TERMINAL_OK')"
