# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T08:00:59Z`

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
| sambanova | 10 | 10 | 1 | 9 | 100.00% | 2413.071 | 3369.3 | 3587.8 |
| mistral | 10 | 10 | 2 | 8 | 100.00% | 2987.653 | 4081.0 | 4486.7 |
| cloudflare | 10 | 10 | 1 | 9 | 100.00% | 1497.06 | 3360.0 | 3590.0 |
| llm7 | 10 | 10 | 0 | 10 | 100.00% | 2969.59 | None | None |
| aion_labs | 10 | 10 | 1 | 9 | 100.00% | 3825.734 | 3545.667 | 2261.6 |
| puter_deepseek | 10 | 10 | 4 | 6 | 100.00% | 12018.808 | 0.0 | 0.0 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_sambanova_full_beast | 10 | 10 | 1 | 9 | 0 | 0 | 9 | 100.00% | 2413.071 | 3587.8 |
| live_mistral_full_beast | 10 | 10 | 2 | 8 | 0 | 0 | 8 | 100.00% | 2987.653 | 4486.7 |
| live_cloudflare_full_beast | 10 | 10 | 1 | 9 | 0 | 1 | 9 | 100.00% | 1497.06 | 3590.0 |
| live_llm7_full_beast | 10 | 10 | 0 | 10 | 1 | 10 | 10 | 100.00% | 2969.59 | None |
| live_aion_labs_full_beast | 10 | 10 | 1 | 9 | 0 | 0 | 9 | 100.00% | 3825.734 | 2261.6 |
| live_puter_deepseek_full_beast | 10 | 10 | 4 | 6 | 0 | 0 | 6 | 100.00% | 12018.808 | 0.0 |

## Live Provider Results

