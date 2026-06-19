# Consolidated Live Provider Benchmark Summary

Generated: `2026-06-19T06:47:49Z`

This report consolidates the latest live BEAST provider-fitness runs. It uses the corrected HF-router reruns for Nscale and OVHCloud, and excludes their earlier direct-route failures from the ranked table.

## Executive Summary

- Providers summarized: `14`
- Total evaluated tasks: `132`
- BEAST end-to-end completions: `132/132`
- Clean provider completions: `27/132`
- BEAST-rescued completions: `105/132`

The main result is not that every provider is independently source-patching ready. The result is that BEAST completed every evaluated task while exposing which providers actually produced valid governed patches and which ones needed local verifier repair.

## Score Definitions

- **Provider Fitness Score** measures how good the provider is by itself: clean verified success, valid JSON/schema, patch application, hidden-test behavior, scope safety, latency, cost, and rollback cleanliness.
- **BEAST Rescue Score** measures how often BEAST extracted a verified fix after the provider output needed rescue. It is useful for routing imperfect but valuable providers behind stricter reins. Infra-invalid routes are marked `n/a` because BEAST rescue there proves system recovery, not provider usefulness.
- **Role Recommendation** is the runtime-routing suggestion: BEAST should choose a provider by role, task class, output contract, and cost envelope, not by a generic model leaderboard.

## Ranked Provider Fitness

| Rank | Provider | Role Recommendation | Tasks | BEAST Pass | Clean | Rescued | Provider Fitness Score | BEAST Rescue Score | JSON | Schema | Patch | Hidden | Avg Latency ms | Tokens/Fix |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `ovhcloud` | `candidate_patch_provider` | 10 | 10 | 5 | 5 | 0.663 | 0.50 | 100% | 100% | 100% | 20% | 12919.0 | 4562.6 |
| 2 | `cohere` | `candidate_patch_provider` | 10 | 10 | 4 | 6 | 0.614 | 0.60 | 100% | 100% | 100% | 0% | 5767.5 | 4518.5 |
| 3 | `deepinfra` | `candidate_patch_provider_high_latency` | 10 | 10 | 4 | 6 | 0.612 | 0.60 | 100% | 100% | 100% | 20% | 27428.9 | 4267.5 |
| 4 | `huggingface` | `rescue_backed_action_ir` | 10 | 10 | 3 | 7 | 0.583 | 0.70 | 100% | 100% | 100% | 0% | 1641.1 | 4527.4 |
| 5 | `nscale` | `rescue_backed_action_ir` | 10 | 10 | 3 | 7 | 0.581 | 0.70 | 100% | 100% | 100% | 0% | 9574.7 | 4343.5 |
| 6 | `openrouter` | `fast_rescue_backed_action_ir` | 10 | 10 | 2 | 8 | 0.544 | 0.80 | 100% | 100% | 100% | 0% | 2703.1 | 4483.8 |
| 7 | `novita` | `low_clean_rescue_candidate` | 10 | 10 | 1 | 9 | 0.510 | 0.90 | 100% | 100% | 100% | 0% | 2638.2 | 3533.0 |
| 8 | `featherless` | `semantic_transform_selector_candidate` | 10 | 10 | 2 | 8 | 0.422 | 0.80 | 60% | 60% | 60% | 0% | 5419.4 | 2468.9 |
| 9 | `nvidia_nim` | `refs_only_transform_selector` | 2 | 2 | 0 | 2 | 0.400 | 1.00 | 50% | 50% | 50% | 0% | 66795.6 | 5350.5 |
| 10 | `cerebras` | `fast_semantic_transform_selector` | 10 | 10 | 2 | 8 | 0.397 | 0.80 | 50% | 50% | 50% | 0% | 1396.4 | 3245.4 |
| 11 | `gemini` | `rescue_backed_action_ir_experimental` | 10 | 10 | 1 | 9 | 0.333 | 0.90 | 40% | 40% | 40% | 0% | 7611.8 | 3217.3 |
| 12 | `groq` | `scout_or_microtask_only` | 10 | 10 | 0 | 10 | 0.230 | 1.00 | 20% | 10% | 10% | 0% | 1202.8 | 740.2 |
| 13 | `hyperbolic` | `do_not_use_until_billing_fixed` | 10 | 10 | 0 | 10 | 0.200 | n/a | 0% | 0% | 0% | 0% | n/a | n/a |
| 14 | `fal` | `do_not_use_until_auth_fixed` | 10 | 10 | 0 | 10 | 0.200 | n/a | 0% | 0% | 0% | 0% | n/a | n/a |

## Hidden Test Interpretation

Hidden tests are benchmark tests that exist in the local task workspace but are not shown in the provider-visible handoff. They are the closest signal in this package to "does this patch generalize beyond the prompt?" rather than "can the provider satisfy the visible failure?"

