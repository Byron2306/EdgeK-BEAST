# Live Free/Low-Cost Routes 10-Task Summary

Generated: `2026-06-19`

Source reports:

- `benchmarks/results/beast_systems_benchmark_live_free_routes_10task.json`
- `benchmarks/results/beast_systems_benchmark_live_free_routes_10task.md`
- `benchmarks/results/beast_systems_benchmark_live_free_routes_10task_gauntlet/`

## Executive Summary

- Providers tested: `6`
- Total live tasks: `60`
- BEAST completions: `60/60`
- Clean provider completions: `9/60`
- BEAST-rescued completions: `51/60`
- GitHub Models was not included because the token reached the endpoint but returned `403 no_access` for probed models.
- Direct DeepSeek was not included because the route returned `402 Payment Required`; Puter DeepSeek was tested as a separate route.

## Provider Fitness

| Rank | Provider | Role Recommendation | Tasks | BEAST Pass | Clean | Rescued | Fitness | JSON | Schema | Patch | Hidden | Avg Latency ms | Notes |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `puter_deepseek` | `candidate_patch_provider_high_latency` | 10 | 10 | 4 | 6 | 0.6191 | 90% | 90% | 90% | 20% | 13101.99 | Best clean count and only hidden-test signal in this batch; one read timeout and high latency. |
| 2 | `mistral` | `rescue_backed_codestral_candidate` | 10 | 10 | 2 | 8 | 0.5447 | 100% | 100% | 100% | 0% | 4115.814 | Codestral produced valid governed output reliably, but BEAST rescued most tasks. |
| 3 | `sambanova` | `fast_rescue_backed_action_ir` | 10 | 10 | 1 | 9 | 0.5117 | 100% | 100% | 100% | 0% | 2982.269 | Fast and compliant, but low clean pass count. |
| 4 | `cloudflare` | `edge_microtask_or_rescue_backed_action_ir` | 10 | 10 | 1 | 9 | 0.4826 | 100% | 90% | 90% | 0% | 2052.423 | Fastest route in this batch; one schema/patch issue; likely best for scout/microtask work. |
| 5 | `aion_labs` | `rate_limited_rescue_candidate` | 10 | 10 | 1 | 9 | 0.3895 | 60% | 60% | 60% | 0% | 5278.112 | First calls worked, then 429s hit; needs rate-limit pacing before fair ranking. |
| 6 | `llm7` | `scout_only_until_hash_contract_fixed` | 10 | 10 | 0 | 10 | 0.2300 | 100% | 10% | 10% | 0% | n/a | Route responded but repeatedly failed handoff-hash/schema contract; BEAST rescue carried completion. |

## Interpretation

The free-route batch strengthened the same BEAST thesis as the earlier provider matrix: system reliability is high, but provider fitness varies sharply once output governance is enforced.

Puter DeepSeek is the most promising new candidate. It produced 4 clean completions, the only 20% hidden-test pass rate in this batch, and a top fitness score. The catch is latency: it averaged about 13.1 seconds on successful provider calls and had one read timeout. That makes it useful, but likely behind a cost/latency policy rather than as the default patch provider.

Mistral Codestral is cleanly worth keeping. It had perfect JSON/schema/patch compliance and 2 clean passes, but most tasks still needed BEAST local repair. That reads as a strong `rescue_backed_codestral_candidate`, not yet a primary patch author.

SambaNova and Cloudflare are valuable for speed and compliance. Cloudflare was fastest and should be considered for edge scout/micro-intent roles. SambaNova had excellent schema compliance but only 1 clean task, so it needs a tighter role or a different model choice before promotion.

Aion Labs needs pacing. The first part of the run worked, then the route returned multiple `429 Too Many Requests`. This should be rerun with lower concurrency or provider-specific sleep/backoff before treating the score as capability-final.

LLM7 should not write patches yet. It produced BEAST-completable runs, but mostly through rescue after handoff-hash/schema failures. Its best current role is scout-only or experimental microtask until it can preserve the Action IR contract.

## Blocked Routes

- `github_models`: endpoint accepted the token, but probed models returned `403 no_access`. The token likely needs GitHub Models access / `models` scope, or model access must be enabled for the account/org.
- `deepseek`: direct route returned `402 Payment Required`. Keep `puter_deepseek` separate because the route and economics are different.

## Recommended Next Moves

- Add retry/backoff/pacing for Aion Labs and other 429-prone routes.
- Promote `puter_deepseek`, `mistral`, `sambanova`, and `cloudflare` into the next comparative matrix.
- Test alternate SambaNova models exposed in the portal/HF route.
- Rerun Cloudflare with `@cf/openai/gpt-oss-120b` if the harness can parse its response shape reliably.
- Fix GitHub Models access, then run GPT-4o/GPT-4o-mini as its own headline route.
