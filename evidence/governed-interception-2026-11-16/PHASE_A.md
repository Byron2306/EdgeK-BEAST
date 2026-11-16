# Governed Interception: Phase A findings (2026-11-16, SAST)

Read-only inventory, except the MCP fixes (test-first, files backed up as `*.before-governed-interception-<ts>`).
No key or token values were read into output; presence was checked by NAME only.

## 1. Provider vault and registry

The "massive list" exists as a **catalogue**, but the vault now holds only **one** credential.

| Source | Entries | Notes |
|---|---|---|
| `app/kernel/registry/provider_registry.py` (ProviderRegistry) | **27 provider lanes** | anthropic, cerebras, codex, cohere, deepinfra, fal, featherless, google, groq, huggingface, hyperbolic, litellm, llama_cpp, local_nim, novita, nscale, nvidia_nim, ollama, openai, openrouter, ovhcloud, replicate, sglang, tensorrt_llm, tgi, vllm, xai |
| `app/kernel/security/secret_vault.py` PROVIDER_ENV | 27 env names (24 providers) | adds mistral, together, perplexity, fireworks, deepseek (not in registry) |
| `deploy/generated/litellm.config.yaml` (LiteLLM on :4000) | 26 model routes | uses `os.environ/<NAME>` refs only |
| `.beast/provider_secrets.env` (the vault, mode 600, 205 B, mtime 2026-11-15 19:07) | **1 key: `NVIDIA_API_KEY`** | `/edgek/providers/secrets` on 8101 agrees: `{nvidia_nim: 1}` |
| HF token | present at `~/.cache/huggingface/token` | **mode 664: run `chmod 600 ~/.cache/huggingface/token`**. Not in the vault and not in the environment |

Searched with no larger vault found: the repo `.beast/`, `~/.beast` (only `keys/residue`), `~/.config/beast` (Guardian/ARDA files only), the restored WSL home (`/data/byron/dio-wsl-restored-20261015/home/byron`, including its `.beast` and `.config`), and older BEAST copies (`~/beast-*`, `~/Downloads/BEAST_*`). Other `.env` files belong to other projects (Metatron, DIO, Vesper). If the original vault held many keys, it may have been lost in the WSL→Linux move. It would need re-importing with `beast` vault import (SecretVault.import_file, merge mode).

**HF-token-capable (HF Inference Providers router `https://router.huggingface.co/v1`, OpenAI-compatible; model suffix `:provider`)**: cerebras, cohere, fal-ai, featherless-ai, fireworks-ai, groq, hyperbolic, nebius, novita, nscale, ovhcloud, replicate, sambanova, scaleway, together, hf-inference (plus newer partners). Of the BEAST registry, **13 lanes can run with just the HF token**: huggingface, cerebras, cohere, fal, featherless, groq, hyperbolic, novita, nscale, ovhcloud, replicate, together*, fireworks* (*vault catalogue only). Local `tgi` also takes HF_TOKEN, but only for gated model downloads.
Configured today: **nvidia_nim (vault)**, **ollama (local, no key)**, and **huggingface via the token file**. All others: not configured.

## 2. MCP
- Launch: stdio `bin/beast mcp --workspace <repo>` (the `beast mcp-config` / `mcp-install` output). HTTP facade: `bin/beast mcp-http --port 8765`, running as pid 830156 since earlier.
- **Bug 1 (fatal):** stdio used LSP `Content-Length` framing. MCP stdio is newline-delimited JSON, so every real client (official SDK, VS Code, Claude Code) hung at `initialize`. Proof: `mcp/before_fix_probe.log` (official `mcp` 1.30 SDK, initialize TimeoutError).
- **Bug 2:** lazily imported `app/kernel/compute/factory.py` does `print("DEBUG: factory.py imported")` to stdout. On first tools/call this would corrupt the stdio stream. It also pollutes `beast --agent` JSON output.
- **Bug 3:** `initialize` echoed any client protocolVersion. **Bug 4:** unknown methods returned -32000, not -32601.
- **Bug 5:** the HTTP "MCP" on 8765 is a REST facade (`/mcp/tools/list` etc.), not MCP Streamable HTTP. Real HTTP MCP clients can't use it.
- **Fixed (test-first):** `app/mcp/stdio_server.py` (NDJSON + legacy Content-Length auto-detect, fd-level stdout protection, version negotiation, -32601) and `app/mcp/server.py` (adds spec Streamable HTTP `POST/GET/DELETE /mcp`, reusing the stdio handler and fail-closed custody). Tests: `tests/test_mcp_stdio_framing.py` (5) and `tests/test_mcp_streamable_http.py` (3), **8/8 pass**.
- **Proof with the official SDK:**
  - stdio: initialize (protocol 2025-11-25), tools/list = 36, `beast_mcp_status` call isError=false (`mcp/after_fix_probe.json`).
  - Streamable HTTP: a new user process on **127.0.0.1:8779** (`bin/beast mcp-http --port 8779`, pid in `.beast/governed-interception/mcp-http-8779.pid`) passed initialize, tools/list (36) and a tool call (`mcp/http_probe.json`).
