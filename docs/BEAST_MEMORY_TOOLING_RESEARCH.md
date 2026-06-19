# BEAST Memory, Tooling, and Workflow Research Notes

Date: 2026-06-13

## Direction

BEAST should treat memory as a governed compiler pipeline:

1. Ingest exact artifacts: Chronicle, route cards, task envelopes, workflow cards, tool outcomes, source files, schemas, logs.
2. Normalize them into typed records with stable IDs, hashes, timestamps, source paths, provider/task metadata, and redaction status.
3. Chunk by structure first, then by size.
4. Add contextual headers before embedding or lexical indexing.
5. Retrieve by metadata filters first, then hybrid dense plus sparse/lexical scoring.
6. Re-rank into task envelopes, Ollama scout packets, swarm cartography, and MCP tool menus.
7. Write outcome back to Chronicle and promotion candidates.

## Compression And Chunking

Practical BEAST chunk types:

- ~~`code_unit`: top-level class/function/interface/type/module section.~~
- ~~`code_window`: overflow slice from a large code unit.~~
- ~~`markdown_section`: heading-bounded doc section.~~
- ~~`structured_record`: JSON/YAML/TOML object or table path.~~
- ~~`chronicle_record`: one task memory event.~~
- ~~`route_card_record`: routing preference and avoidance memory.~~
- ~~`tool_outcome`: high-value MCP/tool result.~~
- ~~`schema_node`: DB/API/message schema field or contract.~~

Keep these fields on every chunk:

- ~~`chunk_id`~~
- ~~`source_uri`~~
- ~~`source_type`~~
- ~~`artifact_type`~~
- ~~`task_id`~~
- ~~`provider`~~
- ~~`language`~~
- ~~`chunk_kind`~~
- ~~`schema_path`~~
- ~~`symbols`~~
- ~~`start_line`~~
- ~~`end_line`~~
- ~~`content_hash`~~
- ~~`context_header`~~
- ~~`token_estimate`~~
- ~~`embedding_model`~~
- ~~`redaction_status`~~

Compression layers:

- ~~Lossless: zlib, schema-row compression, canonical JSON, AST canonicalization.~~
- ~~Semantic: AST summaries, symbol tables, call/import maps, section summaries.~~
- ~~Retrieval: contextual headers, lexical token index, dense vectors, sparse vectors, recency and outcome weighting.~~
- ~~Execution handoff: pack only the winning chunks plus exact source references.~~

Implemented first layered compression slice:

- ~~`app/kernel/ast_compressor.py` supports schema-row JSON, canonical JSON/zlib, Python AST canonicalization, and Python AST summaries.~~
- ~~`app/kernel/compression_pipeline.py` selects JSON, Python AST, or text-prune layers.~~
- ~~`POST /edgek/compression/pipeline` returns compression layers, winning chunks, scored evidence, and Chronicle write status.~~
- ~~Compression chunks include stable IDs, hashes, source URI, chunk kind, schema path, symbols, context headers, token estimate, and redaction status.~~
- ~~Compression pipeline emits `compression_pipeline` evidence bound to `tool:compression_prune`.~~
- ~~High-value compression/tool evidence writes durable records through `app/kernel/evidence_chronicle.py`.~~

Implemented second layered compression slice:

- ~~Compression pipeline emits `markdown_section` chunks from heading-bounded Markdown.~~
- ~~Compression pipeline emits `chronicle_record` chunks from Chronicle/evidence memory records.~~
- ~~Compression pipeline emits `route_card_record` chunks from route-card memory.~~
- ~~Compression pipeline emits `schema_node` chunks from DB/API/message schema-shaped records.~~
- ~~InsightCompiler reads `data/evidence_chronicles` so durable scored evidence participates in ranking and promotion.~~

## Retrieval Stack

Near-term local stack:

- ~~SQLite graph is the source of truth.~~
- ~~Dense vectors remain optional through `sentence-transformers`.~~
- ~~Lexical fallback must work without embeddings.~~
- ~~Metadata filters come before scoring.~~
- ~~Ollama receives compact packet context, not raw repository dumps.~~

Implemented first forensic L4 RAG slice:

