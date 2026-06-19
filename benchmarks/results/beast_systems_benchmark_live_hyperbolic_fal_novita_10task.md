# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T06:00:11Z`

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

| Provider | Tasks | Completed | Clean | Rescued | Completion Rate | Avg Latency ms | Avg Prompt Tokens | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fal | 10 | 10 | 0 | 10 | 100.00% | None | None | None |
| hyperbolic | 10 | 10 | 0 | 10 | 100.00% | None | None | None |
| novita | 10 | 10 | 1 | 9 | 100.00% | 2638.168 | 3266.8 | 3533.0 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_fal_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | None | None |
| live_hyperbolic_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | None | None |
| live_novita_full_beast | 10 | 10 | 1 | 9 | 0 | 1 | 9 | 100.00% | 2638.168 | 3533.0 |

## Live Provider Results

- `hyperbolic` / `provider_model_wiring` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `config_validation_edge_case` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `provider_id_parser` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `multi_file_hidden_decimal_fix` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `ui_state_collapse_selection` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3118; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `async_streaming_empty_chunk` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `provider_config_secret_redaction` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `patch_rollback_created_file` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3027; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `output_governance_malformed_json` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `hyperbolic` / `nim_refs_only_contract` / `live_hyperbolic_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://api.hyperbolic.xyz/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `fal` / `provider_model_wiring` / `live_fal_full_beast`: PASS; estimated_tokens=4275; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `config_validation_edge_case` / `live_fal_full_beast`: PASS; estimated_tokens=3189; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `provider_id_parser` / `live_fal_full_beast`: PASS; estimated_tokens=3167; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `multi_file_hidden_decimal_fix` / `live_fal_full_beast`: PASS; estimated_tokens=3188; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `ui_state_collapse_selection` / `live_fal_full_beast`: PASS; estimated_tokens=3113; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `async_streaming_empty_chunk` / `live_fal_full_beast`: PASS; estimated_tokens=3062; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `provider_config_secret_redaction` / `live_fal_full_beast`: PASS; estimated_tokens=3051; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `patch_rollback_created_file` / `live_fal_full_beast`: PASS; estimated_tokens=3022; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `output_governance_malformed_json` / `live_fal_full_beast`: PASS; estimated_tokens=3038; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `fal` / `nim_refs_only_contract` / `live_fal_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '401 Unauthorized' for url 'https://fal.run/openrouter/router/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `novita` / `provider_model_wiring` / `live_novita_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=4687; latency_ms=4313.806; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `config_validation_edge_case` / `live_novita_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=3298; latency_ms=3924.885; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `provider_id_parser` / `live_novita_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=3331; latency_ms=4431.428; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `multi_file_hidden_decimal_fix` / `live_novita_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=3350; latency_ms=2042.755; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `ui_state_collapse_selection` / `live_novita_full_beast`: PASS; estimated_tokens=3115; provider_prompt_tokens=3223; latency_ms=2125.392; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `async_streaming_empty_chunk` / `live_novita_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=3151; latency_ms=2622.095; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `provider_config_secret_redaction` / `live_novita_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=3147; latency_ms=1953.626; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `patch_rollback_created_file` / `live_novita_full_beast`: PASS; estimated_tokens=3024; provider_prompt_tokens=3145; latency_ms=1653.6; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `output_governance_malformed_json` / `live_novita_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=2161; latency_ms=1414.296; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `novita` / `nim_refs_only_contract` / `live_novita_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=3175; latency_ms=1899.794; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fal | 0.2 | False | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| hyperbolic | 0.2 | False | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| novita | 0.5098 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 9
- `infra_failure`: 20
