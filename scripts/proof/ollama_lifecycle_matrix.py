#!/usr/bin/env python3
"""Diagnose Ollama 3B lifecycle stability independently of BEAST execution."""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def json_post(model: str, prompt: str, num_ctx: int, timeout: float) -> dict:
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json", "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": 64, "num_thread": 2, "num_batch": 128}}
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode())
    return {"response_present": bool(body.get("response")), "prompt_eval_count": body.get("prompt_eval_count"), "eval_count": body.get("eval_count"), "total_duration_ns": body.get("total_duration"), "load_duration_ns": body.get("load_duration"), "prompt_eval_duration_ns": body.get("prompt_eval_duration"), "eval_duration_ns": body.get("eval_duration")}


def health() -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5) as response:
            body = json.loads(response.read().decode())
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "models": [item.get("name") for item in body.get("models", [])]}
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error": f"{type(exc).__name__}: {exc}"}


def runner_snapshot(model: str) -> dict:
    rows = []
    try:
        output = subprocess.run(["pgrep", "-af", "ollama runner"], capture_output=True, text=True, check=False).stdout
        for line in output.splitlines():
            pid = int(line.split()[0])
            status = Path(f"/proc/{pid}/status")
            rss = next((int(item.split()[1]) for item in status.read_text().splitlines() if item.startswith("VmRSS:")), 0) * 1024 if status.exists() else 0
            rows.append({"pid": pid, "rss_bytes": rss, "cmd": line[-400:]})
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "runners": []}
    pressure = {}
    for name in ("memory", "cpu", "io"):
        path = Path(f"/proc/pressure/{name}")
        if path.exists():
            pressure[name] = path.read_text().strip()
    return {"model": model, "runners": rows, "pressure": pressure}


def stop_model(model: str) -> dict:
    result = subprocess.run(["ollama", "stop", model], capture_output=True, text=True, timeout=30, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}


def worker(model: str, prompt: str, num_ctx: int, timeout: float) -> int:
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    try:
        body = json_post(model, prompt, num_ctx, timeout)
        result = {"status": "response", "body": body}
    except urllib.error.HTTPError as exc:
        result = {"status": "http_error", "error": f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:800]}"}
    except Exception as exc:
        result = {"status": "transport_error", "error": f"{type(exc).__name__}: {exc}"}
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    result["wall_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["process_cpu_seconds"] = round((cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime), 6)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] == "response" else 2


def run_case(model: str, name: str, prompt: str, num_ctx: int, timeout: float, restart: bool) -> dict:
    if restart:
        stop = stop_model(model)
        time.sleep(1)
    else:
        stop = None
    before = {"health": health(), "runner": runner_snapshot(model)}
    started = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--model", model, "--ctx", str(num_ctx), "--timeout", str(timeout), "--prompt", prompt]
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout + 10, check=False)
        worker_result = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.stdout.strip() else {"status": "no_worker_output"}
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        worker_result = {"status": "worker_timeout", "stdout": str(exc.stdout or "")[-800:]}
        timed_out = True
    after = {"health": health(), "runner": runner_snapshot(model)}
    status = worker_result.get("status")
    if timed_out:
        classification = "worker_timeout"
    elif status == "response":
        classification = "healthy_response"
    elif not after["health"].get("ok"):
        classification = "runtime_crash_or_unavailable"
    else:
        classification = "provider_transport_failure"
    return {"name": name, "context": num_ctx, "restart": restart, "stop": stop, "classification": classification, "worker": worker_result, "before": before, "after": after, "wall_ms": round((time.perf_counter() - started) * 1000, 2)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"))
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--output", default="benchmarks/results/ollama_lifecycle_matrix.json")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--ctx", type=int, default=1024)
    parser.add_argument("--prompt", default="Return JSON with one field s set to ok.")
    args = parser.parse_args()
    if args.worker:
        return worker(args.model, args.prompt, args.ctx, args.timeout)
    started = time.perf_counter()
    prompt = "Return JSON with one field s set to ok. Do not explain."
    cases = [
        ("cold_ctx512", 512, True),
        ("warm_ctx512", 512, False),
        ("warm_ctx768", 768, False),
        ("warm_ctx1024", 1024, False),
        ("restart_ctx1024", 1024, True),
    ]
    rows = [run_case(args.model, name, prompt, ctx, args.timeout, restart) for name, ctx, restart in cases]
    receipt = {"beast_object_type": "ollama_lifecycle_matrix_receipt", "version": "1.0", "model": args.model, "cases": rows, "summary": {"healthy": sum(row["classification"] == "healthy_response" for row in rows), "timeouts": sum(row["classification"] == "worker_timeout" for row in rows), "runtime_crashes": sum(row["classification"] == "runtime_crash_or_unavailable" for row in rows), "transport_failures": sum(row["classification"] == "provider_transport_failure" for row in rows), "wall_seconds": round(time.perf_counter() - started, 3)}}
    receipt["receipt_hash"] = "sha256:" + __import__("hashlib").sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pack = output.with_name(output.stem + "_pack")
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "matrix_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (pack / "README.md").write_text("# Ollama Lifecycle Matrix\n\nThis isolates model lifecycle stability from BEAST coding correctness.\n", encoding="utf-8")
    manifest = {"beast_object_type": "ollama_lifecycle_integrity_manifest", "files": {path.name: "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest() for path in pack.iterdir() if path.is_file()}}
    (pack / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(pack.with_suffix(".zip"), "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in pack.iterdir():
            if path.is_file(): bundle.write(path, path.name)
    print(json.dumps({"path": str(output), "receipt_hash": receipt["receipt_hash"], "summary": receipt["summary"], "pack": str(pack)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