- ~~`app/kernel/forensic_memory.py` provides an append-only SQLite L4 event ledger.~~
- ~~L4 query applies metadata filters before lexical scoring.~~
- ~~L4 retrieval works without embeddings and reports `vector_available: false` until dense indexing is configured.~~
- ~~RuntimeGovernor emits L4 forensic memory for rejected, failed, abandoned, and circuit-open attempts.~~
- ~~`POST /edgek/interception/event` can persist broad interception events into L4 memory.~~
- ~~`GET /edgek/forensics/l4/state` reports source-of-truth, event kinds, providers, and retrieval capabilities.~~
- ~~`POST /edgek/forensics/l4/query` returns compact forensic context for RAG, ranking, and Ollama scout packets.~~
- ~~L4 forensic events store interception layer metadata and support layer-first filtering.~~
- ~~Ollama Scout packets include compact `forensic_context` from L4 query results, not raw repository or packet dumps.~~
- ~~InsightCompiler can pull bounded L4 forensic query results into ranked live evidence before handoff.~~

Next vector upgrade options:

- SQLite plus local embeddings: simplest, current fit. Recommended next implementation because it preserves the current SQLite source-of-truth and keeps dense vectors optional.
- Postgres with pgvector: best when BEAST needs shared relational memory and SQL governance.
- Qdrant: best fit for hybrid dense/sparse search and named vectors.
- Chroma: quick local prototyping, weaker governance story.
- LanceDB/DuckDB/Parquet: good for local analytical memory and artifact snapshots.

Near-term vector decision:

- Use SQLite plus optional local embeddings first.
- Keep lexical fallback as the mandatory path.
- Keep metadata filters before lexical or dense scoring.
- Treat pgvector/Qdrant/LanceDB as adapter targets after the local embedding contract is stable.

## Insight Compiler

BEAST also needs an analytical layer above memory retrieval. The goal is not to
hand cloud agents more context; the goal is to hand them the best scoped local
judgment BEAST can produce.

Implemented first slice:

- ~~`app/kernel/insight_compiler.py`~~
- ~~`POST /edgek/insights/compile`~~
- ~~`POST /edgek/handoff/prepare`~~
- ~~Chronicle/provider diagnostic records become ranked `EvidenceRecord` objects.~~
- ~~Cloud handoff preparation is not `ready` unless current task markup is present.~~

Implemented second slice:

- ~~`beast handoff-prepare`~~
- ~~`beast openclaw-plan --handoff ...`~~
- ~~`beast hermes-plan --handoff ...`~~
- ~~Openclaw/Hermes profile plans can attach a `handoff_precheck`.~~
- ~~The CLI accepts current task markup from flags or a JSON file.~~
- ~~Complete markup can be persisted under `data/current_tasks/`.~~
- ~~Incomplete markup returns `ready: false` instead of silently producing a cloud-ready packet.~~

Implemented third slice:

- ~~`BeastCLIExecutor.plan()` accepts an `insight_packet`.~~
- ~~Openclaw/Hermes plan actions are shaped by top ranked evidence.~~
- ~~Plans expose `local_insight` summary beside `local_inference`.~~
- ~~The gateway `/edgek/beast-cli/plan` and `/edgek/beast-cli/execute` accept `insight_packet` or `handoff_precheck.insight_packet`.~~
- ~~The CLI injects ready handoff insight before local/gateway profile planning.~~

Implemented fourth slice:

- ~~`InsightCompiler.compile()` accepts live `evidence_records`.~~
- ~~`InsightCompiler.prepare_handoff()` accepts live `evidence_records`.~~
- ~~`tool_interception` evidence can rank immediately beside Chronicle evidence.~~
- ~~`POST /edgek/insights/compile` accepts `evidence_records` / `live_evidence`.~~
- ~~`POST /edgek/handoff/prepare` accepts `evidence_records` / `live_evidence`.~~

~~Every parser, database probe, tool run, lint check, test failure, Chronicle
record, provider diagnostic, route card, and workflow should normalize into a
common evidence envelope:~~

- ~~`evidence_schema_version`~~
- ~~`evidence_id`~~
- ~~`source_type`~~
- ~~`source_uri`~~
- ~~`scope`: repo, package, module, file, symbol, schema, provider, workflow, task~~
- ~~`artifact_type`~~
- ~~`task_id`~~
- ~~`provider`~~
- ~~`severity`~~
- ~~`confidence`~~
- ~~`freshness`~~
- ~~`relevance`~~
- ~~`risk`~~
- ~~`blast_radius`~~
- ~~`repeat_count`~~
- ~~`verification_strength`~~
- ~~`failure_probability`~~
- ~~`uncertainty`~~
- ~~`expected_value`~~
- ~~`priority_score`~~
- ~~`capability_family`~~
- ~~`recommended_capability_id`~~
- ~~`promotion_candidate`~~
- ~~`learning_status`~~
- ~~`score_breakdown`~~
- ~~`signals`~~
- ~~`relationships`~~
- ~~`recommended_actions`~~

Local scores to compute before cloud handoff:

- ~~Relevance score: how tightly the evidence matches the current objective.~~
- ~~Confidence score: how strong and direct the evidence is.~~
- ~~Severity score: impact if ignored.~~
- ~~Blast-radius score: how much code/data/runtime could be affected.~~
- ~~Recency/freshness score: whether the evidence is stale.~~
- ~~Repetition score: whether Chronicle/tool logs show a repeated pattern.~~
- ~~Failure probability: likelihood that this is the current root cause.~~
- ~~Expected value: likely payoff of acting on this evidence.~~
- ~~Verification strength: whether tests, lint, syntax, health checks, or MCP audit confirm it.~~

The handoff packet should include ranked insight, not raw search results:

- ~~likely root cause~~
- ~~confidence and uncertainty~~
- ~~safest local next action~~
- ~~exact evidence references~~
- ~~known failed attempts~~
- ~~policy/credential/circuit state~~
- ~~recommended tool sequence~~
- ~~what not to touch~~

Current task markup must exist before any cloud handoff:

- ~~`objective`~~
- ~~`scope`~~
- ~~`constraints`~~
- ~~`success_criteria`~~
- ~~`task_markup_id`~~
- ~~`task_markup_hash`~~
- ~~local timestamp/source~~

~~This rule prevents context-free escalation. BEAST should know what job is active,
what success means, what scope is allowed, and what constraints matter before
any cloud agent receives context.~~

CLI shape:

```bash
beast handoff-prepare \
  --objective "Diagnose provider failure" \
  --scope "provider diagnostics" \
  --constraint "local first" \
  --success-criteria "ranked evidence included"
```

For profile planning:

```bash
beast hermes-plan --handoff \
  --objective "Coordinate cloud handoff" \
  --scope "provider diagnostics" \
  --success-criteria "handoff precheck ready"
```

## Promotion, Prioritization, And Ranking

~~The skill tree, tool registry, MCP routes, workflow cards, and promotion loop
must not promote merely because something happened often. Promotion needs a
ranked success model.~~

Promotion candidate inputs:

- ~~repeated task class~~
- ~~repeated successful tool sequence~~
- ~~repeated failure avoided by a fix~~
- ~~high Chronicle recurrence~~
- ~~high verification strength~~
- ~~low blast radius~~
- ~~low policy friction~~
- ~~stable output schema~~
- ~~measurable token/time/error reduction~~
- ~~user approval or explicit trust boundary~~

Ranking signals:

- ~~success rate~~
- ~~failure rate after promotion~~
- ~~median verification confidence~~
- ~~average tokens saved~~
- ~~average time saved~~
- ~~number of avoided cloud calls~~
- ~~number of avoided risky tool calls~~
- ~~recency-weighted usage~~
- ~~provider/tool reliability~~
- ~~required approval rate~~
- ~~rollback or rejection count~~

Promotion statuses should stay explicit:

- ~~`observed`~~
- ~~`candidate`~~
- ~~`validated`~~
- ~~`approved`~~
- ~~`promoted`~~
- ~~`degraded`~~
- ~~`retired`~~

~~BEAST should prioritize the next best action by expected value and safety, not
by whatever subsystem noticed a signal first.~~

Implemented first source-envelope emitter slice:

- ~~`app/kernel/evidence_envelope.py` builds scored common evidence envelopes at the source.~~
- ~~Tool interception emits full scored envelopes with failure probability, uncertainty, priority, promotion, learning status, and score breakdown.~~
- ~~Quality Cascade emits `quality_verifier` evidence records for every local check.~~
- ~~Quality Cascade evidence binds provider diagnostic checks to `workflow:provider_diagnostic`.~~

Implemented first promotion ranking slice:

- ~~Promotion candidates carry `priority_score`.~~
- ~~Promotion candidates carry a `ranking` block with score, status, components, weights, and recommendation.~~
- ~~Promotion ranking combines expected value, verification score, repetition score, tool value, safety score, approval friction, and capability binding.~~
- ~~Promotion ranking metrics track success rate, post-promotion failure rate, verification confidence, token/time savings, avoided cloud/risky calls, recency-weighted usage, reliability, approval rate, rollback/rejection count, and schema stability.~~
- ~~Promotion candidates carry explicit `promotion_status`.~~
- ~~Promotion candidate listing sorts by priority score before recency.~~
- ~~Promotion ranking statuses include `promote_next`, `prioritize`, `observe`, and `deprioritize`.~~

## Interception

Interception is the control point that keeps BEAST local-first and sane.

Implemented first interception slice:

- ~~File-read interception emits `interception` metadata.~~
- ~~File-read interception emits canonical `tool_interception` evidence records.~~
- ~~Payload compression emits `interception` metadata.~~
- ~~Payload compression emits canonical `tool_interception` evidence records.~~
- ~~Unsupported tool calls return unmatched interception evidence instead of disappearing.~~

