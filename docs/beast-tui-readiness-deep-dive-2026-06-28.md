# BEAST TUI Readiness Deep Dive

Date: 2026-06-28

Scope: `app/cli/ui.py`, `app/cli/api.py`, `/edgek/*` snapshot dependencies, Memory Hull / Residue Seal / Agent Passport, and Crystal Reuse / LMCache / GPTCache / LiteLLM / OpenLLMetry / Langfuse / TensorZero / Promptfoo layers.

## Executive Readiness

The TUI is structurally ready for the new BEAST layers. The backend snapshot now fetches `/edgek/crystal-reuse` and `/edgek/memory-security?verify=true`; Intelligence shows the new layers as first-class operator panels; Deployment now treats them as deployable runtime infrastructure; Diagnostics now reports their live endpoint state.

Primary remaining risk: third-party service behavior is still deployment-specific. The TUI now requests optional bounded probes for configured integrations, but a green probe only proves endpoint/config reachability within the timeout. Full cache correctness, trace ingestion, TensorZero optimization behavior, and Promptfoo eval execution still require integration-specific acceptance tests.

## Snapshot Pipeline

The TUI source of truth is `BeastApiClient.snapshot()` in `app/cli/api.py`. It concurrently gathers gateway, proxy, MCP, provider registry, provider adapters, PREC state, LiteLLM config, Nginx config, Chronicle, route cards, insights, handoff precheck, telemetry, runtime metrics, session handshake, commons state, tool laziness, plugins, swarm, Ollama, KV cache, compute, crystal compute, proof-local pages, commons spaces/economy/policy, and the two new systems:

| Snapshot field | Endpoint | TUI consumers |
| --- | --- | --- |
| `crystal_reuse` | `/edgek/crystal-reuse` | Intelligence, Deployment, Diagnostics, Economy, Session turn events, selected item detail |
| `crystal_integration_health` | `/edgek/crystal-reuse/integrations?probe=true&timeout_seconds=0.45` | Intelligence, Deployment, Diagnostics, Settings |
| `memory_security` | `/edgek/memory-security?verify=true` | Intelligence, Deployment, Diagnostics, selected item detail |

Failure behavior is acceptable: endpoint errors are captured into `snap.errors`, and pages render fallback rows instead of crashing.

## Page-by-Page Readiness

| Page | Shows data? | New layer coverage | Readiness |
| --- | --- | --- | --- |
| Mission | Yes. Uses provider counts, PREC phases, evidence, commons, KV cache, swarm, Ollama, OpenClaw, economist, tool laziness. | Indirect only through `intelligence_summary`: crystal reuse and memory security are summarized but not highlighted. | Ready for cockpit overview; not the detailed view for new layers. |
| Session | Yes. Shows session state, provider route, context files, patch plans, approvals, output gate, handoff, agent awareness, economist, tool skips, and per-turn crystal reuse decisions. | Direct inline event: `crystal_reuse_decision_id`, action, source, confidence; reusable answers can skip provider execution. | Ready. |
| PREC | Yes. Shows lifecycle rows, selected trace, counts. | No direct crystal/memory panel. | Ready. PREC is workflow-state focused; crystal reuse appears later in Intelligence/Chronicle/Economy. |
| Routing | Yes. Shows provider adapters, backend classes, route resolution, proxy path, model. | LiteLLM visible through adapter/fabric; crystal reuse not directly shown. | Ready. Could later add a pre-provider reuse lane, but current placement is acceptable. |
| Providers | Yes. Shows provider health, route, base URL, model counts, policy, secret state, fitness artifact, fallback. | LiteLLM visible as provider gateway. | Ready. Public cache/trace/eval integrations belong in Deployment/Diagnostics, not provider selection. |
| Capabilities | Yes. Shows capabilities or promotion candidates, confidence, source, status, family distribution, action buttons. | Crystal capability can appear when present in capability inventory. | Ready. Promotion semantics remain advisory. |
| Swarm | Yes. Shows swarm profiles/runs/governance, commons candidates, evidence plane, OpenClaw/Ollama/KV signals. | KV cache visible; crystal reuse not yet a swarm action row. | Ready. Future work: stage crystal export/reuse candidates into swarm evidence plane. |
| Intelligence | Yes. Strongest new-layer coverage. Shows semantic pages, distillation, KV cache, compute, commons, crystal reuse metrics, public integration table, and Memory Hull / Residue Seal / Agent Passport panel. | Full first-class display. | Ready. This is the operator explanation page for BEAST memory and crystal reuse. |
| Spaces | Yes. Shows compute spaces, registry, policy recommendation, evaluation, scale proof density, tiered credit pricing, marketplace gates. | Indirect: spaces consume crystals and signed evidence. | Ready. Claim boundary remains shadow/non-financial unless live reproduction evidence exists. |
| Economy | Yes. Shows rollout actions, token/stream economy, compute receipts, savings, proof density, latest mega artifact, crystal reuse saved tokens, and provider calls avoided. | Direct crystal reuse savings and hit count. | Ready. |
| Chronicle | Yes. Shows records, task type, provider, category, confidence, memory candidate, Memory Hull verification, sidecar path, and summary. | Direct Memory Hull sidecar status when Chronicle rows originate from or match Memory Hull residue. | Ready. |
| Deployment | Yes. Now shows Nginx, LiteLLM, crystal reuse gateway, crystal integrations, memory security, provider adapters, and secrets. Adds a dedicated Crystal + Memory Layers panel. | Full deployment-surface coverage. | Ready after current patch. |
| Diagnostics | Yes. Now includes crystal reuse gateway, crystal integrations, crystal KV transport, Memory Hull, Residue Seal, and Agent Passport rows. | Full health-surface coverage. | Ready after current patch. |
| Settings | Yes. Shows gateway URL, workspace, backend mode, handoff, capability/provider counts, integration config count, integration probe attempts, and sprite mode. | Read-only integration configuration/probe summary. | Ready. |

