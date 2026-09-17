# BEAST Coding Agent Responsibility Census

## Truth boundary

A responsibility claim identifies current ownership pressure; it does not promote runtime participation unless the claimant evidence is observed_runtime.

Responsibilities: **24**  
Unique claimants: **42**  
Unresolved conflicts: **13**  
Phase 1 ownership conflicts: **17**

## Responsibility map

| Responsibility | Status | Current authority | Candidate/supporting claimants | Evidence |
|---|---|---|---|---|
| `run_identity_and_durable_event_ledger` | `observed_authoritative` | `app/kernel/agents/run_store.py` | `app/kernel/agents/run_engine.py` (supporting) | observed_runtime |
| `runtime_planning` | `observed_authoritative` | `app/kernel/agents/planner_runtime.py` | none | observed_runtime |
| `tool_execution_dispatch` | `observed_authoritative` | `app/kernel/agents/tool_runtime.py` | `app/kernel/agents/worktree_tools.py` (supporting) | observed_runtime, static_contract |
| `planner_completion_decision` | `observed_authoritative` | `app/kernel/agents/planner_runtime.py` | none | observed_runtime |
| `operator_mode_and_prompt_intent` | `static_authoritative` | `desktop-ide/renderer/js/ai/mode-controller.js` | `desktop-ide/renderer/js/ai/agent-client.js` (supporting) | static_contract |
| `model_output_protocol` | `unresolved_conflict` | none proven | `desktop-ide/renderer/js/ai/mode-controller.js` (candidate_authority), `app/kernel/agents/planner_runtime.py` (candidate_authority), `app/kernel/governance/output_governor.py` (candidate_authority), `app/kernel/compute/action_ir.py` (supporting) | existing_disposition_registry, observed_runtime, static_contract |
| `agent_run_launch_and_provider_selection` | `unresolved_conflict` | none proven | `desktop-ide/renderer/js/ai/agent-client.js` (candidate_authority), `app/routes/ide_routes/agent_runs.py` (candidate_authority), `app/kernel/compute/inference_interceptor.py` (candidate_authority), `app/kernel/compute/compute_plane.py` (candidate_authority) | existing_disposition_registry, static_contract |
| `repository_context_selection` | `unresolved_conflict` | none proven | `desktop-ide/renderer/js/ai/context-picker.js` (candidate_authority), `app/kernel/data_processing/context_packet.py` (candidate_authority), `app/kernel/data_processing/code_cortex.py` (candidate_authority), `app/kernel/agents/semantic_context.py` (candidate_authority), `desktop-ide/renderer/js/ai/context-manifest.js` (supporting) | static_contract |
| `context_budget_and_compaction` | `unresolved_conflict` | none proven | `desktop-ide/renderer/js/beast-ai-coding.js` (candidate_authority), `desktop-ide/renderer/js/ai/agent-client.js` (candidate_authority), `app/kernel/execution/task_envelope.py` (candidate_authority), `app/kernel/data_processing/context_packet.py` (candidate_authority), `app/kernel/compute/compression_pipeline.py` (candidate_authority), `app/kernel/agents/planner_runtime.py` (candidate_authority) | existing_disposition_registry, observed_runtime, static_contract |
| `editable_source_exactness` | `static_authoritative` | `app/kernel/compute/compression_pipeline.py` | `app/kernel/compute/action_ir.py` (supporting) | existing_disposition_registry |
| `local_planner_provider_budget` | `unresolved_conflict` | none proven | `app/kernel/agents/ollama_planner_provider.py` (candidate_authority), `desktop-ide/renderer/js/beast-ai-coding.js` (candidate_authority), `desktop-ide/renderer/js/ai/agent-client.js` (supporting) | static_contract |
| `governed_inference_routing` | `unresolved_conflict` | none proven | `app/kernel/compute/inference_interceptor.py` (candidate_authority), `app/kernel/compute/compute_plane.py` (candidate_authority), `app/routes/ide_routes/agent_runs.py` (candidate_authority) | existing_disposition_registry, static_contract |
| `stream_output_admission` | `static_authoritative` | `app/kernel/compute/streaming_interceptor.py` | `app/kernel/governance/output_governor.py` (supporting) | existing_disposition_registry, static_contract |
| `verification_gate` | `unresolved_conflict` | `app/kernel/agents/planner_runtime.py` | `app/kernel/data_processing/quality_cascade.py` (candidate_authority), `app/kernel/evidence/post_apply_gate.py` (candidate_authority) | observed_runtime, static_contract |
| `sourceplan_handoff_and_approval` | `unresolved_conflict` | `app/kernel/agents/planner_runtime.py` | `app/kernel/agents/sourceplan_approval.py` (candidate_authority), `app/kernel/evidence/sourceplan_handoff.py` (candidate_authority), `app/kernel/approvals/mode_engine.py` (supporting), `app/kernel/approvals/capability_runtime.py` (supporting) | observed_runtime, static_contract |
| `agent_memory_and_continuity` | `unresolved_conflict` | `app/kernel/agents/run_store.py` | `app/kernel/storage/memory_hull.py` (candidate_authority), `app/kernel/storage/memory_stack.py` (candidate_authority) | observed_runtime, static_contract |
| `coding_evidence_production` | `unresolved_conflict` | `app/kernel/agents/run_store.py` | `app/kernel/storage/evidence_envelope.py` (candidate_authority), `app/kernel/storage/evidence_chronicle.py` (candidate_authority), `app/kernel/data_processing/quality_cascade.py` (supporting) | observed_runtime, static_contract |
| `sensorium_agent_observation` | `unresolved_conflict` | none proven | `app/kernel/agents/run_engine.py` (candidate_authority), `app/kernel/sensorium/runtime.py` (candidate_authority) | not_runtime_proven, static_contract |
| `verified_inference_reuse` | `static_authoritative` | `app/kernel/compute/crystal_reuse_gateway.py` | `app/kernel/storage/memory_hull.py` (supporting) | existing_disposition_registry, static_contract |
| `mission_edit_reuse_lattice` | `static_authoritative` | `app/kernel/compute/mission_crystal_lattice.py` | `app/kernel/compute/runtime_crystallizer.py` (supporting) | existing_disposition_registry |
| `crystal_generalization_promotion_and_replay` | `unresolved_conflict` | none proven | `app/kernel/compute/runtime_crystallizer.py` (candidate_authority), `app/kernel/compute/physical_crystal_lifecycle.py` (candidate_authority), `app/kernel/compute/typed_crystal_interpreter.py` (candidate_authority), `app/kernel/compute/crystal_reuse_gateway.py` (candidate_authority) | existing_disposition_registry |
| `crystal_transport_and_memfd_capsules` | `dormant_or_stranded` | none proven | `app/kernel/crystal_bus/fd_transport.py` (dormant_candidate), `app/kernel/compute/sealed_capsule.py` (dormant_candidate) | existing_disposition_registry, not_runtime_proven |
| `task_input_governance` | `unresolved_conflict` | none proven | `app/kernel/execution/task_envelope.py` (candidate_authority), `app/kernel/approvals/mode_engine.py` (candidate_authority), `desktop-ide/renderer/js/ai/mode-controller.js` (candidate_authority) | static_contract |
| `distributed_execution_and_forge` | `supporting_only` | none proven | `app/kernel/compute/distributed_forge_scheduler.py` (supporting), `app/kernel/compute/forge_supervisor.py` (supporting), `app/kernel/compute/compute_plane.py` (supporting) | existing_disposition_registry |

