# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-21T05:00:15Z`

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
| nvidia_nim | 2 | 1 | 0 | 1 | 0/2 (0.00%) | 0/2 (0.00%) | 2/2 | None | 100.00% | 0.0 | 0.00% | 50.00% | 31695.783 | 4878.0 | None | refs_only_transform_selector | low |
| mistral | 2 | 1 | 0 | 1 | 0/2 (0.00%) | 0/2 (0.00%) | 2/2 | None | 100.00% | 0.0 | 0.00% | 50.00% | 2102.423 | 4061.0 | None | scout_or_infra_probe | low |
| gemini | 2 | 1 | 0 | 1 | 0/2 (0.00%) | 0/2 (0.00%) | 2/2 | None | 100.00% | 0.0 | 0.00% | 50.00% | 5478.32 | 3935.0 | None | scout_or_infra_probe | low |
| cohere | 2 | 1 | 1 | 0 | 1/2 (50.00%) | 1/2 (50.00%) | 2/2 | None | 0.00% | inf | 0.00% | 50.00% | 4324.837 | 4217.0 | None | clean_candidate_cost_incomplete | low |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_nvidia_nim_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 40387.058 | None |
| live_nvidia_nim_full_beast | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 100.00% | 23004.507 | 4878.0 |
| live_mistral_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 1923.604 | None |
| live_mistral_full_beast | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 100.00% | 2281.243 | 4061.0 |
| live_gemini_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 5744.845 | None |
| live_gemini_full_beast | 1 | 1 | 0 | 1 | 0 | 1 | 1 | 100.00% | 5211.795 | 3935.0 |
| live_cohere_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 2958.533 | None |
| live_cohere_full_beast | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 100.00% | 5691.142 | 4217.0 |

## Live Provider Results

- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=347; latency_ms=40387.058; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `nvidia_nim` / `output_governance_malformed_json` / `live_nvidia_nim_full_beast`: PASS; estimated_tokens=3114; provider_prompt_tokens=3978; latency_ms=23004.507; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=336; latency_ms=1923.604; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `mistral` / `output_governance_malformed_json` / `live_mistral_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3725; latency_ms=2281.243; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `gemini` / `output_governance_malformed_json` / `live_gemini_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=363; latency_ms=5744.845; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `gemini` / `output_governance_malformed_json` / `live_gemini_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3899; latency_ms=5211.795; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider failed or produced invalid scoped edit; local verifier repair passed: provider output did not include operations list
- `cohere` / `output_governance_malformed_json` / `live_cohere_raw`: FAIL; estimated_tokens=267; provider_prompt_tokens=354; latency_ms=2958.533; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `cohere` / `output_governance_malformed_json` / `live_cohere_full_beast`: PASS; estimated_tokens=3030; provider_prompt_tokens=3823; latency_ms=5691.142; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cohere | 0.7527 | True | clean_candidate_cost_incomplete | low | None | 0.0 | inf | 0.0 | 1/2 (0.5) | 1/2 (0.5) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| gemini | 0.25 | False | scout_or_infra_probe | low | None | 1.0 | 0.0 | 0.0 | 0/2 (0.0) | 0/2 (0.0) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| mistral | 0.55 | True | scout_or_infra_probe | low | None | 1.0 | 0.0 | 0.0 | 0/2 (0.0) | 0/2 (0.0) | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| nvidia_nim | 0.4 | False | refs_only_transform_selector | low | None | 1.0 | 0.0 | 0.0 | 0/2 (0.0) | 0/2 (0.0) | 0.5 | 0.5 | 0.5 | 0.0 | 0.0 | 0.0 | 1.0 |

## Failure Buckets

- `capability_failure`: 5
- `nim_tests_failed`: 2
