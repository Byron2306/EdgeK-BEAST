# Bounded Deterministic Intelligence: validity, claims, and threat model

## 1. Operational definition

**Bounded deterministic intelligence (BDI)** is a system property, not a metaphysical claim.

A system instance satisfies BDI only when it produces a semantically meaningful answer, refusal, classification, plan, or decision from a declared evidence world through inspectable deterministic rules, while preserving complete provenance and explicit authority limits, and when the same admitted inputs and implementation produce the same normalized semantic result without hidden stochastic dependence in the decision core.

The word **bounded** is essential. The system is valid only for the declared domain, vocabulary, evidence model, rules, and authority policy.

## 2. Minimum validity criteria

All criteria are conjunctive. A single red criterion blocks the public validity claim.

| ID | Criterion | Required evidence | Falsifier |
|---|---|---|---|
| BDI-01 | Input closure | Signed exact inventory of every decision input | An undeclared byte can alter the decision |
| BDI-02 | Rule closure | Versioned deterministic rules or code digest | Hidden prompt/model call changes the result |
| BDI-03 | Replay determinism | Repeated normalized semantic result across runs | Same admitted state yields a different semantic result |
| BDI-04 | Provenance completeness | Every output proposition has evidence and rule parents | A proposition has no derivation path |
| BDI-05 | Authority closure | Explicit authority ceiling at every layer | Evidence or quorum silently grants execution power |
| BDI-06 | Abstention safety | Missing/conflicting evidence produces refusal or unresolved state | System invents a supported-looking answer |
| BDI-07 | Expression closure | Text and visual outputs derive from one verified semantic object | Output communicates an unbound proposition |
| BDI-08 | Lineage closure | Exact digest chain to all predecessor artifacts | A fossil is mismatched, dangling, or substituted |
| BDI-09 | External verifiability | Independent verifier reproduces the checks | Only the author’s runtime can verify |
| BDI-10 | Mutation resistance | Declared hostile mutations are rejected | A mutation preserves a green verification result |
| BDI-11 | Ablation validity | Removing required support causes predicted degradation/refusal | Output survives removal of supposedly necessary evidence |
| BDI-12 | No hidden inference | Offline/network witness proves no post-ledger provider calls | Egress or a hidden model call occurs |
| BDI-13 | Quorum exactness | Votes bind to one proposal, nonce, epoch, state, evidence root, and capability digest | Votes concern materially different propositions |
| BDI-14 | Operator independence | Required quorum/reproduction operators control distinct accounts, keys, and infrastructure | One operator controls the alleged independent witnesses |
| BDI-15 | Falsifiability | Negative tests and rejection conditions are public | No observation could disprove the claim |

## 3. Claim ladder

Claims must be published only at the highest fully supported rung.

### Rung 0 — artifact integrity

> The published bytes match a signed manifest.

This does not establish identity, time, semantic correctness, or real-world truth.

### Rung 1 — deterministic replay

> The frozen implementation and admitted inputs reproduce the same normalized semantic result.

This does not establish that the inputs are true.

### Rung 2 — bounded deterministic intelligence

> Within the declared world, the system composes admitted capabilities, derives supported answers or refusals, and preserves complete provenance without stochastic dependence in the decision core.

This is the principal DAI-Diode validity claim.

### Rung 3 — independently reproduced BDI

> External operators independently reproduce Rung 2 from the public release.

### Rung 4 — heterogeneous attested Commons

> Independently controlled, heterogeneous witnesses evaluate one exact digest-bound proposition and produce a replayable quorum without granting execution authority.

### Rung 5 — priority claim

> To our knowledge, this is the first publicly documented implementation combining the specifically enumerated properties.

Rung 5 requires prior-art evidence. No artifact can prove a universal historical negative by itself.

## 4. Permitted final wording

When BDI-01 through BDI-15 are green:

> **DAI-Diode validates bounded deterministic intelligence as an engineering architecture: deterministic, provenance-bound, multi-capability composition that produces new bounded answers and principled refusals without stochastic inference in the decision core.**

When independent reproduction, independent quorum, and the prior-art matrix are also green:

> **To our knowledge, DAI-Diode is the first publicly documented system to combine closed-world deterministic entailment, signed provenance, authority-bounded expression, multi-domain capability composition, and heterogeneous attested quorum in a replayable evidence architecture.**