Implemented second broad interception slice:

- ~~`app/kernel/interception_events.py` normalizes gateway/proxy/runtime interception events into scored evidence envelopes.~~
- ~~`POST /edgek/interception/event` accepts broad interception events and returns scored evidence.~~
- ~~InsightCompiler accepts `interception_event` live evidence.~~
- ~~Interception events map circuit, latency, packet, cache, port, error, warning, notification, throttle, routing, broker, trace, mining, sandbox, and bypass signals into capability families.~~

Implemented first interception layer-mesh slice:

- ~~`GET /edgek/interception/mesh` exposes the L1-L4 mesh and event-to-capability map.~~
- ~~Interception events carry `interception_layer` plus `intercept_layer_l1` through `intercept_layer_l4` signals.~~
- ~~L1 covers gateway/proxy/provider request-response observations.~~
- ~~L2 covers tool, MCP, CLI, workflow, shell, database, test, and lint observations.~~
- ~~L3 covers policy, credential, circuit, routing, throttle, queue, latency, warning, and notification governance.~~
- ~~L4 covers traces, anomalies, mined sequences, sandbox/bypass events, packet/port observations, cache decisions, and error signatures.~~
- ~~Forensic L4 query accepts `layer` filters so BEAST can retrieve precise local evidence before ranking or handoff.~~

Interception targets:

- ~~file reads~~
- ~~shell commands~~
- ~~MCP tool calls~~
- ~~provider calls~~
- ~~database queries~~
- generated code patches
- ~~test/lint runs~~
- dashboard/widget probes
- ~~secret-bearing payloads~~
- ~~gateway/proxy/runtime attempts~~
- ~~circuit breaker transitions~~
- ~~latency and timeout signals~~
- ~~packet/cache/port observations~~
- ~~routing and broker decisions~~
- ~~trace/mining/sandbox/bypass events~~

Interception should:

- ~~classify intent and risk~~
- redact secrets
- ~~compress or chunk payloads~~
- ~~route to local memory first~~
- ~~attach policy and circuit state~~
- ~~record attempts and outcomes~~
- recommend fallback providers/tools
- ~~emit evidence records for ranking~~
- ~~write Chronicle when the result matters~~
- ~~mark promotion candidates when the same pattern repeats~~

The current compressor/tool-call interception surface is the seed. It should
grow into the point where BEAST turns raw tool activity into governed evidence,
ranked insight, and eventually promoted workflows.

Interception should be treated as a layered mesh, not a single hook:

- ~~L1 request/response: provider calls, proxy routes, status codes, latency, retry-after, payload size, model, route card.~~
- ~~L2 tool/workflow: MCP evaluate/execute, CLI profile actions, shell/database/test/lint invocations, approval gates.~~
- ~~L3 runtime/governance: circuits, stasis wall, throttling, cache hits/misses, broker denials, policy warnings, credential findings.~~
- ~~L4 forensic memory: traces, packet/port observations, sandbox validations, bypass probes, error signatures, anomaly clusters, mined sequences.~~

Forensic L4 memory should gather:

- ~~normalized trace spans with `trace_id`, parent span, route/provider/tool, duration, status, and policy decision.~~
- ~~packet and port observations from proxy/gateway/OS-bypass probes, stored as metadata-first evidence rather than raw packet dumps.~~
- ~~cache and routing decisions, including cache key class, hit/miss, selected fallback, and avoided provider/tool calls.~~
- ~~circuit and throttle transitions, including failure count, retry window, queue pressure, and recovery outcome.~~
- ~~sandbox and bypass attempts, including capability requested, permission boundary, result, and redaction status.~~
- ~~warning/error/notification streams with deduplicated signatures and recurrence windows.~~
- ~~mined sequences from traces that can seed meta-tool and skill candidates.~~

Forensic L4 should improve memory by:

- writing high-value events to `data/evidence_chronicles`.
- chunking trace and event records as `chronicle_record`, `tool_outcome`, `schema_node`, or future `trace_span` chunks.
- ~~feeding compact scored evidence into Ollama Scout packets without requiring raw dumps.~~
- ~~feeding scored evidence into InsightCompiler without requiring a user handoff.~~
- updating promotion ranking metrics for reliability, approval friction, rollback/rejection count, and avoided work.
- ~~preserving only metadata and redacted excerpts by default; raw payload capture should require an explicit forensic/debug approval gate.~~

## Ollama

Ollama should be used as the local classifier/ranker/summarizer, not as an ungated executor.

Jobs:

- ~~classify task type and risk~~
- ~~select tools~~
- ~~rank retrieved chunks~~
- ~~summarize Chronicle memory~~
- ~~draft fallback recommendations~~
- ~~build swarm role briefs~~

Implemented first Ollama decision-contract slice:

- ~~Ollama Scout builds bounded local packets with retrieved chunks, exact context, memory state, tool menu, and constraints.~~
- ~~Offline/server-down runs fall back to deterministic local classification instead of failing the workflow.~~
- ~~Scout packets include `ollama_local_decision_contract` with task type, risk, privacy, cloud handoff status, recommended profile, selected tools, relevant files, and role hints.~~
- ~~Ollama responses are normalized with role hints before downstream use.~~
- ~~BEAST CLI plans surface Ollama decision contracts in `local_inference`.~~
- ~~Scout packets include compact `forensic_context` from L4 memory with layer/event/provider/status filters.~~
- ~~Scout packets include deterministic local `ranked_chunks`, `chronicle_summary`, and `fallback_recommendations`.~~
- ~~`beast scout` exposes ranked chunks, Chronicle summary, L4 forensic context, fallback recommendations, and decision contract from the command hub.~~
- ~~Openclaw/Hermes/Nemoclaw/ZeroClaw plan output surfaces scout packet summaries in `local_inference`.~~

Fallback:

- ~~If Ollama is installed but server is down, BEAST should continue with deterministic ranking.~~
- If a local model is missing, `doctor` should recommend a pull command, not fail the workflow.

~~## Swarm~~

~~Swarm should stay role-based and governed:~~

- ~~Hermes: coordinator/router for role briefs and swarm plan shape.~~
- ~~Openclaw: read-only/local-first planning and inspection.~~
- ~~Nemoclaw: gated high-risk execution profile.~~
- ~~ZeroClaw: planning-only, no tool execution.~~

~~Useful role lanes:~~

- ~~Cartographer: context, graph, memory, schema, exact files.~~
- ~~Compressor: chunk/reduce/package context.~~
- ~~Sentinel: policy, credentials, circuits, approvals, secrets.~~
- ~~Verifier: tests, lint, syntax, static checks.~~
- ~~Scribe: Chronicle and promotion candidate records.~~
- ~~Critic: targeted review when risk or failure warrants it.~~

~~Implemented first governed swarm slice:~~

- ~~`app/kernel/swarm.py` exposes governed profile bindings for Hermes, Openclaw, Nemoclaw, and ZeroClaw.~~
- ~~`GET /edgek/swarm/governance` returns profile and role-lane contracts.~~
- ~~BEAST CLI plans include `swarm_governance` profile and role-lane contracts.~~
- ~~Swarm runs persist execution-profile and role-lane metadata.~~
- ~~Hermes emits role-brief routing events while preserving existing conductor compatibility.~~
- ~~Verifier emits test/lint/syntax/static-check planning for code and test repair tasks.~~
- ~~Scribe emits Chronicle/promotion trace preparation while preserving existing archivist compatibility.~~
- ~~Nemoclaw requires explicit approval, even before high-risk execution wiring expands.~~
- ~~ZeroClaw advertises planning-only/no-tool-execution gates.~~

## Plugins, Skills, Tools, Workflows

Treat every integration as a governed capability record:

Implemented capability-ranked insight slice:

- ~~`EvidenceRecord.recommended_capability_id` links ranked evidence to formal capability records.~~
- ~~Provider timeout/rate/upstream/credential failures map to `workflow:provider_diagnostic`.~~
- ~~Python syntax/import evidence maps to `linter:py_compile`.~~
- ~~Token-heavy intercepted payload evidence maps to `tool:compression_prune`.~~
- ~~BEAST CLI insight actions include `capability_id` when ranked evidence recommends one.~~
- ~~Capability registry validates `workflow:provider_diagnostic`, `linter:py_compile`, and `tool:compression_prune`.~~

Implemented first normalized evidence/ranking slice:

- ~~Evidence records carry `evidence_schema_version`.~~
- ~~Evidence records normalize confidence, freshness, relevance, risk, blast radius, verification strength, and expected value.~~
- ~~Evidence records carry `capability_family` inferred from `recommended_capability_id` or source signals.~~
- ~~Evidence records carry `priority_score` for ranking and handoff ordering.~~
- ~~Repeated/high-value evidence is marked as `promotion_candidate`.~~
- ~~Learning status is normalized as `observe`, `prioritize`, or `promotion_candidate`.~~
- ~~Insight summaries include family counts, capability counts, top capability family, and promotion candidate IDs.~~

Implemented first scoring slice:

