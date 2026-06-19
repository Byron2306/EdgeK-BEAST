# Live Cost + Hidden Coverage 10-Task Summary

Generated: `2026-06-19`

Source reports:

- `benchmarks/results/beast_systems_benchmark_live_cost_hidden_10task.json`
- `benchmarks/results/beast_systems_benchmark_live_cost_hidden_10task.md`
- `benchmarks/results/beast_systems_benchmark_live_cost_hidden_10task_gauntlet/`

## Why This Run Exists

This run addresses the two main skepticism points in the previous evidence package:

1. Hidden tests were too sparse and too easy to criticize.
2. USD/fix was missing for most providers.

The benchmark harness now gives every expanded-surface task a hidden test and separates visible-clean from hidden-clean results in the headline table. It also extracts first-party cost fields from provider responses when available: `usage.estimated_cost`, `usage.cost`, `usage.total_cost_usd`, or `usage.cost_details.upstream_inference_cost`.

## Executive Summary

- Providers/routes tested: `5`
- Total live tasks: `50`
- Hidden coverage: `10/10` tasks per provider
- BEAST completions: `50/50`
- Clean provider completions: `5/50`
- BEAST-rescued completions: `45/50`
- Routes with first-party cost observations: `5/5`
- Routes with near-complete cost observations: `4/5`

DeepInfra returned first-party cost on the first call, then hit `402 Payment Required` for the rest of the run. Its USD/fix row is therefore marked partial and should not be compared directly with the four OpenRouter-backed routes.

## Results

| Rank | Provider Route | Tasks | BEAST Pass | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Coverage | Fitness | First-party USD/Fix | Cost Observations | Avg Latency ms | Tokens/Fix | Notes |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `openrouter_qwen_coder` | 10 | 10 | 2 | 8 | 2/10 | 2/10 | 10/10 | 0.5686 | `$0.001671967` | 10/10 | 7630.2 | 4080.4 | Best score in this run; clean hidden signal improved to 20%. |
| 2 | `openrouter_gptoss` | 10 | 10 | 2 | 8 | 2/10 | 2/10 | 10/10 | 0.5225 | `$0.000526580` | 10/10 | 18066.351 | 4058.4 | Lower USD/fix than Qwen Coder, but much slower. |
| 3 | `openrouter` | 10 | 10 | 0 | 10 | 0/10 | 0/10 | 10/10 | 0.5000 | `$0.000549700` | 10/10 | 2804.888 | 4539.1 | Fast and fully costed, but all tasks required BEAST rescue. |
| 4 | `openrouter_deepseek` | 10 | 10 | 1 | 9 | 1/10 | 1/10 | 10/10 | 0.4868 | `$0.001340760` | 9/10 | 18601.378 | 3720.7 | One direct route billing failure; clean hidden signal at 10%. |
| 5 | `deepinfra` | 10 | 10 | 0 | 10 | 0/10 | 0/10 | 10/10 | 0.2300 | `$0.000041299` | 1/10 | 29784.112 | 595.1 | Cost-partial only: 9/10 calls hit `402 Payment Required`. |

## Interpretation

The hidden-test objection is now materially addressed for the next-run surface. Every task class has hidden coverage, and the report exposes visible-clean and hidden-clean counts side by side. A skeptic can still say the clean hidden rates are low, but they can no longer say the hidden surface was sparse or buried.

The cost objection is also materially improved. Four OpenRouter-backed routes returned near-complete first-party cost data. The standout cost number is `openrouter_gptoss`: about `$0.00052658` per verified fix with `2/10` clean hidden completions. `openrouter/auto` is similarly cheap and fast, but it produced `0/10` clean hidden completions in this run, so its best role remains rescue-backed rather than patch-provider.

`openrouter_qwen_coder` had the best score and clean hidden count, but at roughly 3x the USD/fix of `openrouter_gptoss`. That is exactly the kind of tradeoff BEAST’s route policy should use: spend more on Qwen Coder when a coding-specialized patch attempt is worth it, use cheaper gpt-oss/auto lanes when BEAST is expected to rescue locally.

DeepInfra should not be cost-ranked from this run because the route became billing-blocked after one call. Keep the older DeepInfra full-cost run in the package, but label this focused run as route/billing degraded for DeepInfra.

## Harness Changes Proven By This Run

- Hidden tests now exist for all 10 expanded task classes.
- Markdown provider summaries now include:
  - `Visible Clean`
  - `Hidden Clean`
  - `Hidden Coverage`
  - `First-party USD/Fix`
- Gauntlet cost summaries now include:
  - visible-clean and hidden-clean counts
  - first-party USD/fix
  - cost observation count
- OpenRouter calls now request provider usage/cost data via `usage.include`.

## Recommended Next Moves

- Re-run the broader combined matrix with the expanded hidden surface once time/budget allows.
- Keep OpenRouter route variants in the cost comparison set:
  - `openrouter`
  - `openrouter_gptoss`
  - `openrouter_qwen_coder`
  - `openrouter_deepseek`
- Add provider-specific pricing adapters for routes that do not return first-party dollar cost.
- Fix or top up DeepInfra/HF billing before using DeepInfra in cost comparisons.
- Promote `visible_clean` and `hidden_clean` into the runtime provider-fitness router, not just the report.
