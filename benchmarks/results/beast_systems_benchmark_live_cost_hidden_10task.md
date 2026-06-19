# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-19T08:29:04Z`

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

| Provider | Tasks | Completed | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Coverage | Completion Rate | Avg Latency ms | Tokens/Fix | First-party USD/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openrouter | 10 | 10 | 0 | 10 | 0/10 (0.00%) | 0/10 (0.00%) | 10/10 | 100.00% | 2804.888 | 4539.1 | 0.0005497 |
| openrouter_gptoss | 10 | 10 | 2 | 8 | 2/10 (20.00%) | 2/10 (20.00%) | 10/10 | 100.00% | 18066.351 | 4058.4 | 0.00052658 |
| openrouter_qwen_coder | 10 | 10 | 2 | 8 | 2/10 (20.00%) | 2/10 (20.00%) | 10/10 | 100.00% | 7630.2 | 4080.4 | 0.001671967 |
| openrouter_deepseek | 10 | 10 | 1 | 9 | 1/10 (10.00%) | 1/10 (10.00%) | 10/10 | 100.00% | 18601.378 | 3720.7 | 0.00134076 |
| deepinfra | 10 | 10 | 0 | 10 | 0/10 (0.00%) | 0/10 (0.00%) | 10/10 | 100.00% | 29784.112 | 595.1 | 4.1299e-05 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_openrouter_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | 2804.888 | 4539.1 |
| live_openrouter_gptoss_full_beast | 10 | 10 | 2 | 8 | 1 | 4 | 8 | 100.00% | 18066.351 | 4058.4 |
| live_openrouter_qwen_coder_full_beast | 10 | 10 | 2 | 8 | 0 | 0 | 8 | 100.00% | 7630.2 | 4080.4 |
| live_openrouter_deepseek_full_beast | 10 | 10 | 1 | 9 | 0 | 0 | 9 | 100.00% | 18601.378 | 3720.7 |
| live_deepinfra_full_beast | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 100.00% | 29784.112 | 595.1 |

## Live Provider Results

