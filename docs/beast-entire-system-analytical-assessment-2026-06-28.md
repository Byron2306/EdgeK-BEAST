# BEAST Entire System Analytical Assessment

Date: 2026-06-28

Scope: gateway, TUI, provider routing, PREC, memory/security, crystal reuse, KV/prefill storage, Commons, proof-local compute, enterprise controls, deployment surfaces, and readiness gaps.

## Executive Verdict

BEAST is now best described as an advanced local inference-economy control plane. It is strongest where it treats compute as a governed artifact lifecycle: requests become identities, decisions become signed receipts, provider results become reusable crystals, memory residue becomes human-readable and tamper-evident, and the TUI gives operators a live cockpit over those layers.

It is not yet production GA for broad external users. The local stack is coherent and testable, but several integrations remain contract-level or reachability-level rather than semantic acceptance tested. The right readiness label is:

**Local alpha infrastructure with production-shaped contracts and growing production hardening.**

## Live Snapshot

Observed live gateway after restart:

| Surface | State |
| --- | --- |
| Gateway | Healthy on `127.0.0.1:8000` |
| MCP HTTP | Healthy on `127.0.0.1:8001` |
| LiteLLM sidecar | Responding on `127.0.0.1:4000` |
| Ollama | Responding on `127.0.0.1:11434` |
| Provider secrets | Empty vault, but local/sidecar routes are operational |
| Memory Hull | 12 verified sidecars, 0 failed |
| Residue Seal | Ed25519 key present, mode `0o600` |
| Agent Passport | 5 valid policy rules |
| Crystal reuse storage | 11 active credits |
| Durable KV prefill identities | 3 |
| Live KV tensor blocks | 0 |

The KV result is important: BEAST currently has durable prefill identities even when no live engine KV tensor block is loaded. The TUI now reflects that distinction instead of showing a false zero.

## Recent Fixes

| Issue | Fix | Result |
| --- | --- | --- |
| Provider secrets showed `WARN`/degraded in a local stack | TUI now distinguishes configured secrets from local/sidecar-only operational routes | No warning when LiteLLM/Ollama/local routes are the active path |
| KV prefill blocks showed zero | Durable storage metrics now expose `stored_by_type`, `kv_prefill_credits`; TUI combines durable prefills and live KV blocks | TUI shows durable prefill value even when live KV transport is empty |
| TUI mascot looked static | TUI now prefers real per-frame PNG assets | Animated sprite path is active |
| Stale TUI/gateway confusion | Stale gateway killed and managed gateway restarted | Live gateway uses current code |

Verification:

```text
7 focused tests passed
```

Covered provider secret semantics, durable prefill display, crystal reuse TUI summary, durable prefill storage, and the thin integration harness.

## System Map

| Layer | Primary modules | What it does | Current quality |
| --- | --- | --- | --- |
| Gateway/API | `app/main.py` | Exposes `/edgek/*`, OpenAI-compatible routes, deployment, compute, memory, crystal, enterprise, Commons, and TUI data endpoints | Broad and live; endpoint count is high, so contract discipline matters |
| TUI | `app/cli/ui.py`, `app/cli/api.py` | Operator cockpit over gateway, sessions, routing, providers, intelligence, economy, chronicle, deployment, diagnostics, settings | Strong local visibility; still needs richer drill-down modals |
| Provider routing | `provider_registry.py`, `provider_adapters.py`, `proxy/server.py`, LiteLLM sidecar | Routes local, OpenAI-compatible, native providers, Ollama, LiteLLM | Healthy locally; cloud secrets are optional unless cloud routes are selected |
| PREC lifecycle | `prec_lifecycle.py`, `orchestrator.py` | Tracks perceive/reason/economize/crystallize lifecycle | Visible and useful; could be more tightly tied to crystal decisions |
| Memory/security | `memory_hull.py`, `residue_seal.py`, `agent_passport.py` | Editable Markdown residue, signed sidecars, SPIFFE-shaped local identities, policy decisions | One of the strongest production-shaped areas |
| Crystal reuse | `crystal_reuse_gateway.py`, `durable_inference_storage.py`, `kv_cache_transport.py` | Decides reuse vs provider, stores answers, semantic credits, durable prefills, KV block metadata | Working local core; external cache correctness remains future work |
| Thin harness | `integration_harness.py` | Runs passport -> reuse decision -> provider verify -> seal -> hull -> enterprise -> readiness gate | Correct narrow orchestration path; provider executor remains injectable |
| Enterprise | `enterprise.py` | Teams, users, virtual keys, budgets, observability, encrypted traces, policy packs | Good local control plane; needs production auth boundary |
| Compute economy | `inference_interceptor.py`, `compute_ledger.py`, `commons_economy.py` | Tracks avoidable tokens, receipts, savings, credits | Useful shadow economics; needs longer production traffic windows |
| Commons/proof-local | `commons_space_registry.py`, `federated_commons.py`, `proof_local_compute.py` | Spaces, replay, adoption, federation receipts, public-safe manifests | Advanced lab substrate; not yet live internet federation |
| Inference fabric | `inference_engine_fabric.py` | Declares Ollama, llama.cpp, vLLM, SGLang, TGI, TensorRT-LLM, cache backends | Good capability inventory; most GPU/service engines are not configured |
| Observability/evals | `crystal_integrations.py`, `otel_connector.py` | OpenLLMetry, Langfuse, TensorZero, Promptfoo export/probe contracts | Contract-level plus bounded probes; needs acceptance tests |

