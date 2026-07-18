# ADR-019: Mediated developer workbench and extension execution

## Status

Accepted

## Context

VS Code daily-driver workflows depend on search, tasks, source control, remote terminals, and executable extensions. BEAST must add these without giving renderer code or untrusted extensions arbitrary local/remote process authority.

## Decision

Electron main provides bounded IPC for text search, preview-first replace, Git status, declared npm and `.vscode/tasks.json` tasks, verified SSH remote I/O, reconnect, one-shot remote commands, and persistent SSH-TTY sessions. Declared tasks run through a session host with streamed bounded output, cancellation, background/watch readiness, evidence receipts, and workspace-bounded problem-matcher paths; the renderer receives structured diagnostics rather than process handles. Persistent terminal sessions use strict host-key checking, safe workspace paths and approved shell names, 64 KiB input frames, a 256 KiB retained output window, renderer reattachment, and explicit shutdown. Extension entrypoints execute in the isolated extension host's VM with no Node or Electron globals and may return only serializable mediated actions. Grants are passed into every execution and enforced before the shim exposes workspace folders, bounded file search, or files up to 1 MiB; the shim also exposes mediated command dispatch, notices, configuration fallbacks, and URI helpers. Workspace writes remain outside this shim and must enter BEAST through SourcePlan.

## Trade-offs

This is a controlled interoperability foundation rather than full VS Code parity: arbitrary task definitions, remote process/task lifecycle, and a hardened operating-system sandbox are still deferred. Node VM isolation is defense in depth, not a substitute for a future OS-level sandbox.

## Consequences

- Positive: core daily workflows and extension execution have auditable, bounded paths today.
- Negative: interaction is intentionally narrower than VS Code's unrestricted local extension host.
- Mitigation: add per-capability brokers, Git staging/commit, remote task lifecycle, and OS-level extension isolation before accepting third-party executable extensions.
