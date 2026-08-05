# DAI-Diode: Bounded Deterministic Intelligence Through Signed Provenance, Closed-World Entailment, and Heterogeneous Attested Quorum

**Author:** Byron Bunt  
**Affiliation:** [institutional affiliation, if used]  
**Version:** publication candidate  
**Artifact DOI:** [assign after deposit]  
**Source tag:** [signed tag]  
**Core capsule SHA-256:** [exact digest]  
**Publication envelope SHA-256:** [exact digest]

## Abstract

Contemporary artificial-intelligence systems often conflate useful inference with stochastic generation, incomplete provenance, and implicit authority. This paper presents DAI-Diode, an evidence architecture for **bounded deterministic intelligence**: the reproducible derivation of semantically meaningful answers, refusals, or decisions from a declared evidence world by inspectable deterministic rules, with explicit authority limits, complete provenance, and replayable verification, without hidden stochastic dependence in the decision core.

DAI-Diode combines closed-world entailment, signed provenance, multi-domain capability composition, one-semantic-object text and visual expression, remote attestation, and heterogeneous quorum over an exact digest-bound proposition. The publication evaluates the architecture through deterministic replay, independently authored held-out cases, principled refusal tests, hostile mutation, causal ablation, offline network observation, clean-room reproduction, and independently controlled Commons witnesses. Results are reported separately for answer, refusal, unresolved, provenance, expression, authority, and quorum outcomes. The system does not claim artificial general intelligence, open-world truth, arbitrary language competence, consciousness, or production authority.

When all technical gates pass, the supported conclusion is that DAI-Diode validates bounded deterministic intelligence as an engineering architecture within the declared domain. A narrower priority statement is evaluated separately through a source-backed prior-art matrix and independent review.

## 1. Introduction

The question addressed by DAI-Diode is not whether all intelligence can be reduced to deterministic rules. It is whether a bounded system can accumulate reusable capabilities, compose them across domains, derive new supported propositions, refuse unsupported ones, express the result in multiple forms, and obtain replayable distributed assent while preserving exact provenance and authority boundaries.

The engineering hypothesis is:

> Given a declared evidence world, deterministic rule set, explicit policy, and bounded expression grammar, a system can produce semantically meaningful new answers and principled refusals whose complete derivation and collective verification are independently replayable.

This hypothesis is falsifiable. It fails if undeclared bytes affect the result, the same admitted state produces a different normalized semantic result, an output proposition lacks a derivation path, missing evidence produces invention rather than abstention, expression widens the authorized claim set, quorum votes concern different propositions, post-ledger model calls occur, or independent operators cannot reproduce the result.

## 2. Contributions

This work contributes:

1. an operational definition and conjunctive validity criteria for bounded deterministic intelligence;
2. a content-addressed lineage from the initial bounded kernel through composition, signed provenance, attestation, quorum, and mixed-capability evaluation;
3. deterministic graph, relevance, route, semantic-digest, and expression compilation;
4. refusal semantics for absent, stale, contradictory, or unauthorized evidence;
5. exact text and SVG expression from one verified semantic object;
6. digest-bound heterogeneous witness packets and replayable quorum evaluation;
7. a two-stage core-capsule/publication-envelope design that avoids self-referential release digests;
8. hostile mutation and causal ablation suites with specific expected rejection reasons;
9. independent oracle, no-egress witness, reproduction, and operator-control requirements;
10. a claims ladder that separates byte integrity, technical validity, independent reproduction, quorum, and historical priority.

## 3. Definition

### 3.1 Bounded deterministic intelligence

A system instance satisfies bounded deterministic intelligence only when all declared validity criteria BDI-01 through BDI-15 pass. These criteria cover input closure, rule closure, replay determinism, provenance completeness, authority closure, abstention safety, expression closure, lineage closure, external verifiability, mutation resistance, ablation validity, no hidden inference, quorum exactness, operator independence, and falsifiability.

### 3.2 Decision-core boundary