## Main Runtime Flow

The strongest intended request path is now:

1. Request enters gateway or TUI session.
2. Agent Passport authorizes caller/action/target.
3. Crystal Reuse Gateway checks semantic credits, exact answers, durable prefills, semantic matcher, and live KV transport.
4. If reusable, provider execution can be skipped.
5. If not reusable, provider route runs through BEAST/LiteLLM/Ollama/native adapter.
6. Provider output is verified.
7. Residue Seal signs decision/receipt.
8. Memory Hull writes Markdown plus signed sidecar.
9. Enterprise Manager records budget, observability event, encrypted trace.
10. Readiness hardening emits a gate receipt.

This is production-shaped because each layer leaves an auditable artifact. Its weakness is that only some real provider executions currently traverse the full harness automatically; the harness exists as a thin integration path and should become the default enforced route.

## What Works Well Together

| Combination | Why it matters |
| --- | --- |
| TUI + `/edgek/*` snapshot endpoints | Operators can see almost every subsystem without manual log spelunking |
| Agent Passport + Residue Seal | Policy decisions become signed evidence, not ephemeral booleans |
| CrystalReuseGateway + DurableInferenceStorage | Exact answers, semantic credits, and prefill identities are reusable before provider spend |
| MemoryHull + Chronicle | Human-readable residue can be linked back into operational memory and evidence |
| EnterpriseManager + IntegrationHarness | Team budget, trace, observability, and encrypted receipts attach to real inference paths |
| Commons Spaces + Compute Economy | Reuse claims can be staged as governed, replayable compute-reduction artifacts |
| LiteLLM/Ollama + Provider adapters | Local and sidecar routes keep BEAST useful without cloud credentials |
| OpenLLMetry/Langfuse/TensorZero/Promptfoo contracts + Crystal decisions | Reuse lifecycle can be exported into observability, feedback, and eval systems |

## Integration Inventory

| Integration | Current status | BEAST role | Remaining proof |
| --- | --- | --- | --- |
| Ollama | Configured/live | CPU-local default model/runtime | Per-model quality and context reuse benchmarks |
| LiteLLM | Sidecar responding | Provider gateway/model registry | Full proxy dependency install and route acceptance tests |
| LMCache | Contract/probe profile | External KV cache/offload | Real KV restore correctness under vLLM/SGLang |
| GPTCache | Contract/probe profile | Semantic answer cache | Semantic lookup precision/false-reuse evaluation |
| OpenLLMetry | Contract/probe profile | Crystal lifecycle spans | Collector ingestion and trace shape validation |
| Langfuse | Contract/probe profile | Trace/dataset/eval observations | Authenticated observation ingestion |
| TensorZero | Contract/probe profile | Feedback/optimization loop | Feedback acceptance and optimization effect |
| Promptfoo | Config/file probe profile | Reuse safety eval gates | Actual eval execution in CI |
| vLLM/SGLang/TGI/TensorRT-LLM | Capability profiles | High-throughput/prefix-cache runtimes | Live engine attach and cache compatibility tests |
| GitHub PR connector | Endpoint/module present | Chronicle/PR evidence import/export | Live repo workflow tests |
| MCP broker | Live HTTP/broker state | Governed tool execution | Broader tool catalog and approval UX |

## What Is Working

