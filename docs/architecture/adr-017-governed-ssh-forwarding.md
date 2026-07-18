# ADR-017: Governed SSH forwarding and reverse development tunnels

## Status

Accepted

## Context

Remote development needs the everyday VS Code workflow of making a remote service available locally and, when needed, giving a remote development host access to a local service. Existing BEAST Remote SSH verifies a host key and indexes a bounded workspace, but did not keep an operator-visible forwarding lifecycle.

## Decision

Electron main owns persistent SSH forwarding processes. The renderer can request only an explicit local forward (`ssh -L`) or reverse development tunnel (`ssh -R`) for its connected host. Both forward endpoints bind to `127.0.0.1`, target only `localhost`/loopback, use batch mode, strict known-host verification, keepalives, and `ExitOnForwardFailure`; every forward is listed and can be stopped from Remote Explorer.

## Trade-offs

Public, anonymous share URLs are intentionally not created. That would require a separate authenticated relay service, access controls, expiry, auditability, and an explicit product authorization boundary. The initial capability is powerful enough for development while keeping service exposure local to the SSH endpoints.

## Consequences

- Positive: real SSH port forwarding and reverse tunneling are available from the IDE without renderer shell access.
- Negative: a session does not automatically reconnect and services cannot be publicly shared by default.
- Mitigation: forwards are explicit, visible, stoppable, bound to loopback, terminated with the desktop app, and retain SSH strict host-key verification.
