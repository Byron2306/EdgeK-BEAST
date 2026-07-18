# Compound Agentic Crystallization Experiment

## Claim under test

For a bounded real-repository task family, independently verified
crystallized sub-capabilities can be composed into a new held-out workflow.
The composed workflow must complete with no replay-time model/provider call,
while preserving stage-local verification, mutation refusal, and positive net
economics. This is **not** a claim of model weight learning or general agent
autonomy.

## Why this is stronger than current proof

The current live final-boss receipt proves one crystallized multi-file repair
can replay fresh low-overlap variants. Compound proof requires that no single
stored recipe solves the task: later stages consume only verified structured
outputs from earlier stages, and each stage may independently refuse.

## Required workflow

1. **Envelope and triage**: normalize a semantically distant request into a
   task envelope; reject wrong risk/postcondition classes.
2. **Evidence retrieval**: select two or more candidates from separate
   provenance lanes using contracts, not prompt/cache identity.
3. **Plan composition**: join verified outputs into a typed output IR with
   explicit dependency edges and input/output digests.
4. **Tool execution**: apply an approved multi-file patch or migration only
   after every predecessor proof is valid.
5. **Postcondition verification**: run integration tests plus stage-specific
   verifiers; bind every result to the final receipt.

## Corpus and controls

Use three task families with at least ten held-out variants each: provider
normalization + streaming preservation, schema migration + compatibility shim,
and configuration hardening + secret redaction. Every variant contains
unrelated decoy files and at least four negatives: wrong contract, stale state,
poisoned intermediate IR, and one broken predecessor proof.

Compare these arms:

| Arm | Purpose |
| --- | --- |
| bare local model | baseline capability/cost |
| model + ordinary context | retrieval-only control |
| BEAST single-crystal replay | isolates single-recipe effect |
| BEAST composed crystals | primary claim |
| composed crystals with one invalid predecessor | mandatory safe refusal |
| provider fallback after refusal | validates non-forced admission |

## Advancement gates

- all held-out composed runs pass independent integration tests;
- zero admissions for all mandatory negatives;
- no replay-time model/provider calls for admitted composed runs;
- each final receipt includes the DAG, all stage proof digests, rejected
  candidates, raw verifier output hashes, and full overhead;
- paired net economics is positive after origin amortization;
- separate-host replay is required before any independent-replication claim.

## Current state

The live final-boss run on 2026-07-16 establishes a prerequisite only: one
Qwen 0.5B origin call, four-file migration, 24 decoys, three fresh variants,
three negative controls, and zero replay-time local-engine/provider calls.
It does **not** satisfy composition because its patch recipe remains one
capability. The next implementation is a typed, fail-closed composition DAG
and its sealed receipt/verifier.
