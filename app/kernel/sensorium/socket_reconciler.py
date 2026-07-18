"""Read-only reconciliation of socket observations into lattice identities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.kernel.sensorium.contracts import SocketIdentity


class SocketReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class ReconciledSocket:
    identity: SocketIdentity
    lease_id: str = ""
    lease_match: bool = False
    compatibility_hint: bool = False


class SocketIdentityReconciler:
    """Convert trusted observation records; never opens, closes, or redirects sockets."""

    def reconcile(self, observation: Mapping[str, object], *, lease_index: Mapping[object, str] | None = None) -> ReconciledSocket:
        required = ("family", "protocol", "local_address_class", "local_port",
                    "remote_scope", "owning_process", "service_id", "workspace_id",
                    "cgroup_id", "listener_generation", "opened_at_monotonic_ns",
                    "policy_class")
        missing = [key for key in required if key not in observation]
        if missing:
            raise SocketReconciliationError("missing socket fields: " + ",".join(missing))
        try:
            fields = {key: observation[key] for key in required}
            fields["network_namespace"] = str(observation.get("network_namespace") or "host")
            fields["vrf"] = str(observation.get("vrf") or "production")
            value = SocketIdentity(**fields).with_identity()
            value.validate()
        except (TypeError, ValueError) as exc:
            raise SocketReconciliationError(str(exc)) from exc
        # Port alone is not an identity: IPv4/IPv6, protocol, address class,
        # workspace and listener generation must participate in reconciliation.
        authoritative_keys = (
            value.identity,
            (value.family, value.protocol, value.local_address_class, value.local_port,
             value.workspace_id, value.service_id, value.listener_generation,
             value.network_namespace, value.vrf),
        )
        lease_id = next(((lease_index or {}).get(key, "") for key in authoritative_keys if (lease_index or {}).get(key)), "")
        compatibility_hint = bool((lease_index or {}).get(value.local_port)) and not lease_id
        return ReconciledSocket(value, lease_id=lease_id, lease_match=bool(lease_id), compatibility_hint=compatibility_hint)

    def reconcile_many(self, observations: Iterable[Mapping[str, object]], *, lease_index: Mapping[object, str] | None = None) -> tuple[ReconciledSocket, ...]:
        return tuple(self.reconcile(item, lease_index=lease_index) for item in observations)
