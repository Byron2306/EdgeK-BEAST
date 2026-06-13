# Original Design Gap Audit

Generated from the three supplied DOCX discussion/specification files.

## Now Implemented In This Pass

- Gemini ingress normalization: `/v1beta/models/{model}:generateContent` and `/v1/models/{model}:generateContent` now pass through PREC.
- High-token MCP/tool-schema laziness benchmark: static all-tools mode is compared against lazy intent-selected schemas plus learned skip/call decisions.
- Swarm benchmark: deterministic role orchestration is measured across success, failure, approval, critic, and compression-heavy scenarios.
- Tool laziness expected-value brake: redundant low-value calls skip, rare critical successes continue to call.
- LiteLLM compatibility config generator: `GET /edgek/deploy/litellm-config*` and `scripts/generate_deploy_configs.py`.
- Nginx reverse-proxy deployment template: `GET /edgek/deploy/nginx-config` and `deploy/generated/nginx.edgek.conf`.
- Provider prompt-cache keepalive manager: explicit, authorized, dry-run-by-default registry under `/edgek/prompt-cache/*`.
- Tree-sitter parser integration: `tree-sitter-language-pack` is active for Python, JavaScript, TypeScript, Java, C, and C++ in the workspace graph.
- Tool schema pinning/hashing at MCP registry depth: tool schemas are trust-on-first-use pinned in SQLite and mismatches are denied.
- Same-file read-loop cache serving: MCP `read_file` now serves repeated reads from workspace graph L1/L2 cache with hit/source/hash metadata.
- True semantic vector/RAG file-read interception: CPU-only `sentence-transformers` is installed, the workspace graph has semantic chunk embeddings, MCP reads expose related chunks, tool laziness uses semantic evidence, swarm runs share compact context, and `/edgek/semantic/dedupe` collapses repeated payloads.
- Live Google AI Studio adapter: Gemini `generateContent` requests execute through `GEMINI_API_KEY` / `GOOGLE_API_KEY`, normalize through PREC, and are budgeted under the Google provider.
- Hugging Face router adapter: `/hf/v1/chat/completions` and `/huggingface/v1/chat/completions` execute OpenAI-compatible Hugging Face router calls through `HF_TOKEN`.
- TGI / llama.cpp adapter: `/tgi/v1/chat/completions` and `/llamacpp/v1/chat/completions` route governed requests to `TGI_BASE_URL`, falling back from OpenAI-compatible chat to `/generate`.
- LiteLLM runtime adapter: `/litellm/v1/chat/completions` routes governed requests to a local or remote LiteLLM proxy.
- TGI llama.cpp deployment generator: `/edgek/deploy/tgi-llamacpp` emits build/run commands and BEAST environment wiring.
- Required tool-call interception: `/edgek/tools/intercept` swaps full file reads for top semantic snippets, with generated Nginx `/tool-calls/*` routing and LiteLLM `edgek_tool_interceptor` MCP config.
- Required external tool integrations: `/edgek/tools/integrations` reports GitHub, Postgres, RTK, sqz, LongCodeZip, RepoRelay, and semantic interceptor readiness.
- Token pruning and code filtering: `/edgek/compression/prune` exposes required compressor integration contracts with native-tool execution when available and a deterministic BEAST fallback.
- Ollama scout layer: `/edgek/ollama/status`, `/edgek/ollama/packet`, and `/edgek/ollama/scout` wrap Ollama with BEAST retrieval, schema summaries, tiny tool menus, structured JSON decisions, and deterministic fallback packets.

## Already Present Before This Pass

- OpenAI-compatible ingress.
- Anthropic-compatible ingress.
- Request IR normalization.
- Budget/rate governance.
- Context economizer.
- Workspace graph.
- MCP broker governance and approvals.
- Runtime stasis/circuit breaker ledger.
- Skill tree/meta-tool candidate flow.
- Deterministic swarm kernel.
- Enterprise/team control plane.
- AST/schema-row compression.
- Isolation Forest outlier filter.
- AF_PACKET mmap probe plus DPDK/AF_XDP native probes.
- BEAST cockpit frontend.

## Still Not Fully Implemented

- Provider response streaming for Gemini, Hugging Face, TGI, and LiteLLM. Non-streaming live execution is implemented.
- Live swarm-to-execution coupling. The swarm plans/gates/logs value, but it does not yet drive actual provider/tool execution as a first-class orchestrator.
- Real DPDK dataplane throughput test. This host initializes EAL but its RTL8111 NIC does not appear as a DPDK ethdev; use a supported NIC and boot-time hugepages.
- Native RTK/sqz/LongCodeZip/RepoRelay binaries are required by policy but may report not-ready until installed on the host.

## Evidence Artifacts

- `benchmarks/results/edge_metrics_benchmark.md`
- `benchmarks/results/provider_edge_compare.md`
- `benchmarks/results/live_provider_compare_nvidia_openrouter.json`
- `benchmarks/results/original_discussion_extracts/*.txt`
