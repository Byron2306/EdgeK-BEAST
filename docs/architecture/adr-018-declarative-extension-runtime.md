# ADR-018: Declarative extension runtime before executable extensions

## Status

Accepted

## Context

BEAST needs an extension ecosystem, but executing arbitrary third-party JavaScript in the desktop process would bypass its trust, evidence, and capability model. Detection of the separate VS Code companion did not provide a desktop extension lifecycle or a user-visible permission boundary.

## Decision

Run a separate Node child process that discovers only validated `beast-extension.json` manifests from packaged and workspace extension roots. Manifests declare a fixed capability vocabulary and command contributions. Electron main owns lifecycle and stores grants at `.beast/ide-extension-grants.json`; the renderer can discover, grant declared capabilities, or stop the host through narrow IPC. The host does not execute extension-provided code in this tranche.

## Trade-offs

This is not yet compatible with arbitrary VS Code extensions or a marketplace. It intentionally favors an auditable, deterministic trust boundary over immediate ecosystem breadth.

## Consequences

- Positive: extensions have a real isolated lifecycle, visible requests, and per-workspace grants without renderer process authority.
- Negative: declarative contributions cannot yet run custom code.
- Mitigation: add a sandboxed worker API only after command, filesystem, network, and terminal grants have enforceable mediation and an extension compatibility suite.