The current hidden-test pass rate is intentionally sobering: OVHCloud and DeepInfra lead at 20%, while most providers are at 0%. That does not invalidate the 132/132 BEAST completion result, but it does mean the present live matrix proves governed completion and rescue reliability more strongly than unseen-code generalization. A skeptical reader should treat hidden pass rate as the next benchmark frontier.

The next live surface should include more hidden checks per task class, especially for multi-file fixes, async streaming bugs, rollback behavior, provider config, and NIM refs-only contracts. A provider should not graduate to `primary_patch_provider` on clean visible tests alone.

## Cost/Fix Status

This report has `Tokens/Fix` for every provider with successful live calls, but it does not yet have uniform `USD/Fix`. Provider and router responses do not consistently return dollar cost, and comparable USD/fix requires a timestamped pricing table per provider, model, route, and free-tier policy.

| Provider | Observed USD/Fix | Basis | Notes |
| --- | ---: | --- | --- |
| `deepinfra` | `$0.000332` | Provider/router returned `usage.estimated_cost` for 10/10 calls | Only current run with first-party cost estimates in the raw artifacts. |
| All others | n/a | Token usage captured, pricing not normalized | Needs pricing table and clean/rescued cost split before platform-engineering decisions. |

Recommended formula for the next benchmark:

`usd_per_verified_fix = (input_tokens / 1_000_000 * input_usd_per_mtok + output_tokens / 1_000_000 * output_usd_per_mtok + repair_call_usd) / verified_fixes`

The useful operational split is `clean_usd_per_fix` versus `rescued_usd_per_fix`, because BEAST-rescued providers may still be economical if they are cheap or fast enough and the local repair path is reliable.

## Runtime Router Policy

The next BEAST router should not select a generic "best model." It should select the best provider for the requested role, task class, output contract, and cost envelope.

Recommended role classes:

- `primary_patch_provider`: providers that can directly produce valid governed patches for the current task class.
- `rescued_patch_provider`: providers that often need local verifier repair but still produce useful Action IR or scoped patch attempts.
- `refs_only_action_ir_generator`: providers that should return refs-only intent and let BEAST resolve/compile locally.
- `semantic_transform_selector`: providers that are useful for choosing the local transform, anchor, or edit strategy, but not trusted to author patches.
- `scout_only`: providers useful for fast analysis, triage, summarization, or micro-intent, not patch writing.
- `route_invalid`: providers whose route, model, quota, or token is not currently usable.
- `do_not_use_until_auth_fixed`: providers blocked by auth/billing and excluded from capability routing.

## Provider Notes

- **ovhcloud**: Corrected HF-router run; best clean count and best score in the current set. Route: HF Inference Providers router (`openai/gpt-oss-120b:ovhcloud`). Source: `beast_systems_benchmark_live_nscale_ovhcloud_hfrouter_10task.json`.
- **cohere**: Strong middle-tier result: 4 clean passes, valid JSON/schema/patches. Route: Cohere OpenAI compatibility API. Source: `beast_systems_benchmark_live_nscale_ovhcloud_cohere_10task.json`.
- **deepinfra**: Strong clean count and compliance, but high latency. Route: HF Inference Providers router (`openai/gpt-oss-120b:deepinfra`). Source: `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`.
- **huggingface**: Solid governed output compliance; still mostly rescued. Route: HF Router direct provider preset (`openai/gpt-oss-120b`). Source: `beast_systems_benchmark_live_expanded_openrouter_hf_repaired.json`.
- **nscale**: Corrected HF-router run replaced earlier direct 429 run; viable but rescue-heavy. Route: HF Inference Providers router (`openai/gpt-oss-120b:nscale`). Source: `beast_systems_benchmark_live_nscale_ovhcloud_hfrouter_10task.json`.
- **openrouter**: Good schema compliance, but mostly BEAST-rescued; not yet provider-fit. Route: OpenRouter direct API (`openrouter/auto`). Source: `beast_systems_benchmark_live_expanded_openrouter_hf_repaired.json`.
- **novita**: Direct route worked and produced valid governed patches, but clean success was low. Route: Novita direct OpenAI-compatible API. Source: `beast_systems_benchmark_live_hyperbolic_fal_novita_10task.json`.
- **featherless**: Correct suffix is `featherless-ai`; moderate compliance, rescue-heavy. Route: HF Inference Providers router (`openai/gpt-oss-120b:featherless-ai`). Source: `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`.
- **nvidia_nim**: Only 2 targeted tasks; all completed by BEAST rescue, no clean passes. Route: NVIDIA NIM direct API; targeted 2-task refs-only run. Source: `beast_systems_benchmark_live_expanded_nvidia_repair_targeted.json`.
- **cerebras**: Very fast, but JSON/schema/patch validity was only 50%; some payment errors. Route: HF Inference Providers router (`openai/gpt-oss-120b:cerebras`). Source: `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`.
- **gemini**: Routed correctly through Google OpenAI-compatible endpoint, but weak clean success. Route: Google Gemini OpenAI-compatible endpoint (`gemini-2.5-flash`). Source: `beast_systems_benchmark_live_groq_gemini_10task.json`.
- **groq**: Very fast, but weak Action IR compliance and payload/rate-limit problems. Route: Groq direct OpenAI-compatible API; HF suffix probe failed. Source: `beast_systems_benchmark_live_groq_gemini_10task.json`.
- **hyperbolic**: Direct route returned 402 Payment Required; completions are BEAST rescue only. Route: Direct Hyperbolic API; route failed with payment errors. Source: `beast_systems_benchmark_live_hyperbolic_fal_novita_10task.json`.
- **fal**: Route returned 401 Unauthorized; completions are BEAST rescue only. Route: FAL/OpenRouter route; auth failed in this run. Source: `beast_systems_benchmark_live_hyperbolic_fal_novita_10task.json`.

