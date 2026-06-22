# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-20T08:13:14Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| context_only | 0 | 0 | 0.00% | 0 | 0.00% |
| full_beast | 0 | 0 | 0.00% | 0 | 0.00% |
| rag | 0 | 0 | 0.00% | 0 | 0.00% |
| rag_tools | 0 | 0 | 0.00% | 0 | 0.00% |
| raw | 0 | 0 | 0.00% | 0 | 0.00% |

## Subsystem Probes


## Verified Task Results


## Live Provider Summary

| Provider | Tasks | Completed | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Coverage | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Completion Rate | Avg Latency ms | Tokens/Fix | First-party USD/Fix | Recommended Role | Route Confidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| xai | 28 | 25 | 14 | 11 | 14/28 (50.00%) | 14/28 (50.00%) | 28/28 | None | 44.00% | 1.2727 | 0.00% | 89.29% | 33072.563 | 3512.68 | None | clean_candidate_cost_incomplete | medium |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_xai_full_beast | 24 | 24 | 13 | 11 | 0 | 0 | 11 | 100.00% | 32451.353 | 3627.0 |
| live_xai_raw | 4 | 1 | 1 | 0 | 0 | 0 | 0 | 25.00% | 36799.822 | 769.0 |

## Live Provider Results

- `xai` / `provider_model_wiring` / `live_xai_full_beast`: PASS; estimated_tokens=4259; provider_prompt_tokens=4628; latency_ms=8815.276; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `config_validation_edge_case` / `live_xai_full_beast`: PASS; estimated_tokens=3182; provider_prompt_tokens=3374; latency_ms=36403.829; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `provider_id_parser` / `live_xai_full_beast`: PASS; estimated_tokens=3160; provider_prompt_tokens=3335; latency_ms=35245.34; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `multi_file_hidden_decimal_fix` / `live_xai_full_beast`: PASS; estimated_tokens=3183; provider_prompt_tokens=3375; latency_ms=40498.607; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py', 'app/service.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `ui_state_collapse_selection` / `live_xai_full_beast`: PASS; estimated_tokens=3097; provider_prompt_tokens=3278; latency_ms=26602.989; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `async_streaming_empty_chunk` / `live_xai_full_beast`: PASS; estimated_tokens=3062; provider_prompt_tokens=3214; latency_ms=34387.95; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `provider_config_secret_redaction` / `live_xai_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=3209; latency_ms=25622.539; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `patch_rollback_created_file` / `live_xai_full_beast`: PASS; estimated_tokens=3014; provider_prompt_tokens=3201; latency_ms=39337.094; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `output_governance_malformed_json` / `live_xai_full_beast`: PASS; estimated_tokens=3022; provider_prompt_tokens=3222; latency_ms=37844.775; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `nim_refs_only_contract` / `live_xai_full_beast`: PASS; estimated_tokens=3037; provider_prompt_tokens=3195; latency_ms=24063.566; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `stale_file_hash_rejection` / `live_xai_full_beast`: PASS; estimated_tokens=3059; provider_prompt_tokens=3211; latency_ms=33921.914; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/hash_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `session_latency_budget_clamp` / `live_xai_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3260; latency_ms=22168.327; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/session_budget.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `provider_economist_role_route` / `live_xai_full_beast`: PASS; estimated_tokens=3082; provider_prompt_tokens=3247; latency_ms=31749.84; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/route_economist.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `tool_laziness_required_override` / `live_xai_full_beast`: PASS; estimated_tokens=3048; provider_prompt_tokens=3206; latency_ms=27739.196; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/tool_laziness_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `commons_local_approval_gate` / `live_xai_full_beast`: PASS; estimated_tokens=3065; provider_prompt_tokens=3270; latency_ms=31802.226; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/commons_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `plugin_permission_risk_gate` / `live_xai_full_beast`: PASS; estimated_tokens=3087; provider_prompt_tokens=3257; latency_ms=39510.412; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/plugin_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `otel_attribute_secret_redaction` / `live_xai_full_beast`: PASS; estimated_tokens=3066; provider_prompt_tokens=3263; latency_ms=26603.296; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/otel_redactor.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `network_probe_failure_classification` / `live_xai_full_beast`: PASS; estimated_tokens=3073; provider_prompt_tokens=3243; latency_ms=24167.692; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/network_probe.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `github_pr_task_envelope` / `live_xai_full_beast`: PASS; estimated_tokens=3085; provider_prompt_tokens=3306; latency_ms=27892.294; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/pr_envelope.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `quality_cascade_language_matrix` / `live_xai_full_beast`: PASS; estimated_tokens=3073; provider_prompt_tokens=3293; latency_ms=45457.927; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/quality_matrix.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `mcp_tool_schema_pinning` / `live_xai_full_beast`: PASS; estimated_tokens=3070; provider_prompt_tokens=3275; latency_ms=27502.757; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/mcp_schema.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `chronicle_provider_evidence_record` / `live_xai_full_beast`: PASS; estimated_tokens=3125; provider_prompt_tokens=3292; latency_ms=38645.7; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/chronicle_record.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `deployment_route_resolution` / `live_xai_full_beast`: PASS; estimated_tokens=3075; provider_prompt_tokens=3203; latency_ms=47989.244; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/deployment_route.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `vector_context_deduplication` / `live_xai_full_beast`: PASS; estimated_tokens=3104; provider_prompt_tokens=3303; latency_ms=44859.676; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/vector_context.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `multi_file_hidden_decimal_fix` / `live_xai_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=483; latency_ms=46620.719; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py', 'app/service.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `ui_state_collapse_selection` / `live_xai_raw`: PASS; estimated_tokens=330; provider_prompt_tokens=512; latency_ms=31855.427; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `output_governance_malformed_json` / `live_xai_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=440; latency_ms=46976.083; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `commons_local_approval_gate` / `live_xai_raw`: FAIL; estimated_tokens=301; provider_prompt_tokens=473; latency_ms=21747.058; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/commons_gate.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| xai | 0.6841 | False | clean_candidate_cost_incomplete | medium | None | 0.44 | 1.2727 | 0.0 | 14/28 (0.5) | 14/28 (0.5) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 14
