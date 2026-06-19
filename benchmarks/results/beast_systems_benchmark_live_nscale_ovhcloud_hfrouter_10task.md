# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T06:26:00Z`

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

| Provider | Tasks | Completed | Clean | Rescued | Completion Rate | Avg Latency ms | Avg Prompt Tokens | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nscale | 10 | 10 | 3 | 7 | 100.00% | 9574.702 | 3193.3 | 4343.5 |
| ovhcloud | 10 | 10 | 5 | 5 | 100.00% | 12919.027 | 3463.3 | 4562.6 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nscale_full_beast | 10 | 10 | 3 | 7 | 0 | 2 | 7 | 100.00% | 9574.702 | 4343.5 |
| live_ovhcloud_full_beast | 10 | 10 | 5 | 5 | 0 | 0 | 5 | 100.00% | 12919.027 | 4562.6 |

## Live Provider Results

- `nscale` / `provider_model_wiring` / `live_nscale_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=4750; latency_ms=11779.821; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `config_validation_edge_case` / `live_nscale_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=1981; latency_ms=6849.001; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `provider_id_parser` / `live_nscale_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=3400; latency_ms=9317.733; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `multi_file_hidden_decimal_fix` / `live_nscale_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=2228; latency_ms=11980.096; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `ui_state_collapse_selection` / `live_nscale_full_beast`: PASS; estimated_tokens=3115; provider_prompt_tokens=3349; latency_ms=11323.621; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `async_streaming_empty_chunk` / `live_nscale_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=3281; latency_ms=8397.322; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `provider_config_secret_redaction` / `live_nscale_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=3235; latency_ms=5786.155; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `patch_rollback_created_file` / `live_nscale_full_beast`: PASS; estimated_tokens=3024; provider_prompt_tokens=3224; latency_ms=11089.493; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `output_governance_malformed_json` / `live_nscale_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=3204; latency_ms=10228.416; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `nscale` / `nim_refs_only_contract` / `live_nscale_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=3281; latency_ms=8995.365; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `provider_model_wiring` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=4279; provider_prompt_tokens=4760; latency_ms=19211.534; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `config_validation_edge_case` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=3419; latency_ms=17492.741; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `provider_id_parser` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3171; provider_prompt_tokens=3412; latency_ms=7890.075; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `multi_file_hidden_decimal_fix` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=3447; latency_ms=17201.58; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `ui_state_collapse_selection` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=3358; latency_ms=16759.212; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `async_streaming_empty_chunk` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3066; provider_prompt_tokens=3273; latency_ms=9809.355; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `provider_config_secret_redaction` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=3233; latency_ms=6403.934; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `patch_rollback_created_file` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=3237; latency_ms=11450.273; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `output_governance_malformed_json` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3042; provider_prompt_tokens=3227; latency_ms=13153.451; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `ovhcloud` / `nim_refs_only_contract` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=3267; latency_ms=9818.115; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nscale | 0.581 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ovhcloud | 0.6632 | False | 1.0 | 1.0 | 1.0 | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 12
