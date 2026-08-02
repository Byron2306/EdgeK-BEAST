# BEAST IDE AI Coding

The desktop IDE now has an editor-native AI coding lane built on the existing Monaco, Code Cortex, agent-session, SourcePlan, and crystal-reuse owners.

## Operator workflow

Open a file and select **Ask AI** (or press `Ctrl/Cmd+I` while the editor page has focus).

- **Ask** answers repository questions without creating mutations.
- **Edit** produces the smallest bounded BEAST Action IR edit for the attached files.
- **Agent** investigates dependencies and produces a governed multi-file Action IR patch.

Advisory prompts such as “Explain the active file” are routed to **Ask** even if Agent was previously selected. This prevents a useful explanation from being forced through the patch compiler. Mutation verbs retain the selected Edit/Agent route.

The active file is attached automatically. The operator can pin more files, use `@relative/path` in the prompt, or attach the current editor selection. Code Cortex expands this explicit context with relevant workspace files before inference. The SSE endpoint accepts repeated `context_files` query parameters, persists that resolved scope on the session, and emits `agent_run_context`; the UI shows the exact locked path rather than only a file count.

Conversations are multi-turn and persisted per workspace. Provider/model choice, run stages, tool events, reuse decisions, and SourcePlan compilation remain available without crowding the conversation. Internal Action IR is never presented as the assistant's answer: it is normalized into a file-by-file proposal with an explicit diff-review handoff.

## Premium workspace surface

The editor now treats BEAST intelligence as first-class workspace state instead of hiding it behind a generic chat button.

- The **Intelligence Plane** keeps Code Cortex scope, Crystal Reuse, SourcePlan governance, and coding-agent status visible even when the copilot is closed.
- The editor standing state uses the bundled Code Cortex and holographic-grid assets to provide direct workspace and agent entry points instead of an inert blank canvas.
- The copilot uses the bundled premium agent, crystal, context, orchestrator, and trust-core artwork as functional status markers.
- Ask, Edit, and Agent modes explain their contract in-place; starter briefs accelerate common explain, debug, test, and refactor work.
- Every message can be copied, attached context remains visible, and long conversations scroll independently while the model route and composer remain accessible.
- Opening Pair Programmer now removes redundant workspace banners immediately, increasing the conversation height from 427px to 623px while retaining the explorer. Persistent **Focus** mode additionally hides the explorer and widens the paired editor/assistant surface.
- Edit and Agent runs expose a live semantic timeline for context, connection, repository tools, streamed draft size, patch compilation, bounded validation, and review readiness. While generation is underway, a semantic draft card streams discovered target paths and edit intents without leaking raw model-control JSON.
- Completed proposals scroll directly to structured change cards with file paths, intent, validation receipts, line deltas, and expandable before/after previews. BEAST also opens a read-only Monaco `ORIGINAL ↔ PROPOSED` diff automatically, centers the first changed hunk, and lets each file card reopen its highlighted hunks; **Open full review and apply safely** remains the governed write boundary.
- Interrupted, cancelled, disconnected, or stalled streams always leave a completed message state with recovery guidance; restored conversations cannot remain permanently marked **Working**.
- `Ctrl/Cmd+I` opens the agent lane, `Enter` runs, and `Shift+Enter` inserts a newline. Reduced-motion preferences disable the new spatial transitions.

The workspace keeps the Monaco editor usable at the densest supported desktop layout. In the packaged 1920×995 audit shell, the normal Pair Programmer dock is 430px wide beside a 563px editor; Focus mode expands the paired work area to a 648px editor plus a 560px assistant. Both report zero horizontal overflow.

## Governed edit lifecycle

```text
Prompt + explicit context
  -> Code Cortex context expansion
  -> context-safe crystal reuse preflight
  -> provider/local execution only on miss
  -> exact-answer crystal recording
  -> Action IR validation and exact-snippet resolution
  -> in-memory proposed-file syntax/content validation
  -> isolated allowlisted verifier execution
  -> bounded diagnostic repair and revalidation when needed
  -> SourcePlan diff review
  -> verification + operator approval
  -> rollback-backed apply + evidence closure
```

