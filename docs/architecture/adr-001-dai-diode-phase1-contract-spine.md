# ADR-001: DAI Diode Phase-1 contract spine

## Status

Accepted

## Context

The synthesis now spans four existing stacks:

- Sophia / Integritas: learning, pedagogy, source support and transfer evidence.
- Seraph / Metatron: adversarial challenge, deception, telemetry and harmonic assessment.
- Arda: hardware, kernel, workload and physical attestation.
- BEAST: semantic validation, evidence authority, crystals, Commons and deterministic reuse.

The critical architectural risk is a direct path from learned or advisory output
to capability authority. If Sophia, Seraph or harmonic confidence can authorize
execution by itself, the DAI claim collapses into claimant-supplied authority.

## Decision

Phase 1 introduces a BEAST-local DAI contract spine:

- `ArtifactReceipt`
- `WorldStateSnapshot`
- `ConceptCandidate`
- `CandidatePredicateSpec`
- `TransferEvidence`
- `SeraphAssessment`
- `HarmonicAssessment`
- `ArdaAttestationSummary`
- `QuorumVote`
- `DAIPhase1Packet`
- `DAIValidationReceipt`

The validator enforces the diode law:

```text
Sophia / Seraph / Harmonic / Arda observations
  -> evidence and candidates only
  -> no execution authority
```

Phase 1 packets may pass only as quarantined candidates.

## Rationale

This keeps the first integration useful without pretending the full creature is
already alive. It binds actual external artifacts by recomputed digest, enforces
source linkage, requires near/far/negative transfer evidence, records Seraph and
harmonic inputs, and admits Arda as physical evidence without letting any of
those sources silently promote a capability.

## Trade-offs

- Positive: creates a shared language for Sophia, Seraph, Arda and BEAST without
  weakening BEAST's proof boundaries.
- Positive: gives reviewers a concrete first-phase receipt instead of a purely
  narrative roadmap.
- Negative: does not yet perform cross-repository mutation or live Commons quorum.
- Negative: does not yet verify external signatures for every artifact.
- Mitigation: later phases add signed source receipts, world-state event logs,
  Arda-bound Commons admission, quorum/veto, and promotion-to-crystal.

## Consequences

The next phase can wire Sophia candidate generation and Seraph hostile curriculum
into this object layer directly. The authoritative promotion path remains later:

```text
candidate -> semantic gauntlet -> signed evidence resolver -> world-state lease
-> role-diverse quorum -> Arda/Sensorium observed execution -> plasticity proposal
```

