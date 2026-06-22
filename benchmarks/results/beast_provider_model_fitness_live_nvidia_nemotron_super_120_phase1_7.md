# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-20T21:09:00Z`

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
| nvidia_nim | 2 | 1 | 0 | 1 | 0/2 (0.00%) | 0/2 (0.00%) | 2/2 | None | 100.00% | 0.0 | 0.00% | 50.00% | 12534.789 | 8196.0 | None | refs_only_transform_selector | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 2249.626 | None |
| live_nvidia_nim_full_beast | 1 | 1 | 0 | 1 | 1 | 0 | 1 | 100.00% | 22819.951 | 8196.0 |

## Live Provider Results

- `nvidia_nim` / `provider_model_wiring` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=1020; provider_prompt_tokens=1197; latency_ms=2249.626; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `provider_model_wiring` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=5103; provider_prompt_tokens=8100; latency_ms=22819.951; canonicalized=True; repair_attempted=False; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nvidia_nim | 0.4 | False | refs_only_transform_selector | low | None | 1.0 | 0.0 | 0.0 | 0/2 (0.0) | 0/2 (0.0) | 0.5 | 0.5 | 0.5 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `nim_tests_failed`: 2
