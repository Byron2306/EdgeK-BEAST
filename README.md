<p align="center">
  <img src="BEAST%20mascot%20transparent.png" alt="BEAST mascot" width="520" style="max-width: 92%; height: auto;">
</p>

# BEAST — Governed Execution for Coding Agents
 
**Make coding agents safer, more efficient, and far harder to fool.**
 
BEAST sits between your coding agent, local tools, and model providers. It gives models a small, meaningful view of the repository, requires them to return bounded actions instead of uncontrolled file rewrites, compiles those actions locally, verifies the result, and records what actually worked.
 
Use it with VS Code, Cursor, Claude Code, MCP clients, OpenAI-compatible agents, local Ollama models, or your own orchestration layer.
 
> **Models propose. BEAST resolves, compiles, verifies, routes, remembers, and rolls back.**
 
---
 
## Why Coding Agents Need BEAST
 
Coding agents often fail for reasons that have little to do with raw model intelligence:
 
- They reread entire repositories to answer narrow questions
- They call every available tool because the tools exist
- They confuse provider, router, model, and authentication failures
- They return plausible JSON that violates the required schema
- They rewrite full files when a three-line anchored change would do
- They pass visible tests but fail behaviour they were not shown
- They keep moving after an unsafe patch instead of failing closed
- They treat every model as equally suitable for every role
BEAST changes the execution contract. The cloud model does not need to see everything or write everything. It needs to identify the right next action inside a governed local system.
 
---
 
## Evidence
 
### xAI Omni-Gauntlet — 24 live governed tasks
 
| Result | Outcome |
|---|---:|
| Full-BEAST verified completion | **24 / 24** |
| Provider-clean hidden-passing fixes | **13 / 24** |
| BEAST-rescued verified fixes | **11 / 24** |
| Matched raw Grok completion | **1 / 4** |
| JSON validity | **100%** |
| Schema validity | **100%** |
| Patch application | **100%** |
| Out-of-scope edits | **0%** |
| Architecture layers covered | **13 / 13** |
 
On the matched controls, BEAST raised verified completion from **25% to 100%**. Eleven governed fixes required local verifier rescue — those count as BEAST-rescued, never as clean provider success.
 
### Live provider benchmark — 216+ tasks across 21 provider routes
 
| Result | Count |
|---|---:|
| BEAST end-to-end completions | **216 / 216** |
| Clean provider completions | 41 / 216 |
| BEAST-rescued completions | 175 / 216 |
 
81% of raw provider outputs were non-compliant, malformed, or incomplete. BEAST rescued every one. Without output governance, those tasks would have silently failed or written corrupted patches.
 
Top provider fitness scores (hidden-clean rate / fitness):
 
| Provider | Hidden Clean | Fitness | Role |
|---|---|---|---|
| `xai_grok` | 54% | 0.702 | clean candidate |
| `ovhcloud` | 20% | 0.663 | candidate patch |
| `puter_deepseek` | 20% | 0.619 | candidate patch (free route) |
| `cohere` | 0% | 0.614 | candidate patch |
| `huggingface` | 0% | 0.583 | rescue-backed |
| `mistral_codestral` | 0% | 0.545 | rescue-backed |
 
### Deterministic benchmark — 10 tasks, 5 lanes
 
| Lane | Completed | Median tokens | vs raw |
|---|---|---|---|
| Raw (no BEAST) | 0 / 10 | 47,661 | — |
| Context only | 0 / 10 | 44 | −99.9% |
| RAG | 8 / 10 | 296 | −99.4% |
| RAG + Tools | 10 / 10 | 326 | −99.3% |
| **Full BEAST** | **10 / 10** | **390** | **−99.2%** |
 
Raw context hits the token budget before the model can reason about the scoped problem.
 
### Inference Compute Governor — 7-phase benchmark
 
The Compute Governor asks one question before every provider call: *what unresolved semantic work still requires probabilistic computation?*
 
All 7 phases passed on the same day:
 
| Phase | What was proved | Result |
|---|---|---|
| 1 — Shadow accounting | Receipt coverage, zero behavior change, MAE = 0.0 on token estimates | ✓ 120 paired attempts |
| 1 — Free live | Shadow agreement across Groq, Gemini, OpenRouter simultaneously | ✓ 9/9 live calls |
| 2 — Deterministic displacement | One live Groq schema\_validation call displaced by promoted transform | ✓ 131 tokens not spent |
| 3 — False reuse detection | Adversarial stale capability correctly detected and blocked | ✓ Safety rule held |
| 4 — Adaptive routing | All three rungs demonstrated: local inference, approval pause, cloud inference | ✓ Audit trail persisted |
| 5 — Streaming interception | Live Groq stream cancelled on contract completion — 80 tokens saved on one call | ✓ Repair path also proven |
| 6 — Lifecycle / confidence decay | Repository semantic change dropped confidence 0.97 → 0.485, auto-demoted in 2ms | ✓ Safety hole closed |
| 7 — Runtime reuse | Two provider calls displaced by durable replay — 140 tokens saved | ✓ KV adapter round-tripped |
 
