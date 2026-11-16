"""Hybrid CPU/RAM/VRAM placement micro-benchmark via the Ollama HTTP API (user-level).

Varies num_gpu (layers offloaded to the RTX 3050) and num_ctx; measures first-token
latency (streaming), decode tokens/s, prompt tokens/s, load time and VRAM/RAM.
"""
import json, subprocess, sys, time, urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-coder:7b"
OLLAMA = "http://127.0.0.1:11434"
PROMPT = "Write a Python function `clamp(x, lo, hi)` with a docstring and two doctests. Output only code."
CONFIGS = [  # GPU-heaviest first: only ~1.9 GB VRAM free (ComfyUI holds 4.1 GB), RAM ~1 GB free
    {"num_gpu": 8, "num_ctx": 2048},
    {"num_gpu": 0, "num_ctx": 2048},
    {"num_gpu": 6, "num_ctx": 1024},
]
WALL_CAP_S = 300


def smi():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], text=True).strip()
        used, total = [int(x) for x in out.split(",")]
        return {"vram_used_mib": used, "vram_total_mib": total}
    except Exception as exc:
        return {"error": str(exc)}


def meminfo():
    d = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            d[k] = int(v.split()[0]) // 1024
    return d


def post(path, body, stream=False):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def unload():
    try:
        post("/api/generate", {"model": MODEL, "keep_alive": 0}).read()
    except Exception:
        pass


rows = []
for cfg in CONFIGS:
    unload(); time.sleep(2)
    before = {**smi(), **meminfo()}
    t0 = time.perf_counter(); ttft = None; final = {}; peak = before.get("vram_used_mib", 0)
    try:
      resp = post("/api/generate", {"model": MODEL, "prompt": PROMPT, "stream": True, "keep_alive": "2m",
                                  "options": {**cfg, "num_predict": 96, "temperature": 0, "seed": 7}})
    except Exception as exc:
      rows.append({**cfg, "error": f"{type(exc).__name__}: {exc}"[:200]}); print(json.dumps(rows[-1]), flush=True); continue
    timed_out = False
    for line in resp:
        if time.perf_counter() - t0 > WALL_CAP_S:
            timed_out = True; resp.close(); break
        ev = json.loads(line)
        if ttft is None and ev.get("response"):
            ttft = time.perf_counter() - t0
            s = smi(); peak = max(peak, s.get("vram_used_mib", 0))
        if ev.get("done"):
            final = ev
    wall = time.perf_counter() - t0
    during = {**smi(), **meminfo()}
    try:
        ps = json.loads(urllib.request.urlopen(OLLAMA + "/api/ps").read())["models"]
        size_vram = ps[0].get("size_vram") if ps else None; size = ps[0].get("size") if ps else None
    except Exception:
        size_vram = size = None
    ec, ed = final.get("eval_count", 0), final.get("eval_duration", 1)
    pc, pd = final.get("prompt_eval_count", 0), final.get("prompt_eval_duration", 1)
    row = {**cfg, "timed_out": timed_out, "first_token_s": round(ttft or -1, 3), "wall_s": round(wall, 2),
           "load_s": round(final.get("load_duration", 0) / 1e9, 2),
           "decode_tok_s": round(ec / (ed / 1e9), 2) if ed else None, "eval_count": ec,
           "prompt_tok_s": round(pc / (pd / 1e9), 2) if pd else None, "prompt_count": pc,
           "ollama_size_mib": size // 2**20 if size else None, "ollama_size_vram_mib": size_vram // 2**20 if size_vram is not None else None,
           "vram_before_mib": before.get("vram_used_mib"), "vram_during_mib": during.get("vram_used_mib"), "vram_peak_seen_mib": peak,
           "ram_avail_before_mib": before.get("MemAvailable"), "ram_avail_during_mib": during.get("MemAvailable"),
           "swap_free_during_mib": during.get("SwapFree")}
    rows.append(row); print(json.dumps(row), flush=True)
unload()
time.sleep(2)
print(json.dumps({"after_unload": {**smi(), **meminfo()}}), flush=True)
json.dump({"model": MODEL, "rows": rows, "host": {"gpu": "RTX 3050 6GB Laptop", "cpu": "Ryzen 5 150 (12 threads)"}}, open(sys.argv[2] if len(sys.argv) > 2 else "placement_results.json", "w"), indent=1)
