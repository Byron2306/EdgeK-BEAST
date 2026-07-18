# Crystallized Compute Claim Ledger

**Status:** canonical evidence ledger — 2026-07-16

This document is the source of truth for public, product, and research claims
about crystallized compute. It distinguishes code presence, controlled local
demonstration, production-path observation, independent replication, and
economic proof. A UI card, registry entry, import, unit test, benchmark file,
or signed advertisement is not evidence of a stronger claim by itself.

## Claim levels

| Level | Meaning | Minimum evidence |
| --- | --- | --- |
| `implemented` | Code and contract exist. | Source, tests, and an explicit boundary. |
| `runtime_observed` | The normal production composition path executed it. | Correlated request receipt, verifier result, and bypass accounting. |
| `bounded_proven` | A defined task family was safely reused or transformed. | Held-out positives, negative boundaries, mutation refusal, and replayable evidence. |
| `economically_measured` | Reuse produced net benefit for the defined task family. | Paired baseline, all local/governance costs, confidence interval, and amortization. |
| `independently_replicated` | The result reproduced on an independent physical environment. | Separate host/runtime identity, sealed corpus, independent verifier, and raw receipts. |
| `not_proven` | A proposal, extrapolation, or unsupported generalization. | Must not be presented as achieved. |

## Current claims

| ID | Claim | Level | Evidence | Boundary / next evidence |
| --- | --- | --- | --- | --- |
| CC-01 | A promoted typed crystal can execute through the production ComputePlane with applicability, one-use authority, independent verification, and sealed evidence. | `runtime_observed` | `production-composition-*`, `deployed-enforcement-probe-*` evidence; Sensorium progress Milestone 10. | Bounded file/build mission; not default routing across every IDE or provider path. Instrument ordinary IDE flows and report bypasses. |
| CC-02 | A bounded local physical operation can recur without a provider call and refuse stale or unsafe conditions. | `bounded_proven` | Port/file/build and disk-cleanup receipt families. | Does not imply arbitrary task reuse, broad multi-crystal routing, or universal isolation. |
| CC-03 | A fixed small model plus a bounded residual can outperform the bare model on exact SHA-256 transformation. | `bounded_proven` | `milestone11-*uplift*`, `scientific-uplift-*`, Windows replication receipts. | This is deterministic residual assistance, not learned weights, general coding ability, or discovery-agnostic reuse. |
| CC-04 | One paired local-Ollama task family showed positive net latency and avoided calls under matched conditions. | `economically_measured` | `milestones-12-14-live-closure-2026-07-15.json`. | Three pairs on one host; declared token rate and unavailable energy. Requires a larger preregistered corpus and amortization. |
| CC-05 | Crystal artifacts can be signed, locally admitted, privacy-scanned, and reproduced by separate logical identities. | `bounded_proven` | Milestones 13–14 evidence. | Logical nodes are not remote physical nodes; Commons service/HSM admission remains unproven. |
| CC-06 | Semantic pages, lattice candidates, KV/prefill, routing, and adapter heads improve ordinary coding outcomes. | `not_proven` | Local/synthetic and proposal-only receipts exist. | Must be measured by ablation on the same held-out corpus; no contribution claim until then. |
| CC-07 | BEAST materially improves a small local model on real coding tasks. | `not_proven` | Current hard/final-boss gauntlets are useful pipeline evidence. | Require raw-output scoring, time/token-matched ephemeral baselines, blinded quality-equivalence grading, real-repository corpus, and independent replication. |
| CC-08 | Capability discovery is agnostic to prompt vocabulary, provider identity, runtime, and peer advertisement. | `not_proven` | Discovery catalog and proof-local protocol exist. | Requires sealed cross-surface discovery/reuse experiment described below. |
| CC-09 | Commons federation contributes verified remote compute displacement. | `not_proven` | Two logical-node reproduction is a protocol rehearsal. | Requires a genuinely remote attested node that independently reproduces and measures local displacement. |

## Mandatory receipt fields

Any receipt eligible to advance a claim must bind:

- corpus and task IDs, split/commit digests, and preregistration digest;
- task envelope and discovery representation digests, without raw private data;
- model/runtime/provider identity and exact route;
- candidate provenance, applicability decision, and all rejected candidates;
- initial-state, policy, verifier, postcondition, and mutation digests;
- calls, tokens, latency, CPU, memory/I/O where available, and verifier cost;
- local/provider fallback and bypass counters;
- negative, stale, collision, and poisoned-candidate outcomes;
- independent verifier command/version and receipt content hash.

## Claim advancement rules

1. A result may advance only one named claim at a time.
2. Discovery, advertisement, vector similarity, cache identity, and model output
   are hypotheses. They never grant execution authority or displacement credit.
3. A claim moves to `economically_measured` only with a paired baseline and
   full local overhead; zero provider calls alone are insufficient.
4. A claim moves to `independently_replicated` only when a separate physical
   host reruns a sealed corpus and an independent verifier accepts raw receipts.
5. A failed negative or mutation case demotes the affected capability and is
   included in the published result; it cannot be silently excluded.

## Supersession rule

Older roadmap and audit statements remain historical evidence, but this ledger
controls current status. In particular, the 2026-06 Compute Governor phase
audit predates the 2026-07 ComputePlane composition work; neither document may
be used alone to assert a current production or scientific claim.

## Immediate next proof

Advance CC-08 first: discovery-agnostic reuse. Its experimental protocol is
defined in `docs/DISCOVERY_AGNOSTIC_REUSE_EXPERIMENT.md`. Success can advance
only CC-08; it does not by itself establish general coding uplift (CC-07) or
remote federation economics (CC-09).
