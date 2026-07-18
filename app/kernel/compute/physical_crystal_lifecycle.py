"""Authoritative promotion and recurrence applicability for physical crystals."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from app.kernel.compute.crystal_replay_lab import ReplayLaboratoryReceipt
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, OpcodeRegistry
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts import ProcessLease, SocketIdentity
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.adapters import current_boot_id


PROMOTION_STATES = {"heldout_validated", "promoted", "degraded", "demoted", "revoked", "expired"}
TRANSITIONS = {
    "heldout_validated": {"promoted", "revoked"},
    "promoted": {"degraded", "demoted", "revoked", "expired"},
    "degraded": {"promoted", "demoted", "revoked", "expired"},
    "demoted": {"heldout_validated", "revoked", "expired"},
    "revoked": set(),
    "expired": set(),
}


@dataclass(frozen=True)
class PhysicalCrystalRecord:
    crystal_id: str
    artifact_digest: str
    source_family_hash: str
    opcode_catalog_digest: str
    replay_evidence_root: str
    replay_variant_count: int
    policy_generation: str
    appraisal_ref: str
    approver: str
    approval_receipt: str
    status: str
    promoted_at: float
    expires_at: float
    transition_reason: str
    record_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("record_digest", None)
        return value

    def sealed(self) -> "PhysicalCrystalRecord":
        return replace(self, record_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.status not in PROMOTION_STATES:
            raise ValueError("invalid physical crystal promotion state")
        if self.record_digest != content_hash(self.content_payload()):
            raise ValueError("physical crystal promotion record is tampered")
        if not all((self.crystal_id, self.artifact_digest, self.replay_evidence_root, self.policy_generation, self.appraisal_ref, self.approver, self.approval_receipt, self.transition_reason)):
            raise ValueError("physical crystal promotion record is incomplete")
        if self.expires_at <= self.promoted_at:
            raise ValueError("physical crystal promotion expiry is invalid")


class PhysicalCrystalPromotionRegistry:
    """Single state machine for typed physical-crystal promotion."""

    def __init__(self, *, appraisal_verifier: Callable[[Mapping[str, Any]], bool], path: Path | None = None, require_scientific_evidence: bool = False):
        if not callable(appraisal_verifier):
            raise RuntimeError("physical crystal promotion requires an appraisal verifier")
        self.appraisal_verifier = appraisal_verifier
        self.require_scientific_evidence = bool(require_scientific_evidence)
        self.path = Path(path) if path else None
        self._records: dict[str, PhysicalCrystalRecord] = {}
        self._recurrences: list[dict[str, Any]] = []
        self._lock = RLock()
        self._load()

    def promote(
        self,
        crystal: ExecutableCrystalIR,
        replay: ReplayLaboratoryReceipt,
        *,
        appraisal: Mapping[str, Any],
        policy_generation: str,
        approver: str,
        approval_receipt: str,
        now: float | None = None,
        expires_after_seconds: float = 2592000.0,
        scientific_evidence: Mapping[str, Any] | None = None,
    ) -> PhysicalCrystalRecord:
        now = time.time() if now is None else float(now)
        if crystal.identity != replay.candidate_id or crystal.artifact_digest != replay.crystal_digest:
            raise ValueError("structured replay does not bind the promoted crystal")
        if not replay.promotion_eligible or not replay.evidence_root or replay.verified_variants != len(replay.variant_receipts):
            raise ValueError("structured held-out replay is not promotion eligible")
        if self.require_scientific_evidence:
            from app.kernel.compute.compute_plane import ScientificPromotionGate
            ScientificPromotionGate.require(scientific_evidence or {})
        if not approver or not approval_receipt or not policy_generation:
            raise PermissionError("explicit physical crystal approval is required")
        if (
            appraisal.get("state") not in {"verified", "appraised"}
            or appraisal.get("policy_generation") != policy_generation
            or appraisal.get("artifact_digest") != crystal.artifact_digest
            or appraisal.get("evidence_root") != replay.evidence_root
            or float(appraisal.get("expires_at") or 0) <= now
            or not appraisal.get("appraisal_ref")
            or not self.appraisal_verifier(appraisal)
        ):
            raise PermissionError("promotion appraisal is invalid or not exactly bound")
        record = PhysicalCrystalRecord(
            crystal.identity, crystal.artifact_digest, crystal.source_family_hash,
            crystal.opcode_catalog_digest, replay.evidence_root, len(replay.variant_receipts),
            policy_generation, str(appraisal["appraisal_ref"]), approver, approval_receipt,
            "promoted", now, min(now + float(expires_after_seconds), float(appraisal["expires_at"])),
            "structured_replay_and_operator_approval",
        ).sealed()
        record.validate()
        with self._lock:
            existing = self._records.get(crystal.identity)
            if existing and existing.status not in {"demoted", "degraded"}:
                raise ValueError(f"physical crystal is already {existing.status}")
            self._records[crystal.identity] = record
            self._persist()
        return record

    def transition(self, crystal_id: str, status: str, *, reason: str) -> PhysicalCrystalRecord:
        if not reason:
            raise ValueError("promotion transition reason is required")
        with self._lock:
            current = self._records.get(crystal_id)
            if current is None:
                raise KeyError(crystal_id)
            if status not in TRANSITIONS[current.status]:
                raise ValueError(f"invalid physical crystal transition: {current.status} -> {status}")
            updated = replace(current, status=status, transition_reason=reason, record_digest="").sealed()
            self._records[crystal_id] = updated
            self._persist()
            return updated

    def get(self, crystal_id: str) -> PhysicalCrystalRecord | None:
        with self._lock:
            return self._records.get(crystal_id)

    def require_active(self, crystal_id: str, *, now: float | None = None) -> PhysicalCrystalRecord:
        now = time.time() if now is None else float(now)
        record = self.get(crystal_id)
        if record is None or record.status != "promoted":
            raise PermissionError("physical crystal is not promoted")
        record.validate()
        if record.expires_at <= now:
            self.transition(crystal_id, "expired", reason="promotion_expired")
            raise PermissionError("physical crystal promotion expired")
        return record

    def record_verified_reuse(self, crystal_id: str, *, proof_digest: str, execution_digest: str,
                              occurred_at: float | None = None) -> dict[str, Any]:
        """Durably witness a successful promoted recurrence.

        Promotion is never inferred from this history; it is an auditable
        production signal used for demotion/expiry review and reuse evidence.
        """
        self.require_active(crystal_id, now=occurred_at)
        if not proof_digest or not execution_digest:
            raise ValueError("reuse witness requires applicability and execution digests")
        item = {"crystal_id": crystal_id, "proof_digest": proof_digest,
                "execution_digest": execution_digest, "occurred_at": time.time() if occurred_at is None else float(occurred_at)}
        item["receipt_digest"] = content_hash(item)
        with self._lock:
            if not any(existing["receipt_digest"] == item["receipt_digest"] for existing in self._recurrences):
                self._recurrences.append(item)
                self._persist_recurrences()
        return dict(item)

    def recurrence_summary(self, crystal_id: str) -> dict[str, Any]:
        entries = [item for item in self._recurrences if item["crystal_id"] == crystal_id]
        return {"crystal_id": crystal_id, "verified_reuse_count": len(entries),
                "last_verified_reuse_at": max((item["occurred_at"] for item in entries), default=None)}

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: asdict(value) for key, value in sorted(self._records.items())}
        descriptor, name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _persist_recurrences(self) -> None:
        if self.path is None:
            return
        target = self.path.with_name(self.path.stem + ".recurrences.json")
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self._recurrences, handle, sort_keys=True, separators=(",", ":"))
                handle.flush(); os.fsync(handle.fileno())
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for crystal_id, value in payload.items():
                record = PhysicalCrystalRecord(**value)
                record.validate()
                if record.crystal_id != crystal_id:
                    raise ValueError("physical crystal registry identity mismatch")
                self._records[crystal_id] = record
            recurrence_path = self.path.with_name(self.path.stem + ".recurrences.json")
            if recurrence_path.exists():
                entries = json.loads(recurrence_path.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    raise ValueError("recurrence history must be a list")
                for item in entries:
                    body = dict(item); supplied = body.pop("receipt_digest", "")
                    if supplied != content_hash(body) or not body.get("crystal_id"):
                        raise ValueError("recurrence history is tampered")
                self._recurrences = entries
        except Exception as exc:
            raise RuntimeError("physical crystal promotion registry is invalid") from exc


@dataclass(frozen=True)
class RecurrenceContext:
    parameter_bindings: Mapping[str, Any]
    process_leases: tuple[ProcessLease, ...]
    socket_identities: tuple[SocketIdentity, ...]
    port_leases: tuple[Mapping[str, Any], ...]
    workspace_identity: str
    registry_digest: str
    policy_generation: str
    appraisal: Mapping[str, Any]
    active_conditions: tuple[str, ...] = ()
    workspace_root: str = ""


@dataclass(frozen=True)
class ApplicabilityProof:
    crystal_id: str
    crystal_digest: str
    promotion_record_digest: str
    parameter_bindings: Mapping[str, Any]
    process_lease_ids: tuple[str, ...]
    socket_identity_ids: tuple[str, ...]
    port_lease_ids: tuple[str, ...]
    workspace_identity: str
    registry_digest: str
    policy_generation: str
    appraisal_ref: str
    boot_id: str
    negative_conditions_absent: tuple[str, ...]
    checked_at_monotonic_ns: int
    expires_at_monotonic_ns: int
    workspace_root_digest: str = ""
    proof_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("proof_digest", None)
        return value

    def sealed(self) -> "ApplicabilityProof":
        return replace(self, proof_digest=content_hash(self.content_payload()))

    def validate(self, *, now_monotonic_ns: int | None = None, expected_boot_id: str | None = None) -> None:
        if self.proof_digest != content_hash(self.content_payload()):
            raise ValueError("applicability proof is tampered")
        now = time.monotonic_ns() if now_monotonic_ns is None else int(now_monotonic_ns)
        if self.checked_at_monotonic_ns > now or self.expires_at_monotonic_ns <= now:
            raise PermissionError("applicability proof is stale")
        expected = current_boot_id() if expected_boot_id is None else expected_boot_id
        if not self.boot_id or self.boot_id != expected:
            raise PermissionError("applicability proof crossed the boot boundary")

    @property
    def execution_request_digest(self) -> str:
        return content_hash({"proof_digest": self.proof_digest, "crystal_id": self.crystal_id, "crystal_digest": self.crystal_digest})


@dataclass(frozen=True)
class ApplicabilityDecision:
    allowed: bool
    reason: str
    proof: ApplicabilityProof | None = None


class PhysicalApplicabilityGate:
    def __init__(
        self,
        registry: PhysicalCrystalPromotionRegistry,
        opcode_registry: OpcodeRegistry,
        *,
        appraisal_verifier: Callable[[Mapping[str, Any]], bool],
        process_freshness: Callable[[ProcessLease], bool],
        socket_freshness: Callable[[SocketIdentity], bool],
        port_lease_freshness: Callable[[Mapping[str, Any]], bool],
        proof_ttl_ns: int = 1_000_000_000,
    ):
        for value in (appraisal_verifier, process_freshness, socket_freshness, port_lease_freshness):
            if not callable(value):
                raise RuntimeError("physical applicability requires fresh-state verifiers")
        self.registry, self.opcode_registry = registry, opcode_registry
        self.appraisal_verifier = appraisal_verifier
        self.process_freshness, self.socket_freshness = process_freshness, socket_freshness
        self.port_lease_freshness = port_lease_freshness
        self.proof_ttl_ns = int(proof_ttl_ns)

    def evaluate(
        self,
        crystal: ExecutableCrystalIR,
        context: RecurrenceContext,
        *,
        now: float | None = None,
        monotonic_ns: int | None = None,
    ) -> ApplicabilityDecision:
        try:
            crystal.validate(self.opcode_registry)
            record = self.registry.require_active(crystal.identity, now=now)
            if record.artifact_digest != crystal.artifact_digest or record.opcode_catalog_digest != crystal.opcode_catalog_digest:
                return ApplicabilityDecision(False, "promoted_artifact_or_opcode_catalog_mismatch")
            if context.policy_generation != record.policy_generation:
                return ApplicabilityDecision(False, "policy_generation_mismatch")
            if not context.workspace_identity or not context.registry_digest:
                return ApplicabilityDecision(False, "workspace_or_registry_identity_missing")
            if set(context.parameter_bindings) != set(crystal.parameters):
                return ApplicabilityDecision(False, "parameter_binding_mismatch")
            self._validate_parameters(crystal, context.parameter_bindings)
            appraisal = context.appraisal
            wall_now = time.time() if now is None else float(now)
            if (
                appraisal.get("appraisal_ref") != record.appraisal_ref
                or appraisal.get("policy_generation") != record.policy_generation
                or appraisal.get("state") not in {"verified", "appraised"}
                or appraisal.get("artifact_digest") != crystal.artifact_digest
                or appraisal.get("evidence_root") != record.replay_evidence_root
                or float(appraisal.get("expires_at") or 0) <= wall_now
                or not self.appraisal_verifier(appraisal)
            ):
                return ApplicabilityDecision(False, "appraisal_invalid_or_stale")
            forbidden = self._forbidden_conditions(crystal.negative_conditions)
            active = set(context.active_conditions)
            hit = sorted(forbidden & active)
            if hit:
                return ApplicabilityDecision(False, "negative_applicability_hit:" + ",".join(hit))
            for lease in context.process_leases:
                lease.validate()
                if not self.process_freshness(lease):
                    return ApplicabilityDecision(False, "process_lease_stale")
            process_ids = {lease.lease_id for lease in context.process_leases}
            for identity in context.socket_identities:
                identity.validate()
                if (
                    identity.owning_process not in process_ids
                    or identity.workspace_id != context.workspace_identity
                    or not self.socket_freshness(identity)
                ):
                    return ApplicabilityDecision(False, "socket_identity_stale_or_unbound")
            for lease in context.port_leases:
                if (
                    lease.get("workspace_id") != context.workspace_identity
                    or lease.get("policy_generation") != context.policy_generation
                    or lease.get("appraisal_ref") != record.appraisal_ref
                    or not self.port_lease_freshness(lease)
                ):
                    return ApplicabilityDecision(False, "port_lease_stale_or_unbound")
            requested_port = context.parameter_bindings.get("requested_port")
            if requested_port is not None:
                socket_ports = {item.local_port for item in context.socket_identities}
                lease_ports = {int(item.get("port") or 0) for item in context.port_leases}
                if int(requested_port) not in socket_ports | lease_ports:
                    return ApplicabilityDecision(False, "requested_port_not_bound_to_fresh_descriptor")
            required = {kind for node in crystal.nodes for kind in node.descriptor_requirements}
            available = {
                "process": bool(context.process_leases), "socket": bool(context.socket_identities),
                "port_lease": bool(context.port_leases), "workspace": bool(context.workspace_identity),
            }
            missing = sorted(kind for kind in required if not available.get(kind))
            if missing:
                return ApplicabilityDecision(False, "required_descriptor_missing:" + ",".join(missing))
            workspace_root_digest = ""
            if "workspace" in required:
                root = Path(context.workspace_root)
                if not context.workspace_root or root.is_symlink() or not root.is_dir():
                    return ApplicabilityDecision(False, "workspace_root_missing_or_unsafe")
                workspace_root_digest = content_hash({"resolved_workspace_root": str(root.resolve())})
            checked = time.monotonic_ns() if monotonic_ns is None else int(monotonic_ns)
            proof = ApplicabilityProof(
                crystal.identity, crystal.artifact_digest, record.record_digest,
                dict(context.parameter_bindings), tuple(sorted(process_ids)),
                tuple(sorted(item.identity for item in context.socket_identities)),
                tuple(sorted(str(item.get("lease_id") or "") for item in context.port_leases)),
                context.workspace_identity, context.registry_digest, context.policy_generation,
                record.appraisal_ref, current_boot_id(), tuple(sorted(forbidden - active)), checked,
                checked + self.proof_ttl_ns, workspace_root_digest,
            ).sealed()
            return ApplicabilityDecision(True, "fresh_physical_preconditions_match", proof)
        except (ValueError, PermissionError) as exc:
            return ApplicabilityDecision(False, str(exc))

    @staticmethod
    def _validate_parameters(crystal: ExecutableCrystalIR, bindings: Mapping[str, Any]) -> None:
        for name, schema in crystal.parameters.items():
            value = bindings[name]
            if schema.get("type") == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"parameter_type_mismatch:{name}")
                if not int(schema.get("minimum", value)) <= value <= int(schema.get("maximum", value)):
                    raise ValueError(f"parameter_out_of_range:{name}")

    @staticmethod
    def _forbidden_conditions(values: tuple[str, ...]) -> set[str]:
        result = set()
        for value in values:
            if value.startswith("FAILED_UNDER:") or value.startswith("SAFE_REFUSAL_UNDER:"):
                result.add(value.split(":", 1)[1])
            else:
                result.add(value)
        return result


@dataclass(frozen=True)
class ExecutionAuthorizationReceipt:
    crystal_id: str
    applicability_proof_digest: str
    request_digest: str
    capability_id: str
    authorized: bool
    reason: str
    receipt_digest: str

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def validate(self) -> None:
        if not self.authorized or self.reason != "one_use_capability_consumed":
            raise PermissionError("execution authorization was not granted")
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("execution authorization receipt is tampered")


def consume_execution_authority(
    proof: ApplicabilityProof,
    capability: Mapping[str, Any],
    ledger: OneUseCapabilityLedger,
    *,
    authority: str,
    audience: str,
    now: float | None = None,
    monotonic_ns: int | None = None,
    expected_boot_id: str | None = None,
) -> ExecutionAuthorizationReceipt:
    proof.validate(now_monotonic_ns=monotonic_ns, expected_boot_id=expected_boot_id)
    item = ledger.consume(
        capability,
        request_digest=proof.execution_request_digest,
        authority=authority,
        now=now,
        expected_audience=audience,
        expected_policy_generation=proof.policy_generation,
        expected_appraisal_ref=proof.appraisal_ref,
    )
    payload = {
        "crystal_id": proof.crystal_id, "applicability_proof_digest": proof.proof_digest,
        "request_digest": proof.execution_request_digest, "capability_id": item.capability_id,
        "authorized": True, "reason": "one_use_capability_consumed",
    }
    return ExecutionAuthorizationReceipt(**payload, receipt_digest=content_hash(payload))
