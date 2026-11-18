# Nemotron Handoff: Finish BEAST Agent Coder Runtime Convergence

## Mission

Finish and prove a successful Desktop IDE coding run on the canonical OpenCode-style path. Do not stop at backend unit tests. The IDE must visibly show the typed planner, Effect-backed tool execution, advanced integration receipts, verification, SourcePlan readiness, and a clean terminal state.

Read these first:

1. `docs/superpowers/specs/2026-11-18-agent-coder-runtime-convergence-design.md`
2. `docs/superpowers/plans/2026-11-18-agent-coder-runtime-convergence.md`
3. `docs/BEAST_PHYSICAL_STACK_CENSUS.md`
4. This handoff from top to bottom.

## Safety and worktree constraints

- The worktree contains a very large amount of user-owned work. Do not reset, clean, checkout, or delete unrelated changes.
- Use `apply_patch` for edits.
- Do not weaken immutable execution-target checks to satisfy stale tests.
- Preserve the existing durable BEAST authority boundary: approvals, worktree custody, verification, and SourcePlan remain authoritative.
- Effect/schema execution wraps an already-authorized handler; it must not create a second approval system.
- Never claim engine-native KV from synthetic bytes. Report provenance explicitly.
- Use `.venv/bin/python -m pytest`, not system Python.

## Work already completed

### Canonical OpenCode-style tool path

- Added `app/kernel/agents/canonical_tool_registry.py`.
- `AgentRunEngine` now exposes one facade over the legacy BEAST registry and schema-first registry.
- `AgentToolRuntime` invokes authorized default tools through `EffectToolExecutor` and the Effect TypeScript bridge.
- Real `ToolExecutionContext`, including engine and isolated worktree custody, survives the JSON-RPC callback boundary.
- Tool completion events include `runtime: effect_ts`.

Focused tests already green:

```bash
.venv/bin/python -m pytest -q \
  tests/test_canonical_tool_registry.py \
  tests/test_effect_agent_tool_runtime.py \
  tests/test_effect_tool_executor.py
```

### Typed planner convergence

- Explicit `launch_strategy=typed_planner` is provider-neutral in `app/routes/ide_routes/agent_runs.py`.
- Old simulation clients without an explicit typed strategy retain the compatibility path.
- `AgentPlannerRuntime` owns `CoderIntegrationCoordinator` preflight and verified-completion postflight.
- Preflight is checkpointed once, injects a bounded packet into the next provider prompt, and emits durable `agent.integration.*` events.
- Postflight runs once only after completed verification and SourcePlan evidence.

Focused tests already green:

```bash
.venv/bin/python -m pytest -q \
  tests/test_agent_planner_integrations.py \
  tests/routes/test_agent_run_routes.py
```

### Advanced features on the canonical run

- Compression now receives real observed source files from the typed planner.
- KV lookup fires only for an exact engine/model/tokenizer/prefix hit with payload bytes.
- KV receipts now carry `artifacts.provenance`; deterministic acceptance uses `synthetic_fixture` and must not be described as native capture.
- `KVEngineAdapter` labels its captured bytes `engine_adapter_capture`.
- Swarm integration can now perform an actual `SwarmSpecialistDispatch`, behind the existing compute governor, and inject only accepted bounded advice into provider context.
- NIM SSE and Ollama NDJSON adapters now use `StreamingComputeInterceptor`, recognize typed `decision_type` objects, close upstream on a complete schema-valid action, and record savings/cancellation receipts.
- Planner persists `agent.stream.interception` events.
- A deterministic full coding run now proves: NIM streaming decisions, Effect TS tools, real edit, focused pytest verification, SourcePlan, compression, payload-bearing KV lookup, governed swarm dispatch, and upstream cancellation.

Focused tests green at handoff:

```bash
.venv/bin/python -m pytest -q tests/test_agent_coder_advanced_acceptance.py
# Result: 2 passed

.venv/bin/python -m pytest -q \
  tests/test_planner_stream_interception.py \
  tests/test_streaming_interceptor.py \
  tests/proof/test_nim_planner_provider.py
# Result before the final projection assertions were added: 22 passed

.venv/bin/python -m pytest -q \
  tests/test_agent_coder_advanced_acceptance.py \
  tests/kernel/agents/test_coder_integrations.py \
  tests/test_kv_cache_transport.py \
  tests/test_kv_crystal_tier.py
# Result before the full-run test was added: 36 passed
```

