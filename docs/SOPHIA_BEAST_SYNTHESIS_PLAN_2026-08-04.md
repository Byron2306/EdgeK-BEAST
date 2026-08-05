# Sophia ↔ BEAST synthesis plan

Date: 2026-08-04

## Core thesis

Learning should begin as exploratory acquisition, prove itself through transfer,
become authority only through verification, and thereafter persist as bounded
reusable capability rather than being regenerated probabilistically from
scratch.

In this split:

- **Sophia governs the journey from information to understanding.**
- **BEAST governs the journey from understanding to trusted capability.**

Sophia may propose meaning. BEAST decides whether that meaning has earned the
right to become deterministic machinery.

## What I read

Primary prompt attachment:

- `/home/byron/.codex/attachments/fddfcb8b-2e98-4231-8b87-dd749930cebf/pasted-text.txt`

Primary Sophia / Integritas tree inspected:

- `/home/byron/Integritas-Mechanicus`

Important supporting files inspected:

- `/home/byron/Integritas-Mechanicus/README.md`
- `/home/byron/Integritas-Mechanicus/docs/SOPHIA_SPECULUM_STATUS_AND_IMPROVEMENT_PLAN.md`
- `/home/byron/Integritas-Mechanicus/docs/SOPHIA_NONHUMAN_LEARNING_EXPERIMENT_PROTOCOL.md`
- `/home/byron/Integritas-Mechanicus/scripts/sophia_writing_desk_phase3_export_semantic.py`
- `/home/byron/Integritas-Mechanicus/scripts/sophia_evidence_engine_slice1.py`
- `/home/byron/Integritas-Mechanicus/scripts/sophia_hf_nli_support_suite.py`
- `/home/byron/Integritas-Mechanicus/scripts/sophia_contrastive_baseline_mini_suite.py`
- `/home/byron/Integritas-Mechanicus/arda_os/backend/services/sophia_pedagogy_orchestrator.py`
- `/home/byron/Integritas-Mechanicus/arda_os/backend/services/sophia_project_store.py`

Recent Sophia evidence receipts inspected:

- `sophia_writing_desk_phase3_export_semantic_latest.json`: 60/60
- `sophia_writing_desk_phase3_entailment_scoring_latest.json`: 1/1
- `sophia_writing_desk_phase4_project_store_latest.json`: 8/8
- `sophia_writing_desk_phase5_adaptation_suite_latest.json`: 100/100
- `sophia_writing_desk_phase6_similarity_latest.json`: 7/7
- `sophia_hf_nli_support_latest.json`: 3/3
- `sophia_contrastive_baseline_latest.json`: 5/5
- `sophia_phase78_native_table_figure_gauntlet_latest.json`: 5/5
- `sophia_real_document_corpus_benchmark_latest.json`: 8/8, fixture mode
- `sophia_pedagogy_outcome_calibration_latest.json`: 5/5

## Honest synthesis

Sophia already contains several acquisition-side mechanisms BEAST should not try
to reinvent by hand:

1. Pedagogical office selection and adaptive scaffolding.
2. Concept/lens recognition across learning theories and academic tasks.
3. Claim/source/warrant/limitation ledgers.
4. Project-scoped memory and contamination checks.
5. Source-span humility: source leads are not treated as proof.
6. Similarity/provenance risk classification.
7. NLI-style support and contradiction classification.
8. Real-document/table/figure witness separation, currently with fixture and
   optional-live boundaries.
9. Blinded rater packet and outcome calibration plumbing.

BEAST now contains several authority-side mechanisms Sophia should not try to
duplicate loosely:

1. Canonical semantic program identity.
2. PredicateSpec law: value types, contradiction rules, temporal authority, text
   encoding and visual encoding.
3. Recomputed claim and relationship receipts.
4. Refusal and residual gates before expression.
5. Independent text, visual and SourcePlan entailment checks.
6. Exact source-target capability contracts.
7. Gauntlet receipts with hostile negative controls.
8. Promotion/reuse boundaries for deterministic capability and crystal lanes.

The integration point is therefore not “merge two chatbots.”

The integration point is:

```text
Sophia acquisition artifact
  -> candidate concept / claim / transfer pattern
  -> BEAST candidate PredicateSpec or CapabilitySpec
  -> evidence-bound hidden transfer tests
  -> promote | quarantine | refuse
  -> deterministic text / visual / code behavior
  -> observed outcome evidence
  -> Sophia reflection and revision
```

## Boundary that protects the claim

Sophia’s current evidence is meaningful but not yet the final broad-learning
claim.

We should not claim:

> Sophia has conclusively demonstrated broad concept acquisition across major
> unseen domains.

We can claim:

> Sophia contains an architecture and preliminary evidence for acquisition,
> mediation, authorship-preserving academic support, and compositional transfer.

The joint Sophia → BEAST experiment should test the stronger claim.

## The bridge object

The first shared object should be a `SophiaConceptCandidate`.

It should be inert by default. It proposes a law; it does not grant authority.

Required fields:

```json
{
  "beast_object_type": "sophia_concept_candidate",
  "candidate_id": "sophia:concept:<stable-id>",
  "source_system": "sophia",
  "source_receipts": ["sha256:..."],
  "concept_label": "photosynthetic_inhibition",
  "candidate_predicates": [
    {
      "predicate": "photosynthetic_inhibition",
      "subject_kinds": ["plant", "algae"],
      "value_type": "bool",
      "true_text": "showed photosynthetic inhibition",
      "false_text": "did not show photosynthetic inhibition",
      "visual_true": "inhibition badge",
      "visual_false": "normal photosynthesis badge",
      "conflicts_with": [
        {"predicate": "photosynthesis_operating_normally", "value": true}
      ],
      "evidence_required_when_supported": true
    }
  ],
  "transfer_evidence": {
    "near_transfer": [],
    "far_transfer": [],
    "negative_cases": [],
    "source_span_refs": [],
    "nli_support": []
  },
  "authorship_boundary": "candidate proposed by Sophia; BEAST promotion required",
  "promotion_state": "quarantined_candidate"
}
```

BEAST should consume that candidate only through a verifier. The candidate must
not mutate BEAST’s live predicate registry directly.

## BEAST promotion law for Sophia candidates

A Sophia-origin candidate can become a BEAST law only if all of these pass:

1. Source custody: every source receipt resolves, recomputes, and binds to exact
   Sophia evidence artifact fields.
2. Claim support: candidate source spans classify as support or partial support;
   contradictions are not hidden.
3. Predicate well-typedness: every proposed predicate has value type, subject
   kinds, positive/negative text, visual encoding, and evidence requirements.
4. Ontology consistency: conflicts are explicit and hostile contradictions are
   generated from the schema.
5. Temporal authority: source and observation times parse and are current for
   the proposed law’s scope.
6. Transfer: at least one near-transfer and one far-transfer hidden case pass
   without using original surface wording.
7. Negative controls: unsupported, reversed, stale, contradictory, and irrelevant
   cases are refused.
8. Expression: deterministic text and visual outputs express the actual
   proposition, including value/polarity/unit.
9. Residual discipline: residual-required claims are never narrated as facts
   until a residual result is verified and promoted.
10. Reuse economics: after promotion, repeated tasks use fewer provider calls
    while maintaining or improving verification pass rate.

## First implementable slice

Build the smallest honest loop:

```text
Sophia semantic export fixture
  -> BEAST SophiaConceptCandidate receipt
  -> candidate PredicateSpec compiler
  -> hidden transfer + hostile mutation gauntlet
  -> promoted test-only PredicateLaw registry overlay
  -> deterministic text + SVG expression
  -> zero-provider repeated replay receipt
```

Recommended first domain: academic writing source-support law, because Sophia
already has the strongest machinery there.

Candidate predicate family:

- `source_supports_claim`
- `source_partially_supports_claim`
- `source_contradicts_claim`
- `citation_needed`
- `authorship_preserved`
- `substitution_risk`

Why this domain first:

- Sophia already exports semantic claim/source support artifacts.
- Existing Sophia evidence includes support, contradiction, provenance, citation,
  and authorship cases.
- BEAST’s fourth-wave PredicateSpec machinery is ready to enforce polarity,
  evidence, contradiction, visual proposition coverage, and refusal.
- The claim boundary is publishable: educational support and proof discipline,
  not medical/legal/production autonomy.

## Concrete next patch

Add BEAST-side files:

- `app/kernel/compute/sophia_beast_bridge.py`
- `scripts/run_sophia_beast_concept_bridge_gauntlet.py`
- `tests/test_sophia_beast_bridge.py`

The bridge should:

1. Load a Sophia semantic export JSON artifact.
2. Normalize it into `SophiaConceptCandidate`.
3. Emit deterministic candidate receipt and source receipt digests.
4. Compile a test-only `PredicateLaw` overlay.
5. Generate hidden transfer tasks and hostile mutations.
6. Run BEAST semantic expression over the promoted overlay.
7. Refuse promotion if any hostile mutation passes.
8. Record provider calls used before and after promotion.

## What would count as a real breakthrough result

A serious result would look like:

> The integrated system required probabilistic or exploratory inference during
> initial concept acquisition, but after successful transfer validation and
> BEAST promotion, repeated tasks were completed through deterministic semantic
> capability with lower inference use, stronger provenance, correct refusal at
> unsupported boundaries, and preserved human authorship.

Measured dimensions:

- concept acquisition accuracy;
- near-transfer success;
- far-transfer success;
- contradiction detection;
- unsupported-claim leakage;
- correct refusal;
- semantic-expression accuracy;
- visual proposition coverage;
- code-task success where applicable;
- provider calls after promotion;
- reuse across repeated tasks;
- human authorship preservation.

## External defensibility path

The public experiment should freeze the engine, then choose held-out domains
after freeze:

- academic writing / source support;
- software operations;
- ecology toy domain;
- economics toy domain;
- mechanical systems toy domain;
- network security toy domain.

Compare:

- Sophia alone;
- BEAST alone with manual predicates;
- Sophia → BEAST;
- LLM alone;
- RAG + LLM;
- rule engine;
- knowledge-graph reasoning;
- Sophia → BEAST with acquisition, verifier, or promotion ablated.

The winning claim is not “one guy made a magic brain.”

The winning claim is:

> A concept-acquisition system can propose transferable semantic laws, and a
> proof-first deterministic substrate can decide which of those laws may become
> reusable capability.

That is sober enough to publish and strange enough to matter.

## DAI Diode convergence addendum

Source attachment:

- `/home/byron/.codex/attachments/267315f5-632f-4f67-870e-28d10bf19345/pasted-text.txt`

The Sophia ↔ BEAST bridge is one organ inside a larger architecture:

> Deterministic Artificial Intelligence Diode, or DAI Diode.

The diode law:

> A learned concept may propose capability, but it may not directly authorize
> deterministic behavior.

Capability must first survive:

1. transfer;
2. adversarial challenge;
3. semantic validation;
4. evidence resolution;
5. world-state binding;
6. cryptographic quorum;
7. attested execution.

The reverse path carries evidence, not authority:

```text
execution outcome
  -> telemetry and evidence
  -> learning and revision
```

An execution result may teach the system. It may not silently rewrite the
system.

## Full organism map

| Organ | Responsibility |
| --- | --- |
| Sophia | Concept acquisition, pedagogical mediation, abstraction, authorship preservation, transfer |
| Seraph | Adversarial challenge, deception detection, telemetry fusion, environmental threat sensing |
| Metatron Harmonic Engine | Coherence, drift, discord, confidence and behavioral regulation |
| BEAST | Semantic validation, evidence authority, capability compilation, refusal, deterministic reuse |
| Forge-KV | Working memory, activation continuity, bounded context reuse |
| Commons | Distributed capability hosting, secure node communication, collective witness |
| Quorum Mesh | Role-diverse witness admission, constitutional agreement, authenticated veto |
| World Model | Shared bounded reality against which decisions are made |
| Arda | Hardware, kernel, workload and execution attestation |
| Sensorium | Physical observation, runtime episodes and outcome evidence |
| Crystals | Consolidated verified procedural capability |
| Rekor / release evidence | Public artifact integrity and external reproducibility |

This changes the synthesis from:

```text
Sophia learns -> BEAST verifies
```

to:

```text
Sophia acquires
  -> Seraph challenges
  -> Harmonic engine assesses coherence/discord
  -> BEAST validates and promotes
  -> Commons quorum admits authority
  -> Arda executes under attestation
  -> Sensorium observes
  -> evidence returns for revision
```

## Non-negotiable DAI invariants

These must become code-level gates, not slogans:

1. No direct learning-to-execution path.
2. Evidence may return; authority may not.
3. Harmonic resonance is not truth.
4. Unverified Commons nodes do not vote.
5. Veto must be authenticated.
6. World-state drift invalidates authority.
7. Cryptographic transport does not equal node trust.
8. Production plasticity is never immediate.
9. Independent verification must be genuinely separate.
10. Every consequential result must have a proof bundle.

The strongest one for BEAST implementation is:

```text
Sophia / LLM / Seraph / Harmonic output
  != capability authority
```

Only BEAST promotion plus quorum plus attestation can grant bounded execution
authority.

## Coordination repository strategy

Do not merge every project into a single mega-monolith.

Create a coordination repository such as:

- `Byron2306/DAI-Diode`
- `Byron2306/Deterministic-AI-Diode`

That repository should own:

- specifications;
- shared schemas;
- integration adapters;
- end-to-end harnesses;
- Docker Compose or local orchestration;
- benchmark suites;
- hostile challenge generators;
- evidence bundles;
- release manifests.

Existing repositories remain authoritative for their own organs:

| Repository / project | Owns |
| --- | --- |
| Sophia / Integritas | Learning, pedagogy, transfer, academic integrity support |
| Seraph / Metatron | Deception, telemetry, harmonic assessment, quorum functions |
| EdgeK-BEAST | Semantic authority, crystals, Commons, deterministic reuse |
| Arda / Integritas substrate | Physical attestation and execution truth |
| DAI-Diode | Protocol joining them |

The DAI repository should depend on pinned commits or versioned releases, never
floating branches, for any reproducible experiment.

## Canonical shared contract package

The first engineering deliverable should be a shared canonical object package:

```text
dai_contracts/
  identity.py
  evidence.py
  learning.py
  harmonic.py
  semantic.py
  commons.py
  quorum.py
  world_state.py
  authority.py
  execution.py
  outcome.py
```

Every object must have:

- schema version;
- object type;
- canonical serialization;
- digest;
- created-at time;
- expiry where relevant;
- world-state binding;
- policy generation;
- validator;
- hostile malformed-object tests.

Critical first objects:

- `ObservationReceipt`;
- `ConceptCandidate`;
- `TransferChallengeReceipt`;
- `HarmonicAssessment`;
- `CanonicalPropositionPacket`;
- `EvidenceReceipt`;
- `CapabilityCandidate`;
- `WorldStateSnapshot`;
- `NodeAttestation`;
- `MLKEMSessionReceipt`;
- `QuorumVote`;
- `VetoReceipt`;
- `CapabilityLease`;
- `ExecutionReceipt`;
- `PlasticityProposal`.