## 5. Nonclaims

DAI-Diode does not establish:

- artificial general intelligence;
- universal or open-world truth;
- arbitrary-language competence;
- consciousness, sentience, or personhood;
- that neural models are obsolete;
- that every domain can be compiled into the present ontology;
- production safety outside the tested boundary;
- execution or production authority;
- independent publisher identity merely because a public key is bundled;
- trusted time merely because a timestamp field exists;
- independent witness control merely because providers differ;
- visual entailment beyond the declared closed template/AST;
- world-first priority without a documented prior-art review.

## 6. Threat model

### Adversaries considered

1. Accidental corruption or incomplete upload.
2. Malicious repackaging with changed files.
3. Unlisted-file injection.
4. Path traversal, symlink, special-file, duplicate-path, case-fold, and Unicode collisions.
5. Optimized-runtime removal of assertion checks.
6. Manifest field tampering and checksum theatre.
7. Predecessor substitution or lineage ambiguity.
8. Route widening and semantic-digest substitution.
9. Expression-layer claim injection through text or visual channels.
10. Stale evidence, expired leases, nonce replay, and governance-epoch mismatch.
11. Quorum equivocation across different proposals.
12. Same-operator pseudo-independence.
13. Hidden provider/model calls after capability promotion.
14. Benchmark leakage or same-author oracle bias.
15. Overclaiming from synthetic or bounded results.

### Out of scope for this research release

- compromise of the publisher’s offline private key;
- compromise of the host kernel or hardware root during witness creation;
- cryptanalytic breaks in SHA-256 or Ed25519;
- arbitrary semantic interpretation of unrestricted images or prose;
- production incident response;
- legal certification or regulatory approval.

These exclusions must remain visible in the final paper.

## 7. Authority map

| Object/layer | May assert | May not assert |
|---|---|---|
| Prior capsule | Its own signed bytes and bounded result | Validity of descendants |
| Domain receipt | Observed bounded facts under its issuer policy | General real-world truth |
| Capability ledger | Admitted reusable transformations | Production authority |
| Graph compiler | Deterministic derivation relationships | Facts absent from admitted evidence |
| Relevance compiler | Query-scoped support set | New facts |
| Residual route | Answer/refuse boundary | Speakability beyond verified relevance |
| Expression compiler | Exact authorized semantic projection | Independent semantic authority |
| Text/SVG verifier | Exact expected AST/template closure | Arbitrary visual or linguistic truth |
| Commons witness | Verification result for one exact proposal | Truth of a different proposal |
| Quorum evaluator | Policy result over admitted signed votes | Execution permission |
| Arda authority layer | Separate production grant when policy allows | Implicit grant from evidence alone |
| Publication signer | Publisher’s endorsement of release bytes | Independent replication or priority |

## 8. Required ablations

At minimum:

- remove each capability family one at a time;
- remove each evidence parent one at a time;
- remove provenance binding while preserving summary fields;
- remove policy/authority input;
- remove one quorum role, provider, key, and operator;
- remove hardware-attested lane;
- remove the contradiction/refusal evidence;
- alter the semantic route while keeping the graph digest;
- alter the semantic digest and both expression markers consistently;
- alter the independent oracle after solver freeze.

A valid system should fail, refuse, or degrade exactly where the architecture says it depends on the removed element.

## 9. Required mutations

The publication suite must reject:

- tracked-byte changes;
- added, removed, or renamed files;
- nested control-file basenames;
- malformed, duplicate-key, or schema-invalid JSON;
- signature and key-fingerprint changes;
- path traversal and symlinks;
- case-fold and Unicode path collisions;
- predecessor mismatch;
- stale/expired evidence;
- nonce, epoch, proposal, evidence-root, world-state, or capability-digest mismatch;
- route widening;
- semantic digest substitution;
- text/SVG claim injection;
- optimized Python verification;
- hidden network access during the offline run.

## 10. Publication stop rule

If any final gate is red, publish the artifact as a **research candidate** and state the red gate explicitly. Do not solve a failed test by weakening the claim, changing the oracle after seeing the result, excluding the mutation, or silently regenerating evidence.
