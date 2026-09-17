# BEAST Coding Agent Phase 1 Authority Map

Target authority contracts do not prove live wiring. Runtime claims require independently observed receipts.

| Responsibility | Scope | Target authority | Kind |
|---|---|---|---|
| `agent_memory_and_continuity` | `run_continuity_truth` | `app/kernel/agents/run_store.py` | `scoped_chain` |
| `agent_memory_and_continuity` | `long_lived_residue` | `app/kernel/storage/memory_hull.py` | `scoped_chain` |
| `agent_run_launch_and_provider_selection` | `coding_agent_launch` | `app/routes/ide_routes/agent_runs.py` | `scoped_chain` |
| `agent_run_launch_and_provider_selection` | `provider_route_admission` | `app/kernel/compute/compute_plane.py` | `scoped_chain` |
| `coding_evidence_production` | `run_event_truth` | `app/kernel/agents/run_store.py` | `scoped_chain` |
| `coding_evidence_production` | `evidence_preservation` | `app/kernel/storage/evidence_chronicle.py` | `scoped_chain` |
| `context_budget_and_compaction` | `model_handoff_budget` | `app/kernel/data_processing/context_packet.py` | `scoped_chain` |
| `context_budget_and_compaction` | `source_bound_compression` | `app/kernel/compute/compression_pipeline.py` | `scoped_chain` |
| `crystal_generalization_promotion_and_replay` | `candidate_generalization` | `app/kernel/compute/runtime_crystallizer.py` | `scoped_chain` |
| `crystal_generalization_promotion_and_replay` | `physical_promotion` | `app/kernel/compute/physical_crystal_lifecycle.py` | `scoped_chain` |
| `crystal_generalization_promotion_and_replay` | `typed_replay` | `app/kernel/compute/typed_crystal_interpreter.py` | `scoped_chain` |
| `crystal_transport_and_memfd_capsules` | `immutable_capsule_transport` | `app/kernel/crystal_bus/fd_transport.py` | `transport_only` |
| `governed_inference_routing` | `coding_agent_inference_composition` | `app/kernel/compute/compute_plane.py` | `single_authority` |
| `local_planner_provider_budget` | `effective_ollama_budget` | `app/kernel/agents/ollama_planner_provider.py` | `single_authority` |
| `mission_edit_reuse_lattice` | `verified_edit_reuse_advice` | `app/kernel/compute/mission_crystal_lattice.py` | `advisory_only` |
| `model_output_protocol` | `typed_planner_decision` | `app/kernel/agents/planner_provider.py` | `scoped_chain` |
| `model_output_protocol` | `direct_source_patch_output` | `app/kernel/governance/output_governor.py` | `scoped_chain` |
| `planner_completion_decision` | `whole_objective_completion` | `app/kernel/agents/planner_runtime.py` | `single_authority` |
| `repository_context_selection` | `repository_candidate_discovery` | `app/kernel/data_processing/code_cortex.py` | `scoped_chain` |
| `repository_context_selection` | `model_handoff_context` | `app/kernel/data_processing/context_packet.py` | `scoped_chain` |
| `sensorium_agent_observation` | `observation_admission` | `app/kernel/sensorium/runtime.py` | `single_authority` |
| `sourceplan_handoff_and_approval` | `sourceplan_approval` | `app/kernel/agents/sourceplan_approval.py` | `scoped_chain` |
| `sourceplan_handoff_and_approval` | `sourceplan_evidence_handoff` | `app/kernel/evidence/sourceplan_handoff.py` | `scoped_chain` |
| `task_input_governance` | `typed_mission_envelope` | `app/kernel/execution/task_envelope.py` | `single_authority` |
| `verification_gate` | `fresh_mutation_verification` | `app/kernel/agents/phase_d_execution.py` | `scoped_chain` |
| `verification_gate` | `post_apply_evidence_admission` | `app/kernel/evidence/post_apply_gate.py` | `scoped_chain` |
| `verified_inference_reuse` | `reuse_admission` | `app/kernel/compute/crystal_reuse_gateway.py` | `single_authority` |

## Phase 2/3 repair queue

### `agent_memory_and_continuity`

RunStore owns durable run history; MemoryHull holds optional long-lived residue and cannot rewrite the event chain.

Target status: `target_only_unverified`.

- `separate_run_store_events_from_memory_hull_residue`
- `require_provenance_before_long_lived_memory_promotion`

### `agent_run_launch_and_provider_selection`

