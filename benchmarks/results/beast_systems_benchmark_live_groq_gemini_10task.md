# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T06:44:55Z`

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
| groq | 10 | 10 | 0 | 10 | 100.00% | 1202.829 | 3260.5 | 740.2 |
| gemini | 10 | 10 | 1 | 9 | 100.00% | 7611.807 | 3846.25 | 3217.3 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_groq_full_beast | 10 | 10 | 0 | 10 | 0 | 1 | 10 | 100.00% | 1202.829 | 740.2 |
| live_gemini_full_beast | 10 | 10 | 1 | 9 | 0 | 5 | 9 | 100.00% | 7611.807 | 3217.3 |

## Live Provider Results

- `groq` / `provider_model_wiring` / `live_groq_full_beast`: PASS; estimated_tokens=4276; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '413 Payload Too Large' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/413
- `groq` / `config_validation_edge_case` / `live_groq_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=3327; latency_ms=1604.188; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `provider_id_parser` / `live_groq_full_beast`: PASS; estimated_tokens=3168; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `multi_file_hidden_decimal_fix` / `live_groq_full_beast`: PASS; estimated_tokens=3189; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `ui_state_collapse_selection` / `live_groq_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `async_streaming_empty_chunk` / `live_groq_full_beast`: PASS; estimated_tokens=3063; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `provider_config_secret_redaction` / `live_groq_full_beast`: PASS; estimated_tokens=3052; provider_prompt_tokens=3194; latency_ms=801.469; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `groq` / `patch_rollback_created_file` / `live_groq_full_beast`: PASS; estimated_tokens=3023; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `output_governance_malformed_json` / `live_groq_full_beast`: PASS; estimated_tokens=3039; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `nim_refs_only_contract` / `live_groq_full_beast`: PASS; estimated_tokens=3054; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `gemini` / `provider_model_wiring` / `live_gemini_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Server error '503 Service Unavailable' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503
- `gemini` / `config_validation_edge_case` / `live_gemini_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=4131; latency_ms=8332.976; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `gemini` / `provider_id_parser` / `live_gemini_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=2452; latency_ms=7094.203; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `gemini` / `multi_file_hidden_decimal_fix` / `live_gemini_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=4201; latency_ms=8639.587; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `gemini` / `ui_state_collapse_selection` / `live_gemini_full_beast`: PASS; estimated_tokens=3115; provider_prompt_tokens=4059; latency_ms=6301.528; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `gemini` / `async_streaming_empty_chunk` / `live_gemini_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=3965; latency_ms=5435.765; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `gemini` / `provider_config_secret_redaction` / `live_gemini_full_beast`: PASS; estimated_tokens=3053; provider_prompt_tokens=3992; latency_ms=8256.298; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `gemini` / `patch_rollback_created_file` / `live_gemini_full_beast`: PASS; estimated_tokens=3024; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Server error '503 Service Unavailable' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503
- `gemini` / `output_governance_malformed_json` / `live_gemini_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=3960; latency_ms=9571.731; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `gemini` / `nim_refs_only_contract` / `live_gemini_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=4010; latency_ms=7262.371; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini | 0.333 | False | 0.4 | 0.4 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| groq | 0.23 | False | 0.2 | 0.1 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 9
- `infra_failure`: 10
