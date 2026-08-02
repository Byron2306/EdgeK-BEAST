# Agentic Loop Planning Integrations

Status date: 2026-07-28

This document tracks the next seven planning integrations needed to move BEAST from a governed coding loop to a stronger agentic coding runtime. Each integration is treated as a durable planning surface, not just a prompt tweak.

## Phase 1: Multi-File Execution Planning

Goal: give mutating runs a durable execution plan before the model starts spending turns.

Planning integration:
- Seed a bounded objective-plan workspace for mutating runs.
- Prefer worktree-backed execution when scope is multi-file or cross-cutting.
- Track plan steps for inspect, bind, mutate, verify, and SourcePlan handoff.
- Keep the plan record-only and non-authoritative.

Initial implementation target:
- Auto-seed the durable objective plan for governed mutating runs.
- Include context-file and objective-derived success criteria.
- Reuse the existing `ObjectivePlanWorkspace` instead of creating a parallel planner ledger.

Exit signal:
- A new mutating run starts with a visible durable plan spine before the first edit.

## Phase 2: Repair Autonomy Planning

Goal: make repair loops more surgical and less model-guessy.

Planning integration:
- Convert verifier failures into explicit repair tasks.
- Track file, symbol, failure class, and retry scope as plan state.
- Bound retries by residual class rather than generic turn count.

Exit signal:
- Failed verification creates a repair-specific plan update rather than only raw stderr.

## Phase 3: Latency Observability Planning

Goal: explain slowness at the same level the operator experiences it.

Planning integration:
- Attach latency budgets and actual timings to planner turns, tool calls, and verifiers.
- Surface prompt size, context size, fallback count, and enforcement count in the run console.
- Make slow-path diagnosis part of the durable run record.

Exit signal:
- The IDE can answer why a run feels slow without external logs.

## Phase 4: Model Routing Planning

Goal: route different planning jobs to the cheapest competent route.

Planning integration:
- Split trivial next-action routing from harder repair and summary tasks.
- Prefer deterministic or tiny-model planning first.
- Escalate only when the task class requires it.

Exit signal:
- Planner route choice becomes explicit, durable, and task-class aware.

## Phase 5: Continuity and Resume Planning

Goal: let runs pick up where they left off without re-deciding obvious state.

Planning integration:
- Persist prior failed strategies and avoid repeating them.
- Resume active step, pending repair, and verification context directly from durable state.
- Rebuild working memory from the plan and latest evidence.

Exit signal:
- A resumed run continues with the correct active step and repair context.

## Phase 6: IDE Planning Surfaces

Goal: make the plan visible and navigable in the desktop IDE.

Planning integration:
- Show live plan graph, active step, repair cycle, and latency envelope.
- Expose why a step was chosen and what evidence supports it.
- Connect worktree, verification, approvals, and SourcePlan views back to the same plan spine.

Exit signal:
- The operator can navigate the run through its plan rather than only a flat event log.

## Phase 7: Delegated Planning

Goal: allow bounded subtask delegation without losing governance.

Planning integration:
- Represent delegated investigations and patch preparation as child plan branches.
- Merge child findings back into the parent durable plan.
- Keep authority and evidence scoped per delegated branch.

Exit signal:
- BEAST can split an objective into bounded sub-investigations and rejoin them safely.