BEAST already partially overlaps several of these through semantic receipts,
ML-KEM transport receipts, physical truth certificates, SourcePlan receipts,
and crystal promotion receipts. The DAI task is to make the object boundaries
shared and explicit across repositories.

## DAI Neural Mesh discipline

The neural mesh should not begin as a conventional distributed tensor network.

It should begin as a proof-governed associative network where a “neuron” is a
small capability unit:

- PredicateSpec;
- diagnostic crystal;
- causal rule;
- verification function;
- source transformation;
- local-model expert;
- evidence resolver;
- world-state query.

Memory split:

| Memory type | DAI object |
| --- | --- |
| Working memory | Forge-KV activation/context state |
| Procedural memory | Crystals |
| Semantic memory | PredicateSpecs |
| Situational memory | World model |
| Episodic memory | Runtime episodes |
| Associative memory | Capability routes |

Activation packets must remain reasoning-only until promotion:

```json
{
  "activation_id": "act:...",
  "goal_ref": "goal:repair-service",
  "proposition_refs": ["prop:..."],
  "world_state_hash": "sha256:...",
  "epoch_id": "epoch:...",
  "activation_strength": 0.78,
  "evidence_strength": 0.92,
  "visited_units": [],
  "remaining_hops": 8,
  "authority": "reasoning_only"
}
```

Connection strength should be an inspectable vector, not a mysterious scalar:

- semantic relevance;
- historical success;
- transfer success;
- evidence reliability;
- harmonic compatibility;
- world-state applicability;
- node health;
- latency;
- resource cost;
- risk.

Inhibition comes from contradiction, stale evidence, Seraph deception signals,
harmonic discord, missing witness classes, policy veto, world-state mismatch and
expired authority.

Plasticity loop:

```text
outcome observed
  -> PlasticityProposal
  -> offline replay and hostile testing
  -> BEAST promotion review
  -> quorum approval
  -> new route generation
```

No direct online production mutation.

## Quorum and veto mesh

Quorum must be numerical and role-diverse.

A valid quorum might require:

```text
at least 3 admitted nodes
AND at least 1 semantic witness
AND at least 1 physical witness
AND at least 1 adversarial or governance witness
```

Three identical BEAST replicas are not three independent evidence classes.

Admission sequence:

```text
node connects
  -> Arda attestation verified
  -> attestation binds ML-KEM key
  -> ML-KEM session established
  -> signed challenge completed
  -> epoch checked
  -> world-state hash checked
  -> witness role checked
  -> node admitted
```

Vote outcomes:

- `APPROVED`;
- `DEGRADED_APPROVAL`;
- `REFUSED`;
- `VETOED`;
- `QUORUM_UNAVAILABLE`;
- `WORLD_STATE_FRACTURE`.

A hard veto is valid only when the voter is admitted, signature is valid, veto
is fresh, role is authorized, reason is constitutional, evidence resolves, and
proposal/world-state/epoch bindings match.

## World-state architecture

The world state is the shared reality contract.

A capability is valid only under the state against which it was tested.

Every meaningful change becomes a signed event:

- node admitted;
- node removed;
- service started;
- service failed;
- policy changed;
- capability promoted;
- capability revoked;
- deception interaction observed;
- quorum fractured;
- world-state conflict detected;
- execution completed.

The canonical snapshot is derived from those events and hashed.

Every DAI integration release must include the stale-authority test:

```text
authorize action under world state W1
mutate relevant state to W2
attempt to reuse W1 token
expect deterministic refusal
```

## Revised phased roadmap

The correct build order is:

1. ~~Freeze the thesis into a BEAST-local synthesis plan and DAI addendum.~~
   - `DAI_DIODE_SPEC.md`
   - `CLAIMS_AND_NONCLAIMS.md`
   - `THREAT_MODEL.md`
   - `GLOSSARY.md`
2. ~~Begin shared identity and contract package.~~
   - `app/kernel/dai/contracts.py`
   - `scripts/run_dai_phase1_synthesis_gauntlet.py`
   - `tests/test_dai_phase1_contracts.py`
   - `docs/architecture/adr-001-dai-diode-phase1-contract-spine.md`
3. ~~Harden Evidence Resolver across all supported propositions.~~
4. ~~Build world-state convergence from signed events.~~
5. ~~Bind Commons admission to Arda attestation and ML-KEM sessions.~~
6. ~~Add role-diverse quorum and authenticated veto.~~
7. ~~Add Sophia concept bridge.~~
8. ~~Add Seraph adversarial curriculum.~~
9. ~~Add Harmonic transfer assessment.~~
10. ~~Add BEAST concept-to-capability promotion.~~
11. ~~Add DAI Neural Mesh activation across Commons.~~
12. ~~Add Arda execution and reverse evidence.~~
13. ~~Add closed-loop plasticity through promotion, not live mutation.~~

The temptation will be to start with the neural mesh because it is the most
electrifying part.

Do not.

Without shared contracts, evidence resolution, world-state convergence, attested
Commons admission and quorum/veto, the neural mesh would merely distribute
uncertainty.

With them, it becomes a governed cognitive substrate.

## Phase 1 implementation progress

1. ~~Locate the real Seraph stack under
   `/home/byron/Downloads/Metatron-triune-outbound-gate` and bind the first
   Seraph/Metatron artifacts by digest.~~
2. ~~Bind Sophia and Arda artifacts from `/home/byron/Integritas-Mechanicus` and
   BEAST C4-X evidence into a shared Phase-1 packet.~~
3. ~~Implement the DAI Diode contract spine in BEAST with candidate/advisory/
   attestation scopes that cannot grant execution authority.~~
4. ~~Add hostile controls for direct learning-to-execution, Seraph authority
   inflation, harmonic truth laundering, weak transfer, tampered artifacts,
   bad source linkage and malformed time metadata.~~
5. ~~Run the Phase-1 synthesis gauntlet and store the receipt under
   `evidence/dai-diode/phase1-synthesis-001/`.~~

## Phase 2 implementation progress: Sophia as a producer

1. ~~Add a BEAST-side Sophia export bridge that reads
   `sophia_writing_desk_phase3_export_semantic_latest.json` instead of
   hand-building the candidate.~~
2. ~~Require at least two distinct support families plus explicit contradiction
   / negative-control rows before Sophia can even propose a quarantined
   candidate.~~
3. ~~Digest-bind bounded Sophia row evidence into the candidate transfer
   evidence so the source-support law is derived from actual rows.~~
4. ~~Run the updated Phase-1 synthesis gauntlet with the automatic Sophia
   candidate path.~~

## Phase 3 implementation progress: Seraph as adversarial producer

1. ~~Read the Metatron / Seraph honest classification summary and identify
   bounded challenge seams: Sigma coverage vs live detection, Arkime JSON vs
   PCAP replay, ClamAV enumeration vs maliciousness, and K0 vs K2 authority
   laundering.~~
2. ~~Add a BEAST-side Seraph bridge that compiles those seams into structured
   `SeraphChallengeCase` objects and a `SeraphCurriculum`.~~
3. ~~Extend `SeraphAssessment` with challenge receipt digests while preserving
   `adversarial_challenge_only` authority.~~
4. ~~Run the synthesis gauntlet with automatic Sophia candidate production and
   automatic Seraph curriculum production.~~

## Phase 4 implementation progress: Harmonic as transfer assessor

1. ~~Read the Sophia / Metatron office response proof matrix and identify the
   transfer surface: 19 document-grounded office responses over the same bounded
   source and draft.~~
2. ~~Add a BEAST-side Harmonic bridge that compiles office rows into
   `HarmonicTransferCase` objects and a `HarmonicTransferAssessment`.~~
3. ~~Extend `HarmonicAssessment` with transfer receipt digests while preserving
   `harmonic_assessment_only` authority.~~
4. ~~Run the synthesis gauntlet with automatic Sophia candidate, Seraph
   curriculum and Harmonic transfer assessment production.~~

## Phase 5 implementation progress: Evidence resolver and world-state foundation

1. ~~Add a DAI evidence resolver that recomputes artifact file digests,
   artifact receipt digests, component object digests and exact source-link
   equality before issuing a resolver receipt.~~
2. ~~Define a stable DAI core-packet digest so resolver/world receipts do not
   create circular self-reference inside the packet.~~
3. ~~Add signed/hash-chained DAI world events and convergence into a canonical
   `WorldStateSnapshot`.~~
4. ~~Run the synthesis gauntlet with evidence-resolution and world-state
   convergence receipts attached to the packet.~~

## Phase 6 implementation progress: Commons admission and quorum/veto

1. ~~Bind the live Commons ML-KEM receipt as a Commons artifact in the Phase-1
   packet.~~
2. ~~Add Commons admission receipts requiring ML-KEM confirmations, Arda
   attestation, current world-state digest and semantic/physical/adversarial
   role diversity.~~
3. ~~Add role-diverse quorum decisions with authenticated votes and
   authenticated veto receipts.~~
4. ~~Run the synthesis gauntlet with Commons admission and quorum receipts
   attached to the packet.~~
5. ~~Add hostile controls for wrong ML-KEM algorithm, exported shared secret,
   missing Arda witness, non-diverse admission roles, bad vote signatures,
   non-admitted voters and authenticated veto override.~~

## Phase 7 implementation progress: capability promotion and neural mesh

1. ~~Add a BEAST concept-to-capability promoter that compiles a quarantined
   `ConceptCandidate` into a sealed test-only capability overlay.~~
2. ~~Require Phase-1 validation, evidence resolution, Commons admission and
   role-diverse quorum to bind the same candidate and world-state before
   promotion.~~
3. ~~Add hostile promotion controls for missing negative realization, missing
   transfer evidence, missing source-span custody, support/contradiction
   laundering and authority inflation.~~
4. ~~Add DAI Neural Mesh activation across admitted Commons nodes with
   semantic/physical/adversarial role diversity.~~
5. ~~Bind every mesh node activation to the exact capability digest,
   world-state digest, promotion receipt and quorum receipt.~~
6. ~~Keep mesh activation in `governed_replay_only` mode with zero provider
   calls and no execution authority.~~
7. ~~Run the synthesis gauntlet with capability promotion and neural-mesh
   activation receipts emitted under
   `evidence/dai-diode/phase1-synthesis-001/`.~~

## Phase 8 implementation progress: Arda execution and reverse evidence

1. ~~Add bounded Arda sandbox execution for promoted DAI capabilities.~~
2. ~~Bind execution to the exact capability digest, promotion receipt, neural
   mesh activation receipt, Arda attestation and world-state digest.~~
3. ~~Write a deterministic replay artifact inside a bounded evidence sandbox
   rather than mutating host state.~~
4. ~~Add reverse evidence that recomputes output digest, before/after sandbox
   state and effect digest from the observed files.~~
5. ~~Add hostile controls for tampered replay output, unactivated mesh and
   host-mutation requests.~~
6. ~~Run the synthesis gauntlet with Arda execution and reverse-evidence
   receipts emitted under `evidence/dai-diode/phase1-synthesis-001/`.~~
7. ~~Keep provider calls at zero and general execution authority false.~~

## Phase 9 implementation progress: closed-loop plasticity

1. ~~Add a DAI plasticity loop that consumes Arda reverse evidence and records
   a bounded outcome signal.~~
2. ~~Emit a quarantined capability revision/reinforcement proposal instead of
   mutating the live capability.~~
3. ~~Require any proposed change to re-enter the promotion gauntlet before it
   can become a new capability.~~
4. ~~Bind the plasticity receipt to the exact capability digest, world-state
   digest, promotion receipt, mesh activation receipt, execution receipt and
   reverse-evidence receipt.~~
5. ~~Add hostile controls for unverified reverse evidence, live-mutation
   requests and mismatched capability linkage.~~
6. ~~Run the synthesis gauntlet with outcome signal, revision proposal and
   closed-loop plasticity receipts emitted under
   `evidence/dai-diode/phase1-synthesis-001/`.~~
7. ~~Keep the live capability digest unchanged, provider calls at zero and
   general execution authority false.~~

## Phase 1 synthesis status

All thirteen Phase-1 roadmap steps are complete.  The result is a governed DAI
loop:

```text
Sophia acquisition
  -> Seraph adversarial challenge
  -> Harmonic transfer assessment
  -> BEAST evidence resolution
  -> world-state convergence
  -> Commons ML-KEM admission
  -> role-diverse quorum
  -> test-only capability promotion
  -> neural mesh activation
  -> bounded Arda execution
  -> reverse evidence
  -> plasticity proposal
  -> future promotion, not live mutation
```

## First complete DAI demonstration

Use a domain where BEAST already has physical evidence:

> Safe stale-listener diagnosis and replacement.

Demonstration sequence:

1. Sophia receives unseen documentation/examples about process ownership,
   listening sockets, stale services, health checks, replacement services and
   safe refusal when ownership is unknown.
2. Sophia proposes `stale_listener_conflict`.
3. Near transfer: same service class, different port.
4. Far transfer: different service and namespace, same causal structure.
5. Seraph injects fake process owner, decoy service, misleading health response,
   stale PID, copied evidence digest, delayed sensor event and contradictory
   socket observation.
6. Harmonic assessment checks causal order, confidence under missing evidence,
   paraphrase resistance, decoy avoidance and transfer without unsupported
   invention.
7. BEAST resolves evidence, creates PredicateSpecs, compiles typed crystal and
   replays.
8. Three Commons nodes establish ML-KEM sessions, present Arda-bound identities
   and agree on world-state hash.
9. Role-diverse quorum approves the exact capability under the exact world
   state.
10. Arda executes the crystal inside a bounded local environment.
11. Sensorium verifies old listener retired, correct replacement started,
   service healthy, unrelated processes unchanged, no unapproved provider call
   and receipt chain complete.
12. Negative control mutates world state and attempts to reuse the old lease.
   Expected result: deterministic veto, zero effect.

This is the first “whole creature” proof.

## Operational Phase 2 implementation progress: stale-listener proof

1. ~~Create a disposable localhost lab with a real stale listener child process,
   a real unrelated control listener child process and socket-level health
   observations.~~
   - `app/kernel/dai/phase2_stale_listener.py`
2. ~~Add a Phase-2 world lease that binds exact stale PID/port, control
   PID/port, capability digest, world-state digest and the
   `disposable_localhost_child_processes_only` authority boundary.~~
3. ~~Execute the first bounded live state transition: retire only the leased
   stale child process, rebind a replacement listener on the same port and
   verify the unrelated control listener remains unchanged.~~
4. ~~Add hostile refusals for wrong stale process identity, wrong supplied world
   digest and stale-world lease replay after replacement.~~
