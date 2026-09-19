# BEAST Coding Agent Recovery — Phase 11 Operator Surface Unification

Date: 2026-09-19

Status: **IN PROGRESS**

## Objective

Make the backend coding-agent state legible to an operator without inventing a second UI authority plane.

The operator surface must answer, from durable evidence: planner phase; execution target and transport; authoritative worktree and mutation epoch; current verification; repair/retry/block state; pending human approvals; provider/model route; advisory memory/reuse evidence; and SourcePlan promotion readiness.

## Phase 11 invariant

The UI is a projection, never an authority source. Rendering a green state cannot authorize execution, mutation, verification or promotion.

## First implementation slice

AgentOperationsConsoleViewModel now emits operator_state, a single read-only projection over the existing durable AgentRun checkpoint/events:

- planner phase, turn and repair cycles;
- execution target, target-execution class and transport;
- latest execution gate receipt;
- worktree path/status/current mutation epoch;
- current-epoch verification status and evidence digest;
- latest repair evidence;
- latest memory/reuse evidence pointers;
- pending approval IDs;
- SourcePlan promotion readiness/authorization;
- active provider/model route.

Promotion readiness is deliberately recomputed against current mutation epoch. A stale verifier receipt cannot be painted as promotion-ready merely because an older SourcePlan says it is ready.

Recovery tests live in tests/test_agent_phase11_operator_surface.py.

## Remaining Phase 11 work

1. Render operator_state in the BEAST Agent/Pair Programmer surface.
2. Bind approval controls to existing durable approval endpoints rather than local UI state.
3. Expose worktree diff and verification consoles beside the selected durable run.
4. Surface Memory Hull / crystal reuse as advisory evidence, visually distinct from exact source and verifier authority.
5. Add a deterministic frontend contract proving UI labels derive from backend state.
6. Run the operator-surface gauntlet on Debian/Electron.

Phase 11 closes only when the UI reflects real planner phase, evidence, route, verification and human gates without creating UI-only authority.
