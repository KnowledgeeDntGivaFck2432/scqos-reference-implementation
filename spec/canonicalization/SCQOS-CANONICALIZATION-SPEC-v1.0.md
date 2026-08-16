# SCQOS Canonicalization Contract v1.0

Status: Release Candidate for independent falsification

## 1. Purpose

This document is normative.

A conforming implementation MUST be constructible from this document
without inspecting the SCQOS reference implementation.

The reference implementation is NOT an authority for resolving ambiguity.
If this document does not determine an answer, the specification is
underspecified and the result is HOLD.

## 2. Canonicalization identifier

`SCQOS-C14N-JCS-NFC-1`

## 3. Input data model

Canonicalized values are JSON-compatible values:

- null
- boolean
- string
- finite IEEE-754 binary64 number
- array
- object whose property names are strings

NaN and positive or negative Infinity MUST be rejected.

Duplicate property names MUST be rejected.

Invalid Unicode, including lone surrogate values, MUST be rejected.

Applications requiring integers or decimal quantities that cannot be
represented without loss as IEEE-754 binary64 SHOULD encode those values
using an application-defined string representation.

## 4. Unicode normalization

Before canonical JSON serialization, every JSON string value and every
object property name MUST be transformed to Unicode Normalization Form C
(NFC), recursively through the complete value.

If two distinct original property names normalize to the same NFC
property name, canonicalization MUST terminate with an error.

NFC and NFD spellings of canonically equivalent textual content therefore
produce the same canonical textual content unless normalization creates
a property-name collision, in which case the input is rejected.

## 5. JSON canonicalization

After NFC preprocessing, serialization MUST follow RFC 8785 JSON
Canonicalization Scheme (JCS), except where this specification explicitly
adds the NFC preprocessing rule above.

Accordingly:

1. No insignificant whitespace is emitted.
2. null, true and false use their JSON literal forms.
3. Strings use RFC 8785 escaping rules.
4. Numbers use RFC 8785 / ECMAScript-compatible number serialization.
5. NaN and Infinity are rejected.
6. Object properties are recursively sorted according to RFC 8785 using
   their raw, unescaped property names represented as UTF-16 code units.
7. Array element order is preserved.
8. Objects occurring inside arrays are recursively canonicalized.
9. The final canonical JSON text is encoded as UTF-8.

Negative zero MUST NOT be accepted as an input distinction. An
implementation receiving a preserved negative-zero representation MUST
reject it rather than silently allowing two source states to collapse
without attribution.

## 6. Digest

The digest is:

`SHA-256(canonical_utf8_bytes)`

using SHA-256 as defined by FIPS 180-4.

External textual form:

`sha256:<64 lowercase hexadecimal characters>`

The digest covers exactly the canonical UTF-8 byte sequence and nothing
else.

## 7. Excluded information

Information not present in the input JSON value is not implicitly added
to the digest.

Transport metadata, filenames, filesystem timestamps, operating-system
metadata, source-code location, runtime identity and network metadata are
excluded unless explicitly represented as fields in the input value.

No implementation-specific serialization metadata may be inserted.

## 8. Required failure behavior

A conforming implementation MUST fail closed on:

- malformed JSON
- duplicate object property names
- invalid Unicode
- lone surrogates
- NaN
- Infinity
- NFC property-name collisions
- unsupported values
- any condition for which this specification does not determine one
  canonical byte sequence

Uncertainty MUST NOT silently become a canonical result.

## 9. Required independence rule

A verifier claiming independent implementation MUST NOT inspect, copy,
import, translate, execute, derive rules from, or otherwise use the
SCQOS reference canonicalization source before freezing its own
implementation and results.

It MAY use this specification and the external standards incorporated
herein.

## 10. External normative foundations

- RFC 8785 — JSON Canonicalization Scheme
- Unicode Standard Annex #15 — Unicode Normalization Forms, NFC
- FIPS PUB 180-4 — SHA-256

## 11. Falsification rule

Conformance is established only when the specification alone determines
the expected result for every accepted vector and every conforming
implementation produces that result.

If two implementations can both plausibly claim conformance while
producing different canonical bytes, the specification is HOLD until
the ambiguity is resolved and versioned.

## 12. Versioning

This specification is immutable after final tag publication.

Any semantic change requires a new specification version.

Previous evidence remains bound to the canonicalization contract under
which it was originally produced.
