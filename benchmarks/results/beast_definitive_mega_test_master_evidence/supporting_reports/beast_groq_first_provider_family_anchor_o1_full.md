# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:33:52Z`

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
| groq | 18 | 6 | 0 | 6 | 0/18 (0.00%) | 0/18 (0.00%) | 18/18 | None | 100.00% | 0.0 | 0.00% | 33.33% | 671.322 | 1152.333 | None | scout_or_infra_probe | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_groq_raw | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 621.52 | None |
| live_groq_schema_only | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 602.116 | None |
| live_groq_full_beast | 6 | 6 | 0 | 6 | 0 | 0 | 6 | 100.00% | 1028.347 | 1152.333 |

## Live Provider Results

- `groq` / `output_governance_malformed_json` / `live_groq_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=334; latency_ms=535.283; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `output_governance_malformed_json` / `live_groq_schema_only`: FAIL; estimated_tokens=267; provider_prompt_tokens=334; latency_ms=477.393; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `output_governance_malformed_json` / `live_groq_full_beast`: PASS; estimated_tokens=3028; provider_prompt_tokens=3105; latency_ms=1118.014; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `groq` / `provider_id_parser` / `live_groq_raw`: FAIL; estimated_tokens=409; provider_prompt_tokens=482; latency_ms=739.716; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `provider_id_parser` / `live_groq_schema_only`: FAIL; estimated_tokens=409; provider_prompt_tokens=482; latency_ms=734.68; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `provider_id_parser` / `live_groq_full_beast`: PASS; estimated_tokens=3158; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `multi_file_hidden_decimal_fix` / `live_groq_raw`: FAIL; estimated_tokens=311; provider_prompt_tokens=378; latency_ms=487.954; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `multi_file_hidden_decimal_fix` / `live_groq_schema_only`: FAIL; estimated_tokens=311; provider_prompt_tokens=378; latency_ms=492.151; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `multi_file_hidden_decimal_fix` / `live_groq_full_beast`: PASS; estimated_tokens=3186; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `config_validation_edge_case` / `live_groq_raw`: FAIL; estimated_tokens=427; provider_prompt_tokens=504; latency_ms=765.606; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `config_validation_edge_case` / `live_groq_schema_only`: FAIL; estimated_tokens=427; provider_prompt_tokens=504; latency_ms=741.999; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `config_validation_edge_case` / `live_groq_full_beast`: PASS; estimated_tokens=3180; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/config.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `groq` / `provider_config_secret_redaction` / `live_groq_raw`: FAIL; estimated_tokens=300; provider_prompt_tokens=373; latency_ms=638.715; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `provider_config_secret_redaction` / `live_groq_schema_only`: FAIL; estimated_tokens=300; provider_prompt_tokens=373; latency_ms=675.654; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `provider_config_secret_redaction` / `live_groq_full_beast`: PASS; estimated_tokens=3042; provider_prompt_tokens=3175; latency_ms=938.681; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `groq` / `nim_refs_only_contract` / `live_groq_raw`: FAIL; estimated_tokens=281; provider_prompt_tokens=358; latency_ms=561.849; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `nim_refs_only_contract` / `live_groq_schema_only`: FAIL; estimated_tokens=281; provider_prompt_tokens=358; latency_ms=490.819; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Action IR missing provider_handoff_hash
- `groq` / `nim_refs_only_contract` / `live_groq_full_beast`: PASS; estimated_tokens=3055; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '429 Too Many Requests' for url 'https://api.groq.com/openai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| groq | 0.2833 | False | scout_or_infra_probe | low | None | 1.0 | 0.0 | 0.0 | 0/18 (0.0) | 0/18 (0.0) | 0.7778 | 0.1111 | 0.1111 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 14
- `infra_failure`: 4
