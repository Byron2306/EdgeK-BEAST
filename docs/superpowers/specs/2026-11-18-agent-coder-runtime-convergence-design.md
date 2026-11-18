# Agent Coder Runtime Convergence Design

## Intent

Make the Desktop IDE's durable typed planner the single Agent Coder execution path and make the OpenCode-style Effect/schema runtime its real tool-execution substrate. A successful coding run must progress from a typed provider decision through governed isolated mutation, verification, SourcePlan evidence, and an IDE-visible terminal result without relying on provider-specific legacy orchestration.

## Goals

- Route every IDE request that declares `launch_strategy=typed_planner` through `AgentPlannerRuntime`, regardless of provider.
- Preserve `AgentRunStore`, approvals, isolated worktrees, verification, SourcePlan, and durable SSE as the authority boundaries.
- Use one canonical registry facade that keeps the existing BEAST tool contracts synchronized with the schema-first OpenCode registry.
- Execute authorized tools through `EffectToolExecutor`, including the real Effect TypeScript bridge, while retaining BEAST's existing approval and worktree checks.
- Run `CoderIntegrationCoordinator` preflight and verified-completion postflight from the typed planner so optional BEAST integrations no longer belong uniquely to the compatibility worker.
- Prove the provider-independent path with a deterministic create/edit/verify/SourcePlan acceptance test.
- Prove advanced compression, reusable-payload KV lookup, swarm dispatch, and upstream stream interception on the canonical path with truthful per-capability receipts.

## Non-goals

- Rewriting durable orchestration or the planner decision loop in TypeScript.
- Removing the compatibility stream worker in this tranche; it remains for old clients and simulation.
- Granting new promotion, worktree, remote-execution, or approval authority.
- Making optional crystal, swarm, KV, XDP, or ML-KEM integrations mandatory for a basic coding run. An explicit all-enabled acceptance tier covers the advanced path separately.
- Claiming a live NIM or Ollama success from deterministic acceptance alone.

## Constraints

- Existing tool IDs, schemas, observations, approvals, and SourcePlan semantics remain compatible.
- Schema and Effect failures fail closed and become durable tool observations.
- A tool is authorized once by the existing durable BEAST policy boundary; the Effect layer wraps the already-authorized handler and must not create a second approval system.
- Real `ToolExecutionContext`, including engine and isolated worktree custody, must reach Python handlers even though the Effect program crosses a JSON-RPC boundary.
- Integration events remain redacted and advisory; coordinator failures cannot grant authority or crash the base coding path.
- Existing dirty worktree changes are preserved.

## Approaches

### Optional Effect wrapper

Keep `AgentToolRuntime` as the default and enable Effect only by flag. This is low risk but preserves two execution paths and does not make the OpenCode work real in IDE runs.

### TypeScript planner replacement

Move planning, commands, tools, approvals, and events into TypeScript. This offers architectural purity but would replace mature durable Python contracts and greatly enlarge the acceptance surface.

### Durable Python host with mandatory Effect/schema tool boundary

Keep Python's planner and durable authority model, synchronize legacy BEAST tool specs into one canonical schema facade, and execute authorized handlers through Effect TS. This is the selected approach because it converges execution ownership while preserving the system's strongest tested boundaries.

## Architecture

```text
Desktop IDE
  -> durable AgentRun route
  -> AgentPlannerRuntime (all typed_planner providers)
  -> CoderIntegrationCoordinator preflight
  -> durable approval/worktree authorization
  -> canonical schema registry
  -> EffectToolExecutor / Effect TS bridge
  -> existing Python tool handler
  -> verification + SourcePlan
  -> coordinator verified-completion postflight
  -> durable SSE / IDE result
```

`CanonicalToolRegistry` is the only registry exposed by `AgentRunEngine`. It owns the existing BEAST `ToolSpec` records used by planner and governance and a synchronized OpenCode `ToolRegistry` projection used by Effect execution. Registration and replacement update both atomically.

`AgentToolRuntime` remains responsible for run lookup, read-only enforcement, immutable execution target checks, durable approval validation, worktree custody, observation shaping, and events. Once those checks pass, it delegates the handler invocation to `EffectToolExecutor.execute_authorized()`. The executor applies timeout/resource/cancellation policy and calls the exact registered Python handler through the Effect bridge.

The planner prepares coordinator context once per durable run after it has real observations. A bounded packet and completion marker are stored in the checkpoint so resume does not repeatedly fire integrations. Verified terminal completion invokes postflight once.

Provider adapters bind `StreamingComputeInterceptor` to their real streamed response body. A schema-valid complete planner decision closes the upstream response early and records emitted tokens, cancellation, stop reason, and measured savings. Parsing the complete response after download is not counted as interception.

Advanced integration receipts distinguish eligibility from execution. Compression must transform real observed source context; KV reuse must find payload-bearing bytes for the exact engine/model/tokenizer/prefix identity; swarm must record an admitted specialist dispatch and accepted governed result rather than selection alone. Synthetic KV fixtures remain valid deterministic tests but may not be described as engine-native live reuse.

## Acceptance

- A typed-planner request for a non-NIM/non-Ollama provider selects `typed_planner_v1`.
- The engine's public registry and Effect registry expose the same default tool IDs and reject the same malformed arguments.
- A real default tool executes through Effect and retains its durable BEAST observation/event contract.
- A worktree tool receives engine/worktree context through the Effect callback and completes under an approved capability.
- Typed planner preflight emits normalized integration events and includes its bounded packet in provider context.
- A deterministic coding run reaches `completed` only after mutation, verification, and SourcePlan evidence.
- With advanced flags enabled, a canonical-run test records real compression execution, an exact payload-bearing KV hit, an admitted/accepted specialist dispatch, and provider-stream early cancellation as four distinct receipts.
- Live evidence reports its provenance (`synthetic`, `captured_native_context`, or `engine_native_tensor`) and never promotes synthetic payloads into a native-KV claim.

