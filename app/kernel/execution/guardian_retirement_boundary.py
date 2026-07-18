"""Concrete Guardian/service-registry boundary for stale listener replacement."""

from __future__ import annotations

import socket
from typing import Any, Mapping

from app.kernel.execution.port_lease_broker import PortLease
from app.kernel.execution.socket_guardian import SocketGuardianClient
from app.kernel.execution.stale_process_retirement import StaleProcessRetirementRequest
from app.kernel.networking.service_registry import ServiceRegistry


class GuardianStaleListenerBoundary:
    """Turns retirement checks into kernel socket and Guardian observations."""

    def __init__(
        self,
        client: SocketGuardianClient,
        registry: ServiceRegistry,
        *,
        workspace_id: str,
        guardian_binding: Mapping[str, Any],
        connect_timeout: float = 0.2,
    ):
        self.client = client
        self.registry = registry
        self.workspace_id = workspace_id
        self.guardian_binding = dict(guardian_binding)
        self.connect_timeout = max(0.01, float(connect_timeout))
        self._replacement: PortLease | None = None
        self._predecessor_generation = 0

    def registry_digest(self) -> str:
        return self.registry.digest()

    def listener_generation(self, service_id: str) -> int:
        matches = [
            lease.listener_generation for lease in self.client.snapshot()
            if lease.service_id == service_id and lease.workspace_id == self.workspace_id
        ]
        if matches:
            return max(matches)
        # Before Guardian adoption, the current generation comes from the
        # content-bound Sensorium request. The coordinator compares this value
        # again before authority consumption.
        return self._predecessor_generation

    def bind_request(self, request: StaleProcessRetirementRequest) -> None:
        if request.workspace_identity != self.workspace_id:
            raise PermissionError("retirement workspace does not match Guardian boundary")
        if request.registry_digest != self.registry.digest():
            raise PermissionError("retirement registry does not match Guardian boundary")
        service = self._service(request.service_id)
        if not service.enabled:
            raise PermissionError("disabled service cannot receive a replacement listener")
        self._predecessor_generation = request.listener_generation

    def listener_is_retired(self, request: StaleProcessRetirementRequest) -> bool:
        self.bind_request(request)
        service = self._service(request.service_id)
        host = service.upstream.rsplit(":", 1)[0]
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(self.connect_timeout)
        try:
            return probe.connect_ex((host, service.port)) != 0
        finally:
            probe.close()

    def start_replacement(self, request: StaleProcessRetirementRequest) -> str:
        self.bind_request(request)
        if not self.listener_is_retired(request):
            raise RuntimeError("cannot replace a listener that remains physically reachable")
        service = self._service(request.service_id)
        host = service.upstream.rsplit(":", 1)[0]
        lease = self.client.reserve(
            request.service_id,
            self.workspace_id,
            host=host,
            port=service.port,
            protocol="TCP",
            authority_ref=RETIREMENT_GUARDIAN_AUTHORITY,
            registry_digest=request.registry_digest,
            predecessor_generation=request.listener_generation,
            **self.guardian_binding,
        )
        if lease.listener_generation <= request.listener_generation:
            self._release(lease, "replacement_generation_not_advanced")
            raise RuntimeError("Guardian replacement generation did not advance")
        self._replacement = lease
        return lease.lease_id

    def replacement_is_healthy(self, identity: str) -> bool:
        lease = self._replacement
        if lease is None or lease.lease_id != identity:
            return False
        result = self.client.probe_health(workspace_id=self.workspace_id, **self.guardian_binding)
        healthy = any(
            row.get("lease_id") == identity and row.get("healthy") is True
            for row in result.get("results", ())
        )
        current = next((item for item in self.client.snapshot() if item.lease_id == identity), None)
        verified = bool(
            healthy and current and current.health_state == "healthy"
            and current.listener_generation > self._predecessor_generation
            and current.registry_digest == self.registry.digest()
        )
        if not verified:
            self._release(lease, "replacement_health_rollback")
            self._replacement = None
        return verified

    def rollback_replacement(self, reason: str = "retirement_rollback") -> bool:
        if self._replacement is None:
            return True
        lease = self._replacement
        self._release(lease, reason)
        self._replacement = None
        return all(item.lease_id != lease.lease_id for item in self.client.snapshot())

    def _release(self, lease: PortLease, reason: str) -> None:
        self.client.release(
            lease.lease_id,
            workspace_id=self.workspace_id,
            registry_digest=self.registry.digest(),
            reason=reason,
            **self.guardian_binding,
        )

    def _service(self, service_id: str):
        try:
            return self.registry.services[service_id]
        except KeyError as exc:
            raise PermissionError("service is absent from authoritative registry") from exc


RETIREMENT_GUARDIAN_AUTHORITY = "beast.stale-process-replacement"
