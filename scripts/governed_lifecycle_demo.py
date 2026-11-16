#!/usr/bin/env python3
"""Live demo: a stalled local generation is detected and torn down, VRAM reclaimed.

1. ProcessLifecycle spawns a BEAST-owned llama-server (Ollama's bundled binary, a
   0.5B GGUF fully offloaded to the RTX 3050) inside its own systemd --user scope.
2. The governed client streams a schema-forced request from it.
3. After the first chunks arrive the server is frozen with SIGSTOP (injected hang:
   the same symptom as a wedged CUDA kernel or deadlocked server).
4. The client's inter-chunk stall timer fires; the lifecycle layer verifies
   ownership (pidfd + start time + cgroup), sends SIGTERM via pidfd, escalates to
   SIGKILL after the grace period, writes cgroup.kill, closes fds, and measures
   VRAM before/after with nvidia-smi.  Every step lands in the receipt chain.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.capability_scorecard import CapabilityScorecard  # noqa: E402
from app.kernel.compute.governed_client import Candidate, GovernedModelClient  # noqa: E402
from app.kernel.execution.process_lifecycle import ProcessLifecycle, gpu_memory_by_pid, gpu_used_total_mib  # noqa: E402
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog  # noqa: E402

GGUF = Path.home() / ".cache" / "beast-gguf" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
SERVER = "/usr/local/lib/ollama/llama-server"
OUT = ROOT / "evidence" / "governed-interception-2026-11-16" / "lifecycle"
SCHEMA = {"type": "object", "properties": {"story": {"type": "array", "items": {"type": "string"}, "minItems": 400}},
          "required": ["story"]}


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ["BEAST_PROCESS_LIFECYCLE"] = "1"
    receipts = GovernorReceiptLog(ROOT / ".beast" / "governed-interception" / f"lifecycle-receipts-{time.strftime('%Y%m%dT%H%M%S')}.jsonl")
    life = ProcessLifecycle(receipts=receipts)
    port = free_port()
    gpu_before_spawn = gpu_used_total_mib()
    cuda_dir = "/usr/local/lib/ollama/cuda_v13"  # Ollama's bundled ggml CUDA backend (driver UMD 13.x)
    env = {**os.environ, "LD_LIBRARY_PATH": f"{cuda_dir}:/usr/local/lib/ollama:" + os.environ.get("LD_LIBRARY_PATH", ""),
           "GGML_BACKEND_PATH": f"{cuda_dir}/libggml-cuda.so"}
    log = open(OUT / "llama-server.log", "w")
    handle = life.spawn([SERVER, "--model", str(GGUF), "--host", "127.0.0.1", "--port", str(port), "-ngl", "99", "-c", "4096",
                         "-np", "1", "--no-webui", "--offline", "--no-jinja", "--chat-template", "chatml"],
                        label="llama-server:qwen2.5-0.5b", env=env, stdout=log, stderr=subprocess.STDOUT)
    import urllib.request
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).status == 200:
                break
        except Exception:
            time.sleep(1)
    time.sleep(1)
    loaded = {"pid": handle.pid, "cgroup": handle.cgroup, "beast_scope": handle.beast_scope,
              "gpu_used_before_spawn_mib": gpu_before_spawn, "gpu_used_loaded_mib": gpu_used_total_mib(),
              "server_vram_mib": gpu_memory_by_pid().get(handle.pid, 0)}
    print(json.dumps({"loaded": loaded}), flush=True)
    cand = Candidate(provider="llamacpp-owned", model="qwen2.5-0.5b", kind="openai", base_url=f"http://127.0.0.1:{port}/v1",
                     placement="gpu_full", rung="local_specialist", max_tokens=4000, ttft_timeout_s=60, stall_timeout_s=4)
    client = GovernedModelClient([cand], scorecard=CapabilityScorecard(OUT / "demo-scorecard.json"),
                                 governor=ComputeGovernorSpine(receipts=receipts, enforce=True), use_scorecard=False,
                                 lifecycle=life, lifecycle_handles={cand.ident: handle}, max_attempts=1)

    async def freeze_after_first_tokens():
        await asyncio.sleep(2.0)
        os.kill(handle.pid, signal.SIGSTOP)  # injected hang (pid is ours, verified at spawn)
        return time.time()

    async def run():
        freezer = asyncio.create_task(freeze_after_first_tokens())
        res = await client.complete(family="lifecycle-demo",
                                    messages=[{"role": "user", "content": "Write a 400-sentence story as JSON {\"story\": [...]}."}],
                                    schema=SCHEMA, verify=lambda v: {"passed": True}, run_id="lifecycle-demo")
        return res, await freezer

    res, frozen_at = asyncio.run(run())
    call = res.calls[0].public()
    time.sleep(1)
    summary = {"loaded": loaded, "frozen_at": frozen_at, "call": call,
               "gpu_used_after_teardown_mib": gpu_used_total_mib(),
               "server_alive_after": os.path.exists(f"/proc/{handle.pid}"),
               "receipt_chain": receipts.verify(),
               "teardown_receipt": [r for r in receipts.records() if r.get("type") == "process_teardown"][-1:]}
    (OUT / "lifecycle_demo.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0 if call["status"] == "stream_stall" and not summary["server_alive_after"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
