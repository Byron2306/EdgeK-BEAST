# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:24:23Z`

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
| mistral | 18 | 6 | 1 | 5 | 1/18 (5.56%) | 1/18 (5.56%) | 18/18 | None | 83.33% | 0.2 | 0.00% | 33.33% | 2479.434 | 4297.5 | None | clean_candidate_cost_incomplete | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_mistral_raw | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 2212.242 | None |
| live_mistral_schema_only | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 2502.172 | None |
| live_mistral_full_beast | 6 | 6 | 1 | 5 | 0 | 0 | 5 | 100.00% | 2723.888 | 4297.5 |

## Live Provider Results

- `mistral` / `output_governance_malformed_json` / `live_mistral_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=336; latency_ms=1575.858; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_schema_only`: FAIL; estimated_tokens=267; provider_prompt_tokens=336; latency_ms=1438.392; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3725; latency_ms=2105.7; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_id_parser` / `live_mistral_raw`: FAIL; estimated_tokens=409; provider_prompt_tokens=500; latency_ms=2632.108; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].old matched 0 times in app/provider_parser.py
- `mistral` / `provider_id_parser` / `live_mistral_schema_only`: FAIL; estimated_tokens=409; provider_prompt_tokens=500; latency_ms=2440.88; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].old matched 0 times in app/provider_parser.py
- `mistral` / `provider_id_parser` / `live_mistral_full_beast`: PASS; estimated_tokens=3160; provider_prompt_tokens=3988; latency_ms=1964.851; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `multi_file_hidden_decimal_fix` / `live_mistral_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=386; latency_ms=2064.305; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py', 'app/service.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `multi_file_hidden_decimal_fix` / `live_mistral_schema_only`: FAIL; estimated_tokens=311; provider_prompt_tokens=386; latency_ms=4703.044; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/math_ops.py', 'app/service.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `multi_file_hidden_decimal_fix` / `live_mistral_full_beast`: PASS; estimated_tokens=3188; provider_prompt_tokens=4071; latency_ms=2876.356; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `config_validation_edge_case` / `live_mistral_raw`: FAIL; estimated_tokens=427; provider_prompt_tokens=526; latency_ms=4079.782; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `config_validation_edge_case` / `live_mistral_schema_only`: FAIL; estimated_tokens=427; provider_prompt_tokens=526; latency_ms=3597.185; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `config_validation_edge_case` / `live_mistral_full_beast`: PASS; estimated_tokens=3182; provider_prompt_tokens=4013; latency_ms=3019.069; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=373; latency_ms=1591.515; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_schema_only`: FAIL; estimated_tokens=300; provider_prompt_tokens=373; latency_ms=1633.247; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `provider_config_secret_redaction` / `live_mistral_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3842; latency_ms=4317.474; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `nim_refs_only_contract` / `live_mistral_raw`: FAIL; estimated_tokens=281; provider_prompt_tokens=368; latency_ms=1329.881; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `nim_refs_only_contract` / `live_mistral_schema_only`: FAIL; estimated_tokens=281; provider_prompt_tokens=368; latency_ms=1200.285; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `nim_refs_only_contract` / `live_mistral_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=3893; latency_ms=2059.88; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mistral | 0.5208 | True | clean_candidate_cost_incomplete | low | None | 0.8333 | 0.2 | 0.0 | 1/18 (0.0556) | 1/18 (0.0556) | 1.0 | 0.8889 | 0.8889 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 17
