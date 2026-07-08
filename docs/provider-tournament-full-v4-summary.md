# BEAST Provider Tournament Full V4 Summary

Date: 2026-06-29

Primary receipt:

- `benchmarks/results/provider_tournament_full_v4/provider_tournament_gauntlet.json`
- Receipt hash: `sha256:2c9a2e3b2779eb5f2c65bc1988336bd9f2d7d38762bca07c158d71ddf5fb4636`
- Command shape: `python3 scripts/run_provider_tournament_gauntlet.py --root benchmarks/results/provider_tournament_full_v4 --timeout-seconds 20 --max-tokens 32 --decoy-files 24 --replay-variants 2`

## Executive Result

BEAST Ollama was ranked as the explicit local challenger and passed the deep crystallization track.

The clearest result is:

- Best BEAST-native proof: `ollama` using `qwen2.5:0.5b`
- Best cloud deep-proof comparator: `google` using `gemini-2.5-flash`
- Fastest passed endpoint smoke: `groq` at `249.835 ms`
- Strongest large-model live smoke: `nvidia_nim` using `nvidia/nemotron-3-super-120b-a12b` at `1088.984 ms`

Ollama and Google both scored `10/10` on the final-boss verified task quality gate, but they prove different things. Google proves that a cloud teacher can train a crystal and then be displaced during replay. Ollama proves the stronger local-first path: a local CPU Ollama teacher generated the training signal, BEAST crystallized it, and the replay/far-transfer phase completed without cloud calls.

## Scoreboard

| Metric | Value |
|---|---:|
| Registry providers covered | `27 / 27` |
| Configured providers | `19` |
| Live tests attempted | `16` |
| Passed | `6` |
| Failed | `5` |
| Errors | `5` |
| Skipped | `11` |
| Missing inventory providers | `0` |
| Missing tournament providers | `0` |
| Ollama BEAST status | `passed` |

Reviewer-safe claims in the receipt:

- All registry providers have inventory rows.
- All registry providers have tournament rows.
- Secrets are not written to the receipt.
- Ollama BEAST is the explicit challenger, not a hidden fallback.

## Passed Providers

| Provider | Track | Model | Result | Latency |
|---|---|---|---|---:|
| `ollama` | deep crystallization | `qwen2.5:0.5b` | passed | not directly comparable |
| `google` | deep crystallization | `gemini-2.5-flash` | passed | not directly comparable |
| `groq` | LiteLLM smoke | `groq` | passed | `249.835 ms` |
| `novita` | LiteLLM smoke | `novita` | passed | `1083.327 ms` |
| `nvidia_nim` | live NIM probe | `nvidia/nemotron-3-super-120b-a12b` | passed | `1088.984 ms` |
| `cohere` | LiteLLM smoke | `cohere` | passed | `2324.27 ms` |

The smoke probes are deliberately small endpoint probes. They prove that a provider can return the expected BEAST tournament coding response through its configured lane. They are not equal to the deep crystallization proof.

## Deep Crystallization Comparison

### Ollama BEAST Challenger

Receipt:

- `benchmarks/results/provider_tournament_full_v4/ollama_beast_challenger/final_boss_crystallization_gauntlet.json`
- Receipt hash: `sha256:6776e785a28378cf22fbfcd99fd0188be0c0cbb4b71ee4c059a37ecc45c1beb3`
- Replayable evidence bundle: `benchmarks/results/provider_tournament_full_v4/ollama_beast_challenger/final_boss_replayable_evidence_bundle.zip`
- Bundle hash: `sha256:a4928972c49eba8bb1e704943fe24e6d546fdd9bb23d7e186f3fc3a88821b94c`

Quality:

- Quality score: `10 / 10`
- Evaluation gates passed: `true`
- Changed files: `4`
- Decoy files: `24`
- Replay variants: `2`
- Baseline failures: `3`
- Integration tests passed: `true`
- Negative controls blocked: `3 / 3`

Final-final claims:

| Claim | Value |
|---|---|
| `baseline_replayable` | `true` |
| `cloud_calls_training` | `0` |
| `cloud_calls_replay` | `0` |
| `local_cpu_teacher` | `true` |
| `tiny_model` | `qwen2.5:0.5b` |
| `semantic_credit_reused` | `true` |
| `far_transfer_repaired` | `true` |
| `negative_reuse_cases_blocked` | `true` |
| `memory_hull_signature_verified` | `true` |

