# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-20T21:41:27Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw | 0 | 0 | 0.00% | 0 | 0.00% |
| context_only | 0 | 0 | 0.00% | 0 | 0.00% |
| rag | 0 | 0 | 0.00% | 0 | 0.00% |
| rag_tools | 0 | 0 | 0.00% | 0 | 0.00% |
| full_beast | 0 | 0 | 0.00% | 0 | 0.00% |

## Subsystem Probes


## Verified Task Results


## Live Provider Summary

| Provider | Tasks | Completed | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Coverage | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Completion Rate | Avg Latency ms | Tokens/Fix | First-party USD/Fix | Recommended Role | Route Confidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| nvidia_nim | 28 | 24 | 0 | 24 | 0/28 (0.00%) | 0/28 (0.00%) | 28/28 | None | 100.00% | 0.0 | 0.00% | 85.71% | 40746.984 | 5537.917 | None | refs_only_transform_selector | medium |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_full_beast | 24 | 24 | 0 | 24 | 1 | 19 | 23 | 100.00% | 43567.817 | 5537.917 |
| live_nvidia_nim_raw | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 23821.99 | None |

## Live Provider Results

- `nvidia_nim` / `provider_model_wiring` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=5094; provider_prompt_tokens=8091; latency_ms=99076.083; canonicalized=True; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `config_validation_edge_case` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3541; provider_prompt_tokens=5057; latency_ms=49332.031; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3422; provider_prompt_tokens=4752; latency_ms=69650.675; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `multi_file_hidden_decimal_fix` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3326; provider_prompt_tokens=4486; latency_ms=26476.037; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `ui_state_collapse_selection` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3385; provider_prompt_tokens=4770; latency_ms=48308.301; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `async_streaming_empty_chunk` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3251; provider_prompt_tokens=2552; latency_ms=100405.111; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3127; provider_prompt_tokens=4092; latency_ms=41489.356; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `patch_rollback_created_file` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3122; provider_prompt_tokens=4131; latency_ms=91754.464; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=3978; latency_ms=26395.087; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `nim_refs_only_contract` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3107; provider_prompt_tokens=4000; latency_ms=22195.933; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `stale_file_hash_rejection` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3149; provider_prompt_tokens=2554; latency_ms=28934.122; canonicalized=False; repair_attempted=True; local_verifier_repair=False; changed=['app/hash_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `session_latency_budget_clamp` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3102; provider_prompt_tokens=4077; latency_ms=33337.197; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/session_budget.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_economist_role_route` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3130; provider_prompt_tokens=4027; latency_ms=17231.776; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/route_economist.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `tool_laziness_required_override` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=4021; latency_ms=15110.498; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tool_laziness_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `commons_local_approval_gate` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3125; provider_prompt_tokens=3997; latency_ms=45069.318; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/commons_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `plugin_permission_risk_gate` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3144; provider_prompt_tokens=2414; latency_ms=43514.757; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/plugin_gate.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `otel_attribute_secret_redaction` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3132; provider_prompt_tokens=4028; latency_ms=31582.973; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/otel_redactor.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `network_probe_failure_classification` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3130; provider_prompt_tokens=4016; latency_ms=14127.847; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/network_probe.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `github_pr_task_envelope` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3142; provider_prompt_tokens=4113; latency_ms=73918.919; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/pr_envelope.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `quality_cascade_language_matrix` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3130; provider_prompt_tokens=4036; latency_ms=51213.368; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/quality_matrix.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `mcp_tool_schema_pinning` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3207; provider_prompt_tokens=4311; latency_ms=28377.671; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/mcp_schema.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `chronicle_provider_evidence_record` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3182; provider_prompt_tokens=4058; latency_ms=27648.602; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/chronicle_record.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `deployment_route_resolution` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3140; provider_prompt_tokens=3933; latency_ms=33511.682; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/deployment_route.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `vector_context_deduplication` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3162; provider_prompt_tokens=4011; latency_ms=26965.796; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/vector_context.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `multi_file_hidden_decimal_fix` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=397; latency_ms=28887.278; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `ui_state_collapse_selection` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=330; provider_prompt_tokens=420; latency_ms=28171.683; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=15436.065; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `nvidia_nim` / `commons_local_approval_gate` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=301; provider_prompt_tokens=394; latency_ms=22792.933; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/commons_gate.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nvidia_nim | 0.3071 | False | refs_only_transform_selector | medium | None | 1.0 | 0.0 | 0.0 | 0/28 (0.0) | 0/28 (0.0) | 0.4286 | 0.3571 | 0.3571 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `nim_success`: 16
- `nim_tests_failed`: 12
