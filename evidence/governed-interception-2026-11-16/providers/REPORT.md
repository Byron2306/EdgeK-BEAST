# Direct-provider lanes: Fireworks, SambaNova, Hyperbolic, Replicate, fal (2026-11-16, 09:20-09:45 SAST)

Keys were checked **by name only** in `.beast/provider_secrets.env`: FIREWORKS_API_KEY, HYPERBOLIC_API_KEY, REPLICATE_API_TOKEN, SAMBANOVA_API_KEY and FAL_KEY are all present. Their values were never printed.

## What was added (default-off; under BEAST_GOVERNED_INTERCEPTION / BEAST_CAPABILITY_ROUTER)
- `app/kernel/compute/provider_lanes.json` holds the lane data.
  - `governed_client.provider_lane_candidates()` turns it into candidates. A provider only appears when its key exists in the env or the dotenv file.
  - Static order: fireworks, sambanova, hyperbolic, replicate, then fal_llm last (fal_llm is a low-priority proxy lane).
  - These lanes are appended to `default_candidates()`.
- **OpenAI-compatible lanes:**
  - Fireworks: `https://api.fireworks.ai/inference/v1`
  - SambaNova: `https://api.sambanova.ai/v1`
  - Hyperbolic: `https://api.hyperbolic.ai/inference/v1`. The old `api.hyperbolic.xyz/v1` is decommissioned and returns 404.
  - fal LLM proxy: `https://fal.run/openrouter/router/openai/v1`, with the new `Candidate.auth_scheme="Key"`.
- **Replicate adapter:** `kind="replicate"`, `_call_replicate`.
  - Calls `POST /v1/models/{owner}/{name}/predictions` with `Prefer: wait=60` and polls `urls.get` if the prediction is still running.
  - JSON is enforced by prompt + gate validation + one repair retry (dialect `prompt_validate_retry:attempts=N`).
  - **No native JSON or grammar option exists**: the openapi_schema inputs of all 3 models are only prompt / max_tokens / temperature / top_p / penalties (deepseek also has `thinking`).
- **fal media lane:** `app/kernel/compute/media_lanes.py` (`FalMediaLane`).
  - Uses the queue API `https://queue.fal.run/{model}`, auth `Key $FAL_KEY`.
  - Off unless `BEAST_MEDIA_LANES=1`, and never touches the coding scorecard.
- **Client fixes:**
  - A thinking-only model's rejection ("thinking … not supported") now strips the thinking knobs and retries the same dialect.
  - Replicate http/transport errors record no tokens or spend.
- **Scorecard fixes:**
  - `smoke*` liveness probes no longer feed the cross-family `*` aggregate.
  - The exploration bonus is capped at `explore_c`, so 30+ unseen paid lanes can't outrank cells with real evidence.
  - The canonical scorecard was rebuilt by replaying every proof call: `scripts/governed_scorecard_replay.py`, 212 calls, 113 cells. The pre-replay copy is kept in `.beast/governed-interception/`.

## Live model listings (`/models`, no keys printed)
- **Fireworks:** 31 models (`fireworks-models.json`). Picked:
  - kimi-k3 ($3 / $15)
  - deepseek-v4p1-flash ($0.30 / $1.20)
  - gpt-oss-120b ($0.15 / $0.60)
  - glm-5p3-flash ($0.15 / $0.50)
  - Prices are per Mtok from fireworks.ai/pricing.
- **SambaNova:** 5 models (`sambanova-models.json`). Picked:
  - gpt-oss-120b ($0.22 / $0.59)
  - MiniMax-M3.1-Flash ($0.30 / $1.20)
  - Meta-Llama-3.3-70B ($0.60 / $1.20)
  - GLM-5.3 ($2.80 / $8.80) was skipped as too expensive.
- **Hyperbolic:** `/models` returns **403 `inference_requires_verified_phone`** (Free Tier account). Configured the documented Flux models: glm-5.3-flash, kimi-k3, glm-5.3. Their prices are unverified upper bounds.
- **Replicate:** language-models collection (`replicate-language-models.json`). Picked:
  - openai/gpt-oss-120b ($0.18 / $0.72 from its model page)
  - deepseek-ai/deepseek-v3.1 (price not public, $1 / $3 assumed)
  - qwen/qwen3-235b-a22b-instruct-2507 (price not public, $1 / $3 assumed)