## Evidence truth discovered

The later receipts do not prove live IDE native-KV reuse:

- `evidence/ide-full-architecture-20261117T212110Z/kv-state.json` has zero blocks and zero bytes.
- `evidence/kv-crystal-tier-20261118T113444Z/receipt.json` is green but explicitly synthetic and not engine-native/cross-engine.
- `docs/BEAST_PHYSICAL_STACK_CENSUS.md` says Ollama native context is the only current real KV source; Crystal tensor gauntlets use synthetic tensors; no broad cross-engine native claim is justified.

Keep three distinct labels:

- `synthetic_fixture`: deterministic test bytes only.
- `captured_native_context`: real provider-native context handle/state where supported.
- `engine_adapter_capture`: bytes captured by a real engine adapter.

Do not rename synthetic fixture success to engine-native success.

## Exact remaining work

### 1. Verify the just-added IDE event wiring

The final edits before handoff changed:

- `app/kernel/agents/run_events.py`
  - typed planner stage text includes `typed_planner_v1`;
  - Effect tool result text includes `via Effect TS`;
  - `agent.stream.interception` projects to `agent_run_interception`.
- `desktop-ide/renderer/js/ai/agent-client.js`
  - fresh and reconnect flows render integration receipts as turns/progress;
  - fresh and reconnect flows render stream-interception receipts.
- `desktop-ide/renderer/js/beast-integration-map.js`
  - retains safe `metrics` and `artifacts`, including KV provenance.
- `tests/test_planner_stream_interception.py`
  - added legacy projection assertions.

Run immediately:

```bash
node --check desktop-ide/renderer/js/ai/agent-client.js
node --check desktop-ide/renderer/js/beast-integration-map.js

.venv/bin/python -m pytest -q \
  tests/test_planner_stream_interception.py \
  tests/test_streaming_interceptor.py \
  tests/proof/test_nim_planner_provider.py

node --test \
  desktop-ide/tests/integration-sse-dispatch.test.js \
  desktop-ide/tests/integration-replay-client.test.js \
  desktop-ide/tests/integration-sse-cursor.test.js
```

Fix any failure narrowly. The SSE dispatch test extracts exactly two production `agent_run_integration` listener blocks; keep both fresh and reconnect listeners symmetrical.

### 2. Add an IDE acceptance test, not another backend-only test

Add `desktop-ide/tests/agent-coder-advanced-runtime.test.js` (or extend the existing SSE dispatch harness) that feeds these legacy SSE events to the production listener flow:

1. `agent_run_stage` with `engine: typed_planner_v1`.
2. `agent_run_integration` for:
   - `compression.longcodezip`, `execution/context_compression`, fired;
   - `kv_transport`, `execution/prefix_reuse_lookup`, fired, with `artifacts.provenance=synthetic_fixture` in deterministic mode;
   - `swarm_specialist`, `execution/specialist_dispatch`, fired.
3. `agent_run_interception` with `upstream_cancel_requested=true` and savings.
4. `agent_run_tool` completed with `runtime=effect_ts`.
5. `agent_run_validation` passed.
6. `agent_run_sourceplan` with a real plan containing operations.
7. `agent_run_done` completed.

Assert the Pair Programmer state visibly contains:

- trace/progress for typed planner;
- integration turns for compression, KV, and swarm;
- stream interception turn with saved-token detail;
- tool text saying Effect TS;
- verification passed;
- `sourcePlanReady=true` and a staged proposal;
- final status `ready-to-review`, not the false fallback “finished without a promotable SourcePlan.”

Do not merely assert that listeners were registered.

### 3. Confirm SourcePlan reaches the IDE on typed runs

`app/kernel/agents/worktree_tools.py::_worktree_sourceplan` already emits canonical `agent.sourceplan.ready`, which projects to `agent_run_sourceplan`. Confirm its payload has everything the renderer needs:

- `plan` is a dict;
- `plan.operations` is non-empty for the deterministic edit;
- `plan_id` is present;
- renderer `stageSourcePlan()` returns `ready=true`.

If the IDE test falls into “without a promotable SourcePlan,” debug the projection/payload first. Do not paper over it by changing the terminal fallback.

### 4. Make all advanced events visible in Atlas and Pair Programmer

Confirm:

- Pair Programmer trace and turn cards show compression, KV, swarm, interception, and Effect TS.
- Atlas lifecycle receipts retain `stage`, `operation`, `status`, `reason`, safe metrics, and safe artifacts.
- KV receipt visibly says `synthetic_fixture` in deterministic tests.
- Swarm selection-only events remain `eligibility/specialist_selection`; only accepted dispatch is `execution/specialist_dispatch`.
- Stream interception is a separate event, not mislabeled as an integration durable effect.

### 5. Run the canonical regression set

```bash
.venv/bin/python -m pytest -q \
  tests/test_canonical_tool_registry.py \
  tests/test_effect_agent_tool_runtime.py \
  tests/test_effect_tool_executor.py \
  tests/test_agent_planner_integrations.py \
  tests/test_agent_coder_advanced_acceptance.py \
  tests/test_planner_stream_interception.py \
  tests/test_streaming_interceptor.py \
  tests/proof/test_nim_planner_provider.py \
  tests/kernel/agents/test_coder_integrations.py \
  tests/test_swarm_specialist.py \
  tests/test_kv_cache_transport.py \
  tests/test_kv_crystal_tier.py \
  tests/routes/test_agent_run_routes.py \
  tests/test_agent_planner_runtime.py
```

Then run the relevant Desktop IDE tests and the normal repository test command if time permits.

Known broader-suite observations from before this handoff:

- Three legacy detached-simulation route tests sometimes ended `cancelled` under the TestClient background lifecycle instead of their expected legacy states.
- One stale remote-index test attempted to change a run's immutable target from local to container; do not weaken the immutable-target rule to satisfy it.

Investigate and document these separately if they remain. They are not permission to loosen safety boundaries.

### 6. Perform one live local IDE run if Ollama is reachable

Read-only probe first:

```bash
curl -fsS http://127.0.0.1:11434/api/tags
```

If reachable and a coder model is installed:

1. Start the supported BEAST stack/IDE using the repository scripts.
2. Open a tiny committed Python fixture with a focused pytest.
3. Enable the advanced flags used by the coordinator:
   - `BEAST_COMPRESSION_TIERS=1`
   - `BEAST_ZERO_COPY_KV=1`
   - `BEAST_SWARM_SPECIALIST=1`
4. Run one explicit Agent-mode edit from the IDE.
5. Capture the durable run ID and events.
6. Verify the IDE shows typed planner, Effect TS, compression, swarm dispatch or a truthful refusal, interception, focused verification, SourcePlan, and terminal completion.
7. KV may truthfully be skipped unless a real exact reusable provider payload exists. Do not seed synthetic bytes and call that a live native hit.

If Ollama is unavailable, report deterministic acceptance separately from live-provider acceptance.

## Definition of done

All of the following must be true:

- Explicit typed planner works for every provider route used by the IDE.
- Default governed tools execute through Effect TS after BEAST authorization.
- A real deterministic edit reaches focused behavioral verification and SourcePlan.
- Compression operates on observed source, not empty/request-only context.
- KV fires only on an exact payload-bearing hit and exposes provenance.
- Swarm `fired/execution` means an admitted and accepted dispatch, not selection.
- NIM/Ollama streamed planner output closes upstream on the first complete valid decision.
- Fresh and replayed IDE streams render the same advanced receipts.
- The Pair Programmer finishes at `ready-to-review` with a real SourcePlan.
- Tests and live evidence are reported separately and truthfully.

## Final report format

Report four sections only:

1. **Implemented** — exact code paths completed.
2. **IDE proof** — what was visibly exercised, with run ID and event names.
3. **Verification** — exact commands and pass/fail counts.
4. **Truthful limitations** — especially native KV availability and any live provider/environment blocker.

