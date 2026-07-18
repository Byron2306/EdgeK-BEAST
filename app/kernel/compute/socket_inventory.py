"""Read-only Linux TCP listener inventory for crystal attribution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
import os


@dataclass(frozen=True)
class KernelListener:
    address: str
    port: int
    inode: str
    protocol: str = "TCP"


def _decode_address(value: str) -> tuple[str, int]:
    raw, port_hex = value.split(":")
    address = socket.inet_ntoa(bytes.fromhex(raw)[::-1])
    return address, int(port_hex, 16)


def tcp_listeners(proc_root: Path = Path("/proc")) -> tuple[KernelListener, ...]:
    listeners = []
    path = proc_root / "net/tcp"
    try:
        lines = path.read_text().splitlines()[1:]
    except OSError:
        return ()
    for line in lines:
        fields = line.split()
        if len(fields) < 10 or fields[3] != "0A":
            continue
        address, port = _decode_address(fields[1])
        listeners.append(KernelListener(address, port, fields[9]))
    return tuple(listeners)


def inode_owners(inode: str, proc_root: Path = Path("/proc")) -> tuple[int, ...]:
    owners = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if any(os.readlink(link) == f"socket:[{inode}]" for link in (entry / "fd").iterdir() if link.is_symlink()):
                owners.append(int(entry.name))
        except OSError:
            continue
    return tuple(sorted(owners))