AI output never writes workspace files directly. Edit and Agent modes must resolve into Action IR scoped to attached files. Empty Action IR and plans that resolve to zero edits are failures, not successful no-ops; BEAST performs the bounded repair turn and requires at least one exact, reviewable operation. A valid result is staged in the existing SourcePlan workbench and shown as a readable proposal; the operator reviews the Monaco diff before a verification- and rollback-backed apply. Invalid or stale output is converted into actionable recovery guidance rather than exposed as raw JSON, and any useful prose returned by the model remains visible in the conversation.

Before a plan is offered for review, BEAST applies its exact operations to an in-memory projection of each affected file. Every projection is checked for binary/conflict markers; Python is parsed with `ast`, JSON with the standard parser, and JavaScript with bounded `node --check`. BEAST then creates a temporary isolated verifier workspace, writes only the projected files plus bounded explicit test inputs, and runs allowlisted checks such as `python -m py_compile`, `node --check`, and explicit-file `pytest` targets. Unsupported, broad, or unsafe model-supplied verifier commands are recorded as skipped evidence instead of being executed.

A failed proposal is returned once to the model with only the bounded diagnostics and allowed files, then recompiled and revalidated. Pair Programmer shows the isolated verifier status and command summary directly on the proposal card, so the operator can distinguish “compiled patch” from “checked patch” before opening the governed SourcePlan.

The desktop client also recovers a compiled plan from the terminal session event if an intermediate SourcePlan event is missed. Behavioral parity tests now cover the previously broken raw-JSON transcript, exact live file-scope propagation, empty-plan repair, semantic streaming previews, advisory prompt routing, and completion in `ready-to-review` with a staged plan and no leaked Action IR.

## Crystallised compute behavior

Interactive turns now consult `/edgek/crystal-reuse/decide` before direct provider streaming. Reuse identity binds:

- bounded conversation history;
- active workspace identity;
- attached relative paths;
- hashes of attached file content;
- model, temperature, token ceiling, governance level, and task class.

This prevents a response crystallised for one repository revision from being silently reused in another context. Exact and verified semantic hits can skip provider execution. Successful direct provider responses are recorded through `/edgek/crystal-reuse/record`; semantic promotion remains verification-gated.

The UI surfaces the decision action, source, confidence, avoided-token estimate, record status, and decision ID through the run trace and reuse badge.

## Main implementation points

- `desktop-ide/renderer/js/beast-ai-coding.js` is the public composition root; the 14 focused modules under `renderer/js/ai/` own client, state, events, context, approvals, tools, plans, verification, SourcePlan handoff, conversation rendering, modes, and budgets.
- `desktop-ide/renderer/js/pages/beast-workspace-page.js` owns the editor-integrated panel.
- `app/routes/ide.py` owns persistent agent SSE, multi-turn history, Action IR compilation, and SourcePlan events.
- `app/cli/api.py` owns context-safe reuse-first streaming and response recording.
- `app/kernel/workspaces/agent_session_store.py` owns durable conversation projection.

## Verification

```bash
cd desktop-ide && npm run smoke
cd desktop-ide && npm run smoke:launch
cd desktop-ide && BEAST_VISUAL_PAGES=workspace ./node_modules/.bin/electron scripts/visual-audit-beast-studio.js
BEAST_STATE_ROOT=/tmp/beast-ai-tests python3 -m pytest \
  tests/test_agent_session_store.py \
  tests/test_tui_stream_recovery.py::test_completed_direct_stream_uses_context_safe_crystal_preflight_and_records \
  tests/test_agent_scheduler_mission_cockpit.py -k agent_session_run_events -q
```

## Broader VS Code parity boundary

This closes the primary AI coding loop inside BEAST. General editor parity is a separate product surface: full Language Server Protocol coverage, Debug Adapter Protocol, extension-host compatibility, source control UX, notebook support, remote development, and accessibility conformance still require their own acceptance tracks. Those should reuse this copilot and governed mutation lane rather than create another AI implementation.
