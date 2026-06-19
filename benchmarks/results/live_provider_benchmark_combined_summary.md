# Combined Live Provider Benchmark Summary

Generated: `2026-06-19`

This report combines the earlier comprehensive provider matrix with the newer free/low-cost route matrix. It treats provider route as part of provider identity: for example, direct DeepSeek and Puter-routed DeepSeek are different operational routes, and SambaNova direct should remain distinct from any future SambaNova Hugging Face router route.

## Executive Summary

- Provider/routes summarized: `22`
- Total evaluated live tasks: `212`
- BEAST end-to-end completions: `212/212`
- Clean provider completions: `41/212`
- BEAST-rescued completions: `171/212`
- Highest clean count: `xai` and `ovhcloud` tied with `5/10`
- Best new coding-model route: `xai` with `5/10` clean and `50%` hidden-clean pass
- Best new free/low-cost route: `puter_deepseek` with `4/10` clean and `20%` hidden-test pass
- Fastest usable route in the new batch: `cloudflare`, but still rescue-heavy

The combined result is not a normal model leaderboard. It is a route-fitness map for BEAST runtime policy. The practical question is not "which model is best?" but "which provider route should BEAST trust for this role, task class, output contract, latency budget, and cost envelope?"

## Ranked Provider Fitness

| Rank | Provider Route | Role Recommendation | Tasks | BEAST Pass | Clean | Rescued | Fitness | Rescue Score | JSON | Schema | Patch | Hidden | Avg Latency ms | Tokens/Fix | Route Notes |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `xai` | `clean_candidate_cost_incomplete` | 10 | 10 | 5 | 5 | 0.6757 | 0.50 | 100% | 100% | 100% | 50% | 42938.59 | 3608.5 | Grok coding route produced the strongest hidden-clean result so far; cost data missing. |
| 2 | `ovhcloud` | `candidate_patch_provider` | 10 | 10 | 5 | 5 | 0.6632 | 0.50 | 100% | 100% | 100% | 20% | 14023.829 | 4825.0 | Corrected HF Inference Providers router route. |
| 3 | `puter_deepseek` | `candidate_patch_provider_high_latency` | 10 | 10 | 4 | 6 | 0.6191 | 0.60 | 90% | 90% | 90% | 20% | 13101.99 | n/a | Best free-route result; route is viable but slow and had one read timeout. |
| 4 | `cohere` | `candidate_patch_provider` | 10 | 10 | 4 | 6 | 0.6140 | 0.60 | 100% | 100% | 100% | 0% | 6688.51 | 4907.0 | Strong direct OpenAI-compatible route. |
| 5 | `deepinfra` | `candidate_patch_provider_high_latency` | 10 | 10 | 4 | 6 | 0.6120 | 0.60 | 100% | 100% | 100% | 20% | 32795.397 | 4969.75 | Strong compliance and hidden signal, but very high latency. |
| 6 | `huggingface` | `rescue_backed_action_ir` | 10 | 10 | 3 | 7 | 0.5830 | 0.70 | 100% | 100% | 100% | 0% | 1634.487 | 4947.667 | Fast and compliant, still mostly rescued. |
| 7 | `nscale` | `rescue_backed_action_ir` | 10 | 10 | 3 | 7 | 0.5810 | 0.70 | 100% | 100% | 100% | 0% | 7833.737 | 4200.0 | Corrected HF-router run; earlier direct route excluded from ranking. |
| 8 | `mistral` | `rescue_backed_codestral_candidate` | 10 | 10 | 2 | 8 | 0.5447 | 0.80 | 100% | 100% | 100% | 0% | 4115.814 | 5251.5 | Codestral route is compliant and worth keeping. |
| 9 | `openrouter` | `fast_rescue_backed_action_ir` | 10 | 10 | 2 | 8 | 0.5440 | 0.80 | 100% | 100% | 100% | 0% | 3769.288 | 5489.5 | Good schema compliance, mostly BEAST-rescued. |
| 10 | `sambanova` | `fast_rescue_backed_action_ir` | 10 | 10 | 1 | 9 | 0.5117 | 0.90 | 100% | 100% | 100% | 0% | 2982.269 | 5003.0 | Direct SambaNova Cloud route; fast and compliant, low clean count. |
| 11 | `novita` | `low_clean_rescue_candidate` | 10 | 10 | 1 | 9 | 0.5098 | 0.90 | 100% | 100% | 100% | 0% | 4313.806 | 5184.0 | Direct route works, but clean success remains low. |
| 12 | `cloudflare` | `edge_microtask_or_rescue_backed_action_ir` | 10 | 10 | 1 | 9 | 0.4826 | 0.90 | 100% | 90% | 90% | 0% | 2052.423 | 4959.0 | Fastest new route; likely scout/microtask role first. |
| 13 | `featherless` | `semantic_transform_selector_candidate` | 10 | 10 | 2 | 8 | 0.4221 | 0.80 | 60% | 60% | 60% | 0% | 7149.405 | 5275.0 | Moderate compliance, rescue-heavy. |
| 14 | `nvidia_nim` | `refs_only_transform_selector` | 2 | 2 | 0 | 2 | 0.4000 | 1.00 | 50% | 50% | 50% | 0% | n/a | Targeted 2-task NIM run; still no clean NIM result. |
| 15 | `cerebras` | `fast_semantic_transform_selector` | 10 | 10 | 2 | 8 | 0.3966 | 0.80 | 50% | 50% | 50% | 0% | 1265.566 | 5359.0 | Very fast, but governed-output validity inconsistent. |
| 16 | `aion_labs` | `rate_limited_rescue_candidate` | 10 | 10 | 1 | 9 | 0.3895 | 0.90 | 60% | 60% | 60% | 0% | 5278.112 | 5071.0 | Hit `429` rate limits mid-run; needs pacing/backoff before fair ranking. |
| 17 | `gemini` | `rescue_backed_action_ir_experimental` | 10 | 10 | 1 | 9 | 0.3330 | 0.90 | 40% | 40% | 40% | 0% | 5435.765 | 4196.0 | Routed correctly, weak clean success in this profile. |
| 18 | `groq` | `scout_or_microtask_only` | 10 | 10 | 0 | 10 | 0.2300 | 1.00 | 20% | 10% | 10% | 0% | n/a | Very fast in smoke-style work but weak Action IR compliance. |
| 19 | `llm7` | `scout_only_until_hash_contract_fixed` | 10 | 10 | 0 | 10 | 0.2300 | 1.00 | 100% | 10% | 10% | 0% | n/a | Repeated handoff-hash/schema failures; BEAST rescue carried completion. |
| 20 | `replicate` | `route_degraded_exclude_cost_rank` | 10 | 10 | 0 | 10 | 0.2000 | 1.00 | 0% | 0% | 0% | 0% | n/a | Direct OpenAI-compatible call 404ed; native prediction smoke reached Replicate but returned `402 Payment Required`. |
| 21 | `hyperbolic` | `do_not_use_until_billing_fixed` | 10 | 10 | 0 | 10 | 0.2000 | n/a | 0% | 0% | 0% | 0% | n/a | Direct route returned payment errors; not a fair capability read. |
| 22 | `fal` | `do_not_use_until_auth_fixed` | 10 | 10 | 0 | 10 | 0.2000 | n/a | 0% | 0% | 0% | 0% | n/a | Auth failed in this run; not a fair capability read. |

