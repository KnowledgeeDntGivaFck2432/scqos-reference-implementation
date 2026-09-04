# SCQOS Live Sports Analysis

This package turns the qualified Shadow Clone internet body into a phone-ready,
receipt-verified MLB moneyline analysis application inside the existing AWS
account.

## What the product does

1. The web app submits an MLB date or matchup to the existing 59-faculty
   Supreme Mind governor.
2. Role R15 uses the AgentCore Harness and recorded Browser to observe the
   official MLB schedule and current DraftKings MLB moneyline page.
3. The model returns direct source observations and five bounded probability
   estimates. It does **not** make the final decision.
4. `contract.py` deterministically calculates American-odds implied
   probability, no-vig market probability, model consensus, edge, evidence
   completeness, all eight invariant states, and `EXECUTE`, `HOLD`, or
   `REJECT`.
5. The executor stores the raw analysis and deterministic decision inside the
   signed DynamoDB consequence receipt.
6. The API re-computes both hashes before showing a result. A mismatch fails
   closed.

`EXECUTE` means an analysis candidate only. This product never places or
prepares a wager.

## Deterministic gates

- edge: at least 7%
- evidence completeness: at least 85% (the five-category contract makes this
  all five required categories)
- model agreement: at least 80% across at least five models
- current DraftKings market observation: no older than 10 minutes
- every one of the eight invariants: proven
- unresolved risk flags: none

## One-command deployment

Run from the repository root with the already-created Shadow Clone virtual
environment:

```bash
.shadow-clone-venv/bin/python tools/deploy_sports_analysis.py --publish
```

The deployer preserves the existing Harness and executor configuration,
installs the deterministic contract, creates or updates the Lambda Function URL
web app, rotates its access key, executes one live qualification through the
public HTTPS endpoint, verifies the DynamoDB consequence and decision hashes,
stores evidence in the existing S3 evidence plane, and publishes only after all
gates pass.

The final output prints the app URL and the new access key. Save that key; only
its SHA-256 digest is stored in AWS or evidence.