- Open: the stdio/HTTP tools/list exposes 36 lightweight definitions, while the runtime registers 69 tools. 8765 is still running the old code; Byron should restart it (command below).

## 3. CLI (`bin/beast`, symlinked at `~/.local/bin/beast`; no pyproject entry points)
Commands: ui, ide, up, heal, start, evidence, crystal-proof, spaces (package-tiny-llama, validate, export, import, replay, economy, economy-proof, economy-simulate, credit-issue, promote-crystal, prototype-complete, federate-state/-prepare/-allow/-ingest/-revoke, run), gateway, commons-gateway, mcp, mcp-http, doctor, providers, integrations, compressors, mcp-config, mcp-install, reinstall-surfaces, configure-intelligence, compress, scout, diagnose, route, verify, maintenance, chronicle, promote, prec (status, list, trace, snapshot, start, advance), handoff-prepare, openclaw-plan/-execute, nemoclaw-plan/-execute, zeroclaw-plan, hermes-plan/-execute.

**`heal` in depth** (`command_heal`):
- It probes gateway `/health`, `/proxy/health`, `/mcp/health` on the gateway, MCP HTTP :8765, LiteLLM :4000 `/v1/models`, Ollama :11434 `/api/tags`, and nginx `127.0.0.1:8080/health`.
- **Default is destructive:** `--restart-all true --kill-address-pids true`. It stops pidfile services, **SIGKILLs whatever listens on 8101, 8765, 4000, 8080 and 11434**, then restarts everything, including `ensure_nginx(apply=True)`.
- I ran only `--dry-run true` (full and selective). Results are in `phase_a/heal-dry-run-*.json`:
  - gateway, proxy, mcp, litellm and ollama are OK. nginx is FAIL.
  - Full mode would kill pid 1068209 (**8101**), 830156 (8765) and 830027 (LiteLLM).
  - Selective mode would only "repair" nginx.
- Bugs and risks:
  1. **The default kills 8101 and Ollama listeners.** It should default to selective, with `--restart-all` opt-in.
  2. The nginx check uses :8080, but nginx listens on :80 (`beast ide` passes registry port 80). :80 returns 404 for `/health`, so heal reports nginx as permanently failed.
  3. `/proxy/health` advertises `base_url http://127.0.0.1:8000/proxy`. That port is pocket-tts, not BEAST.
  4. Ollama is a system service (user `ollama`). Heal can't see its PIDs and would try to start a second `ollama serve`.
  5. Stdout is polluted by the `factory.py` DEBUG print, which breaks `--agent` JSON.
  6. Dry-run in full mode reports `would_restart` even for healthy services.
  7. The last real heal (2026-11-15 16:54 SAST) ended in `attention`.
  8. `beast ide` silently runs a non-dry-run heal on launch.

## 4. Proxy / model-call sprawl (43 call-site files; `*.before-*` / `.pre-*` backups ignored)