## What Changed With The Free-Route Batch

The new batch added six routes: `sambanova`, `mistral`, `cloudflare`, `llm7`, `aion_labs`, and `puter_deepseek`.

The important new finding is that Puter-routed DeepSeek is not just a workaround for direct DeepSeek billing. It is a legitimately competitive route under BEAST output governance: 4 clean completions, 90% JSON/schema/patch rates, and 20% hidden-test pass. The penalty is latency and one timeout, so it should be routed behind latency policy rather than blindly promoted.

Mistral Codestral is the cleanest code-focused addition. It produced valid governed outputs on every task, but still needed BEAST repair on 8/10 tasks. That makes it valuable as a rescue-backed coding route and a good target for provider-specific output profiles.

SambaNova and Cloudflare are fast, compliant, and rescue-heavy. SambaNova looks like a good Action IR route if a better model/profile is selected. Cloudflare is especially interesting for edge/scout/microtask use because it was quick and cheap-looking operationally, even though the clean pass rate was only 1/10.

Aion Labs and LLM7 both proved BEAST resilience more than provider readiness. Aion hit rate limits; LLM7 repeatedly failed the handoff-hash/schema contract. They should remain experimental routes until paced and contract-hardened.

## What Changed With The xAI / Replicate Batch

The xAI route materially changes the top of the table. `xai` using `grok-build-0.1` completed all 10 tasks, produced 5 clean provider fixes, and passed hidden tests cleanly on 5/10 tasks. That is the strongest hidden-clean signal in the current provider map. The caution is cost: the run did not include first-party USD observations, so xAI is currently `clean_candidate_cost_incomplete`, not yet cost-ranked.