- ~~`app/kernel/evidence_scoring.py` centralizes evidence scoring.~~
- ~~Scoring returns expected value, priority score, promotion candidate, learning status, and an explainable score breakdown.~~
- ~~Scoring returns failure probability and uncertainty.~~
- ~~Score breakdowns include expected-value components, priority components, weights, raw scores, and thresholds.~~
- ~~Score breakdowns include local score components for relevance, confidence, severity, blast radius, freshness, repetition, failure probability, expected value, and verification strength.~~
- ~~Scoring weights and thresholds are configurable through `policies.evidence_scoring`.~~
- ~~InsightCompiler uses the shared scorer instead of private rank math.~~
- ~~Evidence records carry `score_breakdown`.~~
- ~~`POST /edgek/evidence/score` scores one normalized evidence envelope for other routes, CLI flows, and future MCP tools.~~

Implemented first promotion/learning bridge:

- ~~PromotionLoop consumes `insight_packet` artifacts.~~
- ~~Promotion evidence records include insight evidence count, insight promotion count, top capability family, recommended capability ID, priority score, family counts, and capability counts.~~
- ~~Repeated normalized insight can promote as `meta_tool_recipe` when the top family is debugging, lint/syntax, tool bus, parsing, or vector.~~
- ~~Promotion actions preserve recommended capability ID, capability family, and priority score.~~
- ~~Promotion recommendations preserve capability/family routing guidance for future skills and meta-tools.~~

Implemented first capability inventory slice:

- ~~`app/kernel/capability_registry.py`~~
- ~~`GET /edgek/capabilities`~~
- ~~`GET /edgek/capabilities/families`~~
- ~~Provider capabilities from policy config.~~
- ~~Core tool capabilities for interception, compression, MCP evaluate/execute.~~
- ~~CLI capabilities for doctor, handoff, Openclaw, Nemoclaw, ZeroClaw, and Hermes.~~
- ~~MCP tool capabilities for BEAST planning, execution, status, catalog, Canon validation, and promotion checks.~~
- ~~Workflow and route capabilities for diagnostics, quality cascade, handoff, route cards.~~
- ~~Parser/linter/database/plugin/skill/debugging/vector/tool-bus capability families.~~
- ~~Capability filtering by `kind`.~~
- ~~Capability family rollups for routing and prioritization.~~

- ~~`capability_id`~~
- ~~`kind`: plugin, skill, MCP tool, CLI, workflow, parser, linter, DB, provider~~
- ~~`family`: agentic CLI, debugging, diagnostics, handoff, lint/syntax, parsing, provider, routing, skill, swarm, tool bus, vector~~
- ~~`command` or `endpoint`~~
- ~~`input_schema`~~
- ~~`output_schema`~~
- ~~`risk_level`~~
- ~~`requires_approval`~~
- ~~`read_only`~~
- ~~`writes_files`~~
- ~~`network_access`~~
- ~~`secret_envs`~~
- ~~`health_check`~~
- ~~`test_command`~~
- ~~`owner`~~
- ~~`promotion_status`~~

Immediate capability families:

- ~~Parsers: tree-sitter, Python AST, JSON/YAML/TOML, Markdown headings, OpenAPI, SQL schema.~~
- ~~Debugging: pytest failure parser, stack trace classifier, log signature matcher.~~
- ~~Lint/syntax: `python -m py_compile`, pytest collection, eslint/tsc when package files exist, shellcheck when scripts exist.~~
- ~~Databases: SQLite introspection, Postgres schema/read-only query, vector store health.~~
- ~~Workflows: provider diagnostic, test failure cascade, dashboard widget cascade, MCP install, provider proxy setup.~~
- ~~Skills: mined task patterns, validated meta-tools, role-level playbooks.~~

## Roadmap Comparison Audit

Compared against `docs/BEAST_V2_ROADMAP.md`, `docs/deployment_integrations.md`,
`docs/edge_runtime_setup.md`, and `EdgeK_BEAST_Meta_Optimization_Whitepaper.md`.

Implemented or substantially covered:

- ~~Task envelope spine, provider diagnostics, context packets, quality cascade, route cards, Forge scorecards, Conductor workflows, Canon validation, promotion loop, runtime governance, MCP broker, CLI operator profiles, Ollama Scout, interception mesh, and L4 forensic memory.~~
- ~~Deployment config generation for LiteLLM/Nginx, `/tool-calls/` routing template, prompt-cache keepalives, TGI/llama.cpp plan, OS-bypass probes, and provider edge comparison benchmarks.~~
- ~~Workspace graph retrieval with optional `sentence-transformers` dense embeddings and deterministic lexical fallback.~~

