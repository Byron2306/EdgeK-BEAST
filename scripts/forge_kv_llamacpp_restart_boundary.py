#!/usr/bin/env python3
"""Prove llama.cpp prompt cache is local to one server lifetime, not portable KV."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path("/home/byron/.local/lib/beast/llama.cpp-a582222")
DEFAULT_MODEL = Path("/home/byron/.ollama/models/blobs/sha256-c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515")


def timing(payload: dict) -> dict[str, int | float]:
    values = payload.get("timings") or {}
    return {"cache_n": int(values.get("cache_n") or 0), "prompt_n": int(values.get("prompt_n") or 0),
            "prompt_ms": float(values.get("prompt_ms") or 0.0)}


def completion(client: httpx.Client, url: str, prompt: str, cache_prompt: bool) -> dict[str, int | float]:
    response = client.post(f"{url}/completion", json={"prompt": prompt, "n_predict": 8,
                           "temperature": 0, "seed": 731947, "cache_prompt": cache_prompt, "stream": False})
    response.raise_for_status()
    return timing(response.json())


def wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"llama.cpp exited early: {process.returncode}")
            try:
                if client.get(f"{url}/health").is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
    raise TimeoutError("llama.cpp did not become ready")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(server_bin: Path, model: Path, port: int, library_dir: Path) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = str(library_dir) + (":" + environment["LD_LIBRARY_PATH"] if environment.get("LD_LIBRARY_PATH") else "")
    return subprocess.Popen([str(server_bin), "--model", str(model), "--host", "127.0.0.1", "--port", str(port),
                             "--ctx-size", "4096", "--parallel", "1", "--cache-prompt", "--cache-reuse", "64"],
                            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11436)
    parser.add_argument("--llama-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    server_bin = args.llama_root / "bin" / "llama-server"
    library_dir = args.llama_root / "lib"
    if not server_bin.is_file() or not args.model.is_file() or not library_dir.is_dir():
        raise SystemExit("local llama.cpp binary, libraries, or model are unavailable")
    url = f"http://127.0.0.1:{args.port}"
    prefix = ("BEAST restart-boundary cache proof. " * 80).strip()
    continuation = "\nQuestion: State cache scope in two words."
    first: subprocess.Popen[bytes] | None = None
    second: subprocess.Popen[bytes] | None = None
    try:
        first = start(server_bin, args.model, args.port, library_dir)
        wait_ready(url, first)
        with httpx.Client(timeout=120) as client:
            baseline = completion(client, url, prefix + continuation, cache_prompt=False)
            completion(client, url, prefix + "\nQuestion: Reply READY.", cache_prompt=True)
            warm = completion(client, url, prefix + continuation, cache_prompt=True)
        stop(first); first = None
        second = start(server_bin, args.model, args.port, library_dir)
        wait_ready(url, second)
        with httpx.Client(timeout=120) as client:
            after_restart = completion(client, url, prefix + continuation, cache_prompt=True)
    except (httpx.HTTPError, OSError, RuntimeError, TimeoutError) as exc:
        print(json.dumps({"validated": False, "reason": "llamacpp_restart_boundary_unavailable", "error": str(exc)}))
        return 2
    finally:
        if first is not None: stop(first)
        if second is not None: stop(second)
    validated = (warm["cache_n"] > 0 and warm["prompt_n"] < baseline["prompt_n"]
                 and after_restart["cache_n"] == 0 and after_restart["prompt_n"] >= baseline["prompt_n"] * 0.9)
    receipt = {
        "beast_object_type": "forge_kv_llamacpp_restart_boundary_proof", "version": "1.0",
        "validated": validated,
        "proof_scope": "Local llama.cpp prompt cache across a controlled server restart; no raw KV export.",
        "authority": "engine_local_prompt_cache_only", "portable_raw_kv": False,
        "before_restart": {"baseline": baseline, "warm_cache": warm}, "after_restart": after_restart,
        "prefix_digest": "sha256:" + hashlib.sha256(prefix.encode()).hexdigest(), "created_at": time.time(),
    }
    if not validated:
        receipt["failure_reason"] = "warm hit or restart cold-boundary metric did not match the declared scope"
        print(json.dumps(receipt, sort_keys=True))
        return 1
    destination = ROOT / "evidence" / "forge_kv" / f"llamacpp_restart_boundary_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validated": True, "receipt": str(destination), "result": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