5. ~~Emit Phase-2 evidence receipts under
   `evidence/dai-diode/phase2-stale-listener-001/` with provider calls fixed at
   zero and production authority fixed at false.~~
   - `scripts/run_dai_phase2_stale_listener_demo.py`
   - `tests/test_dai_phase2_stale_listener.py`
6. ~~Bind Sophia acquisition to this domain so `stale_listener_conflict` is
   proposed from unseen examples instead of being hand-selected by BEAST.~~
   - `fixtures/dai_phase2/stale_listener_acquisition_examples.json`
   - `app/kernel/dai/phase2_acquisition.py`
   - `tests/test_dai_phase2_acquisition.py`
7. ~~Add Seraph hostile injections for fake process owner, decoy service,
   misleading health response, stale PID, copied digest, delayed sensor event
   and contradictory socket observation.~~
   - `app/kernel/dai/phase2_seraph.py`
   - `tests/test_dai_phase2_seraph.py`
   - `evidence/dai-diode/phase2-stale-listener-001/phase2_seraph_injection_report.json`
8. ~~Add Harmonic near/far transfer scoring for same service class on different
   port and different namespace/service with the same causal structure.~~
   - `app/kernel/dai/phase2_harmonic.py`
   - `tests/test_dai_phase2_harmonic.py`
   - `evidence/dai-diode/phase2-stale-listener-001/phase2_harmonic_transfer_report.json`
9. ~~Bind the live Phase-2 world digest into Commons ML-KEM node admission and
   role-diverse quorum approval.~~
   - `app/kernel/dai/phase2_commons_quorum.py`
   - `tests/test_dai_phase2_commons_quorum.py`
   - `evidence/dai-diode/phase2-stale-listener-001/phase2_commons_quorum_packet.json`
10. ~~Replace the current stdlib Sensorium-style observation with the stronger
    Sensorium/BPF witness path when the exact C4-X cgroup observer is mounted.~~
    - `app/kernel/dai/phase2_sensorium_bpf.py`
    - `tests/test_dai_phase2_sensorium_bpf.py`
    - `evidence/dai-diode/phase2-stale-listener-001/phase2_sensorium_bpf_witness_report.json`
    - Exact X2 ring-buffer harness:
      `scripts/run_dai_phase2_x2_exact_ring_buffer.py`
    - Live privileged proof output:
      `evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring/`
    - Successful exact receipt:
      `phase2_x2_exact_ring_summary.json`
    - Summary digest:
      `sha256:33f5ecc2762faa364ca7c8b8c86288d72ca36a5373aefc13a65147d5fd9f7c44`
    - Authority level:
      `exact_phase2_cgroup_kernel_witness`
    - Bound kernel events:
      `correlated_socket_bind_event_count = 3`
    - Exact claim flag:
      `sensorium_exact_phase2_kernel_events_bound = true`
11. ~~Package Phase-2 as a frozen archaeological artifact only after the whole
    demonstration sequence, hostile probes and clean-environment reproduction
    pass.~~
    - Frozen identity:
      `DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04`
    - Bundle directory:
      `artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04/`
    - ZIP:
      `artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04.zip`
    - ZIP digest:
      `sha256:e2b8f75fba124399ee679e2eb530509f1eb84829a1402573a039408658aaa15a`
    - Bundle verifier:
      `python3 verify_phase2_exact_bundle.py`
    - Extracted ZIP verification passed with 81 manifest entries and no stale
      `x2_exact_ring_failure.json` file included.

## Operational Phase 2.1 closure hardening progress: authority-grade seams

Goal:

> Preserve the successful Phase-2 run as a fossil, then harden the general
> verifier and reproduction path so a future Phase-2.1 authority-grade run
> cannot be bluffed by stale leases, weak event binding, synthetic Commons
> receipts or live-workspace assumptions.

1. ~~Enforce Phase-2 world lease expiry, one-time consumption, issuer,
   audience, nonce and deterministic issuer signature before any process
   mutation.~~
   - Module:
     `app/kernel/dai/phase2_stale_listener.py`
   - Tests:
     `tests/test_dai_phase2_stale_listener.py`
   - New refusals:
     `lease_expired`,
     `lease_already_consumed`,
     `lease_nonce_missing`,
     `lease_issuer_signature_invalid`.
2. ~~Strengthen exact X2 kernel event binding from "same cgroup digest seen" to
   "one unique kernel socket-bind event per expected process lease."~~
   - Module:
     `app/kernel/dai/phase2_sensorium_bpf.py`
   - Exact event expectations now bind:
     PID/TGID,
     `process_lease_id`,
     process start time,
     role,
     cgroup raw digest,
     event type,
     normalized port,
     normalized address,
     and observation digest.
   - Harness:
     `scripts/run_dai_phase2_x2_exact_ring_buffer.py`
   - Tests:
     `tests/test_dai_phase2_sensorium_bpf.py`
     and `tests/test_dai_phase2_x2_exact_ring_buffer_script.py`.
3. ~~Prevent synthetic ML-KEM receipts from becoming Commons admission/quorum
   authority.~~
   - Module:
     `app/kernel/dai/commons_admission.py`
   - Required ML-KEM receipt features now include recomputed receipt digest,
     requested-node list, pairwise transcript matrix, node public-key document
     and challenge/ciphertext/signature digests.
   - Hostile test rejects invented three-node "passed" receipts.
4. ~~Downgrade the current Commons claim to its honest authority class:
   `local_world_bound_quorum_simulation`.~~
   - Module:
     `app/kernel/dai/phase2_commons_quorum.py`
   - Explicit nonclaim:
     not yet three independently attested Commons machines autonomously
     approving the proposal.
5. ~~Add a source-overlay installer to the Phase-2 capsule generator so a clean
   checkout can be brought to the exact packaged source/test state before live
   reproduction.~~
   - Script:
     `scripts/package_dai_phase2_exact_artifact.py`
   - New capsule entry when repackaged:
     `install_source_overlay.sh`.
6. ~~Add a DIO distributed quorum contract that separates local simulation,
   remote signed software witness, heterogeneous distributed quorum and
   hardware-rooted quorum.~~
   - Module:
     `app/kernel/dai/dio_distributed_quorum.py`
   - Hostile tests reject:
     wrong role with valid signature,
     evidence-root byte mismatch,
     duplicated signing key,
     ML-KEM session evidence masquerading as identity attestation.
7. ~~Add a Hugging Face Docker Space-compatible DIO witness service with
   `/health`, `/attest` and `/evaluate` endpoints.~~
   - App:
     `app/dio_hf_witness_main.py`
   - Deployment scaffold:
     `deploy/dio-hf-witness/`
   - Authority:
     `remote_signed_software_witness_only`.
   - Nonclaim:
     Hugging Face Space witness is not hardware attestation.
8. ~~Run the focused Phase-2.1 hardening test slice.~~
   - Command:
     `PYTHONNOUSERSITE=1 .venv/bin/python -m pytest tests/test_dio_distributed_quorum.py tests/test_dai_phase2_stale_listener.py tests/test_dai_phase2_sensorium_bpf.py tests/test_dai_phase2_x2_exact_ring_buffer_script.py tests/test_dai_phase2_commons_quorum.py -q`
   - Result:
     `24 passed`.
9. ~~Run a fresh privileged Phase-2.1 exact X2 proof with the hardened verifier.~~
   - One-shot privileged runner (proof then Phase-2.1 fossilization):
     `bash scripts/run_dai_phase2_1_closure.sh`
   - It deliberately prompts for sudo in the user terminal and does not accept
     or store a password.
   - This must mint a new summary digest; the old Phase-2 ZIP must not be
     silently replaced.
   - Fresh run:
     `dai-phase2-1-x2-exact-ring-local-001`.
   - Green summary digest:
     `sha256:da1d6a6f10a70d07f6c693adb2904324223454eedbce1d44786e87dc0f4a4abd`.
   - Exact kernel witness report digest:
     `sha256:4b3724a9769cb9c6730c75d1ee8b77a1891b68a0d6fcefc9754adbe1432b4fb0`.
10. ~~Package Phase-2.1 as a new fossil only after the fresh privileged proof
    passes.~~
   - Dedicated packager:
     `scripts/package_dai_phase2_1_artifact.py`.
   - Frozen identity:
     `DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04`.
   - Fossil:
     `artifacts/DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04.zip`.
   - ZIP digest:
     `sha256:fea707f02ae398b4bc0461dcf9bbd34149f78c8beedfeacee5ea3adc37ea679b`.
   - Independent local verifier:
     passed with 97 manifest entries; archive integrity also passed.
11. ~~Deploy the HF witness as an actual remote Docker Space with a pinned public
    Ed25519 key and verifier build.~~
    - Live Space:
      `https://huggingface.co/spaces/Byron230686/dio-phase2-semantic-witness`.
    - Pinned Hub commit:
      `186931786246aaf005dda9247b9c5d9d20419304`.
    - Deployment receipt:
      `evidence/dai-diode/phase2.1-hf-witness/dio_hf_space_deployment.json`.
    - Deployment digest:
      `sha256:f2809ebf5af5bf6090e2e80f7fe187957de44b314f3d9e8f2edf5f0f0c634808`.
    - Live independently checked receipt:
      `evidence/dai-diode/phase2.1-hf-witness/dio_hf_live_witness_receipt.json`.
    - Receipt digest:
      `sha256:d8fbd00ff620ff63327f7f83cdc9809414ce97f4cb39621b97d943d7741d7af1`.
    - Verified facts:
      live health identity, fresh nonce-bound Ed25519 attestation, pinned
      build/container identifiers, and a signature-verified proposal-bound
      semantic vote.
    - Authority remains:
      `remote_signed_software_witness_only`; it is not hardware, execution or
      production authority.
12. Add a hardware-backed phone or TEE witness for the governance role.
13. ~~Add Azure/GCP cloud TEE admission law for hardware-rooted DIO witness
    authority.~~
    - Module:
      `app/kernel/dai/dio_cloud_attestation.py`
    - Deployment guide:
      `deploy/dio-cloud-witness/`
    - Tests:
      `tests/test_dio_cloud_attestation.py`
    - Supported normalized evidence classes:
      Azure SEV-SNP,
      Azure TDX,
      Google Confidential VM vTPM,
      Google Confidential Space.
    - Admission binds:
      provider,
      TEE type,
      service verifier,
      node role,
      verifier build,
      measurement digest,
      public key fingerprint,
      challenge nonce,
      governance epoch,
      raw attestation digest,
      service verification digest,
      and freshness.
    - Nonclaim:
      Azure/GCP account ownership alone is not attestation.
