# Governed interception: Phase B report (2026-11-16, SAST)

Phase A findings: `PHASE_A.md`. TGI run sheet: `RUN_TGI.md`. Machine-readable results: `summary.json`.

## What was built (all default-off)
Flags:
- `BEAST_GOVERNED_INTERCEPTION` (proxy/Executor hook and gauntlet shim)
- `BEAST_CAPABILITY_ROUTER` (scorecard ranking)
- `BEAST_PROCESS_LIFECYCLE` (owned-process teardown)

**New modules:**
- `app/kernel/compute/governed_client.py`: one governed core. It runs:
  - avoid hook;
  - scorecard rank;
  - circuit breaker;
  - governor admit;
  - schema-forced body per dialect (Ollama `format`, NIM `response_format` then `nvext.guided_json`, HF router json_schema strict, TGI `json_object` grammar), with 400/422 dialect fallback;
  - SSE/NDJSON streaming with TTFT and stall timers;
  - incremental JSON gate for early stop and runaway detection;
  - verifier with repair-feedback turns;
  - teardown;
  - scorecard and breaker update;
  - redacted hash-chained `model_call` receipts.
- Candidates:
  - Ollama;
  - NIM (Nemotron / DeepSeek / gpt-oss-20b);
  - HF router (token from `HF_TOKEN` or `~/.cache/huggingface/token`, never logged or receipted);
  - TGI, only if `GET /health` on `TGI_BASE_URL` (default 127.0.0.1:8090) answers 200.
- `app/kernel/compute/capability_scorecard.py`: per (provider, model, family, placement) cell, with decay (half-life 20), UCB-style exploration, demote-after-2 plus cooldown. Stored at `.beast/.../capability_scorecard.json`.
- `app/kernel/compute/placement.py`: live VRAM/RAM probe, returning gpu_full / hybrid:N / cpu, or cloud when the run would swap-thrash. Calibrated for qwen2.5-coder:7b from the measured results (4415 MiB predicted vs 4421 MiB measured at full GPU).
- `app/kernel/execution/process_lifecycle.py`:
  - spawns into a `systemd-run --user --scope` unit named `beast-worker-*`, or adopts a process with proof (pidfd plus start time plus cgroup; refuses foreign uid, docker/system.slice and protected ports 8101/8131);
  - terminates via pidfd SIGTERM, then grace, then SIGKILL, then `cgroup.kill`; closes fds, runs release hooks, measures VRAM, and writes a `process_teardown` receipt;
  - triggers: stream_stall, circuit_open, placement_change, budget_exhausted, runaway_output.

**Wiring:**
- `Executor._try_governed_interception` sits after the local-specialist step on the canonical `/proxy/{provider}/v1/chat/completions` path. It is used when the flag is set and the request carries `metadata.governed_schema`.
- `scripts/gauntlet_large.py::provider_chat` goes through the governed client under the flag. A live NIM check gave ok, early_stop, dialect openai_json_schema, 1.07 s.

**MCP:**
- stdio now speaks NDJSON (with legacy Content-Length auto-detect) and keeps stdout protocol-clean (factory.py prints became logging).
- Spec Streamable HTTP is available at `POST /mcp`. It was verified with the official MCP SDK client (initialize, tools/list and a tool call); the evidence is in `mcp/`.

**Scripts:**
- `scripts/governed_interception_proof.py`
- `scripts/governed_interception_summary.py`
- `scripts/governed_lifecycle_demo.py`

## Tests
- New tests: 43/43 pass.
  - governed_interception: 25
  - process_lifecycle: 6 (real systemd scope)
  - proxy_hook: 3
  - mcp_stdio_framing: 5
  - mcp_streamable_http: 3
  - factory_stdout_clean: 1
- Adjacent existing suites (gauntlet_large, mcp_broker, mcp_runtime_v2, phase_d_execution, governor wiring and spine, structured_edit, cli_executor, crystal execution, governed crystal executor): 107 pass, 4 fail.
  - All 4 failures are in `tests/test_mcp_runtime_v2.py`, with KeyErrors on 'profile', 'privacy' and 'exported'.
  - They test `app/mcp/runtime.py`, which this work did not touch (last modified 2026-10-10), so they are pre-existing.

