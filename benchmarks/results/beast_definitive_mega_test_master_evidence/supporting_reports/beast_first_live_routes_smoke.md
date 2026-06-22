# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T04:53:00Z`

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
| nvidia_nim | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | 7091.261 | None | None | refs_only_transform_selector | low |
| cerebras | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | None | None | None | route_degraded_exclude_cost_rank | degraded |
| mistral | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | 1720.844 | None | None | scout_or_infra_probe | low |
| ovhcloud | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | None | None | None | route_degraded_exclude_cost_rank | degraded |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 7091.261 | None |
| live_cerebras_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | None | None |
| live_mistral_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 1720.844 | None |
| live_ovhcloud_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | None | None |

## Live Provider Results

- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=7091.261; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `cerebras` / `output_governance_malformed_json` / `live_cerebras_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402
- `mistral` / `output_governance_malformed_json` / `live_mistral_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=336; latency_ms=1720.844; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `ovhcloud` / `output_governance_malformed_json` / `live_ovhcloud_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Client error '402 Payment Required' for url 'https://router.huggingface.co/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cerebras | 0.1 | False | route_degraded_exclude_cost_rank | degraded | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| mistral | 0.1 | False | scout_or_infra_probe | low | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| nvidia_nim | 0.1 | False | refs_only_transform_selector | low | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| ovhcloud | 0.1 | False | route_degraded_exclude_cost_rank | degraded | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 1
- `infra_failure`: 2
- `nim_tests_failed`: 1