14. ~~Add the first Google Cloud harvester that produces blocked or normalized
    `DIOCloudTeeEvidence` from the configured GCP project without fabricating
    missing VM attestation.~~
    - Script:
      `scripts/harvest_dio_gcp_tee_attestation.py`
    - Live project:
      `dio-attested-witnesses`.
    - Enabled APIs:
      `compute.googleapis.com`,
      `confidentialcomputing.googleapis.com`.
    - Current live result:
      `gcp_no_compute_instances_found`.
    - Evidence:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-live-001/dio_gcp_tee_attestation_harvest.json`.
    - Harvest digest:
      `sha256:86f595d8380cf28e8958b2bb67bb58bd0116eecaf5f679cd9c836068d91a6df4`.
15. ~~Create or target a live Google Confidential VM witness, then rerun the GCP
    harvester with `--instance <name> --zone <zone>`.~~
    - Live Africa South target:
      `dio-gcp-phase2-witness-01` in `africa-south1-a`.
    - Instance ID:
      `4372098688263098400`.
    - External IP:
      `34.35.123.232`.
    - Confidential instance config:
      `confidentialInstanceType = SEV`.
    - Initial harvester result:
      blocked because the harvester only accepted the older
      `enableConfidentialCompute = true` shape.
    - Parser correction:
      accept `confidentialInstanceType` values `SEV`, `SEV_SNP` and `TDX` as
      confidential-compute inventory evidence.
    - Current inventory-bound live receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-live-002/dio_gcp_tee_attestation_harvest.json`.
    - Harvest digest:
      `sha256:d87a708ebec128f5a1420904db19728bdbe31c9cc90dd355ab0f06c340217166`.
    - Admission report digest:
      `sha256:e593d2f638307ef09e6b07e23f9e38b3fb3b6001bd28feb0355038b834902a59`.
    - Evidence digest:
      `sha256:b14393a4912990f3c1e1be61f73ad4911b1dd3d1efb74027129b9714ad7f84e0`.
    - Boundary:
      this proves a live GCP Confidential Space / Confidential VM inventory path
      is digest-bound; final publication-grade hardware attestation still needs
      the raw Confidential Space attestation token/JWT packet.
    - Launch failure:
      the Confidential Space workload terminated because
      `tee-container-log-redirect=cloud_logging` was requested but the workload
      image/launch policy disallowed logging redirection outside an authorized
      debug/log policy.
    - Corrective launch law:
      recreate/start without `tee-container-log-redirect`, or rebuild/sign the
      workload image with a launch policy that explicitly permits the selected
      logging mode; packet delivery should use an allowed sink such as GCS or a
      relying-party token endpoint.
    - Corrected receipt after token-boundary patch:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-live-003/dio_gcp_tee_attestation_harvest.json`.
    - Corrected harvest digest:
      `sha256:954dba6e267576e888f3920035c988940d90967f0186184fa5adfdc605dbd60b`.
    - Corrected token boundary fields:
      `raw_provider_attestation_token_present = false`,
      `publication_grade_hardware_attestation = false`.
    - Pinned witness image:
      `africa-south1-docker.pkg.dev/dio-attested-witnesses/dio-witnesses/phase2-attestation-smoke@sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592`.
    - GCP live notes:
      `deploy/dio-cloud-witness/gcp-confidential-space-witness.md`.
    - Witness-02 corrected launch:
      removed `tee-container-log-redirect`, used the pinned digest image and
      reached Confidential Space attestation refresh.
    - Witness-02 inventory digest:
      `sha256:3119d9459d8a6d2a8d7703bcfa041af02ec5a0575ec25af0d6ec9434c69730b2`.
    - Witness-02 serial token-claims evidence:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-token/gcp_confidential_space_attestation_token_from_serial.txt`.
    - Witness-02 token-bound harvest:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-token/dio_gcp_tee_attestation_harvest.json`.
    - Witness-02 token-bound harvest digest:
      `sha256:a1280b31dc3102c76f1dffe861ddffdd8d97eb70bc289176c95cd665d248b069`.
    - Witness-02 token boundary:
      `raw_provider_attestation_token_present = true`,
      `raw_token_shape = opaque_text`,
      `publication_grade_hardware_attestation = false`.
    - Witness-02 remaining workload failure:
      workload exited non-zero because the allowed launch-policy env overrides
      `DIO_OUTPUT_BUCKET`, `DIO_OUTPUT_OBJECT` and
      `DIO_PHASE2_EVIDENCE_ROOT` were not supplied.
    - Witness-03 corrective launch:
      pass the allowed env vars through `tee-env-...` metadata and write the
      packet to a GCS output bucket.
    - Repaired witness-02 compact JWT result:
      `PASS: compact provider JWT recovered`.
    - Repaired witness-02 packet:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet.json`.
    - Packet digest:
      `sha256:c3118d58a8aed6d3c63c1c62a917603b00fd1d28bdca97a5b2b6856c57ef33cb`.
    - Vote digest:
      `sha256:b2d4ef2c6039cad816d26b158795fabdaa9296f2c9eb5f8027493566412ad9b7`.
    - Binding / JWT nonce:
      `sha256:655ba0a3b1d68b164db043591d081687b87e0ad40dd7329edda85352226b440d`.
    - JWT-bound harvester result:
      `raw_provider_attestation_token_present = true`,
      `raw_token_shape = jwt_compact`.
    - JWT-bound harvester digest:
      `sha256:c988277ee181de62498bde75d9c64816740b68a9efa4b106ac8f0b77992cefcc`.
    - Local verifier:
      `scripts/verify_dio_gcp_attestation_packet.py`.
    - Local verification receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification.json`.
    - Local verification digest:
      `sha256:4c32e3049f14459d0dfb37e371a0982f2634f2da213f4ff44e4a03dc1d4aed01`.
    - Local verification result:
      `passed = true`,
      `red_gates = []`;
      packet digest, vote digest, binding, JWT issuer, audience, nonce, secure
      boot, Confidential Space name, hardware model, pinned image digest,
      project, zone, instance and evidence-root env override all match.
    - Google JWKS signature verifier upgrade:
      `scripts/verify_dio_gcp_attestation_packet.py` now supports
      `--verify-google-signature`, `--jwks-file`, `--save-jwks` and
      `--evaluation-time`.
    - Live Google Confidential Space JWKS verification receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification-google-signature.json`.
    - Frozen offline JWKS verification receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification-google-signature-offline-frozen.json`.
    - Frozen offline receipt file SHA-256:
      `cb2d7fa3bb8ebe8b7fdf6a2520726e0845d47cd8236901f69e608d6153b91e45`.
    - Frozen offline verification digest:
      `sha256:966bf9fb70c48cd9b0cec71132ba6fc4ba90cc3e64e3a27da8ce3d85901c2edf`.
    - Google Confidential Space JWKS digest:
      `sha256:9aa5655c53bca510b2d13bcb9d7ebea9302b973bc50b35dae93ddadaa8968c17`.
    - Signature verification result:
      `signature_verified = true`,
      `jwt_signature_rs256_google_jwks_valid = true`,
      `red_gates = []`.
    - Remaining boundary:
      the compact JWT signature is provider-verified against Google
      Confidential Space JWKS, but this verifier does not independently
      reconstruct the lower-level SNP/TDX quote material; production authority
      remains off: `production_authority_allowed = false`.
16. ~~Add Azure harvester that produces normalized `DIOCloudTeeEvidence` from a
    live Azure guest-attestation / MAA flow, while blocking honestly when only
    subscription/VM inventory exists.~~
    - Script:
      `scripts/harvest_dio_azure_tee_attestation.py`
    - Original target location:
      `westeurope`.
    - Revised target location:
      `southafricanorth`.
    - Authenticated subscription:
      `658c71c0-13dd-4b25-8518-976b2809464e`.
    - Authenticated user:
      `buntbyron1@gmail.com`.
    - Registered provider observed:
      `Microsoft.Attestation`.
    - Boundary:
      Azure account ownership and VM inventory are not hardware attestation;
      green admission requires a Confidential VM plus raw guest-attestation /
      MAA token/report supplied with `--raw-attestation-token-file`.
    - Current live result:
      `azure_no_vms_found_in_location`.
    - Evidence:
      `evidence/dai-diode/phase2.1-cloud-witness/azure-live-001/dio_azure_tee_attestation_harvest.json`.
    - Harvest digest:
      `sha256:e12d21f8f0ca0776b30dd7d72dc9c4143de7bf296d01b26066c1d29b94a286f3`.
    - Next live step:
      create or target an Azure Confidential VM in South Africa North, run the guest
      attestation / MAA collector inside it, then rerun with
      `--resource-group`, `--vm` and `--raw-attestation-token-file`.
    - West Europe create attempt:
      Azure refused new-customer resource creation with
      `RequestDisallowedByAzure` / `locationineligible`; the resource group was
      created but VM/network/public-IP/NIC creation was blocked.
    - South Africa North VM discovery:
      `Standard_DC2as_v6`, `Standard_DC2ads_v6`, `Standard_DC2as_v5`,
      `Standard_DC2ads_v5`-family successors and larger DC/EC confidential
      families are visible through Azure CLI; the Ubuntu Confidential VM Jammy
      image resolves.
    - Corrected SA preflight:
      account, Compute, Network and Attestation providers are registered;
      `Standard_DC2as_v6`, `Standard_DC4as_v6` and `Standard_DC2ads_v6` are
      visible in `southafricanorth`; image
      `Canonical:0001-com-ubuntu-confidential-vm-jammy:22_04-lts-cvm:latest`
      resolves as `x64`.
    - Corrected create target:
      resource group `dio-azure-witness-sa-rg`,
      VM `dio-azure-tee-governance-01`,
      location `southafricanorth`,
      size `Standard_DC2as_v6`.
    - South Africa North create blocker:
      Azure preflight refused the VM because
      `standardDCasv6Family` quota is `0` in `SouthAfricaNorth`; the VM needs
      `2` cores.
    - Helper correction:
      `scripts/setup_dio_azure_confidential_vm.sh` now has read-only
      `quota` and `request-quota-help` modes and `create` fails fast before
      VM creation when quota is insufficient.
    - SKU/quota distinction:
      Azure shows `Standard_DC2as_v6` and other `standardDCasv6Family` SKUs as
      visible in `southafricanorth` with zones and no restrictions, but the
      subscription quota row for `standardDCasv6Family` remains limit `0`.
    - Helper addition:
      `scripts/setup_dio_azure_confidential_vm.sh skus` reports SKU visibility
      separately from `quota`.
    - Azure setup helper:
      `scripts/setup_dio_azure_confidential_vm.sh`.
    - Azure setup guide:
      `deploy/dio-cloud-witness/azure-confidential-vm-witness.md`.
17. ~~Add a GitHub Actions remote software witness lane using OIDC/Sigstore
    artifact attestations.~~
    - Workflow:
      `.github/workflows/dio-remote-witness.yml`
    - Packet emitter:
      `scripts/run_dio_github_actions_witness.py`
    - Local packet verifier:
      `scripts/verify_dio_github_actions_witness.py`
    - Authority:
      `remote_oidc_sigstore_software_witness_only`.
    - Nonclaims:
      not hardware attestation,
      not execution authority,
      not production authority,
      not a substitute for Azure/GCP TEE.
    - Local dry-run packet digest:
      `sha256:4009784be2007daf4a0bcc43a8f5a15a7636c4cfd862d126bcbeb5584d4d9538`.
18. ~~Push and dispatch the GitHub workflow, then verify the downloaded packet
    with `gh attestation verify`.~~
    - First independent run:
      `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30936843912`.
    - Honest result:
      failed in clean GitHub runner before witness packet emission because
      `PyYAML` was missing from the focused dependency install.
    - Fix in progress:
      add `PyYAML==6.0.2` to the workflow dependency closure, push again and
      require a fresh remote packet plus Sigstore/GitHub attestation.
    - Second independent run:
      `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30937109797`.
    - Honest result:
      dependency closure progressed, but pytest loaded the global
      `tests/conftest.py`, initialized the wider BEAST service factory and
      failed on unrelated full-stack `numpy` dependency closure.
    - Fix in progress:
      run the two DIO remote witness contract tests with `--noconftest`; local
      focused command gives `12 passed`.
    - Successful independent run:
      `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30937227770`.
    - Downloaded packet:
      `evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_packet.json`.
    - Packet digest (recomputed exactly):
      `sha256:9f03a0bc8b50887a02619c4c267fced4d96b7ebfcdd7ba686febce0ea35facdd`.
    - GitHub/Sigstore artifact-attestation verification receipt:
      `evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_verification.json`.
    - Verification digest:
      `sha256:0b7ccd56b6bea180d9f1933ceac191c666fd92cca34366918f03026bb8389313`.
    - Result:
      `gh attestation verify` passed with no red gates. Authority remains
      `remote_oidc_sigstore_software_witness_only`.
19. ~~Add AWS Nitro as the third cloud TEE witness lane.~~
    - Admission-law support:
      `provider = aws`,
      `tee_type = aws_nitro_tpm | aws_nitro_enclave`,
      `service_verifier = aws_nitro_attestation`.
    - Harvester:
      `scripts/harvest_dio_aws_tee_attestation.py`.
    - Setup guide:
      `deploy/dio-cloud-witness/aws-nitro-witness.md`.
    - Tests:
      `tests/test_dio_cloud_attestation.py` now includes AWS NitroTPM witness
      admission; `tests/test_dio_aws_harvester.py` covers the AWS harvester
      green branch and redaction of AWS identity material in blocked receipts.
    - Live AWS account status:
      STS identity works with region `af-south-1`; account identity is recorded
      only as a digest.
    - Live receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-001/dio_aws_tee_attestation_harvest.json`.
    - Live blocked reason:
      `aws_ec2_describe_instances_unavailable_or_unauthorized`.
    - Harvest digest:
      `sha256:b46c18ef16f91f2c6c0bedaf2e91bcbcc59f71f1493d76af75432ed870e2d882`.
    - Required next AWS permission:
      grant the witness IAM user read-only EC2 inventory:
      `ec2:DescribeInstances`; optional preflight:
      `ec2:DescribeRegions`.
    - IAM policy attach attempt:
      attempted to attach `DIOReadOnlyEC2WitnessInventory` to user
      `beast-vector` from the active CLI principal; AWS denied the operation
      because the active principal does not have `iam:PutUserPolicy`.
    - Active CLI boundary:
      `aws sts get-caller-identity` works, but the active principal still lacks
      `ec2:DescribeInstances`; the AWS harvester remains blocked with the same
      digest-bound receipt.
    - Profile switch:
      configured and verified the `beast-vector` AWS CLI profile; STS works
      under that profile.
    - Second live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-002/dio_aws_tee_attestation_harvest.json`.
    - Second live AWS result:
      EC2 inventory is now authorized, but there are zero EC2 instances in
      `af-south-1` for the `beast-vector` profile.
    - Second harvest digest:
      `sha256:808af318da9c617350fbabebf98eeb1dde942e7e88dace26fcb4347cec2abb75`.
    - Third live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-003/dio_aws_tee_attestation_harvest.json`.
    - Third live AWS result:
      EC2 instance `dio-aws-nitro-witness-01` is running as a `t3.micro`, but
      AWS reports `TpmSupport = null`, `EnclaveOptions.Enabled = false`,
      `BootMode = uefi-preferred`, `CurrentInstanceBootMode = uefi`.
    - Third blocked reason:
      `aws_instance_has_no_nitro_tpm_or_enclave_signal`.
    - Third harvest digest:
      `sha256:d2c961611393e0b65335f9b9913f9bf06463b1c0e177fa6f8dddc2bf288c8a06`.
    - Fourth live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-004/dio_aws_tee_attestation_harvest.json`.
    - Fourth live AWS result:
      instance `i-099602b8015c23124` is running in `af-south-1` with
      `TpmSupport = v2.0`, UEFI boot, and no Nitro Enclave enabled. This is
      the correct NitroTPM witness substrate.
    - Fourth blocked reason:
      `aws_raw_nitro_attestation_document_required`.
    - Fourth harvest digest:
      `sha256:5abff0b37d94bf44e8493910d14142958088df9f24a20e876e1bba262db8736c`.
    - ~~Make missing-raw AWS receipts challenge-bound so separate live
      attestation attempts cannot collapse to the same blocked digest.~~
      `scripts/harvest_dio_aws_tee_attestation.py` now records
      `challenge_nonce_digest` when a NitroTPM/Nitro Enclave raw document is
      missing; regression coverage was added in `tests/test_dio_aws_harvester.py`.
    - Fifth live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-005/dio_aws_tee_attestation_harvest.json`.
    - Fifth live AWS result:
      instance `i-099602b8015c23124` exposes `/dev/tpm0` and `/dev/tpmrm0`,
      reports `TpmSupport = v2.0`, and can answer `tpm2_getcap`, but the
      pinned AWS NitroTPM attestation tool cannot obtain a raw document from
      this runtime.
    - Fifth live AWS nonce digest:
      `sha256:a9a3722a28bff52defe6c45c3c076c5678037439f98df872957874d9bcbafda7`.
    - Fifth live AWS harvest digest:
      `sha256:42139bd449e050888c2b3965420fc52d0a7dd6c1f24fd6ddb89c00e9defba18e`.
    - Fifth live AWS evidence files:
      `nitro_tpm_capabilities.txt` records
      `TPM2_PT_NV_INDEX_MAX = 0x800`, `TPM2_PT_MAX_RESPONSE_SIZE = 0x1000`
      and `TPM2_PT_NV_BUFFER_MAX = 0x400`;
      `nitro_tpm_runtime_attempt.log` records the pinned AWS tool failure
      `TPM Error 0x2d5` and a compatibility-buffer experiment ending in
      `command code not supported`.
    - Sixth live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-006/dio_aws_tee_attestation_harvest.json`.
    - Sixth live AWS result:
      instance `i-049ebd67963f06160` is running in `af-south-1` as
      `c7i-flex.large` with `TpmSupport = v2.0`, but
      `EnclaveOptions.Enabled = false`, `KeyName = null`, and its default
      security group allows only self-referenced internal traffic. SSH timed
      out, and no inside-runtime raw attestation document could be collected.
    - Sixth live AWS harvest digest:
      `sha256:6017ae7f88f7927cac332196a3ab5c0225ff6cfb09ea29e38202388cfb92dfad`.
    - Eighth live AWS receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/dio_aws_tee_attestation_harvest.json`.
    - Eighth live AWS result:
      instance `i-0b71289635c195cd0` is running in `af-south-1` as
      `c5a.xlarge` from AMI `ami-09140127a77da9630`, with
      `TpmSupport = v2.0`, `EnclaveOptions.Enabled = true`, key pair
      `dio-aws-nitro-witness-01`, IMDSv2 required, public SSH access from the
      current runner IP and SSM profile `SSMInstanceProfile`.
    - Eighth live AWS raw document:
      `nitro-tpm-attestation-document.cbor`, 5258 bytes, digest
      `sha256:9059b30540b37e2b75e5f9a516bfeab2f7ef65cc6c931ec51919dacf0f954066`.
    - Eighth live AWS admission:
      `green = true`,
      `tee_type = aws_nitro_enclave`,
      `service_verifier = aws_nitro_attestation`,
      `maximum_authority = hardware_rooted_governance_vote_only`,
      `production_authority_allowed = false`.
    - ~~Add full AWS Nitro COSE/x509/PCR verifier and bind strict verification
      into the live AWS harvester receipt.~~
      `scripts/verify_dio_aws_nitro_attestation_document.py` decodes
      COSE_Sign1/CBOR, verifies ES384 COSE signature, verifies the x509 chain
      to the pinned AWS Nitro root fingerprint, checks nonce/user-data,
      instance/module identity and explicit PCR policy.
    - Eighth live AWS strict verifier receipt:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/dio_aws_nitro_attestation_document_verification.json`.
    - Eighth live AWS strict verifier digest:
      `sha256:bb67a662c36adee1bb01d18e21d36fe25c6ecc71a3ff1f49c78076b847841466`.
    - Eighth live AWS PCR policy:
      `evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-pcr-policy-live-008.json`.
    - Eighth live AWS strict harvest digest:
      `sha256:c15cda89dfff726b6da067455abdb94ba5e618a4b609cccd7898c129ece72aaa`.
    - Eighth live AWS initial digest-bound harvest digest:
      `sha256:310a0ac258e9542b72a4b864bff82cfaf2d7fa72b4093dd58c4289506017a0f1`.
    - Remaining AWS boundary:
      AWS now has a raw NitroTPM attestation document captured from an
      Enclave-enabled EC2 runtime, verified through COSE/x509/PCR policy and
      admitted by BEAST's digest-bound cloud witness policy. Production
      authority remains deliberately off pending multi-party quorum publication
      policy, not because the AWS document verifier is missing.

## Operational Phase 3 implementation progress: multi-domain composition

Goal:

> Prove that BEAST can treat verified capabilities as frozen fossils, compose
> them with other independently verified facts, refuse unsupported causal gaps
> and route only unresolved residue.

This phase must move beyond “one solved live action” into “capabilities as
parts of thought.”

1. ~~Register the frozen Phase-2 exact X2 proof as an immutable capability
   fossil for later composition.~~
   - Fossil verifier:
     `app/kernel/dai/phase3_fossil.py`
   - Runner:
     `scripts/run_dai_phase3_fossil_registry.py`
   - Tests:
     `tests/test_dai_phase3_fossil.py`
   - Fossil receipt:
     `evidence/dai-diode/phase3-composition-001/phase3_phase2_fossil_receipt.json`
   - Fossil digest:
     `sha256:a438e0ad8e2f3bae72c24c51fea2b648e4ea5c9eb2a8fa612f233ef97d26a58e`
   - Receipt digest:
     `sha256:7f0d90bda84f1130198738a0ec29d009bb53edbb21588579b50799f751b692cc`
   - Boundary:
     `composition_use_allowed = true`,
     `execution_authority_allowed = false`.
2. ~~Add a second disposable operational domain: stale lockfile / stale
   PID-file cleanup with file/inode evidence and zero production authority.~~
   - Domain module:
     `app/kernel/dai/phase3_lockfile.py`
   - Runner:
     `scripts/run_dai_phase3_lockfile_domain.py`
   - Tests:
     `tests/test_dai_phase3_lockfile.py`
   - Evidence directory:
     `evidence/dai-diode/phase3-composition-001/lockfile-domain/`
   - Summary:
     `phase3_lockfile_domain_summary.json`
   - Summary digest:
     `sha256:4d7b80007dba10b71069bc383cf27996a2a62349645889845455f54d34e3542e`
   - Cleanup receipt digest:
     `sha256:242b814e6cb777d0a13aa7f8c9ed571c28a85c53a7475427b92adb82586a6339`
   - Replay refusal receipt digest:
     `sha256:c1a4c2c4ba5651b567c8df6a12d7a03ee180cbe208f2c4dd20ba6972ec29191f`
   - Boundary:
     `execution_scope = disposable_tempdir_lockfiles_only`,
     `provider_calls_used = 0`,
     `production_authority_allowed = false`.
3. ~~Add a third disposable operational domain: expired local certificate
   causing a bounded handshake refusal, with temporal authority and refusal on
   stale evidence.~~
   - Domain module:
     `app/kernel/dai/phase3_certificate.py`
   - Runner:
     `scripts/run_dai_phase3_certificate_domain.py`
   - Tests:
     `tests/test_dai_phase3_certificate.py`
   - Evidence directory:
     `evidence/dai-diode/phase3-composition-001/certificate-domain/`
   - Summary:
     `phase3_certificate_domain_summary.json`
   - Summary digest:
     `sha256:f5d743f5699a5377bdbde30bca0c10216410a3b5415d3636e4bc22e42a9a0635`
   - Handshake receipt digest:
     `sha256:4c4c38f7e160192a0e635c42757f945770b42269ac12ed24b96fe24b098bb610`
   - Boundary:
     `execution_scope = disposable_localhost_certificate_handshake_only`,
     `expired_certificate_refused = true`,
     `expired_app_payload_received = false`,
     `provider_calls_used = 0`,
     `production_authority_allowed = false`.
4. ~~Build a `Phase3CompositionGraph` that can combine fossils, live facts,
   topology facts, policy facts and current evidence without copying domain
   logic into the answerer.~~
   - Graph module:
     `app/kernel/dai/phase3_composition.py`
   - Runner:
     `scripts/run_dai_phase3_composition_graph.py`
   - Tests:
     `tests/test_dai_phase3_composition.py`
   - Evidence directory:
     `evidence/dai-diode/phase3-composition-001/composition-graph/`
   - Graph:
     `phase3_composition_graph.json`
   - Graph receipt:
     `phase3_composition_graph_receipt.json`
   - Graph digest:
     `sha256:20513df6fe5aaf356d59f72f58850a21d16f13f94521448e51ee4c7b38917c38`
   - Receipt digest:
     `sha256:6e0d82d361921418b173537f5f479d04ee4111d6355e804597d9692e51870719`
   - Composition facts:
     `fact_count = 15`, `edge_count = 8`.
   - Derived claims:
     `multi_domain_composition_ready`,
     `bounded_composition_answer_available`,
     `execution_refused_by_policy`.
   - Boundary:
     `ordinary_answer_available = true`,
     `residual_required = false`,
     `provider_calls_used = 0`,
     `production_authority_allowed = false`,
     `execution_authority_allowed = false`.
5. ~~Add relevance pruning so unrelated causal branches cannot leak into a
   requested explanation.~~
   - Compiler:
     `prune_phase3_composition_graph()` in
     `app/kernel/dai/phase3_composition.py`.
   - Law:
     relevance is backward reachability from explicit answer claims through
     supported causal edges—not shared subjects, labels or graph membership.
   - Green receipt:
     `evidence/dai-diode/phase3-composition-001/composition-graph/phase3_relevance_receipt.json`.
   - Receipt digest:
     `sha256:967e6f655a52121665db2a762c3ceadfa3301ae69b9bb29dd0d2695713c54f02`.
   - Result:
     9 selected facts / 7 selected edges; 6 facts and 1 edge excluded.
   - Hostile controls:
     a disconnected same-subject causal branch is excluded; an unsupported
     edge into a requested conclusion becomes residual and removes ordinary
     answer availability.
6. ~~Add residual routing law: unsupported/residual-required propositions are not
   speakable facts until a verified residual result is promoted.~~
   - Capability gate:
     `route_phase3_residuals()` in `app/kernel/dai/phase3_composition.py`.
   - Law:
     `residual_required`, `stale` and `unsupported` relevant inputs select
     `action = refuse`, set `ordinary_answer_available = false`, and expose
     zero `speakable_fact_ids`; only a dedicated refusal artifact is allowed.
   - Green receipt:
     `evidence/dai-diode/phase3-composition-001/composition-graph/phase3_residual_route_receipt.json`.
   - Receipt digest:
     `sha256:adb2749778ae0747efac04013421aff61f1768c314c1383a968bbc86bcda2074`.
   - Hostile controls:
     residual-required, stale and unsupported mutations all refuse and cannot
     narrate the injected value as a fact.
7. ~~Add deterministic text and visual composition outputs generated from the same
   canonical composition graph, with independent entailment checks.~~
   - Expression module:
     `app/kernel/dai/phase3_expression.py`.
   - Law:
     text and SVG compile independently from the residual-route-authorized
     fact set. The visual compiler never receives the generated text.
   - Outputs:
     `phase3_expression.txt` and `phase3_expression.svg` under
     `evidence/dai-diode/phase3-composition-001/composition-graph/`.
   - Independent verifiers:
     text checks each permitted proposition and excludes unselected fact IDs;
     SVG checks proposition labels/values, causal edges and canvas bounds.
   - Green expression receipt:
     `phase3_expression_receipt.json`.
   - Receipt digest:
     `sha256:010fa57131d4830f0fb46cd563a157031615b89fb4e3ede6c5a0c0d99b702222`.
   - Result:
     9 authorized facts rendered, joined verification green, zero provider
     calls, and production/execution authority false.
   - Hostile controls:
     residual input produces only a refusal text/SVG artifact; tampering a
     visual proposition value independently fails visual entailment.
8. ~~Run a multi-domain hostile gauntlet covering copied receipts, reversed
   causality, stale evidence, irrelevant graph branches, false Boolean
   polarity, authority inflation and fossil mutation.~~
   - Runner:
     `scripts/run_dai_phase3_hostile_gauntlet.py`.
   - Green receipt:
     `evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json`.
   - Receipt digest:
     `sha256:638122c7c4e086d0723f625ecb9db7aae51c1b5bdf99a0f5958443afd8b89e3d`.
   - Result:
     7/7 attacks blocked: receipt role substitution, fossil mutation,
     reversed causality, stale evidence, irrelevant same-subject branch,
     Boolean-polarity tampering and authority inflation.
9. ~~Package Phase-3 as:
   `DAI-Diode-Phase-3__Multi-Domain-Capability-Composition__2026-08-04`.~~
   - Fossil:
     `artifacts/DAI-Diode-Phase-3__Multi-Domain-Capability-Composition__2026-08-04.zip`.
   - ZIP digest:
     `sha256:1e2719757b418a5a2028794f3ed601aa79f09877ba07036ee77e9a5218c837f4`.
   - Contents:
     exact evidence, source overlay, focused tests, dependency specifications,
     predecessor Phase-2.1 fossil, claims/nonclaims/limits, authority map,
     clean-environment guide and manifest verifier.
   - Verification:
     73 manifest entries verified; ZIP integrity passed; focused Phase-3 suite
     passed `15` tests.
   - Immutability law:
     the packager refuses to replace this release identity; corrections must
     use a new release identity.

## Phase 3.1 implementation progress: Closed-World Entailment and Provenance

Goal:

> Close the caveats discovered after the Phase-3 fossil: expression verifiers
> must reject unauthorized extra claims, semantic digest marker tampering and
> summary-only self-hashed evidence substitution before the online Commons
> network is promoted as the next release line.

1. ~~Make text entailment closed-world.~~
   - Verifier:
     `verify_phase3_text_entailment()` in
     `app/kernel/dai/phase3_expression.py`.
   - Law:
     the full text output must exactly match the authorized grammar:
     answer/refusal header, semantic digest marker, authorized fact lines and
     boundary line. Extra unmarked assertions such as
     `production authority allowed = true` are red gates.
   - Tests:
     `tests/test_dai_phase3_expression.py`.
2. ~~Make SVG entailment closed-world.~~
   - Verifier:
     `verify_phase3_visual_entailment()` in
     `app/kernel/dai/phase3_expression.py`.
   - Law:
     only whitelisted SVG elements/attributes are accepted; every semantic text
     value must derive from an authorized fact, authorized edge, refusal marker
     or semantic digest marker. Untagged semantic claims are red gates.
   - Tests:
     `tests/test_dai_phase3_expression.py`.
3. ~~Bind rendered semantic digest markers back to the expression bundle.~~
   - Text gate:
     `text_semantic_digest_marker_matches`.
   - Visual gate:
     `visual_semantic_digest_marker_matches`.
   - Hostile control:
     changing the digest printed in either artifact without changing the bundle
     is rejected.
4. ~~Expand the Phase-3 hostile gauntlet to cover the new caveat attacks.~~
   - Runner:
     `scripts/run_dai_phase3_hostile_gauntlet.py`.
   - New cases:
     `extra_text_claim_rejected`,
     `extra_visual_claim_rejected`,
     `semantic_digest_marker_tamper_rejected`.
   - Fresh receipt:
     `evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json`.
   - Result:
     `10/10` attacks blocked.
   - Receipt digest:
     `sha256:971911fad26b90514bf724103538881357f2018849c1b2d69e2d60fa97ae871b`.
5. ~~Add transitive provenance checks for Phase-3 domain summaries.~~
   - Builder:
     `build_phase3_composition_graph()` in
     `app/kernel/dai/phase3_composition.py`.
   - Law:
     lockfile and certificate summaries must bind the adjacent producer
     receipts and world leases by recomputed digest; the Phase-2 fossil receipt
     must match the pinned fossil, summary and receipt digests.
   - Regression:
     a forged but internally self-consistent summary without its producer
     receipt files is rejected.
6. ~~Make future Phase-3 package verification closed-world.~~
   - Packager:
     `scripts/package_dai_phase3_artifact.py`.
   - Law:
     the verifier now checks `actual_files == manifest_files` except for the
     explicitly regenerated manifest/release files; unmanifested files under
     `source/` or any other package directory are rejected.
   - Reproduction guide:
     now lists the exact eight Phase-3 runner commands in order.
   - Clean-room import fix:
     `tests/__init__.py`.
7. ~~Add signed capability/evidence manifests for Phase 3.1 release packaging.
   Ed25519 is sufficient for this release; ML-KEM remains transport/key
   establishment, not a signing mechanism.~~
   - Packager:
     `scripts/package_dai_phase3_1_artifact.py`.
   - Signed manifests:
     `CAPABILITY_EVIDENCE_MANIFEST.json`,
     `CAPABILITY_EVIDENCE_MANIFEST.sig.json`,
     `RELEASE_MANIFEST.json`,
     `RELEASE_MANIFEST.sig.json`.
   - Signature law:
     the bundled verifier recomputes canonical manifest digests and verifies
     Ed25519 signatures before trusting critical capability/evidence receipts.
   - Manifest digest:
     `sha256:3808ce69f7a314034cc002b2862e5e691ff2cee28642ea96780ad39b5e919a3e`.
   - Capsule signing key fingerprint:
     `sha256:09d41e74d0dadc322f0f7bc8bb36b73d815dcf72308cdf21f941e24d53a4fae4`.
   - Boundary:
     this signs the capsule manifest, not public identity or third-party time.
8. ~~Package `DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04`
   only after signed manifests and one-command clean-room verification pass.~~
   - Bundle:
     `artifacts/DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04/`.
   - ZIP:
     `artifacts/DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04.zip`.
   - ZIP digest:
     `sha256:22b094e1e81cd9f6b75cfbb2637d5a8e9861dc6c3755c0ddb56b9d4068f2ef55`.
   - One-command verifier:
     `python3 verify_phase3_1_bundle.py` passed with `entry_count = 78`.
   - Hostile package checks:
     an added unmanifested file and a mutated signed manifest both failed
     verification as expected.

## Phase 4 implementation progress: DIO Commons Online Space Protocol

Goal:

> Turn individually verified witnesses into a constitutional online Commons:
> differentiated, reachable nodes sharing one proposal/evidence root, world
> state, governance epoch, admission lease and role-bound vote protocol—while
> preserving every node's strict authority ceiling.

1. ~~Define the canonical online Space schema: identity, capability manifest,
   attestation envelope, fresh challenge and signed active Commons lease.~~
   - Module:
     `app/kernel/dai/dio_commons_online.py`.
   - Objects:
     `DIOCommonsSpaceIdentity`, `DIOCommonsCapabilityManifest`,
     `DIOCommonsChallenge` and `DIOCommonsActiveLease`.
   - Binding law:
     the signed identity binds its public key fingerprint, verifier digest,
     manifest digest, attestation class, authority ceiling and epoch; the
     coordinator lease binds that identity/manifest plus fresh proposal,
     evidence root, world state and challenge.
   - Tests:
     `tests/test_dio_commons_online.py` (`2 passed`), including epoch/signature
     mutation and expired-lease refusal.
2. ~~Define admission law: registered key/operator root, unique required role,
   approved verifier/manifest, acceptable attestation class, fresh challenge,
   current epoch, unexpired lease and no duplicate key/operator root.~~
   - Policy objects:
     `DIOCommonsRegisteredSpace`, `DIOCommonsAdmissionPolicy` and
     `DIOCommonsAdmissionReport` in
     `app/kernel/dai/dio_commons_online.py`.
   - Admission function:
     `admit_commons_online_space()`.
   - Law:
     the admitted node must be registered by exact node id, role, operator
     root, signing-key fingerprint, verifier digest, capability-manifest
     digest, attestation class and authority ceiling; the challenge must be
     fresh and epoch-bound; active nodes cannot reuse node id, key, operator
     root or role; the coordinator key must match policy; a signed active lease
     is minted only after all gates pass.
   - Tests:
     `tests/test_dio_commons_online.py` (`5 passed`), including valid admission,
     stale challenge, wrong manifest, duplicate role/operator/key path and
     software-to-hardware attestation-class inflation.
   - Boundary:
     `execution_authority_allowed = false`,
     `production_authority_allowed = false`,
     and failed admission returns no lease.
3. ~~Upgrade the live HF semantic Space to the canonical surface:
   `/health`, `/identity`, `/manifest`, `/attestation`, `/v1/challenge`,
   `/v1/evaluate`, `/v1/vote`, `/v1/refresh-attestation`.~~
   - App:
     `app/dio_hf_witness_main.py`.
   - Deployment script:
     `scripts/deploy_dio_hf_witness_space.py`.
   - Verifier:
     `scripts/verify_dio_hf_witness.py`.
   - Local tests:
     `tests/test_dio_distributed_quorum.py` and
     `tests/test_dio_commons_online.py` (`12 passed`).
   - Live Space:
     `Byron230686/dio-phase2-semantic-witness`.
   - Hub commit:
     `a68ef5bda13cb3e652c48fb6bdd244ab3d2f7566`.
   - Deployment receipt:
     `evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_space_deployment.json`.
   - Deployment digest:
     `sha256:a8f77fa84cf9b8b278214243ed5cb684fc8913a4e3789b84d1beaaeaf0171119`.
   - Boundary:
     persistent signed software witness only; no provider, execution or
     production authority.
4. ~~Add adapters for GCP Confidential Space, AWS Nitro, Arda local and GitHub
   ephemeral provenance witness. Adapters must report their actual persistence
   and attestation class; one-shot/ephemeral adapters cannot claim persistent
   online-node status.~~
   - Adapter module:
     `app/kernel/dai/dio_commons_adapters.py`.
   - Runner:
     `scripts/run_dai_phase4_commons_adapters.py`.
   - Tests:
     `tests/test_dio_commons_adapters.py`.
   - Evidence:
     `evidence/dai-diode/phase4-commons-adapters/`.
   - Summary:
     `dio_phase4_commons_adapter_summary.json`.
   - Summary digest:
     `sha256:e0ae8ece835d1feb8de3c44805a247e9903914e49d355c662a4c150e9507e603`.
   - Adapted witnesses:
     GCP provider hardware attestation, AWS Nitro provider hardware
     attestation, GitHub ephemeral build provenance and Arda local physical
     witness.
   - Boundary:
     `adapted_count = 4`,
     `online_ready_count = 0`,
     `persistent_service_count = 0`,
     `provider_calls_used = 0`,
     `production_authority_allowed = false`,
     `execution_authority_allowed = false`.
5. ~~Build a Commons coordinator that mints a shared proposition session, issues
   challenge-bound leases, collects role-bound votes and verifies the joined
   quorum without execution authority.~~
   - Coordinator module:
     `app/kernel/dai/dio_commons_coordinator.py`.
   - Runner:
     `scripts/run_dai_phase4_commons_coordinator.py`.
   - Tests:
     `tests/test_dio_commons_coordinator.py`,
     `tests/test_dio_commons_coordinator_runner.py`.
   - Evidence:
     `evidence/dai-diode/phase4-commons-coordinator/dio_phase4_commons_coordinator_run.json`.
   - Result:
     live HF signed software witness plus GCP/AWS/GitHub/Arda adapter
     witnesses admitted into one shared proposal/evidence/world/epoch session.
   - Quorum:
     `heterogeneous_distributed_quorum`,
     `admitted_node_count = 5`,
     `valid_vote_count = 5`,
     `decision = approve`.
   - Session digest:
     `sha256:56b69007602f93a011b000034f2410a3eaa432876e63d8bd1f14fb9975596734`.
   - Quorum report digest:
     `sha256:59a22eeefe3cc1f895330a7186da9ec5f505878ba7955a6be158ac5f6e0767ad`.
   - Run digest:
     `sha256:ecbcb8048bff97e8a1fe2d9c6a6e66097c99a452c4bbaac892ffcba54c706a3d`.
   - Boundary:
     adapter votes are explicitly simulated from local signing keys because
     those adapted witnesses are evidence-bearing offline/one-shot spaces, not
     live online voting endpoints; execution and production authority remain
     false.
6. ~~Run a mixed online/offline Commons gauntlet: duplicate key/operator,
   stale epoch/lease, wrong manifest/verifier, attestation downgrade, replayed
   challenge, role collision, veto and adapter persistence inflation.~~
   - Runner:
     `scripts/run_dai_phase4_commons_gauntlet.py`.
   - Tests:
     `tests/test_dio_commons_gauntlet.py` and strengthened coordinator
     regressions in `tests/test_dio_commons_coordinator.py`.
   - Coordinator hardening:
     online HF admission is bound to `signed_software_runtime`, offline
     adapter node ids/operator roots must remain distinct, and invalid adapter
     vote construction becomes a red gate rather than a crash.
   - Green receipt:
     `evidence/dai-diode/phase4-commons-gauntlet/dio_phase4_commons_gauntlet_receipt.json`.
   - Receipt digest:
     `sha256:694f610a863c5e07cb5b5faba1639ed8bd1e3ae1e8957d9724df96c7f86d9ef7`.
   - Result:
     `11/11` hostile cases blocked, including authenticated veto enforcement
     and adapter persistence inflation refusal.
   - Boundary:
     `provider_calls_used = 0`,
     `execution_authority_allowed = false`,
     `production_authority_allowed = false`.
   - Coordinator replay note:
     the stored live HF vote is replayed at its harvest timestamp for
     deterministic offline regression; current live freshness remains the job
     of `scripts/verify_dio_hf_witness.py`.
7. ~~Perform a live HF protocol upgrade and harvest a fresh remote identity,
   manifest, challenge/lease and vote receipt.~~
   - Live receipt:
     `evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_live_witness_receipt.json`.
   - Receipt digest:
     `sha256:b78c726bbb17e23efa0f7a2ed99e00ed8948e50e6411aa38589c252f3113d5d7`.
   - Verified gates:
     signed identity, manifest digest, challenge digest, challenge-bound
     attestation, refresh attestation, `/v1/vote`, `/v1/evaluate`, public key
     fingerprint and source/container build pins.
   - Red gates:
     none.
8. ~~Package Phase 4 as a new fossil only after the online protocol gauntlet and
   live remote receipt both pass.~~
   - Frozen identity:
     `DAI-Diode-Phase-4__DIO-Commons-Online-Space-Protocol__2026-08-04`.
   - Packager:
     `scripts/package_dai_phase4_artifact.py`.
   - Bundle:
     `artifacts/DAI-Diode-Phase-4__DIO-Commons-Online-Space-Protocol__2026-08-04/`.
   - ZIP:
     `artifacts/DAI-Diode-Phase-4__DIO-Commons-Online-Space-Protocol__2026-08-04.zip`.
   - ZIP digest:
     `sha256:fc9e2af6a5f5419cdf67ae1d88d9d076e492b76252b0526510d259e894f986e7`.
   - Signed evidence manifest digest:
     `sha256:6a41729c7219a940e984f7de2007c6d8de6a832dcd131f6447965899a641f4ad`.
   - One-command verifier:
     `python3 verify_phase4_bundle.py` passed with `entry_count = 44` and
     `gauntlet_cases = 11`.
   - Extracted ZIP verifier:
     passed from `/tmp/tmp.rTwc2pExHr/`.
   - Contents:
     live HF deployment and vote receipt, Commons adapter evidence,
     hardened coordinator run, 11-case hostile gauntlet, source overlay,
     tests, dependencies, predecessor Phase-3.1 fossil, claims/nonclaims,
     authority map and clean reproduction guide.

## Phase 5 implementation progress: Autonomous Remote Witnesses

Goal:

> Move from coordinator-owned adapter vote simulation toward real remote
> witnesses that independently evaluate one proposal, bind their own admission
> evidence, sign their own vote and publish a verifier-checkable packet before
> quorum.

1. ~~Define a provider-neutral autonomous remote witness packet law.~~
   - Module:
     `app/kernel/dai/dio_remote_witness_packet.py`.
   - Objects:
     `DIOAutonomousRemoteWitnessPacket` and
     `DIOAutonomousRemoteWitnessVerification`.
   - Law:
     the packet must bind one node admission, one proposal packet, one signed
     vote, the admitted signing key, verifier commit, admission attestation
     digest, role, authority ceiling, freshness window and remote independent
     evaluation flag.
   - Signature law:
     the witness signs the packet envelope, and the vote remains separately
     signed by the same admitted witness key.
   - Hostile runner:
     `scripts/run_dai_phase5_remote_witness_packet_gauntlet.py`.
   - Tests:
     `tests/test_dio_remote_witness_packet.py`.
   - Green receipt:
     `evidence/dai-diode/phase5-remote-witness-packet/phase5_remote_witness_packet_gauntlet_receipt.json`.
   - Receipt digest:
     `sha256:d73ee9ce91657c4492d31561303f15c59d17664a138c2ac3620115ea65c03ce4`.
   - Result:
     `8/8` packet cases passed: valid autonomous packet admitted; bad packet
     signature, wrong proposal binding, stale packet, missing independent
     remote runtime, vote tampering, wrong admission digest and authority
     mismatch rejected.
   - Boundary:
     this creates the law autonomous witnesses must satisfy; it does not yet
     make AWS/GCP/GitHub/Arda persistent autonomous online voters.
2. ~~Upgrade the HF Space to emit the Phase-5 autonomous packet directly from
   `/v1/autonomous-packet`, reusing its existing identity, manifest,
   attestation and vote keys.~~
   - App:
     `app/dio_hf_witness_main.py`.
   - Deployment script:
     `scripts/deploy_dio_hf_witness_space.py`.
   - Live verifier:
     `scripts/verify_dio_hf_witness.py`.
   - Live Space:
     `Byron230686/dio-phase2-semantic-witness`.
   - Hub commit:
     `544a229085182448daa74c099b296d28a851fb9e`.
   - Deployment receipt:
     `evidence/dai-diode/phase5-hf-witness/dio_hf_phase5_space_deployment.json`.
   - Deployment digest:
     `sha256:069c0e9d4c3f5b8cefaa723c46f9294b0347c29595ad73eca6f81d03842c7d4f`.
   - Live receipt:
     `evidence/dai-diode/phase5-hf-witness/dio_hf_phase5_live_witness_receipt.json`.
   - Live receipt digest:
     `sha256:7db5480d63e96e07181e1cf2549d2551e764c954964230f1574e6e8de6c94d88`.
   - Autonomous packet digest:
     `sha256:e7faaf2faa6d75c2c84b89866a122e79e62e3fa0e6cf5d1e62822c751520c141`.
   - Autonomous packet verification digest:
     `sha256:5e8326c594c1b92abaa700f0d34d75050e13c85b178171cbb82188e104f74131`.
   - Verified gates:
     signed identity, manifest, challenge-bound attestation, vote signature,
     autonomous packet envelope signature, proposal/admission binding, remote
     runtime flag, independent evaluation flag and authority ceiling.
   - Red gates:
     none.
3. ~~Upgrade GitHub Actions witness output so the workflow emits a Phase-5
   autonomous packet and binds it to GitHub OIDC/artifact attestation.~~
   - Workflow:
     `.github/workflows/dio-remote-witness.yml`.
   - Emitter:
     `scripts/run_dio_github_actions_witness.py`.
   - Verifier:
     `scripts/verify_dio_github_actions_witness.py`.
   - New packet shape:
     `dio_github_actions_autonomous_witness_envelope` containing a
     provider-neutral `dio_autonomous_remote_witness_packet`, proposal packet,
     admission, node-signed vote, workflow identity digest and GitHub
     artifact-attestation requirement.
   - Backward compatibility:
     the old Phase-2.1 GitHub packet shape remains available through
     `--legacy` and still verifies for Phase-4 adapter evidence.
   - Local dry-run packet:
     `evidence/dai-diode/phase5-github-witness/local-dryrun/dio_github_actions_autonomous_witness_packet.json`.
   - Local dry-run envelope digest:
     `sha256:2bf5d2b4c1ce0c578c73a320397022897162f419b979edd6c894027c27b3caf4`.
   - Local dry-run verification:
     `evidence/dai-diode/phase5-github-witness/local-dryrun/dio_github_actions_autonomous_witness_verification.json`.
   - Local dry-run verification digest:
     `sha256:c21551c58993aa1b784d19a0cf666d4535a443cf657afb0b66c879077ba7d27c`.
   - Local dry-run autonomous packet digest:
     `sha256:961a069b72916bfc3a4e40ca13e44f0698738cbbe491bf8f606e43f2ffa42c62`.
   - Live GitHub Actions run:
     `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30959503947`.
   - Live GitHub commit:
     `1029f4564bb09cb0fec8d1b31519d090dff96119`.
   - Live downloaded packet:
     `evidence/dai-diode/phase5-github-witness/run-30959503947/dio_github_actions_autonomous_witness_packet.json`.
   - Live verification:
     `evidence/dai-diode/phase5-github-witness/run-30959503947/dio_github_actions_autonomous_witness_verification.json`.
   - Live envelope digest:
     `sha256:00775076a18042b6a301f555006fa2a07669351f1aaa9e70e77081810701e758`.
   - Live autonomous packet digest:
     `sha256:91b8f60988323c9ae43dffc65238bc79ec0e236156d25c05daeb30475f170cfa`.
   - Live verification digest:
     `sha256:54c40290acd0f1d9e43af546f3448b85b55cff444d57cbc0775ec5206cb6978b`.
   - Live GitHub/Sigstore artifact attestation:
     verified by `gh attestation verify --repo Byron2306/EdgeK-BEAST`.
   - Corroborating push-triggered run:
     `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30959504318`
     also completed successfully.
   - Tests:
     `tests/test_dio_github_actions_witness.py`,
     `tests/test_dio_remote_witness_packet.py`,
     `tests/test_dio_distributed_quorum.py` and
     `tests/test_dio_cloud_attestation.py` (`25 passed`).
   - Live workflow test command:
     `tests/test_dio_cloud_attestation.py`,
     `tests/test_dio_remote_witness_packet.py` and
     `tests/test_dio_github_actions_witness.py` (`17 passed`).
   - Boundary:
     GitHub is a remote OIDC/Sigstore software witness, not hardware
     attestation and not execution authority.
4. ~~Upgrade AWS Nitro and GCP Confidential Space harvesters so verified
   provider attestation can produce Phase-5 autonomous packets when the remote
   runtime actually signs the packet in situ.~~
   - Bridge:
     `app/kernel/dai/dio_cloud_autonomous_packet.py`.
   - Harvesters:
     `scripts/harvest_dio_aws_tee_attestation.py` and
     `scripts/harvest_dio_gcp_tee_attestation.py`.
   - New flags:
     `--emit-autonomous-packet` and `--remote-runtime-observed`.
   - Output envelopes:
     `dio_aws_autonomous_witness_envelope.json` and
     `dio_gcp_autonomous_witness_envelope.json`.
   - Law:
     a green harvest can be wrapped as a provider-neutral Phase-5 autonomous
     packet signed by the admitted witness key; the packet remains red unless
     `remote_runtime_observed` is true, so a local harvester cannot launder
     itself into a remote autonomous signer.
   - Tests:
     `tests/test_dio_cloud_autonomous_packet.py`,
     `tests/test_dio_github_actions_witness.py`,
     `tests/test_dio_remote_witness_packet.py`,
     `tests/test_dio_distributed_quorum.py` and
     `tests/test_dio_cloud_attestation.py` (`27 passed`).
   - Boundary:
     this wires the autonomous packet path for AWS/GCP harvesters; a final live
     cloud witness still needs the packet signed inside the AWS/GCP runtime and
     harvested with `--remote-runtime-observed`.
5. ~~Add a Phase-5 coordinator path that accepts autonomous packets directly and
   refuses local simulated adapter votes when a packet is expected.~~
   - Coordinator:
     `app/kernel/dai/dio_commons_coordinator.py`.
   - Quorum law update:
     `app/kernel/dai/dio_distributed_quorum.py` now recognizes
     `remote_oidc_sigstore_software_witness_only` as a bounded remote software
     witness authority.
   - Direct autonomous path:
     `run_commons_coordinator_session(..., autonomous_witness_envelopes=...)`
     parses each envelope, verifies the provider-neutral autonomous packet
     against the shared proposal/admission, admits its vote only if verification
     is green and records `autonomous_packet_digests`.
   - Refusal path:
     `expect_autonomous_packets=True` refuses local simulated adapter votes with
     `simulated_adapter_votes_refused_when_autonomous_expected`.
   - Session fields:
     `autonomous_packet_digests` and `autonomous_packet_count`.
   - Tests:
     `tests/test_dio_commons_coordinator.py`,
     `tests/test_dio_commons_coordinator_runner.py`,
     `tests/test_dio_cloud_autonomous_packet.py`,
     `tests/test_dio_github_actions_witness.py`,
     `tests/test_dio_remote_witness_packet.py`,
     `tests/test_dio_distributed_quorum.py` and
     `tests/test_dio_cloud_attestation.py` (`33 passed`).
5a. ~~Add shared-proposal cloud autonomous packet binding, Azure harvester
   parity and a mixed witness readiness receipt.~~
   - Bridge:
     `app/kernel/dai/dio_cloud_autonomous_packet.py` now accepts a
     coordinator-supplied `DIOProposalPacket`, so cloud autonomous witnesses can
     sign over the same Commons proposal instead of minting isolated
     cloud-local proposals.
   - Harvester:
     `scripts/harvest_dio_azure_tee_attestation.py` now supports
     `--emit-autonomous-packet`, `--remote-runtime-observed` and
     `--proposal-file`, matching the AWS/GCP autonomous packet path while still
     refusing green credit without a green Azure guest-attestation harvest. The
     AWS/GCP harvesters also expose `--proposal-file`, so all three cloud
     lanes can bind autonomous signatures to a coordinator-supplied Commons
     proposal.
   - Readiness runner:
     `scripts/run_dai_phase5_mixed_witness_readiness.py`.
   - Fresh HF refresh:
     `evidence/dai-diode/phase5-hf-witness/dio_hf_phase5_live_witness_receipt.json`.
   - HF refreshed receipt digest:
     `sha256:225b84ace597f5e017581683e289057aebfe251b396aa27961d273858a92938d`.
   - Mixed readiness receipt:
     `evidence/dai-diode/phase5-mixed-witness-readiness/dio_phase5_mixed_witness_readiness.json`.
   - Mixed readiness digest:
     `sha256:3eb98e2ddecc2e58df9e8bd9df49c04965ce9ea65cd698afb82cd29e9c6c301f`.
   - Result:
     HF and GitHub are fresh verified autonomous packets, but they do not yet
     share one proposal. GCP/AWS are green cloud harvests that can become
     autonomous packets only after in-runtime signing over the shared
     coordinator proposal. The stored Azure harvest remains blocked with
     `azure_no_vms_found_in_location`. A physical execution witness packet is
     still required before full Commons quorum.
   - Tests:
     `tests/test_dio_cloud_autonomous_packet.py`,
     `tests/test_dio_commons_coordinator.py`,
     `tests/test_dio_github_actions_witness.py` and
     `tests/test_dio_remote_witness_packet.py` (`18 passed`).
5b. ~~Mint one shared Phase-5 Commons proposal and prove HF/GitHub can bind
   autonomous packets to that exact proposal instead of self-minted smoke
   proposals.~~
   - Proposal minter:
     `scripts/mint_dai_phase5_shared_proposal.py`.
   - Shared proposal:
     `evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json`.
   - Shared proposal packet digest:
     `sha256:974d47dcb8f3d46b78f72de97b86a1f7960176423dcea46c37574810650bea86`.
   - Shared proposal digest:
     `sha256:5df338a298b4f95abcc6edfcdc98772b787848c3cc0694a144110ac3553fcaff`.
   - HF verifier:
     `scripts/verify_dio_hf_witness.py` now accepts `--proposal-file`.
   - Live HF shared-proposal receipt:
     `evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json`.
   - Live HF shared-proposal receipt digest:
     `sha256:a1737d69a90592873087c7a3bdf40d7e118923db53bf6fd96120c99fa9c8da0d`.
   - Live HF shared-proposal packet digest:
     `sha256:334699f9c5d21687874c7ec8a54b1ecd04196b2c877518b1ffc9423d290365f9`.
   - Live HF autonomous verification digest:
     `sha256:b8e74bc8fb9cfda4020582a2b74a6951eed6fada7351c7c7233dcc469e94b8a3`.
   - GitHub emitter:
     `scripts/run_dio_github_actions_witness.py` now accepts
     `--proposal-file`.
   - GitHub workflow:
     `.github/workflows/dio-remote-witness.yml` now accepts optional
     `workflow_dispatch` input `proposal_json_b64`, decodes it inside the
     runner and passes it to the packet emitter.
   - Local GitHub shared-proposal packet:
     `evidence/dai-diode/phase5-shared-quorum/github/dio_github_shared_proposal_witness_packet.local.json`.
   - Local GitHub shared-proposal envelope digest:
     `sha256:fb49dc3938627390c802d1c6bfe618c07075ecaf07b06bfa921fe8833c31f7e3`.
   - Local GitHub shared-proposal packet digest:
     `sha256:ff3aba97a3501974c08e8befb18d3a6921e68f278574a5261ed1ccbbb8a689fa`.
   - Local GitHub shared-proposal verification digest:
     `sha256:c299e4291728fa0059120f03d0e6788c7c290fa122728761cac4408975e1fb5e`.
   - Result:
     HF has already signed the shared proposal live with zero red gates.
     GitHub shared-proposal signing verifies locally; the remaining step is a
     live GitHub Actions dispatch from the updated workflow so GitHub OIDC /
     Sigstore attestation binds the same shared proposal.
   - Tests:
     `tests/test_dio_github_actions_witness.py`,
     `tests/test_dio_cloud_autonomous_packet.py`,
     `tests/test_dio_commons_coordinator.py` and
     `tests/test_dio_remote_witness_packet.py` (`19 passed`).
6. ~~Run a live mixed quorum with at least HF plus one cloud/GitHub autonomous
   packet, while preserving the nonclaim that non-persistent sources remain
   adapter-only.~~
   - Shared proposal packet digest:
     `sha256:974d47dcb8f3d46b78f72de97b86a1f7960176423dcea46c37574810650bea86`.
   - Live HF semantic witness:
     `evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json`.
   - Live GitHub run:
     `https://github.com/Byron2306/EdgeK-BEAST/actions/runs/30960436614`.
   - Live GitHub packet:
     `evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_packet.json`.
   - Live GitHub envelope digest:
     `sha256:3440cb4385a732ff7160df7061149cb8772e87e8fb2c89caa0912e2e83cf2996`.
   - Live GitHub verification digest:
     `sha256:4ce16441ae173eafcaad2b4a12f01220e8cbdb7ee81805bdf75f3002121b4f4f`.
   - Live GitHub/Sigstore artifact attestation:
     verified by `gh attestation verify --repo Byron2306/EdgeK-BEAST`.
   - GCP remote physical packet:
     `evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json`.
   - GCP remote physical envelope digest:
     `sha256:de095c739633f7c06a48207b9bdd58085335b0dccf0bdda81e3811cfdb0b2462`.
   - GCP remote governance packet:
     `evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json`.
   - GCP remote governance envelope digest:
     `sha256:e443ec62d6406f1ea2af14e630bd1d69f2285a2df20536ed97ca01213f02b019`.
   - Quorum replay:
     `scripts/run_dai_phase5_shared_quorum_replay.py`.
   - Quorum replay receipt:
     `evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json`.
   - Quorum replay digest:
     `sha256:40a463606d84606260aaaaedde538ff691dd37e7f6cf939c4673a56c809e5a16`.
   - Quorum report digest:
     `sha256:a031335809e7e98609691d56ea297829204eeb6500bfc48a135f3767d558be4d`.
   - Result:
     `4/4` autonomous packets verified against one shared proposal; quorum
     decision `approve`; class `heterogeneous_distributed_quorum`; roles
     present: semantic, adversarial, physical execution and governance; hardware
     rooted node count `2`; red gates: none.
   - Boundary:
     GCP remote packets were signed inside the reachable Confidential VM and
     admitted against frozen instance-description evidence, but the GCP harvest
     still records `raw_provider_attestation_token_present=false` and
     `publication_grade_hardware_attestation=false`. This is a real remote
     autonomous Commons quorum, not yet the final publication-grade Google
     attestation-token proof.