## Detailed New-Layer Data Checks

| Layer | TUI field path | Expected visible signal |
| --- | --- | --- |
| Crystal Reuse Gateway | `snap.crystal_reuse.storage` | active credits, total credits, reuse hit count, measured saved tokens |
| KV Transport | `snap.crystal_reuse.kv_transport` and `snap.kv_cache_state` | total KV blocks, operations logged |
| LMCache/GPTCache/LiteLLM/OpenLLMetry/Langfuse/TensorZero/Promptfoo | `snap.crystal_reuse.integration_health.integrations` | integration count, configured count, project rows, role, capability flags |
| Integration live probes | `snap.crystal_reuse.integration_health.integrations[*].live_probe` | `ready`, `not_configured`, `configured_unverified`, `unreachable`, or probe error reason |
| Memory Hull | `snap.memory_security.memory_hull` | vault root, verified sidecars, failed sidecars |
| Residue Seal | `snap.memory_security.residue_seal` | key existence and key mode |
| Agent Passport | `snap.memory_security.agent_passport.policy_lint` | policy validity and policy count |

## What Is Working Now

- Every TUI page has a render method and fallback rows.
- Snapshot loading is tolerant of missing endpoints.
- Intelligence renders the new BEAST layers in two dedicated panels.
- Deployment now shows crystal/memory layers beside Nginx, LiteLLM, providers, and secrets.
- Diagnostics now exposes the live health of crystal reuse, integrations, KV transport, Memory Hull, Residue Seal, and Agent Passport.
- Settings now includes read-only integration configuration and probe attempt counts.
- Session turn events now include crystal reuse decision id, action, source, and confidence before provider execution.
- Economy now isolates crystal reuse saved tokens and provider calls avoided.
- Chronicle now shows Memory Hull sidecar verification fields for memory candidate records.
- Keyboard page row counts were updated so Deployment selection matches the new rows.
- The new mammoth gauntlet renders all TUI pages from a synthetic full snapshot and asserts the new layer panels appear.

## Remaining Gaps and Follow-Ups

| Gap | Impact | Suggested next step |
| --- | --- | --- |
| Integration probes are reachability checks, not semantic acceptance tests | A service can respond but still reject BEAST payload semantics. | Add service-specific acceptance probes for LMCache KV restore, GPTCache semantic lookup, Langfuse ingestion, TensorZero feedback, and Promptfoo eval execution. |
| Session inline event is text-first | Operators see the decision, but cannot yet open the full sealed decision payload from the Session page. | Add a selectable crystal decision detail modal. |
| Chronicle sidecar matching is best-effort | Rows without residue ids rely on task/summary matching. | Persist `memory_hull_residue_id` when promoting Chronicle records from Memory Hull. |

## Readiness Verdict

TUI readiness is green for local BEAST visibility and yellow-green for third-party service assurance. The console now shows the memory/hull/seal/passport layer and the crystal reuse integration layer in the right operator locations, includes bounded live probes, surfaces per-turn crystal decisions, isolates reuse savings, and displays Memory Hull sidecar status. The remaining work is service-specific acceptance probing and richer detail modals.