## Phase 1 ownership conflicts

### `agent_memory_and_continuity`

AgentRunStore is observed for durable run continuity, while Memory Hull and Memory Stack provide longer-lived residue, project facts, skills, and forensic memory. The coding agent has no explicit memory tier contract tying them together.

- `app/kernel/agents/run_store.py`: role `current_authority`, disposition `online_authoritative`, evidence `observed_runtime`.
- `app/kernel/storage/memory_hull.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/storage/memory_stack.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.

### `agent_run_launch_and_provider_selection`

Renderer routing, AgentRun backend provider preference, and the governed compute plane all participate in provider/route choice; the coding-agent composition root is not singularly owned.

- `desktop-ide/renderer/js/ai/agent-client.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/routes/ide_routes/agent_runs.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/compute/inference_interceptor.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/compute/compute_plane.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.

### `coding_evidence_production`

The observed agent ledger proves run/tool/planner events, while evidence envelopes and Chronicle are separate proof stores used by adjacent organs. Phase 1 must define which receipts constitute coding-agent truth.

- `app/kernel/agents/run_store.py`: role `current_authority`, disposition `online_authoritative`, evidence `observed_runtime`.
- `app/kernel/storage/evidence_envelope.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/storage/evidence_chronicle.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/data_processing/quality_cascade.py`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.

### `context_budget_and_compaction`

The renderer clips planner context to three files, TaskEnvelope defaults to eight files/8K tokens, ContextPacket performs bounded evidence packing, CompressionPipeline offers source-bound compression, and PlannerRuntime performs its own compaction. Budget ownership is fragmented.

- `desktop-ide/renderer/js/beast-ai-coding.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `desktop-ide/renderer/js/ai/agent-client.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/execution/task_envelope.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/data_processing/context_packet.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/compute/compression_pipeline.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/agents/planner_runtime.py`: role `candidate_authority`, disposition `online_authoritative`, evidence `observed_runtime`.

### `crystal_generalization_promotion_and_replay`

BEAST already has separate generalization, physical-promotion, typed replay, and reuse-routing organs. Coding-agent integration must preserve their distinct authority gates instead of collapsing them into generic memory.

- `app/kernel/compute/runtime_crystallizer.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/compute/physical_crystal_lifecycle.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/compute/typed_crystal_interpreter.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/compute/crystal_reuse_gateway.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.

### `crystal_transport_and_memfd_capsules`

Sealed memfd/capsule transport is available as immutable transport evidence, not ambient execution or confidentiality authority; it is not observed in the coding-agent journey.

