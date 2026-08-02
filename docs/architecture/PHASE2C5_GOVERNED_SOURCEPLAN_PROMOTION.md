# Phase 2C.5: Governed SourcePlan Promotion

Phase 2C.5 closes the AgentRun execution loop with deterministic, operator-gated promotion.

## Invariants

1. The agent tool registry contains no promotion tool.
2. Evaluation produces an immutable digest-bound receipt, never a write.
3. Eligibility requires a valid event chain, bound worktree, current verification epoch, SourcePlan draft, resolved translation, valid repair budget, a non-cancelled run, and passing verification evidence.
4. Eligibility creates a pending approval bound to the exact receipt digest and mutation epoch.
5. Promotion requires an approved resolution naming the human operator.
6. Evidence is re-evaluated immediately before promotion; drift blocks the action.
7. Promotion creates a commit candidate only in the isolated worktree. It never applies to the operator checkout.

## Routes

- `POST /edgek/agent-runs/{run_id}/promotion/evaluate`
- `GET /edgek/agent-runs/{run_id}/promotion`
- `POST /edgek/agent-runs/{run_id}/promotion/commit-candidate`
