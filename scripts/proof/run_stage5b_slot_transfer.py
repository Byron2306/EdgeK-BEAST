"""Compare cold prefill against actual llama.cpp slot restore in a fresh process."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import httpx

REVISION = "a5822222909b785f23ddc74ce3c8f85bd0e38562"
MODEL_SHA256 = "c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515"
FILENAME = "stage5b-slot.bin"
PREFIX = ("BEAST restart-boundary cache proof. " * 80).strip()
PRIME = PREFIX + "\nQuestion: Reply READY."
PROBE = PREFIX + "\nQuestion: State cache scope in two words."


def file_digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def digest_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def natural(body, key):
    value = body.get(key)
    if type(value) is not int or value < 0:
        raise ValueError(f"missing or invalid {key}")
    return value


def completion_record(body):
    timings = body.get("timings") or {}
    text, tokens = body.get("content"), body.get("tokens")
    if not isinstance(text, str) or not isinstance(tokens, list) or not tokens or any(type(x) is not int for x in tokens):
        raise ValueError("completion missing text or generated token IDs")
    ms = timings.get("prompt_ms")
    if type(ms) not in {int, float} or not 0 <= ms < float("inf"):
        raise ValueError("missing or invalid prompt_ms")
    return {"cache_n": natural(timings, "cache_n"), "prompt_n": natural(timings, "prompt_n"),
            "prompt_ms": ms, "content_sha256": digest_bytes(text.encode()),
            "tokens_sha256": digest_bytes(json.dumps(tokens, separators=(",", ":")).encode()),
            "output_tokens": len(tokens)}


class Worker:
    def __init__(self, pid, port, client):
        self.pid, self.port, self.client = pid, port, client
        self.url = f"http://127.0.0.1:{port}"

    def completion(self, prompt):
        response = self.client.post(self.url + "/completion", json={
            "prompt": prompt, "id_slot": 0, "n_predict": 8, "temperature": 0,
            "seed": 731947, "cache_prompt": True, "stream": False, "return_tokens": True,
        })
        response.raise_for_status()
        return completion_record(response.json())

    def slot(self, action):
        response = self.client.post(self.url + f"/slots/0?action={action}", json={"filename": FILENAME})
        response.raise_for_status()
        body = response.json()
        if body.get("id_slot") != 0 or body.get("filename") != FILENAME:
            raise ValueError("slot receipt does not match the request")
        keys = ("n_saved", "n_written") if action == "save" else ("n_restored", "n_read")
        return {**{key: natural(body, key) for key in keys}, "timings": body.get("timings", {})}


def free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def owns_listener(pid, port):
    target = f"0100007F:{port:04X}"
    listeners = set()
    with Path("/proc/net/tcp").open() as handle:
        next(handle)
        for line in handle:
            fields = line.split()
            if fields[1] == target and fields[3] == "0A":
                listeners.add(f"socket:[{fields[9]}]")
    try:
        for fd in (Path("/proc") / str(pid) / "fd").iterdir():
            try:
                if os.readlink(fd) in listeners:
                    return True
            except FileNotFoundError:
                continue
    except FileNotFoundError:
        return False
    return False


def environment(lib):
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ") if key in os.environ}
    env["LD_LIBRARY_PATH"] = str(lib)
    return env


def make_backend(binary, model, lib):
    @contextmanager
    def start(role, directory, log):
        directory.mkdir(exist_ok=True)
        port = free_loopback_port()
        with log.open("wb") as output:
            child = subprocess.Popen([
                str(binary), "--model", str(model), "--host", "127.0.0.1", "--port", str(port),
                "--ctx-size", "4096", "--parallel", "1", "--n-gpu-layers", "0",
                "--cache-prompt", "--cache-reuse", "64", "--slot-save-path", str(directory),
            ], stdout=output, stderr=subprocess.STDOUT, env=environment(lib), cwd=directory)
            try:
                url = f"http://127.0.0.1:{port}"
                with httpx.Client(trust_env=False, timeout=120) as client:
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        if child.poll() is not None:
                            raise RuntimeError(f"{role} process exited ({child.returncode})")
                        try:
                            if owns_listener(child.pid, port) and client.get(url + "/health", timeout=2).is_success:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise TimeoutError(f"{role} server did not become ready")
                    yield Worker(child.pid, port, client)
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
    return start


def run_trial(out, repeat, backend):
    trial = out / f"trial-{repeat:02d}"
    trial.mkdir()
    pids = {}
    with tempfile.TemporaryDirectory(prefix="slot-state-", dir=trial) as d:
        state = Path(d)
        dirs = {name: state / name for name in ("donor", "cold", "restored")}
        with backend("donor", dirs["donor"], trial / "donor.log") as worker:
            pids["donor"] = worker.pid
            primed = worker.completion(PRIME)
            save = worker.slot("save")
            source = dirs["donor"] / FILENAME
            size = source.stat().st_size
            source_sha = file_digest(source)
            warm = worker.completion(PROBE)
        if not size or save["n_saved"] == 0 or save["n_written"] != size:
            raise ValueError("donor did not save a complete nonempty slot")
        dirs["restored"].mkdir()
        target = dirs["restored"] / FILENAME
        started = time.perf_counter_ns()
        shutil.copyfile(source, target)
        copy_ms = (time.perf_counter_ns() - started) / 1e6
        destination_sha = file_digest(target)
        if source_sha != destination_sha or target.stat().st_size != size:
            raise ValueError("copied slot failed size or digest verification")

        order = ["cold", "restored"] if repeat % 2 else ["restored", "cold"]
        result = {}
        for role in order:
            with backend(role, dirs[role], trial / (role + ".log")) as worker:
                pids[role] = worker.pid
                if role == "restored":
                    restore = worker.slot("restore")
                result[role] = worker.completion(PROBE)  # First and only completion in each receiver.

    cold, restored = result["cold"], result["restored"]
    checks = {
        "distinct_processes": len(set(pids.values())) == 3,
        "donor_cold_then_warm": primed["cache_n"] == 0 and warm["cache_n"] > 0,
        "cold_control_recomputed": cold["cache_n"] == 0 and cold["prompt_n"] > 0,
        "restore_acknowledged": restore["n_restored"] == save["n_saved"] and restore["n_read"] == size,
        "destination_consumed_cache": 0 < restored["cache_n"] <= restore["n_restored"]
            and restored["prompt_n"] < cold["prompt_n"],
        "matched_prompt_accounting": restored["cache_n"] + restored["prompt_n"] == cold["prompt_n"],
        "output_equivalent": all(cold[k] == restored[k] for k in ("content_sha256", "tokens_sha256", "output_tokens")),
    }
    report = {"repeat": repeat, "validated": all(checks.values()), "checks": checks, "pids": pids,
              "receiver_order": order, "donor_prime": primed, "donor_warm": warm,
              "save": save, "restore": restore, **result,
              "transfer": {"mode": "local_file_copy", "bytes": size, "sha256_match": True,
                           "source_sha256": source_sha, "destination_sha256": destination_sha, "copy_ms": copy_ms}}
    write_json(trial / "receipt.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--llama-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args(argv)
    binary = (args.llama_root / "bin" / "llama-server").resolve()
    lib = (args.llama_root / "lib").resolve()
    model = args.model.resolve()
    if not binary.is_file() or not model.is_file() or not lib.is_dir():
        parser.error("missing llama-server, library directory or GGUF")
    binary_hash, gguf_hash = file_digest(binary), file_digest(model)
    if binary_hash != args.expected_binary_sha256 or gguf_hash != MODEL_SHA256:
        parser.error("binary or GGUF digest differs from the pinned input")
    version = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                             timeout=10, check=True, env=environment(lib))
    version_text = (version.stdout + version.stderr).strip()
    if REVISION[:7] not in version_text:
        parser.error(f"llama-server build version did not identify {REVISION[:7]}")
    out = args.out.resolve()
    out.mkdir(parents=True)
    write_json(out / "plan.json", {
        "schema": "beast.stage5b.slot_transfer.v1", "expected_llamacpp_revision": REVISION,
        "server_reported_version": version_text, "server_sha256": binary_hash, "model_sha256": gguf_hash,
        "shared_lib_sha256": {p.name: file_digest(p.resolve()) for p in sorted(lib.glob("*.so*")) if p.is_file()},
        "prime_prompt_sha256": digest_bytes(PRIME.encode()), "probe_prompt_sha256": digest_bytes(PROBE.encode()),
        "planned_repeats": args.repeats,
        "scope": "Same host/engine/build/model, independent processes, trusted local slot file. "
                 "Not network transport, cross-engine portability, or proof of lower end-to-end latency.",
    })
    backend = make_backend(binary, model, lib)
    rows = []
    for i in range(1, args.repeats + 1):
        try:
            row = run_trial(out, i, backend)
        except (OSError, ValueError, RuntimeError, TimeoutError, httpx.HTTPError) as exc:
            row = {"repeat": i, "validated": False, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
    passed = sum(r["validated"] for r in rows)
    write_json(out / "summary.json", {"schema": "beast.stage5b.slot_transfer.v1",
                                     "verified": passed, "planned": args.repeats, "trials": rows})
    paths = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{file_digest(p)}  {p.relative_to(out)}\n" for p in paths))
    print("REPORT:", out)
    return int(passed != args.repeats)


if __name__ == "__main__":
    raise SystemExit(main())
