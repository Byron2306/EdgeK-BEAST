# BEAST ablations and evidence map

This is a research order, not a production rollout. Keep deterministic closeout as
the coding baseline and freeze suite, revision, model, request and turn limits,
seeds, and comparison rules before collecting results. For each toggle retain
attempts, independent verification, actual model requests/usage, bytes delivered,
wall time, and raw receipts. Record no-effect, failed, and not-run cases separately.
Do not infer an interaction from pilots on different fixtures.

| Order / mechanism | Evidence in hand and what it establishes | Missing comparison or receipt |
|---|---|---|
| 0. Direct coder, closeout, RepoRelay | Repeated synthetic NIM factorial: closeout 15/15 verified, direct 14/15, RepoRelay and combined each 10/15. Earlier shipping traces identify which turns disappeared. | Held-out real repo tasks. Keep RepoRelay off by default; if revisited, compare narrower hints at the same turn limit and inspect the costly read or recovery turns. |
| 1. RTK, SQZ, and combined compression | A completed 45-trial synthetic matrix with full usage; all arms 15/15 verified. Native RTK −4.1% and SQZ −3.7% aggregate input tokens versus raw diagnostic closeout. Same request count as each other, one above control. | Ordinary logs and independently selected repo fixtures, then a separate upstream binary matrix. Add an RTK→SQZ arm only against the best individual stage and account for incremental effects. |
| 2. LongCodeZip-style source compression | Passthrough and AST-stubbed dependency context use the same closeout runner. The edit file is byte exact, and source-packet hashes link to the submitted NIM user message. | Six-trial live pilot, then paired repeats and held-out source cases. Track rereads and false fixes. Vary dependency ambiguity and include a long function whose body is essential so elision can lose. |
| 3. RAG, RepoRelay alternatives, memory | C4-X pgvector benchmark bundles include case/scorecard artifacts. The run labels its baseline adapters local references rather than independent implementations. The document frontier includes audit/oracle protocol materials, not confirmed blinded human and native vision scores. | Compare no retrieval, lexical, and vector retrieval on frozen tasks and false-neighbor cases. Measure receipts for chunks actually used. Test memory recall separately with fresh, stale, and wrong-repo records. Keep missing document annotations and adjudication uncredited. |
| 4. Interception, cascade, routing, swarm | Governed-interception summaries include routed attempts, feedback reruns, receipt chains and estimated spend. TGI pack includes backend health, routed path, batching and spend fields. A direct-coder swarm screenshot shows advisory role dispatch with zero model calls. | Compare pass-through with interception at the same route, and separate streamed action extraction, retry/repair, batching, route selection, and specialist calls. Under fixed budgets report verified rate, invalid or duplicate actions, time to first action and all added calls. No compute credit for routing telemetry alone. |
| 5. KV and inference reuse | The coder integration can identify local engine payloads by compatible prefix identity. Forge KV Level 6 is fixture-driven and excludes native context export; Levels 7/8 are offline gauntlets. Those are custody/protocol evidence, not a live native restore result. | First local same-engine cold vs warm vs explicit import. Retain engine-side proof of cache consumption, cached and recomputed prefix tokens, prefill/TTFT, transfer time and byte overhead. Change one prefix/model/tokenizer/quantization anchor and show stale state gets no credit. Hosted provider caching, cross-node restore and transport are distinct arms. |
| 6. Semantic RAID and resume | Real context-packet store, content hash, mirrors, index, and reconstruction code. That proves there is a recovery mechanism, not a prompt compressor. | Compare rebuild vs RAID restore on identical interrupted tasks. Drop or corrupt a fixture copy, restore exactly, refuse if all copies are bad, and measure time, source rereads and successful resume. |
| 7. Sensorium, memfd, AF_XDP and Commons | The uploads include five sealed-memory receipt entries in the large gauntlet pack, AF_XDP echo evidence, Sensorium logs, and Commons lab registrations. The sampled lab registration has `require_arda=false`. These are separately scoped observations. | Keep observability overhead, descriptor transport, AF_XDP transport and authenticated cross-node workload delivery in separate lanes. Require a common run ID, workload digest and receiver verification before joining them to an inference or crystal result. A registration is not execution; an echo is not a routed model call. |
| **7B. Physical crystal distribution and handoff** | The real capsule worker checks seals and digests through a read-only mapping after an SCM_RIGHTS handoff. It copies payload bytes for JSON parsing. The current pipe helper reads and hashes only, so it is not a like-for-like replay comparison. | Compare whole blobs, Git packs, and real Xet on a pinned artifact corpus, then pipe vs sealed memfd with the identical local worker. Feed actual reconstruction, transfer, and verification costs into final crystal economics. See the [stage protocol](#stage-7b-physical-crystal-distribution-and-handoff). |
| 8. Accounting across stages | Request and token usage records, estimated spend fields, shadow and Compute Governor receipts exist. The prior PGEC record joins are insufficient for causal reuse credit where the writer fills pass/zero-call/latency fields directly. | Compare metered versus shadow costs and publish coverage. Identify what is observed, estimated or unknown. Include cold creation, validation, storage/transfer and fallbacks. Report break-even and cost per independently verified task; never blend counterfactual token savings with billed spend or measured GPU compute. |
| **9. Crystals, last** | The BEHEMOTH Phase II runner uses the real promoted family registry/interpreter. The reported cross-revision run reproduced final-tree digests for two seeds. A separate uploaded proper-coding receipt has two crystal verifications but no verified live sample; PGEC flags written by a receipt constructor are not replay or runtime verification. | Measure cold solve/promotion vs warm replay on unseen recurrences. Add direct, individual child, sequential, and lattice arms; run benign drift, semantic near-miss, hidden postcondition failure, incompatible environment and damaged artifact controls. Independently verify effect, rollback and final tree. Measure actual model and engine calls, verification cost, and break-even. Cross-node/cross-provider claims require distinct evidence that the destination executed and verified the effect. |

## Concrete code and evidence anchors

- Context treatments: `app/context/compression_tiers.py`,
  `app/kernel/agents/coder_integrations.py`, and
  `scripts/proof/run_coder_efficiency_matrix.py`.
- Recovery and transport: `app/kernel/data_processing/semantic_raid.py`,
  `app/kernel/compute/kv_transport.py`, `app/kernel/compute/local_prefix_kv_store.py`,
  and `app/kernel/compute/forge_kv_level{6,7,8}_gauntlet.py`.
- Interception and crystals: `app/kernel/compute/inference_interceptor.py`,
  `app/kernel/compute/streaming_interceptor.py`, `app/kernel/compute/family_crystals.py`,
  and `scripts/proof/crystal_ir_reuse_gauntlet.py`.
- Archived evidence families reviewed: governed interception (including TGI),
  C4-X pgvector and document frontier, gauntlet memfd, AF_XDP echo, Commons lab,
  Ollama Crystal IR, and the BEHEMOTH Phase II runner and controls. This was a
  selective review of manifests and representative receipts, not a certification
  of every archive member. Raw uploads and local registry databases are not
  included in this branch.

Crystals come after the other lanes so the final paired run can distinguish
actual replay savings from a smaller prompt, an already warm engine, cheaper
verification, or recovered context.

## Separate the parser, symbols, graph, and RAG

The next context experiments should not add every navigator to the same prompt.
These are distinct layers, even though parts of BEAST share an index.

| Layer | Confirmed code path | Comparison |
|---|---|---|
| Parser (Tree-sitter) | `code_indexers.py` uses optional Tree-sitter grammars and language-specific fallback extractors. The parser status and individual symbol provenance are available. | Tree-sitter enabled vs fallback-only on a frozen cross-language symbol oracle. Keep the graph, task, and retrieval policy constant. Report actual parser per symbol, completeness, false symbols, parse time and warm/cold index cost. |
| Schema trees / symbol outline | `memory_contract.schema_source` turns indexed symbols for nominated files into schema memory hits and can also emit a capability-contract hit. | Raw exact source vs the same source plus a bounded outline, or symbol outline vs file-only map under matched byte budgets. Do not mix tool-schema changes into the code-symbol arm. Test duplicate names and scoped paths. |
| Workspace / worktree graph | `WorkspaceGraph` indexes files, symbols, imports, and routes; `WorkspaceGraphService` exposes symbol and context views. The memory contract has a separate graph source. | File list vs symbol outline vs symbol outline + dependency edges. Key indexing and reads to the actual bound worktree revision, compare cold build and warm lookup, and mutate a dependency to verify graph invalidation. Do not credit RepoRelay for graph edges it did not supply. |
| RAG | The graph has lexical/semantic lookup and a vector path; the coder vector hook is advisory. C4-X also has pgvector benchmark material and a repository adapter. | No retrieval vs lexical vs vector, using the same chunk set, revision and per-prompt budget. Score recall and distractor selection, exact chunks delivered, rereads, cost, and independent verification. Keep graph+RAG fusion for a later interaction test. |

If “tree setter” refers to a separate feature rather than Tree-sitter, its exact
implementation needs an anchor before it gets an experiment arm. None of these
features is enabled by the prebound LongCodeZip matrix.

## Worktree navigation and output filters

The `worktree-navigation` matrix holds the file set, full-source tool access,
binding, and closeout constant. Arms are a file list, that list plus real indexed
symbols, and the same symbols plus local-import dependency edges. It builds the
real workspace graph in a fresh database per applicable attempt and attaches
the packet on the first provider request. It reports parser provenance, packet
size and submission, graph-build time (included in wall time), paired results
against files, and the incremental graph comparison against symbols. The
8,000-byte ceiling is shared; actual prompt sizes differ and are charged. This
is a small synthetic pilot, not an evaluation of large-repo ranking or warm
graph invalidation. Compression, vector RAG, and crystal replay remain off.

Keep output hygiene experiments separate from this navigation matrix:

- **ANSI:** raw vs strip rendering sequences only. Check split escape sequences,
  exact filenames, tracebacks, and error codes. Include already-clean output.
- **Whitespace:** raw vs conservative normalization, preserving Python
  indentation, diffs, columns when meaningful, and exact edit text. Refuse
  transformations on structured/mutation inputs; start with diagnostics.
- **Chunking:** fixed bytes/lines vs syntax-aware chunks with the same input
  budget and same ranking. Hold retrieval fixed first, then separately test
  overlap and retrieval. Verify boundaries that split a traceback or symbol,
  duplicate delivery, and the rate of downstream reads and completions.

For family-crystal custody, take SQLite online backups using
`scripts/proof/backup_family_crystal_registry.py`. It verifies every record
through the registry, checks expected IDs/digests and promoted child links,
and seals a private inventory and manifest. Store another checked copy on
independent storage. Do not publish the database. A text receipt is not a
backup. Use `scripts/proof/run_behemoth_phase2.py` on a checked copy to run the
real interpreter on generated fixtures with independent visible and hidden
checks, tamper and failed-stage controls. Do not mix those generated controls
with the later live crystal economics matrix.


## Stage 7B: physical crystal distribution and handoff

**Status:** planned, not run. Insert this after the existing telemetry and
transport probes and before the final crystal replay and economics matrix.
This is a physical-byte experiment, independent of Stage 3's source and output
chunking, and does not require model requests.

### 7B.1 Durable storage and cross-host distribution

Freeze an ordered, digest-pinned corpus of export-safe crystal artifacts with
their exact bytes and dependency manifests. Include identical copies, small
edits in place, a shifted insertion near the start, and unrelated content.
Report the native artifact size range. Keep large synthetic size sweeps
separate so they cannot inflate claims for small real capsules.

Use three real arms on the same artifact versions: whole digest-addressed
blob storage, Git packs, and a real Xet client/backend using content-defined
chunking. Pin tool versions and report storage configuration. A local CDC
approximation may serve as a labeled control but cannot stand in for Xet.
Give each arm matching cold (empty receiver) and warm (same prior logical
versions) trials. Distinguish upload/update and fetch; keep client and server
cache state and transport topology explicit. Do not compare local Git I/O
latency directly with hosted Xet network latency.

Record logical bytes, physical stored byte deltas, indexes/manifests and any
other metadata, actual new bytes transferred in each direction, reconstruction
CPU and wall time, and receiver peak RSS with measurement scope. Report
application bytes separately from observed network bytes. Unknown metrics
remain unknown; Git pack size is not a wire-byte receipt. Require the receiver
to reconstruct byte-identical content matching the pinned artifact digest.

### 7B.2 Host-local capsule delivery

After reconstruction, run pipe bytes and a sealed memfd with SCM_RIGHTS
against the same capsule framing and worker behavior. Match spawn versus
already-running worker conditions across arms. Instrument sender preparation
and sealing, payload and control bytes at handoff, receiver read/mmap and hash,
JSON parse and hydration, then replay and independent postcondition verification.
The transport-independent integrity and replay checks must be the same. Record
seal checks for the memfd arm separately. Account for observed copies and peak
RSS without treating an mmap as free or adding shared mapped pages twice.

Record both one-worker cold hydration and reuse of a single sealed mapping
across multiple worker handoffs, charging its initial hydration once. Require
the same successful postcondition and final tree for positive pairs. Exercise
missing or corrupted storage chunks and tampered payloads, and separately test
that the memfd path refuses an unsealed descriptor. A memfd is volatile and
same-host only. Cross-host distribution ends with the bytes reconstructed at
the destination; descriptor handoff begins there.

Join storage, receiver, handoff and replay receipts by run, artifact and
manifest digest. Report any preserved-byte savings separately from model
compute avoided and carry measured costs into the final crystal comparison.
The existing pipe hash helper is useful as a transport control, not a matched
end-to-end replay baseline.

## Stage 4 interception census and experiment order

These paths act on different objects. Keep all on the roadmap, but use a
separate comparison for each mechanism. No live eBPF attachment, existing
listener adoption, or production policy change belongs in the coding benchmark.

| Lane | Actual path and current evidence boundary | Comparison and required receipt |
|---|---|---|
| 4A. Direct-coder stream | NIM and Ollama planner adapters call `StreamingInterceptionEngine`. Native NIM can stop on complete, invalid, repetition, explanation, or estimated budget conditions. | Same NIM SSE request, drain vs complete top-level schema shape vs native policy. Count observed SSE bytes, exit reason, first shape and first completed tool, rejections, repeated proposals and independently verified repairs. Missing usage is unknown. This branch adds the NIM matrix. Match native Ollama streaming separately. |
| 4B. Governed proxy | `execution/execute.py` routes opted-in schema-carrying requests to `GovernedModelClient` using `constrained_output` and `JsonStreamGate`. Existing TGI evidence combines grammar, gate, candidate chain, and verifier feedback. | First fix one provider/model and schema; separate request constraint/dialect from the incremental gate, then split verifier rejection, repair feedback, fixed retry and fallback routing. Record actual backend, requests, verifier checks and counted failures. |
| 4C. Compute interception before provider | `ComputePlane.begin` invokes `InferenceComputeInterceptor`. This path can transform/route a request, resolve it deterministically or via verified reuse, or send it upstream. | Pass-through vs shadow proposal vs one independently verified resolved branch at a time. Keep the candidate set fixed first. No avoided-call credit unless the effect verifies and no provider/engine call occurred. |
| 4D. Placement and specialist escalation | Governed scorecard/circuit/placement logic and `swarm_specialist.py` are distinct from surface/advisory swarm roles. TGI has sequential versus concurrent evidence. | Fixed route vs ranked route, then specialist off/on and serial vs batching in separate paired runs. Charge all candidates, retries, verification, and queueing. Require actual dispatch and model-call receipts, not advisory UI events. |
| 4E / Stage 5. Reusable context | `SemanticComputePageStore` keeps exact-identity verified application pages. `memory_contract.page_source` exposes page hits, alongside a separate verified semantic cache source. `local_prefix_kv_store.py` concerns engine-prefix compatibility, not application page hits. | Rebuild vs matched page lookup and use. Test stale identity and tamper refusal, then independently verify the dependent result. Separately test the engine's native KV cache with evidence of actual consumption and prefill avoided. |
| Stage 6. Recovery, not a hit policy | `SemanticRaidStore` stores and reconstructs digest-bound mirrored context packets. `ArtifactFossilLayerStore` checkpoints and replays lineage. The IDE stream has an explicit context-packet persistence hook. | Rebuild vs restore after matched interrupted work. Test intact, one copy damaged and both copies damaged. Charge persistence/recovery, verify restored bytes and the resumed task. Test fossil lineage replay separately. |
| Stage 7. Socket custody and packet delivery | `socket_guardian.py` has inherited/systemd listener custody, lease handoff and a separate `pidfd_getfd` adoption path. ARDA-aware XDP simulator and AF_XDP worker/echo evidence are separate paths, not proxy/cache hooks. | On authorized fixture listeners compare normal restart/systemd handoff vs Guardian paths, recording continuity, refusal and whether pidfd actually worked. Separately compare the kernel path vs AF_XDP for identical authorized test traffic, distinguishing simulator, actual copy mode and actual zero-copy mode. Require receiver payload verification, fallback counters, CPU and tail latency. |
| Stage 7B / final. Physical artifacts and replay | Sealed memfd, Git/Xet/whole blobs and crystal interpreter are distinct transport/storage/work-avoidance layers. | Follow Stage 7B above, then charge its measured costs in the held-out crystal economics comparison. |

For Stage 4A, count only provider-reported usage. Closing an SSE reader can hide
the terminal usage frame even when the provider already did work. Observed SSE
bytes are application bytes read, not socket/NIC bytes or billed tokens. Time to
first complete schema shape is not tool authorization. The tool registry,
worktree approval and independent verification stay unchanged in every arm.

### Stage 4B fixed-route governed proxy pilot

Run `python -m scripts.proof.run_stage4b_governed_proxy --out <fresh-directory>`
for the mock SSE controls. The runner requires a full `jsonschema` validator;
the optional required-keys fallback does not enforce the test's `minItems`.
Then run with `--provider nim --repeats 3 --request-cap 27` for the live pilot.
The gateway is not involved. The runner uses the real `GovernedModelClient`
request, stream, governor admission, and verification path directly.

Each block pairs the same task, prompt, model, provider seed, schema, and SSE
request options. Compare prompt-only drain against schema-constrained drain
to isolate the provider request constraint. Then compare constrained drain
against the identical constrained request with the stream gate allowed to
close early. All arms use the same local schema extraction to select the first
valid object. No feedback, retry, dialect fallback, batching, specialist or
reuse. The constrained dialect defaults to `openai_json_schema`; a route
rejection is sealed as an abort, not retried under another dialect. An explicit
`--dialect nim_guided_json` run is a new, separately identified batch.

The mocked server sends a schema-invalid empty edits array, a valid action,
then trailing bytes and usage. No provider claims from these controls.
The original v1 pilot required exact proposal equality. Its repair outcomes
cannot distinguish wrong fixes from alternate edit spans. Preserve that run as
formatting and stream evidence, not as behavioral verification. In v2 an edit
must name the fixture, have a unique nonempty anchor, and keep the patched
program in the experiment's small Python subset with the original signature.
A separate, resource-limited worker per check runs public and held-out behavior
tests. This is not an OS sandbox or a general-purpose Python verifier. An edit
outside the supported subset is classified separately from a behavior failure.
V2 reports the exact match only as a diagnostic, and its mock controls use a
whole-file replacement that is not the canonical edit. Request arms, fixture
prompts, seeds, and model are unchanged.
The observed content bytes exclude SSE overhead; observed SSE line bytes
exclude line separators and are not network bytes.
Terminal usage may be absent after client close. Use observed usage on the
attempts rather than the governed client's existing cost estimates and never
infer prevented model computation or billing from closing the client.
