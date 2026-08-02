# BEAST IDE — VS Code Parity and Release Guide

**Status:** implementation and release reference

**Date:** 2026-07-18

**Scope:** \`desktop-ide/\`, renderer workbench, execution targets, governed AI coding, and acceptance validation

## Executive summary

BEAST IDE is organized around the same user journey as VS Code: open a workspace, select an execution target, browse and edit files, run tasks and tests, inspect diagnostics, debug, use extensions, and collaborate with an AI coding agent. BEAST adds governed mutations, trust, evidence, crystallised compute reuse, source-plan review, and rollback around that familiar workflow.

BEAST is now a capable governed development workbench, not a VS Code clone. The important distinction is that VS Code optimizes for broad, mature editor ecosystem compatibility while BEAST optimizes for controlled execution, reviewable mutation, evidence, and reusable verified work. The parity figures below therefore measure practical daily-driver coverage against the most common VS Code journeys. They are not a claim of byte-for-byte compatibility with VS Code or its marketplace.

## Honest current-state assessment

### Where BEAST is today

The desktop workbench can be used for real repository work: open multi-root workspaces, edit in Monaco, search and replace with previews, run tasks and terminals, inspect Git changes, use installed language servers and debuggers, work with notebooks, attach remote targets, and ask the Pair Programmer for a governed change proposal. The normal mutation path is deliberately different from VS Code: AI-generated or system-mediated edits become a SourcePlan, are shown as diffs, validated, approved, applied with exact-content guards, and backed by rollback/evidence.

That makes BEAST particularly strong when the work must be attributable and reversible. It is less mature than VS Code where the value comes from the enormous extension ecosystem, years of language-specific UX refinement, and the operational breadth of Remote Development.

### Scoring model: implementation is not operational maturity

Each percentage below is a weighted estimate of four questions: is the user surface present (25%), is there a bounded main-process/backend contract (25%), is the main journey automatically exercised (30%), and has it been run against the relevant live runtime (20%). This deliberately prevents a static string check from being counted as the same thing as a real SSH host, Docker engine, debugger, or model run.

- **Implementation coverage:** **78%**. Most daily desktop journeys have an implementation and a visible workbench surface.
- **Automated acceptance coverage:** **about 80%**. The complete local protocol suite is green; external SSH and Compose-specific runtime checks remain optional.
- **Operational maturity:** **about 64%**. Local workflows and a generic Docker target are now exercised, while real SSH and Compose-specific acceptance are still missing.

These are planning estimates, not benchmark results. A capability is only called *live-verified* when a real external process or service is exercised. “Protocol-ready” means a real local handshake may exist; it does not mean every adapter/version/environment is supported.

## Current parity snapshot

| Area | Estimated VS Code parity | What works now | Important remaining gap |
|---|---:|---|---|
| Core editor, layout, panels, zoom | 91% | Monaco editing, tabs, split views, persistent panel/shell sizing, zoom, quick-open, command palette, keyboard flows and window-state persistence | Editor groups, profiles, deeper accessibility auditing and platform-scale performance work |
| Explorer/workspaces/multi-root | 87% | Persisted workspace folders, safe paths, target-aware list/read/atomic digest-checked write, root-aware LSP initialization and multi-root UI controls | Reliable file watching, remote watcher semantics, large-repo indexing and folder lifecycle soak |
| Git/source control | 82% | Status/diffs, index/worktree view, file and hunk actions, conflicts, history, remotes, branch/commit, fetch/pull/push, rebase and cherry-pick controls | Graph/timeline quality, richer three-way merge UX, multi-repository ergonomics and real remote-operation test coverage |
| Search/LSP/refactoring | 81% | Bounded search/replace, diagnostics, completion, hover, definition, references, rename, actions, formatting, document symbols, semantic tokens and workspace-symbol requests | Per-language feature consistency, richer code-action/refactor UX and a CI image with every server installed |
| Debugging | 80% | DAP launch/attach request handling, conditions/log messages/function breakpoints, stepping, stack/variables, console/watches, launch.json/compounds; local debugpy/Delve/LLDB and launch lifecycle accepted | Adapter-specific configuration breadth, attach-to-process discovery, exception/data breakpoints and a broad cross-platform test-debug matrix |
| Testing and notebooks | 78% | Workspace tests, individual pytest nodes, failure navigation/debug handoff, target routing; `.ipynb` editing and a locally accepted persistent Python-kernel path | Framework breadth, rich notebook MIME/widgets, trust UX, test history and other language test adapters |
| Tasks/terminal | 82% | Persistent local/remote terminals, declared VS Code tasks, cancellation, watch readiness, problem matchers and target routing | PTY edge cases, shell portability, task dependency/presentation behavior and sustained remote sessions |
| Extensions | 80% | Command-palette discovery, grants validated against the active target, enable/disable, managed workspace install/remove, explicit atomic deployment to SSH/container, target-aware activation, Node.js preflight, bounded failure diagnostics, and a mediated VM/shim; executable lifecycle passes | Marketplace/update, broad `vscode.*`, webview/tree/editor contributions and broader sandbox hardening remain unfinished |
| Remote SSH | 80% | Strict-host-key transport, workspace/runtime health checks, remote files/search/atomic digest-checked saves, persistent terminals, reconnect, loopback forwarding, explicit workspace-extension deployment/runtime preflight, and remote LSP/DAP stdio relay | Real-host CI, file watching, secrets, remote process lifecycle and reconnection soak |
| Dev Containers | 75% | Image/Dockerfile/Compose inspect/start/attach/stop/restart/rebuild/log/terminal actions, published-port discovery/opening, selected execution target, explicit workspace-extension deployment and container LSP/DAP transport; generic Docker target acceptance passed | Feature/mount parity, container extension lifecycle and Docker-backed CI acceptance |
| AI pair programmer | 80% | Explicit context locking, native provider streaming, Action IR/SourcePlan, isolated validation, diff review, rollback, retryable focused local-Qwen recovery, and a live compact local-Qwen route | A true iterative tool/observe/repair loop, reliable large local patches, test selection and resilient provider recovery |
| Reliability/validation | 80% | Syntax checks, seven local LSP handshakes, accepted local DAP/kernel paths, green extension lifecycle, Git lifecycle fixture, AI proposal fixture, visual checks and evidence/rollback tests | Continuous live SSH/Compose/provider matrices, load/soak testing and release telemetry |

### Evidence behind the numbers

The main local acceptance command is `desktop-ide/scripts/verify-ide-parity-foundation.js`. Assertion totals are generated by the verifier and must not be maintained manually in this guide. It does more than inspect files in a few important cases: it starts local LSP/DAP/kernels when available, creates a temporary Git repository to exercise status/staging/index/worktree diffs/conflict resolution, and simulates the AI proposal lifecycle. It also has structural assertions that prove wiring exists but cannot prove a real external service works. That distinction is recorded in `contracts/beast-parity-contract.v1.yaml`.

The execution-target checker (`verify-execution-target-parity.js`) verifies that Explorer, tasks, tests, LSP, DAP and extensions receive the selected target, and that SSH/container protocol paths use real stdio transport definitions. Its live SSH and container checks are **environment-gated** through `BEAST_PARITY_SSH_HOST` and `BEAST_PARITY_CONTAINER_IMAGE`; they are skipped without those variables. Therefore SSH and Dev Container scores are not allowed to exceed the high 60s yet.

Historical local runs reached a fully green provisioned matrix, including language-server, debugger, notebook, Git, extension, AI-proposal, and container probes. Those figures are snapshots, not permanent release facts. Current totals and skip reasons are generated into `build/PHASE0_STATUS.json`; external SSH and container claims remain environment-specific and must identify the target used. The deploy operation deliberately transfers only a validated manifest plus its bounded entrypoint and atomically replaces files for that extension ID; it does not mirror or delete arbitrary target files.

### Detailed capability audit

#### Workbench, editor, and workspace model

The renderer is no longer a single fixed dashboard. It has a routed workbench, persistent layout state, shell and in-workspace resizers, editor/explorer/assistant panels, zoom persistence, window-bound persistence, a keyboard command palette, quick-open, editor breadcrumbs, and a Monaco-backed editor cortex. Multi-root folders are persisted and are carried into LSP `workspaceFolders`; target-aware operations route through the desktop bridge rather than allowing arbitrary renderer filesystem access.

This is close to VS Code for the *basic editing loop*. The main remaining difference is polish and scale: VS Code has years of behavior around editor groups, restore rules, dirty buffers, file watching, virtual documents, workspace trust, profiles, accessibility and enormous trees. BEAST has the architectural seams for several of these, but they are not yet equally exercised under large repositories or hostile filesystem conditions.

#### Source control

The repository contains substantive Git functionality, not just a status badge. The main process exposes bounded Git status, diff, stage/unstage/discard, hunk actions, conflict parsing/resolution, history, remotes and guarded operations for fetch, fast-forward pull, push, rebase and cherry-pick. The workspace page renders history/remotes and exposes hunk/conflict/rebase/cherry-pick controls. The parity harness creates an actual temporary repository, stages changes, verifies index/worktree diffs, creates a conflict, and resolves it.

That supports the 82% score, but not full parity. The current history presentation is a list rather than a visual graph; merge resolution is a bounded workbench rather than VS Code’s fully refined merge editor; rebase/cherry-pick have controls but lack a wide scenario matrix; and multi-repository coordination has not been proven at the same level. The next Git work should be UX and live-operation hardening, not another basic wrapper around `git`.

#### Language intelligence and refactoring

The protocol host requests completion, hover, definition, references, rename, code actions, formatting, document symbols, semantic tokens and workspace symbols. The renderer registers Monaco semantic-token support and can issue `workspace/symbol` requests. The desktop package includes TypeScript, Pyright, pylsp, Bash and VS Code extracted language-server dependencies; Go, Rust and clangd are discovered/provisioned where available. The parity runner performs local initialize handshakes for TypeScript, Python, pylsp, Bash and Go, while Rust/clangd are conditional on installation.

The score remains below full parity because a request path is not identical to a consistently good language experience. BEAST still needs server-version compatibility tests, reliable progress/cancellation/restart behavior, multi-root semantics across all servers, richer rename/code-action previews, and user-visible fallback when a server provides only a subset of features. VS Code also has a far larger language-extension catalog.

#### Debugging

The DAP implementation has progressed beyond a launch button: it manages framed protocol sessions, supports `launch` and `attach`, protects the configuration-done order, routes local/SSH/container adapters through the protocol host, and exposes breakpoint condition, log message and function-breakpoint inputs. It reads `.vscode/launch.json`, launches named configurations, and starts compounds. With the local verification flags enabled, debugpy, Delve, LLDB, and a stopped-Python-debuggee launch all passed. This materially improves confidence in the local debugging path, but is not a claim of production-wide adapter or remote-debug readiness.

The missing 22% is meaningful: attach-to-process discovery/selection, adapter-specific schemas and UX, exception breakpoints, data breakpoints, test-debug workflows, child-process behavior and a persistent live-adapter version matrix all need work. The earlier `configurationDone` error is a reminder that DAP is sequence-sensitive; every new adapter path needs an actual protocol test.

#### Tasks, terminals, tests, and notebooks

The desktop host has bounded persistent local and remote terminal sessions, task parsing for supported `.vscode/tasks.json` task kinds, cancellation, background readiness and problem-matcher diagnostics. Test surfaces can discover/run workspace tests, target individual pytest nodes, navigate failures and hand a focused test to debugging. Notebook support has a native `.ipynb` workbench and persistent Python-kernel relay path.

This is useful for a Python/JavaScript-centric daily workflow, but it is not yet equivalent to VS Code’s task/test/notebook ecosystem. The greatest practical gaps are framework-specific discovery adapters, test result history, rich notebook output/widgets, cell-level Monaco behavior, terminal compatibility on unusual shells, and task dependency/presentation semantics.

#### Extensions

BEAST has a meaningful security posture here: extension manifests are discovered, grants are persisted per workspace, enablement is persisted, managed workspace extensions can be installed/removed, and code runs in a mediated VM context with a restricted `vscode` shim. Activation receives the selected execution target. This is ahead of a simple plugin registry.

It is still far from VS Code extension parity. The install path accepts BEAST-shaped extension folders, not Marketplace packages, and the shim does not provide broad editor, tree-view, webview, diagnostics, notebook, SCM or debug contribution APIs. The executable lifecycle is now a green local release gate, but the sandbox and API surface still need broader adversarial and compatibility testing. Extension parity must be measured as compatibility with a published supported API subset, not by counting manifests.

For remote and container targets, extension placement is now an explicit operator action in the Compatibility workbench: **Deploy to Active Target**. This avoids the unsafe illusion that a desktop-local extension path is usable by a remote process. Deployments are deliberately narrow and non-destructive to unrelated target extensions; target-local grants are still resolved from the desktop workspace policy when the host is started. The missing step is a full remote extension-management service with version/update state and a live SSH/Compose acceptance matrix.

#### Remote SSH and Dev Containers

SSH uses strict host-key checking, bounded remote search, atomic digest-protected remote saves, persistent remote terminal sessions, reconnect metadata and controlled loopback forwards. LSP/DAP can be launched over SSH stdio. Dev Container support can inspect, start, attach, stop, rebuild, show logs and run a terminal for image, Dockerfile and safe workspace-local Compose configurations. The selected execution target is propagated into multiple workbench services.

This is a credible foundation, but not a substitute yet for VS Code Remote Development. Live checks are optional, file watching and remote extension placement are incomplete, Compose/feature/mount support is narrower, and there is no evidence here of long-running real SSH/Docker soak. The right next proof is a CI matrix with a disposable strict-host-key SSH host and a Dev Container fixture, not more static transport code.

#### Pair Programmer and governed AI

BEAST’s AI lane is unusually complete at the *review and apply* end: attached files are displayed and locked, provider events are streamed, a model response is compiled to Action IR, exact operations are validated against source, isolated allowlisted checks can run in a temporary workspace, and the result enters SourcePlan review before approval, apply, evidence and rollback. This is where BEAST is most clearly differentiated from an ordinary chat panel.

The local Ollama route is now also technically healthy for compact work: `qwen2.5-coder:1.5b` uses native SSE and is deliberately limited to three files, 2,400 characters each and 1,024 output tokens. A live end-to-end probe delivered a first token in roughly four seconds and completed in roughly twenty seconds. That is a responsiveness improvement, not a claim that a small CPU model will reliably create a large patch. For complex work, the user should choose a stronger provider; the product should make that escalation policy explicit.

The remaining AI gap relative to Cursor/Claude Code is the autonomous loop. BEAST has structured proposal/repair behavior, but it does not yet have a mature repeated cycle of inspect → tool use → edit → execute targeted tests → interpret failures → repair, with each step visible and governed. Closing that loop while preserving SourcePlan/evidence discipline is the highest-value AI investment.

### Areas where BEAST is ahead of stock VS Code

These are product advantages, not claims that VS Code cannot be extended to approximate them:

1. **Governed mutation by default.** A change can be represented as a SourcePlan with exact old/new content, a validation result, operator approval, hashes, and rollback rather than becoming an untracked editor write.
2. **Evidence and provenance are first-class.** Provider, model, attached context, file identity, verification outcome and apply receipt are part of the workbench lifecycle. This is unusually valuable for regulated, safety-sensitive, or multi-operator work.
3. **Context-bound reusable compute.** Crystal reuse binds a result to prompt, bounded history, workspace identity and file hashes, avoiding a naive cache hit against changed source.
4. **One execution-target contract.** Local, SSH and Dev Container operations are intended to use the same target identity across Explorer, tasks, language tooling, debugging, tests and extensions instead of being independently configured islands.
5. **AI is a review surface, not a blind side channel.** The Pair Programmer retains explicit file context, streaming progress, proposal cards, diff handoff, validation, and recovery state in the primary workbench.

### Where VS Code remains clearly ahead

1. **Extension ecosystem and compatibility.** VS Code has the Marketplace, a stable broad API, mature contribution points and years of extension compatibility. BEAST currently supports a deliberately restricted subset.
2. **Language and debug breadth.** VS Code has deeper out-of-box configuration and production exposure across languages, debuggers, notebooks, test adapters and framework-specific refactor workflows.
3. **Git ergonomics.** BEAST now covers the basic operations, but VS Code’s merge editor, history/timeline, multi-repository coordination and interaction polish are substantially more mature.
4. **Remote development maturity.** VS Code Remote SSH, Dev Containers, WSL and Codespaces have a much broader real-world deployment/test matrix. BEAST has the contracts and substantial flows, but needs sustained operational proof.
5. **Accessibility, localization and performance hardening.** VS Code benefits from a very large production population. BEAST needs audited keyboard/screen-reader paths, high-scale workspace tests, startup/memory telemetry and platform soak.

### What should be done next

The highest-value path to genuine parity is not another decorative panel. It is to complete the workflows developers reach for every day:

1. **Polish source control:** improve the existing hunk/conflict/history/remote/rebase/cherry-pick flows with a visual graph, richer three-way merge behavior, multi-repository coordination and live remote-operation tests.
2. **Make execution targets real end-to-end:** run the same remote/container target through Explorer, LSP, debugging, tests, tasks and extensions; add live SSH and Docker CI environments.
3. **Deepen LSP/DAP:** make existing semantic/workspace-symbol, launch/attach, breakpoint and compound paths consistent across adapters; add code-action/refactor previews, attach discovery, exception/data breakpoints and adapter-version acceptance.
4. **Graduate extensions:** executable sandbox lifecycle, extension install/remove/update, contribution points and a documented compatibility matrix. Do not imply Marketplace parity before this exists.
5. **Harden the Pair Programmer:** keep the compact local-Qwen path for responsiveness, route complex edits to a stronger configured model, make model/tool failures retryable, and improve selection-aware multi-file planning and test selection.
6. **Prove reliability:** CI should record local, SSH and container acceptance; installed LSP/DAP versions; extension sandbox tests; and provider latency/error budgets. A contract without a live matrix is not parity.

## Product architecture

### Renderer workbench

The renderer owns interaction and presentation, never a governance bypass. Key modules:

- \`renderer/index.html\` — workbench shell, panel layout, accessible controls and overlays.
- \`renderer/js/beast-store.js\` — durable UI state, active workspace, target, tabs, context and trust.
- \`renderer/js/beast-desktop-bridge.js\` — typed bridge to main-process IPC.
- \`renderer/js/beast-editor-cortex.js\` — buffers, selections, diffs, hunk decorations and apply/reject.
- \`renderer/js/beast-ai-coding.js\` — pair-programmer conversation, context chips, run details, streaming and source-plan review.
- \`renderer/js/beast-model-agent-bridge.js\` — model discovery and local Ollama fallback (\`qwen2.5-coder:1.5b\` for compact Pair Programmer edits; \`qwen2.5:0.5b\` remains a lightweight general fallback).
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

Verify the API and install the Pair Programmer's local coding model:

\`\`\`bash
curl -fsS http://127.0.0.1:11434/api/tags
ollama pull qwen2.5-coder:1.5b
\`\`\`

Run a direct generation probe:

\`\`\`bash
curl -fsS http://127.0.0.1:11434/api/generate \\
  -H 'content-type: application/json' \\
  -d '{"model":"qwen2.5-coder:1.5b","prompt":"Reply with OK","stream":false}'
\`\`\`

The current local Pair Programmer profile is \`qwen2.5-coder:1.5b\`. It uses native Ollama SSE rather than waiting for a non-streaming compatibility response, and bounds a local coding turn to three files, 2,400 characters per file, and 1,024 output tokens. This is intentionally a responsive small-patch mode, not a promise that a CPU-only 1.5B model can reliably plan a large repository-wide refactor. A live route check delivered its first token in about four seconds and completed a bounded turn in about twenty seconds; model quality still depends on available RAM/CPU and selected source scope.

For complex multi-file implementation work, select a stronger configured provider/model. The workbench should make that escalation explicit rather than silently making the local model wait for minutes.

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

- Focused Pair Programmer route tests: **2 passed**, including compact local-Qwen limits and normal Action-IR repair behavior for non-local providers.
- JavaScript/Python syntax checks for the local-Qwen, gateway, and renderer changes: **passed**.
- Parity verifier: consult the generated release-contract report for the current commit, environment, assertion total, failures, and skips.
- Execution-target verifier: consult `build/PHASE0_STATUS.json` for the current environment. Live SSH and container checks are explicitly environment-gated and must retain their individual skip reasons.
- Earlier launch/edit-pipeline results remain useful evidence, but should be rerun from the current commit before release certification.

## Push-readiness and release procedure

Configured remotes:

\`\`\`text
origin      git@github.com:Byron2306/EdgeK-BEAST.git
page-target git@github.com:Byron2306/EdgeK-BEAST-page.git
\`\`\`

Current branch: \`chore/wip-safety-hygiene\`. Current published commit: \`5ce009d feat: advance BEAST IDE and compute platform\`, pushed to \`origin/chore/wip-safety-hygiene\` on 2026-07-18. The push was a broad repository snapshot (including IDE, compute, assets, evidence and generated material), so subsequent releases should use a smaller reviewed staging set where practical.

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

BEAST IDE has a VS Code-shaped workbench with BEAST-native governance and evidence, and it is now materially beyond a prototype. It is not at full VS Code parity: extension breadth, Git power features, remote/container operational maturity, language/debug depth and accessibility/performance proof are the decisive remaining tracks. Local Ollama is live and stream-verified for compact Qwen coding turns; larger edits should deliberately use a stronger provider until local hardware/model capacity is expanded.