- `sambanova` / `provider_model_wiring` / `live_sambanova_full_beast`: PASS; estimated_tokens=4280; provider_prompt_tokens=4637; latency_ms=2982.269; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `config_validation_edge_case` / `live_sambanova_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=3294; latency_ms=2382.082; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `provider_id_parser` / `live_sambanova_full_beast`: PASS; estimated_tokens=3172; provider_prompt_tokens=3320; latency_ms=2158.44; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `multi_file_hidden_decimal_fix` / `live_sambanova_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=3349; latency_ms=2318.227; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `ui_state_collapse_selection` / `live_sambanova_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=3235; latency_ms=2381.268; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `async_streaming_empty_chunk` / `live_sambanova_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3197; latency_ms=2474.655; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `provider_config_secret_redaction` / `live_sambanova_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=3161; latency_ms=2388.993; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `patch_rollback_created_file` / `live_sambanova_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=3152; latency_ms=2377.545; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `output_governance_malformed_json` / `live_sambanova_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=3159; latency_ms=2368.702; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `sambanova` / `nim_refs_only_contract` / `live_sambanova_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=3189; latency_ms=2298.525; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_model_wiring` / `live_mistral_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=5539; latency_ms=5913.323; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `config_validation_edge_case` / `live_mistral_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=4019; latency_ms=3570.152; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_id_parser` / `live_mistral_full_beast`: PASS; estimated_tokens=3170; provider_prompt_tokens=3990; latency_ms=2197.054; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `multi_file_hidden_decimal_fix` / `live_mistral_full_beast`: PASS; estimated_tokens=3191; provider_prompt_tokens=4077; latency_ms=3760.762; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `ui_state_collapse_selection` / `live_mistral_full_beast`: PASS; estimated_tokens=3116; provider_prompt_tokens=3963; latency_ms=2817.424; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `async_streaming_empty_chunk` / `live_mistral_full_beast`: PASS; estimated_tokens=3065; provider_prompt_tokens=3860; latency_ms=2318.305; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_full_beast`: PASS; estimated_tokens=3054; provider_prompt_tokens=3843; latency_ms=2306.662; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `patch_rollback_created_file` / `live_mistral_full_beast`: PASS; estimated_tokens=3025; provider_prompt_tokens=3796; latency_ms=2224.945; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_full_beast`: PASS; estimated_tokens=3041; provider_prompt_tokens=3819; latency_ms=2420.987; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `nim_refs_only_contract` / `live_mistral_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=3904; latency_ms=2346.913; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `provider_model_wiring` / `live_cloudflare_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=4615; latency_ms=2052.423; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `config_validation_edge_case` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=3331; latency_ms=1216.256; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `provider_id_parser` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=3317; latency_ms=1025.43; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `multi_file_hidden_decimal_fix` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=3343; latency_ms=2330.626; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `ui_state_collapse_selection` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3118; provider_prompt_tokens=3229; latency_ms=1493.745; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `async_streaming_empty_chunk` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3165; latency_ms=1133.537; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `provider_config_secret_redaction` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=3146; latency_ms=1244.133; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `patch_rollback_created_file` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3027; provider_prompt_tokens=3120; latency_ms=1677.323; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: action a3 old snippet matched 2 times in app/rollback.py
- `cloudflare` / `output_governance_malformed_json` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3148; latency_ms=1448.619; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cloudflare` / `nim_refs_only_contract` / `live_cloudflare_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=3186; latency_ms=1348.509; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `llm7` / `provider_model_wiring` / `live_llm7_full_beast`: PASS; estimated_tokens=4276; provider_prompt_tokens=None; latency_ms=4731.127; canonicalized=True; repair_attempted=True; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Server error '524 <none>' for url 'https://api.llm7.io/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/524
- `llm7` / `config_validation_edge_case` / `live_llm7_full_beast`: PASS; estimated_tokens=3190; provider_prompt_tokens=None; latency_ms=4882.157; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `provider_id_parser` / `live_llm7_full_beast`: PASS; estimated_tokens=3168; provider_prompt_tokens=None; latency_ms=4360.348; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `multi_file_hidden_decimal_fix` / `live_llm7_full_beast`: PASS; estimated_tokens=3189; provider_prompt_tokens=None; latency_ms=2925.709; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `ui_state_collapse_selection` / `live_llm7_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=None; latency_ms=2627.559; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `async_streaming_empty_chunk` / `live_llm7_full_beast`: PASS; estimated_tokens=3063; provider_prompt_tokens=None; latency_ms=1953.133; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `provider_config_secret_redaction` / `live_llm7_full_beast`: PASS; estimated_tokens=3052; provider_prompt_tokens=None; latency_ms=1863.329; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `patch_rollback_created_file` / `live_llm7_full_beast`: PASS; estimated_tokens=3023; provider_prompt_tokens=None; latency_ms=2173.388; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `output_governance_malformed_json` / `live_llm7_full_beast`: PASS; estimated_tokens=3039; provider_prompt_tokens=None; latency_ms=2308.457; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Action IR handoff_hash did not match provider handoff
- `llm7` / `nim_refs_only_contract` / `live_llm7_full_beast`: PASS; estimated_tokens=3054; provider_prompt_tokens=None; latency_ms=1870.692; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `provider_model_wiring` / `live_aion_labs_full_beast`: PASS; estimated_tokens=4280; provider_prompt_tokens=4691; latency_ms=5278.112; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `config_validation_edge_case` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=3375; latency_ms=2943.939; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `provider_id_parser` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3172; provider_prompt_tokens=3332; latency_ms=3787.748; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `multi_file_hidden_decimal_fix` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=3386; latency_ms=3423.492; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `ui_state_collapse_selection` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=3265; latency_ms=3558.558; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `async_streaming_empty_chunk` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3225; latency_ms=3962.555; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `aion_labs` / `provider_config_secret_redaction` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.aionlabs.ai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `aion_labs` / `patch_rollback_created_file` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.aionlabs.ai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `aion_labs` / `output_governance_malformed_json` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.aionlabs.ai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `aion_labs` / `nim_refs_only_contract` / `live_aion_labs_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.aionlabs.ai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `puter_deepseek` / `provider_model_wiring` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=4284; provider_prompt_tokens=0; latency_ms=13325.674; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `config_validation_edge_case` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3198; provider_prompt_tokens=0; latency_ms=8861.195; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `provider_id_parser` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3176; provider_prompt_tokens=0; latency_ms=5184.976; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `multi_file_hidden_decimal_fix` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3196; provider_prompt_tokens=0; latency_ms=16114.276; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `ui_state_collapse_selection` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3121; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: The read operation timed out
- `puter_deepseek` / `async_streaming_empty_chunk` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3070; provider_prompt_tokens=0; latency_ms=12517.862; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `provider_config_secret_redaction` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3059; provider_prompt_tokens=0; latency_ms=14308.734; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `patch_rollback_created_file` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=0; latency_ms=15916.535; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `output_governance_malformed_json` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3047; provider_prompt_tokens=0; latency_ms=9684.328; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `puter_deepseek` / `nim_refs_only_contract` / `live_puter_deepseek_full_beast`: PASS; estimated_tokens=3061; provider_prompt_tokens=0; latency_ms=12255.689; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aion_labs | 0.3895 | False | 0.6 | 0.6 | 0.6 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| cloudflare | 0.4826 | False | 1.0 | 0.9 | 0.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| llm7 | 0.23 | False | 1.0 | 0.1 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| mistral | 0.5447 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| puter_deepseek | 0.6191 | False | 0.9 | 0.9 | 0.9 | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 |
| sambanova | 0.5117 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 46
- `infra_failure`: 5
