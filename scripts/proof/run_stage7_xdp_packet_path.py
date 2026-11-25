"""Paired native UDP / AF_XDP echo trials on private, disposable veth links."""

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import secrets
import shutil
import signal
import socket
from statistics import median
import struct
import subprocess
import sys
import tempfile
import time

DEST = ("10.203.0.2", 20397)
PEER = "10.203.0.1"
RX_MAC = "02:00:00:20:30:02"
TX_MAC = "02:00:00:20:30:01"
READY = "BEAST_READY "


def probe(address, count, size, interval, timeout):
    sent, echoed = hashlib.sha256(), hashlib.sha256()
    timings = []
    unexpected = 0
    cpu_start = time.process_time_ns()
    wall_start = time.monotonic_ns()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.connect(address)
        next_send = time.monotonic()
        for sequence in range(count):
            time.sleep(max(0, next_send - time.monotonic()))
            tag = struct.pack("!I", sequence)
            packet = tag + hashlib.shake_256(b"beast-x3-packet-v1" + tag).digest(size - 4)
            start = time.monotonic_ns()
            next_send = time.monotonic() + interval
            client.send(packet)
            sent.update(packet)
            expires = time.monotonic() + timeout
            while (remaining := expires - time.monotonic()) > 0:
                client.settimeout(remaining)
                try:
                    response = client.recv(2048)
                except TimeoutError:
                    break
                if response == packet:
                    timings.append((time.monotonic_ns() - start) / 1000)
                    echoed.update(response)
                    break
                unexpected += 1
        # Also detect replies queued after the final valid response.
        client.settimeout(interval)
        while True:
            try:
                client.recv(2048)
            except TimeoutError:
                break
            unexpected += 1
    ms = sorted(timings)
    return {
        "sent": count, "valid": len(ms), "missing": count - len(ms), "unexpected": unexpected,
        "sent_sha256": sent.hexdigest(), "echo_sha256": echoed.hexdigest(),
        "rtt_us": timings,
        "rtt_p50_us": ms[math.ceil(len(ms) * .50) - 1] if ms else None,
        "rtt_p99_us": ms[math.ceil(len(ms) * .99) - 1] if ms else None,
        "client_cpu_ms": (time.process_time_ns() - cpu_start) / 1e6,
        "probe_wall_ms": (time.monotonic_ns() - wall_start) / 1e6,
    }


def verified(requested, observed, client, server):
    count = client["sent"]
    return (
        observed == requested and count > 0 and client["valid"] == count
        and client["unexpected"] == 0 and client["sent_sha256"] == client["echo_sha256"]
        and server.get("packets_rx") == count and server.get("packets_tx") == count
        and (requested == "udp" or
             (server.get("xdp_packets_seen") == count and server.get("xdp_socket_misses") == 0))
    )