6a. ~~Push Google/Azure provider attestation closure for the cloud witness
    lanes.~~
   - Google re-verification:
     the preserved Google Confidential Space packet was reverified against the
     frozen Google JWKS/signature path instead of relying on a loose packet
     shape.
   - Google verification receipt:
     `evidence/dai-diode/phase5-shared-quorum/gcp/google-confidential-space-provider-signature-reverification.json`.
   - Google packet digest:
     `sha256:c3118d58a8aed6d3c63c1c62a917603b00fd1d28bdca97a5b2b6856c57ef33cb`.
   - Google verification digest:
     `sha256:966bf9fb70c48cd9b0cec71132ba6fc4ba90cc3e64e3a27da8ce3d85901c2edf`.
   - Google result:
     compact JWT signature verified with Google JWKS; expected image digest,
     image reference, project, zone, instance, evidence root, temporal validity
     and packet nonce binding all passed with no red gates.
   - Azure live Confidential VM:
     `dio-azure-tee-governance-01` in `southafricanorth`,
     `Standard_DC2as_v6`, `ConfidentialVM`, vTPM enabled, Secure Boot enabled,
     VM ID `466fcc1d-cabc-4042-963c-6faf3ea9c586`.
   - Azure raw MAA token:
     `evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token.jwt`.
   - Azure raw MAA token file digest:
     `sha256:d0875afbb34068e7881aa01ca8ed3fef7a5989b1ea73c9236d26246590d5b196`.
   - Azure VM description:
     `evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_tee_governance_01_vm_description.json`.
   - Azure VM description file digest:
     `sha256:ab5b7e188d4b14173270eb25f34c96a278e8767283e63a1dd56f28525f7e8e45`.
   - Azure BEAST harvest:
     `evidence/dai-diode/phase5-shared-quorum/azure-live-maa-001/dio_azure_tee_attestation_harvest.json`.
   - Azure harvest digest:
     `sha256:6b156024ccf83f7106b175b75e65f56b0e2bd4b119004d49125fff1bf96e2bcd`.
   - Azure admission report digest:
     `sha256:df5675269c407631b902d706759686b2662d45ac8888ff63ffe75843560b136a`.
   - Azure MAA verifier:
     `scripts/verify_dio_azure_maa_token.py`.
   - Azure live verifier receipt:
     `evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.json`.
   - Azure live verification digest:
     `sha256:13cd905ca91ef07b86752d8874d4e6d21e300214e111e883099a943899fd7316`.
   - Azure frozen JWKS:
     `evidence/dai-diode/phase5-shared-quorum/azure/azure-maa-jwks.json`.
   - Azure JWKS digest:
     `sha256:46b7ff1df1b903f9e9b1c1c43363199eea990025ea2852af44add3d14ed677a9`.
   - Azure offline verifier receipt:
     `evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.offline.json`.
   - Azure offline verification digest:
     `sha256:e164ff3d76bb6fa6f7eb53dd7f99e1e860f5d2cf0f630a1e5053a2722c168b94`.
   - Azure result:
     MAA compact JWT verified as RS256 against Azure Attestation JWKS/x5c leaf;
     issuer matched the token `jku` origin; token was temporally fresh; Azure VM
     attestation type, protocol v3, SEV-SNP isolation, Azure-compliant CVM
     status, Secure Boot, vTPM and VM ID binding all passed with no red gates.
   - Boundary:
     Azure now has provider-service MAA JWT verification and BEAST admission
     evidence. This is still not an independent AMD VCEK reconstruction of the
     raw SNP report, and production authority remains deliberately off.
