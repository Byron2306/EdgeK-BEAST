# ADR-015: Governed developer-runtime workbench

## Status

Accepted

## Context

The compatibility host established protocol-safe language intelligence, but daily IDE work also needs debugging, notebook execution, and remote workspace access. Giving renderer code general child-process or shell access would undermine BEAST's trust, evidence, and workspace boundaries.

## Decision

Expose three narrow Electron-main capabilities through the existing preload boundary:

- allowlisted Debug Adapter Protocol sessions, initialized in the main process;
- explicit Python notebook-cell execution with bounded output, timeout, and a SHA-256 execution receipt;
- SSH workspace verification and bounded file listing, with strict host-key verification and conservative host/path validation.

The renderer can send structured configuration and protocol requests only. It cannot receive a process handle or invoke a shell. Debugging, cell execution, and remote connection remain explicit operator actions.

## Rationale

This extends the protocol-native host already used for LSP without adding a second extension architecture. It produces a usable vertical slice now while allowing a future notebook kernel manager and remote filesystem provider to replace the bounded adapters behind the same UI contract.

## Trade-offs

The notebook runner currently supports Python cells rather than the full Jupyter document/kernel model. Remote development provides verified SSH connection and bounded file indexing, not a mounted remote filesystem or forwarded-port manager. DAP functionality activates only when a local adapter, such as `debugpy`, is installed.

## Consequences

- Positive: operator-facing VS Code workflows become usable without renderer process authority.
- Negative: capability availability follows installed local tools and pre-trusted SSH hosts.
- Mitigation: the Compatibility Center reports each dependency honestly and offers the VS Code companion for extensions requiring the full `vscode.*` API.
