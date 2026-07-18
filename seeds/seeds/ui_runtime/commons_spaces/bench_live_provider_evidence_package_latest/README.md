# Live Provider Evidence Package

This package contains the consolidated evidence bundle for the latest BEAST live provider benchmark runs.

## Contents

- `summary/`: consolidated provider-fitness summary.
- `reports/`: source JSON and Markdown reports for each included live run.
- `gauntlet/`: Gauntlet-shaped artifacts from each run, including provider fitness, task results, failure buckets, cost/latency summaries, evidence cards, patches, and rollback snapshots where present.
- `tests/`: focused tests that cover the benchmark harness and output-governance bridge.
- `code/`: benchmark and BEAST output-governance/sourceplan bridge code used to produce or enforce the evidence.
- `MANIFEST.txt`: complete file list for the package.

## Scope

Included provider runs:

- OpenRouter and HuggingFace repaired expanded run.
- NVIDIA NIM targeted repair run.
- Hyperbolic, FAL, and Novita 10-task run.
- Cohere run from the Nscale/OVHCloud/Cohere batch.
- Corrected Nscale and OVHCloud Hugging Face router run.
- Cerebras, DeepInfra, and Featherless Hugging Face router run.
- Groq and Gemini 10-task run.
- Free/low-cost route run: SambaNova, Mistral, Cloudflare, LLM7, Aion Labs, and Puter-routed DeepSeek.
- Focused hidden-coverage and first-party cost run: OpenRouter route variants and DeepInfra.
- Full all-route BEAST run with hidden-clean economics: 25 provider routes, all 10 tasks, full BEAST lane.

## Hidden Tests

Hidden tests are local benchmark tests that were not included in the provider-visible handoff. They approximate unseen-code behavior: a provider can pass the visible failure while still failing hidden behavior that a real codebase would care about.

The consolidated summary preserves hidden-test pass rates because they are an important skepticism check. In the original broad matrix, hidden pass rates were low across the board, so that part of the evidence package should be read as strong proof of BEAST-governed completion and rescue behavior, not yet as final proof of broad unseen-code generalization.

The focused `beast_systems_benchmark_live_cost_hidden_10task` run addresses the measurement weakness: all 10 expanded task classes now include hidden tests, and provider summaries report visible-clean and hidden-clean counts separately. Clean hidden rates are still modest, but hidden coverage is no longer sparse.

The full `beast_systems_benchmark_live_all_routes_full_beast_hidden_cost` run applies that hidden coverage to every configured provider route. It should be read as the broad route-policy evidence surface: BEAST completed every task, while clean hidden passes remained sparse and provider-specific.

## Cost/Fix

The package includes `Tokens/Fix` for comparable throughput analysis. Uniform `USD/Fix` is not yet available across every provider because many routes do not return dollar cost in their live responses and pricing depends on provider, model, route, and free-tier policy.

The current raw artifacts include one observed dollar-cost sample: DeepInfra returned `usage.estimated_cost` for 10/10 calls in `beast_systems_benchmark_live_cerebras_deepinfra_featherless_hfrouter_10task.json`, totaling `$0.003318228`, or about `$0.000332` per verified fix.

The focused cost run adds first-party cost extraction for OpenRouter-backed routes. It produced complete or near-complete first-party USD/fix rows for `openrouter`, `openrouter_gptoss`, `openrouter_qwen_coder`, and `openrouter_deepseek`. DeepInfra also returned one first-party cost observation in that focused run, but then hit `402 Payment Required`, so that row is marked partial and should not be cost-ranked.

The all-route run adds the runtime-economics fields used by the BEAST router:

- `Hidden Clean USD/Fix`
- `Hidden Clean / USD`
- `Rescue Rate`
- `Clean:Rescue`
- `Cost Coverage`
- `Recommended Role`
- `Route Confidence`

Routes with incomplete cost observations or billing/auth/quota failures are excluded from definitive cost ranking.

Future evidence packages should add a timestamped pricing table for providers that do not return first-party cost, and report `clean_usd_per_fix`, `rescued_usd_per_fix`, and total `usd_per_verified_fix`.

Secrets are intentionally excluded.
