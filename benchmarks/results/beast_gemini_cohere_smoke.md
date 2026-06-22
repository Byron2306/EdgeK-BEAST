# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T04:57:46Z`

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
| gemini | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | 1519.111 | None | None | scout_or_infra_probe | low |
| cohere | 1 | 0 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) | 1/1 | None | 0.00% | None | 0.00% | 0.00% | 1750.065 | None | None | scout_or_infra_probe | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_gemini_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 1519.111 | None |
| live_cohere_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 1750.065 | None |

## Live Provider Results

- `gemini` / `output_governance_malformed_json` / `live_gemini_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=363; latency_ms=1519.111; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `cohere` / `output_governance_malformed_json` / `live_cohere_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=354; latency_ms=1750.065; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cohere | 0.1 | False | scout_or_infra_probe | low | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| gemini | 0.1 | False | scout_or_infra_probe | low | None | 0.0 | None | 0.0 | 0/1 (0.0) | 0/1 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 2
