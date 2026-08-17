# Supreme Computation — Physical Quantum Evidence Package

## Public claim represented by this package

The execution recovered results associated with four AWS Braket
physical Rigetti QPU tasks.

Displayed execution summary:

- Physical QPU: Rigetti Cepheus-1-108Q
- Simulator used: NO
- Physical tasks recovered: 4 / 4
- Total shots: 2,000
- Observed CHSH |S|: 2.364
- Classical bound: 2.0
- Reported significance above bound: 5.07 sigma
- Final pipeline verdict: PASS_PHYSICAL_QUANTUM_PROOF

## What is included

FULL_BRAKET_TASK_ARNS.txt
    Complete task identifiers recovered from local evidence.

SHA256SUMS.txt
    SHA-256 hashes of the packaged artifacts.

sc-final-physical-quantum-proof.json
    Final proof receipt, when found locally.

Additional JSON artifacts
    Existing quantum/proof/receipt artifacts discovered locally.

## Independent verification

1. Inspect FULL_BRAKET_TASK_ARNS.txt.
2. Confirm that the task identifiers correspond to the claimed AWS Braket jobs
   using an AWS account with authorization to inspect those tasks.
3. Inspect the packaged result/receipt artifacts.
4. Recompute the CHSH correlations from the recorded measurement counts.
5. Recompute S and compare |S| with the classical bound of 2.
6. Recompute the SHA-256 hashes.
7. Compare them with SHA256SUMS.txt and the hashes recorded by the proof.
8. Verify that the evidence supports the claimed pipeline verdict.

IMPORTANT:
A SHA-256 digest proves byte identity/integrity of the hashed artifact.
It does not by itself prove the physical origin or correctness of the
underlying experiment. Physical provenance should be checked against
the corresponding AWS Braket task metadata/results.

Nothing in this packaging step submits a new quantum task.
