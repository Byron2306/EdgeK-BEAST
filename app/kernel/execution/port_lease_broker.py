"""Explicit, capability-like TCP port leases for governed services."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import socket
import threading
import time
from typing import Callable, Dict
from pathlib import Path


@dataclass(frozen=True)
class PortLease:
    lease_id: str
    service_id: str
    workspace_id: str
    host: str
    port: int
    protocol: str
    issued_at_monotonic_ns: int
    receipt_digest: str
    network_namespace: str = "host"
    listener_generation: int = 1
    expires_at_monotonic_ns: int = 0
    family: str = "AF_INET"
    vrf: str = "production"
    lifecycle_state: str = "reserved"
    health_state: str = "unknown"
    authority_ref: str = ""
    appraisal_ref: str = ""
    transferred_at_monotonic_ns: int = 0
    capability_ref: str = ""
    policy_generation: str = ""
    registry_digest: str = ""
    issued_at_unix: float = 0.0
    expires_at_unix: float = 0.0
    release_reason: str = ""


@dataclass(frozen=True)
class SocketHandoffReceipt:
    lease_id: str
    service_id: str
    workspace_id: str
    listener_generation: int
    network_namespace: str
    vrf: str
    authority_ref: str
    appraisal_ref: str
    transferred_at_monotonic_ns: int
    receipt_digest: str
    capability_ref: str = ""
    policy_generation: str = ""
    registry_digest: str = ""
    guardian_id: str = "beast.local/in-process-broker"
    signature: str = ""


class PortLeaseBroker:
    """Reserve ports by retaining the bound socket until explicit release.

    A service receives a receipt and must use the returned socket (or release
    the lease before binding independently). Silent port seizure is impossible
    while the broker owns the reservation.
    """

    def __init__(self, *, socket_factory: Callable[..., socket.socket] = socket.socket,
                 guardian_client=None) -> None:
        self._lock = threading.RLock()
        self._leases: Dict[str, tuple[PortLease, socket.socket, bool]] = {}
        self._socket_factory = socket_factory
        self._generations: Dict[tuple[str, str, str, int, str], int] = {}
        self.guardian_client = guardian_client

    def reserve(self, service_id: str, workspace_id: str, *, host: str = "127.0.0.1",
                port: int = 0, network_namespace: str = "host", ttl_seconds: float = 0,
                family: str = "AF_INET", protocol: str = "TCP", vrf: str = "production",
                authority_ref: str = "", appraisal_ref: str = "", capability_ref: str = "",
                policy_generation: str = "", registry_digest: str = "") -> PortLease:
        if self.guardian_client is not None:
            return self.guardian_client.reserve(
                service_id, workspace_id, host=host, port=port,
                network_namespace=network_namespace, ttl_seconds=ttl_seconds,
                family=family, protocol=protocol, vrf=vrf,
                authority_ref=authority_ref, appraisal_ref=appraisal_ref,
                capability_ref=capability_ref, policy_generation=policy_generation,
                registry_digest=registry_digest,
            )
        if not service_id or not workspace_id:
            raise ValueError("service_id and workspace_id are required")
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if family not in {"AF_INET", "AF_INET6"}:
            raise ValueError("family must be AF_INET or AF_INET6")
        protocol = protocol.upper()
        if protocol not in {"TCP", "UDP"}:
            raise ValueError("protocol must be TCP or UDP")
        socket_family = socket.AF_INET if family == "AF_INET" else socket.AF_INET6
        socket_type = socket.SOCK_STREAM if protocol == "TCP" else socket.SOCK_DGRAM
        sock = self._socket_factory(socket_family, socket_type)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            actual_port = int(sock.getsockname()[1])
            issued = time.monotonic_ns()
            generation_key = (family, protocol, host, actual_port, network_namespace)
            with self._lock:
                generation = self._generations.get(generation_key, 0) + 1
                self._generations[generation_key] = generation
            material = {"service_id": service_id, "workspace_id": workspace_id,
                        "host": host, "port": actual_port, "protocol": protocol,
                        "family": family, "network_namespace": network_namespace,
                        "vrf": vrf, "listener_generation": generation,
                        "authority_ref": authority_ref, "appraisal_ref": appraisal_ref,
                        "capability_ref": capability_ref, "policy_generation": policy_generation,
                        "registry_digest": registry_digest,
                        "issued_at_monotonic_ns": issued}
            lease_id = "portlease:" + hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            digest = "sha256:" + hashlib.sha256(lease_id.encode()).hexdigest()
            expiry = issued + int(ttl_seconds * 1_000_000_000) if ttl_seconds else 0
            lease = PortLease(
                lease_id, service_id, workspace_id, host, actual_port, protocol,
                issued, digest, network_namespace, generation, expiry, family, vrf,
                "reserved", "unknown", authority_ref, appraisal_ref, 0,
                capability_ref, policy_generation, registry_digest, time.time(),
                time.time() + ttl_seconds if ttl_seconds else 0.0, "",
            )
            with self._lock:
                self._leases[lease_id] = (lease, sock, False)
            return lease
        except Exception:
            sock.close()
            raise

    def take_socket_with_receipt(self, lease_id: str, *, workspace_id: str = "",
                                 capability_ref: str = "", appraisal_ref: str = "",
                                 policy_generation: str = "", registry_digest: str = "") -> tuple[socket.socket, SocketHandoffReceipt]:
        if self.guardian_client is not None:
            _lease, sock, receipt = self.guardian_client.recover(
                lease_id, workspace_id=workspace_id, capability_ref=capability_ref,
                appraisal_ref=appraisal_ref, policy_generation=policy_generation,
                registry_digest=registry_digest,
            )
            return sock, receipt
        with self._lock:
            try:
                lease, sock, _ = self._leases[lease_id]
                if lease.expires_at_monotonic_ns and time.monotonic_ns() >= lease.expires_at_monotonic_ns:
                    raise KeyError("expired port lease")
                transferred_at = time.monotonic_ns()
                lease = replace(lease, lifecycle_state="handed_off", transferred_at_monotonic_ns=transferred_at)
                self._leases[lease_id] = (lease, sock, True)
                material = {
                    "lease_id": lease.lease_id, "service_id": lease.service_id,
                    "workspace_id": lease.workspace_id,
                    "listener_generation": lease.listener_generation,
                    "network_namespace": lease.network_namespace, "vrf": lease.vrf,
                    "authority_ref": lease.authority_ref, "appraisal_ref": lease.appraisal_ref,
                    "capability_ref": lease.capability_ref, "policy_generation": lease.policy_generation,
                    "registry_digest": lease.registry_digest,
                    "transferred_at_monotonic_ns": transferred_at,
                }
                digest = "sha256:" + hashlib.sha256(
                    json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                receipt = SocketHandoffReceipt(**material, receipt_digest=digest)
                return sock, receipt
            except KeyError as exc:
                raise KeyError("unknown or released port lease") from exc

    def take_socket(self, lease_id: str, **binding) -> socket.socket:
        """Compatibility wrapper; governed callers should retain the receipt."""
        return self.take_socket_with_receipt(lease_id, **binding)[0]

    def release(self, lease_id: str, **binding) -> PortLease:
        if self.guardian_client is not None:
            return self.guardian_client.release(lease_id, **binding)
        with self._lock:
            try:
                lease, sock, _ = self._leases.pop(lease_id)
            except KeyError as exc:
                raise KeyError("unknown or released port lease") from exc
            sock.close()
            return replace(lease, lifecycle_state="released", release_reason=str(binding.get("reason") or "explicit_release"))

    def mark_health(self, lease_id: str, *, healthy: bool, **binding) -> PortLease:
        if self.guardian_client is not None:
            return self.guardian_client.mark_health(lease_id, healthy=healthy, **binding)
        with self._lock:
            try:
                lease, sock, transferred = self._leases[lease_id]
            except KeyError as exc:
                raise KeyError("unknown or released port lease") from exc
            lease = replace(lease, health_state="healthy" if healthy else "unhealthy")
            self._leases[lease_id] = (lease, sock, transferred)
            return lease

    @staticmethod
    def reconciliation_key(lease: PortLease, *, local_address_class: str) -> tuple[object, ...]:
        return (
            lease.family, lease.protocol, local_address_class, lease.port,
            lease.workspace_id, lease.service_id, lease.listener_generation,
            lease.network_namespace, lease.vrf,
        )

    def snapshot(self) -> tuple[PortLease, ...]:
        if self.guardian_client is not None:
            return self.guardian_client.snapshot()
        with self._lock:
            return tuple(item[0] for item in self._leases.values() if not item[0].expires_at_monotonic_ns or time.monotonic_ns() < item[0].expires_at_monotonic_ns)

    def reconcile(self, *, now_monotonic_ns: int | None = None) -> tuple[PortLease, ...]:
        """Expire leases and close their retained sockets after restart/drift."""
        if self.guardian_client is not None:
            return self.guardian_client.snapshot()
        now = time.monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns
        expired = []
        with self._lock:
            for lease_id, (lease, sock, _) in self._leases.items():
                if lease.expires_at_monotonic_ns and now >= lease.expires_at_monotonic_ns:
                    expired.append(lease_id)
            for lease_id in expired:
                _, sock, _ = self._leases.pop(lease_id)
                sock.close()
        return self.snapshot()

    def persist_receipts(self, path: str | Path) -> None:
        """Persist non-secret lease receipts for restart reconciliation."""
        payload = [lease.__dict__ for lease in self.snapshot()]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    @staticmethod
    def load_receipts(path: str | Path) -> tuple[PortLease, ...]:
        """Load receipts as evidence only; sockets must be rebound explicitly."""
        if not Path(path).exists():
            return ()
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        return tuple(PortLease(**item) for item in values)