- `app/kernel/crystal_bus/fd_transport.py`: role `dormant_candidate`, disposition `dormant_gated`, evidence `not_runtime_proven`.
- `app/kernel/compute/sealed_capsule.py`: role `dormant_candidate`, disposition `stranded`, evidence `existing_disposition_registry`.

### `governed_inference_routing`

BEAST has a governed compute/interception plane, while the coding-agent route can prefer direct local planner execution. Phase 1 must establish one coding-agent inference composition root.

- `app/kernel/compute/inference_interceptor.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/kernel/compute/compute_plane.py`: role `candidate_authority`, disposition `online_supporting`, evidence `existing_disposition_registry`.
- `app/routes/ide_routes/agent_runs.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.

### `local_planner_provider_budget`

Backend Ollama defaults use 768 context and 96 predicted tokens (48 on native-context continuation), while renderer profiles advertise materially larger context/output budgets. Operator-visible and executable budgets disagree.

- `app/kernel/agents/ollama_planner_provider.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `desktop-ide/renderer/js/beast-ai-coding.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `desktop-ide/renderer/js/ai/agent-client.js`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.

### `mission_edit_reuse_lattice`

MissionCrystalLattice records verified SourcePlan situations but is explicitly advisory/no-auto-apply; it should feed planning without becoming mutation authority.

- `app/kernel/compute/mission_crystal_lattice.py`: role `current_authority`, disposition `online_authoritative`, evidence `existing_disposition_registry`.
- `app/kernel/compute/runtime_crystallizer.py`: role `supporting`, disposition `online_supporting`, evidence `existing_disposition_registry`.

### `model_output_protocol`

Renderer instructions demand Action IR while the observed typed planner consumes PlannerDecision tool/complete/blocked decisions; OutputGovernor separately compiles provider Action IR. Protocol ownership is split.

- `desktop-ide/renderer/js/ai/mode-controller.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/agents/planner_runtime.py`: role `candidate_authority`, disposition `online_authoritative`, evidence `observed_runtime`.
- `app/kernel/governance/output_governor.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/compute/action_ir.py`: role `supporting`, disposition `online_supporting`, evidence `existing_disposition_registry`.

### `planner_completion_decision`

Current completion authority is observed in AgentPlannerRuntime, but the Phase 0 cross-file journey completed with consumer.py unresolved; completion semantics require redesign before promotion.

- `app/kernel/agents/planner_runtime.py`: role `current_authority`, disposition `online_authoritative`, evidence `observed_runtime`.

### `repository_context_selection`

Frontend selection, deterministic ContextPacket packing, Code Cortex repository intelligence, semantic planner context, and the renderer manifest all claim parts of context selection without one explicit authority boundary.

- `desktop-ide/renderer/js/ai/context-picker.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/data_processing/context_packet.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/data_processing/code_cortex.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/agents/semantic_context.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `desktop-ide/renderer/js/ai/context-manifest.js`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.

### `sensorium_agent_observation`

AgentRunEngine attempts best-effort Sensorium mirroring, but the Phase 0 runtime harness has no independent Sensorium receipt. The observation edge remains unproven.

- `app/kernel/agents/run_engine.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/sensorium/runtime.py`: role `candidate_authority`, disposition `online_supporting`, evidence `not_runtime_proven`.

### `sourceplan_handoff_and_approval`

PlannerRuntime requires SourcePlan draft evidence, while approval, handoff, and capability layers separately define whether mutation may proceed. Their authority boundaries need one explicit chain.

- `app/kernel/agents/planner_runtime.py`: role `current_authority`, disposition `online_authoritative`, evidence `observed_runtime`.
- `app/kernel/agents/sourceplan_approval.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/evidence/sourceplan_handoff.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/approvals/mode_engine.py`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/approvals/capability_runtime.py`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.

### `task_input_governance`

Natural-language intent is interpreted independently by renderer mode rules, TaskEnvelope classification/budgets, and approval-mode policy. A single typed coding mission envelope is not yet authoritative.

- `app/kernel/execution/task_envelope.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/approvals/mode_engine.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `desktop-ide/renderer/js/ai/mode-controller.js`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.

### `verification_gate`

Observed planner execution enforces worktree.verify after mutation, while QualityCascade and the post-apply evidence gate provide broader verification semantics that are not observed in the coding-agent journey.

- `app/kernel/agents/planner_runtime.py`: role `current_authority`, disposition `online_authoritative`, evidence `observed_runtime`.
- `app/kernel/data_processing/quality_cascade.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.
- `app/kernel/evidence/post_apply_gate.py`: role `candidate_authority`, disposition `online_supporting`, evidence `static_contract`.

### `verified_inference_reuse`

CrystalReuseGateway defines verified replay/semantic credit/KV/local execution ordering and only promotes verified results, but Phase 0 has not observed it on the coding-agent path.

- `app/kernel/compute/crystal_reuse_gateway.py`: role `current_authority`, disposition `online_authoritative`, evidence `existing_disposition_registry`.
- `app/kernel/storage/memory_hull.py`: role `supporting`, disposition `online_supporting`, evidence `static_contract`.