## Live proof
Tasks ran on throwaway gauntlet repos in temp dirs. Acceptance is the gauntlet's own `apply_and_verify` plus the hidden intent check.

| Phase | Tasks | Accepted | Notes |
|---|---|---|---|
| Routed: scorecard + fallback chain, 10 tasks over 9 families incl. rename, multi-file composite, far | 10 | **7** | const/op/obo were solved by local qwen3:4b in 1 call. exc: qwen3 and granite rejected (granite's degenerate stub was caught), then Nemotron passed. tool, dual and far were passed by HF gpt-oss-120b. ren-h1, ren-h2 and refguard-h1 failed. |
| Hard rerun with verifier-feedback turns and full-GPU qwen2.5-coder:7b | 5 | **1** | ren-h2 was solved by HF Kimi-K2.7-Code (the baseline never solved rename). ren-h1, ren-h3 and refguard-h1/h2 failed. |
| Head-to-head, 3 tasks x 7 candidates | 21 | 7 | const-h2 was passed by every model that answered. ren-h3 was failed by all. refguard-h2 was passed only by Kimi. |

**Per-call results:**
- 52 calls were answered; all **52 were JSON-schema-valid (100%)**, and all 52 early-stopped as soon as the edits object was complete.
- Median completion was **72 tokens**, against a 2048-4096 max_tokens cap.
- 6 calls were transport failures (DeepSeek 4, gpt-oss-20b 2: NIM ReadTimeout). The breaker opened on DeepSeek and skipped it twice with no request sent.

**Versus baseline (`evidence/gauntlet-2026-11-16-large/summary.json`):**
- Baseline: Nemotron passed 5/6 h2h families (median 719 tokens per pass incl. prompt). DeepSeek and gpt-oss passed 0, burning 75-90 s per timeout before the breaker. Rename was unsolved. 2 false accepts.
- Now: a rename task is solved for the first time (Kimi via the HF router, 2.2 s), and gpt-oss-20b passed one task on NIM.
- No false accepts. The verifier rejected granite's stub and several hidden-check failures.
- Local qwen3:4b took the easy families at $0, so cloud is only used when needed.
- Not improved: rename (3 of 4 still fail), refguard composite (1 of 4 pass) and NIM DeepSeek availability.

## Lifecycle live demo (`lifecycle/lifecycle_demo.json`)
1. BEAST spawned Ollama's bundled llama-server (qwen2.5-0.5b Q4_K_M, `-ngl 99`) in scope `beast-worker-36303b4a35`. VRAM went 8 → 568 MiB (server 554 MiB).
2. It streamed a schema-forced request, then SIGSTOP-froze the server to inject a hang.
3. The stall timer fired, and the lifecycle layer verified identity and sent pidfd SIGTERM, then SIGKILL, then `cgroup.kill`.
4. The server was dead and **VRAM returned to 8 MiB (554 MiB reclaimed)** in 3.8 s, with a `process_teardown` receipt. The receipt chain is valid.

An earlier CPU-only run of the same demo (the backend lib path was missing) showed the inter-chunk stall variant.

## Spend
- NIM: free-tier credits, about 11.0k prompt (estimated) and 1.4k completion tokens over 18 calls, 6 of them timeouts.
- Ollama: local.
- HF router (DeepInfra), estimated **$0.0073** in total:
  - gpt-oss-120b: 9 calls, ≈$0.0004
  - Kimi-K2.7-Code: 8 calls, ≈$0.0070
- Early stop closes the stream before the usage chunk, so prompt tokens are estimated from the rebuilt prompts. The client now records that estimate itself.
- The placement benchmark was local only.

## Open issues
- Rename and refguard remain hard for every model: models emit one edit where four call sites change. A deterministic rename tool (AST-wide symbol replace) is the likely real fix, not a bigger model.
- NIM DeepSeek-v4.1-flash and gpt-oss-20b time out frequently (provider side).
- The placement calibration only covers qwen2.5-coder:7b.
- The MCP REST facade on :8765 still runs old code until it is restarted. The spec server for this session is on :8779.
- TGI is not tested live: there is no nvidia-container-toolkit, and the disk is tight.
- 4 pre-existing failures in `test_mcp_runtime_v2`.
