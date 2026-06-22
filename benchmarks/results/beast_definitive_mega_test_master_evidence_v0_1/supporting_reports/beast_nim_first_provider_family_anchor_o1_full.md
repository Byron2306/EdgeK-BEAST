# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:17:47Z`

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
| nvidia_nim | 18 | 6 | 0 | 6 | 0/18 (0.00%) | 0/18 (0.00%) | 18/18 | None | 100.00% | 0.0 | 0.00% | 33.33% | 24146.621 | 5295.5 | None | refs_only_transform_selector | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_raw | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 32146.373 | None |
| live_nvidia_nim_schema_only | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 27094.27 | None |
| live_nvidia_nim_full_beast | 6 | 6 | 0 | 6 | 0 | 5 | 6 | 100.00% | 13199.22 | 5295.5 |

## Live Provider Results

- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=59070.194; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=22386.561; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=3978; latency_ms=17146.063; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=409; provider_prompt_tokens=511; latency_ms=21865.571; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=409; provider_prompt_tokens=511; latency_ms=43022.943; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_id_parser` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3421; provider_prompt_tokens=4756; latency_ms=13720.321; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `multi_file_hidden_decimal_fix` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=397; latency_ms=20782.903; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `multi_file_hidden_decimal_fix` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=311; provider_prompt_tokens=397; latency_ms=13761.416; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: operations[0].path was not allowed: one allowed path
- `nvidia_nim` / `multi_file_hidden_decimal_fix` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3324; provider_prompt_tokens=4477; latency_ms=8336.873; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `nvidia_nim` / `config_validation_edge_case` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=427; provider_prompt_tokens=537; latency_ms=49190.195; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `config_validation_edge_case` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=427; provider_prompt_tokens=537; latency_ms=45928.872; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `config_validation_edge_case` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3540; provider_prompt_tokens=5059; latency_ms=9879.423; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=384; latency_ms=25464.381; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=300; provider_prompt_tokens=384; latency_ms=13949.959; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_config_secret_redaction` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3126; provider_prompt_tokens=4095; latency_ms=14658.323; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR
- `nvidia_nim` / `nim_refs_only_contract` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=281; provider_prompt_tokens=379; latency_ms=16504.994; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `nim_refs_only_contract` / `live_nvidia_nim_schema_only`: FAIL; estimated_tokens=281; provider_prompt_tokens=379; latency_ms=23515.87; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `nim_refs_only_contract` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=4008; latency_ms=15454.316; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: refs-only provider must return BEAST Action IR

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nvidia_nim | 0.2667 | False | refs_only_transform_selector | low | None | 1.0 | 0.0 | 0.0 | 0/18 (0.0) | 0/18 (0.0) | 0.1111 | 0.0556 | 0.0556 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `nim_success`: 5
- `nim_tests_failed`: 13
