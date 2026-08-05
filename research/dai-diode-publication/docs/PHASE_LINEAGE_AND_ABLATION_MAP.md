# Phase lineage and ablation map

This document is the review map for the DAI-Diode sequence. It does not replace the digest ledger; it tells reviewers what each phase contributes and what must fail when that contribution is removed.

## Lineage interpretation

| Phase | Primary contribution | Evidence expected in final capsule | Required ablation outcome |
|---|---|---|---|
| 1 | Initial bounded deterministic kernel/authority boundary | Original immutable archive; internal release manifest; kernel result receipt; code digest | Remove it and every descendant claim requiring the original bounded kernel must lose lineage validity or refuse |
| 2 | Exact operational truth / stale-listener and X2 witness behavior | Exact Phase 2 archive and receipts actually consumed by descendants | Substitute Phase 2.1 or another similarly named artifact and predecessor verification must reject |
| 2.1 | Authority-grade correction/extension of stale-listener evidence | Preserved as a distinct node with explicit `corrects`/`supersedes` relation if applicable | Removing it must affect only descendants that explicitly consume it; it must never silently replace Phase 2 |
| 3 | Multi-domain capability composition, graph, relevance, residual route, text/SVG expression | Original archive; graph and rule records; relevance/route/expression receipts | Remove composition and mixed-domain questions must refuse; single-domain evidence may remain available |
| 3.1 | Closed-world entailment and signed provenance | Original archive; signed manifests; exact file inventory; corrected predecessor binding | Remove signed provenance and semantic computation may remain possible, but publication admission must reject |
| 4 | Remote/hardware attestation bridge | Original archive; raw tokens, JWKS, provider identity, attestation verification receipts | Remove it and hardware/remote-attestation claims must become unavailable without affecting purely software semantics |
| 5 | Heterogeneous autonomous Commons quorum | Original archive; exact proposal; signed witness packets; raw attestations; deterministic quorum report | Remove a required role/provider/operator/key and quorum must reject or degrade exactly according to policy |
| 6.2 | Mixed-capability truth arena | Original archive; frozen solver; cases; oracle; result receipts; refusal artifacts | Remove either capability family and dependent mixed cases must refuse; unrelated cases must remain stable |
| Final | Publication closure | Exact lineage ledger; independent oracle; mutation/ablation/offline/reproduction reports; external anchors | Remove any required publication evidence and the corresponding public claim must be withheld |

## Mandatory lineage corrections

### Phase 2 versus Phase 2.1

The Phase 3.1 audit identified a concrete mismatch: the embedded Phase 2.1 ZIP was not the same release/digest referenced by the Phase 3 fossil receipt and source constants. The final ledger must preserve both objects and state exactly which object each descendant consumed.

Acceptable resolution:

1. keep the original Phase 2 node;
2. keep the Phase 2.1 node;
3. add `corrects` or `supersedes` only if historically accurate;
4. add `declared_predecessor` from each descendant to the artifact it actually used;
5. regenerate descendants only if the intended lineage changes;
6. never rewrite an old receipt to pretend it consumed a different predecessor.

### Phase 4 and Phase 5 raw attestation evidence

A verification receipt alone is weaker than preserving the raw token/JWT, JWKS or public-key material, provider identity evidence, evaluation time, policy, and verifier digest. The final publication should contain both raw evidence and the normalized witness packet.

### Phase 5 operator independence

Different providers are not sufficient if one person/account controls every lane. The final quorum claim requires independent human/control domains. Preserve a separate operator-control attestation for each lane.

### Phase 6.2 oracle independence

The existing bounded arena is evidence of engineering validity, but the final arena must be authored after solver freeze by an independent case author. Preserve the signed oracle before execution.

## Cross-phase invariants

Every descendant must preserve:

- `production_authority_allowed = false`;
- `execution_authority_allowed = false`;
- exact predecessor digest binding;
- exact implementation identity;
- explicit policy and governance epoch;
- no route widening;
- semantic digest recomputation;
- refusal on missing/stale/conflicting support;
- deterministic normalized output;
- no hidden post-ledger provider call for the offline claim.

## Hostile mutation obligations by phase

### Phase 1/2 operational kernel

- stale listener becomes fresh without evidence;
- exact-X2 cardinality altered to X1/X3;
- process/port/inode values substituted;
- lease expired or issued in the future;
- authority flag flipped;
- witness code digest changed.

### Phase 3/3.1 composition and expression

- summary-only provenance substitution;
- missing graph parent;
- manually widened route;
- relevance slice from another query;
- semantic digest and both expression markers changed consistently;
- unauthorized text line;
- unauthorized SVG text, edge, node, geometry, style, hidden metadata, or accessibility label;
- nested reserved filename;
- added unlisted file;
- verifier run under `python -O`;
- duplicate JSON key;
- path normalization collision.

### Phase 4 attestation

- JWT/JWKS `kid` mismatch;
- issuer/audience mismatch;
- expired or future token;
- nonce mismatch;
- VM/workload identity mismatch;
- attestation claim stripped while receipt remains;
- provider receipt replayed against a different proposal;
- raw evidence absent.

### Phase 5 quorum

- one key used under two operators;
- one operator under two provider labels;
- proposal digest mismatch;
- evidence root mismatch;
- world-state mismatch;
- capability digest mismatch;
- governance epoch mismatch;
- challenge nonce mismatch;
- stale vote;
- equivocation by one signer;
- duplicate vote counted twice;
- required role absent;
- hardware-rooted count inflated by a software-only lane;
- quorum result edited without recomputation.

### Phase 6.2 arena

- held-out label changed after solver output;
- case appears in training/promotion evidence;
- required capability removed;
- contradictory evidence added;
- irrelevant capability removed;
- fact order changed;
- case ID/digest mismatch;
- expected answer/refusal denominator misreported;
- post-ledger network access enabled;
- absolute path included in implementation digest;
- same-author oracle substituted for independent oracle.

## Ablation interpretation

Ablation is not merely “accuracy got worse.” It tests the architecture’s causal claims.

A good result is selective:

- removing a required capability breaks only dependent cases;
- removing provenance blocks admission, not necessarily raw computation;
- removing attestation blocks attestation claims, not semantic answers;
- removing quorum blocks collective approval, not local verification;
- removing policy causes refusal, never authority escalation;
- removing an irrelevant component does not alter unrelated outputs.

If every ablation breaks everything, the system is monolithic rather than compositional. If no ablation changes anything, the claimed dependencies are decorative.

## Final pass statement

The lineage is publication-closed only when:

1. every phase node is an exact digest of an original archive;
2. every predecessor edge is supported by internal evidence;
3. all ambiguity is represented rather than erased;
4. the final solver consumes only admitted nodes;
5. ablation demonstrates the predicted role of each phase;
6. mutation demonstrates that substitutions are rejected;
7. independent operators reproduce the final result;
8. the public claim does not exceed the highest green rung.
