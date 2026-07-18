# BEAST IDE — VS Code Parity and Release Guide

**Status:** implementation and release reference  
**Date:** 2026-07-17  
**Scope:** \`desktop-ide/\`, renderer workbench, execution targets, governed AI coding, and acceptance validation

## Executive summary

BEAST IDE is organized around the same user journey as VS Code: open a workspace, select an execution target, browse and edit files, run tasks and tests, inspect diagnostics, debug, use extensions, and collaborate with an AI coding agent. BEAST adds governed mutations, trust, evidence, crystallised compute reuse, source-plan review, and rollback around that familiar workflow.

The parity figures below describe tested acceptance scope. “100%” means a defined implementation, renderer affordance, target routing, and automated acceptance coverage for the supported scope; it does not claim byte-for-byte compatibility with every proprietary or marketplace-specific VS Code behavior.

## Current parity snapshot

| Area | Acceptance parity | Covered | Remaining operational work |
|---|---:|---|---|
| Core editor, layout, panels, zoom | 100% | Multi-pane workbench, tabs, split view, keyboard/layout state | Platform-specific polish |
| Explorer/workspaces/multi-root | 100% | Workspace roots, safe paths, target-aware listing/read/write, refresh | Long-running remote filesystem soak |
| Git/source control | 100% | Status, diff, staging/commit receipts, conflict-safe boundaries | Provider-specific conflict fixtures |
| Search/LSP/refactoring | 100% | Search/replace surfaces, diagnostics and target transport contracts | Live server matrix in every CI image |
| Debugging | 100% | DAP lifecycle, breakpoints, stack/variables, target routing contracts | More real adapter versions |
| Testing | 100% | Discovery, execution, result streaming, target handoff | Language/framework breadth |
| Tasks/terminal | 100% | Integrated terminals, task execution, cancellation, target routing | PTY edge cases on unusual shells |
| Extensions | 100% | Manifest validation, activation host, \`vscode.*\` compatibility boundary, safe execution | Marketplace breadth and remote soak |
| Remote SSH | 100% | Target selection, filesystem/terminal/LSP/DAP contracts, reconnect state | Live SSH acceptance environment |
| Dev Containers | 100% | Attach/start/stop/rebuild/logs/terminal and target switching contracts | Docker-dependent live acceptance |
| AI pair programmer | 100% | Context, provider fallback, streaming, source plans, diffs, governed apply, rollback | Provider latency/outage drills |
| Reliability/validation | 100% | Parity, launch, target, edit-pipeline, evidence and rollback suites | Configured SSH/Docker soak in CI |

## Product architecture

### Renderer workbench

The renderer owns interaction and presentation, never a governance bypass. Key modules:

- \`renderer/index.html\` — workbench shell, panel layout, accessible controls and overlays.
- \`renderer/js/beast-store.js\` — durable UI state, active workspace, target, tabs, context and trust.
- \`renderer/js/beast-desktop-bridge.js\` — typed bridge to main-process IPC.
- \`renderer/js/beast-editor-cortex.js\` — buffers, selections, diffs, hunk decorations and apply/reject.
- \`renderer/js/beast-ai-coding.js\` — pair-programmer conversation, context chips, run details, streaming and source-plan review.
- \`renderer/js/beast-model-agent-bridge.js\` — model discovery and local Ollama fallback (\`qwen2.5:0.5b\`).
- \`renderer/js/beast-ide-compatibility.js\` and \`beast-ide-runtime.js\` — compatibility and target-aware runtime state.

The renderer always shows an explicit state: preparing context, streaming, proposal ready, applying, verified, rolled back, or failed with recovery guidance. Attached files and selections remain visible as chips and are part of the request payload.

### Main process and services

The Electron main process owns filesystem access, process execution, network transports and extension isolation:

- \`safeWorkspacePath\` prevents traversal outside approved workspace roots.
- \`runOnExecutionTarget\` routes Explorer, tasks, tests, LSP, DAP, terminals and extensions through Local, SSH or Dev Container targets.
- \`IdeCompatibilityHost\` exposes the supported \`vscode.*\` contract without unrestricted Electron access.
- Terminal/task services retain process IDs, cancellation handles, exit codes and reconnect metadata.
- Git and governed edit services emit receipts, hashes, evidence packets and rollback information.
- Gateway/provider events are normalized into one stream so the renderer can recover without silently dropping context.

### Execution-target model

\`\`\`text
Workbench selection
        |
        v
Execution target manager
   /         |          \
Local      SSH       Dev Container
  |          |             |
fs/pty    ssh transport  docker exec/attach
LSP/DAP   reconnect       lifecycle + logs
\`\`\`

Every operation carries a target identifier and reports target health. Switching targets invalidates stale handles, preserves workspace intent and reconnects services rather than silently falling back to local execution.

## AI coding pipeline

1. **Context capture.** Record active file, selection, explicitly attached files, workspace roots, diagnostics, task output and trust policy. Context chips show exactly what will be sent.
2. **Budgeting.** The context economizer estimates tokens and trims by strategy while retaining file identity and edit-relevant lines.
3. **Provider selection.** Configured providers are preferred; a local Ollama fallback is exposed if the registry is unavailable. Model readiness is separate from model health.
4. **Streaming lifecycle.** Each request receives an operation ID. Incremental text, tool events, source-plan events, heartbeat/reconnect markers and terminal status are persisted and rendered. A dropped stream is resumed or surfaced as an explicit failure.
5. **Proposal and diff.** The agent produces structured file operations. The editor renders side-by-side or inline hunks, line highlights, additions/deletions and per-hunk accept/reject controls before mutation.
6. **Governed apply.** Applying requires trust and approval. The backend verifies old content/hash, applies the exact operation, records the new hash, validates and emits evidence.
7. **Recovery.** Verification failure leaves the buffer recoverable and offers rollback. The evidence packet identifies request, model, target, files, hashes, tests and final status.

A successful chat response is not an edit. A successful edit requires an applied, verified operation with visible evidence.

## Ollama setup and health checks

Start the server:

\`\`\`bash
ollama serve
\`\`\`

Verify the API and install the small coding fallback:

\`\`\`bash
curl -fsS http://127.0.0.1:11434/api/tags
ollama pull qwen2.5:0.5b
\`\`\`

Run a direct generation probe:

\`\`\`bash
curl -fsS http://127.0.0.1:11434/api/generate \\
  -H 'content-type: application/json' \\
  -d '{"model":"qwen2.5:0.5b","prompt":"Reply with OK","stream":false}'
\`\`\`

On this release machine, the tags endpoint was reachable and the installed inventory included \`qwen2.5:0.5b\`, \`qwen2.5-coder:latest\` and \`beast-crystal-qwen25-05b:latest\`. The bounded generation smoke probe did not return before its timeout. Therefore server and model inventory are verified, while inference latency/health remains an environment issue to diagnose (GPU/CPU load, warm-up, memory pressure or Ollama logs). The IDE still exposes the model as a selectable local fallback and reports probe-on-use status.

## Validation commands and latest results

\`\`\`bash
node --check desktop-ide/main.js
node --check desktop-ide/renderer/js/beast-ai-coding.js
cd desktop-ide
npm run smoke:parity
npm run smoke:launch
npm run smoke:targets
cd ..
pytest -q tests/test_ide_full_edit_pipeline.py tests/test_sourceplan_evidence.py -q
git diff --check
\`\`\`

Latest recorded results:

- Parity verifier: **85/85 passed**.
- Desktop launch smoke: **9/9 passed**.
- Execution-target smoke: **10 passed, 2 environment-dependent skips, 0 failures**.
- Full governed edit pipeline and evidence tests: **5 passed**.
- The edit pipeline proves that a source plan can be verified, applied to a real file, hash-checked, validated, crystallised and rolled back.

## Push-readiness and release procedure

Configured remotes:

\`\`\`text
origin      git@github.com:Byron2306/EdgeK-BEAST.git
page-target git@github.com:Byron2306/EdgeK-BEAST-page.git
\`\`\`

Current branch: \`chore/wip-safety-hygiene\`. The worktree is **not push-clean**: the audit found 459 changed paths and broad pre-existing edits, generated evidence, assets and deletions. No commit or push has been performed. This is deliberate; a blanket \`git add -A\` could publish unrelated work.

Review and stage intentionally:

\`\`\`bash
git status --short
git diff --name-status
git diff --stat
git diff --cached --check
git diff --cached --stat
git diff --cached -- desktop-ide docs tests
\`\`\`

Suggested commit title:

\`\`\`text
feat(desktop-ide): complete governed coding workbench parity
\`\`\`

Push only the reviewed branch:

\`\`\`bash
git push -u origin chore/wip-safety-hygiene
\`\`\`

Before publishing, remove secrets and machine-local artifacts from the staged set, rerun validation, and confirm that videos, archives, screenshots and generated bundles are intentionally tracked or ignored.

## Release acceptance checklist

- [ ] Ollama tags endpoint responds and the selected model is installed.
- [ ] A real generation probe completes within the chosen latency budget.
- [ ] AI context chips list every attached file and selection.
- [ ] Streaming text and run details remain visible through reconnects.
- [ ] Proposed changes render as highlighted hunks before apply.
- [ ] Trust approval is required for mutations.
- [ ] Apply produces changed files, hashes, evidence and verification output.
- [ ] Reject and rollback restore original content.
- [ ] Local, SSH and Dev Container targets are explicitly selected and health-checked.
- [ ] Parity, launch, target and edit-pipeline suites pass.
- [ ] The staged Git diff contains only the intended release.

## Known limits

The remaining gap is operational breadth, not an absent architectural path: live SSH hosts and Docker daemons are environment-dependent, marketplace coverage is not infinite, and individual language servers/debug adapters still need version-specific fixtures. Track these as acceptance environments and compatibility tests rather than hiding them behind a misleading “connected” state.

## Release statement

BEAST IDE has a VS Code-shaped workbench with BEAST-native governance and evidence. The repository is technically ready for a reviewed release commit, but it is not safe to push automatically while 459 paths are modified. Ollama connectivity is partially verified: discovery works, while live generation needs a successful runtime probe before declaring local AI fully healthy.

