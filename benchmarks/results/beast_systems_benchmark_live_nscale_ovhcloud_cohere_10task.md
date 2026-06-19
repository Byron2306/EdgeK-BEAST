# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T06:17:18Z`

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
| nscale | 10 | 10 | 0 | 10 | 100.00% | None | None | None |
| ovhcloud | 10 | 10 | 0 | 10 | 100.00% | None | None | None |
| cohere | 10 | 10 | 4 | 6 | 100.00% | 5767.528 | 4140.2 | 4518.5 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nscale_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | None | None |
| live_ovhcloud_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | None | None |
| live_cohere_full_beast | 10 | 10 | 4 | 6 | 0 | 0 | 6 | 100.00% | 5767.528 | 4518.5 |

## Live Provider Results

- `nscale` / `provider_model_wiring` / `live_nscale_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `config_validation_edge_case` / `live_nscale_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `provider_id_parser` / `live_nscale_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `multi_file_hidden_decimal_fix` / `live_nscale_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `ui_state_collapse_selection` / `live_nscale_full_beast`: PASS; estimated_tokens=3115; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `async_streaming_empty_chunk` / `live_nscale_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `provider_config_secret_redaction` / `live_nscale_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `patch_rollback_created_file` / `live_nscale_full_beast`: PASS; estimated_tokens=3024; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `output_governance_malformed_json` / `live_nscale_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `nscale` / `nim_refs_only_contract` / `live_nscale_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://inference.api.nscale.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `ovhcloud` / `provider_model_wiring` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=4279; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `config_validation_edge_case` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `provider_id_parser` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3171; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `multi_file_hidden_decimal_fix` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `ui_state_collapse_selection` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `async_streaming_empty_chunk` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3066; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `provider_config_secret_redaction` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `patch_rollback_created_file` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `output_governance_malformed_json` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3042; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `ovhcloud` / `nim_refs_only_contract` / `live_ovhcloud_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '403 Forbidden' for url 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
- `cohere` / `provider_model_wiring` / `live_cohere_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=5655; latency_ms=11145.936; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `config_validation_edge_case` / `live_cohere_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=4076; latency_ms=6126.243; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=4074; latency_ms=4622.888; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `multi_file_hidden_decimal_fix` / `live_cohere_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=4119; latency_ms=5196.953; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `ui_state_collapse_selection` / `live_cohere_full_beast`: PASS; estimated_tokens=3115; provider_prompt_tokens=4015; latency_ms=5501.162; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `async_streaming_empty_chunk` / `live_cohere_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=3859; latency_ms=3921.387; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=3929; latency_ms=4858.974; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `patch_rollback_created_file` / `live_cohere_full_beast`: PASS; estimated_tokens=3024; provider_prompt_tokens=3846; latency_ms=5686.072; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `output_governance_malformed_json` / `live_cohere_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=3886; latency_ms=5834.362; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `nim_refs_only_contract` / `live_cohere_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=3943; latency_ms=4781.3; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cohere | 0.614 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| nscale | 0.2 | False | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ovhcloud | 0.2 | False | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 6
- `infra_failure`: 20
