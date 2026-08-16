# SCQOS Canonicalization Falsification Vectors

These vectors are derived from the normative specification.

The SCQOS reference implementation MUST NOT be used to determine an
expected value.

For every accepted vector, an evaluator must:

1. Derive the expected canonical text from the specification and its
   incorporated standards.
2. Record the expected UTF-8 bytes.
3. Record SHA-256 of those bytes.
4. Freeze the expected result.
5. Only then execute an implementation.
6. Compare implementation output against the frozen expected result.

For every rejected vector, the evaluator must freeze the expected
failure class before executing an implementation.

If the expected answer cannot be determined without executing SCQOS
source code, the specification is HOLD.
