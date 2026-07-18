"""Authorization-bound interpreter for promoted typed physical crystals."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Mapping

from app.kernel.compute.crystal_replay_lab import ReplayHandlerRegistry, default_replay_handlers
from app.kernel.compute.physical_crystal_lifecycle import (
    ApplicabilityProof,
    ExecutionAuthorizationReceipt,
    PhysicalApplicabilityGate,
    RecurrenceContext,
)
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, OpcodeRegistry, TypedCrystalNode
from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class InterpretedNodeReceipt:
    node_id: str
    opcode: str
    effect: Mapping[str, Any]
    verification: Mapping[str, bool]
    verified: bool
    rollback_attempted: bool
    rollback_successful: bool
    cpu_time_ms: float
    wall_time_ms: float
    status: str
    evidence_digest: str


@dataclass(frozen=True)
class TypedCrystalExecutionReceipt:
    crystal_id: str
    crystal_digest: str
    applicability_proof_digest: str
    authorization_receipt_digest: str
    pre_execution_revalidated: bool
    post_execution_revalidated: bool
    node_receipts: tuple[InterpretedNodeReceipt, ...]
    postcondition_checks: Mapping[str, bool]
    rollback_successful: bool
    physically_observed: bool
    provider_calls_before: int | None
    provider_calls_after: int | None
    provider_calls_during_execution: int | None
    cloud_displacement_proven: bool
    evidence_node_id: str
    final_status: str
    receipt_digest: str

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("typed crystal execution receipt is tampered")
        if self.final_status == "verified_local_recurrence" and not (
            self.pre_execution_revalidated
            and self.post_execution_revalidated
            and self.physically_observed
            and self.cloud_displacement_proven
            and all(self.postcondition_checks.values())
            and all(item.verified for item in self.node_receipts)
        ):
            raise ValueError("verified local recurrence claim is incomplete")


class TypedCrystalInterpreter:
    def __init__(
        self,
        opcode_registry: OpcodeRegistry,
        applicability_gate: PhysicalApplicabilityGate,
        *,
        handlers: ReplayHandlerRegistry | None = None,
        evidence: ControlEvidenceGraph | None = None,
        provider_call_counter: Callable[[], int] | None = None,
    ):
        self.opcode_registry = opcode_registry
        self.applicability_gate = applicability_gate
        self.handlers = handlers or default_replay_handlers()
        self.evidence = evidence or ControlEvidenceGraph()
        self.provider_call_counter = provider_call_counter

    def execute(
        self,
        crystal: ExecutableCrystalIR,
        proof: ApplicabilityProof,
        authorization: ExecutionAuthorizationReceipt,
        recurrence: RecurrenceContext,
        *,
        execution_state: Mapping[str, Any],
        now: float | None = None,
        monotonic_ns: int | None = None,
    ) -> TypedCrystalExecutionReceipt:
        crystal.validate(self.opcode_registry)
        proof.validate(now_monotonic_ns=monotonic_ns)
        authorization.validate()
        if (
            proof.crystal_id != crystal.identity
            or proof.crystal_digest != crystal.artifact_digest
            or authorization.crystal_id != crystal.identity
            or authorization.applicability_proof_digest != proof.proof_digest
            or authorization.request_digest != proof.execution_request_digest
        ):
            raise PermissionError("execution proof, authority, and crystal binding mismatch")
        self.handlers.require(crystal)

        pre = self.applicability_gate.evaluate(
            crystal, recurrence, now=now, monotonic_ns=monotonic_ns,
        )
        if not pre.allowed or pre.proof is None or not self._same_physical_binding(proof, pre.proof):
            raise PermissionError("physical preconditions drifted before execution")

        before = self.provider_call_counter() if self.provider_call_counter is not None else None
        context: dict[str, Any] = {
            "parameters": dict(proof.parameter_bindings),
            "descriptors": {
                "process": proof.process_lease_ids,
                "socket": proof.socket_identity_ids,
                "port_lease": proof.port_lease_ids,
                "workspace": (proof.workspace_identity,),
            },
            "state": dict(execution_state), "unrelated_state": {}, "outputs": {},
            "workspace": recurrence.workspace_root or "promoted-runtime",
        }
        node_receipts = []
        for node in crystal.nodes:
            receipt = self._execute_node(context, node)
            node_receipts.append(receipt)
            context["outputs"][node.node_id] = dict(receipt.effect)
            if not receipt.verified:
                break
        after = self.provider_call_counter() if self.provider_call_counter is not None else None
        provider_delta = None if before is None or after is None else after - before
        cloud_proven = provider_delta == 0 if provider_delta is not None else False
        postconditions = self._postconditions(crystal, context, tuple(node_receipts))
        post = self.applicability_gate.evaluate(
            crystal, recurrence, now=now, monotonic_ns=monotonic_ns,
        )
        post_revalidated = bool(post.allowed and post.proof and self._same_physical_binding(proof, post.proof))
        physically_observed = any(
            item.opcode in {"socket.inventory", "socket.reconcile", "service.verify_health",
                            "process_lease.revalidate", "file.inspect_source", "artifact.verify_build",
                            "disk.inspect_pressure", "disk.verify_cleanup"}
            and item.verified for item in node_receipts
        )
        rollback_successful = all(not item.rollback_attempted or item.rollback_successful for item in node_receipts)
        verified = (
            len(node_receipts) == len(crystal.nodes)
            and all(item.verified for item in node_receipts)
            and all(postconditions.values())
            and post_revalidated
            and physically_observed
            and cloud_proven
            and context.get("selected_branch") != "request_operator_approval"
        )
        final_status = "verified_local_recurrence" if verified else "execution_verification_failed"
        evidence_payload = {
            "crystal_id": crystal.identity, "crystal_digest": crystal.artifact_digest,
            "applicability_proof_digest": proof.proof_digest,
            "authorization_receipt_digest": authorization.receipt_digest,
            "pre_execution_revalidated": True, "post_execution_revalidated": post_revalidated,
            "nodes": [item.evidence_digest for item in node_receipts],
            "postconditions": postconditions, "provider_calls_before": before,
            "provider_calls_after": after, "provider_calls_during_execution": provider_delta,
            "cloud_displacement_proven": cloud_proven, "final_status": final_status,
        }
        evidence_node = self.evidence.add("typed_crystal_local_recurrence", evidence_payload)
        receipt_payload = {
            "crystal_id": crystal.identity, "crystal_digest": crystal.artifact_digest,
            "applicability_proof_digest": proof.proof_digest,
            "authorization_receipt_digest": authorization.receipt_digest,
            "pre_execution_revalidated": True, "post_execution_revalidated": post_revalidated,
            "node_receipts": tuple(node_receipts), "postcondition_checks": postconditions,
            "rollback_successful": rollback_successful, "physically_observed": physically_observed,
            "provider_calls_before": before, "provider_calls_after": after,
            "provider_calls_during_execution": provider_delta,
            "cloud_displacement_proven": cloud_proven, "evidence_node_id": evidence_node.node_id,
            "final_status": final_status,
        }
        result = TypedCrystalExecutionReceipt(**receipt_payload, receipt_digest="")
        result = replace(result, receipt_digest=content_hash(result.content_payload()))
        result.validate()
        return result

    def _execute_node(self, context: dict[str, Any], node: TypedCrystalNode) -> InterpretedNodeReceipt:
        handler = self.handlers.handlers[node.handler_key]
        verifier = self.handlers.verifiers[node.verifier_key]
        started_wall, started_cpu = time.perf_counter(), time.process_time()
        effect: Mapping[str, Any] = {}
        verification: Mapping[str, bool] = {}
        rollback_attempted = rollback_successful = False
        error = ""
        try:
            effect = dict(handler(context, node))
            verification = {key: bool(value) for key, value in verifier(context, node, effect).items()}
            verified = bool(verification) and all(verification.values())
        except Exception as exc:
            verified = False
            error = type(exc).__name__
            effect = {"error_type": error, "message_retained": False}
            verification = {"handler_completed": False}
        if not verified and node.rollback_key:
            rollback_attempted = True
            try:
                rolled = self.handlers.rollbacks[node.rollback_key](context, node, effect)
                rollback_successful = bool(rolled.get("rolled_back"))
            except Exception:
                rollback_successful = False
        wall_ms = (time.perf_counter() - started_wall) * 1000.0
        cpu_ms = (time.process_time() - started_cpu) * 1000.0
        if wall_ms > float(node.resource_limits.get("wall_time_ms", float("inf"))) or cpu_ms > float(node.resource_limits.get("cpu_time_ms", float("inf"))):
            verified = False
            error = "resource_envelope_exceeded"
        status = "verified" if verified else ("rolled_back" if rollback_successful else "failed")
        payload = {
            "node_id": node.node_id, "opcode": node.opcode, "effect": effect,
            "verification": verification, "verified": verified,
            "rollback_attempted": rollback_attempted, "rollback_successful": rollback_successful,
            "cpu_time_ms": round(cpu_ms, 6), "wall_time_ms": round(wall_ms, 6),
            "status": status, "error": error,
        }
        return InterpretedNodeReceipt(
            node.node_id, node.opcode, effect, verification, verified,
            rollback_attempted, rollback_successful, round(cpu_ms, 6), round(wall_ms, 6),
            status, content_hash(payload),
        )

    @staticmethod
    def _same_physical_binding(original: ApplicabilityProof, current: ApplicabilityProof) -> bool:
        fields = (
            "crystal_id", "crystal_digest", "promotion_record_digest", "parameter_bindings",
            "process_lease_ids", "socket_identity_ids", "port_lease_ids", "workspace_identity",
            "registry_digest", "policy_generation", "appraisal_ref", "negative_conditions_absent",
            "workspace_root_digest",
        )
        return all(getattr(original, field) == getattr(current, field) for field in fields)

    @staticmethod
    def _postconditions(
        crystal: ExecutableCrystalIR,
        context: Mapping[str, Any],
        nodes: tuple[InterpretedNodeReceipt, ...],
    ) -> dict[str, bool]:
        by_opcode = {item.opcode: item for item in nodes}
        checks: dict[str, bool] = {}
        for condition in crystal.postconditions:
            if condition == "outcome:verified_success":
                checks[condition] = len(nodes) == len(crystal.nodes) and all(item.verified for item in nodes)
                continue
            opcode, separator, expected = condition.rpartition(":")
            node = by_opcode.get(opcode) if separator else None
            if node is None:
                checks[condition] = False
            elif opcode == "service.verify_health" and expected == "success":
                checks[condition] = node.verified and node.effect.get("healthy") is True
            else:
                checks[condition] = node.verified and expected == "success"
        checks["safe_non_refusal_branch"] = context.get("selected_branch") != "request_operator_approval"
        return checks