| Path | What it is | Governed? |
|---|---|---|
| `app/proxy/server.py` `/proxy/{provider}/v1/chat/completions`, `/proxy/v1/chat/completions` | registry-routed proxy → `huggingface_adapter._run_prec` → `execute.py` RequestExecutor | **Yes**: perceive→economize→reason (deny/defer)→compute_plane.begin (deterministic/reuse/local/specialist)→provider; receipts; streaming interceptor (schema-aware) when stream=true |
| `app/adapters/{openai,anthropic,gemini,huggingface}_adapter.py` (`/v1/*`, `/proxy/openai/*` …) | per-vendor compat surfaces | Yes, through the PREC orchestrator (`execute_cycle`) / `_run_prec` |
| `app/kernel/execution/execute.py` `_execute_ollama/_openai/_openai_compatible/_tgi/_gemini/_anthropic` | the actual HTTP egress for the governed path | Yes (receipts + interceptor), but **no schema-forced output, no scorecard, fixed provider choice** |
| LiteLLM proxy :4000 (`deploy/generated/litellm.config.yaml`) | separate OpenAI-compat router (26 routes) | **No** if called directly; yes only when reached via `/proxy/litellm` |
| `app/kernel/agents/swarm_specialist.py` (Ollama `/api/generate`) | D9 local specialist | Partly: governor admit + receipts, `format` schema; no stream interception |
| `app/kernel/agents/{nim,ollama}_planner_provider.py` | planner LLM calls | Partly: schema/format, no admit or receipts |
| `app/kernel/adapters/providers.py`, `provider_adapters.py` | legacy provider clients | No |
| `app/kernel/compute/inference_engine_fabric.py` (`/edgek/inference-engines/{id}/generate` in main.py) | direct TGI/vLLM/OpenAI-compat engine calls | No admit or receipts |
| `app/kernel/compute/generation_provider_adapters.py` | image/media generation providers | Receipts only |
| `app/kernel/compute/nim_live_probe.py`, `nim_picker.py`, `provider_tournament_gauntlet.py`, `*_crystallization_gauntlet.py`, `milestone11_*`, `scientific_uplift_experiment.py`, `crystallized_compute_proof.py` | probes/experiments | Receipts, no admit (raw httpx) |
| `app/kernel/local/ollama_scout.py`, `ollama_kv_manager.py` | Ollama context/KV helpers | No |
| `app/cli/coder_client.py`, `app/cli/api.py` | CLI/TUI clients | Go to the gateway (governed) except a direct Ollama fallback in coder_client |
| `scripts/gauntlet_large.py`, `gauntlet_memfd_replay.py` | today's gauntlet | admit + receipts, but **raw httpx to NIM, stream:false, no interceptor, no schema forcing** |
| `scripts/proof/*`, `scripts/benchmark_*`, `forge_kv_*`, `windows_*` | proof scripts | No |

**Recommendation:**
- The canonical path is `/proxy/{provider}/v1/chat/completions` → `_run_prec` → `RequestExecutor`. It is the only path with deny/defer, reuse, compute_plane, receipts and the interceptor.
- Phase B adds `app/kernel/compute/governed_client.py`, one in-process governed client with the same steps (avoid → rank by scorecard → constrained body → stream + early stop → verify → scorecard + receipts). It plugs into `execute.py` behind `BEAST_GOVERNED_INTERCEPTION` / `BEAST_CAPABILITY_ROUTER`, so proxy and internal callers share the code.
- Everything else becomes a thin shim over it: planners, specialist, inference_engine_fabric, gauntlet scripts and probes. LiteLLM should only be reachable as a backend behind the proxy; ARDA/X6 can enforce that.

## 5. GPU / host (all confirmed with nvidia-smi, free, lscpu)
- **GPU:** NVIDIA GeForce RTX 3050 6GB Laptop GPU, 6144 MiB. Driver/KMD 620.70.06 (nvidia-smi 615.71.09), CUDA UMD 13.5.
- **VRAM contention (before, pass 1-2):** **4134 MiB was held by ComfyUI** (pid 746277, `/data/byron/lilith-local/runtime/ComfyUI`, idle 17 h). Only ~2 GB is free for serving.
- **CPU:** AMD Ryzen 5 150 with Radeon iGPU, 12 threads. The iGPU exposes `/dev/kfd` and `/dev/dri/renderD129`, but there is no rocminfo or vulkaninfo. Treat it as not used.
- **RAM:** 14.8 GiB total, **~1 GB available, 11 GB of 15 GB swap in use**. ComfyUI RSS is 7.9 GB. **Memory is the binding constraint, more than VRAM.**
- **Disk:** `/` has 11 GB free (Ollama models live there); `/data` is 99% full (4.2 GB free).
- **Docker 29.9.3:** runtimes are runc only. **No nvidia-container-toolkit, no CDI specs.** `docker run --gpus all` will fail until Byron installs the toolkit (sudo). The `ollama/ollama:latest` image is present. No TGI or vLLM image, and no vllm, llama-server or text-generation-launcher binaries on PATH (Ollama bundles its own llama-server).
- **Ollama 0.40.5:** system service (user `ollama`). Models: qwen3:4b, granite3.3:2b, granite3.2:2b, plus `qwen2.5-coder:7b` (Q4_K_M, 4.7 GB) that I pulled through the user-level API for the placement benchmark (kept; the placement benchmark uses it).
- TGI commands: see `RUN_TGI.md`. Placement benchmark: see §6.

