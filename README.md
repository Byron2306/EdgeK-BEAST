<p align="center">
  <img src="BEAST%20mascot%20transparent.png" alt="BEAST mascot" width="420" style="max-width: 90%; height: auto;">
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
 
---
 
## Use It With Your Coding Agent
 
### VS Code
 
```bash
code --install-extension vscode-extension/edgek-beast-1.2.0.vsix
```
 
Provides `/sourceplan`, governed hunk preview and apply, rollback, maintenance cascades, provider role selection, Chronicle, route fitness, and live BEAST status. See [VS Code extension setup](vscode-extension/README.md).
 
### Cursor and Claude Code
 
Route MCP tool calls through BEAST for schema pinning, policy checks, Action IR, SourcePlan, Provider Economist, Tool Laziness, Chronicle, and Commons access. See the [Cursor and Claude Code MCP pack](integrations/mcp-clients/README.md).
 
### HTTP and custom agents
 
BEAST exposes OpenAI- and Anthropic-compatible inference alongside its governance APIs. Full endpoint reference: [docs/api.md](docs/api.md).
 
---
 
## Provider Setup
 
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
 
Local scouting via Ollama without sending repository context to a cloud provider:
 
```bash
export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_SCOUT_MODEL=qwen2.5:0.5b
```
 
---
 
## Run the Evidence Suite
 
Local preflight (no provider calls needed):
 
```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --output beast_xai_omni_gauntlet_preflight
```
 
Live xAI Omni-Gauntlet:
 
```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --live \
  --output beast_xai_omni_gauntlet_live \
  --max-tokens 1400 \
  --timeout 240
```
 
Compute Governor phase benchmarks:
 
```bash
.venv/bin/python benchmarks/compute_governor_phase1_shadow.py
.venv/bin/python benchmarks/compute_governor_phase2_live_displacement.py
# ... through phase 7
```
 
Evidence package:
 
```bash
.venv/bin/python benchmarks/package_xai_omni_evidence.py --run-tests
```
 
---
 
## Core API Surface
 
```
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
 
POST /edgek/connectors/github/pr/ingest
POST /edgek/connectors/otel/export
POST /edgek/plugins/install
```
 
---
 
## Security Model
 
- Output is validated before source mutation
- Allowed edit paths are explicit
- File hashes reject stale Action IR
- Shared capability evidence excludes prompts, source code, paths, and secrets
- Plugin side effects require declared permissions and approval
- OTEL, GitHub writes, plugin installation, Commons contribution, and Commons adoption are approval-gated
- Chronicle preserves clean, repaired, rejected, and failed outcomes
- Provider credentials stay in environment variables or the local Secret Vault
- The Capability Exchange is disabled by default
---
 
## Honest Boundaries
 
- BEAST does not make weak providers independently strong. It constrains, repairs, verifies, and assigns them narrower roles.
- A BEAST-rescued fix is system success, not provider-clean success.
- Hidden-clean performance is still modest across most current providers.
- Local governance cannot remove provider network latency.
- Cost rankings require first-party billing observations; token counts are not treated as dollars.
- Compute Governor counterfactual savings are hypotheses until verified by controlled ablations.
- The current xAI run did not pass the provider-clean rollback hard gate.
---
 
## Project Status
 
Active development. The governed coding flow, provider handoff, Action IR, local patch compiler, verification, rollback, Chronicle, Provider Economist, Tool Laziness, Agent Awareness, Meta Tool Commons, Inference Compute Governor (7 phases), connectors, plugin manifests, MCP pack, VS Code extension, and TUI are implemented and benchmarked.
 
APIs and evidence schemas may still evolve. Contributions, provider reruns, adversarial tasks, connector implementations, and independent reproduction are welcome.
 
- [xAI Omni comprehensive summary](benchmarks/results/beast_xai_omni_comprehensive_summary.md)
- [Complete evidence package](benchmarks/results/beast_xai_omni_evidence_package.zip)
- [Combined provider research](benchmarks/results/live_provider_benchmark_combined_summary.md)
- [Inference Compute Governor](docs/compute-governor.md)
- [Compute Governor roadmap](docs/compute-governor-roadmap.md)
- [Methodology and reproduction](docs/xai-omni-gauntlet.md)
---
 
## License
 
MIT — see [LICENSE](LICENSE).
