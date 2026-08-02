"""Host-aware file-server proxy and low-latency socket helpers."""
from __future__ import annotations

import dataclasses
import ipaddress
import os
import re
import socket
from typing import Iterable, Mapping, Optional

_HOST_RE = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)(?::[0-9]{1,5})?$")


class ForwardingError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ForwardedRequestIdentity:
    host: str
    proto: str
    client_ip: str
    trusted_forwarder: bool


class HostForwardingPolicy:
    """Resolve forwarding headers only from explicitly trusted proxy peers."""

    def __init__(self, *, trusted_proxies: Iterable[str] = (), allowed_hosts: Iterable[str] = ()) -> None:
        self.trusted_proxies = tuple(ipaddress.ip_network(value, strict=False) for value in trusted_proxies)
        self.allowed_hosts = {value.lower().rstrip(".") for value in allowed_hosts}

    def _trusted(self, remote_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(remote_ip)
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxies)

    @staticmethod
    def _clean_host(value: str) -> str:
        host = value.strip().split(",", 1)[0].strip()
        if not host or not _HOST_RE.fullmatch(host) or any(ch in host for ch in "\r\n/\\"):
            raise ForwardingError("invalid host forwarding value")
        return host

    def resolve(self, headers: Mapping[str, str], *, remote_ip: str, tls: bool = False) -> ForwardedRequestIdentity:
        normalized = {str(k).lower(): str(v) for k, v in headers.items()}
        trusted = self._trusted(remote_ip)
        raw_host = normalized.get("host", "")
        proto = "https" if tls else "http"
        client = remote_ip
        if trusted:
            raw_host = normalized.get("x-forwarded-host", raw_host)
            proto = normalized.get("x-forwarded-proto", proto).split(",", 1)[0].strip().lower()
            client = normalized.get("x-forwarded-for", remote_ip).split(",", 1)[0].strip()
        host = self._clean_host(raw_host)
        bare = host[1:host.index("]")] if host.startswith("[") else host.split(":", 1)[0]
        if self.allowed_hosts and bare.lower().rstrip(".") not in self.allowed_hosts:
            raise ForwardingError("host is not allowed")
        if proto not in {"http", "https"}:
            raise ForwardingError("forwarded protocol is invalid")
        return ForwardedRequestIdentity(host, proto, client, trusted)


def create_reuseport_listener(host: str, port: int, *, backlog: int = 256, ipv6: bool = False) -> socket.socket:
    family = socket.AF_INET6 if ipv6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind((host, int(port)))
        sock.listen(max(1, int(backlog)))
        sock.set_inheritable(False)
        return sock
    except Exception:
        sock.close()
        raise


def socket_diagnostics() -> dict[str, object]:
    """Return a capability snapshot; netlink SOCK_DIAG is delegated to a helper."""
    return {
        "sock_diag_proc_tcp": os.path.exists("/proc/net/tcp"),
        "sock_diag_proc_tcp6": os.path.exists("/proc/net/tcp6"),
        "so_reuseport": hasattr(socket, "SO_REUSEPORT"),
        "bpf_sk_lookup_requires_privileged_loader": True,
        "af_xdp_requires_umem_and_privileged_loader": True,
    }
