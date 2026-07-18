"""Proof-carrying Port Conflict Repair Crystal planner."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from app.kernel.sensorium.contracts import ProcessLease, ContractValidationError


@dataclass(frozen=True)
class RepairPlan:
    crystal_id: str
    action: str
    requested_port: int
    owning_process: str
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    evidence_digest: str
    approval_required: bool
    approval_present: bool = False
    approval_valid: bool = False


class PortConflictRepairCrystal:
    crystal_id = "crystal:port-conflict-repair:v1"

    @staticmethod
    def _validated_owner(listener: Mapping[str, Any] | None, process_lease: ProcessLease | Mapping[str, Any] | None) -> bool:
        if not listener:
            return True
        if process_lease is None:
            return False
        try:
            lease = process_lease if isinstance(process_lease, ProcessLease) else ProcessLease(
                **{key: value for key, value in process_lease.items() if key in ProcessLease.__dataclass_fields__}
            )
            lease.validate()
        except (TypeError, ValueError, ContractValidationError):
            return False
        return (
            str(listener.get("owning_process") or "") == lease.lease_id
            and (not listener.get("executable_digest") or listener.get("executable_digest") == lease.executable_digest)
        )

    def plan(self, *, requested_port: int, listener: Mapping[str, Any] | None,
             lease_match: bool, process_start_verified: bool, health_ok: bool,
             operator_approved: bool = False,
             process_lease: ProcessLease | Mapping[str, Any] | None = None) -> RepairPlan:
        if not 1 <= requested_port <= 65535:
            raise ValueError("requested port is invalid")
        owner = str((listener or {}).get("owning_process", ""))
        identity_matches = self._validated_owner(listener, process_lease)
        preconditions = ["listener_socket_identified", "service_registry_consulted"]
        if owner:
            preconditions.extend(("owning_process_identified", "process_start_time_verified"))
        if not listener:
            action = "bind_requested_port"
            approval = False
        elif lease_match and health_ok and process_start_verified and identity_matches:
            action = "reuse_existing_service"
            approval = False
        elif not process_start_verified or not identity_matches or not operator_approved:
            action = "request_operator_approval"
            approval = True
        else:
            action = "retire_stale_process_and_rebind"
            approval = True
        post = ("expected_service_listening", "port_registry_reconciled", "health_endpoint_verified")
        evidence = {
            "listener": dict(listener or {}), "requested_port": requested_port,
            "lease_match": lease_match, "process_start_verified": process_start_verified,
            "process_identity_verified": identity_matches, "health_ok": health_ok,
            "operator_approved": operator_approved,
        }
        digest = "sha256:" + hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        approval_valid = bool(operator_approved and approval)
        return RepairPlan(self.crystal_id, action, requested_port, owner, tuple(preconditions), post, digest, approval, operator_approved, approval_valid)

    def execute_bounded(self, plan: RepairPlan, *, actuator, verifier) -> dict[str, Any]:
        """Run only a non-destructive planned action and verify postconditions."""
        if plan.approval_required and not plan.approval_valid:
            raise PermissionError("operator approval is required before destructive port repair")
        if plan.action not in {"bind_requested_port", "reuse_existing_service"}:
            raise PermissionError(f"action is not bounded-safe: {plan.action}")
        effect = actuator(plan)
        verification = verifier(plan, effect)
        if not isinstance(verification, Mapping) or not all(bool(verification.get(key)) for key in plan.postconditions):
            raise RuntimeError("port repair postcondition verification failed")
        return {"plan": plan, "effect": dict(effect or {}), "verification": dict(verification), "status": "verified_success"}

    def execute_with_socket_probe(
        self, plan: RepairPlan, *, host: str = "127.0.0.1", broker=None,
        service_id: str = "", workspace_id: str = "", service_handoff=None,
        listener_probe=None, registry_probe=None, health_probe=None,
    ) -> dict[str, Any]:
        """Bind/reuse only with three independent, mandatory postcondition probes.

        A newly bound socket remains owned by ``PortLeaseBroker`` after return.
        The service handoff callback receives that live socket and its lease.
        """
        missing = [name for name, value in (
            ("listener_probe", listener_probe), ("registry_probe", registry_probe),
            ("health_probe", health_probe),
        ) if value is None]
        if missing:
            raise ValueError("independent port-repair probes are required: " + ", ".join(missing))
        created_lease_id = ""

        def actuator(p):
            nonlocal created_lease_id
            if p.action == "reuse_existing_service":
                return {"reused": True, "host": host, "port": p.requested_port}
            if broker is None or not service_id or not workspace_id or service_handoff is None:
                raise ValueError("bind repair requires broker, service identity, workspace identity, and service_handoff")
            lease = broker.reserve(service_id, workspace_id, host=host, port=p.requested_port)
            created_lease_id = lease.lease_id
            sock, handoff_receipt = broker.take_socket_with_receipt(lease.lease_id)
            sock.listen(16)
            handoff = dict(service_handoff(p, lease, sock) or {})
            return {
                "reused": False, "host": host, "port": p.requested_port,
                "lease_id": lease.lease_id, "listener_generation": lease.listener_generation,
                "handoff_receipt": handoff_receipt.__dict__, "service_handoff": handoff,
            }

        def verifier(p, effect):
            return {
                "expected_service_listening": bool(listener_probe(p, effect)),
                "port_registry_reconciled": bool(registry_probe(p, effect)),
                "health_endpoint_verified": bool(health_probe(p, effect)),
            }

        try:
            return self.execute_bounded(plan, actuator=actuator, verifier=verifier)
        except Exception:
            if created_lease_id and broker is not None:
                try:
                    broker.release(created_lease_id)
                except KeyError:
                    pass
            raise
