"""Same-host listener continuity on an owned TCP loopback fixture."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import random
import select
import socket
from statistics import median
import subprocess
import sys
import tempfile
import threading
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient, SocketGuardianServer

REPO = Path(__file__).resolve().parents[2]
LANES = ("plain_restart", "guardian_scm", "guardian_pidfd")
WORKSPACE = "stage7a-fixture"
SERVICE = "stage7a-loopback-echo"
BINDING = {"workspace_id": WORKSPACE, "capability_ref": "fixture:capability",
           "appraisal_ref": "fixture:appraisal", "policy_generation": "fixture:policy"}
UNAVAILABLE_ERRNOS = {errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT,
                      errno.ESOCKTNOSUPPORT, errno.ENOSYS}


def write_json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def client_for(sock_path, public_path):
    key = serialization.load_pem_public_key(public_path.read_bytes())
    return SocketGuardianClient(
        sock_path, receipt_verifier=key,
        process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope=WORKSPACE),
    )


@contextmanager
def guardian(root):
    # Unix socket names have a short kernel limit. Keep only the socket in /tmp.
    with tempfile.TemporaryDirectory(prefix="beast-7a-") as d:
        sock_path = Path(d) / "guardian.sock"
        signing = Ed25519PrivateKey.generate()
        pub = root / "guardian-public.pem"
        pub.write_bytes(signing.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        server = SocketGuardianServer(
            sock_path, root / "guardian.sqlite3", signer=signing,
            authorize=lambda req: req.get("op") in {"snapshot", "events"}
                or all(req.get(k) == v for k, v in BINDING.items()),
        )
        server.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, client_for(sock_path, pub), sock_path, pub
        finally:
            server.stop()
            thread.join(timeout=3)


def listen(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(32)
    return sock


def worker(port, log, *, guardian_socket=None, public=None, lease_id=None):
    handoff = None
    if guardian_socket:
        _, listener, receipt = client_for(guardian_socket, public).recover(lease_id, **BINDING)
        # recover() already verifies the guardian's digital signature and receipt digest.
        handoff = receipt.__dict__
    else:
        listener = listen(port)
    with listener, log.open("ab", buffering=0) as journal:
        print(json.dumps({"pid": os.getpid(), "port": listener.getsockname()[1], "fd": listener.fileno(),
                          "inode": os.fstat(listener.fileno()).st_ino, "handoff": handoff}), flush=True)
        while True:
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(2)
                try:
                    with peer.makefile("rb") as reader:
                        request = reader.readline(120)
                    if not request.endswith(b"\n"):
                        continue
                    text = request.rstrip(b"\n")
                    if not text or not all(chr(c).isalnum() or c == 45 for c in text):
                        continue
                    journal.write(text + b"\n")
                    peer.sendall(request)
                except OSError:
                    continue


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


def start_worker(stack, root, generation, port=0, guardian_args=None):
    stderr = stack.enter_context((root / f"worker-{generation}.stderr").open("wb"))
    argv = [sys.executable, "-B", "-m", "scripts.proof.run_stage7a_socket_continuity",
            "--worker", "--out", str(root / f"worker-{generation}.requests"), "--port", str(port)]
    if guardian_args is not None:
        sock, pub, lease_id = guardian_args
        argv += ["--guardian-socket", str(sock), "--public", str(pub), "--lease-id", lease_id]
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}
    process = subprocess.Popen(argv, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=stderr, text=True)
    stack.callback(process.stdout.close)
    stack.callback(stop, process)
    if not select.select([process.stdout], [], [], 8)[0]:
        raise TimeoutError("fixture worker readiness timed out")
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(f"fixture worker exited before readiness: {process.poll()}")
    state = json.loads(line)
    if state.get("pid") != process.pid or (port and state.get("port") != port):
        raise RuntimeError("fixture readiness identity mismatch")
    write_json(root / f"worker-{generation}.json", state)
    return process, state


def request(port, phase, i, ready=None):
    request_id = f"{phase}-{i:02}"
    msg = (request_id + "\n").encode()
    start = time.perf_counter_ns()
    if ready is not None:
        ready.set()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
            with sock.makefile("rb") as reader:
                sock.sendall(msg)
                echoed = reader.readline(120)
        status = "ok" if echoed == msg else "bad_response"
    except ConnectionRefusedError:
        status = "refused"
    except TimeoutError:
        status = "timeout"
    except OSError as exc:
        status = f"socket_errno_{exc.errno}"
    return {"request_id": request_id, "phase": phase, "status": status,
            "ms": round((time.perf_counter_ns() - start) / 1e6, 3)}


def accounting(rows, application):
    counts = Counter(application)
    phases = {}
    for phase in ("before", "gap", "after"):
        phases[phase] = dict(Counter(r["status"] for r in rows if r["phase"] == phase))
    clients = {r["request_id"] for r in rows if r["status"] == "ok"}
    known = {r["request_id"] for r in rows}
    return {"attempted": len(rows), "completed": len(clients), "failed": len(rows) - len(clients),
            "phases": phases, "application_records": len(application),
            "application_duplicates": sum(n - 1 for n in counts.values()),
            "unknown_application_ids": sorted(counts.keys() - known),
            "completed_without_application_record": sorted(clients - counts.keys()),
            "application_without_completion": sorted(counts.keys() - clients)}


def adopt_child(server, process, first, evidence):
    from unittest.mock import patch
    from app.kernel.system_monitor import ExecutionPrimitives

    real = ExecutionPrimitives.pidfd_getfd

    def observed(*args, **kwargs):
        evidence["pidfd_getfd_attempted"] = True
        try:
            result = real(*args, **kwargs)
        except OSError as exc:
            evidence["pidfd_getfd_errno"] = exc.errno
            raise
        evidence["pidfd_getfd_succeeded"] = True
        return result

    # Only the immediate child we created can be selected. There is no PID CLI
    # input, permission modification, or adoption of an existing service.
    if first["pid"] != process.pid or process.poll() is not None:
        raise RuntimeError("pidfd donor is not the live fixture child")
    with patch.object(ExecutionPrimitives, "pidfd_getfd", side_effect=observed):
        return server.adopt_pidfd_socket(SERVICE, process.pid, first["fd"],
                                         authority_ref="fixture-only", contract_port=first["port"], **BINDING)


def run_trial(root, lane, repeat, *, gap_ms, gap_requests):
    root.mkdir(parents=True)
    row = {"lane": lane, "repeat": repeat, "status": "completed", "verified": False,
           "pidfd_getfd_attempted": False, "pidfd_getfd_succeeded": False, "pidfd_getfd_errno": None}
    with ExitStack() as stack:
        server = client = lease = args = None
        if lane != "plain_restart":
            try:
                server, client, sock, pub = stack.enter_context(guardian(root))
            except OSError as exc:
                if exc.errno not in UNAVAILABLE_ERRNOS:
                    raise
                return {**row, "status": "unavailable", "reason": f"guardian control socket errno={exc.errno}"}
        if lane == "guardian_scm":
            lease = client.reserve(SERVICE, host="127.0.0.1", port=0, backlog=32,
                                   authority_ref="fixture-only", **BINDING)
            args = (sock, pub, lease.lease_id)
        first_process, first = start_worker(stack, root, 1, guardian_args=args)
        port = first["port"]
        if lane == "guardian_pidfd":
            try:
                lease = adopt_child(server, first_process, first, row)
            except (OSError, NotImplementedError) as exc:
                if isinstance(exc, OSError) and exc.errno not in UNAVAILABLE_ERRNOS:
                    raise
                return {**row, "status": "unavailable", "reason": f"pidfd adoption unavailable: {exc}"}
            args = (sock, pub, lease.lease_id)

        rows = [request(port, "before", i) for i in range(4)]
        stop(first_process)
        gap_start = time.perf_counter_ns()
        with ThreadPoolExecutor(max_workers=gap_requests) as pool:
            ready = [threading.Event() for _ in range(gap_requests)]
            futures = [pool.submit(request, port, "gap", i, ready[i]) for i in range(gap_requests)]
            if not all(event.wait(timeout=2) for event in ready):
                raise TimeoutError("gap traffic failed to start")
            time.sleep(max(0, gap_ms / 1000 - (time.perf_counter_ns() - gap_start) / 1e9))
            _, second = start_worker(stack, root, 2, port, args)
            ready_ms = (time.perf_counter_ns() - gap_start) / 1e6
            rows += [future.result(timeout=4) for future in futures]
        rows += [request(port, "after", i) for i in range(4)]
        if lease is not None:
            client.release(lease.lease_id, reason="fixture_complete", **BINDING)
            write_json(root / "guardian-events.json", client.events(limit=40))

    application = [line for f in sorted(root.glob("worker-*.requests")) for line in f.read_text().splitlines()]
    counts = accounting(rows, application)
    same = first["inode"] == second["inode"]
    handoffs = [x["handoff"] for x in (first, second) if x["handoff"]]
    expected_handoffs = {"plain_restart": 0, "guardian_scm": 2, "guardian_pidfd": 1}[lane]
    signed = sum(bool(receipt.get("signature")) for receipt in handoffs)
    expected_gap = {"refused": gap_requests} if lane == "plain_restart" else {"ok": gap_requests}
    verified = (counts["phases"]["gap"] == expected_gap
                and counts["phases"]["before"] == counts["phases"]["after"] == {"ok": 4}
                and not any(counts[k] for k in ("application_duplicates", "unknown_application_ids",
                                                "completed_without_application_record", "application_without_completion"))
                and signed == expected_handoffs and same == (lane != "plain_restart")
                and first["pid"] != second["pid"]
                and row["pidfd_getfd_succeeded"] == (lane == "guardian_pidfd"))
    row.update(verified=verified, initial_pid=first["pid"], replacement_pid=second["pid"],
               listener_same=same, signed_handoffs=signed, replacement_ready_ms=round(ready_ms, 3),
               accounting=counts)
    write_json(root / "requests.json", rows)
    return row


def summary(rows, lanes, repeats):
    result = {}
    for lane in lanes:
        trials = [r for r in rows if r["lane"] == lane]
        completed = [r for r in trials if r["status"] == "completed"]
        phase = Counter()
        for row in completed:
            phase.update(row["accounting"]["phases"]["gap"])
        result[lane] = {"planned": repeats, "completed": len(completed),
                        "verified": sum(r["verified"] for r in trials),
                        "unavailable": [r["reason"] for r in trials if r["status"] == "unavailable"],
                        "errors": [r["reason"] for r in trials if r["status"] == "error"],
                        "gap_requests": dict(phase),
                        "duplicate_application_records": sum(r["accounting"]["application_duplicates"] for r in completed),
                        "pidfd_getfd_attempts": sum(r["pidfd_getfd_attempted"] is True for r in trials),
                        "pidfd_getfd_successes": sum(r["pidfd_getfd_succeeded"] is True for r in trials),
                        "median_replacement_ready_ms": median(r["replacement_ready_ms"] for r in completed)
                            if completed else None}
    return {"schema": "beast.stage7a.socket_continuity.v1", "lanes": result}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--lanes", nargs="+", choices=LANES, default=LANES)
    p.add_argument("--gap-ms", type=int, default=150)
    p.add_argument("--gap-requests", type=int, default=12)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--seed", type=int, default=4327)
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    p.add_argument("--guardian-socket", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--public", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--lease-id", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker:
        worker(args.port, args.out, guardian_socket=args.guardian_socket, public=args.public, lease_id=args.lease_id)
        return
    if not (50 <= args.gap_ms <= 1000 and 1 <= args.gap_requests <= 24 and 1 <= args.repeats <= 10
            and len(set(args.lanes)) == len(args.lanes)):
        p.error("expected gap 50–1000 ms, 1–24 gap requests, 1–10 repeats, unique lanes")
    out = args.out.resolve()
    out.mkdir(parents=True)
    rows = []
    write_json(out / "plan.json", {"lanes": args.lanes, "gap_ms": args.gap_ms, "gap_requests": args.gap_requests,
        "repeats": args.repeats, "seed": args.seed,
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "scope": "Owned disposable loopback listener. New TCP connections, no retries. Worker restart, not guardian restart. "
                 "No kernel policy changes, independent networking transport, or established connection survival claim."})
    with (out / "attempts.jsonl").open("a", encoding="utf-8") as f:
        for repeat in range(1, args.repeats + 1):
            lanes = list(args.lanes)
            random.Random(args.seed + repeat).shuffle(lanes)
            for lane in lanes:
                try:
                    row = run_trial(out / f"{repeat:02}-{lane}", lane, repeat,
                                    gap_ms=args.gap_ms, gap_requests=args.gap_requests)
                except (OSError, RuntimeError, ValueError) as exc:
                    row = {"lane": lane, "repeat": repeat, "status": "error", "verified": False,
                           "reason": f"{type(exc).__name__}: {exc}", "pidfd_getfd_attempted": None,
                           "pidfd_getfd_succeeded": None}
                rows.append(row)
                f.write(json.dumps(row, sort_keys=True) + "\n")
                f.flush()
                print(lane, repeat, row["status"], "verified=", row["verified"], flush=True)
    write_json(out / "summary.json", summary(rows, args.lanes, args.repeats))
    files = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n" for p in files))
    print("REPORT:", out)
    if any(not r["verified"] and r["status"] != "unavailable" for r in rows):
        return 1
    return 2 if any(r["status"] == "unavailable" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
