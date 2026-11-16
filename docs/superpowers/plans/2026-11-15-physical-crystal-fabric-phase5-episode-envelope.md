# Physical Crystal Fabric Phase 5 Episode Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every AgentRun, and every swarm lane through an adapter, produces one canonical, hash-sealed, privacy-filtered Episode Envelope, with real budget accounting for model turns, tokens, tool calls and wall time.

**Architecture:** A `RunBudgetTracker` records each real provider decision and each governed tool execution into `AgentRunStore.merge_budget()` (finally wiring the unused budget path) and emits one durable `agent.budget.recorded` event per tool step, carrying the decision source (model, crystal, runtime). `AgentPlannerRuntime.run()` brackets the existing loop to account for wall time and seals an envelope when the run ends. `EpisodeEnvelopeBuilder` derives the envelope from the run record, the durable event chain and the planner observations, keeping only allow-listed structured fields and digests. `EpisodeEnvelopeStore` persists it by run ID. A swarm `Scribe` adapter maps phase E episodes into the same contract.

**Tech Stack:** Python 3.13 standard library, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`
**Roadmap:** `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md`

## Global Constraints

- Envelopes carry no raw prompts, file contents, tool stdout/stderr, credentials or secret-pattern matches. Free text is reduced to digests; allow-listed scalars pass through after secret redaction.
- The envelope is sealed with a canonical SHA-256 digest and bound to the AgentRun event-chain head. A tampered envelope fails validation.
- Budget accounting never changes planner behavior. Recording failures are swallowed and reported, never fatal to a run.
- Token counts are provider-reported when `last_usage` exists; otherwise they are estimated (characters/4) and labeled `estimated`.
- Backend only, with offline tests. No renderer changes (operator ordering ruling).

## Review Focus

- Model turns count only real provider calls, not runtime-enforced or crystal-supplied decisions.
- Every executed tool step is counted exactly once, including failures.
- Secret-pattern strings in arguments never appear in an envelope.
- Envelope digests are deterministic for the same run record.

---

### Task 1: Budget Tracker and Envelope Contract

**Files:**
- Create: `app/kernel/sensorium/episode_envelope.py`
- Test: `tests/test_episode_envelope.py`

**Interfaces:**
- Produces: `RunBudgetTracker(store, emit)`, `.record_model_turn(...)`, `.record_tool_call(...)`, `.mark_wall(...)`; `EpisodeEnvelope` (sealed, `validate()`); `EpisodeEnvelopeBuilder.build(store, run_id)`; `EpisodeEnvelopeStore(path).put/get`; `envelope_from_swarm_episode(episode, *, run_id)`.

- [ ] Write tests for budget accumulation, provider-vs-estimated tokens, privacy filtering, sealing/tamper detection, deterministic digest, negative evidence for failed steps, and the swarm adapter.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_episode_envelope.py` and verify RED.
- [ ] Implement.
- [ ] Re-run and verify GREEN.

### Task 2: Planner Runtime Wiring

**Files:**
- Modify: `app/kernel/agents/planner_runtime.py`
- Test: `tests/test_episode_envelope.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `AgentPlannerRuntime(..., budget_tracker=None, envelope_store=None)`; metered provider calls at every model call site; per-tool budget events; wall time; `agent.episode.sealed` with the envelope digest at run end.

- [ ] Write scripted-run tests: budget counters match the script, runtime-enforced steps are not counted as model turns, and an envelope is sealed and stored at completion.
- [ ] Verify RED, implement, verify GREEN; re-run `tests/test_agent_planner_runtime.py` for regressions.
