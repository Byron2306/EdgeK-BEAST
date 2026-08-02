# Remote IDE Implementation Notes

**Date:** 2026-07-28

## Why this exists

BEAST already has target-aware approval language, remote Commons transport, and planner/runtime routing, but it still needs stronger remote workspace execution to reach practical parity with major IDE remote-development flows.

This note anchors the next implementation phases against the current public models used by VS Code Remote Development and JetBrains Remote Development.

## Observed platform patterns

### VS Code Remote SSH

- A local client connects to a remote host and installs or reuses a remote server component.
- The remote server hosts extensions that need direct filesystem and tool access.
- Remote terminals, debugging, and most workspace operations execute on the remote host, not by replaying local actions.
- The client keeps a strong remote identity and reconnect path rather than silently falling back to local execution.

### VS Code Dev Containers

- A `devcontainer.json` contract describes how to create or attach to a development container.
- The workspace can be mounted, copied, or cloned into the container.
- Extensions run inside the container when they need container-local tools and filesystem access.
- Port forwarding, lifecycle hooks, and predictable environment bootstrapping are first-class parts of the contract.

### JetBrains Remote Development

- A thin client connects to an IDE backend running on a remote host.
- The backend performs indexing, analysis, build, run, debug, and test execution.
- SSH is only one entry path; orchestration and dev-container-backed flows are also part of the model.
- The important architectural split is durable backend session ownership with reconnectable client views.

## BEAST gaps to close

1. Durable remote workspace sessions
- We need a first-class session object for `local`, `ssh`, and `devcontainer` targets that owns process lifecycle, health, reconnect state, and capability probes.

2. Remote extension host parity
- Current docs describe explicit target deployment, but BEAST still needs a real remote extension lifecycle service with install, enablement, versioning, health, and restart behavior per target.
- Status: partially implemented. Desktop now tracks per-target extension lifecycle, runtime preflight, deployment, discovery, execution, and stop state, and acceptance includes a real mediated extension command workload. Remaining work is broad `vscode.*` compatibility, marketplace/update semantics, richer contribution points, and a larger real-extension workload matrix.

3. Dev container contract ingestion
- Approval and target vocabulary exists, but BEAST still needs native `devcontainer.json` parsing and lifecycle semantics for mounts, features, post-create/update hooks, env injection, and forwarded ports.

4. Remote watch and invalidation semantics
- Large-repo parity depends on file watching, invalidation, and change propagation that behave correctly over SSH and container boundaries.

5. Target-owned tool execution
- The agentic loop should bind tool observations, edits, tests, terminals, and verifier runs to the active target session so the planner reasons over the real execution environment.
- Status: implemented for backend AgentRun read/mutate/verify/diff/sourceplan/promotion-candidate/final-apply lanes. `workspace.list`, `workspace.read_range`, `workspace.search_text`, `workspace.index`, `worktree.bind`, `worktree.write_file`, `worktree.replace_exact`, `worktree.verify`, `worktree.diff`, and `worktree.sourceplan_draft` now execute through SSH/Docker targets with strict target/path validation, target-side isolated worktrees, target-side verifier receipts, and target-side Git diff evidence. Remote SourcePlan drafts can now flow through receipt-bound human approval into target-side Git commit candidates, then through a second receipt-bound final-apply approval into target-side fast-forward merge with rollback refs, without mutating the operator workspace. Live acceptance now covers planner-driven fail/repair/reverify loops; remaining work is broader coverage across larger repo shapes.

6. Remote session recovery
- Reconnect should preserve target identity, terminal handles, active jobs, and agent run continuity after transient transport loss.

7. Live acceptance matrix
- Real parity needs CI fixtures for strict-host-key SSH and Docker/devcontainer paths, not only local protocol checks and static transport assertions.
- Status: implemented for disposable strict-host-key SSH and Docker target-side governed mutation/final-apply, plus planner-driven multi-turn remote CI loops that intentionally fail verification, repair, reverify, draft SourcePlan evidence, create a remote commit candidate and perform final target-side apply. The IDE-services parity fixture also unifies LSP, DAP, test explorer, SCM, and extension workload readiness. Remaining work is making these always-on across a broader CI matrix and adding long-running soak/reconnect workloads.