- **fal:** the any-llm enum lists OpenRouter models. The proxy lane uses `openai/gpt-oss-120b`.

## Smoke results (1 tiny schema-forced call per route, max_tokens ≤ 512)
| Provider | Route | Result | JSON mode that worked | TTFT ms | Latency ms | Tokens in / out | Spend |
|---|---|---|---|---|---|---|---|
| Fireworks | kimi-k3 | ok, valid, correct | json_schema | 3934 | 4312 | 43 / 22 (est.) | $0.000459 |
| Fireworks | deepseek-v4p1-flash | ok | json_schema | 1467 | 1788 | 43 / 24 | $0.000042 |
| Fireworks | gpt-oss-120b | ok | json_schema | 1990 | 2364 | 43 / 26 | $0.000022 |
| Fireworks | glm-5p3-flash | first run 400 (thinking-only rejects thinking-off); **ok after fix** | json_schema | 1301 | 1392 | 43 / 24 | $0.000018 |
| SambaNova | gpt-oss-120b | 502 upstream error | not determined | - | - | - | $0 |
| SambaNova | MiniMax-M3.1-Flash | **402 PAYMENT_METHOD_REQUIRED** (balance 0) | not determined | - | - | - | $0 |
| SambaNova | Llama-3.3-70B | **402 PAYMENT_METHOD_REQUIRED** | not determined | - | - | - | $0 |
| Hyperbolic | glm-5.3-flash / kimi-k3 / glm-5.3 | **403 inference_requires_verified_phone** | not determined | - | - | - | $0 |
| Replicate | gpt-oss-120b / deepseek-v3.1 | **402 insufficient credit** | prompt + validate + retry (no native mode) | - | - | - | $0* |
| Replicate | qwen3-235b | 429 (throttled at 6/min for no-credit accounts) | same | - | - | - | $0* |
| fal (LLM proxy) | openai/gpt-oss-120b | **403 user locked: exhausted balance** | not determined | - | - | - | $0 |
| fal (media) | fal-ai/flux/schnell 512² | **403 exhausted balance** (est. $0.0008 had it run) | n/a | - | 1292 | - | $0 |

*The Replicate rows in `provider-smoke-*.json` show $0.000355 in total of phantom "spend": prompt tokens times price, recorded before the no-spend-on-error fix. Nothing ran, and Replicate bills nothing for 402/429.

**JSON mode per provider:**
- Fireworks: `response_format json_schema` was accepted for all 4 models; json_object was never needed.
- Replicate: there is no native mode, so prompt + validate + retry is used.
- SambaNova, Hyperbolic, fal: untested, because the accounts are blocked by billing or verification.

## Hard set: same 13 tasks, solo, up to 2 attempts with test feedback
Each model ran alone, so this is an apples-to-apples comparison.

| Candidate | Accepted | 1st-attempt pass | Calls | JSON valid | p50 latency | Spend | Failed |
|---|---|---|---|---|---|---|---|
| HF Kimi-K2.7-Code:deepinfra | **13/13** | 10 | 16 | 16/16 | 6.6 s | $0.0126 | - |
| **Fireworks deepseek-v4p1-flash** | **12/13** | 8 | 18 | 18/18 | **2.0 s** | $0.0062 | far-1 |
| **Fireworks glm-5p3-flash** | **12/13** | 8 | 18 | 17/18 | 2.6 s | **$0.0037** | far-1 |
| HF gpt-oss-120b:deepinfra | 9/13 | 8 | 18 | 18/18 | 3.6 s | $0.0008 | ren-h1, ren-h2, refguard-h1, refguard-h2 |

