# Physical Crystal Fabric Phase 6 Crystal Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop. A verified Episode Envelope becomes a candidate coding crystal; failed envelopes become negative evidence; candidates are promoted only after held-out replay on 3 or more variants; and a later AgentRun reuses the promoted recipe at planning time, doing measurably less work, without ever exceeding reviewed authority.

**Architecture:** A separate reviewed coding opcode catalog (`worktree.inspect`, `worktree.bind`, `worktree.replace_exact`, `worktree.verify`, plus the pure decision opcode `repair.resolve_constant`) uses the existing `OpcodeSpec`/`OpcodeRegistry` contract without changing the physical catalog digest. `CodingCrystalExtractor` generalizes a verified envelope (with its locally bound observations) into a parameterized recipe. `HeldOutReplayGate` (existing) runs the recipe in fresh AgentRuns on held-out variants with a provider that must not be consulted. `CodingCrystalRegistry` (SQLite) records candidate → promoted → demoted transitions and negative evidence. `CodingCrystalPlanner` runs an applicability gate and consumes an exact signed one-use capability (existing `OneUseCapabilityLedger`). It then gives `AgentPlannerRuntime` a session that supplies recipe decisions instead of model turns. Every step still goes through the runtime's normal argument validation, approvals and `engine.execute_tool`.

