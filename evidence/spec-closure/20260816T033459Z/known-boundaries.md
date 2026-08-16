# Known Boundaries at Specification Freeze Preparation

## Unicode normalization

The prior SCQOS canonicalization path serialized Unicode as UTF-8 but did
not normatively pin NFC normalization.

Independent verifier Nikolai Nedovodin identified this boundary on
2026-08-15.

SCQOS Canonicalization Contract v1.0 closes the specification-level
ambiguity by requiring recursive NFC normalization and fail-closed
rejection of normalized property-name collisions.

## Implementation migration

Existing historical receipts remain evidence under the canonicalization
behavior that produced them.

The new specification MUST NOT retroactively rewrite or reinterpret
historical digests.

A current implementation may claim conformance to
SCQOS-C14N-JCS-NFC-1 only after independent conformance testing against
specification-derived vectors.
