# Scoped 100% Parity Areas

As of Friday, July 31, 2026, BEAST has twelve areas that are treated as `100%` complete against an explicit, automated parity contract.

This is intentionally narrower than claiming the entire IDE is at `100%`.

## 1. Notebook MIME / Trust / Runtime Contract

Scope:
- normalized notebook MIME bundle handling
- trust-aware rich output behavior
- restricted-vs-trusted output gating
- persistent-kernel receipt and runtime summary coverage
- renderer support for MIME-aware output inspection

Verifier:
- `desktop-ide/scripts/verify-notebook-mime-trust-parity.js`

Passing means:
- MIME normalization is correct
- trust-sensitive output classes are surfaced
- restricted rendering behavior is enforced
- renderer/runtime contract strings are present

Artifact:
- `build/NOTEBOOK_MIME_TRUST_PARITY.json`

## 2. VS Code Extension Package / Runtime Contract

Scope:
- `package.json` discovery and compatibility classification
- activation-event handling
- command registration
- tree/status/language mediated actions
- uglier package runtime cases:
  - `node_modules` package loading
  - package `exports` subpath resolution
  - `asAbsolutePath` asset reads
  - hosted webview views
  - webview panel `postMessage`
  - webview disposal behavior

Verifier:
- `desktop-ide/scripts/verify-real-vscode-extension-host.js`

Passing means:
- BEAST’s mediated VS Code shim can execute these runtime patterns safely and correctly
- the harsher extension fixture passes alongside the real BEAST extension workload

Artifact:
- `build/REAL_VSCODE_EXTENSION_HOST_PARITY.json`

## 3. Gateway Stability Contract

Scope:
- single-flight gateway startup behavior
- busy-listener reuse instead of runaway port hopping
- compatibility-checked attach/recovery logic
- bounded managed-startup fallback to local IDE mode
- bounded request/response payload enforcement
- main-process-mediated event streaming

Verifier:
- `desktop-ide/scripts/verify-gateway-stability-contract.js`

Passing means:
- the gateway route/stability guardrails BEAST depends on are wired and enforced
- recovery and fallback semantics remain intact under the defined desktop contract

Artifact:
- `build/GATEWAY_STABILITY_CONTRACT.json`

## 4. IDE Services Spine Contract

Scope:
- unified IDE services snapshot for LSP, DAP, tests, tasks, SCM, extensions, and workspace index
- semantic navigation readiness: symbols, definitions, references, dependents, rename preview
- focused test/task execution with history receipts
- packaged and BEAST extension workload execution through the mediated extension host
- webview, tree, terminal, task, watcher, storage, secret, and persistence extension behaviors

Verifier:
- `desktop-ide/scripts/verify-ide-services-parity.js`

Passing means:
- the main “daily-driver” IDE services backbone works together as one contract rather than isolated badges
- semantic queries, task/test flows, and mediated extension workloads all pass in the same acceptance run

Artifact:
- `build/IDE_SERVICES_PARITY.json`

## 5. Execution Target Governed Contract

Scope:
- local execution-target routing surfaces
- target soak/session receipts
- target-side remote mutation and verifier execution through SSH/container targets
- governed final apply evidence/rollback flow
- planner verification strategy and repair evidence preservation for remote targets
- provider escalation after hard remote repair failures

Verifier:
- `desktop-ide/scripts/verify-execution-target-governed-contract.js`

Passing means:
- the target orchestration and agentic apply loop BEAST proves locally are intact
- only the explicitly environment-gated live handshake rows remain excluded from this narrower contract

Artifact:
- `build/EXECUTION_TARGET_GOVERNED_CONTRACT.json`

## 6. Remote Extension Runtime Contract

Scope:
- remote extension deployment and activation routing for SSH/container targets
- remote continuity across interruption/reconnect cycles
- hosted tree/webview/storage/secret/task/terminal behavior under remote extension workloads
- disposable SSH/container watcher continuity
- repeated remote soak behavior

Verifier:
- `desktop-ide/scripts/verify-remote-extension-runtime-contract.js`

