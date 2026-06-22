# BEAST xAI Omni-Gauntlet

Generated: `2026-06-20T08:13:14Z`

This run evaluates Grok as one governed component inside BEAST. Provider-clean and BEAST-rescued outcomes are reported separately.

## Headline

- Full-BEAST completions: `24/24`
- Clean provider completions: `13`
- BEAST-rescued completions: `11`
- Hidden clean: `13/24`
- Raw baseline completions: `1/4`
- Local subsystem probe groups: `13/13`
- Fitness: `0.702`; role: `clean_candidate_cost_incomplete`
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
| live_xai_full_beast | 4 | 4 | 100.00% | 3585.5 | 34187.149 |
| live_xai_raw | 4 | 1 | 25.00% | 688.0 | 36799.822 |

## Matched Historical Comparison

| Run | Tasks | Completed | Clean | Avg Latency ms | Avg Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous xAI 10-task | 10 | 10 | 5 | 42938.59 | 3608.5 |
| Omni first 10 | 10 | 10 | 6 | 30882.196 | 3732.3 |

Observed average-latency change: `-28.08%`; token change: `3.43%`. Provider load may affect latency.

## Provider Outcome Classes

**Clean governed tasks:** `provider_id_parser`, `multi_file_hidden_decimal_fix`, `async_streaming_empty_chunk`, `provider_config_secret_redaction`, `output_governance_malformed_json`, `nim_refs_only_contract`, `stale_file_hash_rejection`, `session_latency_budget_clamp`, `tool_laziness_required_override`, `plugin_permission_risk_gate`, `otel_attribute_secret_redaction`, `mcp_tool_schema_pinning`, `vector_context_deduplication`.

**BEAST-rescued tasks:** `provider_model_wiring`, `config_validation_edge_case`, `ui_state_collapse_selection`, `patch_rollback_created_file`, `provider_economist_role_route`, `commons_local_approval_gate`, `network_probe_failure_classification`, `github_pr_task_envelope`, `quality_cascade_language_matrix`, `chronicle_provider_evidence_record`, `deployment_route_resolution`.

## Local System Probes

- **coding_and_hidden_tests**: PASS in `2076.948 ms` (3 test files).
- **input_governance**: PASS in `2041.668 ms` (5 test files).
- **output_governance**: PASS in `638.645 ms` (3 test files).
- **agent_awareness_preflight**: PASS in `1449.922 ms` (4 test files).
- **provider_economics_and_routing**: PASS in `1089.729 ms` (4 test files).
- **tool_bus_and_laziness**: PASS in `2977.484 ms` (5 test files).
- **commons_skills_and_promotion**: PASS in `1197.376 ms` (5 test files).
- **chronicle_memory_and_prec**: PASS in `1242.782 ms` (6 test files).
- **connectors_observability_and_network**: PASS in `481.752 ms` (3 test files).
- **marketplace_security_and_enterprise**: PASS in `586.101 ms` (5 test files).
- **quality_forge_and_packaging**: PASS in `2504.784 ms` (3 test files).
- **tui_and_operator_surface**: PASS in `1064.113 ms` (2 test files).
- **gateway_swarm_and_workflows**: PASS in `1375.861 ms` (4 test files).

## Interpretation

A live completion proves the BEAST system reached a verified fix. A clean completion additionally proves Grok's governed output passed without canonicalization, schema repair, or local verifier repair. Local probes test BEAST itself and are not credited to Grok.

Cost rankings remain excluded when xAI does not return first-party request cost observations.
