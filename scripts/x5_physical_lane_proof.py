#!/usr/bin/env python3
"""Send one digest-verified object over an explicitly selected physical NIC."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return "sha256:" + digest.hexdigest(), size


def recv_exact(sock: socket.socket, length: int) -> bytes:
    parts: list[bytes] = []
    remaining = length
    while remaining:
        block = sock.recv(remaining)
        if not block:
            raise ConnectionError("peer closed before completing framed response")
        parts.append(block)
        remaining -= len(block)
    return b"".join(parts)


def physical_interface(interface: str) -> dict[str, object]:
    root = Path("/sys/class/net") / interface
    if not root.is_dir():
        raise ValueError(f"unknown interface: {interface}")
    def read(name: str) -> str:
        return (root / name).read_text(encoding="utf-8").strip()
    facts = {"interface": interface, "carrier": read("carrier"), "operstate": read("operstate"),
             "type": read("type"), "mac_address": read("address")}
    if facts["carrier"] != "1" or facts["operstate"] != "up" or facts["type"] != "1":
        raise ValueError(f"{interface} is not an active Ethernet carrier: {facts}")
    return facts


def route_for(remote_ip: str) -> dict[str, object]:
    completed = subprocess.run(["ip", "-j", "route", "get", remote_ip], check=True,
                               capture_output=True, text=True)
    routes = json.loads(completed.stdout)
    if not routes:
        raise ValueError(f"no route to {remote_ip}")
    return dict(routes[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="X5 real physical Ethernet lane proof client")
    parser.add_argument("--object", type=Path, required=True)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--local-ip", required=True)
    parser.add_argument("--remote-ip", required=True)
    parser.add_argument("--port", type=int, default=45850)
    parser.add_argument("--listen", action="store_true", help="accept an outbound connection from the receiver")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.object.is_file():
        raise SystemExit(f"object not found: {args.object}")
    physical = physical_interface(args.interface)
    route = route_for(args.remote_ip)
    if route.get("dev") != args.interface or route.get("prefsrc") not in {None, args.local_ip}:
        raise SystemExit(f"route does not bind {args.remote_ip} to {args.interface}/{args.local_ip}: {route}")
    object_digest, object_size = sha256_file(args.object)
    header = json.dumps({"version": "1.0", "object_digest": object_digest, "object_size": object_size},
                        sort_keys=True, separators=(",", ":")).encode()
    started = time.perf_counter_ns()
    listener: socket.socket | None = None
    if args.listen:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.local_ip, args.port))
        listener.listen(1)
        listener.settimeout(30)
        peer, peer_address = listener.accept()
        if peer_address[0] != args.remote_ip:
            peer.close()
            raise ConnectionError(f"unexpected receiver address: {peer_address[0]}")
    else:
        peer = socket.create_connection((args.remote_ip, args.port), timeout=10,
                                        source_address=(args.local_ip, 0))
    try:
        peer.settimeout(20)
        peer.sendall(struct.pack("!I", len(header)) + header)
        with args.object.open("rb") as source:
            while block := source.read(1024 * 1024):
                peer.sendall(block)
        response_size = struct.unpack("!I", recv_exact(peer, 4))[0]
        if not 2 <= response_size <= 4096:
            raise ValueError(f"invalid receiver response length: {response_size}")
        response = json.loads(recv_exact(peer, response_size))
    finally:
        peer.close()
        if listener is not None:
            listener.close()
    elapsed_us = (time.perf_counter_ns() - started) // 1000
    validated = (response.get("received_digest") == object_digest
                 and response.get("received_size") == object_size
                 and response.get("verified") is True)
    result = {
        "beast_object_type": "x5_physical_lane_proof",
        "version": "1.0",
        "authority": "controlled_physical_ethernet_lab",
        "physical_lane": True,
        "validated": validated,
        "sender": {**physical, "local_ip": args.local_ip, "route": route},
        "receiver": {"remote_ip": args.remote_ip, "port": args.port, "connection_mode": "receiver_pull" if args.listen else "sender_push", "receipt": response},
        "object_digest": object_digest,
        "bytes_sent": object_size,
        "elapsed_us": elapsed_us,
        "raw_payload_retained": False,
    }
    result["receipt_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validated": validated, "receipt": str(args.receipt), "result": result}, sort_keys=True))
    return 0 if validated else 1


if __name__ == "__main__":
    raise SystemExit(main())