The deterministic decision core begins after evidence and capability admission. Stochastic or human-assisted processes may be used before promotion, provided their outputs are frozen, signed, governed, and not invoked during the claimed deterministic replay. The publication therefore distinguishes:

- **pre-ledger acquisition or promotion**;
- **post-ledger deterministic composition and expression**;
- **external verification and quorum**;
- **separate production authority**.

### 3.3 Authority ceiling

Every artifact, receipt, witness packet, report, and release preserves:

```text
production_authority_allowed = false
execution_authority_allowed = false
```

Evidence validity never silently grants execution authority. Any production grant belongs to a separate authority system and is outside the present claim.

## 4. System architecture

### 4.1 Evidence world

The evidence world is an exact, signed, content-addressed inventory. Admission rejects unlisted files, missing files, digest or size mismatch, unsafe paths, duplicate keys, stale evidence, invalid issuer signatures, and lineage ambiguity.

### 4.2 Capability ledger

A capability is a reusable bounded transformation with declared inputs, outputs, policy, implementation identity, provenance, and authority ceiling. Capabilities may be composed only when their contracts and evidence dependencies are satisfied.

### 4.3 Rule and derivation graph

Every derived proposition is represented by a rule record containing:

- rule identifier;
- input fact identifiers;
- policy identifiers;
- transformation and implementation identity;
- output proposition identifier;
- deterministic evaluation result.

The graph is a derivation proof, not a decorative relationship map.

### 4.4 Relevance and residual route

Relevance is recomputed from the verified graph and query. The residual route is recomputed from relevance, policy, and conflict state. A route object is never trusted as independent authority. Speakability is the intersection of admitted facts, verified relevance, derivation support, and policy.

### 4.5 Semantic object and expression

The semantic digest is recomputed from the query, graph, selected facts, route, policy, implementation identity, and composition result. Text and SVG are compiled from this verified semantic object. Verification compares exact canonical text and a canonical SVG abstract syntax tree, including propositions, labels, edges, geometry, states, and metadata permitted by policy.

### 4.6 Remote attestation

Remote evidence preserves the raw provider token or attestation object, public verification material, identity claims, evaluation time, policy, and verifier digest. A normalized verification receipt without raw evidence is insufficient for the strongest claim.

### 4.7 Commons quorum

Each witness packet binds to the same:

- proposal digest;
- capability digest;
- evidence root;
- world-state hash;
- governance epoch;
- challenge nonce;
- verifier digest;
- validity window;
- authority ceiling.

The evaluator rejects duplicate keys, duplicate votes, operator/control-domain collapse, provider collapse, stale votes, equivocation, missing roles, and any binding mismatch.

### 4.8 Publication architecture

The technical subject is first frozen as `CORE_CAPSULE.zip`. Independent reports bind to its exact digest. A later publication envelope contains the unchanged core and those reports. The envelope has a separate externally anchored digest and signing identity. This avoids an impossible report that claims the digest of a ZIP containing itself.

## 5. Lineage

The final lineage ledger preserves each original artifact unchanged and records exact digest edges. It distinguishes historical Phase 2 and Phase 2.1 objects rather than silently substituting one for the other. Any prior mismatch remains visible as a corrected or superseded branch.

The canonical lineage and contribution map is:

| Phase | Contribution | Exact artifact digest | Predecessor evidence |
|---|---|---|---|
| 1 | initial bounded kernel and authority boundary | [digest] | [evidence] |
| 2 | operational truth / stale-listener exact-X2 witness | [digest] | [evidence] |
| 2.1 | authority-grade correction or extension | [digest] | [relation] |
| 3 | multi-domain capability composition and expression | [digest] | [evidence] |
| 3.1 | closed-world entailment and signed provenance | [digest] | [evidence] |
| 4 | remote/hardware attestation bridge | [digest] | [evidence] |
| 5 | heterogeneous autonomous Commons quorum | [digest] | [evidence] |
| 6.2 | mixed-capability truth arena | [digest] | [evidence] |
| Final | publication closure | [digest] | [evidence] |