Remaining mismatches or thin areas:

- ~~`POST /edgek/chronicle/publish` is documented and exposed through MCP tooling, but the FastAPI route is not present yet.~~ FastAPI route is present and covered by Chronicle projection tests.
- ~~Generic aliases from the whitepaper are not all present: `/edgek/quality/run`, `/edgek/pathfinder/route-card`, `/edgek/forge/decision`, and `/edgek/conductor/workflow-card` should alias current V2 endpoints or be documented as renamed.~~ These aliases are present and covered by task-envelope endpoint tests.
- ~~Chronicle projection connectors are still mostly aspirational: Jira, Linear, Notion, Confluence, Mermaid, PR-summary, and release-note publication should become governed draft/publish adapters.~~ Implemented governed draft/publish projection contracts; external writes remain connector-not-configured/dry-run by default.
- ~~CLI command aliases from the vision are incomplete: `beast diagnose`, `beast route`, `beast verify`, `beast chronicle`, and `beast promote` should wrap existing provider diagnostic, route card, quality cascade, Chronicle, and promotion endpoints.~~
- ~~Vector/RAG adapters beyond SQLite plus optional local embeddings are capability records, not active stores: pgvector, Qdrant, Chroma, and LanceDB/DuckDB/Parquet remain adapter targets.~~ Implemented active adapter-status inventory with SQLite local embeddings as the active path and pgvector/Qdrant/Chroma/LanceDB-DuckDB-Parquet as governed targets.
- ~~Route cards exist, but provider diagnostics still partially use builder logic; the route-card-driven diagnostic order should become the single source of truth.~~ Quality Cascade now exposes `route_execution` from `route_card.preferred_order`; provider diagnostics surface the same canonical execution contract.
- ~~Write-safe executor regression coverage is intentionally deferred until Nemoclaw/write bindings mature.~~ Nemoclaw now has approved `local_write` MCP regression coverage for bounded `write_file` workflows.
- ~~Tool-call interception is generated for Nginx/LiteLLM and available as `/edgek/tools/intercept`, but transparent interception still depends on clients routing through BEAST.~~ BEAST now exposes transparent-interception readiness at `/edgek/interception/transparent/state`; generated Nginx routes `/tool-calls/*`, `/v1/*`, `/proxy/<provider>/*`, and `/mcp/*` through BEAST. OS-level arbitrary process interception remains an operator/network configuration boundary.

## Outstanding Architecture Tasks

Provider gateway registry:

- ~~Create a single provider registry as the source of truth for policy, capability inventory, proxy routes, LiteLLM config, Nginx config, provider tests, UI provider pages, and MCP provider tools.~~ First registry spine is implemented in `app/kernel/provider_registry.py`; policy, capability inventory, deployment generation, proxy health, and tests now read from the same provider records. UI/MCP provider-specific surfaces can now consume the registry rather than maintaining their own list.
- ~~Keep BEAST in front of LiteLLM. LiteLLM should be a managed backend lane, not the governance layer.~~ Registry inventory and generated LiteLLM/Nginx config now state BEAST as the governance layer and LiteLLM as a managed backend lane.
- ~~Support adapter backend classes: `native_anthropic`, `native_gemini`, `native_huggingface`, `openai_compatible`, `litellm`, and `ollama`.~~ Provider records normalize these backend classes and keep legacy aliases mapped into the canonical set.
- ~~Route OpenAI-compatible clients through the BEAST governance moment before native adapters, OpenAI-compatible adapters, or LiteLLM receive traffic.~~ Compatibility `/v1/*` and generated provider-explicit `/proxy/<provider>/*` Nginx lanes point at BEAST first, with provider headers for registry-driven resolution.
- ~~Preserve three gateway lanes: compatibility `/v1/*`, provider-explicit `/proxy/<provider>/*`, and MCP governance through stdio/HTTP MCP.~~ Registry inventory exposes the three lanes for operators and generated deployment config.
- Runtime proxy status: Nginx/LiteLLM config generation is active, and BEAST now exposes registry-backed `/proxy/v1/chat/completions` plus `/proxy/<provider>/v1/chat/completions` fallback routes for LiteLLM/OpenAI-compatible providers. Native provider routes still use their mounted adapters.
- Deployment control status: BEAST can now write generated configs, dry-run/apply Nginx config and reload commands through `/edgek/deploy/nginx/apply`, and dry-run/start/stop/status a local LiteLLM sidecar through `/edgek/deploy/litellm-sidecar/*`.

PREC lifecycle:

