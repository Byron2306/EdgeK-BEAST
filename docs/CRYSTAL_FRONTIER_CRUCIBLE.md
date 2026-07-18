# BEAST Crystal Frontier Crucible

The Crucible is an independent evaluation laboratory. It is not a scheduler,
executor, promotion path, or UI claim surface. It tests whether proof-carrying
crystals retain frontier-quality engineering within declared boundaries.

## Components

| Component | Executable boundary |
| --- | --- |
| Sealed Task Foundry | `SealedTaskFoundry` commits task/repository/verifier digests before runs. |
| Agent Lane Controller | six fixed lanes: frontier native/governed, local, crystal only/hybrid, placebo. |
| Hidden Verifier Vault | verifier content stays out of `PublicEvidenceExporter`; only commitment digest is public. |
| Blind Review Chamber | lane-hidden packets and separate private lane key. |
| Sensorium Run Recorder | each `CrucibleRun` binds episode, attestation, policy, tool, crystal, and lattice digests. |
| Statistical Evidence Engine | paired 95% and 99% bootstrap gates for H1/H2 plus H3 false-execution rate. |
| Attested Reproduction Runner | run record carries runner-image and attestation digests; remote execution is a required later gate. |
| Public Evidence Exporter | emits sanitized public evidence without hidden verifiers, private keys, source tasks, or solutions. |

## Hypotheses

- H1: crystal-only is non-inferior to frontier-native on predeclared eligible
  C1–C3 tasks, at both 95% and 99% confidence.
- H2: crystal-hybrid has superior verified completion to frontier-native over
  the mixed workload while reporting cloud/cost/latency separately.
- H3: false crystal execution on C5–C6 tasks stays below the preregistered
  threshold.
- H4: longitudinal coverage increases without degradation; this requires
  repeated sealed releases and is not established by one Crucible run.

## Current boundary

The core is implemented and unit-tested. No result has yet advanced H1–H4:
CrystalBench has not been independently authored, sealed, sized by power
analysis, blind-reviewed, or independently reproduced. Existing gauntlets are
candidate task-family inputs, not decisive Crucible evidence.