8. Unified IDE readiness spine
- VS Code-grade parity requires one coherent health model for language intelligence, debug adapters, test explorer, source control, and extension host state rather than independent panel-level checks.
- Status: implemented as `beast_ide_services_snapshot`, exposed through Electron IPC/preload/runtime and accepted by `verify-ide-services-parity.js`.

9. Target-aware workspace index
- Agentic parity requires a workspace index that summarizes files, languages, imports, symbols, tests, SCM freshness and target identity before an agent chooses reads, edits, or verification.
- Status: implemented as `beast_workspace_index_snapshot`, exposed through Electron IPC/preload/runtime, folded into IDE services scoring, and accepted against a mixed JS/Python/Nim fixture. Remote SSH/container targets now run a target-side deep index extractor that preserves file, language, test, import and symbol shape for agent planning.

10. Index-first agentic loop gates
- A true coding agent loop must not allow a model to skip from prompt to completion. The controller should enforce evidence-first inspection, isolated mutation, verifier execution, repair if needed, and SourcePlan handoff before declaring success.
- Status: implemented in the backend AgentRun planner runtime. `workspace.index` is now a read-only agent tool for local/SSH/container targets, heuristic fallback starts with the index, prompt compaction preserves index summary/files/symbols, phase enforcement requires inspect/bind/mutate/verify/handoff, and completion is rejected until `worktree.verify` and `worktree.sourceplan_draft` are both fresh after mutation.

## Recommended implementation order

### Phase A

- Introduce a durable target-session registry shared by Explorer, terminal, tasks, tests, LSP, DAP, extensions, and agent runs.
- Make all target-aware services depend on that registry rather than ad hoc target strings.

### Immediate next steps

1. Make agent runs target-session-native.
- Carry durable target session identity from the IDE into AgentRun creation, planner telemetry, tool execution context, verifier receipts, and recovery events.
- Status: implemented for AgentRun request normalization, planner prompt context, tool execution context, verifier receipts, and direct tool calls.

2. Add targeted verifier and test planning.
- Let the planner choose the smallest relevant verify/test command from changed files, recent failures, and workspace test catalog.
- Status: implemented with a deterministic verification planner, focused pytest/Vitest/Jest selection for changed test files, workspace-index related-test selection for Python/JS/TS imports, source compile gates, and target-aware prompt hints.

3. Add remote watcher and invalidation semantics.
- Preserve correctness for SSH/devcontainer sessions when files change outside the active editor or active tool loop.
- Status: implemented as execution-target polling watchers for SSH/container workspaces, routed through the existing workspace-watch IPC stream with target session metadata.

4. Add remote extension-host lifecycle state.
- Track per-target install, deploy, health, runtime preflight, and restart status.
- Status: implemented with per-target extension lifecycle state, runtime preflight/deploy/discover/execute/stop events, status IPC, renderer runtime state, and module-boundary acceptance checks.

5. Add live remote acceptance fixtures.
- Run disposable strict-host-key SSH and devcontainer/compose acceptance in CI, including multi-turn agent runs.
- Status: implemented for disposable live Docker/devcontainer and strict-host-key SSH fixtures. Environment-gated live acceptance now covers planner-driven index -> bind -> mutate -> failed verify -> repair -> reverify -> SourcePlan -> remote commit candidate -> final target-side apply for Docker container targets and disposable sshd targets with temporary keys and generated `known_hosts`. Remaining work is broadening the matrix to larger repo fixtures, reconnect interruption tests and long-running soak.

### Phase B

- Add `devcontainer.json` ingestion and normalized workspace-target descriptors.
- Persist port forwards, lifecycle hooks, env projection, and container capability probes.

### Phase C

- Implement remote extension-host lifecycle management.
- Add remote watcher streams and reconnect-safe invalidation.

### Phase D

- Run live acceptance against disposable SSH and devcontainer fixtures.
- Make agent planner/tool verification runs consume the same target session abstraction.

## Reference sources

- VS Code Remote Development overview: https://code.visualstudio.com/docs/remote/remote-overview
- VS Code Remote SSH: https://code.visualstudio.com/docs/remote/ssh
- VS Code Dev Containers: https://code.visualstudio.com/docs/devcontainers/containers
- Dev Container Specification: https://containers.dev/overview
- JetBrains remote development overview: https://www.jetbrains.com/help/idea/remote-development-overview.html
- JetBrains Gateway: https://www.jetbrains.com/help/idea/remote-development-a.html
