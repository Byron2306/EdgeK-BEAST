# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T06:38:04Z`

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
| cerebras | 10 | 10 | 2 | 8 | 100.00% | 1396.37 | 3354.143 | 3245.4 |
| deepinfra | 10 | 10 | 4 | 6 | 100.00% | 27428.858 | 3172.2 | 4267.5 |
| featherless | 10 | 10 | 2 | 8 | 100.00% | 5419.406 | 3138.333 | 2468.9 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_cerebras_full_beast | 10 | 10 | 2 | 8 | 0 | 3 | 8 | 100.00% | 1396.37 | 3245.4 |
| live_deepinfra_full_beast | 10 | 10 | 4 | 6 | 0 | 2 | 6 | 100.00% | 27428.858 | 4267.5 |
| live_featherless_full_beast | 10 | 10 | 2 | 8 | 0 | 2 | 8 | 100.00% | 5419.406 | 2468.9 |

## Live Provider Results

- `cerebras` / `provider_model_wiring` / `live_cerebras_full_beast`: PASS; estimated_tokens=4279; provider_prompt_tokens=4755; latency_ms=1279.439; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `cerebras` / `config_validation_edge_case` / `live_cerebras_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=3400; latency_ms=1014.188; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cerebras` / `provider_id_parser` / `live_cerebras_full_beast`: PASS; estimated_tokens=3171; provider_prompt_tokens=3433; latency_ms=2229.08; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `cerebras` / `multi_file_hidden_decimal_fix` / `live_cerebras_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=1970; latency_ms=1015.451; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `cerebras` / `ui_state_collapse_selection` / `live_cerebras_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=3333; latency_ms=1511.047; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `cerebras` / `async_streaming_empty_chunk` / `live_cerebras_full_beast`: PASS; estimated_tokens=3066; provider_prompt_tokens=3280; latency_ms=1251.694; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `cerebras` / `provider_config_secret_redaction` / `live_cerebras_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=3308; latency_ms=1473.691; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `cerebras` / `patch_rollback_created_file` / `live_cerebras_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `cerebras` / `output_governance_malformed_json` / `live_cerebras_full_beast`: PASS; estimated_tokens=3042; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `cerebras` / `nim_refs_only_contract` / `live_cerebras_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `provider_model_wiring` / `live_deepinfra_full_beast`: PASS; estimated_tokens=4280; provider_prompt_tokens=4753; latency_ms=28125.172; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `config_validation_edge_case` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=1981; latency_ms=21714.396; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `provider_id_parser` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3172; provider_prompt_tokens=3405; latency_ms=37697.772; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `multi_file_hidden_decimal_fix` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=3365; latency_ms=29122.197; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `ui_state_collapse_selection` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=3338; latency_ms=30885.079; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `async_streaming_empty_chunk` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=1971; latency_ms=24473.265; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `provider_config_secret_redaction` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=3262; latency_ms=36236.448; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `patch_rollback_created_file` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=3199; latency_ms=27085.724; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `output_governance_malformed_json` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=3178; latency_ms=19752.743; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `nim_refs_only_contract` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=3270; latency_ms=19195.783; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `provider_model_wiring` / `live_featherless_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=4740; latency_ms=7313.129; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `config_validation_edge_case` / `live_featherless_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=1975; latency_ms=3356.211; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `provider_id_parser` / `live_featherless_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=3396; latency_ms=5280.734; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `multi_file_hidden_decimal_fix` / `live_featherless_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=2103; latency_ms=4612.048; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `ui_state_collapse_selection` / `live_featherless_full_beast`: PASS; estimated_tokens=3119; provider_prompt_tokens=3342; latency_ms=4968.635; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `async_streaming_empty_chunk` / `live_featherless_full_beast`: PASS; estimated_tokens=3068; provider_prompt_tokens=3274; latency_ms=6985.681; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `featherless` / `provider_config_secret_redaction` / `live_featherless_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `featherless` / `patch_rollback_created_file` / `live_featherless_full_beast`: PASS; estimated_tokens=3028; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `featherless` / `output_governance_malformed_json` / `live_featherless_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `featherless` / `nim_refs_only_contract` / `live_featherless_full_beast`: PASS; estimated_tokens=3059; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cerebras | 0.3966 | False | 0.5 | 0.5 | 0.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| deepinfra | 0.612 | False | 1.0 | 1.0 | 1.0 | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 |
| featherless | 0.4221 | False | 0.6 | 0.6 | 0.6 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 14
- `infra_failure`: 8
