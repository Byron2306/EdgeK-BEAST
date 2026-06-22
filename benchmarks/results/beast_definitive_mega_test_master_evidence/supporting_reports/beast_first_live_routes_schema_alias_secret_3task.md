# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:08:08Z`

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
| nvidia_nim | 6 | 4 | 1 | 3 | 1/6 (16.67%) | 1/6 (16.67%) | 6/6 | None | 75.00% | 0.3333 | 0.00% | 66.67% | 30923.037 | 4235.0 | None | nim_clean_candidate | low |
| mistral | 6 | 3 | 1 | 2 | 1/6 (16.67%) | 1/6 (16.67%) | 6/6 | None | 66.67% | 0.5 | 0.00% | 50.00% | 2223.972 | 4194.667 | None | clean_candidate_cost_incomplete | low |
| gemini | 6 | 3 | 0 | 3 | 0/6 (0.00%) | 0/6 (0.00%) | 6/6 | None | 100.00% | 0.0 | 0.00% | 50.00% | 5313.102 | 1311.333 | None | route_degraded_exclude_cost_rank | degraded |
| cohere | 6 | 4 | 3 | 1 | 3/6 (50.00%) | 3/6 (50.00%) | 6/6 | None | 25.00% | 3.0 | 0.00% | 66.67% | 4714.603 | 3388.0 | None | clean_candidate_cost_incomplete | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_raw | 3 | 1 | 1 | 0 | 0 | 0 | 0 | 33.33% | 34241.978 | 1411.0 |
| live_nvidia_nim_full_beast | 3 | 3 | 0 | 3 | 0 | 3 | 3 | 100.00% | 27604.096 | 5176.333 |
| live_mistral_raw | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 2174.576 | None |
| live_mistral_full_beast | 3 | 3 | 1 | 2 | 0 | 0 | 2 | 100.00% | 2273.367 | 4194.667 |
| live_gemini_raw | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 5052.318 | None |
| live_gemini_full_beast | 3 | 3 | 0 | 3 | 0 | 1 | 3 | 100.00% | 5573.887 | 1311.333 |
| live_cohere_raw | 3 | 1 | 1 | 0 | 0 | 0 | 0 | 33.33% | 3902.845 | 691.0 |
| live_cohere_full_beast | 3 | 3 | 2 | 1 | 0 | 0 | 1 | 100.00% | 5526.361 | 4287.0 |

## Live Provider Results

- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=14542.227; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=3978; latency_ms=19970.784; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_raw`: PASS; estimated_tokens=409; provider_prompt_tokens=511; latency_ms=34929.077; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3421; provider_prompt_tokens=4756; latency_ms=49517.795; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=384; latency_ms=53254.629; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3126; provider_prompt_tokens=4095; latency_ms=13323.708; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `mistral` / `output_governance_malformed_json` / `live_mistral_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=336; latency_ms=2092.699; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3725; latency_ms=2042.406; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_id_parser` / `live_mistral_raw`: FAIL; estimated_tokens=409; provider_prompt_tokens=500; latency_ms=2620.409; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].old matched 0 times in app/provider_parser.py
- `mistral` / `provider_id_parser` / `live_mistral_full_beast`: PASS; estimated_tokens=3160; provider_prompt_tokens=3988; latency_ms=1920.449; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=373; latency_ms=1810.621; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3842; latency_ms=2857.247; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `gemini` / `output_governance_malformed_json` / `live_gemini_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=363; latency_ms=5052.318; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `gemini` / `output_governance_malformed_json` / `live_gemini_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3899; latency_ms=5573.887; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `gemini` / `provider_id_parser` / `live_gemini_raw`: FAIL; estimated_tokens=409; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Client error '429 Too Many Requests' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `gemini` / `provider_id_parser` / `live_gemini_full_beast`: PASS; estimated_tokens=3159; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `gemini` / `provider_config_secret_redaction` / `live_gemini_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Client error '429 Too Many Requests' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `gemini` / `provider_config_secret_redaction` / `live_gemini_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `cohere` / `output_governance_malformed_json` / `live_cohere_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=354; latency_ms=3242.7; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `output_governance_malformed_json` / `live_cohere_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3823; latency_ms=6132.19; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_raw`: PASS; estimated_tokens=409; provider_prompt_tokens=521; latency_ms=4729.814; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_full_beast`: PASS; estimated_tokens=3159; provider_prompt_tokens=4073; latency_ms=5582.793; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=396; latency_ms=3736.02; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=3925; latency_ms=4864.1; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cohere | 0.7579 | True | clean_candidate_cost_incomplete | low | None | 0.25 | 3.0 | 0.0 | 3/6 (0.5) | 3/6 (0.5) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| gemini | 0.25 | False | route_degraded_exclude_cost_rank | degraded | None | 1.0 | 0.0 | 0.0 | 0/6 (0.0) | 0/6 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| mistral | 0.555 | True | clean_candidate_cost_incomplete | low | None | 0.6667 | 0.5 | 0.0 | 1/6 (0.1667) | 1/6 (0.1667) | 1.0 | 0.8333 | 0.8333 | 0.0 | 0.0 | 0.0 | 1.0 |
| nvidia_nim | 0.34 | False | nim_clean_candidate | low | None | 0.75 | 0.3333 | 0.0 | 1/6 (0.1667) | 1/6 (0.1667) | 0.1667 | 0.1667 | 0.1667 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 10
- `infra_failure`: 4
- `nim_success`: 3
- `nim_tests_failed`: 2