## What Happened

1. **OVHCloud was the best clean source-patching candidate in this set.** Once routed through Hugging Face Inference Providers, it reached 5 clean passes out of 10, JSON/schema/patch validity of 100%, and the top fitness score.
2. **Cohere, DeepInfra, HuggingFace, and Nscale formed the viable middle tier.** They produced valid governed output reliably, but still needed BEAST rescue on most tasks.
3. **OpenRouter and Novita were usable but rescue-heavy.** They can participate in BEAST, but the provider alone did not yet carry many fixes cleanly.
4. **Cerebras and Featherless were fast enough to be interesting, but their governed-output validity was inconsistent.** They need tighter output profiles or different model choices before they are source-patching candidates.
5. **Groq was extremely fast but not patch-fit in this configuration.** It hit payload/rate-limit issues and produced weak Action IR compliance.
6. **Gemini routed correctly but had low clean success.** It may need a different output contract, model, or prompt profile.
7. **Hyperbolic and FAL did not get a fair capability read.** Their failures were route/payment/auth issues, so the BEAST completions there mainly prove recovery behavior, not provider coding ability.
8. **NIM remains a special case.** The targeted run proved BEAST can recover and complete refs-only tasks, but no clean NIM result has landed yet.

## Interpretation

The benchmark now separates four facts that used to blur together:

- **System reliability:** BEAST completed every task in these latest runs.
- **Provider fitness:** only a subset of providers generated valid, passing patches without rescue.
- **Rescue value:** some weak providers are still useful when BEAST applies stricter reins, local compilation, and verifier repair.
- **Route correctness:** several apparent provider failures were actually wrong route, auth, quota, or billing lane issues.

The strongest practical signal is that output governance is doing useful work: invalid or incomplete provider patches are not blindly trusted. BEAST can reject, repair, and verify locally, while the provider-fitness score remains honest about whether the provider itself deserves source-patching responsibility.

## Recommended Next Moves

- Promote `ovhcloud`, `deepinfra`, `cohere`, `huggingface`, and corrected `nscale` into the next comparison set.
- Implement a role-aware provider router that consumes `Role Recommendation`, `Provider Fitness Score`, and `BEAST Rescue Score`.
- Rerun top providers on a larger surface with repeats, because 10 tasks is enough for signal but not enough for stable ranking.
- Add provider-specific output profiles for fast-but-flaky routes like Cerebras, Featherless, Groq, and Gemini.
- Treat Groq-like providers as `scout_or_microtask_only` unless a smaller output contract proves clean patch reliability.
- Treat NIM-like providers as `refs_only_transform_selector` until clean refs-only Action IR passes land.
- Keep infra failures out of provider capability rankings unless the correct route and token type are confirmed.
- Run a direct BEAST-vs-non-BEAST comparison for the top five providers only, where provider cost and latency are measured on identical tasks.
- Expand hidden-test coverage and report visible-test pass rate separately from hidden-test pass rate.
- Add timestamped model pricing metadata and report `clean_usd_per_fix`, `rescued_usd_per_fix`, and `total_usd_per_verified_fix`.

## Source Reports

- `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`
- `beast_systems_benchmark_live_expanded_nvidia_repair_targeted.json`
- `beast_systems_benchmark_live_expanded_openrouter_hf_repaired.json`
- `beast_systems_benchmark_live_groq_gemini_10task.json`
- `beast_systems_benchmark_live_hyperbolic_fal_novita_10task.json`
- `beast_systems_benchmark_live_nscale_ovhcloud_cohere_10task.json`
- `beast_systems_benchmark_live_nscale_ovhcloud_hfrouter_10task.json`