def command(*argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(f"{' '.join(argv)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


@contextmanager
def topology(ip):
    suffix = secrets.token_hex(5)
    rx, tx = f"bx3rx-{suffix}", f"bx3tx-{suffix}"
    with ExitStack() as stack:
        for ns in (rx, tx):
            command(ip, "netns", "add", ns)
            stack.callback(command, ip, "netns", "delete", ns)
        command(ip, "-n", tx, "link", "add", "eth0", "type", "veth",
                "peer", "name", "bxpeer", "netns", rx)
        command(ip, "-n", rx, "link", "set", "bxpeer", "name", "eth0")
        for ns, address, mac, peer, peer_mac in (
            (rx, DEST[0], RX_MAC, PEER, TX_MAC), (tx, PEER, TX_MAC, DEST[0], RX_MAC),
        ):
            command(ip, "-n", ns, "link", "set", "eth0", "address", mac, "up")
            command(ip, "-n", ns, "address", "add", f"{address}/24", "dev", "eth0")
            command(ip, "-n", ns, "neigh", "replace", peer, "lladdr", peer_mac,
                    "nud", "permanent", "dev", "eth0")
        yield rx, tx


def children_cpu_ms():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return (r.ru_utime + r.ru_stime) * 1000


def trial(args, ip, mode, size, repeat):
    row = {"requested_mode": mode, "size": size, "repeat": repeat, "verified": False}
    executable = [str(args.udp)]
    if mode != "udp":
        executable = [str(args.worker), "--interface", "eth0", "--object", str(args.object),
                      "--echo", "--ready-json", "--generic-xdp" if mode == "copy" else "--zero-copy"]
    with tempfile.TemporaryDirectory(prefix="beast-x3-") as tmp:
        error_path = Path(tmp) / "server.err"
        try:
            with topology(ip) as (rx, tx), error_path.open("wb") as err:
                cpu_start = children_cpu_ms()
                server = subprocess.Popen([ip, "netns", "exec", rx, *executable],
                                          stdout=subprocess.PIPE, stderr=err, text=True)
                sender_cpu = 0
                try:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        marker = [line[len(READY):] for line in error_path.read_text(errors="replace").splitlines()
                                  if line.startswith(READY)]
                        if len(marker) == 1:
                            row.update(json.loads(marker[0]))
                            break
                        if server.poll() is not None:
                            raise RuntimeError(f"receiver exited before readiness ({server.returncode})")
                        time.sleep(.01)
                    else:
                        raise RuntimeError("receiver readiness timed out")
                    if row.get("observed_mode") != mode:
                        raise RuntimeError("kernel-reported mode did not match the requested lane")
                    sender_start = children_cpu_ms()
                    try:
                        row["client"] = json.loads(command(
                            ip, "netns", "exec", tx, sys.executable, str(Path(__file__).resolve()),
                            "_probe", str(args.packets), str(size)))
                    finally:
                        sender_cpu = children_cpu_ms() - sender_start
                finally:
                    if server.poll() is None:
                        server.terminate()
                    try:
                        output, _ = server.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.communicate()
                        raise RuntimeError("receiver did not stop on SIGTERM")
                    row["receiver_process_cpu_ms_including_startup"] = round(
                        children_cpu_ms() - cpu_start - sender_cpu, 3)
                if server.returncode:
                    raise RuntimeError(f"receiver exited with status {server.returncode}")
                row["server"] = json.loads(output)
                row["verified"] = verified(mode, row["observed_mode"], row["client"], row["server"])
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            row["error"] = str(exc)
        if error_path.exists():
            row["receiver_diagnostics"] = [
                line for line in error_path.read_text(errors="replace").splitlines()
                if not line.startswith(READY)
            ][-20:]
    return row


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "_probe":
        print(json.dumps(probe(DEST, int(sys.argv[2]), int(sys.argv[3]), .002, .05)))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("udp", "worker", "object", "out"):
        parser.add_argument(f"--{argument}", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=5, choices=range(1, 11), metavar="1..10")
    parser.add_argument("--packets", type=int, default=64, choices=range(1, 129), metavar="1..128")
    parser.add_argument("--probe-zero-copy", action="store_true")
    args = parser.parse_args()
    ip = shutil.which("ip")
    if os.geteuid() or not ip:
        parser.error("the isolated live run requires root and iproute2")
    for name in ("udp", "worker", "object"):
        file = getattr(args, name).resolve()
        if not file.is_file() or (name != "object" and not os.access(file, os.X_OK)):
            parser.error(f"missing or unusable --{name}: {file}")
        setattr(args, name, file)
    args.out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(7303)
    rows, pairs = [], []
    for size in (64, 512, 1200):
        for repeat in range(1, args.repeats + 1):
            order = ["udp", "copy"]
            rng.shuffle(order)
            arms = {}
            for mode in order:
                row = trial(args, ip, mode, size, repeat)
                arms[mode] = row
                rows.append(row)
                print(size, repeat, mode, f"verified={row['verified']}", row.get("error", ""), flush=True)
            same = (all(row["verified"] for row in arms.values()) and
                    arms["udp"]["client"]["sent_sha256"] == arms["copy"]["client"]["sent_sha256"])
            comparisons = {}
            if same:
                for key in ("rtt_p50_us", "rtt_p99_us", "client_cpu_ms", "probe_wall_ms"):
                    comparisons[key] = arms["copy"]["client"][key] - arms["udp"]["client"][key]
                key = "receiver_process_cpu_ms_including_startup"
                comparisons[key] = arms["copy"][key] - arms["udp"][key]
            pairs.append({"size": size, "repeat": repeat, "order": order, "verified": same,
                          "copy_minus_udp": comparisons})
    zero = None
    if args.probe_zero_copy:
        zero = trial(args, ip, "zero_copy", 64, 1)
        rows.append(zero)
        print(f"zero_copy_probe verified={zero['verified']}", zero.get("error", ""), flush=True)
    passed = sum(pair["verified"] for pair in pairs)
    by_size = {}
    for size in (64, 512, 1200):
        comparable = [pair["copy_minus_udp"] for pair in pairs
                      if pair["size"] == size and pair["verified"]]
        by_size[str(size)] = {
            "verified_pairs": len(comparable),
            "median_paired_copy_minus_udp": {
                key: median(pair[key] for pair in comparable)
                for key in (comparable[0] if comparable else {})
            },
        }
    summary = {
        "schema": "beast.stage7.xdp_packet_path.v1",
        "scope": "Same-host private veth echo between native UDP and generic AF_XDP copy",
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "binary_sha256": {name: sha256(getattr(args, name)) for name in ("udp", "worker", "object")},
        "packets_per_trial": args.packets, "pace_ms": 2, "receive_timeout_ms": 50,
        "pairs_planned": len(pairs), "pairs_verified": passed, "pairs": pairs, "by_size": by_size,
        "zero_copy_probe": "not_requested" if zero is None else
                           "verified" if zero["verified"] else "not_demonstrated",
    }
    paths = [args.out / "attempts.jsonl", args.out / "summary.json"]
    paths[0].write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    paths[1].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (args.out / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in paths))
    print(f"REPORT={args.out} PAIRS_VERIFIED={passed}/{len(pairs)}", flush=True)
    return 0 if passed == len(pairs) else 1


def stop(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
