# DAI-Diode final publication protocol

## Purpose

This protocol converts the existing DAI-Diode research lineage into a defensible public release. It separates five proofs that reviewers will otherwise conflate:

1. **byte integrity** — the release has not changed;
2. **publisher identity** — the release is anchored to an external identity/key;
3. **semantic validity** — the deterministic core produces the claimed bounded result;
4. **independent reproducibility** — other operators can reproduce it;
5. **historical novelty** — the exact combination is not found in documented prior art.

No single signature, benchmark, quorum, or paper proves all five.

## A. Freeze the solver before the final arena

1. Commit all deterministic-core source to a clean branch.
2. Record the Git tree digest and implementation file digests.
3. Create a signed tag named for the solver freeze.
4. Prohibit changes to the solver, oracle interpreter, route compiler, and result evaluator after the independent cases are revealed.
5. If a defect requires a code change, increment the release candidate and regenerate the independent test set.

## B. Normalize the full Phase 1–6.2 lineage

Copy every original archive unchanged into `candidate/artifacts/`.

Run:

```bash
python dai_publication.py discover-lineage candidate/artifacts \
  --output candidate/lineage/LINEAGE_LEDGER.discovered.json
```

Then manually construct `LINEAGE_LEDGER.json`:

- one node for each exact artifact digest;
- one unambiguous phase label per canonical release;
- exact `declared_predecessor` edges from newer artifact to older artifact;
- exact containment and reference evidence;
- all prior mismatches preserved as superseded/error nodes, never silently deleted;
- `required_phase_sequence` set to the actual public sequence;
- `review_required` set to `false` only after two-person review;
- `conflicts` and `dangling_lineage_references` empty.

The ledger must explicitly resolve the historical Phase 2 versus Phase 2.1 mismatch found during the Phase 3.1 audit. The final release may preserve both artifacts, but only one can be the exact predecessor of a given descendant.

## C. Rebuild the semantic proof from admitted evidence

The final deterministic runner must:

1. verify the full lineage before loading semantic evidence;
2. verify issuer signatures and freshness for every domain receipt;
3. compile the graph from admitted evidence only;
4. represent every derived claim as a rule record with complete parent IDs;
5. recompute relevance from the graph and query;
6. recompute the residual route from graph, relevance, and policy;
7. recompute the semantic digest from the query, graph, verified route, selected facts, policy, and implementation identity;
8. compile text and SVG from the verified semantic object;
9. compare exact expected text and exact canonical SVG AST;
10. emit refusal when support is missing, stale, contradictory, or unauthorized.

A bare route dataclass, receipt summary, semantic digest field, or expression marker is never authority.

## D. Independent arena

The final arena must be created after solver freeze by at least one person who did not author the solver.

Deliverables:

```text
arena/
  ARENA_CASES.json
  INDEPENDENT_ORACLE.json
  CASE_AUTHOR_ATTESTATION.json
  SOLVER_FREEZE.json
  ABLATION_PLAN.json
  BASELINE_INPUT.json
  RESULTS.json
```

Rules:

- case authors receive the public capability/evidence schema, not solver internals;
- cases include ordinary answer, refusal, contradiction, stale evidence, missing capability, and authority-boundary classes;
- the oracle is signed before the solver is run;
- no failing case is removed after results are known;
- corrections are append-only and publicly explained;
- metrics distinguish applicable answer cases from refusal cases;
- all denominators are explicit.

Minimum target:

- at least 100 independently authored cases;
- at least 25 refusal/contradiction cases;
- at least 20 cross-capability composition cases;
- at least 10 authority-boundary cases;
- 100% provenance and authority safety;
- semantic accuracy reported with confidence intervals, not only a single percentage.

## E. Ablation matrix

Run the exact solver against leave-one-component-out variants:

| Ablation | Expected effect |
|---|---|
| Remove Phase 1/2 kernel evidence | Descendant claims requiring it refuse or lose lineage validity |
| Remove Phase 3 composition rule | Mixed-domain answers become unavailable |
| Remove Phase 3.1 signed provenance | Semantic result may compute but cannot be admitted as provenance-closed |
| Remove Phase 4 attestation lane | Hardware/remote-attestation claim becomes unavailable |
| Remove one Phase 5 witness | Quorum degrades according to policy |
| Collapse distinct operators to one | Independence gate fails |
| Remove one Phase 6.2 capability family | Cases requiring that family refuse |
| Remove policy fact | No authority-bearing expression is allowed |
| Widen route without relevance support | Verification rejects |
| Substitute semantic digest and markers together | Verification rejects |
| Remove contradiction evidence | Contradiction-case behavior changes predictably and is recorded |
| Remove provenance while keeping summary | Admission rejects summary-only substitution |

Ablation reports must preserve the exact input/output digests and adapter implementation digest.

## F. Defensive mutation matrix

The built-in harness covers generic archive/release mutations. The system-specific Seraph/BEAST mutation corpus must additionally include:

