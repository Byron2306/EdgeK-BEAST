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
9. Run a fresh privileged Phase-2.1 exact X2 proof with the hardened verifier.
   - Required user-run command:
     `sudo .venv/bin/python scripts/run_dai_phase2_x2_exact_ring_buffer.py --out evidence/dai-diode/phase2.1-stale-listener-001/x2-exact-ring --run-id dai-phase2-1-x2-exact-ring-local-001`
   - This must mint a new summary digest; the old Phase-2 ZIP must not be
     silently replaced.
10. Package Phase-2.1 as a new fossil only after the fresh privileged proof
    passes.
11. Deploy the HF witness as an actual remote Docker Space with a pinned public
    Ed25519 key and verifier build.
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
15. Create or target a live Google Confidential VM witness, then rerun the GCP
    harvester with `--instance <name> --zone <zone>`.
16. Add Azure harvester that produces normalized `DIOCloudTeeEvidence` from a
    live Azure guest-attestation / MAA flow.
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
18. Push and dispatch the GitHub workflow, then verify the downloaded packet
    with `gh attestation verify`.
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
5. Add relevance pruning so unrelated causal branches cannot leak into a
   requested explanation.
6. Add residual routing law: unsupported/residual-required propositions are not
   speakable facts until a verified residual result is promoted.
7. Add deterministic text and visual composition outputs generated from the same
   canonical composition graph, with independent entailment checks.
8. Run a multi-domain hostile gauntlet covering copied receipts, reversed
   causality, stale evidence, irrelevant graph branches, false Boolean
   polarity, authority inflation and fossil mutation.
9. Package Phase-3 as:
   `DAI-Diode-Phase-3__Multi-Domain-Capability-Composition__2026-08-04`.

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
