# BEAST Desktop IDE

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

The app starts or attaches to `http://127.0.0.1:8000` and calls existing
`/edgek/ide/*`, `/edgek/workspace/*`, and SourcePlan routes.

## Governed Terminal

The terminal is an operator console, not a raw shell. Commands are classified by
Safety Governor first, run with an explicit workspace working directory and
timeout, and successful or failed executions are kept as terminal evidence
receipts that can be copied or filtered in the Evidence Bus.
