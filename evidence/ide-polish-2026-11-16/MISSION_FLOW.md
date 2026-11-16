# IDE work-mission flow — test gateway :8199

Date: 2026-11-16, afternoon (Africa/Johannesburg, UTC+2).

Verified end-to-end against **current code** on an isolated test gateway at
`http://127.0.0.1:8199`. The live gateway on **8101 was not restarted or
killed** (it stayed pid 2021217 for the whole run). Model spend was **$0.000**
against a $0.03 cap: Ask and Agent were pinned to local TGI
(`Qwen/Qwen2.5-Coder-3B-Instruct-AWQ`). No provider keys were printed.

Workspace: `/tmp/beast-mission-ws-20261116` (a small temp project with
`src/counters.py` and `tests/test_counters.py`, not a copy of the BEAST tree,
so secrets and `.beast/` never entered the test workspace).

Gateway env (8199 only): `BEAST_GOVERNED_INTERCEPTION=1`,
`BEAST_CAPABILITY_ROUTER=1`, `BEAST_PROCESS_LIFECYCLE=1`,
`BEAST_GPU_SCHEDULER=1`, `BEAST_STATE_ROOT=/tmp/beast-ide-8199-mission-20261116`,
`BEAST_ZERO_REVIEW_ROOT` set to the temp workspace, `BEAST_GATEWAY_PORT=8199`,
`BEAST_PUBLIC_BASE_URL=http://127.0.0.1:8199`, `TGI_BASE_URL=http://127.0.0.1:8090`.
The process was stopped after this proof.

Machine-readable log: `evidence/ide-polish-2026-11-16/mission-flow-8199.json`.

## Result

**34 / 34 steps passed** (one testing step needed a harness correction: the
first attempt used `/usr/bin/python3`, which has no pytest; rerunning with the
repo `.venv` and `PYTHONPATH` on the temp workspace passed 2/2. That was not
an IDE or gateway failure).

## Step-by-step

Each row is the backend endpoint (or local check) the IDE page uses, in the
order a work-mission would walk them. Renderer handlers already chain the
same calls and pass `root_path` / plan / run id from Workspace → SourcePlan →
Review → Testing → Trust → Crystallization.

| # | Step | Endpoint / check | Result | Notes |
|---|---|---|---|---|
| 1 | Gateway health | `GET /health` | PASS | `status=healthy` |
| 2 | Set workspace, list files | `GET /edgek/workspace/files?root_path=…` | PASS | 3 files, `src/counters.py` present |
| 3 | Select file (Monaco) | `GET /edgek/workspace/file?path=src/counters.py` | PASS | 266 bytes, `increment()` present |
| 4 | Model / provider inventory | `GET /edgek/ide/model-inventory` | PASS | 38 routes, 130 scorecard cells. Blocked (not hidden): `fal_llm`, `hyperbolic`, `replicate`, `sambanova`. Rename family leader: Fireworks `glm-5p3-flash` |
| 5 | Auto pick for rename | `POST /edgek/ide/model-route` `family=rename` | PASS | Auto mapped `rename` → `refactor-rename-symbol` and chose Fireworks `glm-5p3-flash` via the capability router. Not called (resolve only). |
| 6 | Ask — create session | `POST /edgek/ide/agent-sessions/create` `mode=chat` | PASS | `session_id=chat-eb758998`, provider pinned to TGI |
| 7 | Ask — run | `POST /edgek/agent-runs` `launch=true` | PASS | `run_id=chat-eb758998-6bf75f7ca28f` launched |
| 8 | Ask — wait | `GET /edgek/agent-runs/{id}` | PASS (paused) | State reached `waiting_for_approval`. The governed path started the TGI turn and then paused for an operator admit/approval, which is intended. No paid spend. |
| 9 | Run Agent — create session | `POST /edgek/ide/agent-sessions/create` `mode=implementer` | PASS | `session_id=implementer-cdd017b6` |
| 10 | Run Agent — run | `POST /edgek/agent-runs` `launch=true` | PASS | `run_id=implementer-cdd017b6-77ebc1491249` launched |
| 11 | Run Agent — wait | `GET /edgek/agent-runs/{id}` | PASS (paused) | Also `waiting_for_approval`. Same governed pause as Ask. |
| 12 | SourcePlan draft | `POST /edgek/ide/sourceplan/from-editor` | PASS | Deterministic editor diff adding `decrement()`. `plan_id=desktop_editor_4e192331d620` |
| 13 | SourcePlan lifecycle | `POST /edgek/ide/sourceplan/lifecycle` | PASS | `ok=true`, `can_apply=true`, 1 operation, 0 stale |
| 14 | SourcePlan lifecycle GET | `GET /edgek/ide/sourceplan/lifecycle` | PASS | **No longer 405.** Body-less GET returns 200 with `missing_plan` (needs the plan in the POST body, which the IDE already sends). |
| 15 | SourcePlan verify | `POST /edgek/sourceplan/verify` | PASS | HTTP 200 |
| 16 | Diff view | lifecycle `preview.operations` / `preview.diff` | PASS | 1 operation; preview has `diff`, `operations`, `shadow_buffers`, `preview_hash` |
| 17 | Review snapshot | `GET /edgek/ide/snapshot` | PASS | HTTP 200 |
| 18 | Review approvals | `GET /edgek/mcp/approvals?limit=20` | PASS | HTTP 200 |
| 19 | Review tooling | `GET /edgek/ide/tooling-snapshot` | PASS | `ok=true` |
| 20 | Review evidence | `GET /edgek/evidence-bus/query?limit=25` | PASS | HTTP 200 |
| 21 | Review board (was 503) | `GET /edgek/zero/review-board?workspace=…` | PASS | **No longer 503.** `ok=true`, workspace = the temp root, 0 runs |
| 22 | Review status (was 503) | `GET /edgek/zero/reviews?workspace=…` | PASS | `ok=true`, workspace configured from the IDE workspace (or `BEAST_ZERO_REVIEW_ROOT`) |
| 23 | Run tests | pytest on the temp workspace | PASS | 2 passed, with repo `.venv` and `PYTHONPATH` |
| 24 | Testing verification console | `GET /edgek/agent-runs/{id}/console/verification` | PASS | HTTP 200 (or empty console when the run is still waiting for approval) |
| 25 | Trust snapshot | `GET /edgek/ide/snapshot` | PASS | `status=ready` |
| 26 | Trust system snapshot | `GET /edgek/ide/system-snapshot` | PASS | `ok=true` |
| 27 | Trust memory security | `GET /edgek/memory-security?verify=true` | PASS | HTTP 200 |
| 28 | Trust approvals | `GET /edgek/mcp/approvals?limit=20` | PASS | HTTP 200 |
| 29 | Trust chronicle | `GET /edgek/chronicle?limit=20` | PASS | 20 entries |
| 30 | Crystals reuse / credits | `GET /edgek/crystal-reuse` | PASS | **17 credits** reported |
| 31 | Crystal chain | `GET /edgek/crystal-chain?include_blocks=true` | PASS | 5 blocks |
| 32 | Crystal lattice | `GET /edgek/crystal-lattice` | PASS | HTTP 200 |
| 33 | Compute economy | `GET /edgek/commons-economy` | PASS | HTTP 200 (`credit_count=0` on this isolated state root; reuse credits live on `/edgek/crystal-reuse`) |
| 34 | Spend cap | TGI-only, no paid provider calls | PASS | **$0.000 / $0.03** |

