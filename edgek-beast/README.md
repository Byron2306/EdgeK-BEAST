# EdgeK BEAST Gateway

Governed local AI execution broker for agentic coding - emphasizing budgeted, observable, tool-aware, and context-efficient workflows.

## Overview

EdgeK BEAST (Broker for Efficient Agentic Systems and Tooling) is a governed MCP (Model Context Protocol) and LLM gateway designed for token-efficient agentic coding workflows. It implements the five architectural commitments:

1. **Protocol Unification** - Single gateway for multiple LLM providers
2. **Context Economy** - 10-stage context compression pipeline
3. **MCP Tool Governance** - Trust levels, budgeting, and poisoning defense
4. **Runtime Control** - Stasis wall, circuit breakers, timeout budgeting
5. **Forensic Observability** - Comprehensive tracing and metrics

## Implemented Phases

### Phase 1: Minimal Gateway Implementation

This phase establishes the foundation with:
- OpenAI-compatible API endpoints
- Anthropic-compatible API endpoints  
- Basic request/response handling
- Health checks and logging
- Policy configuration framework

### Phase 2: Budget/Rate Control

The reason phase now enforces request, cost, RPM, and TPM budgets using a SQLite-backed ledger in `data/budget.db`. Deferrals include retry metadata and `Retry-After` headers, and cost estimates use provider pricing from policy.

### Phase 3: Context Economizer

Oversized requests now pass through a deterministic context economizer before governance. It preserves system messages and recent turns, trims long message bodies, omits older middle context when needed, records budget-fit status, and writes context-economy metadata into traces and telemetry.

### Phase 4: Workspace Graph

Crystallization now updates a queryable SQLite workspace graph in `data/workspace_graph.db`, with nodes and edges for sessions, traces, providers, models, policies, context-economy events, file paths, directories, repositories, and lightweight Python symbols. The graph can be indexed from repositories, rebuilt from trace archives, searched, traversed by neighborhood, exported as a bounded graph snapshot, checked for integrity, and consulted by the reason phase when a request mentions known graph nodes.

### Phase 5: MCP Broker

MCP/tool requests can now be evaluated against `mcp_server_classes` policy. The broker classifies requests, applies trust/approval/budget policy, checks shell allow/deny lists, applies file-operation policy, records audit and execution events, creates pending approvals for gated requests, and supports constrained execution for local read-only file reads and approved policy-allowed shell commands.

### Phase 6: Runtime Governance

Provider execution now passes through a runtime governor with stasis-wall concurrency admission, provider-specific concurrency and timeout settings, provider circuit breakers, timeout wrapping, stale-attempt lease cleanup, runtime integrity checks, and a durable execution-attempt ledger in `data/runtime.db`.

### Phase 7: Skill Tree & Meta-Tools

Successful traces and supplied tool sequences can now be mined into repeated sequence patterns, converted into meta-tool candidates, validated in a sandbox validator, and promoted through a user-approval gate into the skill registry. Phase 7 state uses `data/skills.db` for learned skills, sequence patterns, meta-tool candidates, and validation history, while `data/traces.db` remains available for explicit execution-trace mining.

### Phase 8: Swarm Kernel

The gateway now includes a deterministic internal swarm kernel backed by `data/swarm.db`. It runs a role-based state machine with Conductor, Sentinel, Cartographer, Compressor, Supervisor, Critic, and Archivist events; applies deterministic approval and destructive-action gates; invokes the critic only for failure/high-risk/model-critic requests; and records measurable value logs for token savings, avoided model calls, and blocked risk.

### Phase 9: Team/Enterprise Mode

The gateway now includes a local enterprise control plane backed by `data/enterprise.db`. It supports teams, users, scoped virtual keys, per-team request and cost budgets, centralized observability events, OTLP-like JSON export, policy pack registration and team assignment, and sealed trace storage with integrity checks.

### L3/L4 Crystallization Foundation

Completed interactions are now crystallized into:
- `data/traces.jsonl` for append-only forensic trace storage
- `data/trace_index.db` for trace and workspace-interaction indexing
- `data/skills.db` for learned request-routing/governance skills

## Project Structure