## 6. Hybrid placement benchmark: qwen2.5-coder:7b Q4_K_M via system Ollama (one schema-forced prompt, 55 prompt tokens, ~78 output tokens)
Raw data: `placement/placement_results_pass{1,2,3}.json` and the logs. Conditions: `placement/conditions.txt`.

**Before (pass 1-2): ComfyUI resident.** VRAM 4164/6144 MiB used, MemAvailable 1.0-4.8 GB, 9-11 GB swap used.

| num_gpu | ctx | result | first token s | decode tok/s | VRAM used by model |
|---|---|---|---|---|---|
| 10 / 8 | 2048 | HTTP 500 (CUDA OOM, ComfyUI held VRAM) | - | - | - |
| 10 | 1024 | HTTP 500 | - | - | - |
| 6 | 2048 | ok | 49.4 | 2.76 | ~1.3 GB |
| 6 | 1024 | ok | 16.0 | 6.0 | 1336 MiB |
| 0 (CPU) | 2048 | ok, swap-thrashing | 111.1 | 0.42 | 0 |
| 0 (CPU, attempt 1) | 2048 | aborted (swap thrash) | - | - | - |

**After (pass 3, 08:22 SAST): ComfyUI stopped with Byron's approval.** VRAM 96/6144 MiB, MemAvailable ~11.6 GB, swap 7.6 GB used.

| num_gpu | ctx | first token s (incl. load) | load s | decode tok/s | prompt tok/s | VRAM (model) | RAM drop |
|---|---|---|---|---|---|---|---|
| 99 (full, 29/29) | 2048 | 9.9 (cold) | 9.75 | **27.1** | 292 | 4421 MiB | 0.7 GB |
| 99 (full) | 4096 | 4.3 (warm-ish) | 4.16 | **27.3** | 372 | 4535 MiB | 0.4 GB |
| 18 | 2048 | 5.1 | 4.78 | 10.7 | 186 | 2947 MiB | 2.2 GB |
| 6 | 2048 | 7.0 | 6.53 | 6.9 | 121 | 1346 MiB | 3.8 GB |
| 0 (CPU) | 2048 | 10.1 | 8.33 | 5.2 | 31 | 0 | 4.6 GB |

After unload VRAM returned to 8 MiB.

**Conclusions**
- **Full GPU:** with the GPU free, the full-GPU 7B is about 10x faster than any split measured with ComfyUI resident (27 vs 2.8 tok/s), and 2.5x faster than the best hybrid (18 layers). That leaves ~1.5 GB of VRAM headroom at ctx 4096.
- **Decode speed** scales roughly with the fraction of layers on the GPU. A partial split buys little over CPU, because the CPU-side layers dominate decode time.
- **RAM:** the binding risk is RAM, not VRAM. CPU-only takes ~4.6 GB of RAM, and when MemAvailable was ~1 GB it thrashed swap.
- **Planner:** `placement.plan()` now routes to `cloud` when the RAM need exceeds available minus a 1 GB reserve. It is calibrated to these measurements (133.4 MiB/layer + 546 MiB overhead; predicts 4415 MiB full vs 4421 measured).
- **Recommendation:**
  - Keep qwen2.5-coder:7b and run it `gpu_full` (num_gpu 99, ctx ≤ 8192) as the local coder.
  - Don't co-host TGI on the 3050 at the same time. Time-share instead: stop Ollama models (keep_alive:0) before starting TGI, or run TGI only for HF models Ollama lacks.
  - If ComfyUI comes back, BEAST's planner will push the 7B to cloud or the 4B instead of thrashing.