Replicate should not be judged as a model failure from the original combined run. The direct route returned `404 Not Found` on `https://api.replicate.com/v1/chat/completions` for every task. A follow-up native prediction smoke fixed the route shape by calling `POST /v1/models/{owner}/{model}/predictions`, but the selected account/model returned `402 Payment Required`. So the next blocker is not schema or BEAST integration; it is Replicate access/billing or selecting a runnable model for the token.

## Hidden Test Read

The hidden-test result is still the most skeptical signal in the original combined matrix.

Only three routes reached `20%` hidden-test pass:

- `ovhcloud`
- `deepinfra`
- `puter_deepseek`
- `xai`

Most routes remain at `0%`, even when they achieved 100% BEAST completion. That means the evidence strongly supports BEAST as a governed completion and rescue system, but it does not yet prove broad unseen-code generalization for most providers.

That gap has now been addressed in the follow-up `beast_systems_benchmark_live_cost_hidden_10task` run. The expanded benchmark surface now gives every task class a hidden test, reports `Visible Clean` and `Hidden Clean` separately, and exposes hidden coverage in the headline provider table. The clean hidden rates are still modest, but the denominator is no longer sparse or hidden.

Focused hidden-coverage result:

| Provider Route | Hidden Coverage | Visible Clean | Hidden Clean | BEAST Pass |
| --- | ---: | ---: | ---: | ---: |
| `openrouter_qwen_coder` | 10/10 | 2/10 | 2/10 | 10/10 |
| `openrouter_gptoss` | 10/10 | 2/10 | 2/10 | 10/10 |
| `openrouter_deepseek` | 10/10 | 1/10 | 1/10 | 10/10 |
| `openrouter` | 10/10 | 0/10 | 0/10 | 10/10 |
| `deepinfra` | 10/10 | 0/10 | 0/10 | 10/10 |
| `xai` | 10/10 | 5/10 | 5/10 | 10/10 |

## Runtime Routing Tiers

### Patch Provider Candidates

These routes have the strongest combination of clean passes, governed-output validity, and hidden-test signal:

- `ovhcloud`
- `xai`
- `puter_deepseek`
- `cohere`
- `deepinfra`

They are not interchangeable. `ovhcloud` has the highest clean count, `puter_deepseek` has strong free-route performance but high latency, `cohere` is a stable direct route, and `deepinfra` is capable but very slow.

### Rescue-Backed Action IR Routes

These routes are useful when BEAST remains in control of resolving, compiling, repairing, and verifying:

- `huggingface`
- `nscale`
- `mistral`
- `openrouter`
- `sambanova`
- `novita`
- `cloudflare`

This tier is where BEAST’s mirror architecture matters most: providers provide intent, BEAST governs the local action.

### Semantic Selector / Scout Routes

These routes should not be trusted to author patches yet, but may still be useful for triage, micro-intent, semantic transform selection, or fast analysis:

- `cloudflare`
- `cerebras`
- `featherless`
- `groq`
- `llm7`
- `nvidia_nim`

For NIM specifically, the right target remains refs-only Action IR / transform selection until clean NIM passes land.

### Route Invalid / Needs Fix

These routes should stay out of capability ranking until access or billing is resolved:

- `github_models`: endpoint accepts token, but model calls returned `403 no_access`.
- `replicate`: OpenAI-compatible call returned `404`; native prediction call reached `/v1/models/{owner}/{model}/predictions` but returned `402 Payment Required`.
- `deepseek`: direct API returned `402 Payment Required`; Puter DeepSeek is a separate viable route.
- `hyperbolic`: direct route returned payment errors.
- `fal`: route returned auth errors.

## Cost/Fix Status

Tokens/fix are available for most successful routes, but USD/fix is still not comparable across the full matrix. Most provider responses do not return first-party dollar cost, and several routes are free-credit, user-funded, router-mediated, or account-quota based.

The only current first-party observed USD/fix sample remains `deepinfra`, which returned `usage.estimated_cost` in the raw artifacts: approximately `$0.000332` per verified fix in that run.

The follow-up cost-focused run now proves the cost extraction path across OpenRouter-backed routes. OpenRouter calls request usage/cost data, and the harness extracts first-party cost from fields such as `usage.estimated_cost`, `usage.cost`, `usage.total_cost_usd`, and `usage.cost_details.upstream_inference_cost`.

