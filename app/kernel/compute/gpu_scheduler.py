"""GPU self-scheduling between local TGI and Ollama on one 6 GB RTX 3050 (``BEAST_GPU_SCHEDULER``, default on
whenever governed interception is on; set ``BEAST_GPU_SCHEDULER=0`` to disable).

TGI (container ``beast-tgi``) pre-allocates most of the VRAM for its continuous-batching KV pool, so a GPU Ollama
model loaded next to it is either refused, squeezed into a slow hybrid split, or evicts nothing and thrashes. The
scheduler therefore treats the GPU as one exclusive local lane:

* ``state()``      -- nvidia-smi VRAM + compute apps, TGI ``/health``, Ollama ``/api/ps`` (loaded models, VRAM share).
* ``owner()``      -- ``tgi`` when TGI is healthy (it holds the VRAM), else ``ollama`` (or ``none``).
* ``local_candidates(cands)`` -- filters a governed candidate list: with TGI up, GPU Ollama candidates are dropped
  (or re-planned onto CPU by ``placement.plan`` only if RAM allows and the caller opts in) and TGI goes first;
  with TGI down, TGI is dropped and Ollama keeps the GPU.
* ``prepare_tgi_batch()`` -- before a TGI batch, unload every Ollama model (``keep_alive: 0``; an API call, never a
  service restart) and report the VRAM freed; refuses to touch anything else.
* ``prepare_ollama(model)`` -- placement plan for an Ollama call given the current owner (TGI up => CPU/hybrid/cloud).

BEAST never starts/stops the ``beast-tgi`` container itself (operator-owned); ``operator_commands()`` lists them.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
TGI = os.environ.get("TGI_BASE_URL", "http://127.0.0.1:8090").rstrip("/")


def enabled(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    raw = str(env.get("BEAST_GPU_SCHEDULER", "")).strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return raw in {"1", "true", "yes", "on"} or str(env.get("BEAST_GOVERNED_INTERCEPTION", "")).strip().lower() in {"1", "true", "yes", "on"}


def _get(url: str, timeout: float = 2.0) -> Optional[Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - loopback
            body = r.read().decode("utf-8") or "{}"
            return json.loads(body) if body.strip().startswith(("{", "[")) else {"_status": r.status}
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _post(url: str, payload: Dict[str, Any], timeout: float = 30.0) -> Optional[Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - loopback
            text = r.read().decode("utf-8")
            return json.loads(text.strip().splitlines()[-1]) if text.strip() else {}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"error": type(exc).__name__}


def vram() -> Dict[str, Any]:
    try:
        line = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
                                       text=True, timeout=5).strip().splitlines()[0]
        total, used = [int(x) for x in line.split(",")]
        apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                                       text=True, timeout=5).strip().splitlines()
        return {"total_mib": total, "used_mib": used, "free_mib": total - used,
                "apps": [{"pid": int(a.split(",")[0]), "mib": int(a.split(",")[1])} for a in apps if a.strip()]}
    except Exception as exc:  # noqa: BLE001 - no GPU / driver
        return {"total_mib": 0, "used_mib": 0, "free_mib": 0, "apps": [], "error": type(exc).__name__}


def tgi_healthy(base: str = TGI) -> bool:
    try:
        with urllib.request.urlopen(base + "/health", timeout=1.5) as r:  # noqa: S310
            return r.status == 200
    except (OSError, urllib.error.URLError):
        return False


def ollama_loaded(base: str = OLLAMA) -> List[Dict[str, Any]]:
    ps = _get(base + "/api/ps") or {}
    return [{"name": m.get("name"), "size_vram_mib": int(m.get("size_vram", 0)) // 2**20, "size_mib": int(m.get("size", 0)) // 2**20,
             "expires_at": m.get("expires_at")} for m in ps.get("models", [])]


def state() -> Dict[str, Any]:
    tgi = tgi_healthy()
    loaded = ollama_loaded()
    return {"at": time.time(), "vram": vram(), "tgi_healthy": tgi, "ollama_loaded": loaded,
            "owner": "tgi" if tgi else ("ollama" if any(m["size_vram_mib"] for m in loaded) else "none")}


def owner() -> str:
    return "tgi" if tgi_healthy() else "ollama"


def local_candidates(cands: Sequence[Any], *, tgi_up: Optional[bool] = None, allow_cpu_ollama: bool = False) -> List[Any]:
    """GPU-exclusive local lane: TGI first when healthy (GPU Ollama dropped), else Ollama keeps the GPU (TGI dropped)."""
    tgi_up = tgi_healthy() if tgi_up is None else tgi_up
    tgi = [c for c in cands if getattr(c, "provider", "") == "tgi"]
    ollama = [c for c in cands if getattr(c, "provider", "") == "ollama"]
    rest = [c for c in cands if getattr(c, "provider", "") not in {"tgi", "ollama"}]
    if tgi_up:
        keep: List[Any] = []
        if allow_cpu_ollama:
            keep = [replace(c, placement="cpu", options={**dict(c.options or {}), "options": {"num_gpu": 0}}) for c in ollama]
        return [*tgi, *keep, *rest]
    return [*ollama, *rest]


def prepare_tgi_batch(*, base: str = OLLAMA, settle_s: float = 1.5) -> Dict[str, Any]:
    """Unload every Ollama model (keep_alive 0) so TGI's batch has the GPU; returns before/after VRAM."""
    before = vram()
    loaded = ollama_loaded(base)
    unloaded = []
    for m in loaded:
        res = _post(base + "/api/generate", {"model": m["name"], "keep_alive": 0, "prompt": "", "stream": False}, timeout=30)
        unloaded.append({"model": m["name"], "vram_mib": m["size_vram_mib"], "ok": not (res or {}).get("error")})
    if unloaded:
        time.sleep(settle_s)
    after = vram()
    return {"action": "prepare_tgi_batch", "unloaded": unloaded, "vram_used_before_mib": before.get("used_mib"),
            "vram_used_after_mib": after.get("used_mib"), "freed_mib": (before.get("used_mib") or 0) - (after.get("used_mib") or 0),
            "tgi_healthy": tgi_healthy()}


