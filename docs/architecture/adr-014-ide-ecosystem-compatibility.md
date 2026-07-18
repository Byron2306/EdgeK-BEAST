# ADR-014: IDE ecosystem compatibility boundary

## Status

Accepted for the first parity milestone.

## Context

BEAST already owns Monaco editing, governed SourcePlans, agent sessions, trust,
evidence, tools, and crystallised-compute reuse. It does not yet own the daily
driver protocol surfaces expected from VS Code: language servers, debug
adapters, notebooks, extension execution, and remote workspaces.

The product is an enterprise desktop application with local-first operation,
explicit trust boundaries, and a large existing modular-monolith backend. The
compatibility layer must not let arbitrary renderer content spawn processes or
bypass SourcePlan and evidence controls.

## Options considered

| Option | Advantages | Costs and risks |
|---|---|---|
| Embed Code OSS | Highest immediate compatibility | Very large fork, duplicate shell, licensing/update burden, and BEAST UX/governance becomes secondary |
| Reimplement the VS Code extension API | Familiar extension model | Multi-year compatibility surface with high behavioral drift risk |
| Protocol-native host plus VS Code companion | Reuses LSP/DAP standards, keeps Monaco and BEAST governance, ships incrementally | Extensions that require `vscode.*` still run in the existing VS Code companion until an API shim is implemented |

## Decision

Use a process-isolated compatibility host in Electron's main process.

- Language servers and debug adapters are discovered from an allowlisted
  catalog and launched without a shell.
- JSON-RPC/DAP messages cross a narrow preload IPC boundary. The renderer never
  receives general process-spawn authority.
- Monaco providers consume standard completion, hover, definition, and
  diagnostics responses.
- Notebook kernels and remote transports begin as discovered capability
  contracts, then gain execution and filesystem adapters behind the same host.
- Extensions using the complete VS Code API continue to run through the BEAST
  VS Code companion. Desktop extension compatibility will be added as a
  separately versioned API shim, not an undocumented partial clone.
- Every mutation remains governed by SourcePlan; protocol features may inspect
  freely but cannot silently write the workspace.

## Trade-offs

- BEAST does not claim immediate compatibility with the complete VS Code
  Marketplace.
- Protocol-native features arrive sooner and are portable across editors.
- The compatibility host adds process lifecycle and message-framing code that
  must be tested for crashes, malformed frames, timeouts, and workspace escape.

## Consequences

- Positive: real LSP/DAP foundations without replacing the BEAST shell.
- Positive: capability reporting is evidence-based rather than aspirational.
- Negative: notebook, remote filesystem, and VS Code API-shim work remain
  explicit follow-on milestones.
- Mitigation: the capability center labels each surface as available,
  foundation, companion, or missing and links it into the operator journey.

## Revisit trigger

Reconsider embedding Code OSS only if protocol-native coverage cannot meet the
daily-driver acceptance matrix or Marketplace compatibility becomes a hard
customer requirement that outweighs BEAST shell ownership.