Backend route binds the mission and governed compute admits the provider; frontend preference is only a request.

Target status: `target_only_unverified`.

- `bind_agent_run_launch_to_compute_route_receipt`
- `make_renderer_provider_preference_advisory`

### `coding_evidence_production`

The observed run ledger is primary; Chronicle preserves derived evidence without asserting unobserved success.

Target status: `target_only_unverified`.

- `link_agent_run_receipts_to_chronicle_without_rewriting_status`

### `context_budget_and_compaction`

ContextPacket sets the final handoff budget; source-bound summaries cannot authorize editable anchors.

Target status: `target_only_unverified`.

- `remove_frontend_three_file_truncation`
- `preserve_exact_editable_anchors_during_compaction`

### `crystal_generalization_promotion_and_replay`

Separate candidate, promotion, and typed replay gates retain distinct authority; no replay authorizes a mutation.

Target status: `target_only_unverified`.

- `require_transfer_verification_before_physical_promotion`
- `revalidate_typed_replay_against_current_source`

### `crystal_transport_and_memfd_capsules`

Sealed memfd transport does not grant execution or confidentiality authority and is not observed on the coding-agent route.

Target status: `target_only_unverified`.

- `prove_fd_transport_on_coding_agent_path_before_activation`

### `governed_inference_routing`

One compute composition root governs every provider attempt; direct local calls must be routed through it.

Target status: `target_only_unverified`.

- `route_typed_planner_provider_attempts_through_compute_plane`

### `local_planner_provider_budget`

The effective provider num_ctx and num_predict own executable limits; UI budget estimates must mirror them.

Target status: `target_only_unverified`.

- `surface_effective_num_ctx_and_num_predict_in_operator_telemetry`
- `remove_hard_coded_48_token_continuation_limit`

### `mission_edit_reuse_lattice`

Lattice matches are advisory and never apply edits or convey approval.

Target status: `target_only_unverified`.

- `expose_lattice_matches_as_advice_only`

### `model_output_protocol`

Typed planner decisions and source-patch Action IR are different protocols; frontend instructions cannot bind both as one.

Target status: `target_only_unverified`.

- `remove_frontend_action_ir_from_typed_planner_objective`
- `preserve_output_governor_for_direct_source_patch_output`

### `planner_completion_decision`

Planner completion requires proof that the entire original objective is satisfied, including consumer.py in cross-file work.

Target status: `target_only_unverified`.

- `require_whole_objective_evidence_before_terminal_complete`
- `regress_unresolved_consumer_py_cross_file_case`

### `repository_context_selection`

Code Cortex discovers candidates; ContextPacket owns final evidence-bound handoff, including late files.

Target status: `target_only_unverified`.

- `feed_code_cortex_candidates_into_context_packet`
- `prove_cross_file_discovery_without_manual_three_file_attachment`

### `sensorium_agent_observation`

Sensorium must issue an independent receipt before mirror delivery is called observed.

Target status: `target_only_unverified`.

- `require_independent_sensorium_delivery_receipt`

### `sourceplan_handoff_and_approval`

SourcePlan approval is explicit; handoff preserves evidence and planner state alone is not mutation authority.

Target status: `target_only_unverified`.

- `enforce_explicit_sourceplan_approval_before_mutation`
- `bind_handoff_to_source_hash_and_capability`

### `task_input_governance`

TaskEnvelope owns mission constraints; frontend mode is operator intent, not a policy grant.

Target status: `target_only_unverified`.

- `canonicalize_renderer_intent_into_task_envelope`
- `reject_unauthorized_task_mode_escalation`

### `verification_gate`

Fresh worktree verification precedes post-apply evidence admission and whole-objective completion.

Target status: `target_only_unverified`.

- `bind_phase_d_verify_to_post_apply_evidence_gate`
- `block_completion_on_unresolved_original_objective`

### `verified_inference_reuse`

ReuseGateway decides verified inference reuse; cached content never grants action authority.

Target status: `target_only_unverified`.

- `require_current_source_and_policy_digests_before_reuse`
- `prohibit_reuse_from_granting_mutation_authority`

## Evidence boundary

Phase 1 defines target authority by scope. It does not change the Phase 0 census or establish live wiring. The Phase 0 cross-file completion defect remains open. Desktop ingress, real provider execution, and Sensorium delivery need distinct runtime receipts before promotion. Compressed source and crystal suggestions never grant mutation authority.
