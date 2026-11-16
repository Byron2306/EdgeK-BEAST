# BEAST Coder TLI Design

## Intent

Replace the default `beast ui` experience with a focused coding terminal interface while retaining BEAST's existing coding runtime, providers, Meta Skills, MCP infrastructure, tool execution, streaming transport, original wordmark, and motion-locked Beastie. The mission console remains available as a legacy route.

## Goals

- Present a compact streaming coding conversation with visible, durable tool execution receipts.
- Expose `/help`, `/model`, `/provider`, `/skills`, `/mcp`, `/tools`, `/workspace`, `/status`, `/clear`, and `/exit` against real gateway capabilities.
- Persist the selected workspace, provider/model, conversation, and run references locally under the selected workspace.
- Reuse `beast_wordmark()` and `sprite_mascot()` from `app.cli.ui`, backed by `app/cli/assets/sprites/mascot_frames.json` with `motion_locked = true` and all four existing states.
- Route coding prompts through durable AgentRuns and their typed `AgentPlannerRuntime` tool executor, never through swarm orchestration.
- Stage and test the new module before changing the `beast ui` launcher.

## Non-goals

- Replacing or deleting the mission dashboard or any backend module.
- Reworking provider adapters, Meta Skills, MCP, tool policies, approvals, or AgentRun semantics.
- Adding a second model-generated tool protocol or treating assistant prose as execution evidence.
- Changing production service configuration.

## Constraints and anti-goals

- Preserve all unrelated dirty-worktree changes.
- Do not reset, clean, or delete anything.
- A tool result is displayed as executed only when it comes from a durable AgentRun event/observation with receipt metadata.
- Workspace selection must resolve to an existing directory and remain explicit in the header and status.
- Default launch switching is the final step and occurs only if acceptance tests pass; `beast ui --legacy` is the rollback route.

## Existing runtime trace

The authoritative executable is `bin/beast`. The durable coding path is:

`POST /edgek/agent-runs` → `AgentRunEngine.create_run()` → `_launch_for_run()` → `AgentPlannerRuntime.run()` → `AgentRunEngine.execute_tool()` → `AgentToolRegistry` / `tool_runtime` → durable AgentRun events and observations → `GET /edgek/agent-runs/{run_id}/events` SSE.

Provider deltas are emitted as `agent.model.delta`; tool requests, state transitions, observations, approvals, and receipt-bearing results are persisted in the AgentRun store. This is the API boundary for coding turns. The older `BeastApiClient.stream_live_turn()` remains useful for conversational/provider transport but is not the authority for executed coding tools.

Discovery sources are the existing `/edgek/providers/registry`, `/edgek/skills`, `/edgek/skills/state`, `/edgek/mcp/state`, and AgentRun tool-registry endpoints.

## Approaches considered

1. **Durable AgentRun gateway client (selected).** A small Textual app calls the existing HTTP endpoints and projects canonical events into chat/tool receipt views. This preserves runtime ownership, streaming, and receipts and keeps the interface isolated.
2. **Direct in-process runtime.** Instantiate `AgentRunEngine` and `AgentPlannerRuntime` inside the TLI. This avoids a gateway dependency but duplicates application wiring and risks diverging from production provider/MCP configuration.
3. **Refit the existing mission console.** Hide most pages and reuse its live-turn code. This minimizes initial files but entangles the replacement with a 16k-line dashboard and uses a conversational path that does not guarantee typed tool receipts.

Approach 1 is selected because it is the narrowest change that satisfies runtime truth, persistence, provider/MCP/skills discovery, and rollback requirements.

## Components

- `app/cli/coder_client.py`: typed, async HTTP client for discovery, session/run creation, SSE events, and persisted receipt retrieval.
- `app/cli/coder_state.py`: workspace-bound settings and transcript persistence, command parsing, and event-to-view projection.
- `app/cli/coder.py`: focused Textual layout, original brand renderers, animation states, slash commands, and streaming interaction.
- `tests/test_coder_tli.py`: unit and Textual pilot tests using a fake runtime client.
- `tests/test_coder_client.py`: transport contract and SSE parsing tests.
- `bin/beast`: only after staged acceptance, route `ui` to Coder and add `ui --legacy` rollback.

## Interaction and failure behavior

The header always shows the original wordmark, Beastie, workspace, provider, model, and connection/run state. Conversation occupies the main column; a restrained tool/receipt rail shows actual event type, tool ID, status, stdout/stderr summary, receipt ID/digest, and sequence. Slash commands render capability data returned by the runtime. Gateway errors are shown as errors and never replaced with synthetic success. Approval-required tools remain pending and visible.

Each prompt creates a run tied to a persistent coding session and explicit workspace, then follows canonical events. A completed run is appended to the workspace transcript. `/clear` clears the visible/persisted conversation but does not delete BEAST's durable run ledger.

## Acceptance and rollout

First launch `python -m app.cli.coder --workspace ~/granite-agent-test` and run focused automated tests. Then execute the requested Granite workflow against the real gateway and independently verify the created file and Python output. Only after all required acceptance items pass may `bin/beast` change its default `ui` import. Any failed item remains explicitly reported and leaves the legacy default unchanged.

