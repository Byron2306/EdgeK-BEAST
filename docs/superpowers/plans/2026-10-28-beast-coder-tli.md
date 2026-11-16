# BEAST Coder TLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a focused BEAST coding TLI backed by the existing durable coding-agent runtime, then switch `beast ui` only if acceptance passes.

**Architecture:** A focused Textual app uses a small async gateway client and workspace-bound state store. Coding turns create and follow durable AgentRuns; only canonical tool observations and receipt fields are rendered as execution results. Existing UI brand renderers and assets are imported unchanged.

**Tech Stack:** Python 3.11, Textual, Rich, httpx, pytest/pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-10-28-beast-coder-tli-design.md`

## Global Constraints

- Preserve the dirty worktree and all unrelated modifications.
- Do not invoke swarm orchestration from the default coding route.
- Preserve `app/cli/assets/sprites/mascot_frames.json` and `motion_locked = true`.
- Display execution as successful only from actual AgentRun observation/receipt evidence.
- Stage and test before changing the default `beast ui` launcher.
- Retain the legacy dashboard and an explicit rollback route.

## Review Focus

- Missing/unreachable gateway must render an honest offline error while local help and workspace selection remain usable.
- Malformed or partial SSE frames must not fabricate tokens, completion, or tool success.
- Workspace paths outside an existing directory must be rejected without changing persisted selection.
- Provider/model values must come from actual discovery or an explicit user choice and remain visible.
- Approval-pending and failed tool observations must remain distinct from successful execution receipts.

---

### Task 1: Runtime client and event projection

**Files:**
- Create: `app/cli/coder_client.py`
- Create: `tests/test_coder_client.py`

**Interfaces:**
- Produces: `CoderRuntimeClient`, `RuntimeEvent`, `iter_sse_events()`, discovery methods, `ensure_session()`, `start_run()`, and `follow_run()`.
- Consumes: existing HTTP contracts under `/edgek/providers/registry`, `/edgek/skills`, `/edgek/mcp/state`, `/edgek/ide/agent-sessions/create`, and `/edgek/agent-runs`.

- [ ] Write failing tests for SSE fragmentation, discovery payloads, run creation, canonical event streaming, and HTTP errors.
- [ ] Run `pytest -q tests/test_coder_client.py` and verify failure because the module is absent.
- [ ] Implement the minimal async client and bounded SSE parser.
- [ ] Run `pytest -q tests/test_coder_client.py` and verify pass.

### Task 2: Persistent Coder state and commands

**Files:**
- Create: `app/cli/coder_state.py`
- Create: `tests/test_coder_state.py`

**Interfaces:**
- Produces: `CoderSettings`, `ConversationStore`, `SlashCommand`, `parse_slash_command()`, and `project_runtime_event()`.
- Consumes: `RuntimeEvent` from Task 1.

- [ ] Write failing tests for workspace validation, atomic settings/transcript persistence, all required commands, clear semantics, and receipt-only successful tool projection.
- [ ] Run `pytest -q tests/test_coder_state.py` and verify failure.
- [ ] Implement the minimal state, parsing, and projection layer.
- [ ] Run `pytest -q tests/test_coder_state.py` and verify pass.

### Task 3: Focused Textual interface

**Files:**
- Create: `app/cli/coder.py`
- Create: `tests/test_coder_tli.py`

**Interfaces:**
- Produces: `BeastCoderApp`, `run()`, CLI `main()`, command dispatch, streaming turn rendering, and mascot state transitions.
- Consumes: `CoderRuntimeClient`, `ConversationStore`, `beast_wordmark()`, `sprite_mascot()`.

- [ ] Write failing Textual pilot tests for header/mascot, explicit workspace, required commands, provider/model switching, discovery rendering, stream deltas, tool receipts, clear, and exit.
- [ ] Run `pytest -q tests/test_coder_tli.py` and verify failure.
- [ ] Implement the compact layout and command/stream controller with the existing palette and renderers.
- [ ] Run `pytest -q tests/test_coder_tli.py` and verify pass.

### Task 4: Staged real-runtime acceptance

**Files:**
- Create only test artifacts inside: `~/granite-agent-test`
- Modify no launcher file in this task.

**Interfaces:**
- Consumes: `python -m app.cli.coder --workspace ~/granite-agent-test` and the active BEAST gateway/provider infrastructure.
- Produces: captured launch, stream, structured tool, execution receipt, file verification, Python execution, discovery, and switching evidence.

- [ ] Confirm the Granite workspace exists and record its initial state without deleting anything.
- [ ] Launch the staged TLI and observe the original header and Beastie.
- [ ] Request a bounded file creation and Python execution through Granite.
- [ ] Independently inspect the requested file and execute the script outside model output.
- [ ] Exercise `/skills`, `/mcp`, `/tools`, `/provider`, and `/model` against actual capability responses.
- [ ] Run focused and relevant regression tests and record exact output.

### Task 5: Default launcher switch and rollback

**Files:**
- Modify: `bin/beast`
- Test: `tests/test_beast_cli_script.py`

**Interfaces:**
- Produces: `beast ui` → Coder TLI; `beast ui --legacy` → unchanged mission console.
- Consumes: all acceptance evidence from Task 4.

- [ ] If any mandatory acceptance item failed, do not perform this task and report the blocker.
- [ ] Write a failing launcher test for the new default and legacy route.
- [ ] Run the focused launcher test and verify failure.
- [ ] Make the smallest parser/import change in `bin/beast`.
- [ ] Run launcher, Coder, and existing CLI tests; verify pass.
- [ ] Re-run launch smoke tests for both default and legacy routes.

