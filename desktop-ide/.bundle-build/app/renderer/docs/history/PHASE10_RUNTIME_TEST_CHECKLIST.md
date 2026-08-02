# Phase 10 Runtime Acceptance Checklist

1. Launch through the real Electron main process, not only `file://`.
2. Confirm the header phase pill reports `IPC` when `window.beastDesktop.status` is available.
3. Choose a workspace and verify one workspace event, one index refresh, and preserved tabs.
4. Switch between Workspace, SourcePlan, Models, Agents, Review, Memory, Map, and Terminal; verify scroll and focus restoration.
5. Disconnect the gateway; confirm pages retain normalized local state and the runtime card reports degraded mode.
6. Reconnect and run `/runtime probe`; confirm mode returns to Electron or HTTP.
7. Run simultaneous refresh actions and verify the gateway receives a single production refresh group.
8. Exercise SourcePlan verify/apply, terminal classification/execution, agent create, evidence pack, worktree, release readiness, and gateway restart.
9. Inspect DevTools for unhandled promise rejections, duplicate page roots, duplicate IDs, and horizontal document overflow.
10. Close the window with dirty buffers, reopen, and confirm restoration.
