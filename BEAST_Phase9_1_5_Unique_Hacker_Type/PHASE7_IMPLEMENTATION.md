# BEAST Phase 7 Implementation

## Terminal Nexus, Tooling Forge, and Doctor Diagnostics

Phase 7 transplants the remaining operational utility plane into BEAST Core Shell v2 without restoring any legacy renderer ownership.

## Architectural contract

- One `#beastPageOutlet`
- One `#beastContextRail`
- One router owner
- One mascot controller
- One Phase 7 application owner
- No `app.js`, `opcb-renderers.js`, `opcb-state.js`, or legacy Studio integration runtime
- Page subscriptions and streams are disposed when their owning page or shell is destroyed

## High-definition graphics cleanup

Phase 7 introduces four new 1024×1024 transparent-center nine-slice masters:

- `panel-hd-neutral.png`
- `panel-hd-cyan.png`
- `panel-hd-amber.png`
- `panel-hd-danger.png`

They replace contaminated sheet crops and share one controlled `border-image` geometry. The centre remains real HTML, so cards scale without stretching text or baking labels into artwork.

The green treatment is a travelling signal current inside neutral chrome. It strengthens on hover, focus, selection, warning, and active execution rather than permanently painting every edge fluorescent green.

## Terminal Nexus

The Terminal page owns a governed command lifecycle:

1. Classify the command through the Safety Governor.
2. Display decision, risk, reasons, working directory, and evidence requirements.
3. Require explicit operator approval for governed mutation classes.
4. Stream stdout, stderr, heartbeat, and completion events.
5. Persist workspace-scoped command history and execution receipts.
6. Support cancellation without rebuilding the page.

Primary contracts:

- `POST /edgek/safety-governor/classify-command`
- `GET /edgek/ide/terminal/stream` via `EventSource`

Terminal controls include classification, execution, cancellation, CWD selection, timeout control, quick commands, output clearing, receipt copying, history, and recent execution inspection.

## Tooling Forge

The Tooling page combines the operational surfaces that were previously scattered across old Tooling, MCP, plugin, environment, and benchmark panels.

It provides:

- syntax and lint contract status
- MCP broker health
- server inventory and schema pins
- pending approval decisions
- plugin registry and manifest validation
- local runtime/environment inventory
- capability/action catalog
- recent MCP execution and audit records
- public grading daemon benchmark launch
- selected-module inspector

Primary contracts:

- `GET /edgek/ide/tooling-snapshot`
- `GET /edgek/mcp/state`
- `GET /edgek/mcp/servers`
- `GET /edgek/mcp/schema-pins`
- `GET /edgek/mcp/approvals`
- `GET /edgek/mcp/audit`
- `GET /edgek/mcp/executions`
- `GET /edgek/plugins`
- `POST /edgek/plugins/manifest/validate`
- `POST /edgek/mcp/approvals/{id}/{decision}`
- `POST /edgek/benchmarks/public-grading-daemon`

Electron-local tooling snapshots remain supported as a fallback.

## Doctor Diagnostics

Doctor performs a parallel deep scan rather than sequentially repainting a dashboard after each endpoint response.

The scan checks:

- Gateway root contract
- IDE snapshot
- action/capability manifest
- tooling snapshot
- system plane
- MCP broker
- plugin registry

It normalizes the results into one health score, contract checklist, route ledger, system-resource summary, port/process inspection, and repair recommendations. Gateway restart is available only through the Electron preload bridge and requires explicit operator confirmation.

Primary contracts:

- `GET /edgek/root-info`
- `GET /edgek/ide/snapshot`
- `GET /edgek/ide/actions/manifest`
- `GET /edgek/ide/tooling-snapshot`
- `GET /edgek/ide/system-snapshot`
- `GET /edgek/mcp/state`
- `GET /edgek/plugins`

## State ownership

`beast-store.js` now includes dedicated slices for:

- `terminal`
- `tooling`
- `doctor`

`beast-terminal-tooling-doctor-bridge.js` is the only network and persistence owner for these slices. Page renderers subscribe to store changes and patch targeted DOM regions. They do not replace the full page after live data arrives.

## Command dock routes

- `/terminal`
- `/terminal clear`
- `/terminal <command>`
- `/tooling`
- `/tooling refresh`
- `/tooling benchmark`
- `/doctor`
- `/doctor scan`

`/terminal <command>` stages a command in Terminal Nexus. It does not silently execute it.

## Responsive behaviour

The pages retain a single vertical scroll owner and collapse progressively:

- wide desktop: full primary and inspector columns
- medium desktop: inspector moves below primary content
- narrow desktop: metrics and controls stack
- reduced motion: scan, pulse, orbit, and current animations stop while state contrast remains

## Acceptance boundary

Static syntax, ownership, references, asset integrity, and backend-free capture-mode rendering are validated in this package. Final command streaming, Electron restart, filesystem CWD, MCP decisions, and live gateway health require acceptance inside the actual BEAST Electron runtime.