Interpretation:

This is the most important proof in the tournament. It says BEAST can use a tiny local Ollama model as the training teacher, capture the successful repair as crystallized compute, and then reuse the promoted semantic credit on a far-transfer variant without making another provider call.

The reviewer-safe version of the claim is:

> A local CPU-first BEAST/Ollama run produced a verified multi-file gateway repair recipe, preserved baseline and patched repos separately, promoted the result into reusable semantic compute residue, blocked negative reuse cases, and repaired far-transfer variants without cloud replay calls.

### Google Comparator

Receipt:

- `benchmarks/results/provider_tournament_full_v4/provider_competitors/google/final_boss_crystallization_gauntlet.json`
- Receipt hash: `sha256:1b5ce2bcf1a5888cab7905eead8c75c85f4d804864b671247b9a74177ddac5bd`
- Replayable evidence bundle: `benchmarks/results/provider_tournament_full_v4/provider_competitors/google/final_boss_replayable_evidence_bundle.zip`
- Bundle hash: `sha256:a2d8262947c51557134924e2cb1721a9231489263ad36c3d51f6f2291f07aa94`

Quality:

- Quality score: `10 / 10`
- Evaluation gates passed: `true`
- Changed files: `4`
- Decoy files: `24`
- Replay variants: `2`
- Baseline failures: `3`
- Integration tests passed: `true`
- Negative controls blocked: `3 / 3`

Final-final claims:

| Claim | Value |
|---|---|
| `baseline_replayable` | `true` |
| `cloud_calls_training` | `1` |
| `cloud_calls_replay` | `0` |
| `local_cpu_teacher` | `false` |
| `semantic_credit_reused` | `true` |
| `far_transfer_repaired` | `true` |
| `negative_reuse_cases_blocked` | `true` |
| `memory_hull_signature_verified` | `true` |

Interpretation:

Google proves the cloud-teacher displacement path: a cloud model can be used once during training, then BEAST stores the verified outcome as reusable compute and completes replay/far-transfer without another cloud call.

That is strong, but it is not the same claim as Ollama. Ollama proves local genesis; Google proves cloud-to-crystal displacement.

## Fastest Successful Smoke Providers

Only smoke tracks have directly comparable latency numbers. The deep crystallization tracks include local repo creation, pytest gates, durable cache work, negative controls, memory hull sidecars, and bundle generation, so their row-level latency is intentionally not compared to smoke calls.

Fastest passed smoke lanes:

1. `groq`: `249.835 ms`
2. `novita`: `1083.327 ms`
3. `nvidia_nim`: `1088.984 ms`
4. `cohere`: `2324.27 ms`

This means Groq was the fastest simple completion lane in this run. It does not mean Groq did the best crystallization work, because Groq was only smoke-tested in this tournament.

## Failed or Error Providers

These are not all BEAST failures. Several are provider account, credit, model-access, or local endpoint shape failures.

| Provider | Status | Cause |
|---|---|---|
| `openai` | failed | 401 invalid/rejected API key |
| `codex` | failed | 401 invalid/rejected API key |
| `xai` | failed | 403 provider error |
| `local_nim` | failed | HTTP 200 but response did not match tournament probe |
| `llama_cpp` | failed | HTTP 200 but response did not match tournament probe |
| `deepinfra` | error | positive balance required |
| `hyperbolic` | error | insufficient funds |
| `nscale` | error | insufficient credit |
| `featherless` | error | gated model access |
| `fal` | error | tournament uses an invalid LiteLLM text-chat probe for this lane |

Important detail: `local_nim` and `llama_cpp` were reachable enough to return HTTP 200, but they did not return a valid tournament coding completion. BEAST marked them as failed, not skipped. That is the right behavior for a completion tournament.

## Skipped Providers

Skipped providers either lacked required secrets/endpoints or do not yet have a direct tournament probe implemented.

Skipped:

- `anthropic`
- `cerebras`
- `huggingface`
- `litellm`
- `openrouter`
- `ovhcloud`
- `replicate`
- `sglang`
- `tensorrt_llm`
- `tgi`
- `vllm`