## 6. Threat model

The evaluation considers accidental corruption, malicious repackaging, unlisted-file injection, path and normalization attacks, optimized-runtime fail-open behavior, manifest and checksum theatre, predecessor substitution, route widening, semantic-digest substitution, expression injection, stale evidence, replay, quorum equivocation, pseudo-independence, hidden provider calls, benchmark leakage, and overclaiming.

Out of scope are compromise of offline signing keys, compromise of the host kernel or hardware root at witness creation, cryptanalytic breaks in SHA-256 or Ed25519, unrestricted image or prose interpretation, production incident response, and legal or regulatory certification.

## 7. Experimental method

### 7.1 Solver freeze

The solver, route compiler, semantic evaluator, expression compiler, and scoring logic are frozen at signed commit and tag before independent cases or oracle outputs are revealed.

### 7.2 Independent truth arena

An independent case author creates and signs the cases and oracle after solver freeze. The set includes ordinary answers, refusals, contradictions, stale evidence, missing capabilities, cross-capability composition, and authority-boundary cases. No failed case is removed after execution; corrections are append-only.

### 7.3 Deterministic replay

The same admitted state is executed repeatedly across supported Python versions and independent environments. Both byte-level receipts and normalized semantic digests are reported. Volatile process identifiers, ports, paths, and timestamps are excluded from semantic equivalence.

### 7.4 Mutation

Generic archive mutations test exact file closure, signatures, path handling, optimized Python, and outer-ZIP metadata. Semantic attacks test lineage, provenance, freshness, relevance, route, semantic digest, expression, proposal binding, quorum independence, and offline closure. Each attack has a specific expected rejection reason; a crash is not counted as success.

### 7.5 Ablation

Leave-one-component-out variants test causal architecture claims. Removing provenance should block admission, not necessarily raw computation. Removing attestation should block attestation claims, not unrelated semantic answers. Removing one capability family should affect only dependent cases. Removing a required quorum role should affect quorum, not local replay.

### 7.6 Offline observation

The post-ledger arena runs with deny-by-default egress and DNS denial. An independent observer preserves network policy, socket or eBPF trace, packet summary, DNS attempts, process tree, image digest, solver digest, and signed report.

### 7.7 Independent reproduction

At least two operators use separate people, machines, accounts, control domains, and signing keys. They receive only the public core capsule, external digest and fingerprint anchors, and public instructions. Their signed reports must agree on the normalized semantic result digest.

### 7.8 Independent quorum

At least three independently controlled operators on at least three infrastructure/control domains evaluate one exact proposal. Raw attestation evidence is preserved for every lane. The quorum is replayed from frozen packets without recontacting providers.

## 8. Results

All values in this section must be generated from signed machine-readable reports. Do not transcribe them manually.

### 8.1 Artifact integrity

| Metric | Result | Evidence object |
|---|---:|---|
| Signed core entries | [machine value] | [path/digest] |
| Unlisted-file rejection | [pass/fail] | [mutation case] |
| Optimized-Python refusal | [pass/fail] | [mutation case] |
| External core fingerprint anchor | [pass/fail] | [anchor] |
| External envelope digest anchor | [pass/fail] | [anchor] |

### 8.2 Arena

| Category | Correct | Total | Rate |
|---|---:|---:|---:|
| Supported answer | [value] | [value] | [value] |
| Refusal | [value] | [value] | [value] |
| Unresolved/contradiction | [value] | [value] | [value] |
| Cross-capability composition | [value] | [value] | [value] |
| Authority boundary | [value] | [value] | [value] |
| Text expression closure | [value] | [value] | [value] |
| SVG expression closure | [value] | [value] | [value] |

### 8.3 Mutation and ablation

| Suite | Passed | Total | Red cases |
|---|---:|---:|---|
| Archive/release mutation | [value] | [value] | [list] |
| Semantic mutation | [value] | [value] | [list] |
| Causal ablation | [value] | [value] | [list] |