- `openrouter` / `provider_model_wiring` / `live_openrouter_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=5783; latency_ms=4237.811; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `config_validation_edge_case` / `live_openrouter_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=4161; latency_ms=3503.608; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `provider_id_parser` / `live_openrouter_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=4141; latency_ms=3201.421; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `multi_file_hidden_decimal_fix` / `live_openrouter_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=4185; latency_ms=2863.531; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `ui_state_collapse_selection` / `live_openrouter_full_beast`: PASS; estimated_tokens=3118; provider_prompt_tokens=4096; latency_ms=1897.028; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `async_streaming_empty_chunk` / `live_openrouter_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3966; latency_ms=3549.645; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `provider_config_secret_redaction` / `live_openrouter_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=4004; latency_ms=2284.021; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `patch_rollback_created_file` / `live_openrouter_full_beast`: PASS; estimated_tokens=3027; provider_prompt_tokens=3915; latency_ms=1955.338; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `output_governance_malformed_json` / `live_openrouter_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3975; latency_ms=1765.71; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `nim_refs_only_contract` / `live_openrouter_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=3972; latency_ms=2790.768; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `provider_model_wiring` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=4286; provider_prompt_tokens=4759; latency_ms=15995.725; canonicalized=True; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `config_validation_edge_case` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3200; provider_prompt_tokens=1955; latency_ms=14459.613; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `provider_id_parser` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3178; provider_prompt_tokens=2259; latency_ms=10339.788; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `multi_file_hidden_decimal_fix` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3198; provider_prompt_tokens=3449; latency_ms=29372.932; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: action a1 did not include resolvable old/new snippets
- `openrouter_gptoss` / `ui_state_collapse_selection` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3123; provider_prompt_tokens=3355; latency_ms=8729.976; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `async_streaming_empty_chunk` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3073; provider_prompt_tokens=3181; latency_ms=23391.388; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `provider_config_secret_redaction` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3062; provider_prompt_tokens=3274; latency_ms=27483.102; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `patch_rollback_created_file` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3032; provider_prompt_tokens=3227; latency_ms=23151.839; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `output_governance_malformed_json` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3049; provider_prompt_tokens=3227; latency_ms=24994.62; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_gptoss` / `nim_refs_only_contract` / `live_openrouter_gptoss_full_beast`: PASS; estimated_tokens=3064; provider_prompt_tokens=2124; latency_ms=2744.532; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `provider_model_wiring` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=4289; provider_prompt_tokens=5148; latency_ms=11270.971; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `config_validation_edge_case` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3203; provider_prompt_tokens=3701; latency_ms=7901.776; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `provider_id_parser` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3181; provider_prompt_tokens=3666; latency_ms=8121.336; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `multi_file_hidden_decimal_fix` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3201; provider_prompt_tokens=3741; latency_ms=5271.65; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `ui_state_collapse_selection` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3126; provider_prompt_tokens=3609; latency_ms=5603.046; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `async_streaming_empty_chunk` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3076; provider_prompt_tokens=3507; latency_ms=5030.225; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `provider_config_secret_redaction` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3065; provider_prompt_tokens=3542; latency_ms=8554.942; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `patch_rollback_created_file` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3035; provider_prompt_tokens=3496; latency_ms=8735.341; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `output_governance_malformed_json` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3052; provider_prompt_tokens=3549; latency_ms=8005.493; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_qwen_coder` / `nim_refs_only_contract` / `live_openrouter_qwen_coder_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3556; latency_ms=7807.223; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `provider_model_wiring` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=4287; provider_prompt_tokens=5141; latency_ms=25780.657; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `config_validation_edge_case` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3201; provider_prompt_tokens=3692; latency_ms=15898.888; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `provider_id_parser` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3179; provider_prompt_tokens=3664; latency_ms=10709.776; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `multi_file_hidden_decimal_fix` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3200; provider_prompt_tokens=3692; latency_ms=6025.7; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `ui_state_collapse_selection` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3125; provider_prompt_tokens=3604; latency_ms=17421.154; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `async_streaming_empty_chunk` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3074; provider_prompt_tokens=3514; latency_ms=15080.619; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `provider_config_secret_redaction` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3063; provider_prompt_tokens=3532; latency_ms=14274.287; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `patch_rollback_created_file` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3034; provider_prompt_tokens=3500; latency_ms=31854.53; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `output_governance_malformed_json` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3050; provider_prompt_tokens=3547; latency_ms=30366.79; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter_deepseek` / `nim_refs_only_contract` / `live_openrouter_deepseek_full_beast`: PASS; estimated_tokens=3065; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://openrouter.ai/api/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `provider_model_wiring` / `live_deepinfra_full_beast`: PASS; estimated_tokens=4280; provider_prompt_tokens=4753; latency_ms=29784.112; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `deepinfra` / `config_validation_edge_case` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `provider_id_parser` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3172; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `multi_file_hidden_decimal_fix` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3192; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `ui_state_collapse_selection` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3117; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `async_streaming_empty_chunk` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `provider_config_secret_redaction` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `patch_rollback_created_file` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3026; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `output_governance_malformed_json` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `deepinfra` / `nim_refs_only_contract` / `live_deepinfra_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402

## Live Provider Fitness

| Provider | Score | Eligible | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deepinfra | 0.23 | False | 0/10 (0.0) | 0/10 (0.0) | 0.1 | 0.1 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 |
| openrouter | 0.5 | False | 0/10 (0.0) | 0/10 (0.0) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| openrouter_deepseek | 0.4868 | False | 1/10 (0.1) | 1/10 (0.1) | 0.9 | 0.9 | 0.9 | 0.0 | 0.0 | 0.0 | 0.0 |
| openrouter_gptoss | 0.5225 | False | 2/10 (0.2) | 2/10 (0.2) | 0.9 | 0.9 | 0.9 | 0.0 | 0.0 | 0.0 | 0.0 |
| openrouter_qwen_coder | 0.5686 | False | 2/10 (0.2) | 2/10 (0.2) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 35
- `infra_failure`: 10
