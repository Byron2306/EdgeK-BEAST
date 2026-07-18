# BEAST IDE — VS Code parity program

This program measures parity by complete operator journeys. A surface is not
"supported" merely because an executable or route exists.

## Operator journey

```text
First load
  -> choose and index workspace
  -> define mission and success outcome
  -> trust + tools + protocol preflight
  -> edit with Monaco, LSP, and BEAST AI
  -> stage mutations as SourcePlan
  -> review checks and approval gates
  -> collect evidence
  -> crystallise verified reusable compute
```

The persistent **Mission Journey** launcher can reopen this runway at any time.
Starting a mission carries its objective directly into the editor copilot.

## Capability matrix

The current desktop tranche adds an explicit developer-runtime workbench: DAP sessions when an adapter is installed, receipt-backed Python cells, verified SSH workspace probing with bounded remote indexing, and user-controlled SSH forwards/reverse development tunnels. These are operator-triggered capabilities, not renderer shell access. See [ADR-015](architecture/adr-015-governed-developer-runtime-workbench.md) and [ADR-017](architecture/adr-017-governed-ssh-forwarding.md).

| Track | Current milestone | Daily-driver acceptance boundary |
|---|---|---|
| Workspace/editor | Monaco tabs, explorer, split view, persistent buffers, governed files; keyboard-first quick open (`Ctrl/Cmd+P`), command palette (`Ctrl/Cmd+Shift+P`/F1), editor breadcrumbs, bounded workspace text search, preview-first replace, and a Source Control workbench with index/worktree Monaco diffs, grouped changes, file/all staging, commit receipts, branch create/switch, status-bar entry, and `Ctrl/Cmd+Shift+G`; declared npm and `.vscode/tasks.json` tasks, streamed/cancellable task sessions, watch readiness, and clickable problem-matcher diagnostics | Merge/conflict editor, history graph and remotes, hunk staging, compound task dependencies/presentation groups, and multi-root workspaces |
| AI coding | Conversation-first Pair Programmer with advisory Ask auto-routing, authoritative live file-scope locking, token-streamed Ask answers, semantic live Agent/Edit draft timelines, full-height workbench layout, exact crystal reuse, Action IR normalization, empty-plan and syntax repair, isolated allowlisted verifier execution, automatic Monaco hunk previews, per-file before/after review, and SourcePlan staging | Broader repository tool loop, dependency-aware test selection, and full isolated-worktree execution |
| Language servers | Process-isolated LSP host; TypeScript/JavaScript, Pyright, pylsp, Go gopls, Bash, JSON, HTML, and CSS ready; Rust Analyzer and clangd expose verified one-click system provisioning; completion, hover, definition, diagnostics, references, rename, actions, formatting, and symbols wired to Monaco | Semantic tokens, workspace symbols, and multi-root lifecycle |
| Debugging | Socket-isolated `debugpy` and Delve DAP relays; Python/Go/native adapter selection, standards-correct launch/configuration order, breakpoints, stepping, stack/threads, variables, persisted watch expressions, debug console, and one-click LLDB provisioning | Attach configurations, compound launch/test matrix, and breakpoint-condition UX |
| Extensions | Isolated desktop extension-manifest host, bundled/workspace discovery, explicit persisted per-workspace grants, mediated VM execution, contributed-command buttons, and a grant-enforced `vscode` shim for commands, notices, workspace identity, bounded file search, and read-only file access | Hardened executable sandbox, broad versioned desktop `vscode.*` API, editor/diagnostic/tree/webview contributions, marketplace/install/update and compatibility suite |
| Notebooks | Native `.ipynb` workbench with code/Markdown cells, cell reorder/add/delete, persistent BEAST Python execution, retained outputs including safe PNG/text rendering, and normal local SourcePlan or verified remote save behavior | Cell Monaco editors, broader rich mime, notebook trust prompts, and interactive widget support |
| Remote development | Strict-host-key SSH verification, bounded remote indexing/read/write APIs, fixed-text remote workspace search with editor handoff, reconnect, persistent SSH-TTY shell sessions with bounded I/O, explicit one-shot commands, loopback-only local forwards (`-L`) and reverse dev tunnels (`-R`); Docker transport discovery | File watching, secrets, workspace identity, remote process/task lifecycle, and remote extension placement |
| Trust/tools | Existing Trust, Tooling Forge, MCP approvals and Safety Governor integrated into first-run preflight | Per-workspace trust prompts and capability grants matching every extension/protocol action |
| Proof/reuse | SourcePlan, Review, Evidence, rollback and Crystal surfaces linked in the journey | One-click handoff state, no dead ends, complete acceptance telemetry and recovery paths |

## Foundation architecture

- [`desktop-ide/ide-compatibility-host.js`](../desktop-ide/ide-compatibility-host.js)
  owns allowlisted protocol process discovery, lifecycle, framing, and timeouts.
- [`desktop-ide/renderer/js/beast-ide-compatibility.js`](../desktop-ide/renderer/js/beast-ide-compatibility.js)
  maps LSP results into Monaco providers and diagnostics.
- [`desktop-ide/renderer/js/beast-onboarding.js`](../desktop-ide/renderer/js/beast-onboarding.js)
  owns the first-load and persistent mission journey.
- [`ADR-014`](architecture/adr-014-ide-ecosystem-compatibility.md) records
  why BEAST uses a protocol-native host plus the existing VS Code companion.
- [`ADR-020`](architecture/adr-020-mediated-source-control-workbench.md) records
  why Source Control uses bounded main-process Git contracts and structured
  renderer state instead of exposing a shell.
- [`ADR-021`](architecture/adr-021-conversation-first-ai-workbench.md) records
  why Pair Programmer uses progressive disclosure and a persistent Focus mode
  while retaining governed context, crystal reuse, and SourcePlan review.
- [`ADR-022`](architecture/adr-022-bounded-ai-proposal-validation.md) records
  why AI edits are validated and repaired before SourcePlan review, with only
  allowlisted verifier commands executed inside a temporary isolated workspace.

## Verification

```bash
cd desktop-ide
npm run smoke:parity
BEAST_VERIFY_DAP=1 npm run smoke:parity
BEAST_VERIFY_DAP=1 BEAST_VERIFY_KERNEL=1 npm run smoke:parity
npm run smoke
npm run smoke:launch
```

The parity smoke performs real TypeScript, Python, Bash, and Go language-server
initialize handshakes. With `BEAST_VERIFY_DAP=1`, it performs real loopback
`debugpy` and Delve Debug Adapter Protocol handshakes and launches a Python
debuggee through configuration to a stopped process. Static discovery alone is
not accepted as protocol readiness. `BEAST_VERIFY_KERNEL=1` executes a cell
through the persistent bundled Jupyter kernel.
