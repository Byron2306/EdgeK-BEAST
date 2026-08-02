#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from pathlib import Path


def run_server(host: str, port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind((host, port))
        while True:
            data, address = server.recvfrom(65535)
            server.sendto(data, address)


def run_sender(host: str, port: int, seconds: int, packets_per_second: int, payload_size: int) -> int:
    payload = (b"B" * max(1, payload_size))[:payload_size]
    interval = 1.0 / max(1, packets_per_second)
    sent = 0
    deadline = time.monotonic() + max(1, seconds)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while time.monotonic() < deadline:
            sock.sendto(payload, (host, port))
            sent += 1
            time.sleep(interval)
    print(json.dumps({"packets_sent": sent, "bytes_sent": sent * len(payload)}))
    return 0


def run_echo_check(host: str, port: int, file_path: Path) -> int:
    payload = file_path.read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3.0)
        started = time.perf_counter_ns()
        sock.sendto(payload, (host, port))
        echoed, _ = sock.recvfrom(max(65535, len(payload) + 64))
        latency_us = (time.perf_counter_ns() - started) / 1000.0
    echoed_digest = "sha256:" + hashlib.sha256(echoed).hexdigest()
    print(json.dumps({
        "verified": echoed_digest == digest,
        "object_digest": echoed_digest,
        "bytes_sent": len(payload),
        "latency_us": latency_us,
    }))
    return 0 if echoed_digest == digest else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="X7 UDP peer helper")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=45678)

    send = sub.add_parser("send")
    send.add_argument("--host", required=True)
    send.add_argument("--port", type=int, default=45678)
    send.add_argument("--seconds", type=int, default=5)
    send.add_argument("--packets-per-second", type=int, default=64)
    send.add_argument("--payload-size", type=int, default=512)

    echo = sub.add_parser("echo-check")
    echo.add_argument("--host", required=True)
    echo.add_argument("--port", type=int, default=45678)
    echo.add_argument("--file", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "serve":
        return run_server(args.host, args.port)
    if args.command == "send":
        return run_sender(args.host, args.port, args.seconds, args.packets_per_second, args.payload_size)
    return run_echo_check(args.host, args.port, args.file)


if __name__ == "__main__":
    raise SystemExit(main())
