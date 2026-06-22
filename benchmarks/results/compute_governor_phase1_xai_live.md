# Compute Governor Phase 1 xAI Live Observation

- Model: `grok-build-0.1`
- Tasks/classes: `24/24`
- Verified tasks: `24/24` (`100.0%`)
- Actual provider calls: `25`
- Compute receipts: `25`
- Receipt coverage: `100.0%`
- Observed tokens: `232081`
- Observed first-party cost lower bound: `$0.3589802` across the 24 retained final responses
- Cost note: one discarded pre-repair response makes the true 25-call total slightly higher
- Candidate avoidable tokens: `33017` (counterfactual)
- Predicted savings USD: `0.052213896` (counterfactual)
- Cost coverage: `100.0%`
- Enforced suppressions: `0`
- False suppression rate: `0.0%`
- Live observation: `PASS`

## Tasks

| Task | Class | Verified | Latency ms | Tokens |
| --- | --- | --- | ---: | ---: |
| `provider_model_wiring` | `provider_routing` | PASS | 6902.997 | 5298 |
| `config_validation_edge_case` | `config_governance` | PASS | 49845.458 | 3732 |
| `provider_id_parser` | `parsing` | PASS | 33768.579 | 3545 |
| `multi_file_hidden_decimal_fix` | `multi_file_hidden` | PASS | 41081.101 | 3723 |
| `ui_state_collapse_selection` | `tui_state` | PASS | 46320.102 | 3474 |
| `async_streaming_empty_chunk` | `async_streaming` | PASS | 19769.787 | 3435 |
| `provider_config_secret_redaction` | `secret_redaction` | PASS | 39470.063 | 3467 |
| `patch_rollback_created_file` | `rollback` | PASS | 50901.122 | 3396 |
| `output_governance_malformed_json` | `output_governance` | PASS | 55359.329 | 3496 |
| `nim_refs_only_contract` | `refs_only_action_ir` | PASS | 31889.963 | 3459 |
| `stale_file_hash_rejection` | `stale_file_hash_rejection` | PASS | 33902.346 | 3401 |
| `session_latency_budget_clamp` | `session_latency_budget_clamp` | PASS | 29877.344 | 3540 |
| `provider_economist_role_route` | `provider_economist_role_route` | PASS | 38272.069 | 3543 |
| `tool_laziness_required_override` | `tool_laziness_required_override` | PASS | 17032.377 | 3440 |
| `commons_local_approval_gate` | `commons_local_approval_gate` | PASS | 22835.982 | 3528 |
| `plugin_permission_risk_gate` | `plugin_permission_risk_gate` | PASS | 52940.327 | 2822 |
| `otel_attribute_secret_redaction` | `otel_attribute_secret_redaction` | PASS | 27736.371 | 3541 |
| `network_probe_failure_classification` | `network_probe_failure_classification` | PASS | 29768.423 | 3559 |
| `github_pr_task_envelope` | `github_pr_task_envelope` | PASS | 33453.884 | 3607 |
| `quality_cascade_language_matrix` | `quality_cascade_language_matrix` | PASS | 34699.71 | 3663 |
| `mcp_tool_schema_pinning` | `mcp_tool_schema_pinning` | PASS | 18029.552 | 3607 |
| `chronicle_provider_evidence_record` | `chronicle_provider_evidence_record` | PASS | 36191.943 | 3571 |
| `deployment_route_resolution` | `deployment_route_resolution` | PASS | 35163.159 | 3454 |
| `vector_context_deduplication` | `vector_context_deduplication` | PASS | 27869.057 | 3653 |

## Claim Boundary

This live run proves shadow receipt coverage and observed behavior on xAI. Avoidable-token and USD values remain counterfactual; no provider call was suppressed or displaced.
