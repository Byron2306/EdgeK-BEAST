# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-20T21:03:48Z`

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
| gemini | 2 | 1 | 0 | 1 | 0/2 (0.00%) | 0/2 (0.00%) | 2/2 | None | 100.00% | 0.0 | 0.00% | 50.00% | None | None | None | scout_or_infra_probe | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_gemini_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | None | None |
| live_gemini_full_beast | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 100.00% | None | None |

## Live Provider Results

- `gemini` / `provider_model_wiring` / `live_gemini_raw`: FAIL; estimated_tokens=1020; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: Client error '400 Bad Request' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400
- `gemini` / `provider_model_wiring` / `live_gemini_full_beast`: PASS; estimated_tokens=4278; provider_prompt_tokens=None; latency_ms=None; canonicalized=False; repair_attempted=None; local_verifier_repair=True; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: Client error '400 Bad Request' for url 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini | 0.25 | False | scout_or_infra_probe | low | None | 1.0 | 0.0 | 0.0 | 0/2 (0.0) | 0/2 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 2
