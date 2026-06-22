# BEAST Nvidia Nim Omni-Gauntlet

Generated: `2026-06-20T21:41:27Z`

This run evaluates Nvidia Nim as one governed component inside BEAST. Provider-clean and BEAST-rescued outcomes are reported separately.

## Headline

- Full-BEAST completions: `24/24`
- Clean provider completions: `0`
- BEAST-rescued completions: `24`
- Hidden clean: `0/24`
- Raw baseline completions: `0/4`
- Local subsystem probe groups: `13/13`
- Fitness: `0.3`; role: `refs_only_transform_selector`
- Evidence coverage: `13/13`

## Layer Coverage

| Layer | Live Tasks | Local Probe | Status |
| --- | ---: | --- | --- |
| input_governance | 3 | PASS | covered |
| output_governance | 3 | PASS | covered |
| coding_and_hidden_tests | 3 | PASS | covered |
| agent_awareness_preflight | 1 | PASS | covered |
| provider_economics_and_routing | 3 | PASS | covered |
| tool_bus_and_laziness | 2 | PASS | covered |
| commons_skills_and_promotion | 1 | PASS | covered |
| chronicle_memory_and_prec | 1 | PASS | covered |
| connectors_observability_and_network | 3 | PASS | covered |
| marketplace_security_and_enterprise | 2 | PASS | covered |
| quality_forge_and_packaging | 1 | PASS | covered |
| tui_and_operator_surface | 1 | PASS | covered |
| gateway_swarm_and_workflows | 1 | PASS | covered |

## Ablation

| Lane | Tasks | Completed | Completion | Avg Tokens | Avg Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_full_beast | 4 | 4 | 100.00% | 5697.5 | 36562.186 |
| live_nvidia_nim_raw | 4 | 0 | 0.00% | 1600.5 | 23821.99 |

## Matched Historical Comparison

| Run | Tasks | Completed | Clean | Avg Latency ms | Avg Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous xAI 10-task | 10 | 10 | 5 | 42938.59 | 3608.5 |
| Omni first 10 | 10 | 10 | 0 | 57508.308 | 5978.9 |

Observed average-latency change: `33.93%`; token change: `65.69%`. Provider load may affect latency.

## Provider Outcome Classes

**Clean governed tasks:** .

**BEAST-rescued tasks:** `provider_model_wiring`, `config_validation_edge_case`, `provider_id_parser`, `multi_file_hidden_decimal_fix`, `ui_state_collapse_selection`, `async_streaming_empty_chunk`, `provider_config_secret_redaction`, `patch_rollback_created_file`, `output_governance_malformed_json`, `nim_refs_only_contract`, `stale_file_hash_rejection`, `session_latency_budget_clamp`, `provider_economist_role_route`, `tool_laziness_required_override`, `commons_local_approval_gate`, `plugin_permission_risk_gate`, `otel_attribute_secret_redaction`, `network_probe_failure_classification`, `github_pr_task_envelope`, `quality_cascade_language_matrix`, `mcp_tool_schema_pinning`, `chronicle_provider_evidence_record`, `deployment_route_resolution`, `vector_context_deduplication`.

## Local System Probes

- **coding_and_hidden_tests**: PASS in `3753.579 ms` (3 test files).
- **input_governance**: PASS in `2434.71 ms` (5 test files).
- **output_governance**: PASS in `1035.964 ms` (3 test files).
- **agent_awareness_preflight**: PASS in `2506.267 ms` (4 test files).
- **provider_economics_and_routing**: PASS in `1509.089 ms` (4 test files).
- **tool_bus_and_laziness**: PASS in `4130.867 ms` (5 test files).
- **commons_skills_and_promotion**: PASS in `1524.405 ms` (5 test files).
- **chronicle_memory_and_prec**: PASS in `2588.363 ms` (6 test files).
- **connectors_observability_and_network**: PASS in `1356.642 ms` (3 test files).
- **marketplace_security_and_enterprise**: PASS in `1819.396 ms` (5 test files).
- **quality_forge_and_packaging**: PASS in `5112.853 ms` (3 test files).
- **tui_and_operator_surface**: PASS in `2786.889 ms` (2 test files).
- **gateway_swarm_and_workflows**: PASS in `3136.063 ms` (4 test files).

## Interpretation

A live completion proves the BEAST system reached a verified fix. A clean completion additionally proves Nvidia Nim's governed output passed without canonicalization, schema repair, or local verifier repair. Local probes test BEAST itself and are not credited to the provider.

Cost rankings remain excluded when the provider does not return first-party request cost observations.