Every phase carries an explicit `claim_boundary`. Counterfactual estimates are labelled as hypotheses until verified by controlled ablations.
 
Benchmark source files: [`benchmarks/results/`](benchmarks/results/)
 
---
 
## What BEAST Does
 
### Give agents the right context
 
BEAST builds bounded task envelopes from workspace structure, symbols, dependencies, Chronicle memory, route state, and current failures. Its workspace graph, context economiser, semantic retrieval, compression pipeline, and Ollama scout reduce duplicate reading before cloud escalation.
 
### Turn model output into safe local actions
 
Providers return typed Action IR under an output contract (`beast.action_intent.v1`). BEAST then:
 
1. validates the handoff and schema
2. rejects stale file hashes and unauthorised paths
3. resolves file and anchor references locally
4. compiles deterministic patches
5. previews selectable hunks
6. runs visible and hidden verification
7. applies only approved changes
8. preserves rollback and Chronicle evidence
Malformed, incomplete, or incorrect output is classified honestly. A locally repaired result counts as **BEAST-rescued**, never as a clean provider success.
 
### Choose providers by job, not hype
 
The Provider Economist routes by requested role, task class, output contract, hidden-clean performance, rescue rate, latency, token use, observed USD cost, and route confidence. A provider can be a patch candidate, rescue-backed Action IR generator, refs-only transform selector, scout, microtask worker, or invalid route.
 
### Stop calling tools that do not help
 
Tool Laziness learns which calls produced useful evidence in a specific scenario. Workflow-required tools always override learned skips.
 
### Make agents aware they are inside BEAST
 
Every attached agent can receive a Session Handshake containing available local help, tool-value decisions, Provider Economist selection, preflight budgets, cloud-escalation rules, and output-governance requirements. This prevents an agent from duplicating work BEAST already completed.
 
### Govern inference compute
 
The Inference Compute Governor shadows every provider call with a privacy-safe Compute Plan and Compute Receipt. It identifies deterministic and reusable work, and in later phases displaces calls that do not need probabilistic computation. Ambiguous decisions escalate — they never suppress silently.
 
### Learn without surrendering local control
 
The opt-in Meta Tool Commons exchanges privacy-safe capability evidence, not prompts or source code. Rankings remain contextual to capability version, schema hash, task class, and role. Shared candidates are advisory; local policy and explicit approval decide adoption.
 
---
 
## Capabilities
 
| Capability | What it gives a coding agent |
|---|---|
| Mirrored input/output governance | Bounded context entering the model and bounded actions leaving it |
| Action IR and local patch compiler | Small semantic intent becomes deterministic local edits |
| Provider-specific output profiles | NIM uses refs-only actions; other providers use richer contracts |
| Hidden-test-aware fitness | Distinguishes plausible patches from behaviourally correct patches |
| Clean versus rescued accounting | Measures provider capability separately from BEAST system reliability |
| Provider Economist | Selects routes by role, cost envelope, latency, rescue fit, and trust |
| Tool Laziness | Suppresses historically low-value calls without blocking required tools |
| Session Handshake | Tells external agents what BEAST already knows and enforces |
| Inference Compute Governor | Seven-phase shadow and enforcement layer over probabilistic work |
| Streaming interception | Stops generation when a complete governed object has arrived |
| Durable inference storage | Verified artifacts become reusable Semantic Compute Credits |
| Compute Forge Node | Idle machines build fingerprints and prepare handoff packets locally |
| Confidence decay | Repository change automatically demotes promoted capabilities |
| Chronicle and PREC lifecycle | Records perception, reasoning, economy, crystallisation, and outcomes |
| Meta Tool Commons | Shares schema-pinned capability priors without automatic adoption |
| GitHub PR Connector | Converts PR diffs and failed checks into governed task envelopes |
| OpenTelemetry Connector | Projects Chronicle and fitness evidence into OTLP traces |
| Plugin Marketplace | Validates risk, permissions, budgets, and tool-schema hashes |
| Quality Cascade and Forge | Language-aware syntax, test, dependency, and packaging checks |
| Responsive TUI | Live routes, fitness, plans, hunks, approvals, Chronicle, and agent state |
 
