# Phase 2C.3: Worktree Mutation Plane

Phase 2C.3 binds AgentRun mutation to Worktree Forge. The operator workspace is never a mutation target.

## Tools

- `worktree.bind`: creates and durably binds an isolated Git worktree.
- `worktree.write_file`: bounded UTF-8 creation or replacement inside the worktree.
- `worktree.replace_exact`: exact occurrence-checked replacement inside the worktree.
- `worktree.verify`: explicit argv execution without a shell, inside the worktree.
- `worktree.diff`: read-only diff inspection.
- `worktree.sourceplan_draft`: non-applying SourcePlan synthesis after passing verification.

Mutation and execution tools require a run-scoped approved capability. Promotion remains unavailable to the agent.
