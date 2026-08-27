# Frozen SCQOS XRPL Mainnet Causal Proof v1

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

- Source: `rwEZsqSjFHR3Q6cxUefCA5WRfVe6HsjrNL`
- Destination: `r4sGL5ZnpHdfoCF3ioFdcux1VhaxziFMP6`
- Wrong control (ledger accepted): https://livenet.xrpl.org/transactions/C474989DFE4354CBB9A1F0B977BAF473EE91345DC6387F84C80F5A3B5F1110F9
- Correct governed transaction: https://livenet.xrpl.org/transactions/D13EDAED96354DD2CF16382BA815367A37F5408D64B362FC24C19DEDF6775AD7

Independent local verification:

```bash
.venv-crypto-proof/bin/python crypto_holy_grail/scqos_freeze_publish.py verify --live
```

Verification checks the Ed25519 signature, every frozen file hash, both immutable
transaction hashes against a live XRPL Mainnet node, and the causal assertions in
the authenticated SCQOS receipt. No private key is required.
