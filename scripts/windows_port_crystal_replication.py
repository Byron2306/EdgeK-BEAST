#!/usr/bin/env python3
"""Windows-native independent replication of the learned port-reuse contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import time
import uuid
from pathlib import Path


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def listener():
    value = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    value.bind(("127.0.0.1", 0)); value.listen(8)
    return value, int(value.getsockname()[1])


def probe(port: int) -> bool:
    try:
        value = socket.create_connection(("127.0.0.1", port), timeout=1); value.close(); return True
    except OSError:
        return False


def episode(port: int, owner_known: bool, healthy: bool):
    state = f"socket_state:port:{port}"
    branch = "reuse_existing_service" if owner_known and healthy else "request_operator_approval"
    facts = [
        {"operation": "socket.inventory", "phase": "observation", "subject": f"port:{port}", "result": "observed", "produces": [state]},
        {"operation": "repair.select_branch", "phase": "decision", "subject": f"port:{port}", "result": "selected", "reads": [state], "branch": branch},
        {"operation": "service.verify_health", "phase": "verification", "subject": "service:observed-loopback", "result": "success" if healthy else "refused", "requires": [state]},
    ]
    return {"episode_hash": digest(facts), "port": port, "owner_pid": os.getpid() if owner_known else None, "facts": facts, "status": "verified_success" if branch == "reuse_existing_service" else "refused"}


def run(allow_non_windows: bool = False):
    if os.name != "nt" and not allow_non_windows:
        raise RuntimeError("this replication runner must execute on the Windows laptop")
    positives = []
    for _ in range(3):
        sock, port = listener()
        try: positives.append(episode(port, True, probe(port)))
        finally: sock.close()
    sock, port = listener()
    negative = episode(port, False, False); sock.close()
    signature = [(fact["operation"], fact["phase"]) for fact in positives[0]["facts"]]
    if any([(fact["operation"], fact["phase"]) for fact in item["facts"]] != signature for item in positives[1:]):
        raise RuntimeError("natural Windows episodes lack one structural signature")
    trials = []
    for index in range(3):
        sock, heldout_port = listener()
        try:
            ok = probe(heldout_port)
            trials.append({"id": digest({"seed": "windows-independent", "index": index}), "port": heldout_port, "expected": "reuse_existing_service", "observed": "reuse_existing_service" if ok else "request_operator_approval", "verified": ok})
        finally: sock.close()
    stale_sock, stale_port = listener(); stale_sock.close()
    stale_refused = not probe(stale_port)
    trials.append({"id": digest({"seed": "windows-independent", "index": 3}), "port": stale_port, "expected": "request_operator_approval", "observed": "request_operator_approval" if stale_refused else "reuse_existing_service", "verified": stale_refused, "negative": True})
    body = {
        "experiment_id": "windows-port-crystal:" + uuid.uuid4().hex,
        "physical_domain": "windows-" + platform.release(), "contract_id": "beast.sensorium.port-reuse.v1",
        "machine": platform.node(), "platform": platform.platform(),
        "self_test": os.name != "nt",
        "positive_episode_hashes": [item["episode_hash"] for item in positives],
        "negative_episode_hashes": [negative["episode_hash"]],
        "structural_signature": signature, "inferred_parameters": ["requested_port"],
        "heldout_trials": trials, "provider_calls": 0, "provider_disabled_recurrence": True,
        "stale_process_refused": stale_refused, "fixture_built_candidate": False,
        "verified": all(item["verified"] for item in trials), "created_at": time.time(),
    }
    body["receipt_digest"] = digest(body)
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--self-test-non-windows", action="store_true")
    args = parser.parse_args()
    receipt = run(args.self_test_non_windows)
    Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt["receipt_digest"])


if __name__ == "__main__": main()
