# Agent Coder Runtime Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the typed planner the canonical IDE coding path and execute its governed tools through the OpenCode-style schema and Effect runtime.

**Architecture:** Python retains durable orchestration, approvals, worktree custody, verification, and SourcePlan. A synchronized canonical registry projects existing BEAST tool specs into the schema-first registry, and `AgentToolRuntime` delegates already-authorized handler execution through Effect TS. The typed planner owns integration coordinator preflight/postflight for every provider.

**Tech Stack:** Python 3.13, FastAPI, asyncio, Effect TypeScript JSON-RPC bridge, pytest, Electron renderer

**Spec:** `docs/superpowers/specs/2026-11-18-agent-coder-runtime-convergence-design.md`

## Global Constraints

- Preserve existing tool IDs, durable observations, approval semantics, isolated worktrees, verification, and SourcePlan behavior.
- Do not introduce a second approval authority in the Effect/schema layer.
- Optional integrations must fail closed without preventing the base coding loop.
- Preserve unrelated dirty worktree changes.
- No production gateway restart or live provider claim is part of deterministic acceptance.
- Advanced acceptance must distinguish deterministic synthetic fixtures from live engine-native evidence.

## Review Focus

- Approval-required tools must not execute when the Effect path is invoked without the existing durable approval.
- Real worktree/engine context must survive the Effect callback boundary.
- Remote execution targets must remain bound to the immutable AgentRun destination.
- Resume must not duplicate coordinator preflight or postflight effects.
- Provider-neutral typed launch must not break legacy simulation clients.

---

### Task 1: Canonical schema registry facade

**Files:**
- Create: `app/kernel/agents/canonical_tool_registry.py`
- Modify: `app/kernel/agents/run_engine.py`
- Test: `tests/test_canonical_tool_registry.py`

**Interfaces:**
- Consumes: `build_default_tool_registry() -> AgentToolRegistry` and `ToolRegistry`.
- Produces: `CanonicalToolRegistry.from_agent_registry(registry, workspace_root)` with `get`, `list`, `validate_arguments`, `register`, and `effect_registry`.

- [ ] Write failing tests proving default tool parity and schema rejection.
- [ ] Run the focused tests and verify RED because the facade does not exist.
- [ ] Implement synchronized registration and configure `AgentRunEngine` to expose the facade.
- [ ] Run the focused registry and existing tool-runtime tests and verify GREEN.

### Task 2: Effect execution behind existing BEAST authorization

**Files:**
- Modify: `app/kernel/agents/effect_tool_executor.py`
- Modify: `app/kernel/agents/tool_runtime.py`
- Modify: `app/kernel/agents/run_engine.py`
- Test: `tests/test_effect_agent_tool_runtime.py`

**Interfaces:**
- Consumes: authorized `ToolSpec`, arguments, and `ToolExecutionContext` from `AgentToolRuntime`.
- Produces: `EffectToolExecutor.execute_authorized(tool_id, arguments, context, ...) -> ToolCallResult`.

- [ ] Write failing tests proving a default read tool runs through Effect and a worktree handler receives real engine custody.
- [ ] Run the focused tests and verify RED because default execution still calls handlers directly.
- [ ] Add the authorized execution entry point and context-token bridge; delegate from `AgentToolRuntime` after existing policy checks.
- [ ] Run focused Effect, tool-runtime, planner-runtime, and route tests and verify GREEN.

### Task 3: Typed planner integration preflight and postflight

**Files:**
- Modify: `app/kernel/agents/planner_runtime.py`
- Test: `tests/test_agent_planner_integrations.py`

**Interfaces:**
- Consumes: real planner observations and `CoderIntegrationCoordinator.prepare/complete`.
- Produces: checkpointed `coder_integrations` packet plus normalized durable `agent.integration.*` events.

- [ ] Write failing tests proving preflight fires once, provider context includes the packet, and verified postflight fires once.
- [ ] Run the focused tests and verify RED because the typed planner does not own the coordinator.
- [ ] Implement bounded preflight/postflight with failure isolation and resume markers.
- [ ] Run focused coordinator and planner suites and verify GREEN.

### Task 4: Provider-neutral typed launch and coding acceptance

**Files:**
- Modify: `app/routes/ide_routes/agent_runs.py`
- Test: `tests/routes/test_agent_run_routes.py`
- Test: `tests/test_agent_coder_canonical_acceptance.py`

**Interfaces:**
- Consumes: request `launch_strategy=typed_planner` and the existing generic `CallbackPlannerProvider` fallback.
- Produces: `typed_planner_v1` for every explicit typed-planner IDE run.

- [ ] Write failing route and deterministic edit/verify/SourcePlan acceptance tests.
- [ ] Run both tests and verify RED because generic providers still select the compatibility worker.
- [ ] Make explicit typed strategy provider-neutral while retaining legacy simulation fallback.
- [ ] Run route, planner, Effect, desktop contract, and full project tests; record any unrelated pre-existing failures.

### Task 5: Advanced canonical-path acceptance

**Files:**
- Modify: `app/kernel/agents/coder_integrations.py`
- Modify: `app/kernel/agents/ollama_planner_provider.py`
- Modify: `app/kernel/agents/nim_planner_provider.py`
- Test: `tests/test_agent_coder_advanced_acceptance.py`
- Test: `tests/test_planner_stream_interception.py`

**Interfaces:**
- Consumes: observed source files, exact KV identity and payload, admitted specialist dispatcher, and real provider streams.
- Produces: bounded integration packets plus distinct compression/KV/swarm/interception receipts with provenance.

- [ ] Write failing tests for real-source compression, exact payload-bearing KV reuse, admitted specialist dispatch, and upstream early cancellation.
- [ ] Run focused tests and verify RED where selection-only swarm and unbound provider streams fall short.
- [ ] Bind specialist dispatch to the coordinator without granting authority, and bind `StreamingComputeInterceptor` to Ollama/NIM streamed bodies.
- [ ] Add a same-run advanced acceptance test and provenance fields that prevent synthetic KV from being claimed as native capture.
- [ ] Run focused advanced tests, the complete canonical Agent Coder suite, and the relevant existing phase-8/KV suites.

