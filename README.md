<p align="center">
  <img src="BEAST%20mascot%20transparent.png" alt="BEAST mascot" width="520" style="max-width: 92%; height: auto;">
</p>

# BEAST - Governed Execution for Coding Agents

**Make coding agents safer, more efficient, and far harder to fool.**

BEAST sits between your coding agent, local tools, and model providers. It gives models a small, meaningful view of the repository, requires them to return bounded actions instead of uncontrolled file rewrites, compiles those actions locally, verifies the result, and records what actually worked.

Use it with VS Code, Cursor, Claude Code, MCP clients, OpenAI-compatible agents, local Ollama models, or your own orchestration layer.

> **Models propose. BEAST resolves, compiles, verifies, routes, remembers, and rolls back.**

## Why Coding Agents Need BEAST

Coding agents often fail for reasons that have little to do with raw model intelligence:

- They reread entire repositories to answer narrow questions.
- They call every available tool because the tools exist.
- They confuse provider, router, model, and authentication failures.
- They return plausible JSON that violates the required schema.
- They rewrite full files when a three-line anchored change would do.
- They pass visible tests but fail behavior they were not shown.
- They keep moving after an unsafe patch instead of failing closed.
- They treat every model as equally suitable for every role.

BEAST changes the execution contract. The cloud model does not need to see everything or write everything. It needs to identify the right next action inside a governed local system.

## What BEAST Does

### Give Agents the Right Context

BEAST builds bounded task envelopes from workspace structure, symbols, dependencies, Chronicle memory, route state, and current failures. Its workspace graph, context economizer, semantic retrieval, compression pipeline, and Ollama scout reduce duplicate reading before cloud escalation.

### Turn Model Output into Safe Local Actions

Providers return typed Action IR under an output contract such as `beast.action_intent.v1`. BEAST then:

1. validates the handoff and schema;
2. rejects stale file hashes and unauthorized paths;
3. resolves file and anchor references locally;
4. compiles deterministic patches;
5. previews selectable hunks;
6. runs visible and hidden verification;
7. applies only approved changes;
8. preserves rollback and Chronicle evidence.

Malformed, incomplete, or incorrect output is classified honestly. A locally repaired result counts as **BEAST-rescued**, never as a clean provider success.

### Choose Providers by Job, Not Hype

The Provider Economist routes by:

- requested role;
- task class and output contract;
- hidden-clean performance;
- rescue rate;
- latency and token use;
- observed USD cost;
- route and authentication confidence.

A provider can be a patch candidate, rescue-backed Action IR generator, refs-only transform selector, scout, microtask worker, or invalid route. BEAST does not flatten those roles into a model leaderboard.

### Stop Calling Tools That Do Not Help

Tool Laziness learns which calls produced useful evidence in a specific scenario. OpenClaw and other attached agents consume explicit call, skip, and learn-more decisions. Workflow-required tools always override learned skips.

### Make Agents Aware They Are Inside BEAST

Every attached agent can receive a Session Handshake containing:

- available local help;
- tool-value decisions;
- Provider Economist selection;
- preflight and Ollama scout budgets;
- cloud-escalation rules;
- output-governance and rollback requirements.

This prevents an agent from duplicating work BEAST already completed. See [Agent Awareness](docs/agent-awareness.md).

### Learn Without Surrendering Local Control

The opt-in Meta Tool Commons exchanges privacy-safe capability evidence, not prompts or source code. Rankings remain contextual to capability version, schema hash, task class, and role. Shared candidates are advisory; local policy and explicit approval decide whether a skill or meta-tool is adopted.

See [Meta Tool Commons](docs/meta-tool-commons.md).

## Capabilities That Are Unusual in One System

| Capability | What it gives a coding agent |
| --- | --- |
| Mirrored input/output governance | Bounded context entering the model and bounded actions leaving it |
| Action IR and local patch compiler | Small semantic intent becomes deterministic local edits |
| Provider-specific output profiles | NIM can use refs-only actions while other providers use richer contracts |
| Hidden-test-aware fitness | Distinguishes plausible patches from behaviorally correct patches |
| Clean versus rescued accounting | Measures provider capability separately from BEAST system reliability |
| Provider Economist | Selects routes by role, cost envelope, latency, rescue fit, and trust |
| Tool Laziness | Suppresses historically low-value calls without blocking required tools |
| Session Handshake | Tells external agents what BEAST already knows and enforces |
| Inference Compute Governor | Shadow-plans probabilistic work and measures each provider call without changing behavior |
| Chronicle and PREC lifecycle | Records perception, reasoning, economy, crystallization, verification, and outcomes |
| Meta Tool Commons | Shares schema-pinned capability priors without universal rankings or automatic adoption |
| Network Chronicle | Attaches payload-free packet timing evidence to route diagnostics |
| GitHub PR Connector | Converts PR diffs, failed checks, and review comments into governed task envelopes |
| OpenTelemetry Connector | Projects Chronicle, route, packet, and fitness evidence into OTLP traces |
| Extension Marketplace | Validates plugin risk, permissions, budgets, approvals, and tool-schema hashes |
| Quality Cascade and Forge | Runs language-aware syntax, tests, dependency, documentation, extension, and packaging checks |
| Responsive TUI | Exposes routes, fitness, plans, hunks, approvals, Chronicle, Commons, and live agent decisions |

