# Full BEAST All-Route Hidden-Cost Summary

Generated: `2026-06-19`

Source reports:

- `benchmarks/results/beast_systems_benchmark_live_all_routes_full_beast_hidden_cost.json`
- `benchmarks/results/beast_systems_benchmark_live_all_routes_full_beast_hidden_cost.md`
- `benchmarks/results/beast_systems_benchmark_live_all_routes_full_beast_hidden_cost_gauntlet/`

## Executive Summary

- Provider routes tested: `25`
- Tasks per provider route: `10`
- Total live tasks: `250`
- BEAST end-to-end completions: `250/250`
- Clean provider completions: `9/250`
- BEAST-rescued completions: `241/250`
- Hidden coverage: `10/10` tasks for every provider route
- Routes with any clean hidden pass: `5/25`
- Routes with first-party hidden-clean USD/fix in this run: `1/25`

This is the right framing:

BEAST reliably completed the tasks and exposed which provider routes produced clean hidden-passing patches versus which routes required BEAST rescue.

It is not yet correct to claim that providers reliably solve hidden coding tasks cleanly. The best clean hidden count in this full all-route run was `3/10`.

## Sacred Metric

The new routing metric is:

`Hidden Clean USD/Fix = first-party observed cost for clean hidden-passing fixes / clean hidden-passing fixes`

The inverse is also recorded:

`Hidden Clean / USD = clean hidden-passing fixes / first-party observed USD`

Routes are excluded from cost ranking when cost coverage is incomplete or the route is degraded by auth, billing, quota, or timeout failures.

## All-Route Result Table

| Provider | Clean | Hidden Clean | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Fitness | Role | Confidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `cohere` | 3/10 | 3/10 | None | 70% | 0.4286 | 0% | 0.581 | `clean_candidate_cost_incomplete` | `medium_cost_incomplete` |
| `mistral` | 2/10 | 2/10 | None | 80% | 0.25 | 0% | 0.571 | `clean_candidate_cost_incomplete` | `medium_cost_incomplete` |
| `openrouter` | 2/10 | 2/10 | 0.00026688 | 80% | 0.25 | 40% | 0.3524 | `route_degraded_exclude_cost_rank` | `degraded` |
| `gemini` | 1/10 | 1/10 | None | 90% | 0.1111 | 0% | 0.2805 | `route_degraded_exclude_cost_rank` | `degraded` |
| `puter_deepseek` | 1/10 | 1/10 | None | 90% | 0.1111 | 0% | 0.5385 | `clean_candidate_cost_incomplete` | `medium_cost_incomplete` |
| `aion_labs` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `cerebras` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.23 | `route_degraded_exclude_cost_rank` | `degraded` |
| `cloudflare` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.47 | `scout_or_infra_probe` | `medium_cost_incomplete` |
| `deepinfra` | 0/10 | 0/10 | None | 100% | 0.0 | 10% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `deepseek` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `fal` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `featherless` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `github_models` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `groq` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.23 | `route_degraded_exclude_cost_rank` | `degraded` |
| `huggingface` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.23 | `route_degraded_exclude_cost_rank` | `degraded` |
| `hyperbolic` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `llm7` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.26 | `scout_or_infra_probe` | `medium_cost_incomplete` |
| `novita` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.5 | `scout_or_infra_probe` | `medium_cost_incomplete` |
| `nscale` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.23 | `route_degraded_exclude_cost_rank` | `degraded` |
| `nvidia_nim` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.29 | `refs_only_transform_selector` | `medium_cost_incomplete` |
| `openrouter_deepseek` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `openrouter_gptoss` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `openrouter_qwen_coder` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `ovhcloud` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.2 | `route_degraded_exclude_cost_rank` | `degraded` |
| `sambanova` | 0/10 | 0/10 | None | 100% | 0.0 | 0% | 0.5 | `scout_or_infra_probe` | `medium_cost_incomplete` |

## Cost Rank Eligibility

No route in this all-route run should be promoted into a definitive cost ranking.

`openrouter` is the only route with observed first-party hidden-clean USD/fix:

- Hidden clean: `2/10`
- Hidden Clean USD/Fix: `$0.00026688`
- Hidden Clean / USD: `3747.002`
- Cost coverage: `40%`

Because cost coverage was only `40%` and the route later hit `402 Payment Required`, it is evidence of a cheap clean-capable route, but it is not eligible for a final cost leaderboard.

DeepInfra had one first-party cost observation and then degraded, so it is also excluded from cost ranking in this all-route run.

## Routing Policy Read

High-risk source patch:

- Current all-route winner by clean hidden count: `cohere`
- Next best clean hidden route: `mistral`
- Both need external pricing adapters or first-party cost support before they can be ranked by hidden-clean economics.

Cost-sensitive clean-capable route:

- `openrouter` showed the only first-party hidden-clean USD/fix in this run, but cost coverage was incomplete and billing degraded mid-run.
- Keep the earlier focused OpenRouter cost run as the cleaner cost evidence until OpenRouter quota/billing is stable.

Low-risk or strong-local-repair tasks:

- `cloudflare`, `novita`, `sambanova`, and `llm7` remain possible scout or infra-probe routes.
- They were not clean patch providers in this run.

Specialized route:

- `nvidia_nim` remains a `refs_only_transform_selector`.
- It completed under BEAST rescue but produced `0/10` clean hidden passes and had high latency.

Exclude from cost ranking:

- Any route with incomplete cost observations, `402`, `403`, `429`, auth failures, or sustained provider errors.
- In this run that includes the OpenRouter variants after billing degradation, DeepInfra, HuggingFace router derivatives affected by payment errors, Gemini after quota errors, GitHub Models, FAL, Hyperbolic, and direct DeepSeek.

## Bottom Line

The full all-route run proves BEAST system reliability under messy provider conditions: `250/250` end-to-end completions.

It also proves why BEAST needs provider-economist routing:

- `clean hidden` separates patch-capable routes from rescue-only routes.
- `Hidden Clean USD/Fix` separates cheap clean-capable routes from cheap rescue routes.
- `Cost Coverage` prevents partial billing data from polluting cost rankings.
- `Recommended Role` and `Route Confidence` keep degraded infra out of capability claims.

The next fair cost run should target only routes with stable billing and first-party cost data, then require at least `80%` cost coverage before assigning a cost rank.
