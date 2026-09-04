# SCQOS Cryptocurrency Holy Grail Proof

This is an exchange-independent pre-signing safety boundary. It tests whether a
cryptocurrency transaction remains coherent across intent, authority, policy,
wallet identity, live chain evidence, transaction construction, signing,
validated consequence, and durable proof.

The current first stage is a closed XRPL Payment fault universe. It has one valid
PERMIT control and named HOLD or REJECT mutations for every governed input. No
real or test cryptocurrency is moved by this stage.

Run from the repository root:

```bash
python3 -m venv .venv-crypto-proof
.venv-crypto-proof/bin/pip install -r crypto_holy_grail/requirements.txt
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/scqos_crypto_proof.py --matrix
```

The process exits nonzero if any fault is accidentally permitted or returns the
wrong governed decision. A signed JSON receipt is written under
`evidence/crypto_holy_grail/`.

Run the live Testnet causal experiment only after the matrix passes:

```bash
SCQOS_KERNEL_MODULE=scqos_supreme_stack \
  .venv-crypto-proof/bin/python crypto_holy_grail/xrpl_live_testnet.py \
  --confirm-testnet-control
```

The live runner creates disposable Testnet wallets without printing or persisting
their seeds. It proves the exact prepared wrong transaction is executable when
the test-only control deliberately bypasses governance, blocked before signing
when governed, and that the correct control is permitted and reaches a validated
ledger. The experiment uses 2 drops of valueless Testnet XRP.

Or install, test, run the matrix, and run the live experiment in one command:

```bash
bash crypto_holy_grail/run_proof.sh
```

Run the full-authority SCQOS terminal proof:

```bash
bash crypto_holy_grail/run_full_terminal_proof.sh
```

Run any owner-authorized command through SCQOS:

```bash
.venv-crypto-proof/bin/python crypto_holy_grail/scqos_full_terminal.py \
  --objective "describe the exact purpose" \
  --expected-effect "describe the exact consequence" \
  -- command argument1 argument2
```

Use `--shell "..."` instead of `-- ...` when the exact command needs Bash
features such as pipes or redirection. The gateway has no read-only policy and no
application allowlist; the current operating-system identity remains the authority.

## Freeze and publish the completed Mainnet proof

After the live XRPL Mainnet experiment prints
`SCQOS_MAINNET_SUPREME_PROOF: COMPLETE`, freeze its authenticated receipt,
revalidate both public transaction hashes against live ledger data, run the full
test suite, generate a persistent Ed25519 evidence identity, hash and sign the
public package, verify it, commit only the source and secret-free evidence, push
the current named branch without switching branches, and confirm the remote
commit with:

```bash
bash crypto_holy_grail/run_freeze_publish.sh
```

This publication command creates no transaction and moves no cryptocurrency.
The HMAC receipt key, Ed25519 private key, wallet seeds, Coinbase keys, virtual
environment, terminal receipts, and mutable local audit logs are never staged.
Anyone can independently verify the frozen package and live transactions with:

```bash
.venv-crypto-proof/bin/python crypto_holy_grail/scqos_freeze_publish.py verify --live
```