## Evidence, Not a Perfect-Model Story

The latest xAI Omni-Gauntlet exercised 24 live governed tasks, four matched raw controls, 13 local subsystem groups, and 13 architecture layers.

| Result | Outcome |
| --- | ---: |
| Full-BEAST verified completion | **24/24** |
| Provider-clean hidden-passing fixes | **13/24** |
| BEAST-rescued verified fixes | **11/24** |
| Matched raw Grok completion | **1/4** |
| JSON validity | **100%** |
| Schema validity | **100%** |
| Patch application | **100%** |
| Out-of-scope edits | **0%** |
| Syntax errors | **0%** |
| Timeouts | **0%** |
| Architecture layers covered | **13/13** |

On the matched controls, BEAST raised verified completion from **25% to 100%**. That does not mean Grok independently solved every task: eleven governed fixes required local verifier rescue, and the live rollback task failed the provider-clean rollback gate.

The evidence package includes every task definition, hidden test, provider response classification, patch, repair record, JUnit result, relevant implementation source, git state, SHA-256 manifest, and secret scan.

- [Comprehensive xAI summary](benchmarks/results/beast_xai_omni_comprehensive_summary.md)
- [Complete evidence package](benchmarks/results/beast_xai_omni_evidence_package.zip)
- [Methodology and reproduction](docs/xai-omni-gauntlet.md)
- [Combined provider research](benchmarks/results/live_provider_benchmark_combined_summary.md)

No first-party xAI USD observations were returned, so xAI remains excluded from cost rankings. BEAST reports missing evidence instead of inventing economics.

## How It Works

```text
VS Code / Cursor / Claude Code / MCP client / coding agent
                         |
                         v
              BEAST Session Handshake
                         |
       +-----------------+-----------------+
       |                                   |
       v                                   v
Input governance                    Runtime intelligence
Task envelope                       Provider Economist
Workspace graph                     Tool Laziness
Chronicle retrieval                 Ollama scout
Context compression                 Budget and route gates
       |                                   |
       +-----------------+-----------------+
                         |
                         v
              Provider handoff packet
                         |
                         v
             Model returns Action IR
                         |
                         v
Output gate -> ref resolver -> local patch compiler
                         |
                         v
             hunk preview and approval
                         |
                         v
        verification -> apply or rollback
                         |
                         v
       Chronicle / PREC / OTEL / fitness evidence
```

BEAST supports native, OpenAI-compatible, Hugging Face router, LiteLLM-managed, and local Ollama/NIM lanes. More than 20 provider routes have been exercised in the current research set.

## Quick Start

```bash
git clone https://github.com/Byron2306/EdgeK-BEAST.git
cd EdgeK-BEAST

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check the gateway:

```bash
curl http://127.0.0.1:8000/health
```

Point an OpenAI-compatible client at BEAST:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=your-provider-key
```

Provider secrets can also be kept in `.beast/provider_secrets.env`; the Secret Vault exposes only presence and fingerprints to diagnostics.

## Use It With Your Coding Agent

### VS Code

The extension provides `/sourceplan`, governed hunk preview and apply, rollback, maintenance cascades, provider role selection, Chronicle, route fitness, and live BEAST status.

```bash
code --install-extension vscode-extension/edgek-beast-1.2.0.vsix
```

See [VS Code extension setup](vscode-extension/README.md).

### Cursor and Claude Code

Route MCP tool calls through BEAST for schema pinning, policy checks, Action IR, SourcePlan, Provider Economist, Tool Laziness, Chronicle, and Commons access.

See the [Cursor and Claude Code MCP pack](integrations/mcp-clients/README.md).

### OpenClaw and Agent Executors

BEAST plans and executes local-first workflows with a strict preflight budget. Optional Ollama scouting is skipped before it can overrun the deadline. Low-value tool actions are suppressed, while required workflow actions remain available.

### Inference Compute Governor

Phase 1 observes every governed provider call through a privacy-safe Compute Plan, non-enforcing Compute Gate, and runtime-linked Compute Receipt. It identifies deterministic and reusable work but does not yet suppress or reroute inference. Ambiguous decisions recommend escalation, never silent suppression. Counterfactual token and USD estimates remain hypotheses until verified by controlled ablations, and dollar projections require first-party cost evidence.

See [Inference Compute Governor](docs/compute-governor.md) and the [phased rollout roadmap](docs/compute-governor-roadmap.md).

