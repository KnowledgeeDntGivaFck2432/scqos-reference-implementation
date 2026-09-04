# Shadow Clone

Shadow Clone activates the existing `SUPREME-MIND-59-FACULTY-UNIVERSE-V1` as
a recursively multiplying, internet-operating workforce governed by SCQOS.

The existing live architecture already proves:

- 59 faculties bound to one sovereign human principal.
- A canonical manifest frozen in S3.
- Shared state and receipts in DynamoDB.
- An SQS action plane.
- A Lambda governor that returns PERMIT, HOLD, or REJECT.

The existing runtime records admitted queued work as
`EXECUTOR_ADAPTER_NOT_REGISTERED`. Shadow Clone closes that specific circuit by
registering an executor backed by Amazon Bedrock AgentCore Harness and Browser.

## One-command deployment

Run from the repository root:

```bash
python3 -m venv .shadow-clone-venv && .shadow-clone-venv/bin/pip install --quiet boto3==1.43.82 && .shadow-clone-venv/bin/python tools/deploy_shadow_clone.py --publish
```

The command refuses to deploy if the local or live Supreme Mind manifest does
not match the recorded SHA-256 identity, if the role universe is not exactly 59,
or if the existing governor, tables, queue, or health state are not live.

It then:

1. Runs the deterministic eight-invariant clone protocol tests.
2. Builds and pushes a pinned, immutable browser container.
3. Creates a dedicated public-internet browser whose sessions are recorded to S3.
4. Deploys the SCQOS system prompt through AgentCore Harness.
5. Deploys the recursive Lambda executor.
6. Connects it to the existing Supreme Mind SQS action queue.
7. Executes a read-only qualification against a current official sports page.
8. Refuses PERMIT unless identity, live evidence, all eight invariants, coherence,
   the consequence receipt, and the browser recording agree.
9. Freezes the code, cloud identities, live result, recordings, and hashes in an evidence bundle.
10. Publishes only the Shadow Clone code and its evidence through an isolated Git worktree.

If local Docker/buildx is unavailable, the same command automatically performs
the immutable ARM64 container build in AWS CodeBuild.

## Execution boundary

Read-only faculties can research, inspect, analyze, forecast, draft, and propose
child clones autonomously. External mutations still require the existing
governor's registered tool contract, evidence, role authority, and any required
human authorization. A child clone can never bypass the same governor used by
its parent.

## Learning boundary

Every qualified consequence is appended to both the faculty's memory and the
59-faculty shared experience plane, so later clones inherit verified learning
in real time. Proposed model, policy, tool, authority, and constitutional changes
are stored as versioned HOLD candidates until independently requalified. This
allows continuous learning without silently replacing the authoritative state.