Some of these skips are expected because they are infrastructure lanes or require local servers. Others need secrets or a dedicated native probe.

## Evidence Bundle Contents

The deep crystallization receipts include evidence that is independently inspectable:

- Baseline training repo
- Baseline far-transfer repo
- Patched training repo
- Patched far-transfer repo
- Negative cases:
  - `secret_bearing_promotion.json`
  - `wrong_repo_fingerprint.json`
  - `wrong_task_class.json`
- Proof files:
  - `baseline_pytest.json`
  - `after_pytest.json`
  - `eval_gates.json`
  - `local_engine_probe.json`
  - `semantic_reuse_decision.json`
  - `memory_hull_verification.json`
  - `receipt_hash_verification.json`
- Durable cache records
- Trace ledger
- Route optimizer store
- Semantic cache store
- Replayable zip bundle

This matters because the claim is not just "a model answered." The proof includes broken baselines, patched repos, verifier gates, sealed memory, negative controls, semantic reuse decisions, and replayable bundles.

## What This Ultimately Means

The tournament supports three major conclusions.

First, BEAST can compare local and cloud/provider lanes in one inventory. It emitted rows for all 27 registry providers and did not hide missing providers.

Second, BEAST Ollama is no longer merely a local fallback. In this run it is a ranked, passing challenger with the strongest local-first crystallization evidence. It used a tiny local model, produced a verified repair crystal, reused it on far transfer, and avoided cloud calls during replay.

Third, the crystallization architecture is doing something materially different from normal prompt caching. The evidence shows:

- A broken baseline was preserved.
- A repair was generated and normalized into a verifier-approved recipe.
- Pytest/integration gates passed after repair.
- Negative reuse cases were blocked.
- Memory Hull sidecars were verified.
- A semantic reuse decision was used.
- The replay completed without provider calls.

That is the central BEAST claim: expensive or uncertain inference can be converted into deterministic, locally governed, replayable compute residue that later displaces repeated model calls.

## What It Does Not Prove Yet

The result is strong, but the boundary should stay honest.

It does not prove that every configured provider is healthy. Several provider lanes failed for account balance, auth, gating, or local endpoint response-shape reasons.

It does not prove Groq, Cohere, Novita, or NIM can perform the full final-boss crystallization task, because those lanes were smoke-tested rather than deep-tested in this tournament.

It does not prove production-scale task coverage. The final-boss task is production-shaped and multi-file, but still synthetic. A corpus of real issue repairs is the next higher bar.

It does not prove that local Ollama is fastest. The local Ollama row is a deep proof, not a comparable smoke call. The fastest simple completion smoke was Groq.

## Practical Ranking

| Category | Winner | Why |
|---|---|---|
| Best BEAST-native proof | `ollama` | Local CPU teacher, no cloud training/replay, semantic credit reused |
| Best cloud deep proof | `google` | Full final-boss proof passed with one cloud training call and zero replay calls |
| Fastest simple smoke | `groq` | `249.835 ms` |
| Best large-model live smoke | `nvidia_nim` | Nemotron 120B completed live probe in `1088.984 ms` |
| Best evidence bundle | `ollama` | Stronger local-first claim plus replayable bundle and negative controls |

## Recommended Next Gauntlet

The next tournament should add deep crystallization runs for the fastest smoke winners:

- Groq deep crystallization
- NVIDIA NIM deep crystallization
- Cohere deep crystallization
- Novita deep crystallization

It should also repair the remaining probe gaps:

- Replace invalid OpenAI/Codex credentials.
- Fix xAI authorization/model selection.
- Add a proper FAL-native probe instead of the current LiteLLM chat probe.
- Add direct native probes for Hugging Face and Replicate.
- Make `local_nim` and `llama_cpp` return valid OpenAI-compatible chat content or mark them as non-chat lanes.
- Add account-balance preflight classification for DeepInfra, Hyperbolic, and Nscale.

The highest-value next proof would be a four-way deep crystallization bracket:

1. Ollama local CPU
2. Google Gemini
3. Groq
4. NVIDIA NIM

Run the same multi-file repair task, same baseline, same decoys, same negative controls, same replay variants, same evidence bundle requirements. That would separate endpoint speed from crystallization quality and make the ranking much harder to dismiss.
