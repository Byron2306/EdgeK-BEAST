# Live Expanded Repaired Provider Summary

| Provider | Scope | Completed | Clean | Rescued | Local repair | Schema repair | Avg latency ms | Tokens / verified fix |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `huggingface` | 10 expanded tasks | 10/10 | 3 | 7 | 7 | 1 | 1641.115 | 4527.4 |
| `openrouter` | 10 expanded tasks | 10/10 | 2 | 8 | 8 | 1 | 2703.126 | 4483.8 |
| `nvidia_nim` | 2 targeted NIM tasks | 2/2 | 0 | 2 | 2 | 2 | 66795.641 | 5350.5 |

## Readout

- OpenRouter and HuggingFace now complete the expanded live suite under full BEAST governance, but most hard-task completions are BEAST local verifier repairs rather than clean provider solves.
- NIM targeted tasks also complete with repair, but both are rescued and latency remains the main operational cost.
- Provider fitness should therefore report two truths: BEAST completion rate is high; clean provider fitness is still modest.

## Source Reports

- `benchmarks/results/beast_systems_benchmark_live_expanded_openrouter_hf_repaired.json`
- `benchmarks/results/beast_systems_benchmark_live_expanded_nvidia_repair_targeted.json`
