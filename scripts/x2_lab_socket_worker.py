#!/usr/bin/env python3
"""Controlled in-life socket activity for the X2 observation proof."""
from __future__ import annotations

import socket
import sys
import time


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: x2_lab_socket_worker.py FIFO_PATH")
    with open(sys.argv[1], "rb", buffering=0) as gate:
        gate.read(1)
    for _ in range(64):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("127.0.0.1", 0))
        udp.close()
    for _ in range(64):
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(0.02)
        tcp.connect_ex(("127.0.0.1", 9))
        tcp.close()
    time.sleep(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
