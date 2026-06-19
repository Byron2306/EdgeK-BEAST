# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T17:53:41Z`

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
| xai | 10 | 10 | 5 | 5 | 5/10 (50.00%) | 5/10 (50.00%) | 10/10 | None | 50.00% | 1.0 | 0.00% | 100.00% | 42938.59 | 3608.5 | None | clean_candidate_cost_incomplete | medium_cost_incomplete |
| replicate | 10 | 10 | 0 | 10 | 0/10 (0.00%) | 0/10 (0.00%) | 10/10 | None | 100.00% | 0.0 | 0.00% | 100.00% | None | None | None | route_degraded_exclude_cost_rank | degraded |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_xai_full_beast | 10 | 10 | 5 | 5 | 0 | 1 | 5 | 100.00% | 42938.59 | 3608.5 |
| live_replicate_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | None | None |

## Live Provider Results

- `xai` / `provider_model_wiring` / `live_xai_full_beast`: PASS; estimated_tokens=4275; provider_prompt_tokens=4639; latency_ms=14473.045; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `config_validation_edge_case` / `live_xai_full_beast`: PASS; estimated_tokens=3189; provider_prompt_tokens=3377; latency_ms=66544.449; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `provider_id_parser` / `live_xai_full_beast`: PASS; estimated_tokens=3167; provider_prompt_tokens=3344; latency_ms=40233.586; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `multi_file_hidden_decimal_fix` / `live_xai_full_beast`: PASS; estimated_tokens=3188; provider_prompt_tokens=3377; latency_ms=57255.458; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `ui_state_collapse_selection` / `live_xai_full_beast`: PASS; estimated_tokens=3113; provider_prompt_tokens=2265; latency_ms=30272.55; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `async_streaming_empty_chunk` / `live_xai_full_beast`: PASS; estimated_tokens=3062; provider_prompt_tokens=3204; latency_ms=23386.983; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `provider_config_secret_redaction` / `live_xai_full_beast`: PASS; estimated_tokens=3051; provider_prompt_tokens=3211; latency_ms=34676.235; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `patch_rollback_created_file` / `live_xai_full_beast`: PASS; estimated_tokens=3022; provider_prompt_tokens=3206; latency_ms=70012.129; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `output_governance_malformed_json` / `live_xai_full_beast`: PASS; estimated_tokens=3038; provider_prompt_tokens=3228; latency_ms=39931.699; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `xai` / `nim_refs_only_contract` / `live_xai_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=3209; latency_ms=52599.768; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `replicate` / `provider_model_wiring` / `live_replicate_full_beast`: PASS; estimated_tokens=4280; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `config_validation_edge_case` / `live_replicate_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `provider_id_parser` / `live_replicate_full_beast`: PASS; estimated_tokens=3172; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `multi_file_hidden_decimal_fix` / `live_replicate_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `ui_state_collapse_selection` / `live_replicate_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `async_streaming_empty_chunk` / `live_replicate_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `provider_config_secret_redaction` / `live_replicate_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `patch_rollback_created_file` / `live_replicate_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `output_governance_malformed_json` / `live_replicate_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
- `replicate` / `nim_refs_only_contract` / `live_replicate_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '404 Not Found' for url 'https://api.replicate.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| replicate | 0.2 | False | route_degraded_exclude_cost_rank | degraded | None | 1.0 | 0.0 | 0.0 | 0/10 (0.0) | 0/10 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| xai | 0.6757 | False | clean_candidate_cost_incomplete | medium_cost_incomplete | None | 0.5 | 1.0 | 0.0 | 5/10 (0.5) | 5/10 (0.5) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 5
- `infra_failure`: 10
