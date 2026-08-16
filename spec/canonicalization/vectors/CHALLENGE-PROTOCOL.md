# SCQOS Canonicalization Independent Challenge Protocol

Authority: SCQOS-C14N-JCS-NFC-1 specification only.

The SCQOS reference implementation MUST NOT be inspected or executed
to determine expected answers.

An evaluator SHALL derive expected behavior from:

1. SCQOS Canonicalization Contract v1.0
2. RFC 8785 JSON Canonicalization Scheme
3. Unicode UAX #15 NFC
4. FIPS 180-4 SHA-256

For every challenge:

1. Read only the specification and incorporated standards.
2. Determine whether the input MUST be ACCEPTED or REJECTED.
3. For ACCEPTED inputs, derive canonical UTF-8 bytes.
4. Compute SHA-256 of those frozen bytes.
5. Record the expected result before executing any candidate implementation.
6. Freeze the challenge record.
7. Only then run candidate implementations.
8. Any ambiguity is HOLD, never guessed.

Required adversarial classes:

- NFC versus NFD equivalent string values
- NFC versus NFD object keys
- NFC key collision
- reversed object insertion order
- nested object ordering
- UTF-16 property ordering boundary
- empty object
- empty array
- quote escaping
- backslash escaping
- newline/tab/control escaping
- shortest-round-trip floating-point edge
- scientific notation
- NaN
- positive Infinity
- negative Infinity
- negative zero
- deep nesting
- malformed JSON
- invalid Unicode/lone surrogate

PASS requires the specification alone to determine the result.

If the evaluator must inspect SCQOS source to know the answer:
SPECIFICATION_HOLD_UNDERSPECIFIED.