- every known Phase 3.1 bypass;
- stale lease and future-issued evidence;
- wrong challenge nonce;
- wrong governance epoch;
- wrong world-state hash;
- wrong capability digest;
- wrong evidence root;
- proposal equivocation across witnesses;
- duplicate signer key under multiple operator labels;
- same cloud account under multiple provider labels;
- raw attestation/JWKS mismatch;
- unsupported text claim;
- unsupported SVG text, geometry, edge, color/state, or hidden metadata;
- reordered facts where order is not semantically relevant;
- semantically altered facts with unchanged presentation;
- dirty source tree and mismatched implementation digest;
- archive bomb and malformed JSON edge cases.

Every mutation must have an expected rejection code. “Raised some error” is weaker than proving the intended gate fired.

## G. Offline/no-provider proof

The final arena run must happen in a separately observed environment with outbound egress denied.

Preserve:

- container or VM image digest;
- network namespace/firewall policy digest;
- packet-capture or eBPF/Sensorium summary;
- DNS and socket-denial logs;
- process tree;
- open-file inventory;
- start/end monotonic and wall-clock readings;
- verifier and solver digests;
- signed witness report.

The defensible claim is:

> No outbound provider call was observed during the post-ledger deterministic arena under the declared network-denial policy.

Do not claim that no hidden call is possible in all environments.

## H. Independent reproduction

At least two reproduction operators must:

- use separate people, machines, accounts, and signing keys;
- start from the public tagged source and release ZIP only;
- follow the public guide without private help;
- preserve environment and dependency digests;
- run verification, tests, semantic replay, mutation, and at least a subset of ablations;
- sign a reproduction report.

Recommended report fields:

```json
{
  "schema": "dai.independent-reproduction.v1",
  "operator_id": "public-stable-identifier",
  "operator_key_fingerprint": "sha256:...",
  "release_zip_sha256": "sha256:...",
  "source_commit": "...",
  "environment_digest": "sha256:...",
  "verifier_digest": "sha256:...",
  "semantic_result_digest": "sha256:...",
  "mutation_report_digest": "sha256:...",
  "result": "pass",
  "signature": "..."
}
```

## I. Independent Commons quorum

The strongest final quorum should have at least three separately controlled operators and three infrastructure/control domains.

Each signed packet must bind:

- proposal digest;
- capability digest;
- evidence root;
- world-state hash;
- governance epoch;
- challenge nonce;
- issued-at and expires-at;
- verifier implementation digest;
- operator identity;
- signing-key fingerprint;
- infrastructure provider/runtime;
- authority ceiling;
- decision and refusal reason.

The final quorum evaluator must detect duplicate keys, duplicate operators, provider collapse, stale votes, equivocation, and mismatched proposal fields.

## J. Prior-art and world-first review

Search and compare at minimum:

- expert systems and production-rule systems;
- Datalog, Prolog, Answer Set Programming, theorem proving;
- truth-maintenance and assumption-based reasoning;
- proof-carrying data/code and certified computation;
- provenance semirings and why-provenance;
- content-addressed and reproducible computation;
- policy-as-code and authorization logic;
- verifiable computation and proof systems;
- remote attestation and confidential-computing governance;
- Byzantine quorum and federated trust;
- neuro-symbolic and model-assisted symbolic systems;
- autonomous institutions/DAOs and machine governance;
- deterministic planning and workflow engines;
- provenance-aware RAG/knowledge graphs;
- multi-agent debate/voting systems;
- multimodal semantic rendering from a shared graph.

Use the supplied matrix. A work only defeats the narrow novelty claim if it combines every required property in one publicly documented, replayable architecture.

The paper must use **“to our knowledge”** unless independent reviewers explicitly endorse stronger wording.

## K. Release build and public anchors

1. Generate the release key offline or use a stable documented signing identity.
2. Set `SOURCE_DATE_EPOCH` to the signed-tag time.
3. Build the deterministic ZIP.
4. Verify the ZIP on a second machine.
5. Publish the ZIP SHA-256 and public-key fingerprint in:
   - signed Git tag;
   - GitHub release notes;
   - Sigstore/Rekor or equivalent transparency record;
   - Zenodo/OSF/institutional repository deposit.
6. Publish the raw evidence and machine-readable reports, not only a paper PDF.
7. Preserve key-rotation and revocation policy.

## L. Stop conditions

Do not call the release final if any of these remain:

- unresolved lineage conflict;
- unpinned release key;
- unlisted file accepted;
- optimized verifier accepted;
- mutation bypass;
- ablation contradicts the architecture;
- same-author-only oracle;
- no external reproduction;
- pseudo-independent quorum;
- no network-denial evidence;
- changed solver after hidden cases;
- unreviewed prior-art matrix;
- authority boundary not explicitly false.

A transparent RC with one red gate is stronger science than a “final” release whose hard case was hidden.
