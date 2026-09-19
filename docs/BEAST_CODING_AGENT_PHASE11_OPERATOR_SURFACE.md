# BEAST Coding Agent Recovery — Phase 11 Operator Surface Unification

Date: 2026-09-19

Status: **COMPLETE at repository implementation level**

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

## Phase 11 closure

The durable backend projection is now rendered in the BEAST Agents surface as Operator Truth. It exposes planner phase, execution target/transport, worktree mutation epoch, verification currency, pending human gates, promotion state and provider/model route.

Existing durable approval cards already resolve through the AgentRun approval endpoint. The surface labels execution-gate, repair and reuse evidence without upgrading them into authority.

A deterministic static frontend/backend contract lives at desktop-ide/scripts/verify-phase11-operator-surface.js and is exposed as npm run phase11:verify. Python recovery tests cover current-epoch verification and stale-proof promotion refusal.

**COMPLETE at repository implementation level.** The Phase 11 exit condition is satisfied structurally: the UI reflects actual durable planner/evidence/route/verification/human-gate state through a read-only projection, rather than maintaining a competing UI truth.

Fresh runtime acceptance remains deliberately separate. Debian/Electron should run the Python Phase 11 tests, npm run phase11:verify, and visual interaction acceptance before claiming live UI proof.

The recovery programme can now proceed to **Phase 12 — Agent Gauntlet & Promotion**.
