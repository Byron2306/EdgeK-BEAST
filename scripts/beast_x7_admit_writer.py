#!/usr/bin/env python3
"""BEAST X7 admit-token writer (closure 2026-11-16). Operator-run only. Dry run by default.

Reads Governor admits from the governed_egress admit queue (``BEAST_ARDA_EGRESS_ADMIT=1`` writes
.beast/governed-egress/admit-queue.jsonl). It resolves each model host to its IPs and fills the X7 maps pinned under
/sys/fs/bpf/beast/x7:
  model_egress_dst[{v4-mapped addr, port, AF_INET6}] = 1
  admit_tokens[{tgid, dst}] = {arda_generation(cgroup of tgid), arda policy prefix, receipt prefix, expires_ns}
ARDA's own pinned maps (/sys/fs/bpf/arda/active_generation_map, policy_state_map) are only READ (bpftool lookup).
Without --apply this prints the bpftool commands and touches nothing. --apply needs root and is for the operator only.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / ".beast" / "governed-egress" / "admit-queue.jsonl"
ARDA = "/sys/fs/bpf/arda"
X7 = "/sys/fs/bpf/beast/x7"
BPFTOOL = "/usr/sbin/bpftool"
AF_INET6 = 10


def pack_dst(ip: str, port: int) -> bytes:
    addr = ipaddress.ip_address(ip)
    if addr.version == 4:
        raw = b"\0" * 10 + b"\xff\xff" + addr.packed
    elif addr.ipv4_mapped is not None:
        raw = b"\0" * 10 + b"\xff\xff" + addr.ipv4_mapped.packed
    else:
        raw = addr.packed
    return raw + struct.pack("!H", port) + struct.pack("<H", AF_INET6)


def pack_key(tgid: int, ip: str, port: int) -> bytes:
    return struct.pack("<II", tgid, 0) + pack_dst(ip, port)


def pack_token(arda_generation: int, policy_prefix: int, receipt_prefix_hex: str, expires_ns: int) -> bytes:
    return struct.pack("<QQQQ", arda_generation, policy_prefix, int(receipt_prefix_hex[:16] or "0", 16), expires_ns)


def hexargs(b: bytes) -> List[str]:
    return [f"{x:02x}" for x in b]


def cgroup_id(pid: int) -> Optional[int]:
    try:
        line = next(l for l in Path(f"/proc/{pid}/cgroup").read_text().splitlines() if l.startswith("0::"))
        return os.stat("/sys/fs/cgroup" + line[3:]).st_ino
    except (OSError, StopIteration):
        return None


def resolve(host: str) -> tuple[list[str], int]:
    name, _, port = host.rpartition(":") if host.count(":") == 1 else (host, "", "")
    name = name or host
    port_i = int(port) if port.isdigit() else 443
    ips = sorted({ai[4][0] for ai in socket.getaddrinfo(name, port_i, proto=socket.IPPROTO_TCP)})
    return ips, port_i


def bpftool_lookup(pin: str, key: bytes, apply: bool) -> Optional[bytes]:
    if not apply:
        return None
    out = subprocess.run([BPFTOOL, "-j", "map", "lookup", "pinned", pin, "key", "hex", *hexargs(key)],
                         capture_output=True, text=True, timeout=10)
    if out.returncode:
        return None
    val = json.loads(out.stdout).get("value", [])
    return bytes(int(x, 16) for x in val)


def commands_for(row: dict, apply: bool) -> List[List[str]]:
    pid = int(row["pid"])
    ips, port = resolve(row["host"])
    cg = cgroup_id(pid) or 0
    gen_raw = bpftool_lookup(f"{ARDA}/active_generation_map", struct.pack("<Q", cg), apply)
    pol_raw = bpftool_lookup(f"{ARDA}/policy_state_map", struct.pack("<I", 0), apply)
    gen = struct.unpack("<Q", gen_raw[:8])[0] if gen_raw else 0          # 0 in dry run / unmeasured
    prefix = struct.unpack("<Q", pol_raw[:8])[0] if pol_raw else 0
    expires = time.monotonic_ns() + int(row.get("ttl_ms", 30000)) * 1_000_000
    cmds = []
    for ip in ips:
        cmds.append([BPFTOOL, "map", "update", "pinned", f"{X7}/model_egress_dst", "key", "hex", *hexargs(pack_dst(ip, port)),
                     "value", "hex", "01"])
        cmds.append([BPFTOOL, "map", "update", "pinned", f"{X7}/admit_tokens", "key", "hex", *hexargs(pack_key(pid, ip, port)),
                     "value", "hex", *hexargs(pack_token(gen, prefix, row.get("receipt_prefix", ""), expires))])
    return cmds


def rows(queue: Path, since: float) -> Iterable[dict]:
    if not queue.exists():
        return []
    out = []
    for line in queue.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if float(r.get("at", 0)) >= since:
            out.append(r)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--queue", type=Path, default=QUEUE)
    ap.add_argument("--since-seconds", type=float, default=60.0)
    ap.add_argument("--apply", action="store_true", help="operator only (root): run bpftool against the pinned maps")
    ap.add_argument("--follow", action="store_true")
    a = ap.parse_args(argv)
    if a.apply and os.geteuid() != 0:
        print("refusing --apply without root; run the dry run to see the commands", file=sys.stderr)
        return 2
    seen = time.time() - a.since_seconds
    while True:
        batch = list(rows(a.queue, seen))
        seen = time.time()
        for r in batch:
            for cmd in commands_for(r, a.apply):
                if a.apply:
                    subprocess.run(cmd, check=False, timeout=10)
                else:
                    print(" ".join(cmd))
        if not a.follow:
            return 0
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