### 8.4 Offline execution

| Observation | Result |
|---|---|
| Default egress | deny |
| DNS | denied |
| Observed outbound connections | [value] |
| Observed post-ledger provider calls | [value] |
| Observer signature | [verified/unverified] |

### 8.5 Reproduction

| Operator | Control domain | Environment digest | Semantic result digest | Result |
|---|---|---|---|---|
| [operator 1] | [domain] | [digest] | [digest] | [pass/fail] |
| [operator 2] | [domain] | [digest] | [digest] | [pass/fail] |

### 8.6 Commons quorum

| Metric | Result |
|---|---:|
| Approvals | [value] |
| Distinct operators | [value] |
| Distinct control domains | [value] |
| Distinct signing keys | [value] |
| Distinct providers | [value] |
| Required roles present | [yes/no] |
| Raw attestation objects | [value] |
| Exact proposal binding | [pass/fail] |
| Replay result | [decision] |

## 9. Prior art and novelty

DAI-Diode must be compared against expert systems, logic programming, answer-set programming, theorem proving, truth-maintenance systems, proof-carrying code and data, database provenance, content-addressed and reproducible computation, authorization logic, policy-as-code, software-supply-chain provenance, remote attestation, Byzantine and federated quorum, verifiable computation, neuro-symbolic systems, knowledge-graph provenance, DAO governance, and shared-semantic multimodal rendering.

No individual ingredient is claimed as new. The narrow priority question is whether a previously documented system combines all of the following in one replayable evidence architecture:

1. closed-world deterministic entailment;
2. signed provenance;
3. explicit authority-bounded expression;
4. multi-domain capability composition;
5. shared text and visual semantics;
6. raw remote-attestation evidence;
7. heterogeneous independently controlled quorum;
8. deterministic replay and refusal;
9. public mutation, ablation, and reproduction evidence.

The permitted priority wording, only after source completion and independent review, is:

> To our knowledge, DAI-Diode is the first publicly documented system to combine closed-world deterministic entailment, signed provenance, authority-bounded expression, multi-domain capability composition, and heterogeneous attested quorum in a replayable evidence architecture.

## 10. Limitations

The evidence world is bounded and curated. The system does not solve arbitrary open-world interpretation. Ontology construction and capability promotion may involve human or stochastic processes before freeze. Independent operators can establish separate control domains but cannot make compromise impossible. Remote attestation inherits provider, hardware, firmware, and verifier assumptions. Synthetic or authored cases cannot substitute for all real-world deployment evidence. The world-first conclusion is contingent on the documented search scope and may be revised if prior art is found.

## 11. Reproducibility and availability

The publication provides:

- signed source tag;
- immutable core capsule;
- signed publication envelope;
- external digest and key anchors;
- full lineage ledger;
- schemas and verifier;
- exact dependency environment;
- independent arena and oracle;
- mutation and ablation plans and reports;
- raw attestation evidence;
- independent reproduction reports;
- prior-art matrix;
- DOI-backed archival deposit.

The core and envelope are verified separately to avoid self-reference.

## 12. Conclusion

If all technical gates pass, the evidence supports the following bounded conclusion:

> DAI-Diode validates bounded deterministic intelligence as an engineering architecture: deterministic, provenance-bound, multi-capability composition that produces new bounded answers and principled refusals without stochastic inference in the decision core.

This result does not establish AGI or universal truth. It establishes a narrower and testable proposition: intelligence-like composition, judgment, abstention, expression, and distributed verification can be engineered deterministically within a declared evidence and authority boundary.

## Appendix A. Claims and nonclaims

[Auto-generate from `CLAIMS_REGISTRY.json`.]

## Appendix B. Validity criteria

[Auto-generate from `BDI_VALIDITY_CRITERIA.json`.]

## Appendix C. Mutation and ablation matrix

[Auto-generate from signed reports.]

## Appendix D. Artifact manifest

[Auto-generate exact release IDs, digests, signer fingerprints, and external anchors.]
