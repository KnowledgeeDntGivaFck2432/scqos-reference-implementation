# SCQOS Public Execution Challenge v1

This deploys a public, rate-limited AWS endpoint that runs a frozen six-case
adversarial matrix through the SCQOS nine-gate kernel. Decisions are stored in
DynamoDB and signed by an AWS KMS asymmetric key. The endpoint is shadow-only:
it never executes the proposed external action.

## Launch from AWS CloudShell

From the repository root:

```bash
bash challenge/public_execution_challenge/deploy.sh
```

The script resolves the active AWS identity, builds a content-addressed Lambda
artifact, deploys the stack, runs the public matrix, fails if any expected
decision differs, and prints the public URL.

## Public routes

- `GET /` — executive challenge page
- `GET /v1/health` — deployed source and frozen contract identity
- `POST /v1/run-matrix` — six signed adversarial receipts
- `POST /v1/challenge` — one built-in case or a supplied transition
- `GET /v1/receipt/{receipt_id}` — retrieve an exact signed receipt
- `GET /v1/evidence` — live XRPL and cloud evidence snapshot
- `GET /v1/public-key` — DER-encoded KMS verification key

The frozen claim and its explicit boundary are in `contract.json`.