- ~~Add first-class PREC lifecycle state for every task, tool call, route, handoff, and IDE session.~~ `app/kernel/prec_lifecycle.py` now stores append-only lifecycle records and phase events; `/edgek/prec/state`, `/edgek/prec/lifecycle`, `/edgek/prec/start`, and `/edgek/prec/update` expose the operator surface.
- ~~Map Perceive to interception, local signals, Chronicle memory, provider policy, and evidence envelopes.~~ Perceive phase snapshots compact task envelopes, provider policy hints, interception payloads, and evidence records.
- ~~Map Reason to InsightCompiler ranked insight, root cause, confidence, uncertainty, and safe next action.~~ Reason phase snapshots compact insight packets, quality reports, forge scorecards, root-cause summaries, and uncertainty/confidence where present.
- ~~Map Economize to compact context packets, selected chunks, route constraints, tool sequence, and avoid list.~~ Economize phase snapshots compact context packets, route cards, route order, recommended tool sequence, and context budget stats.
- ~~Map Crystallize to Chronicle records, route-card updates, capability signals, promotion candidates, skill confidence, and workflow cards.~~ Crystallize phase snapshots compact Chronicle writes, route-card memory, workflow cards, promotion candidates, and provider API trace crystallization.
- ~~Add cloud-handoff readiness checks requiring P complete, R complete, E complete, and C planned.~~ Handoff/task/tool endpoints now attach completed PREC lifecycle summaries, and lifecycle detail exposes phase status for readiness checks.
- ~~Proposed modules: `app/kernel/prec_lifecycle.py`, `app/kernel/prec_models.py`, `app/kernel/prec_store.py`.~~ Implemented as a single compact append-only store module: `app/kernel/prec_lifecycle.py`.
- ~~Proposed endpoints: `GET /edgek/prec/state`, `GET /edgek/prec/traces`, `GET /edgek/prec/traces/{task_id}`, `POST /edgek/prec/start`, `POST /edgek/prec/advance`, `POST /edgek/prec/crystallize`.~~ Implemented HTTP surface: `GET /edgek/prec/state`, `GET /edgek/prec/lifecycle`, `GET /edgek/prec/lifecycle/{lifecycle_id}`, `POST /edgek/prec/start`, and `POST /edgek/prec/update`.
- ~~Proposed CLI: `beast prec status`, `beast prec trace <task-id>`, `beast prec start --objective ...`, `beast prec advance <task-id> --stage reason`, `beast prec crystallize <task-id>`.~~ Implemented `beast prec status`, `beast prec list`, `beast prec trace <lifecycle-id>`, `beast prec start --objective ...`, and `beast prec advance <lifecycle-id> --phase reason`.
- ~~Add snapshot compacting for the PREC lifecycle.~~ `PRECLifecycleStore.compact_snapshot()` now produces bounded `prec_lifecycle_snapshot` packets with phase summaries, artifact refs, route constraints, compact context stats, ranked insight, crystallized memory, token estimates, hashes, and optional persistence. Exposed through `GET /edgek/prec/lifecycle/{lifecycle_id}/snapshot`, `GET /edgek/prec/lifecycle/{lifecycle_id}/snapshots`, and `beast prec snapshot <lifecycle-id>`.
- Proposed MCP tools: `beast_prec_status`, `beast_prec_trace`, `beast_prec_prepare_handoff`, `beast_prec_crystallize`.

Test Harness Stabilization Patch:

- ~~Move tests into `tests/` with `tests/conftest.py` and `tests/benchmarks/`.~~
- ~~Add pytest markers: `unit`, `api`, `cli`, `mcp`, `live`, `benchmark`, `semantic`, `integration`, and `manual`.~~
- ~~Convert localhost smoke tests to FastAPI TestClient/ASGI tests unless explicitly marked `live`.~~
- ~~Retire or mark manual MCP protocol experiments.~~
- ~~Add timeouts to all CLI subprocess tests.~~
- ~~Add `pytest.ini` with marker definitions and sane default testpaths.~~
- ~~Standard local command: `pytest -m "not live and not benchmark and not semantic and not manual" -q`.~~
- ~~Big gauntlet command: `pytest -m "live or benchmark" -q`.~~
- ~~Keep deterministic unit/API tests independent from an already-running localhost gateway.~~
- Add a CI command list in repository docs or workflow config.
- Continue splitting mixed integration files when a file contains both local and optional-environment tests.

## External Research Anchors

- Anthropic contextual retrieval: contextual chunk headers plus BM25 and embeddings.
- LangChain splitters: recursive splitting remains a reliable baseline.
- LlamaIndex node parsers: file-aware parsers and hierarchical retrieval are useful for docs/code.
- Qdrant hybrid search: dense plus sparse vectors with reciprocal rank fusion.