7. ~~Package Phase 5 only after autonomous packet gauntlet, live packet harvest
   and coordinator replay all pass from a clean source overlay.~~
   - Package script:
     `scripts/package_dai_phase5_artifact.py`.
   - Frozen release identity:
     `DAI-Diode-Phase-5__Heterogeneous-Autonomous-Commons-Quorum__2026-08-04`.
   - Bundle directory:
     `artifacts/DAI-Diode-Phase-5__Heterogeneous-Autonomous-Commons-Quorum__2026-08-04`.
   - Sealed ZIP:
     `artifacts/DAI-Diode-Phase-5__Heterogeneous-Autonomous-Commons-Quorum__2026-08-04.zip`.
   - ZIP digest:
     `sha256:041c4fe10c6b360f318e0c2271a4d9a671c8a922a38973178c2f007b23bc876d`.
   - Phase-5 evidence manifest digest:
     `sha256:128326bc58eec92fcc51fbf314bbba42214aa59fc15c001b75d4489295e3a4ce`.
   - One-command verifier:
     `python3 verify_phase5_bundle.py`.
   - Verifier result:
     `verified=true`, `entry_count=85`, `provider_calls_used=0`,
     `production_authority_allowed=false`,
     `execution_authority_allowed=false`.
   - Shared quorum report digest:
     `sha256:a031335809e7e98609691d56ea297829204eeb6500bfc48a135f3767d558be4d`.
   - Self-contained contents:
     shared proposal, live HF shared-proposal receipt, live GitHub
     Actions/Sigstore verification, GCP physical/governance remote envelopes,
     Google Confidential Space provider-signature re-verification, Azure live
     Confidential VM MAA token/JWKS/x5c verification with offline JWKS replay,
     remote witness packet gauntlet, Phase-4 predecessor fossil, source overlay,
     focused tests, dependency manifests, SHA-256 manifest, claims/nonclaims,
     authority map and clean-environment reproduction guide.
   - Boundary:
     the fossil proves a bounded heterogeneous autonomous Commons quorum and
     provider-service attestation closure. It still does not grant production
     execution authority and does not claim independent AMD VCEK reconstruction
     of raw SNP reports.

