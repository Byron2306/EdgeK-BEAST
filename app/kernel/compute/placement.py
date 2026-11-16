"""Hybrid CPU/RAM/VRAM placement planner for local model calls.

Decides, per request, where a local model's weights and KV cache should live:
all layers on the GPU, a hybrid split (``num_gpu`` layers on the RTX 3050,
the rest on the Ryzen CPU / system RAM), CPU only, or "do not run locally"
(route to cloud) when the host would swap-thrash.

Inputs are live pressure (nvidia-smi free VRAM, /proc/meminfo MemAvailable and
swap) and the capability scorecard's placement dimension.  The output maps to
Ollama request options (``num_gpu``, ``num_ctx``) and records the placement
label used as the scorecard's 4th key ("gpu_full", "hybrid:<n>", "cpu",
"cloud").  KV-cache quantisation (``OLLAMA_KV_CACHE_TYPE=q8_0`` with
``OLLAMA_FLASH_ATTENTION=1``) and MoE expert offload (llama.cpp
``--n-cpu-moe`` / ``-ot exps=CPU``) are server-level settings, so they are
reported as recommendations, not per-request options.
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ModelShape:
    name: str
    weights_mib: int          # on-disk quantised weights
    n_layers: int             # transformer blocks (+1 output layer counted separately by llama.cpp)
    kv_kib_per_token: float   # fp16 KV per token across all layers (GQA aware)
    moe: bool = False
    # Measured on this host (RTX 3050 6GB, Ollama 0.40.5, ctx 2048, f16 KV): VRAM ~= overhead + layers * layer_mib.
    measured_layer_mib: float = 0.0
    measured_overhead_mib: float = 0.0


# Approximate shapes (fp16 KV) for models BEAST uses locally.
SHAPES: Dict[str, ModelShape] = {
    "qwen2.5-coder:7b": ModelShape("qwen2.5-coder:7b", 4460, 28, 56.0, False, 133.4, 546.0),  # 28 L x 4 KV x 128 x 2 x 2B; calibrated 2026-11-16 (6L=1346, 18L=2947, 29L=4421 MiB)
    "qwen3:4b": ModelShape("qwen3:4b", 2440, 36, 144.0, False, 68.0, 429.0),  # 36 L x 8 KV heads x 128 x 2 x 2B; calibrated 2026-11-16 closure (2L=565, 8L=973 MiB delta)
    "granite3.3:2b": ModelShape("granite3.3:2b", 1480, 40, 80.0, False, 39.2, 222.0),  # calibrated 2026-11-16 closure (4L=379, 16L=849 MiB delta)
    "granite3.2:2b": ModelShape("granite3.2:2b", 1480, 40, 80.0, False, 39.2, 222.0),  # same architecture/size as granite3.3:2b; inferred, not separately measured
}


def probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        line = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
                                       text=True, timeout=5).strip().splitlines()[0]
        total, used = [int(x) for x in line.split(",")]
        out.update(vram_total_mib=total, vram_used_mib=used, vram_free_mib=total - used)
    except Exception as exc:  # no NVIDIA GPU or driver
        out.update(vram_total_mib=0, vram_used_mib=0, vram_free_mib=0, gpu_error=type(exc).__name__)
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for raw in handle:
                key, value = raw.split(":", 1)
                info[key] = int(value.split()[0]) // 1024
        out.update(ram_total_mib=info.get("MemTotal", 0), ram_available_mib=info.get("MemAvailable", 0),
                   swap_total_mib=info.get("SwapTotal", 0), swap_free_mib=info.get("SwapFree", 0))
    except OSError:
        pass
    return out


def plan(model: str, *, num_ctx: int = 2048, pressure: Optional[Mapping[str, Any]] = None, vram_reserve_mib: int = 384,
         ram_reserve_mib: int = 1024, kv_quant: str = "f16", shape: Optional[ModelShape] = None) -> Dict[str, Any]:
    """Return a placement decision for ``model`` given live ``pressure``."""
    pressure = dict(pressure if pressure is not None else probe())
    shape = shape or SHAPES.get(model)
    if shape is None:
        return {"model": model, "placement": "unknown", "reason": "no_shape_for_model", "options": {}}
    kv_factor = {"f16": 1.0, "q8_0": 0.5, "q4_0": 0.25}.get(kv_quant, 1.0)
    kv_mib = shape.kv_kib_per_token * num_ctx * kv_factor / 1024.0
    per_layer = shape.weights_mib / (shape.n_layers + 1)
    kv_per_layer = kv_mib / shape.n_layers
    compute_buf = 300.0  # llama.cpp CUDA compute buffer, rough
    if shape.measured_layer_mib > 0:
        # measured slope already includes that layer's KV at ctx 2048; scale KV share for other contexts / quant
        kv_2048 = shape.kv_kib_per_token * 2048 / 1024.0 / shape.n_layers
        per_layer = shape.measured_layer_mib - kv_2048
        compute_buf = shape.measured_overhead_mib
    vram_free = float(pressure.get("vram_free_mib", 0)) - vram_reserve_mib - compute_buf
    fit_layers = int(max(0.0, vram_free) // (per_layer + kv_per_layer)) if vram_free > 0 else 0
    fit_layers = min(fit_layers, shape.n_layers + 1)
    cpu_layers = (shape.n_layers + 1) - fit_layers
    ram_need = cpu_layers * per_layer + (shape.n_layers - min(fit_layers, shape.n_layers)) * kv_per_layer
    ram_avail = float(pressure.get("ram_available_mib", 0)) - ram_reserve_mib
    if fit_layers >= shape.n_layers + 1:
        placement = "gpu_full"
    elif fit_layers == 0:
        placement = "cpu"
    else:
        placement = f"hybrid:{fit_layers}"
    thrash = ram_need > max(0.0, ram_avail)
    decision = {
        "model": model, "num_ctx": num_ctx, "kv_quant": kv_quant, "placement": "cloud" if thrash else placement,
        "local_placement": placement, "num_gpu": fit_layers, "layers_total": shape.n_layers + 1,
        "est_vram_mib": round(fit_layers * (per_layer + kv_per_layer) + (compute_buf if fit_layers else 0)),
        "est_ram_mib": round(ram_need), "kv_cache_mib": round(kv_mib, 1),
        "reason": (f"ram_pressure: needs ~{ram_need:.0f} MiB RAM, only {max(0.0, ram_avail):.0f} MiB available "
                   "after reserve; local run would swap-thrash") if thrash else "fits",
        "options": {} if thrash else {"num_gpu": fit_layers, "num_ctx": num_ctx},
        "pressure": {k: pressure.get(k) for k in ("vram_free_mib", "ram_available_mib", "swap_free_mib")},
        "recommendations": [],
    }
    if kv_quant == "f16" and kv_mib > 128:
        decision["recommendations"].append("server: OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 halves KV memory")
    if shape.moe:
        decision["recommendations"].append("llama-server --n-cpu-moe N keeps attention on GPU, experts on CPU")
    return decision


def shape_dict(model: str) -> Dict[str, Any]:
    shape = SHAPES.get(model)
    return asdict(shape) if shape else {}


__all__ = ["ModelShape", "SHAPES", "plan", "probe", "shape_dict"]