```
edgek-beast/
├── app/
│   ├── __init__.py
│   ├── main.py              # Main FastAPI application
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── openai_adapter.py    # OpenAI-compatible endpoints
│   │   └── anthropic_adapter.py # Anthropic-compatible endpoints
│   └── (future: kernel, context, mcp, telemetry, data modules)
├── policies/
│   └── default.yaml         # L0 meta rules and governance settings
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # (future) Docker deployment
└── README.md                # This file
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   The core install includes `tree-sitter-language-pack`, which enables
   multi-language syntax indexing on Python 3.13. Semantic embedding/RAG
   dependencies are intentionally separate because they pull large ML wheels:
   ```bash
   pip install -r requirements-semantic.txt
   ```
   LiteLLM proxy support is optional:
   ```bash
   pip install -r requirements-litellm.txt
   ```
   Required tool-call integrations use:
   ```bash
   pip install -r requirements-integrations.txt
   ```

## Running the Gateway

Start the gateway server:
```bash
python -m app.main
```

The server will be available at:
- http://localhost:8000

## API Endpoints

### Health Check
```
GET /health
```

### Gateway State
```
GET /edgek/state
GET /edgek/benchmarks/comparative
POST /edgek/benchmarks/comparative
GET /edgek/benchmarks/gauntlet
POST /edgek/benchmarks/gauntlet
POST /v1beta/models/{model}:generateContent
POST /v1/models/{model}:generateContent
POST /hf/v1/chat/completions
POST /huggingface/v1/chat/completions
POST /tgi/v1/chat/completions
POST /llamacpp/v1/chat/completions
POST /litellm/v1/chat/completions
GET  /edgek/providers/state
POST /edgek/tools/intercept
GET  /edgek/tools/integrations
POST /edgek/compression/prune
GET  /edgek/ollama/status
POST /edgek/ollama/packet
POST /edgek/ollama/scout
```

### BEAST Cockpit
```
GET /ui
```

The cockpit is a hosted HTML operations deck with live budget, runtime, memory graph,
MCP audit, enterprise observability, control actions, and gated versus non-gated
comparative benchmark results.

### Edge Runtime Modules
```
GET  /edgek/os-bypass/capabilities
POST /edgek/os-bypass/af-packet/probe
POST /edgek/os-bypass/dpdk/probe
POST /edgek/os-bypass/af-xdp/probe
POST /edgek/compression/json
POST /edgek/compression/python
POST /edgek/isolation-forest/predict
POST /edgek/tool-laziness/record
GET  /edgek/tool-laziness/recommend
POST /edgek/tool-laziness/benchmark
POST /edgek/tool-laziness/schema-benchmark
GET  /edgek/deploy/litellm-config
GET  /edgek/deploy/litellm-config.yaml
GET  /edgek/deploy/nginx-config
POST /edgek/deploy/write-configs
GET  /edgek/prompt-cache/state
GET  /edgek/prompt-cache/keepalives
POST /edgek/prompt-cache/keepalives
POST /edgek/prompt-cache/tick
GET  /edgek/prompt-cache/events
```

The OS-bypass module exposes host capability checks and an AF_PACKET TPACKET_V3
mmap packet-ring probe. DPDK and AF_XDP probe native userspace libraries when
available. The compression module supports lossless JSON schema-row compression
and semantic Python AST compression. The Isolation Forest module provides
deterministic edge outlier scoring without a scikit-learn dependency. The
tool-laziness learner records tool/provider outcomes and learns when redundant
calls should be skipped.

The schema benchmark measures the original BEAST "Tool Tax" claim by comparing
static all-tools MCP schema injection against lazy, intent-selected tool schema
exposure over a high-token multi-turn coding session.

Deployment helpers generate LiteLLM and Nginx integration files from BEAST
policy:

```bash
PYTHONPATH=. python3 scripts/generate_deploy_configs.py --out deploy/generated
```

Prompt-cache keepalives are explicit and auditable. Registrations require
`authorized: true`; ticks are dry-run by default unless a registration disables
dry-run and the tick call passes `allow_network: true`.

See `docs/deployment_integrations.md` for the LiteLLM, Nginx, and keepalive
runbook.

Live provider environment variables:

```bash
export GEMINI_API_KEY='...'
export HF_TOKEN='...'
export HF_INFERENCE_BASE_URL='https://router.huggingface.co/v1'
export TGI_BASE_URL='http://127.0.0.1:3000'
export LITELLM_BASE_URL='http://127.0.0.1:4000/v1'
export GITHUB_TOKEN='...'
export POSTGRES_DSN='postgresql://user:pass@host:5432/dbname'
```

The Hugging Face adapter uses the OpenAI-compatible Hugging Face router by
default. The TGI adapter targets a local or remote Text Generation Inference
server, including the llama.cpp backend. The LiteLLM adapter targets a running
LiteLLM proxy but still enters through BEAST for governance, compression,
runtime controls, tool-laziness, and forensics.

Tool-call interception is a required BEAST integration surface. Nginx can route
`/tool-calls/*` to `/edgek/tools/intercept`; LiteLLM receives an
`edgek_tool_interceptor` MCP server entry. File-read requests can be swapped
from full source files into the top semantic snippets from the workspace graph
or deterministic semantic grep. Required integration readiness is reported at
`/edgek/tools/integrations` for GitHub, Postgres, RTK, sqz, LongCodeZip,
RepoRelay, and the semantic interceptor.

### Ollama Scout Layer

BEAST can sit around Ollama as a local scout:

```
User task -> BEAST context tools -> compact handoff packet -> Ollama scout
          -> BEAST executes next step or escalates to cloud/NIM/API
```

Use:

```bash
curl -sS http://127.0.0.1:8000/edgek/ollama/status
curl -sS -X POST http://127.0.0.1:8000/edgek/ollama/scout \
  -H 'Content-Type: application/json' \
  -d '{"task":"Find why login token refresh test fails","context_limit":6,"tool_limit":5}'
```

BEAST does deterministic retrieval first: semantic chunks, tree-sitter/workspace
symbols, compact Postgres schema, GitHub availability, and a tiny tool menu.
Ollama receives that packet and returns structured JSON for task type, risk,
privacy level, relevant files, and needed tools. If Ollama is installed but the
daemon/model is unavailable, BEAST still returns a deterministic fallback packet.

On Debian/Ubuntu hosts, install native DPDK/AF_XDP libraries with:

```bash
sudo ./scripts/install_native_os_bypass_deps.sh
```

Library installation is only the first step for packet IO. DPDK still needs
hugepages plus a vfio/uio-bound NIC. AF_XDP still needs kernel/NIC support and
CAP_NET_ADMIN/CAP_BPF or equivalent permissions.

Operational setup details are in `docs/edge_runtime_setup.md`. The conservative
host configurator is dry-run by default:

```bash
./scripts/configure_os_bypass_host.sh
HUGEPAGES=1024 ./scripts/configure_os_bypass_host.sh --apply
```

To contrast cloud APIs against a local NVIDIA NIM deployment running on an edge
GPU, point the provider benchmark at any OpenAI-compatible NIM endpoint:

```bash
export LOCAL_NIM_BASE_URL='http://<edge-gpu-host>:8000/v1'
export LOCAL_NIM_MODEL='<model-served-by-local-nim>'
PYTHONPATH=. python3 benchmarks/provider_edge_compare.py --dry-run
PYTHONPATH=. python3 benchmarks/provider_edge_compare.py --repeats 3
```

The generated `benchmarks/results/provider_edge_compare.*` reports compare raw
provider calls with BEAST-governed calls using Isolation Forest filtering,
context economy, and AST/schema-row compression.

### Workspace Graph
```
GET /edgek/workspace
POST /edgek/workspace/index
POST /edgek/workspace/rebuild
GET /edgek/workspace/export
GET /edgek/workspace/integrity
GET /edgek/workspace/search?q=reason.py&node_type=file
GET /edgek/workspace/nodes/file:app/kernel/reason.py
```

### MCP Broker
```
POST /edgek/mcp/evaluate
POST /edgek/mcp/execute
GET  /edgek/mcp/state
GET  /edgek/mcp/audit
GET  /edgek/mcp/executions
GET  /edgek/mcp/servers
POST /edgek/mcp/servers
GET  /edgek/mcp/approvals
GET  /edgek/mcp/approvals/{request_id}
POST /edgek/mcp/approvals/{request_id}/approve
POST /edgek/mcp/approvals/{request_id}/deny
```

### Runtime Governance
```
GET  /edgek/runtime/state
GET  /edgek/runtime/attempts
GET  /edgek/runtime/attempts/{attempt_id}
GET  /edgek/runtime/integrity
POST /edgek/runtime/sweep
POST /edgek/runtime/circuit-breakers/{provider}/reset
```

### Skill Tree & Meta-Tools
```
GET  /edgek/skills/state
GET  /edgek/skills
POST /edgek/skills/mine
GET  /edgek/skills/patterns
POST /edgek/skills/candidates/generate
GET  /edgek/skills/candidates
GET  /edgek/skills/candidates/{candidate_id}
POST /edgek/skills/candidates/{candidate_id}/validate
GET  /edgek/skills/candidates/{candidate_id}/validations
POST /edgek/skills/candidates/{candidate_id}/promote
```

### Swarm Kernel
```
GET  /edgek/swarm/state
POST /edgek/swarm/run
GET  /edgek/swarm/runs
GET  /edgek/swarm/runs/{run_id}
GET  /edgek/swarm/value
```

### Team/Enterprise Mode
```
GET  /edgek/enterprise/state
POST /edgek/enterprise/teams
GET  /edgek/enterprise/teams
GET  /edgek/enterprise/teams/{team_id}
POST /edgek/enterprise/users
POST /edgek/enterprise/virtual-keys
POST /edgek/enterprise/auth/verify
GET  /edgek/enterprise/teams/{team_id}/budget
POST /edgek/enterprise/teams/{team_id}/budget/check
POST /edgek/enterprise/usage
POST /edgek/enterprise/observability
GET  /edgek/enterprise/observability
GET  /edgek/enterprise/otel
POST /edgek/enterprise/policy-packs
GET  /edgek/enterprise/policy-packs
POST /edgek/enterprise/teams/{team_id}/policy-packs/{pack_id}
GET  /edgek/enterprise/teams/{team_id}/policy
POST /edgek/enterprise/traces/encrypted
GET  /edgek/enterprise/teams/{team_id}/traces/{trace_id}
```

### Root Information
```
GET /
```

### OpenAI-Compatible Endpoints
```
GET  /v1/models
POST /v1/chat/completions
POST /v1/completions
```

### Anthropic-Compatible Endpoints
```
POST /v1/messages
```

## Configuration

Policy configuration is located in `policies/default.yaml`. This file contains:
- Meta rules (L0 layer)
- Provider configurations
- MCP server classes and trust levels
- File operation policies
- Queue policy options
- Swarm design configuration
- Team/enterprise configuration
- Skill tree configuration
- Forensic archive settings (L4 layer)

## Next Phases

Following the implementation roadmap from the whitepaper:
- Phase 4: Workspace Graph (completed)
- Phase 5: MCP Broker (completed)
- Phase 6: Runtime Governance (completed)
- Phase 7: Skill Tree & Meta-Tools (completed)
- Phase 8: Swarm Kernel (completed)
- Phase 9: Team/Enterprise Mode (completed)

## Enhanced Features (Beyond Original Roadmap)

### True Semantic Vector/RAG File-Read Interception
- Added optional semantic embedding storage and retrieval using `sentence-transformers`
- CPU-only semantic install is supported with `torch` from the PyTorch CPU wheel index
- `/edgek/workspace/semantic-index` builds chunk embeddings for workspace RAG
- `/edgek/workspace/semantic-context` returns compact memory/forensics context by meaning
- MCP `read_file` responses can include semantically related chunks for smarter read-loop avoidance
- Tool laziness can blend learned skip/call history with semantic workspace evidence
- Swarm cartography now shares compact semantic context chunks instead of rereading broad files
- `/edgek/semantic/dedupe` collapses exact and semantic repeated payloads before token spend

### Tree-sitter Parser Integration
- Active multi-language Tree-sitter parser support through `tree-sitter-language-pack`
  for Python, JavaScript, TypeScript, Java, C, C++
- Enhanced symbol extraction beyond Python AST to support multiple languages
- Language-aware symbol indexing in the workspace graph
- Fallback to regex-based extraction when Tree-sitter is not available

## License

MIT License - see LICENSE file for details.