## Cross-phase closure hardening: verifier and provenance blockers

Source:

- `/home/byron/.codex/attachments/4f364a67-d84c-4b1f-b98c-ec760b250d2d/pasted-text.txt`

Goal:

> Treat the Phase 3.1 / Phase 4 fossils as archaeological artifacts that must
> survive hostile verifier execution, tampered control files, nested file
> attacks, semantic digest substitution, route inflation and predecessor-chain
> mismatch without relying on Python `assert` or self-consistent labels.

1. ~~Remove `assert` from active signed bundle verifier templates and reject
   optimized Python execution.~~
   - Hardened packagers:
     `scripts/package_dai_phase3_1_artifact.py` and
     `scripts/package_dai_phase4_artifact.py`.
   - Law:
     generated verifiers raise explicit `VerificationError` / `RuntimeError`
     for integrity decisions and fail immediately under `python -O`.
   - Negative controls:
     Phase 4 generated verifier rejects optimized mode, README tamper,
     nested `source/nested/RELEASE_MANIFEST.json`, `SHA256SUMS.txt` tamper and
     manifest `entry_count` tamper.
   - Tests:
     `tests/test_dai_phase4_bundle_verifier_hardening.py`.
   - Result:
     `3 passed`.
2. ~~Fix closed-world file-set verification for active signed bundle templates.~~
   - Law:
     control files are excluded only by exact normalized root-relative path,
     not basename; nested control-file copies are rejected; duplicate paths,
     case-fold collisions, Unicode NFC collisions, symlinks, hard links and
     path traversal are rejected.
   - Hardened templates:
     Phase 3.1 and Phase 4 generated verifiers.