- **Rename and refguard are now solved** by DeepSeek-V4.1-Flash and GLM-5.3-Flash on Fireworks. Every hidden check passed.
- Kimi solo did much better than when it sat at the end of the earlier chains (8/15 calls passed there). Provider-side variance and the chain's accumulated feedback turns are the likely reasons.
- far-1 fails only on the two new models.

## Scorecard and ranking (after replay)
Top of `rank()` over all default candidates (`scorecard_ranking.json`):

| Family | Ranking |
|---|---|
| refactor-rename-symbol | Fireworks deepseek-v4p1-flash 0.705 > Fireworks glm-5p3-flash 0.621 > unproven lanes 0.59 |
| composite-refguard | glm-5p3-flash 0.736 > Kimi:deepinfra 0.643 > deepseek-v4p1-flash 0.636 |
| far | Kimi:deepinfra 0.823 > gpt-oss-120b:deepinfra 0.714 |
| fix-* / toolchain | gpt-oss-120b:deepinfra ≈ Kimi ≈ the Fireworks pair ≈ 0.81-0.92 |

Blocked lanes (SambaNova, Hyperbolic, Replicate, fal) each carry one `http_error` and sit below the evidence-backed lanes.

## Spend (this step)
- Fireworks smoke: **$0.00054**
- Hard set:
  - Fireworks: $0.0099
  - HF baseline: $0.0134
- **Total ≈ $0.0238**, under the $0.05 cap. Blocked providers cost $0, and fal media cost $0.

## Corrected earlier figures (exact, from the evidence files)
**TGI-first chain run** (`tgi/tgi-routed-20261116T090515.json`):
- 13 tasks, **40 model calls**: TGI 13, NIM 11, HF 16.
- Spend $0.010915.

**15-route HF smoke** (`tgi/hf-smoke-*.json`):
- First pass, 14 ok routes:
  - TTFT **487.2-4170.2 ms**: min DeepSeek-V4.1-Flash:baseten, max GLM-5.3-Flash:novita.
  - Latency **510.8-4623.8 ms**: min gpt-oss-120b:cerebras, max GLM-5.3-Flash:novita.
- Final 15 routes, including the Qwen3.8-27B:cerebras retry:
  - TTFT **469.0-4170.2 ms**.
  - Latency **480.6-4623.8 ms**.
- Spend: $0.000792 first pass + $0.00008 retry = **$0.000872**.

## Test results (2026-11-16, Africa/Johannesburg, UTC+2)
**Governed-interception suite** (live repo): `tests/test_governed_interception.py` + `tests/test_factory_stdout_clean.py` → **38 passed + 1 passed, 0 failed**.

**Full suite** (live repo, `full_suite_current.txt`): 2520 passed, 76 failed, 1 error, 6 skipped (23m50s). Breakdown of the non-passing items:
- `test_governed_interception.py::test_fal_media_lane_queue_flow_and_off_by_default`: a test-isolation bug where another test left `FAL_KEY` set in the env. Fixed with `monkeypatch.delenv`, and it now passes (it's included in the 38 above).
- `tests/test_equivalence_engine.py` ERROR: a pytest "import file mismatch" because it shares a basename with `tests/phase3/test_equivalence_engine.py`. It's a stale `__pycache__`/duplicate-basename collection problem. The file was last committed 2026-07-17, isn't touched by this work, and passes when run on its own in the baseline, current copy and live repo. **Preexisting, not a regression.**
- The other **75 failures** were re-run in two bounded copies (app/tests/scripts/etc., without .venv/.git/.beast/evidence/models):
  - `/tmp/gi-base`: the `.before-governed-interception-*` originals restored, and the new governed modules removed.
  - `/tmp/gi-cur`: the current code.

  Both ran with pytest `--timeout=120` and a 700 s cap. Both gave **75 failed**, and the failing-ID sets are **identical** (`diff` is empty). **All 75 are preexisting.** Logs: `regression_baseline_failing_ids.txt`, `regression_current_failing_ids.txt`, `regression_failing_ids.list`. Dominant causes: Ollama model not installed, missing `docs/evidence/*` and `.byron/services.yaml` fixtures, AgentRun destination guards, and pytest-timeout on live-service tests.

**New regressions: 0.**
