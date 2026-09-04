# World-first claim boundary — 2026-08-27

## Claim made by this release

> The first publicly reproducible cross-substrate proof-before-action execution
> challenge using one frozen governance contract, nine cryptographic gate
> proofs, signed decision receipts, and live independent evidence anchors.

This is a falsifiable combination claim. A prior system defeats it by producing
a publicly timestamped implementation that contains every element of the claim,
not merely one adjacent feature.

## Required evidence in this release

| Element | Public test |
|---|---|
| Frozen contract | Contract hash returned by `/v1/health` |
| Adversarial execution | Six-case matrix returns expected PERMIT/HOLD/REJECT |
| Nine-gate proof | PERMIT receipt contains nine non-empty gate hashes |
| Signed receipt | KMS ECDSA signature and public key are returned |
| Reproducibility | Source commit and content-addressed deployment artifact |
| Independent anchors | Live XRPL results and primary standards links |
| Safety boundary | `SHADOW_ONLY`; external side effects are always false |

## Prior-art categories checked

Current systems and publications discuss agent authorization, policy engines,
proof-before-action, execution permits, receipts, and replay. Those individual
concepts are not claimed as inventions here. The novelty claim is the exact
public, cross-substrate, frozen-contract, nine-proof, independently anchored
challenge assembled in this release.

Primary context:

- NIST AI Agent Standards Initiative: https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative
- NIST software and AI-agent identity and authorization: https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization
- OWASP Top 10 for Agentic Applications 2026: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

Search cannot prove universal nonexistence. The correct professional posture is
to publish the exact claim, timestamp its evidence, invite counterexamples, and
revise the priority claim if earlier complete evidence is produced.
