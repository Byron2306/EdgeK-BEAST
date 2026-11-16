# BEAST Desktop IDE

The editor now includes an integrated Ask/Edit/Agent coding copilot with Code Cortex context expansion, persistent sessions, governed SourcePlan patches, and context-safe crystallised compute reuse. See [BEAST IDE AI Coding](../docs/BEAST_IDE_AI_CODING.md).

The VS Code parity track now includes a guided first-mission runway, a process-isolated LSP/DAP compatibility host, bundled TypeScript/JavaScript, Python, JSON, HTML, and CSS language servers, and an honest capability center. See [BEAST IDE VS Code Parity](../docs/BEAST_IDE_VSCODE_PARITY.md).

This is the installable desktop shell for BEAST. It uses the TUI as the product
spine, but runs as a local desktop application similar in shape to VS Code:

- desktop process owns gateway startup and workspace selection;
- renderer shows Mission Control, editor, SourcePlan, Evidence Bus, Code Cortex,
  agent sessions, and worktree missions;
- all writes still go through BEAST governance rather than direct file mutation.

The Electron app currently uses the Phase 9.1.5 renderer from
`../BEAST_Phase9_1_5_Unique_Hacker_Type` as its UI baseline. Its page and
referenced styles/scripts are mirrored under `renderer/` so the packaged app
loads the same layout. Routes added in the later desktop release (including
IDE Compatibility, Compute Fabric, Commons, Testing, Reality Matrix and
Systems Atlas) remain available in this shell. Page data loads as each route
is opened instead of issuing requests for every page during startup. The
restored pages use the bundled Phase 9.1.5 page frames, route icons, local
typefaces, and route-specific layouts so dense operational data remains
readable without replacing the original shell.

The animated matrix background is off by default to keep the desktop responsive;
select the matrix-grid atmosphere in Settings to enable it. Canvas visualizers
are throttled and pause while the window is hidden.

## Integration Atlas

Systems Atlas is the source-of-record view for backend integrations exposed to
the IDE. It reads `GET /edgek/ide/integrations` and keeps four claims separate:

- **Implemented** means the backend code is present.
- **Enabled** means its runtime flag or default policy is active.
- **Evidence** means a bounded artifact exists in the current workspace.
- **Live** requires a current positive runtime observation; historical evidence
  is never promoted to live state.

Agent Constellation, Compute Fabric, Crystallization, Commons, and Tooling Forge
show compact rails backed by the same catalog. Selecting an entry opens its full
Atlas record, including the audited component baseline and claim boundary. An
unreachable catalog is shown as an error and is not replaced with demo data.

The Agent Coder path emits durable `agent.integration.fired`,
`agent.integration.skipped`, and `agent.integration.failed` receipts. Context
compression, Vector RAG, memory recall, crystal lookup, and swarm selection run
before provider handoff. Memory sealing and crystal learning only run after an
approved SourcePlan passes verification; crystal promotion remains an operator
action. ML-KEM, XDP/eBPF, and X7 LSM/ARDA remain operator-loaded infrastructure.

## Development

```bash
cd desktop-ide
npm install
npm run smoke
npm start
```

`npm start` now launches through `scripts/start-desktop-ide.js`, which strips
inherited `ELECTRON_RUN_AS_NODE=1` shells and applies Linux/container-safe
Electron flags by default. Set `BEAST_ELECTRON_SANDBOX=1` to force the normal
Chromium sandbox path on trusted hosts.

## Packaging

```bash
cd desktop-ide
npm run smoke
npm run package:linux
```

The app starts or attaches to the `.byron/services.yaml` BEAST upstream
(`http://127.0.0.1:8101` by default) and calls existing
`/edgek/ide/*`, `/edgek/workspace/*`, and SourcePlan routes.

## Governed Terminal

The terminal is an operator console, not a raw shell. Commands are classified by
Safety Governor first, run with an explicit workspace working directory and
timeout, and successful or failed executions are kept as terminal evidence
receipts that can be copied or filtered in the Evidence Bus.
