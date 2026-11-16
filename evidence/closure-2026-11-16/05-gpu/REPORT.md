# Step 5 — GPU self-scheduling (closure 2026-11-16)

## What changed
- `app/kernel/compute/gpu_scheduler.py` (new this job):
  - **Automatic local-lane switch**: `local_candidates()`.
    - TGI healthy → TGI first and GPU-Ollama candidates dropped (CPU Ollama allowed with `num_gpu:0` if asked).
    - TGI down → Ollama keeps the GPU and TGI is dropped.
  - Enabled by `BEAST_GPU_SCHEDULER=1` or by `BEAST_GOVERNED_INTERCEPTION=1`; `BEAST_GPU_SCHEDULER=0` turns it off.
  - **Unload before a TGI batch**: new `ensure_tgi_gpu()` sends `keep_alive:0` to every GPU-resident Ollama model, throttled to once per 5 s.
    It is wired into `GovernedModelClient._call` before every TGI call (`app/kernel/compute/governed_client.py`, backup kept), and events are
    kept in `client.gpu_prepare_events`. `prepare_tgi_batch()` remains for whole batches (it reports VRAM before/after).
  - `prepare_ollama()` uses the calibrated placement planner and notes when TGI holds the GPU.
  - Stopping or starting the TGI container is **not** automated. Those stay operator commands (`docker stop/start beast-tgi`), because
    beast-tgi is outside BEAST's kill authority under the rules.
- `app/kernel/compute/placement.py` (backup `*.before-closure-20261116`): measured calibration added. Values are partial loads in the ~1.8 GB
  left beside TGI, at ctx 2048 with f16 KV, measured by nvidia-smi delta; every load was unloaded afterwards and VRAM returned to 4312 MiB each time
  (`calibration.json`):
  | model | loads | per-layer MiB | overhead MiB | full-GPU estimate |
  |---|---|---|---|---|
  | qwen3:4b | 2L=565, 8L=973 | **68.0** | **429** | 2945 MiB (37 L) |
  | granite3.3:2b | 4L=379, 16L=849 | **39.2** | **222** | 1829 MiB (41 L) |
  | granite3.2:2b | inferred = granite3.3:2b (same architecture/size; not separately measured) | 39.2 | 222 | |
  | qwen2.5-coder:7b | already calibrated earlier today | 133.4 | 546 | 4415 MiB |
  With TGI resident (1832 MiB free), the planner now says: qwen3:4b hybrid:14, granite hybrid:31, 7B hybrid:6.
- `tests/test_gpu_scheduler.py` (new): **6/6**. Together with test_governed_interception*, displacement and the live-displacement harness: **49/49 pass**.

## Who keeps reloading qwen3:4b (read-only investigation)
- I could not read the Ollama journal: byron is not in `adm`/`systemd-journal`, and `/usr/share/ollama/.ollama/logs` is permission-denied.
  No cron entries and no user timers exist. No in-process periodic loop in BEAST loads Ollama models.
- Callers that request qwen3:4b by default (ranked by likelihood):
  1. **BEAST's own governed path**: `governed_client.default_candidates` listed `ollama/qwen3:4b` as the first local candidate. This morning's
     gauntlets also used it directly (`scripts/gauntlet_large.py` SPECIALIST_MODEL="qwen3:4b"). This is what reloaded it during today's runs.
     **Now fixed** by the GPU scheduler: GPU Ollama is dropped while TGI is up, and resident models are unloaded before TGI calls.
  2. **LiteLLM on :4000** (pid 830027, started Sun 16:54 SAST): `deploy/generated/litellm.config.yaml` routes `model_name: qwen3:4b` → `ollama/qwen3:4b`.
     Any client that asks LiteLLM for that alias reloads it. Not changed (the LiteLLM proposal was not to be applied).
  3. The **second BEAST gateway** in guardian socket mode (pid 1370366, `bin/beast gateway --socket-mode guardian`, beast-beast-guardian-consumer.service).
     It runs the same code paths: `ollama_scout` default model qwen3:4b (`OLLAMA_SCOUT_MODEL`), `swarm_specialist` preference qwen3:4b first,
     zero_desktop_review (`BEAST_ZERO_REVIEW_MODEL` default qwen3:4b), and the provider_registry default_model.
  4. Not BEAST, checked and ruled out: the DIO serve_* scripts and lilith_worker contain no qwen3 references.
  - The trace ledger has 9 qwen3:4b crystal-reuse decisions from `local_execution_gateway` (latest 2026-11-16 00:15 SAST). That is consistent with #1/#3.
- **Tool to catch it definitively**: new `scripts/ollama_load_watch.py` (read-only). It polls /api/ps and snapshots `ss -tnp` clients on :11434
  the moment a model appears. I validated it with a CPU-only granite load, where it attributed the load to the curl pid.
  Byron: `sudo .venv/bin/python scripts/ollama_load_watch.py --seconds 3600 --out .beast/ollama-load-watch.jsonl` (sudo so every uid is visible).
  Alternatively: `sudo journalctl -u ollama --since today | grep -E 'POST|qwen3'`.
- Current state: `/api/ps` is empty (nothing loaded); VRAM 4312/6144 MiB, all TGI.

## Commands Byron may run
- Hand the GPU to Ollama: `docker stop beast-tgi` (the scheduler then routes to Ollama automatically). To return it: `docker start beast-tgi`.
- To stop the guardian gateway or LiteLLM reloading qwen3:4b: set `OLLAMA_SCOUT_MODEL=granite3.3:2b` (or the governed flags) in their environments, or remove the qwen3:4b alias from LiteLLM.

## Spend
$0 (local calibration loads only).
