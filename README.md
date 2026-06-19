<p align="center">
  <img src="BEAST%20mascot.png" alt="BEAST mascot" width="240">
</p>

# EdgeK BEAST

**Governed output gateway for agentic coding tools.**

BEAST sits between your AI coding agent (Cursor, Claude Code, VS Code Copilot) and any LLM provider. It governs what goes *in* and what comes *out* — enforcing output contracts, repairing non-compliant patches before they touch your filesystem, and learning which tool calls are worth making.

---

## Why this exists

AI coding agents are not careful. They read entire files when they need three lines. They write to paths they shouldn't. They spend your token budget on redundant lookups. When a provider returns malformed JSON, they fail silently or corrupt your code.

BEAST intercepts both sides:

- **Input governance** — context compression, tool laziness learning, budget enforcement, circuit breakers
- **Output governance** — every model response is parsed against a typed output contract (`beast.action_intent.v1`) before anything touches disk. Non-compliant patches are repaired locally and verified. If verification fails, nothing is written.

---

## Benchmark results

### Deterministic — 10 tasks, 5 lanes

| Lane | Completed | Median tokens | vs raw |
|---|---|---|---|
| Raw (no BEAST) | 0 / 10 | 47,661 | — |
| Context only | 0 / 10 | 44 | −99.9% |
| RAG | 8 / 10 | 296 | −99.4% |
| RAG + Tools | 10 / 10 | 326 | −99.3% |
| **Full BEAST** | **10 / 10** | **390** | **−99.2%** |

Raw context hits the token budget before the model can reason about the scoped problem. BEAST completes 100% of tasks at under 400 tokens, verified by passing pytest suites.

### Live providers — 192 tasks across 20 provider routes

| Result | Count |
|---|---|
| BEAST end-to-end completions | **192 / 192** |
| Clean provider completions | 36 / 192 |
| BEAST-rescued completions | 156 / 192 |

79% of raw provider outputs were non-compliant, malformed, or incomplete. BEAST rescued every one of them. Without output governance, those 156 tasks would have silently failed or written corrupted patches.

### Provider fitness ranking

| Rank | Provider | Role | Clean | Fitness | Latency |
|---|---|---|---|---|---|
| 1 | `ovhcloud` | candidate patch provider | 5/10 | 0.663 | 14s |
| 2 | `puter_deepseek` | candidate patch (high latency) | 4/10 | 0.619 | 13s |
| 3 | `cohere` | candidate patch provider | 4/10 | 0.614 | 6.7s |
| 4 | `deepinfra` | candidate patch (high latency) | 4/10 | 0.612 | 32s |
| 5 | `huggingface` | rescue-backed action IR | 3/10 | 0.583 | 1.6s |
| 6 | `nscale` | rescue-backed action IR | 3/10 | 0.581 | 7.8s |
| 7 | `mistral` | rescue-backed (Codestral) | 2/10 | 0.545 | 4.1s |
| 8 | `openrouter` | fast rescue-backed action IR | 2/10 | 0.544 | 3.8s |
| 9 | `sambanova` | fast rescue-backed action IR | 1/10 | 0.512 | 3.0s |
| 10 | `cloudflare` | edge / microtask | 1/10 | 0.483 | 2.1s |
| 11–14 | `cerebras`, `featherless`, `nvidia_nim`, `gemini` | scout / selector | 0–2/10 | 0.33–0.42 | varies |
| 15–16 | `groq`, `llm7` | scout only | 0/10 | 0.23 | fast |
| 17–18 | `aion_labs`, `novita` | rate-limited / rescue | 1/10 | 0.39–0.51 | varies |
| 19–20 | `hyperbolic`, `fal` | do not use (auth/billing) | 0/10 | — | — |

**Notable findings:**
- **Puter-routed DeepSeek** achieved 4 clean passes on a free proxied route — matching paid providers. BEAST can make unconventional free routes production-viable through governance.
- **LLM7** returned valid JSON on 100% of tasks but passed the output schema on only 10%. Without an output governor, it looks like it's working. It isn't.
- **NVIDIA NIM** failed the output contract on every task. BEAST repaired and rescued both targeted tasks. Zero silent failures.
- **DeepInfra** observed cost: ~$0.000332 per verified, governed code fix.

---

## Architecture

```
Coding agent (Cursor / Claude Code / VS Code)
        │
        ▼
┌─────────────────────────────────────────┐
│              BEAST Gateway              │
│                                         │
│  Input side          Output side        │
│  ─────────           ───────────        │
│  Context economy     Output contract    │
│  Tool laziness       Local verifier     │
│  Budget ledger       Patch compiler     │
│  Circuit breakers    Anchor resolver    │
│  Workspace graph     Repair engine      │
│  MCP broker          Sandbox validator  │
│                                         │
│  Memory: L0 policy → L4 forensic archive│
└─────────────────────────────────────────┘
        │
        ▼
  Any LLM provider (20+ tested)
```

### The output governance loop

Every model response passes through:

1. **Contract parse** — response must conform to `beast.action_intent.v1`
2. **Anchor resolution** — `anchor_ref` fields resolve to exact code locations; no copy-paste writes
3. **Path validation** — writes outside allowed paths are rejected before compilation
4. **Local patch compile** — `ActionIR` → `ResolvedAction` → staged file writes
5. **Sandbox verification** — compiled patches run against pytest before disk commit
6. **Repair** — if verification fails, the local verifier attempts repair before giving up
7. **Forensic record** — every outcome (clean, repaired, rejected) is written to the Chronicle

Provider-specific output profiles handle model quirks: NVIDIA NIM gets `refs_only=True`; HuggingFace gets `repair_attempts=2`.

### Memory layers

| Layer | Name | Contents |
|---|---|---|
| L0 | Meta Rules | Spend caps, shell allowlists, blocked paths — immutable |
| L1 | Insight Index | Session state, cache handles, circuit state |
| L2 | Workspace Graph | Symbol maps, dependency edges, semantic chunks |
| L3 | Skill Tree | Promoted, verified workflows and route cards |
| L4 | Forensic Archive | Append-only Chronicle — every request, every outcome |

---

## Installation

```bash
git clone https://github.com/yourusername/edgek-beast
cd edgek-beast
pip install -r requirements.txt
```

Optional (semantic RAG, large ML wheels):
```bash
pip install -r requirements-semantic.txt
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
export HF_TOKEN='...'
export HF_INFERENCE_BASE_URL='https://router.huggingface.co/v1'
export OPENROUTER_API_KEY='...'
export GEMINI_API_KEY='...'
export NVIDIA_API_KEY='...'
export COHERE_API_KEY='...'
export MISTRAL_API_KEY='...'
# Local
export LOCAL_NIM_BASE_URL='http://localhost:8000/v1'
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
