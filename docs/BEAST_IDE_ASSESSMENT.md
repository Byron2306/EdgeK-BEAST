# BEAST IDE — Deep Assessment

_Assessment date: 2026-07-09. Author: hands-on review of the running system + code read._
_Confidence tags: **[verified]** = I ran it or read the implementation; **[inferred]** = read-through only; **[unverified]** = claimed but not independently confirmed._

## 1. What this actually is (honest elevator pitch)

BEAST is a **governance-and-provenance layer wrapped around multi-provider LLM inference, plus an IDE (VS Code extension + Electron desktop app) that surfaces it.** The real, working core is:

- A FastAPI **gateway** that proxies ~27 providers (OpenAI-compatible, native Anthropic/Gemini/HF/Replicate, Ollama, LiteLLM) behind one lane. **[verified: NVIDIA NIM live-streamed]**
- A **safe-edit pipeline** ("SourcePlan"): agent output → Action IR → hash-checked operations → preview/scorecard/verify → operator approval → apply with rollback + content-addressed evidence. **[verified: read + route-tested]**
- A **governance/audit spine**: Safety Governor (command classification), Evidence Bus (sha256 receipt store), policy gates, MCP broker (policy-classed, approval-gated tool execution with SQLite audit). **[verified]**
- An **MCP surface**: a stdio server exposing ~40 BEAST tools, consumable by Claude Code / Cursor / VS Code. **[verified via format map]**

The marketing thesis ("Inference Economy Inversion", "Compute Commons", tiny local models beating frontier models via BEAST scaffolding) is a **research narrative layered on top** — see §5.

## 2. What's genuinely good / differentiated

- **Provenance-first editing is real and disciplined.** Unlike Cursor/Claude Code, edits don't apply directly — they route through SourcePlan with expected-hash checks, explicit approval, rollback capture, and an evidence receipt. For regulated/audited environments this is a real differentiator, not theater. **[verified]**
- **Everything emits content-addressed receipts.** The Evidence Bus (`sha256:` artifacts) gives a genuine audit trail across terminal runs, kills, sourceplans, runbooks. **[verified — I saw receipts written for governed process-kills]**
- **The Safety Governor is a real (if heuristic) gate.** Regex high-risk patterns + mode/mutation conflict detection + unknown-repo-binary detection + operator-override escalation, all recorded. Not sandboxing, but a coherent policy layer. **[verified: read `classify_command`]**
- **MCP broker is substantive**: SQLite-backed server registry, `server_class` policy gating, approval workflow, execution audit, schema pins. **[inferred: thorough sub-survey]**
- **Multi-provider routing actually works** and is broad. **[verified]**
- **Breadth of surface**: ~99k LOC Python / 233 files, 131 test files / 852 test functions, VS Code extension with ~50 commands + chat participant + MCP provider, Electron app with Monaco. This is a lot of built surface for what appears to be a small team. **[verified: counts]**

## 3. What's lacking / weak / risky

- **The "agent" is a streaming chat, not an autonomous coding loop.** It streams tokens and can compile Action IR → SourcePlan, but there's no iterative tool-use/observe/repair loop like Claude Code or Cursor Composer. The governance is ahead of the autonomy. **[verified: read `stream_live_turn` + run-events]**
- **Single-worker uvicorn + sync work in async paths.** I found and fixed an event-loop starvation bug (heavy synchronous repo scans inside SSE generators froze the loop 15–20s, stalling agent runs). This class of bug likely recurs elsewhere; the gateway needs a systematic "no blocking calls on the loop" pass or multiple workers. **[verified: reproduced + fixed]**
- **Generic plugin execution is a stub.** Plugins validate and install-to-JSON, but only 6 hard-coded built-ins actually execute; custom `python`/`http`/`mcp_stdio` entrypoints are metadata-only. The "marketplace" is a registry, not a runtime. **[inferred: sub-survey]**
- **Editor UX is far behind competitors.** Monaco is embedded, but there's no LSP, no real multi-file navigation/refactor, no inline diff-apply UX comparable to Cursor. It's a governed viewer/editor, not a daily-driver editor yet. **[inferred]**
- **Naming vs substance gap** (see §4) — the branding oversells and will hurt credibility with technical evaluators.
- **Repo hygiene is poor** and actively risky:
  - The **entire desktop IDE and a 2295-line `app/routes/ide.py` are uncommitted** (untracked/modified) — no git safety net for the core of the product. **[verified]**
  - 16 `check_*.py` / `test_*.py` / `fix_imports_v2.py` debug scripts in the repo root. **[verified]**
  - 9 committed binaries in root (`.pdf`, `.mp4`, `.pptx`, 6 `.png`). **[verified]**
  - A duplicate abandoned **`new ide/` (78M)** alongside `desktop-ide/` (1.1G — node_modules appears tracked). **[verified]**
  - `.bak` files and multiple `check_registry_v*.py` iterations left in tree. **[verified]**