**Tech Stack:** Python 3.13, Ed25519 one-use capabilities, SQLite, git worktrees, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`
**Roadmap:** `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md`

## Global Constraints

- A crystal can only emit tool decisions mapped from reviewed opcodes (`workspace.read_range`, `worktree.bind`, `worktree.replace_exact`, `worktree.verify`). Anything else is refused at compile time and again at execution time.
- Crystals never fabricate approvals. Mutations and verification use the run's existing operator approvals through the unchanged `_authorize_tool`.
- The verification command always comes from the durable run request (`verified_handoff_command`), never from the crystal.
- Reuse needs an exact signed one-use capability bound to crystal digest, run ID and parameter digest. A consumed capability is refused.
- Promotion needs at least 3 held-out successes with zero failures. A failed postcondition during reuse demotes the crystal and returns control to the provider.
- Backend only, with offline tests. No renderer changes.

## Review Focus

- A misfit task (no failing test, missing target, wrong family) must be refused before any mutation.
- A tampered record or a non-reviewed opcode/tool must be refused.
- Replaying a consumed capability must be refused, and the run must fall back to normal planning.
- A failing recipe must demote the crystal, and later activations must refuse it.
- Reuse must reach the same verified outcome with at most 50% of the model turns and at most 70% of the tool calls.

---

### Task 1: Reviewed Coding Opcodes and Resolver

**Files:**
- Create: `app/kernel/compute/coding_crystals.py`
- Test: `tests/test_coding_crystals.py`

**Interfaces:**
- Produces: `coding_opcode_registry()`, `CODING_OPCODE_TOOLS`, `resolve_constant(verify_output, target_content) -> dict | None`.

- [ ] Tests: catalog validates; exactly the reviewed tools are mapped; resolver handles unittest/pytest equality failures and refuses ambiguous or absent assignments.
- [ ] Verify RED, implement, verify GREEN.

### Task 2: Extraction, Negative Evidence and Registry

**Files:**
- Modify: `app/kernel/compute/coding_crystals.py`
- Test: `tests/test_coding_crystals.py`

**Interfaces:**
- Consumes: Phase 5 `EpisodeEnvelope`.
- Produces: `CodingCrystalExtractor.extract(envelope, observations) -> CodingCrystalCandidate`, `CodingCrystalRegistry(path)` with `add_candidate`, `record_negative`, `promote`, `demote`, `record_reuse`, `get`, `active_for_family`.

- [ ] Tests: verified envelope → candidate with only reviewed opcodes; failed envelope → negative evidence and no candidate; tampered record refused; illegal opcode refused at compile time.
- [ ] Verify RED, implement, verify GREEN.

### Task 3: Held-Out Replay, Promotion and Planning-Time Reuse

**Files:**
- Modify: `app/kernel/compute/coding_crystals.py`
- Modify: `app/kernel/agents/planner_runtime.py`
- Test: `tests/test_coding_crystals.py`

**Interfaces:**
- Consumes: Tasks 1-2, Phase 5 budget tracker.
- Produces: `replay_candidate(...)` via `HeldOutReplayGate`, `CodingCrystalAuthority` (signs one-use capabilities), `CodingCrystalPlanner.activate(run, run_id) -> CodingCrystalSession | None`, and `AgentPlannerRuntime(..., crystal_planner=None)`.

- [ ] Tests: applicability refusals, capability replay refusal, demotion on failed postcondition, a disallowed tool in a tampered recipe refused at execution.
- [ ] Verify RED, implement, verify GREEN; re-run `tests/test_agent_planner_runtime.py`.

### Task 4: Closed-Loop Acceptance Test

**Files:**
- Test: `tests/test_crystal_fabric_closed_loop.py`

- [ ] Learn → extract → replay on 3 held-out variants (plus a refused misfit) → promote → reuse. Assert the same verified outcome, `model_turns ≤ 0.5×` and `tool_calls ≤ 0.7×`, and report tokens and wall time. Negative controls: demotion, reviewed-ops boundary, capability replay.
- [ ] Run scoped pytest, Ruff, desktop smoke, and `git diff --check`.

## Enabling Coding Crystals (production wiring, default OFF)

Crystal planning is off unless `BEAST_CODING_CRYSTALS=1` is set in the gateway's environment.

- **Signing key:** the existing ARDA runtime key `~/.local/state/beast/compute_plane/authority/arda-runtime-ed25519.pem`, loaded by path only (never copied, printed or re-permissioned). Override with `BEAST_CODING_CRYSTAL_KEY=/path/key.pem`. A key readable by group/other, missing, or not Ed25519 fails closed (crystals stay off; `status` reports the reason).
- **Durable state (git-ignored):** `.beast/crystals/coding_crystals.sqlite3` (registry + negative evidence), `.beast/crystals/coding_crystal_capabilities.sqlite3` (one-use capability ledger), `.beast/sensorium/episode_envelopes.sqlite3` (sealed Episode Envelopes).
- **Wiring:** `app/routes/agent_runs.py` and `app/routes/ide_routes/agent_runs.py` pass `planner_runtime_extras(root)` to `AgentPlannerRuntime`; empty when off.
- **Runs eligible for reuse:** `mode: agent`, request with `task_family: "fix-failing-assertion"`, `post_session_closure: "verified_handoff"`, `post_session_test_runner`, `required_test_files`, `implementation_target`.

Steps:
1. `BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py status` → expect `"reason": "ready"` and a public `key_id` fingerprint.
2. Start a temporary gateway with the flag (do not touch the 8101 process): `BEAST_CODING_CRYSTALS=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8131`.
3. Run one model-driven eligible agent run to completion (its envelope is sealed into `.beast/sensorium`).
4. Learn and promote it: `BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py learn <run_id>` (offline held-out replay on 3 synthetic variants, no model; promotes only if 3/3 pass).
5. When the 8101 gateway restarts with `BEAST_CODING_CRYSTALS=1` in its environment, eligible runs reuse the promoted crystal. To turn it off, unset the variable and restart; the registry can stay.


## Paper alignment (operator ruling 2026-11-15)
- Candidate = PGEC §2.2 "candidate capability" (no right to execute or promote). Promoted crystal = PGEC §2.2.
- Recipe: P/Θ/Gₖ/Q/Γ/𝒱/𝒜/Δ = preconditions (failing verify), parameters (target, constant), reviewed opcodes,
  passing verify, applicability gate, held-out replay, `REVIEWED_TOOLS`, demotion (PGEC eq. 2-5).
- **Conflict fixed (paper wins):** PGEC §1 and §2.4 make promotion a human-controlled act. The production
  `learn`/`reproduce` paths now stop at `verified_awaiting_operator_promotion` unless `--approve-by` names the
  operator. The offline harness still calls `replay_candidate(promote=True)`.
- **Conflict fixed (paper wins):** the efficiency report's token numbers are chars/4 estimates. Under v0.9 Table 3
  they are flagged `tokens_estimated` and never credited. Model turns and tool calls are measured.
- Economic value of reuse = PGEC eq. 6 V_K (see the phase-7 plan), not gross avoided turns.

### Enabling Coding Crystals — promotion and economy addendum
- `scripts/coding_crystals.py learn RUN_ID --approve-by <operator>` promotes after 3/3 held-out replay. Without
  `--approve-by` it reports `verified_awaiting_operator_promotion`.
- Every verified crystal run emits `agent.crystal.reduction_receipt`. Inspect it with
  `scripts/coding_crystals.py ledger` (ledger-only credits at `.beast/crystals/coding_crystal_shadow_ledger.sqlite3`).
- Optional identity env vars: `BEAST_COMMONS_NODE_ID` (default `beast-control-plane`) and `BEAST_COMMONS_USER_ID`
  (default `operator`).