---
 
## Quick Start
 
```bash
git clone https://github.com/Byron2306/EdgeK-BEAST.git
cd EdgeK-BEAST
pip install -r requirements.txt
```

Optional (semantic RAG, large ML wheels):
```bash
curl http://127.0.0.1:8000/health
```

Optional (LiteLLM proxy support):
```bash
pip install -r requirements-litellm.txt
```

Start the gateway:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8005
```

Point your coding agent at BEAST instead of your provider directly:
```bash
# OpenAI-compatible (Cursor, Claude Code, etc.)
export OPENAI_BASE_URL=http://localhost:8005/v1

# Anthropic-compatible
export ANTHROPIC_BASE_URL=http://localhost:8005
```

---

## Provider setup

Set whichever providers you use:

```bash
export XAI_API_KEY='...'
export OPENROUTER_API_KEY='...'
export HF_TOKEN='...'
export NVIDIA_API_KEY='...'
export MISTRAL_API_KEY='...'
export COHERE_API_KEY='...'
export GEMINI_API_KEY='...'
```

BEAST will route, govern, and fall back across providers according to the fitness map. Providers you haven't configured are skipped cleanly.

---

## Key endpoints

```
# Gateway health
GET  /health
GET  /edgek/state

# BEAST Cockpit (live ops dashboard)
GET  /ui

# Inference (drop-in replacements)
POST /v1/chat/completions          # OpenAI-compatible
POST /v1/messages                  # Anthropic-compatible
POST /hf/v1/chat/completions       # HuggingFace router
POST /litellm/v1/chat/completions  # LiteLLM proxy

# Context and workspace
POST /edgek/tools/intercept        # Semantic tool-call interception
GET  /edgek/workspace              # Workspace graph state
POST /edgek/workspace/index        # Index a repository

# Budget and runtime
GET  /edgek/runtime/state
GET  /edgek/runtime/attempts
POST /edgek/runtime/circuit-breakers/{provider}/reset

# MCP broker
POST /edgek/mcp/evaluate
POST /edgek/mcp/execute
GET  /edgek/mcp/audit

# Skills and promotion
GET  /edgek/skills/promotion-candidates
POST /edgek/skills/promote

# Enterprise
POST /edgek/enterprise/teams
POST /edgek/enterprise/virtual-keys
GET  /edgek/enterprise/observability
```

Full endpoint reference in the [API docs](docs/api.md).

---

## Configuration

`policies/default.yaml` controls everything:

- Spend caps and token budgets per provider and per team
- Shell command allowlists and blocklists
- File path write restrictions
- MCP server trust levels
- Circuit breaker thresholds
- Tool laziness learning parameters

---

## Running the benchmark yourself

```bash
# Deterministic benchmark (no API calls needed)
PYTHONPATH=. python3 benchmarks/run_benchmark.py --lanes all --tasks 10

# Live provider benchmark
PYTHONPATH=. python3 benchmarks/run_live_benchmark.py --providers hf,openrouter,cohere

# Provider edge compare (cloud vs local NIM)
PYTHONPATH=. python3 benchmarks/provider_edge_compare.py --repeats 3
```

Results are written to `benchmarks/results/`.

---

## Deployment integrations

BEAST generates LiteLLM and Nginx configs directly from your active policy:

```bash
PYTHONPATH=. python3 scripts/generate_deploy_configs.py --out deploy/generated
```

Nginx routes `/tool-calls/*` into BEAST's semantic interceptor — file read requests return the top 3 relevant snippets instead of full source files.

See [deployment_integrations.md](docs/deployment_integrations.md) for the full runbook including GitHub tool calls, Postgres integration, and prompt-cache keepalive setup.

---

## What BEAST does not do

- It does not replace your LLM provider. It governs the traffic between your agent and your provider.
- It does not add latency you'll notice for most tasks. Output governance adds microseconds locally; provider latency dominates.
- It does not require a GPU. The entire governance and compilation pipeline runs on CPU.
- It does not phone home. Everything — workspace graph, budget ledger, forensic archive, skill tree — is local SQLite and append-only files.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Status

Active development. Core governance pipeline (input economy + output contracts + local verification) is stable and benchmarked. V2 roadmap focuses on the Chronicle engine, route cards, and skill promotion loop. See [BEAST_V2_ROADMAP.md](docs/BEAST_V2_ROADMAP.md).

Contributions, issues, and provider benchmark results welcome.