_LAST_PREPARE: Dict[str, float] = {"at": 0.0}


def ensure_tgi_gpu(*, base: str = OLLAMA, min_interval_s: float = 5.0, loaded: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Cheap pre-call hook for a TGI batch: unload only GPU-resident Ollama models, at most once per ``min_interval_s``."""
    now = time.time()
    if now - _LAST_PREPARE["at"] < min_interval_s:
        return {"action": "skip", "reason": "throttled"}
    _LAST_PREPARE["at"] = now
    loaded = ollama_loaded(base) if loaded is None else loaded
    on_gpu = [m for m in loaded if m.get("size_vram_mib")]
    if not on_gpu:
        return {"action": "none", "reason": "no_gpu_resident_ollama_models"}
    unloaded = []
    for m in on_gpu:
        res = _post(base + "/api/generate", {"model": m["name"], "keep_alive": 0, "prompt": "", "stream": False}, timeout=30)
        unloaded.append({"model": m["name"], "vram_mib": m["size_vram_mib"], "ok": res is not None and not (res or {}).get("error")})
    return {"action": "unloaded", "unloaded": unloaded, "freed_est_mib": sum(m["vram_mib"] for m in unloaded if m["ok"])}


def prepare_ollama(model: str, *, num_ctx: int = 2048) -> Dict[str, Any]:
    from app.kernel.compute import placement

    pressure = placement.probe()
    decision = placement.plan(model, num_ctx=num_ctx, pressure=pressure)
    decision["gpu_owner"] = owner()
    if decision["gpu_owner"] == "tgi" and decision.get("placement", "").startswith(("gpu_full", "hybrid")):
        decision["note"] = "TGI holds the GPU: GPU Ollama would squeeze into the leftover VRAM; prefer TGI or cloud"
    return decision


def operator_commands() -> Dict[str, str]:
    return {"pause_tgi_for_ollama": "docker stop beast-tgi", "resume_tgi": "docker start beast-tgi",
            "tgi_health": f"curl -s {TGI}/health -o /dev/null -w '%{{http_code}}\\n'"}


__all__ = ["enabled", "ensure_tgi_gpu", "local_candidates", "operator_commands", "owner", "prepare_ollama", "prepare_tgi_batch", "state", "vram"]