3. ~~Make `SHA256SUMS.txt` meaningful for active signed bundle templates.~~
   - Law:
     checksum lines are GNU-compatible `<hex>  <path>` records derived from
     `SHA256_MANIFEST.json`; verifier recomputes and rejects any checksum-file
     mutation.
4. ~~Make the overlay installer non-destructive for dependency files.~~
   - Law:
     dependency specifications install under
     `reproduction-dependencies/` instead of overwriting target
     `pyproject.toml`, `pytest.ini` or requirements files; source/test overlay
     refuses to overwrite differing files.
5. ~~Add independently derived semantic digests for Phase-3 expression bundles:
   recompute from query, selected facts, graph, relevance slice, route, policy
   and composition result rather than comparing mutually consistent markers.~~
   - Module:
     `app/kernel/dai/phase3_expression.py`.
   - Derivation function:
     `derive_phase3_expression_semantic_digest()`.
   - Law:
     semantic digest now derives from graph digest/id/compiler/version, query,
     recomputed relevance slice, recomputed residual route, selected facts,
     selected edges, policy facts, derived claim ids and composition result.
   - Fresh expression receipt:
     `evidence/dai-diode/phase3-composition-001/composition-graph/phase3_expression_receipt.json`.
   - Receipt digest:
     `sha256:ff73430b34ff8e6b2ca882e3ce8a2881cee6c98ed966349fef429e605736e1bc`.
   - Semantic digest:
     `sha256:2e157bb388163aaf151560e1454ff921b1eb20023cd7484d7f9cc841d15276ff`.
   - Hostile control:
     text, SVG and bundle rewritten to the same fake semantic digest are now
     rejected by both text and visual verifiers.
6. ~~Recompute and verify residual/expression route authority from signed
   relevance and derivation receipts; `route.speakable_fact_ids` must not be
   trusted as a bare authority object.~~
   - Compiler law:
     `compile_phase3_expression()` recomputes relevance and residual routing
     before selecting expressible facts.
   - Verifier law:
     text and visual entailment independently recompute the same derivation
     context and reject route objects that do not reproduce from graph and
     relevance.
   - Hostile control:
     injecting an excluded fact into `route.speakable_fact_ids` fails compiler
     and both expression verifiers.
   - Tests:
     `tests/test_dai_phase3_expression.py` (`7 passed`).
   - Phase-3 hostile gauntlet:
     `10/10` attacks still blocked; receipt digest
     `sha256:8e271be8c571b6e4015aec33118c790857602a1e463ac2ab62bbb8462411a72a`.
   - Active Phase-3 and Phase-3.1 correction packagers now pin the new
     expression receipt digest.
7. ~~Add explicit rule records for every computed claim, including rule id,
   input fact ids, policy ids, transformation version, output claim id,
   implementation/code digest and deterministic result.~~
   - Module:
     `app/kernel/dai/phase3_composition.py`.
   - Law:
     every `derived_claim_id` must have exactly one `Phase3DerivationRule`
     record whose output claim exists, whose input/policy facts exist, whose
     transformation version is named and whose implementation digest binds the
     code that created the rule.
   - Rules emitted:
     `rule:phase3:multi-domain-composition-ready:v1`,
     `rule:phase3:bounded-answer-available:v1` and
     `rule:phase3:execution-refused:v1`.
   - Rule digests:
     `sha256:e5e5f0eba0fe06a0da63c6108cb414a0d9ee730506e40c152ad4abf9433e92db`,
     `sha256:2db806adda6fd5d47f8e6aee330985f2e2507e27d8597c22dbc144c47a0b2423`,
     `sha256:03da11786fa5be5a85d24e9e45a4be7b1501f47ff5c48af092def54d149a7a95`.
   - Fresh graph receipt digest:
     `sha256:4f0b0d214e2b0cafbe439329006ce4458558df43a73f3270b8dae332ca6d7418`.
   - Fresh graph digest:
     `sha256:bb5e8ee63f7552a2d260b9cb07aa0ea572c7582d490c75d4c3ed6cd2410b60e8`.
   - Hostile control:
     a synthetic derived answer claim with no derivation rule is refused during
     graph construction and counted as a blocked reversed-causality attack.
   - Tests:
     `tests/test_dai_phase3_composition.py`,
     `tests/test_dai_phase3_expression.py`,
     `tests/test_dai_phase3_hostile_gauntlet.py` and
     `tests/test_dai_phase4_bundle_verifier_hardening.py` (`25 passed`).
   - Packaging smoke:
     Phase-3 and Phase-3.1 correction packagers both verify in temporary output
     directories with the refreshed hostile, expression and graph receipt pins.
8. ~~Repair predecessor provenance by opening predecessor ZIPs, verifying their
   internal manifests/signatures and binding the exact internal release digest
   to the consuming fossil receipt.~~
   - Hardened packagers:
     `scripts/package_dai_phase3_1_artifact.py` and
     `scripts/package_dai_phase4_artifact.py`.
   - Package-time law:
     predecessor ZIP paths are audited, extracted into a temporary directory,
     verified with the predecessor's own verifier, and then bound as
     `PREDECESSOR_PROVENANCE.json`.
   - Generated-verifier law:
     the consuming bundle verifier independently reopens the embedded
     predecessor ZIP under `prior-fossils/`, reruns the predecessor verifier,
     recomputes the predecessor `RELEASE_MANIFEST.json` digest and compares the
     exact reconstructed provenance record to the signed release binding.
   - Phase-3.1 predecessor:
     Phase-2.1 internal release digest
     `sha256:74691890eaa4f48b0c2c3a028f0b366e2142f447f55a328df0a98e7abfc20454`.
   - Phase-4 predecessor:
     Phase-3.1 internal release digest
     `sha256:8422aa39fc49d2dfe64d28892be3362da25ba51cb1ed158c34e66915c4c669ad`.
   - Tests:
     focused closure suite now reports `26 passed`, including predecessor
     provenance binding in `tests/test_dai_phase4_bundle_verifier_hardening.py`.
   - Packaging smoke:
     Phase-3.1 and Phase-4 correction packagers both self-verify in temporary
     output directories with predecessor provenance included in the closed file
     manifest.
9. ~~Replace fixture-layout-sensitive bundled test instructions with a
   clean-environment reproduction script that states Python/system dependency
   policy, expected commands, expected outputs and expected test counts.~~
   - Hardened packagers:
     `scripts/package_dai_phase3_1_artifact.py` and
     `scripts/package_dai_phase4_artifact.py`.
   - New bundled script:
     `reproduce_clean_environment.sh`.
   - Script behavior:
     verifies the fossil first, installs source/tests/dependencies through the
     non-destructive overlay path, copies only the bounded evidence trees,
     reruns the phase reproduction commands, runs focused tests and emits a
     small JSON reproduction receipt.
   - Dependency policy:
     the caller supplies a clean checkout and Python environment; dependency
     specs are bundled but the reproduction script performs no network install.
   - Expected test counts:
     Phase 3.1 reproduction expects `36 passed`; Phase 4 reproduction expects
     `24 passed`.
   - Packaging smoke:
     Phase-3.1 temp bundle self-verifies with `entry_count=83`; Phase-4 temp
     bundle self-verifies with `entry_count=46`.
   - Script syntax:
     generated Phase-3.1 and Phase-4 `reproduce_clean_environment.sh` files pass
     `bash -n`.

## Adversarial programme to add to the plan

Evidence attacks:

- fabricated SHA-256 references;
- valid receipt for different proposition;
- receipt replay from another run;
- expired evidence;
- wrong signer;
- altered receipt after signing.

Semantic attacks:

- Boolean string masquerading as Boolean;
- polarity contradiction;
- incompatible ontology states;
- wrong measurement unit;
- stale causal source;
- irrelevant branch ending on same subject;
- text, visual and code disagreement.

Learning attacks:

- memorized wording;
- near-transfer success but far-transfer collapse;
- confidence unaffected by missing evidence;
- concept copied from distractor;
- false abstraction from too few examples.

Harmonic attacks:

- mechanically regular malicious actor;
- low-variance replay;
- gradual drift;
- bursty but benign workload;
- adversarial mimicry;
- confidence laundering.

Commons attacks:

- forged node identity;
- correct ML-KEM exchange from wrong workload;
- stale attestation;
- split world-state hashes;
- replayed quorum vote;
- Sybil nodes with same witness class;
- one unavailable node;
- colluding nodes.

Execution attacks:

- changed target digest;
- changed source file after promotion;
- namespace drift;
- cgroup drift;
- token replay;
- rollback failure;
- unobserved side effect;
- provider call inside supposedly deterministic execution.

## Benchmark additions

Hard constitutional metrics should be perfect on the frozen test suite:

- forged evidence rejected;
- stale token rejected;
- wrong world state rejected;
- wrong workload rejected;
- unauthorized node excluded;
- valid veto enforced;
- provider-call boundary respected.

Learning metrics:

- concept acquisition accuracy;
- near-transfer accuracy;
- far-transfer accuracy;
- negative-example recognition;
- confidence calibration;
- unsupported inference rate.

Mesh metrics:

- activation route accuracy;
- node-failure recovery;
- split-brain detection;
- quorum latency;
- activation depth;
- inhibitory precision;
- route stability after restart.

Economic metrics:

- provider calls avoided;
- prompt work avoided;
- latency;
- energy;
- memory;
- network traffic;
- crystal reuse rate;
- cold inference rate.

Required comparisons:

1. LLM alone.
2. Retrieval + LLM.
3. Sophia alone.
4. BEAST with manually authored rules.
5. Fixed rule graph.
6. Neural mesh without proof governance.
7. Complete DAI Diode.

Ablations:

- without Seraph;
- without Harmonic;
- without world-state binding;
- without quorum;
- without Arda;
- without evidence resolution;
- without crystals;
- without Sophia transfer.

## Scientific claims ladder

Already supportable:

> BEAST contains bounded mechanisms for typed semantic validation, refusal,
> proof-carrying physical recurrence, deterministic capability reuse and
> three-node ML-KEM Commons communication.

Supportable after integration:

> The DAI Diode integrates concept acquisition, adversarial transfer testing,
> semantic verification, distributed cryptographic witness, world-state binding
> and attested execution into one reproducible protocol.

Supportable after controlled benchmarks:

> Learned concepts can be promoted into bounded deterministic capabilities while
> reducing unsupported outputs and preventing unauthorized execution.

Supportable after independent replication:

> The architecture’s core effects reproduce outside the original development
> environment.

Not supportable without much stronger evidence:

- AGI achieved;
- general intelligence solved;
- all hallucination eliminated;
- formal correctness across arbitrary domains;
- universal neural replacement;
- unbreakable security.

This bounded ladder makes the work stronger, not smaller.
