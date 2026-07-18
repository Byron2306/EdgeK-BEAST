# BEAST Desktop IDE

The editor now includes an integrated Ask/Edit/Agent coding copilot with Code Cortex context expansion, persistent sessions, governed SourcePlan patches, and context-safe crystallised compute reuse. See [BEAST IDE AI Coding](../docs/BEAST_IDE_AI_CODING.md).

The VS Code parity track now includes a guided first-mission runway, a process-isolated LSP/DAP compatibility host, bundled TypeScript/JavaScript, Python, JSON, HTML, and CSS language servers, and an honest capability center. See [BEAST IDE VS Code Parity](../docs/BEAST_IDE_VSCODE_PARITY.md).

This is the installable desktop shell for BEAST. It uses the TUI as the product
spine, but runs as a local desktop application similar in shape to VS Code:

- desktop process owns gateway startup and workspace selection;
- renderer shows Mission Control, editor, SourcePlan, Evidence Bus, Code Cortex,
  agent sessions, and worktree missions;
- all writes still go through BEAST governance rather than direct file mutation.

## Development

```bash
cd desktop-ide
npm install
npm run smoke
npm start
```

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