- Gateway stack is live and restarts cleanly.
- TUI shows live system state and new memory/crystal layers.
- Provider routes can operate locally without cloud keys.
- Provider secret warnings no longer conflate missing cloud keys with local readiness.
- Memory Hull writes and verifies sealed residue.
- Residue Seal uses native Ed25519 when available.
- Agent Passport validates local SPIFFE-shaped identities and signed policy decisions.
- Crystal Reuse Gateway has working exact answer, semantic credit, durable prefill, KV transport, and provider fallback decisions.
- Durable storage now reports stored compute by type, including KV prefills.
- Thin integration harness proves end-to-end signed request-to-receipt flow.
- Enterprise Manager can record usage, observability, encrypted traces, and budgets.
- Commons/proof-local systems provide a large experimental surface for replayable compute claims.
- Inference fabric declares local, CPU, GPU, cache, and orchestration capabilities.

## Main Gaps

| Gap | Why it matters | Recommended next move |
| --- | --- | --- |
| Harness not yet the universal runtime path | Some routes can still bypass the full passport/reuse/seal/hull/enterprise chain | Move provider execution through `BeastIntegrationHarness` by default |
| External integrations mostly contract-level | Payloads exist, but services may reject them or behave differently | Add acceptance tests per service with short timeouts and fixtures |
| Live KV tensor blocks are zero | Durable prefills exist, but real engine KV movement is not active | Add a live Ollama/vLLM/SGLang KV restore harness |
| LiteLLM proxy dependency warning exists in logs | Some sidecar launches can fail without `litellm[proxy]` deps like `backoff` | Normalize requirements and install path |
| Cloud provider secrets absent | Fine for local mode, but cloud routes cannot be truth-tested | Add secret presence/readiness by selected route, not global provider list |
| Commons federation not continuously running | Local receipts exist, but long-running cross-node behavior is unproven | Run two/three-node federation soak with churn and replay |
| Compute economy is shadow/local | Savings claims need longer real traffic windows | Add 7/30-day workload-frequency receipt pipeline |
| TUI detail depth | Surfaces are broad, but some rows lack sealed receipt drill-down | Add modals for crystal decisions, enterprise traces, and Memory Hull sidecars |
| API surface is very large | Broad endpoints increase regression risk | Publish stable API groups and deprecate experimental routes explicitly |
| Auth boundary is local-shaped | Agent Passport is SPIFFE-shaped but not mTLS/SPIRE-backed | Bind passports to real certs or workload identity for deployment |

## Architectural Evaluation

BEAST’s architecture is ambitious but internally consistent: it treats inference as a governed supply chain rather than a stateless API call. The most important architectural decision is separating durable semantic artifacts from engine-native KV blocks. That is the right trade-off. KV cache is powerful but brittle; semantic credits and signed residue are more portable.

The main architectural risk is breadth. BEAST has gateway, TUI, provider routing, compute economy, Commons, federation, proof-local, enterprise, plugins, skills, cache integrations, observability, and eval exports all in one system. That breadth is useful for a lab, but production will require stricter lanes:

- enforced request path,
- stable API contracts,
- explicit experimental namespaces,
- acceptance probes for every external system,
- deployment profiles that say exactly what is required for local, team, and production modes.

## Readiness Scorecard

| Dimension | Score | Rationale |
| --- | ---: | --- |
| Local gateway/TUI operation | 8/10 | Live, restartable, broad visibility |
| Memory/security integrity | 8/10 | Signed, verified, editable, policy-shaped |
| Crystal reuse local core | 7/10 | Works locally; durable prefill metrics fixed |
| Provider routing | 7/10 | Local/sidecar strong, cloud depends on secrets |
| Enterprise controls | 6/10 | Good local primitives, not full external auth |
| External integrations | 4/10 | Good contracts, incomplete acceptance tests |
| Production ops | 5/10 | Artifacts exist, but service supervision and drills need work |
| Federation/Commons | 5/10 | Advanced lab receipts, not continuous public network |
| Test posture | 7/10 | Focused layers pass; full broad suite can be slow/hang in aggregate |

## Recommended Next Three Moves

1. Make `BeastIntegrationHarness` the default provider execution path for TUI/session/gateway calls.
2. Build a live acceptance harness for LMCache/GPTCache/LiteLLM/OpenLLMetry/Langfuse/TensorZero/Promptfoo with explicit pass/fail receipts.
3. Run a long-lived local production drill: supervised gateway/MCP/LiteLLM/Ollama, backup/restore, migration rehearsal, 7-day traffic capture, and crystal reuse false-positive measurement.

## Bottom Line

BEAST now has a credible spine: identity, reuse, verification, signed residue, memory, enterprise trace, and readiness receipts can be linked in one flow. The system is no longer just a collection of interesting subsystems. It has an emerging operating model.

The remaining work is not more surfaces. It is enforcement, acceptance, soak, and measurement.
