# Phase 2C.1: Typed Tool Plane

Phase 2C.1 introduces the first provider-neutral tool execution boundary for durable AgentRuns.

## Guarantees

- Tools are registered through `AgentToolRegistry` using immutable `ToolSpec` contracts.
- Every tool declares risk, effect, input schema, target support, timeout, output limit, approval policy, and worktree requirement.
- `AgentToolRuntime` validates authority before invoking a handler.
- Workspace paths are resolved beneath the declared root and traversal escapes are rejected.
- Tool start, completion, and failure are written to the durable AgentRun event chain.
- Completed results become structured `ToolObservation` objects with evidence digests.
- The runtime checkpoints the latest observation for replay and future planner turns.
- Promotion tools are categorically denied to autonomous execution.

## Initial built-in tools

- `workspace.list`
- `workspace.read_range`
- `workspace.search_text`
- `git.status`

All four are read-only. Mutating tools are intentionally deferred until Worktree Forge is bound into the tool context.

## New API

- `GET /edgek/agent-runs/{run_id}/tools`
- `POST /edgek/agent-runs/{run_id}/tools/{tool_id}/execute`

These endpoints expose the same registry and runtime that the Phase 2C planner will consume. They are not a parallel debug-only implementation.

## Next seam

Phase 2C.2 adds a bounded planner loop that asks the selected model for one typed action at a time, executes through this registry, and returns the observation to the same durable run.
