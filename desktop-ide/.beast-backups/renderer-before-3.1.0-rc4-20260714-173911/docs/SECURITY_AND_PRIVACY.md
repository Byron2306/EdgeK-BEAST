# Security and privacy notes

- The renderer prefers an Electron IPC bridge when available and falls back to localhost HTTP.
- Mutating terminal, file, SourcePlan, worktree and deployment operations must remain governed and explicitly confirmed.
- Do not expose the BEAST gateway on a public interface without authentication and transport controls.
- Release diagnostics include runtime status and fault messages. Review them before sharing outside the project.
- No user data, credentials, API keys or font files are bundled in this release.