## Fixes made so this flow works

- **SourcePlan lifecycle 405:** `GET /edgek/ide/sourceplan/lifecycle` is now accepted as well as POST. The IDE's Refresh Lifecycle button already used POST; probes and a body-less GET no longer 405.
- **Review 503 "Desktop Review workspace is not configured":** `/edgek/zero/review-board` and `/edgek/zero/reviews` fall back to the workspace the IDE already sends (query or body) when `BEAST_ZERO_REVIEW_ROOT` is unset. The env var remains authoritative when set. The board is no longer empty just because that extra env was missing.
- **Auto rename pick:** today's Fireworks / rename / refguard scorecard cells were merged into `.beast/capability_scorecard.json` (130 cells). `family=rename` is aliased to `refactor-rename-symbol`. Auto now picks Fireworks `glm-5p3-flash` for rename.
- **Blocked providers:** SambaNova (402 payment method), Hyperbolic (403 verified phone), Replicate (402 insufficient credit), and fal (403 exhausted balance) are marked `blocked` in the inventory and skipped by Auto. They are still listed, not hidden.

## Renderer chaining (page to page)

- Workspace file tree and Monaco use `BeastDesktopBridge` `root_path` + `/edgek/workspace/files` and `/edgek/workspace/file`.
- Ask / Run Agent use `BeastWorkspaceAgentPanel` → `agent-client.js`: session create, then `/edgek/agent-runs` with the selected provider/model, then the event stream. Mode `ask` maps to `chat`; Agent maps to `implementer`.
- SourcePlan uses `BeastEditorCortex.draftSourcePlan` → `/edgek/ide/sourceplan/from-editor`, `refreshLifecycle` → POST lifecycle, `verifyPlan` → `/edgek/sourceplan/verify`. The SourcePlan page buttons call those same handlers. Diffs come from the lifecycle preview.
- Review uses `BeastReviewEvidenceBridge.refreshReview` (snapshot, approvals, tooling, evidence bus). The Zero Review dock additionally calls `/edgek/zero/review-board?workspace=`.
- Testing's verification console is keyed by the durable AgentRun id from the previous step.
- Trust uses `BeastTrustMemoryBridge` (snapshot, system snapshot, memory-security, approvals, chronicle).
- Crystallization / economy use `BeastMapCrystalBridge` and the utility orchestration bridge (`/edgek/crystal-reuse`, chain, lattice, commons-economy).

## Still open in this flow

- Ask and Agent runs pause at `waiting_for_approval` on the governed path. Completing the turn needs an operator admit/approval in the IDE (or an admit token). That was not forced here.
- The Testing page itself is still a thin, run-id-based console; it does not list episodes on its own.
- Crystal *economy* credits on an isolated `BEAST_STATE_ROOT` are 0; the live reuse credits (17) are on `/edgek/crystal-reuse`.
