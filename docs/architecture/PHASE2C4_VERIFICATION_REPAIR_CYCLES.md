# Phase 2C.4: Durable Verification-Driven Repair Cycles

Phase 2C.4 closes the loop between isolated mutation and proof. A failed `worktree.verify` call now returns its full structured observation to the planner, increments a durable repair counter, and emits explicit repair events. The planner may perform another bounded mutation and verification turn under the same AgentRun and worktree.

## Invariants

- Failed verification is evidence, not an unstructured exception.
- Repair cycles are bounded independently from planner turns.
- Every mutation increments `worktree_mutation_epoch`.
- Any mutation invalidates the previous verification receipt and SourcePlan checkpoint.
- SourcePlan synthesis requires a passing receipt whose `mutation_epoch` equals the latest worktree mutation epoch.
- Verification still uses direct argv execution without a shell.
- Promotion remains operator-only.

## Canonical events

- `agent.verification.failed`
- `agent.repair.required`
- `agent.verification.passed`
- `agent.repair.budget_exhausted`
- `agent.worktree.mutated`
