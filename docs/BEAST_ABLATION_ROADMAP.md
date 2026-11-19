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
