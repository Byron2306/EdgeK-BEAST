# Component and route catalog

Release: `3.1.0-rc3`

| Route | Primary surface | Renderer |
|---|---|---|
| `studio` | BEAST Studio overview and topology | `js/pages/beast-phase8-pages.js` |
| `workspace` | Monaco Editor Cortex and file explorer | `js/pages/beast-workspace-page.js` |
| `source` | SourcePlan Forge and governed diff | `js/pages/beast-sourceplan-page.js` |
| `mission` | Mission overview and flow canvas | `js/pages/beast-mission-page.js` |
| `models` | Local-first model router | `js/pages/beast-models-page.js` |
| `agents` | Agent constellation and session control | `js/pages/beast-agents-page.js` |
| `review` | Quality gates, contradictions, risks, tests | `js/pages/beast-review-page.js` |
| `trust` | Trust posture, attestation, policy guardrails | `js/pages/beast-trust-page.js` |
| `memory` | Memory observatory and governed recall | `js/pages/beast-memory-page.js` |
| `evidence` | Evidence Forge and audit packs | `js/pages/beast-evidence-page.js` |
| `crystallization` | Crystallization chamber and immutable receipts | `js/pages/beast-crystallization-page.js` |
| `map` | Mission dependency map | `js/pages/beast-map-page.js` |
| `terminal` | Governed Terminal Nexus | `js/pages/beast-terminal-page.js` |
| `tooling` | Tooling Forge, MCP, plugins and capabilities | `js/pages/beast-tooling-page.js` |
| `doctor` | Gateway and runtime diagnostics | `js/pages/beast-doctor-page.js` |
| `providers` | Provider plane and inference economics | `js/pages/beast-phase8-pages.js` |
| `system` | System telemetry, ports and processes | `js/pages/beast-phase8-pages.js` |
| `worktrees` | Parallel worktree missions | `js/pages/beast-phase8-pages.js` |
| `deploy` | Release Forge and runbooks | `js/pages/beast-phase8-pages.js` |
| `chronicle` | Operational event ledger | `js/pages/beast-phase8-pages.js` |
| `economy` | Compute Economy and verified savings | `js/pages/beast-phase8-pages.js` |
| `settings` | IDE controls and governance preferences | `js/pages/beast-phase8-pages.js` |

## Shared controllers

- `beast-runtime-contract.js`: transport, cancellation, retry, deduplication and health.
- `beast-page-session.js`: focus, scroll and route state preservation.
- `beast-runtime-watchdog.js`: ownership, overflow and runtime-fault monitoring.
- `beast-accessibility-performance.js`: responsive accessibility and adaptive atmosphere.
- `beast-production-visual.js`: high-definition headers, graphs, maps, rings and visual layers.
- `beast-release-guard.js`: release identity, singleton verification and diagnostics export.