## 4. Naming vs substance (the "theater" question)

Backed by real logic: **SourcePlan, Evidence Bus, Safety Governor, MCP broker, provider registry** — these do non-trivial work matching their names.

Thin relative to their grandeur: **"Crystal Lattice" / "Crystallized Compute Proof" / "Compute Governor" / "Mission Cockpit"** are largely **aggregation + receipt-generation with evocative names** (`crystallized_compute_proof.py` is 1,384 lines but centers on producing "proof" receipts around reuse decisions rather than a novel algorithm). **[inferred]** The naming density (every module is a "Governor"/"Cockpit"/"Lattice"/"Commons") makes it hard for an evaluator to find the real substance — which exists — under the branding. **Recommendation: dial the naming back; let the governance substance speak.**

## 5. The core thesis: is it valuable / is it true?

The claim — local-CPU-first, tiny models (e.g. Llama-3.1-8B) matching frontier output via BEAST scaffolding, "inverting" the inference economy — is **not independently verified here.** There are 115 benchmark result JSONs in `benchmarks/results/`, but I did not validate their methodology, baselines, or reproducibility. **[unverified]** As stated, the thesis risks being **unfalsifiable** without: fixed public baselines, held-out tasks, blind grading, and cost accounting that includes the scaffolding's own token/compute overhead. Until that exists, treat the economic claims as a hypothesis, not a result.

## 6. Where it stands vs the market

| Dimension | BEAST | Cursor / Claude Code / Windsurf |
|---|---|---|
| Governance / audit / provenance | **Ahead** (SourcePlan + Evidence) | Minimal |
| Multi-provider / local-first | **Ahead** (~27 providers, Ollama/NIM) | Narrower |
| Autonomous agent loop | Behind (chat + Action IR) | Ahead (Composer/agent) |
| Editor UX / LSP / refactor | Behind | Ahead |
| Packaging / onboarding / stability | Behind (uncommitted WIP, hygiene) | Ahead |

**Realistic maturity: advanced prototype / internal tool**, not near-shippable as a general IDE. But the governance layer could ship *now* as an MCP server + gateway for teams that need audited AI edits.

## 7. Will it be valuable? — verdict

**Conditionally yes, if refocused.** The valuable, defensible IP is the **governed, auditable, provider-agnostic inference layer** (SourcePlan + Evidence + Safety Governor + MCP broker). That solves a real problem — *provable, policy-controlled AI code changes* — that mainstream tools ignore. The full "IDE" and the "inference economy" thesis are the weaker bets.

Highest-leverage path: **stop competing with Cursor on editor UX; double down on being the governance/provenance layer that plugs into the editors people already use** (VS Code extension + MCP server + gateway), and prove or drop the economic thesis with rigorous baselines.

## 8. Prioritized recommendations

1. **Commit the WIP now.** The product's core is untracked. Get `desktop-ide/` and `ide.py` into git; add a real `.gitignore` (exclude `node_modules/`, `.bak`, root binaries, `new ide/`). _(P0, hours)_
2. **Repo hygiene pass**: delete/relocate root `check_*.py`, drop the abandoned `new ide/`, move binaries to a release/assets store, remove `.bak` files. _(P0)_
3. **Event-loop discipline**: audit all async routes for blocking calls; adopt `asyncio.to_thread` (done for the IDE snapshot paths) or run multiple workers. _(P1)_
4. **Sharpen positioning**: lead with "auditable, governed, multi-provider AI edits via MCP + gateway." Tone down internal codenames in external-facing surfaces. _(P1)_
5. **Prove or retire the economic thesis**: publish a reproducible benchmark harness with public baselines, blind grading, and full cost accounting — or reframe it as an open research question. _(P1)_
6. **Close the agent loop**: add iterative tool-use/verify/repair so the "agent" earns the name, feeding results through the existing SourcePlan governance (which is the moat). _(P2)_
7. **Make plugins executable** or rename the "marketplace" to "registry" to match reality. _(P2)_

---

_This assessment is deliberately blunt per request. The short version: the governance/provenance engine is genuinely good and differentiated; the editor, the autonomous agent, the naming, and the economic thesis are the parts that need work or honesty._