Passing means:
- BEAST’s remote extension runtime survives real routing, continuity, and soak-style workloads in the bounded acceptance harness

Artifact:
- `build/REMOTE_EXTENSION_RUNTIME_CONTRACT.json`

## 7. Language / Navigation Contract

Scope:
- live local LSP handshakes across the shipped language matrix
- unified semantic index and navigation readiness
- workspace symbols, definitions, references, dependents, and rename preview
- diagnostics and refactor readiness through the IDE services spine

Verifier:
- `desktop-ide/scripts/verify-language-navigation-contract.js`

Passing means:
- BEAST’s practical code-intelligence spine is working end to end in the bounded acceptance harness

Artifact:
- `build/LANGUAGE_NAVIGATION_CONTRACT.json`

## 8. Debug Lifecycle Contract

Scope:
- paused-state debug UI wiring
- loaded-sources, restart, and restart-frame protocol support
- remote debug auto-resume across SSH reconnect and container attach/restart
- explicit bounded treatment of live adapter handshakes that are environment-gated elsewhere

Verifier:
- `desktop-ide/scripts/verify-debug-lifecycle-contract.js`

Passing means:
- the debug lifecycle and recovery contract BEAST proves locally is intact, including remote recovery behavior

Artifact:
- `build/DEBUG_LIFECYCLE_CONTRACT.json`

## 9. Notebook Runtime Contract

Scope:
- persistent notebook kernel lifecycle
- notebook execution receipts and runtime summaries
- trust-sensitive widget/HTML/visualization MIME classification
- notebook document parse/serialize and per-cell execution metadata wiring
- trusted vs restricted notebook runtime state path

Verifier:
- `desktop-ide/scripts/verify-notebook-runtime-contract.js`

Passing means:
- BEAST’s notebook runtime path, beyond basic MIME/trust rendering, is functioning as a bounded contract with real kernel-request behavior

Artifact:
- `build/NOTEBOOK_RUNTIME_CONTRACT.json`

## 10. Notebook Widget / State Contract

Scope:
- widget-view and structured visualization MIME bundle preservation
- trust-sensitive widget/Plotly/Vega/Vega-Lite classification
- trusted vs restricted notebook review messaging for interactive bundles
- per-output trust metadata and summary propagation into notebook cells

Verifier:
- `desktop-ide/scripts/verify-notebook-widget-state-contract.js`

Passing means:
- BEAST preserves notebook widget/visualization state correctly in the bounded shell contract, even though it intentionally does not embed the full interactive runtimes

Artifact:
- `build/NOTEBOOK_WIDGET_STATE_CONTRACT.json`

## 11. DAP Governed Contract

Scope:
- bounded DAP lifecycle wiring
- paused-state/source/variable/restart UI coverage
- remote debug recovery across SSH reconnect and container attach/restart
- explicit treatment of live adapter handshakes as environment-gated rather than silently claimed

Verifier:
- `desktop-ide/scripts/verify-dap-governed-contract.js`

Passing means:
- BEAST’s governed debugging contract is intact in this environment, with honest exclusion of live adapter fixtures that were not executed

Artifact:
- `build/DAP_GOVERNED_CONTRACT.json`

## 12. Test Explorer Contract

Scope:
- test discovery breadth across pytest, Go, Rust, Java, .NET, Playwright, and Cypress
- focused file/node runs
- flaky retry recording
- task evidence/history integration
- pytest debug handoff path

Verifier:
- `desktop-ide/scripts/verify-test-explorer-contract.js`

Passing means:
- BEAST’s practical test-explorer workflow is working as one bounded contract rather than isolated discovery and history pieces

Artifact:
- `build/TEST_EXPLORER_CONTRACT.json`

## Combined Proof

Run:

```bash
node desktop-ide/scripts/verify-scoped-100-parity.js
```

Artifact:
- `build/SCOPED_100_PARITY.json`

If that verifier passes, both bounded areas are at `100%` against their defined parity contracts.
