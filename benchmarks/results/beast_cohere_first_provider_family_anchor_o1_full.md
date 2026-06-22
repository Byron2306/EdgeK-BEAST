# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:20:59Z`

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
| cohere | 18 | 9 | 4 | 5 | 4/18 (22.22%) | 4/18 (22.22%) | 18/18 | None | 55.56% | 0.8 | 0.00% | 50.00% | 4640.135 | 3001.444 | None | clean_candidate_cost_incomplete | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_cohere_raw | 6 | 1 | 1 | 0 | 0 | 0 | 0 | 16.67% | 5048.334 | 691.0 |
| live_cohere_schema_only | 6 | 2 | 2 | 0 | 0 | 0 | 0 | 33.33% | 3440.064 | 633.0 |
| live_cohere_full_beast | 6 | 6 | 1 | 5 | 0 | 1 | 5 | 100.00% | 5432.008 | 4176.0 |

## Live Provider Results

- `cohere` / `output_governance_malformed_json` / `live_cohere_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=354; latency_ms=3758.043; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `output_governance_malformed_json` / `live_cohere_schema_only`: FAIL; estimated_tokens=267; provider_prompt_tokens=354; latency_ms=3131.917; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `output_governance_malformed_json` / `live_cohere_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=2800; latency_ms=4500.492; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_raw`: PASS; estimated_tokens=409; provider_prompt_tokens=521; latency_ms=2727.991; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_schema_only`: PASS; estimated_tokens=409; provider_prompt_tokens=521; latency_ms=2512.701; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_id_parser` / `live_cohere_full_beast`: PASS; estimated_tokens=3159; provider_prompt_tokens=4073; latency_ms=5003.587; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `multi_file_hidden_decimal_fix` / `live_cohere_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=408; latency_ms=8655.38; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py', 'app/service.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `multi_file_hidden_decimal_fix` / `live_cohere_schema_only`: PASS; estimated_tokens=311; provider_prompt_tokens=408; latency_ms=2291.708; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `multi_file_hidden_decimal_fix` / `live_cohere_full_beast`: PASS; estimated_tokens=3187; provider_prompt_tokens=4116; latency_ms=6068.908; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `config_validation_edge_case` / `live_cohere_raw`: FAIL; estimated_tokens=427; provider_prompt_tokens=551; latency_ms=5412.347; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].content was empty
- `cohere` / `config_validation_edge_case` / `live_cohere_schema_only`: FAIL; estimated_tokens=427; provider_prompt_tokens=551; latency_ms=5945.269; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].content was empty
- `cohere` / `config_validation_edge_case` / `live_cohere_full_beast`: PASS; estimated_tokens=3181; provider_prompt_tokens=4079; latency_ms=6495.819; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=396; latency_ms=4082.319; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_schema_only`: FAIL; estimated_tokens=300; provider_prompt_tokens=396; latency_ms=3513.232; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `provider_config_secret_redaction` / `live_cohere_full_beast`: PASS; estimated_tokens=3043; provider_prompt_tokens=3925; latency_ms=6046.95; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `nim_refs_only_contract` / `live_cohere_raw`: FAIL; estimated_tokens=281; provider_prompt_tokens=376; latency_ms=5653.924; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `nim_refs_only_contract` / `live_cohere_schema_only`: FAIL; estimated_tokens=281; provider_prompt_tokens=376; latency_ms=3245.558; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `nim_refs_only_contract` / `live_cohere_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=3935; latency_ms=4476.291; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cohere | 0.6073 | False | clean_candidate_cost_incomplete | low | None | 0.5556 | 0.8 | 0.0 | 4/18 (0.2222) | 4/18 (0.2222) | 1.0 | 0.8889 | 0.8889 | 0.0 | 0.0556 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 14
