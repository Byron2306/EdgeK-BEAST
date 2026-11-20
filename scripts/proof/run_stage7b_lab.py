"""Start three real loopback Commons nodes and exercise Forge and Sensorium.

This is Stage 7B readiness only. No model calls, host daemon changes, or
claims of cold/warm transfer savings or emergent lattice composition.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from scripts.attest_remote_commons_lab import attest
from scripts.bootstrap_remote_commons_lab import bootstrap

REPO = Path(__file__).resolve().parents[2]


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def read_health(address, child):
    http = build_opener(ProxyHandler({}))
    until = time.monotonic() + 15
    while time.monotonic() < until:
        if child.poll() is not None:
            raise RuntimeError(f"Commons node exited ({child.returncode}), inspect its log")
        try:
            with http.open(f"{address}/health", timeout=1) as response:
                return json.load(response)
        except OSError:
            time.sleep(.1)
    raise RuntimeError(f"Commons health unavailable at {address}, inspect its log")


@contextmanager
def commons_lab(out, ledger, base_port, *, before_launch=None):
    lab = out / "lab"
    with ExitStack() as stack:
        sockets = []
        for slot in range(3):
            listener = stack.enter_context(socket.socket())
            listener.bind(("127.0.0.1", base_port + slot))
            sockets.append(listener)
        subprocess.run([sys.executable, "scripts/provision_remote_commons_lab.py",
                        "--root", str(lab), "--base-port", str(base_port), "--nodes", "3"],
                       cwd=REPO, check=True, stdout=subprocess.DEVNULL)
        trust = attest(lab, lattice_root=ledger, ttl_seconds=3600)
        manifest = json.loads((lab / "manifest.json").read_text())
        if before_launch:
            before_launch(lab, manifest)
        children = []
        for entry, listener in zip(manifest["nodes"], sockets, strict=True):
            node = entry["node_id"]
            state = lab / node
            log = stack.enter_context((out / (node + ".log")).open("wb"))
            env = dict(os.environ)
            for key in ("BEAST_COMMONS_ARDA_APPRAISAL", "BEAST_COMMONS_WORKLOAD_DIGEST",
                        "BEAST_COMMONS_ML_KEM_SECRET_KEY"):
                env.pop(key, None)
            env.update(BEAST_COMMONS_NODE_ID=node, BEAST_COMMONS_NODE_ROOT=str(state / "data"),
                       BEAST_COMMONS_NODE_SIGNING_KEY=str(state / "node.pem"),
                       BEAST_COMMONS_CLIENT_TRUST_STORE=str(state / "clients.yaml"),
                       BEAST_COMMONS_TRUST_EVIDENCE=str(state / "trust-evidence.json"))
            child = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.commons_node_main:app",
                                      "--fd", str(listener.fileno())],
                                     cwd=REPO, env=env, pass_fds=(listener.fileno(),),
                                     stdout=log, stderr=subprocess.STDOUT)
            stack.callback(stop, child)
            children.append((entry, child))
            listener.close()
        for entry, child in children:
            health = read_health(f"http://127.0.0.1:{entry['port']}", child)
            if health.get("ok") is not True:
                raise RuntimeError(f"Commons health did not pass: {entry['node_id']}")
        yield lab, manifest, trust


def run(out, ledger, base_port):
    run_id = "stage7b-" + uuid4().hex
    report = out / "report"
    report.mkdir()
    runtime = SensoriumRuntime(journal_path=report / "sensorium.sqlite3", export_root=out / "outbox")

    def observed(event_type, payload):
        return runtime.observe_owned(
            event_type=event_type, source="stage7b_lab",
            payload_schema="beast.stage7b.readiness.v1", workspace_id=run_id,
            payload={"run_id": run_id, **payload},
        ).to_dict()

    with commons_lab(out, ledger, base_port) as (lab, manifest, trust):
        events = [observed("health.verified", {"node_id": entry["node_id"], "ok": True})
                  for entry in manifest["nodes"]]
        custody = asyncio.run(bootstrap(lab, out / "client-state"))
        events.append(observed("artifact.build_verified", {
            "manifest_digest": custody["manifest_digest"], "scope": "commons_seed_custody"}))
        fixture = out / "fixture"
        fixture.mkdir()
        payload = fixture / "pricing.py"
        payload.write_text("def total(value):\n    return value + 1\n", encoding="utf-8")
        forge = ComputeForgeNode("stage7b-forge", storage=DurableInferenceStorage(out / "forge"),
                                 sensorium_runtime=runtime)
        stack.callback(forge.close)
        before = forge.watch_repo(str(fixture), ["pricing.py"])["fingerprint_hash"]
        payload.write_text("def total(value):\n    return value + 2\n", encoding="utf-8")
        after = forge.watch_repo(str(fixture), ["pricing.py"])["fingerprint_hash"]
        if not before or not after or before == after or not runtime.journal.verify():
            raise RuntimeError("Forge fingerprint change or Sensorium journal verification failed")
        events.append(observed("file.source_inspected", {
            "node_id": forge.profile.node_id, "before": before, "after": after}))
        if not runtime.journal.verify():
            raise RuntimeError("final Sensorium journal verification failed")
        summary = {
            "run_id": run_id, "status": "ready", "scope": "same-host loopback readiness only",
            "commons_nodes_registered": custody["discovery"]["trusted_candidate_count"],
            "commons_seed_manifest_digest": custody["manifest_digest"],
            "commons_seed_custody": custody["local_admission"],
            "forge_fingerprint_before": before, "forge_fingerprint_after": after,
            "sensorium_events": events, "historical_lattice_anchor": trust["lattice"],
            "new_lattice_tested": False, "memfd_tested": False, "model_calls_requested": 0,
        }
        if summary["commons_nodes_registered"] != 3:
            raise RuntimeError("not all three Commons nodes registered")
        target = report / "summary.json"
        target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        files = [target, *sorted(report.glob("sensorium.*"))]
        (report / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files))
    print(f"STAGE7B_READY={report}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="new private run directory")
    parser.add_argument("--lattice-root", required=True, type=Path, help="existing verified trust anchor")
    parser.add_argument("--base-port", type=int, default=18111)
    args = parser.parse_args()
    if not 1024 <= args.base_port <= 65533:
        parser.error("base port must leave room for three unprivileged ports")
    ledger = args.lattice_root.resolve()
    if not (ledger / "lattice_checkpoints.jsonl").is_file():
        parser.error("no existing lattice ledger at --lattice-root")
    out = args.out.resolve()
    out.mkdir(mode=0o700, exist_ok=False)

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        run(out, ledger, args.base_port)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