Focused first-party USD/fix result:

| Provider Route | First-party USD / Verified Fix | Cost Observations | Clean | Hidden Clean | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `openrouter_gptoss` | `$0.000526580` | 10/10 | 2/10 | 2/10 | Lowest complete-cost route with clean hidden passes. |
| `openrouter` | `$0.000549700` | 10/10 | 0/10 | 0/10 | Cheap and fast, but rescue-backed only in this run. |
| `openrouter_deepseek` | `$0.001340760` | 9/10 | 1/10 | 1/10 | One direct route billing failure. |
| `openrouter_qwen_coder` | `$0.001671967` | 10/10 | 2/10 | 2/10 | Best focused score, higher cost. |
| `deepinfra` | `$0.000041299` | 1/10 | 0/10 | 0/10 | Cost-partial only; route hit `402 Payment Required` after one call. |

The next benchmark should still add pricing metadata for routes that do not return first-party dollar cost:

- `pricing_source`
- `price_timestamp`
- `input_usd_per_mtok`
- `output_usd_per_mtok`
- `clean_usd_per_fix`
- `rescued_usd_per_fix`
- `total_usd_per_verified_fix`
- `free_tier_eligible`
- `quota_or_credit_limited`

## Full All-Route Hidden-Cost Run

The follow-up `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost` run tested every configured route on the full BEAST lane:

- Provider routes: `25`
- Tasks per route: `10`
- BEAST completions: `250/250`
- Clean provider completions: `9/250`
- BEAST-rescued completions: `241/250`
- Hidden coverage: `10/10` tasks per route

The run adds the BEAST router economics fields:

- `Hidden Clean USD/Fix`
- `Hidden Clean / USD`
- `Rescue Rate`
- `Clean:Rescue`
- `Cost Coverage`
- `Recommended Role`
- `Route Confidence`

The broad result is intentionally conservative: BEAST completed everything, but only `cohere`, `mistral`, `openrouter`, `gemini`, and `puter_deepseek` produced any clean hidden passes. `openrouter` was the only route with observed first-party hidden-clean USD/fix in this all-route run, but cost coverage was only `40%` and the route later degraded with billing errors, so it is not eligible for definitive cost ranking from this run.

Source: `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost_summary.md`.

## Bottom Line

The combined matrix gives BEAST a real routing policy surface:

- Use `ovhcloud`, `puter_deepseek`, `cohere`, and `deepinfra` as candidate patch-provider lanes.
- Promote `xai` into the candidate patch-provider set, but keep it out of cost rankings until first-party USD/fix is observed.
- Use `huggingface`, `nscale`, `mistral`, `openrouter`, `sambanova`, `novita`, and `cloudflare` as rescue-backed Action IR lanes.
- Use `cloudflare`, `cerebras`, `groq`, `llm7`, and `nvidia_nim` for scout, microtask, semantic selection, or refs-only roles until clean patch reliability improves.
- Keep billing/auth-invalid routes out of provider capability rankings.

The strongest overall evidence remains this: BEAST completed every evaluated live task across a large and messy provider surface, while the fitness scores stayed honest about which providers were actually patch-ready and which were merely rescue-useful.

## Source Reports

- `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost.json`
- `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost.md`
- `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost_summary.md`
- `beast_systems_benchmark_live_cost_hidden_10task.json`
- `beast_systems_benchmark_live_cost_hidden_10task.md`
- `beast_systems_benchmark_live_cost_hidden_10task_summary.md`
- `beast_systems_benchmark_live_free_routes_10task.json`
- `beast_systems_benchmark_live_free_routes_10task.md`
- `beast_systems_benchmark_live_free_routes_10task_summary.md`
- `beast_systems_benchmark_live_xai_replicate_10task.json`
- `beast_systems_benchmark_live_xai_replicate_10task.md`
- `beast_systems_benchmark_live_replicate_native_smoke.json`
- `beast_systems_benchmark_live_replicate_native_smoke.md`
- `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`
- `beast_systems_benchmark_live_expanded_nvidia_repair_targeted.json`
- `beast_systems_benchmark_live_expanded_openrouter_hf_repaired.json`
- `beast_systems_benchmark_live_groq_gemini_10task.json`
- `beast_systems_benchmark_live_hyperbolic_fal_novita_10task.json`
- `beast_systems_benchmark_live_nscale_ovhcloud_cohere_10task.json`
- `beast_systems_benchmark_live_nscale_ovhcloud_hfrouter_10task.json`
