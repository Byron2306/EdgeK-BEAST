# TGI (beast-tgi) + HF-router lanes: governed interception proof, 2026-11-16 09:00-09:20 SAST

## Server
- **Health:** `/health` returns 200.
- **`/info`:**
  - model Qwen/Qwen2.5-Coder-3B-Instruct-AWQ, TGI 3.3.6-dev0;
  - max_concurrent_requests 8;
  - max_input_tokens 3072, max_total_tokens 4096.
- **VRAM** (`/usr/bin/nvidia-smi`, driver 620.70.06):
  - 4224/6144 MiB at start (TGI pid 4210 MiB);
  - 4312 MiB under load and at the end.
- **Ollama:** `/api/ps` was empty. No Ollama model was loaded while TGI held the GPU. The Ollama comparison uses the earlier full-GPU numbers (from before TGI started).

## Grammar-constrained, streamed, early-stopped
- **Constraint and streaming:** all 26 TGI calls used `response_format {type: json_object, value: <EDITS_SCHEMA>}` (dialect `tgi_json_object`) over `/v1/chat/completions` SSE.
- **Results:** 26/26 were schema-valid and 26/26 were early-stopped by the gate. Output was 28-76 tokens against a 768 cap.
- **Grammar compile cost:** the first call compiled the grammar (TTFT 17.5 s). After that, TTFT was 73-280 ms.

## Same 13-task set (routed 10 + h2h 3: rename, refguard, multi-file composite, far)
| Run | Accepted | Notes |
|---|---|---|
| TGI-3B alone, 1 attempt | **2/13** (const-h1, const-h2) | 13/13 JSON valid. p50 latency 1.05 s. $0. The other 11 parsed fine but failed the tests. |
| TGI-first chain (TGI → Nemotron → gpt-oss-120b:deepinfra → Kimi:deepinfra), feedback turns on | **11/13** | Accepted by: TGI 2, Nemotron 2, gpt-oss-120b 2, Kimi 5. Only ren-h1 and ren-h3 failed. 40 calls, 40/40 JSON valid, 0 transport errors. $0.0109. |

**Note:** the earlier proof got 7/10 routed and 1/5 on the hard rerun. The TGI-first chain ran with feedback turns and 4 attempts on every task, so the jump is partly from that, not only from TGI.

## Continuous batching (8 gauntlet prompts, warm server, 2 rounds)
| Mode | Wall s | req/s | p50 ms | p95 ms | TTFT p50 ms | Completion tok/s (aggregate) |
|---|---|---|---|---|---|---|
| Sequential, round 1 | 8.42 | 0.95 | 1026 | 1316 | 81 | 32.8 |
| 8 concurrent, round 1 | 4.56 | 1.76 | 3926 | 4500 | 198 | 60.6 |
| Sequential, round 2 | 8.48 | 0.94 | 1010 | 1299 | 83 | 32.6 |
| 8 concurrent, round 2 | 3.90 | 2.05 | 3300 | 3862 | 160 | 70.7 |

- **Throughput:** 1.85-2.17x higher with 8 concurrent requests. Per-request latency rose about 3.5x.
- **Correctness:** 8/8 JSON valid and early-stopped in every mode.
- **Why tok/s looks low:** outputs are about 35 tokens, so prompt prefill dominates (prompts are 500-1000 tokens).
- **Accept rate:** concurrent results scored the same as solo (1/8). Batching doesn't change quality.

## Model comparison (all calls in this evidence; pass rate is per answered call)
Each model saw a different task mix (routing order), so pass rates are only roughly comparable.

| Candidate | Answered (transport err) | JSON valid | Verified pass | Latency p50 | Spend |
|---|---|---|---|---|---|
| HF Kimi-K2.7-Code:deepinfra | 15 (0) | 100% | 8 (53%) | 6.8 s | $0.0130 |
| Ollama qwen3:4b (earlier, GPU) | 11 (0) | 100% | 4 (36%) | 13.9 s | $0 |
| HF gpt-oss-120b:deepinfra | 18 (0) | 100% | 6 (33%) | 2.9 s | $0.0006 |
| NIM gpt-oss-20b | 3 (2) | 100% | 1 | 97 s | free tier |
| NIM Nemotron-3.5 | 20 (0) | 100% | 4 (20%) | 1.3 s | free tier |
| **TGI Qwen2.5-Coder-3B-AWQ** | 26 (0) | 100% | 4 (15%) | **1.05 s** | $0 |
| Ollama granite3.3:2b (earlier) | 7 (0) | 100% | 1 (14%) | 11.2 s | $0 |
| Ollama qwen2.5-coder:7b full GPU (earlier; hard tasks only) | 5 (0) | 100% | 0 | 11.0 s | $0 |
| NIM DeepSeek-v4.1-flash | 0 (4) | - | - | - | free tier |

**Takeaway:** TGI-3B is the fastest local first rung. It's 13x quicker than Ollama qwen3:4b and handles concurrency, but it only solves the trivial constant-fix family. It's worth keeping as rung 0 because every miss costs about 1 s and $0. Its scorecard cells drop fast, so the router skips it on hard families.

## HF-router lanes (approved), 1 tiny schema-forced call each
- **Result:** all **15/15 routes ok**: JSON valid, correct edit, early-stopped, `openai_json_schema` dialect.
- **Speed and cost:** TTFT 0.47-4.2 s. Fastest were gpt-oss-120b:cerebras (0.5 s), Qwen3.8-27B:cerebras (0.47 s) and DeepSeek-V4.1-Flash:baseten (0.49 s). Smoke spend was $0.00087.
- **Fix made during the smoke run:** Qwen3.8-27B:cerebras first returned 400, because `chat_template_kwargs` isn't supported there. The client now strips a rejected optional knob and retries the same dialect. Covered by a new test; the live retry was ok.
- **Unlisted prices:** featherless-ai (Kimi) and zai-org (GLM) prices aren't listed by the router. Spend for those routes uses the most expensive sibling route as an upper bound.

## Spend (this run)
- **HF router: $0.0118 in total.**
  - TGI-first chain: $0.0109
  - Smoke: $0.0009
- NIM: free tier only.
- TGI and Ollama: local.
- **Cumulative today, including the earlier proof: ≈ $0.019.**