### HTTP and Custom Agents

BEAST exposes OpenAI- and Anthropic-compatible inference alongside its governance APIs. The full endpoint reference is in [docs/api.md](docs/api.md).

## The BEAST TUI

Launch the terminal interface:

```bash
./bin/beast ui
```

The TUI includes:

- animated Idle, Working, Alert, and Finished mascot states;
- live provider, route, model, and secret-presence resolution;
- `/sourceplan`, output gate, operation and verifier views;
- selectable diff hunks, approval queue, apply, verify, and rollback;
- Provider Fitness and Chronicle panels;
- a responsive **Intelligence** workspace for Agent Awareness, Provider Economist, Tool Laziness, Meta Tool Commons, OTEL, and marketplace state.

Press `j` to open Intelligence or `Ctrl+K` for the command palette.

## Connectors and Extensions

### GitHub PR Connector

Ingest PR files, failed checks, and review comments as a bounded task envelope. BEAST can publish an approved Chronicle summary back to the PR.

### Network Chronicle Connector

Attach packet-probe metadata to provider diagnostics and benchmark runs without retaining packet payloads.

### OpenTelemetry

Export Chronicle records, route cards, provider fitness, and packet timings over governed OTLP/HTTP. Live export requires explicit approval.

### Plugin Marketplace

Plugins declare risk class, entrypoint, permissions, network domains, environment access, budgets, approval policy, and pinned tool schemas. Installation is dry-run and approval-gated by default.

See [Plugin manifests](plugins/README.md).

## Provider Routing

Configure only the routes you want:

```bash
export XAI_API_KEY='...'
export OPENROUTER_API_KEY='...'
export HF_TOKEN='...'
export NVIDIA_API_KEY='...'
export MISTRAL_API_KEY='...'
export COHERE_API_KEY='...'
export GEMINI_API_KEY='...'
```

BEAST resolves provider aliases, default models, adapters, proxy lanes, output profiles, and secret requirements before a governed turn. Missing or invalid routes fail separately from model capability.

Local scouting can use Ollama without sending repository context to a cloud provider:

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_SCOUT_MODEL=qwen2.5:0.5b
```

## Core API Surface

```text
POST /v1/chat/completions
POST /v1/messages

POST /edgek/session/handshake
POST /edgek/handoff/prepare
POST /edgek/beast-cli/plan
POST /edgek/beast-cli/execute

POST /edgek/provider-economist/select
POST /edgek/tool-laziness/recommend-tools

GET  /edgek/meta-tool-commons
POST /edgek/meta-tool-commons/rank
POST /edgek/meta-tool-commons/adopt

POST /edgek/connectors/network-chronicle/attach
POST /edgek/connectors/github/pr/ingest
POST /edgek/connectors/otel/export

POST /edgek/plugins/manifest/validate
POST /edgek/plugins/install
```

## Run the Evidence Suite

Run the complete local preflight without provider calls:

```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --output beast_xai_omni_gauntlet_preflight
```

Run the live xAI Omni-Gauntlet:

```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --live \
  --output beast_xai_omni_gauntlet_live \
  --max-tokens 1400 \
  --timeout 240
```

Build the publication-grade evidence package:

```bash
.venv/bin/python benchmarks/package_xai_omni_evidence.py --run-tests
```

## Security Model

- Output is validated before source mutation.
- Allowed edit paths are explicit.
- File hashes reject stale Action IR.
- Shared capability evidence excludes prompts, source code, paths, and secrets.
- Plugin side effects require declared permissions and approval.
- OTEL, GitHub writes, plugin installation, Commons contribution, and Commons adoption are approval-gated.
- Chronicle preserves clean, repaired, rejected, and failed outcomes.
- Provider credentials stay in environment variables or the local Secret Vault.

The Capability Exchange is disabled by default. BEAST does not send workspace knowledge or capability evidence to a central service unless the operator opts in.

## Honest Boundaries

- BEAST does not make weak providers independently strong. It constrains, repairs, verifies, and assigns them narrower roles.
- A BEAST-rescued fix is system success, not provider-clean success.
- Hidden-clean performance is still modest across current providers.
- Local governance cannot remove provider network latency.
- Cost rankings require first-party billing observations; token counts are not treated as dollars.
- The current xAI run did not pass the provider-clean rollback hard gate.

## Project Status

BEAST is under active development. The governed coding flow, provider handoff, Action IR, local patch compiler, verification, rollback, Chronicle, Provider Economist, Tool Laziness, Agent Awareness, Commons, connectors, plugin manifests, MCP pack, VS Code extension, and TUI are implemented and exercised.

The project is ready for experimentation and integration, but APIs and evidence schemas may still evolve. Contributions, provider reruns, adversarial tasks, connector implementations, and independent reproduction are welcome.

## License

MIT - see [LICENSE](LICENSE).
