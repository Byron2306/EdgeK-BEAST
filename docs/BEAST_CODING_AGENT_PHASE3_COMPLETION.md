# BEAST Coding Agent Phase 3 — Completion Record

**Status:** PASS  
**Phase:** 3 — Real least-authority model-directed tool use  
**Implementation head:** `15cea53b7d078df4c9714799a16e1f95c6ef73a3`  
**Base Phase 2 head:** `2f9825c576a79de5ff47b54a95bd33a4aa9a3201`

## Exit result

The Phase 3 exit gate defined in
`4.0/BEAST_Next_Level_Upgrade_Master_Plan_2026-07-18.md` is satisfied.

A seeded multi-file defect was solved through the durable AgentRun path with:

```text
inspect
  -> isolated worktree
  -> bounded mutation
  -> cheapest-first verification
  -> focused verification failure
  -> diagnosis / repair
  -> mutation epoch advance
  -> fresh verification ladder
  -> focused verification success
  -> SourcePlan draft
```

The operator workspace remained untouched throughout the model-directed mutation
journey. SourcePlan remains a separate promotion boundary.

## Verified Phase 3 gates

The unified Phase 3 completion run reported:

```json
{
  "least_authority_tool_plane": true,
  "policy_profile_budgets": true,
  "stagnation_and_oscillation_control": true,
  "verification_ladder": true,
  "seeded_multifile_repair_to_sourceplan": true,
  "real_model_directed_tool_use": true,
  "phase2_behavior_preserved": true,
  "phase3_exit_met": true
}
```

### 1. Least-authority model-directed tools

AgentRun tools now publish and enforce explicit authority classes:

```text
A_READ_AUTOMATIC
B_READ_SENSITIVE
C_ISOLATED_MUTATION
D_CONSEQUENTIAL_EXECUTION
E_NEVER_MODEL_AUTHORIZED
```

Each tool request receives a hash-bound authority receipt before handler
execution. Class E is structurally unavailable to model authority. Isolated
mutation remains worktree-bound and request-bound approval remains required.

### 2. Policy-profile budgets

Phase 3 introduces explicit `compact`, `balanced`, and `extended` policy
profiles covering model turns, tool calls, mutation calls, verification cycles,
changed files/lines, wall time, token use, cost and parallel subagents.

Budget usage is derived from the AgentRun event ledger. A projected breach is
refused before the action executes and terminates the run as
`BUDGET_EXHAUSTED` where applicable.

Legacy Phase 2 runs do not silently inherit Phase 3's balanced limits.
`legacy_compat` preserves existing Phase 2 semantics unless a Phase 3 policy
or Phase 3-specific limit is explicitly requested.

### 3. Stagnation and oscillation control

The planner detects:

- equivalent repeated tool calls with no new evidence;
- two-action oscillation;
- repeated equivalent verification failures;
- repeated truncated output.

A first detection requires a replan. Repeating the same dead-end action after
that replan fails closed instead of spending the remaining budget.

### 4. Verification ladder and freshness

Opt-in Phase 3 runs use a cheapest-first verification ladder:

```text
worktree diff safety
  -> relevant syntax / type verification
  -> focused affected verification
```

Verification observations carry the worktree mutation epoch. A repair mutation
invalidates earlier ladder stages. SourcePlan synthesis refuses stale or
incomplete verification evidence.

### 5. Real-model tool selection

Hosted acceptance uses a real local Ollama `qwen2.5:0.5b` model through
BEAST's production `OllamaPlannerProvider`.

The model selects `workspace.list`. If its first tool packet violates the
typed argument schema, BEAST does not strip or accept unauthorized fields.
The model receives a bounded schema-correction turn and execution occurs only
after the canonical tool registry accepts the packet. The accepted request then
passes the Phase 3 authority and budget gates.

## Regression closure

Phase 3 discovered and repaired two compatibility issues before closure:

1. New Phase 3 balanced budgets initially constrained legacy Phase 2 runs. The
   resolver now requires an explicit Phase 3 policy signal before those limits
   apply.
2. A Phase 2 tamper test could accidentally replace a hash character with the
   same value. The test now guarantees a genuinely different evidence
   reference before asserting fail-closed rejection.

On the implementation head, all of the following completed successfully:

- Agentic Loop Endurance
- BEAST Phase 2 Request Trace
- BEAST Phase 3 Least Authority
- BEAST Phase 3 Live Model Tool Acceptance
- BEAST Phase 3 Completion Gate
- BEAST Phase 2 Completion Gate

## Closure evidence

Unified Phase 3 completion workflow run: `35296717404`  
Live-model workflow run: `35296717254`  
Inherited Phase 2 completion run: `35296717310`  
Endurance run: `35296717231`

Phase 3 completion artifact:

```text
name: beast-phase3-completion-receipt
artifact_id: 10527844402
digest: sha256:ec29cd83d326d98aab01bbf8c8bc93e39c8fd332d0ec329540c47de26e506128
```

The completion compiler emitted `phase3_exit_met: true`.

## Evidence boundary

This record proves the hosted Linux Phase 3 acceptance matrix.

The earlier Android/Termux evidence in
`docs/BEAST_PHASE2_TERMUX_ANDROID_ACCEPTANCE.md` remains valid Phase 2
evidence, but this completion record does not claim that the full Phase 3
authority, budget, stagnation and repair gauntlet has yet been rerun on
Android/Termux.

Phase 3 does not grant model authority to promote a SourcePlan, push a remote,
publish packages, alter global policy, disable evidence, or erase audit
history.
