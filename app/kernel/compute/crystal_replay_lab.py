"""Structured isolated replay laboratory for typed Compute Crystals."""

from __future__ import annotations

import copy
import socket
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from app.kernel.compute.heldout_replay import ReplayReceipt
from app.kernel.compute.file_build_transform import (
    atomic_render, inspect_source as inspect_build_source, safe_workspace,
    verify_artifact as verify_build_artifact,
)
from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest, execute_cleanup
from app.kernel.compute.socket_inventory import inode_owners, tcp_listeners
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, OpcodeRegistry, TypedCrystalNode
from app.kernel.execution.cgroup_capsule import CgroupV2Discovery
from app.kernel.sensorium.contracts_hash import content_hash


Handler = Callable[[dict[str, Any], TypedCrystalNode], Mapping[str, Any]]
Verifier = Callable[[dict[str, Any], TypedCrystalNode, Mapping[str, Any]], Mapping[str, bool]]
Rollback = Callable[[dict[str, Any], TypedCrystalNode, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class ReplayVariant:
    variant_id: str
    parameters: Mapping[str, Any]
    descriptors: Mapping[str, tuple[str, ...]]
    initial_state: Mapping[str, Any]
    expected: Mapping[str, Any]
    negative: bool = False
    boundary_conditions: tuple[str, ...] = ()
    unrelated_state: Mapping[str, Any] = field(default_factory=dict)
    inject_failure_at: str = ""

    def validate(self) -> None:
        if not self.variant_id or not isinstance(self.parameters, Mapping):
            raise ValueError("replay variant requires identity and parameters")
        if any(kind not in {"process", "socket", "port_lease", "workspace"} for kind in self.descriptors):
            raise ValueError("replay variant contains an unsupported descriptor class")
        for kind, identities in self.descriptors.items():
            if not identities or any(not str(value).startswith(f"{kind}:") for value in identities):
                raise ValueError(f"replay variant {kind} descriptors are invalid")
        if self.negative and not self.boundary_conditions:
            raise ValueError("negative replay variant requires boundary conditions")


@dataclass(frozen=True)
class NodeReplayReceipt:
    node_id: str
    opcode: str
    handler_key: str
    attempted: bool
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
class VariantReplayReceipt:
    variant_id: str
    negative: bool
    initial_state_fingerprint: str
    final_state_fingerprint: str
    unrelated_state_unchanged: bool
    isolation: Mapping[str, Any]
    node_receipts: tuple[NodeReplayReceipt, ...]
    expected_checks: Mapping[str, bool]
    verified: bool
    safe_refusal: bool
    rollback_successful: bool
    boundary_updates: tuple[str, ...]
    resource_usage: Mapping[str, float]
    evidence_digest: str
    status: str


@dataclass(frozen=True)
class ReplayLaboratoryReceipt:
    candidate_id: str
    crystal_digest: str
    variant_receipts: tuple[VariantReplayReceipt, ...]
    positive_variants: int
    negative_variants: int
    verified_variants: int
    promotion_eligible: bool
    reason: str
    evidence_root: str

    def to_replay_receipt(self) -> ReplayReceipt:
        results = tuple(item.verified for item in self.variant_receipts)
        return ReplayReceipt(
            self.candidate_id, len(results), sum(results), self.promotion_eligible,
            self.reason, tuple(item.variant_id for item in self.variant_receipts), results,
            self.evidence_root, True,
        )

    def narrow_candidate(self, candidate: Any) -> Any:
        """Return a candidate whose applicability records replay boundaries."""
        if str(getattr(candidate, "identity", "")) != self.candidate_id:
            raise ValueError("replay laboratory receipt does not match candidate")
        updates = tuple(dict.fromkeys(
            update for receipt in self.variant_receipts for update in receipt.boundary_updates
        ))
        return replace(
            candidate,
            negative_conditions=tuple(dict.fromkeys((*getattr(candidate, "negative_conditions", ()), *updates))),
        )


class ReplayHandlerRegistry:
    def __init__(self):
        self.handlers: dict[str, Handler] = {}
        self.verifiers: dict[str, Verifier] = {}
        self.rollbacks: dict[str, Rollback] = {}

    def register_handler(self, key: str, handler: Handler) -> None:
        self._register(self.handlers, key, handler)

    def register_verifier(self, key: str, verifier: Verifier) -> None:
        self._register(self.verifiers, key, verifier)

    def register_rollback(self, key: str, rollback: Rollback) -> None:
        self._register(self.rollbacks, key, rollback)

    @staticmethod
    def _register(target: dict[str, Any], key: str, value: Any) -> None:
        if not key or not callable(value) or key in target:
            raise ValueError(f"invalid or duplicate replay implementation: {key}")
        target[key] = value

    def require(self, crystal: ExecutableCrystalIR) -> None:
        for node in crystal.nodes:
            if node.handler_key not in self.handlers:
                raise ValueError(f"replay handler is unavailable: {node.handler_key}")
            if node.verifier_key not in self.verifiers:
                raise ValueError(f"replay verifier is unavailable: {node.verifier_key}")
            if node.rollback_key and node.rollback_key not in self.rollbacks:
                raise ValueError(f"replay rollback is unavailable: {node.rollback_key}")


def default_replay_handlers() -> ReplayHandlerRegistry:
    registry = ReplayHandlerRegistry()

    def inventory(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        port = int(context["parameters"]["requested_port"])
        state = context["state"]
        if state.get("kernel_inventory"):
            listener = next((item for item in tcp_listeners() if item.port == port), None)
            owners = list(inode_owners(listener.inode)) if listener is not None else []
            if state.get("force_owner_unknown"):
                owners = []
            return {
                "port": port, "occupied": listener is not None, "inode": listener.inode if listener else "",
                "owners": owners, "source": "proc_net_tcp_and_fd_inode",
            }
        supplied = dict(state.get("socket_state") or {})
        return {"port": port, "source": "isolated_variant_state", **supplied}

    def choose_branch(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        inventory_effect = context["outputs"].get("step:0") or {}
        if inventory_effect.get("occupied") and inventory_effect.get("owners") and not context["state"].get("health_failure"):
            branch = "reuse_existing_service"
        elif not inventory_effect.get("occupied"):
            branch = "bind_requested_port"
        else:
            branch = "request_operator_approval"
        context["selected_branch"] = branch
        return {"branch": branch, "safe_refusal": branch == "request_operator_approval"}

    def verify_health(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        port = int(context["parameters"]["requested_port"])
        branch = context.get("selected_branch", "")
        healthy = False
        if branch == "reuse_existing_service" and context["state"].get("kernel_inventory"):
            try:
                probe = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                probe.close()
                healthy = True
            except OSError:
                healthy = False
        elif branch == "reuse_existing_service":
            healthy = bool(context["state"].get("health_ok", True))
        return {"healthy": healthy, "branch": branch, "probe": "loopback_tcp" if context["state"].get("kernel_inventory") else "isolated_state"}

    def inspect_source(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        return inspect_build_source(str(context.get("workspace") or ""))

    def choose_build_branch(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        source = context["outputs"].get("step:0") or {}
        branch = "render_canonical_artifact" if source.get("eligible") else "request_operator_approval"
        context["selected_branch"] = branch
        return {"branch": branch, "safe_refusal": branch == "request_operator_approval"}

    def render_artifact(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        if context.get("selected_branch") == "request_operator_approval":
            return {"written": False, "refused": True, "bounded": True}
        root = safe_workspace(str(context.get("workspace") or "")); target = root / "generated.json"; source = context["outputs"]["step:0"]
        backup = target.read_bytes() if target.is_file() and not target.is_symlink() else None
        context["artifact_backup"] = backup; context["artifact_backup_captured"] = True
        effect = atomic_render(root, source)
        context["state"].update({"artifact_digest": effect["artifact_sha256"], "artifact_bytes": effect["bytes"], "build_test_passed": True})
        return effect

    def verify_artifact(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        if context.get("selected_branch") == "request_operator_approval":
            return {"verified": False, "safe_refusal": True, "bytes_match": True, "tests_passed": True}
        return verify_build_artifact(str(context.get("workspace") or ""), context["outputs"]["step:0"])

    def restore_artifact(context: dict[str, Any], _node: TypedCrystalNode, _effect: Mapping[str, Any]) -> Mapping[str, Any]:
        root = safe_workspace(str(context.get("workspace") or "")); target = root / "generated.json"; backup = context.get("artifact_backup")
        if not context.get("artifact_backup_captured"):
            return {"rolled_back": True, "reason": "actuator_did_not_mutate"}
        if backup is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(backup)
        return {"rolled_back": (not target.exists()) if backup is None else target.read_bytes() == backup}

    def inspect_disk(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        manifest, observation = build_cleanup_manifest(str(context.get("workspace") or ""))
        context["cleanup_manifest"] = manifest
        expected = str(context["parameters"].get("cleanup_manifest_digest") or "")
        return {"manifest_digest": manifest.manifest_digest, "manifest_matches": expected == "AUTO" or manifest.manifest_digest == expected,
                "selected_files": len(manifest.entries), "selected_bytes": manifest.total_bytes,
                "approval_class": manifest.approval_class, "pressure": observation}

    def plan_disk(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        observed = context["outputs"].get("step:0") or {}
        branch = "quarantine_and_purge" if observed.get("manifest_matches") and observed.get("selected_files", 0) > 0 else "request_operator_approval"
        context["selected_branch"] = branch
        return {"branch": branch, "safe_refusal": branch == "request_operator_approval"}

    def cleanup_disk(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        if context.get("selected_branch") != "quarantine_and_purge":
            return {"verified": False, "refused": True, "bounded": True}
        approval = str(context["state"].get("cleanup_approval_receipt") or "")
        if content_hash(approval) != str(context["parameters"].get("approval_receipt_digest") or ""):
            raise PermissionError("cleanup approval receipt binding mismatch")
        result = execute_cleanup(str(context.get("workspace") or ""), context["cleanup_manifest"],
            approval_receipt=approval,
            inject_failure_before_purge=bool(context["state"].get("inject_cleanup_failure")))
        context["state"].update(result)
        return result

    def verify_disk(context: dict[str, Any], _node: TypedCrystalNode) -> Mapping[str, Any]:
        effect = context["outputs"].get("step:2") or {}
        if effect.get("refused") is True:
            return {"verified": False, "targets_absent": True, "quarantine_removed": True, "safe_refusal": True}
        return {"verified": effect.get("verified") is True, "targets_absent": effect.get("all_targets_absent") is True,
                "quarantine_removed": effect.get("quarantine_removed") is True}

    def confirm_cleanup_rollback(context: dict[str, Any], _node: TypedCrystalNode, _effect: Mapping[str, Any]) -> Mapping[str, Any]:
        manifest = context.get("cleanup_manifest")
        root = Path(str(context.get("workspace") or ""))
        restored = bool(manifest is not None and all((root / item.relative_path).is_file() for item in manifest.entries))
        return {"rolled_back": restored}

    registry.register_handler("sensorium.socket_inventory", inventory)
    registry.register_handler("planner.port_conflict_branch", choose_branch)
    registry.register_handler("verifier.service_health", verify_health)
    registry.register_verifier("verifier.socket_inventory_complete", lambda _c, _n, effect: {"inventory_complete": "occupied" in effect and "owners" in effect})
    registry.register_verifier("verifier.branch_within_allowlist", lambda _c, _n, effect: {"branch_allowed": effect.get("branch") in {"reuse_existing_service", "bind_requested_port", "request_operator_approval"}})
    registry.register_verifier("verifier.health_probe_receipt", lambda _c, _n, effect: {"probe_completed": isinstance(effect.get("healthy"), bool), "branch_recorded": bool(effect.get("branch"))})
    registry.register_handler("sensorium.file_source", inspect_source)
    registry.register_handler("planner.build_repair_branch", choose_build_branch)
    registry.register_handler("builder.render_canonical_artifact", render_artifact)
    registry.register_handler("verifier.canonical_build_artifact", verify_artifact)
    registry.register_verifier("verifier.file_source_bounded", lambda _c, _n, effect: {"bounded_read": isinstance(effect.get("eligible"), bool) and int(effect.get("bytes", -1)) <= 4096})
    registry.register_verifier("verifier.build_branch_allowlisted", lambda _c, _n, effect: {"branch_allowed": effect.get("branch") in {"render_canonical_artifact", "request_operator_approval"}})
    registry.register_verifier("verifier.artifact_write_bounded", lambda context, _n, effect: {"bounded_write_or_refusal": not context["state"].get("force_artifact_verification_failure") and effect.get("bounded") is True and (effect.get("written") is True or effect.get("refused") is True)})
    registry.register_verifier("verifier.canonical_build_receipt", lambda _c, _n, effect: {"objective_verifier_completed": effect.get("bytes_match") is True and effect.get("tests_passed") is True and (effect.get("verified") is True or effect.get("safe_refusal") is True)})
    registry.register_rollback("rollback.restore_generated_artifact", restore_artifact)
    registry.register_handler("sensorium.disk_pressure", inspect_disk)
    registry.register_handler("planner.disk_cleanup", plan_disk)
    registry.register_handler("disk.quarantine_and_purge", cleanup_disk)
    registry.register_handler("verifier.disk_cleanup", verify_disk)
    registry.register_verifier("verifier.disk_manifest_bound", lambda _c, _n, effect: {"manifest_observed": bool(effect.get("manifest_digest")), "binding_decided": isinstance(effect.get("manifest_matches"), bool)})
    registry.register_verifier("verifier.disk_cleanup_branch_allowlisted", lambda _c, _n, effect: {"branch_allowed": effect.get("branch") in {"quarantine_and_purge", "request_operator_approval"}})
    registry.register_verifier("verifier.disk_cleanup_bounded", lambda _c, _n, effect: {"bounded_cleanup_or_refusal": effect.get("verified") is True or effect.get("refused") is True})
    registry.register_verifier("verifier.disk_cleanup_receipt", lambda _c, _n, effect: {"objective_verifier_completed": (effect.get("verified") is True and effect.get("targets_absent") is True and effect.get("quarantine_removed") is True) or effect.get("safe_refusal") is True})
    registry.register_rollback("rollback.restore_quarantined_files", confirm_cleanup_rollback)
    return registry


class CrystalReplayLaboratory:
    def __init__(
        self,
        opcode_registry: OpcodeRegistry,
        *,
        handlers: ReplayHandlerRegistry | None = None,
        root: Path | None = None,
        minimum_positive_variants: int = 3,
        require_negative_variant: bool = True,
    ):
        self.opcode_registry = opcode_registry
        self.handlers = handlers or default_replay_handlers()
        self.root = Path(root) if root is not None else None
        self.minimum_positive_variants = int(minimum_positive_variants)
        self.require_negative_variant = bool(require_negative_variant)

    def run(self, crystal: ExecutableCrystalIR, variants: list[ReplayVariant]) -> ReplayLaboratoryReceipt:
        crystal.validate(self.opcode_registry)
        self.handlers.require(crystal)
        if not variants:
            raise ValueError("held-out replay requires variants")
        receipts = tuple(self._run_variant(crystal, variant) for variant in variants)
        positives = sum(not item.negative for item in receipts)
        negatives = sum(item.negative for item in receipts)
        verified = sum(item.verified for item in receipts)
        eligible = (
            verified == len(receipts)
            and positives >= self.minimum_positive_variants
            and (not self.require_negative_variant or negatives > 0)
        )
        if verified != len(receipts):
            reason = "one_or_more_variants_failed"
        elif positives < self.minimum_positive_variants:
            reason = "insufficient_positive_variants"
        elif self.require_negative_variant and negatives == 0:
            reason = "negative_variant_required"
        else:
            reason = "structured_heldout_replay_passed"
        root = content_hash([item.evidence_digest for item in receipts])
        return ReplayLaboratoryReceipt(
            crystal.identity, crystal.artifact_digest, receipts, positives, negatives,
            verified, eligible, reason, root,
        )

    def _run_variant(self, crystal: ExecutableCrystalIR, variant: ReplayVariant) -> VariantReplayReceipt:
        variant.validate()
        self._validate_inputs(crystal, variant)
        state = copy.deepcopy(dict(variant.initial_state))
        unrelated = copy.deepcopy(dict(variant.unrelated_state))
        initial_fingerprint = content_hash(state)
        unrelated_before = content_hash(unrelated)
        cgroup = CgroupV2Discovery().state()
        parent = str(self.root) if self.root is not None else None
        with tempfile.TemporaryDirectory(prefix=f"beast-replay-{variant.variant_id}-", dir=parent) as directory:
            for relative, payload in dict(state.get("workspace_files") or {}).items():
                path = Path(directory) / str(relative)
                try:
                    path.resolve().relative_to(Path(directory).resolve())
                except ValueError:
                    raise ValueError("replay workspace fixture path is unsafe")
                if ".." in Path(str(relative)).parts or path.name.startswith(".") or path.is_symlink():
                    raise ValueError("replay workspace fixture path is unsafe")
                path.parent.mkdir(parents=True, exist_ok=True)
                data = payload.encode() if isinstance(payload, str) else bytes(payload)
                path.write_bytes(data)
            context: dict[str, Any] = {
                "parameters": dict(variant.parameters), "descriptors": copy.deepcopy(dict(variant.descriptors)),
                "state": state, "unrelated_state": unrelated, "outputs": {}, "workspace": directory,
            }
            node_receipts = []
            for node in crystal.nodes:
                node_receipts.append(self._run_node(context, node, variant.inject_failure_at))
                context["outputs"][node.node_id] = dict(node_receipts[-1].effect)
                if not node_receipts[-1].verified:
                    break
            expected_checks = self._expected_checks(context, variant.expected)
            all_nodes = len(node_receipts) == len(crystal.nodes) and all(item.verified for item in node_receipts)
            safe_refusal = bool(context.get("selected_branch") == "request_operator_approval")
            unrelated_unchanged = unrelated_before == content_hash(context["unrelated_state"])
            if variant.negative:
                verified = all_nodes and safe_refusal and all(expected_checks.values()) and unrelated_unchanged
            else:
                verified = all_nodes and not safe_refusal and all(expected_checks.values()) and unrelated_unchanged
            rollback_successful = all(
                not item.rollback_attempted or item.rollback_successful for item in node_receipts
            )
            boundary_updates = tuple(
                f"SAFE_REFUSAL_UNDER:{condition}" if verified and variant.negative else f"FAILED_UNDER:{condition}"
                for condition in variant.boundary_conditions
            )
            cpu = sum(item.cpu_time_ms for item in node_receipts)
            wall = sum(item.wall_time_ms for item in node_receipts)
            final_fingerprint = content_hash(context["state"])
            isolation = {
                "filesystem": "private_temporary_directory",
                "workspace_destroyed_after_replay": True,
                "state": "deep_copy",
                "process_namespace": "not_established",
                "network_namespace": "host_loopback_read_only_probe" if state.get("kernel_inventory") else "not_used",
                "cgroup_v2_available": bool(cgroup.get("available")),
                "cgroup_delegated_writable": bool(cgroup.get("delegated_writable")),
                "cgroup_capsule_established": False,
            }
            evidence = content_hash({
                "variant": variant.variant_id, "initial": initial_fingerprint, "final": final_fingerprint,
                "nodes": [item.evidence_digest for item in node_receipts], "expected": expected_checks,
                "unrelated_unchanged": unrelated_unchanged, "isolation": isolation,
            })
            return VariantReplayReceipt(
                variant.variant_id, variant.negative, initial_fingerprint, final_fingerprint,
                unrelated_unchanged, isolation, tuple(node_receipts), expected_checks, verified,
                safe_refusal, rollback_successful, boundary_updates,
                {"cpu_time_ms": round(cpu, 6), "wall_time_ms": round(wall, 6)},
                evidence, "verified" if verified else "failed",
            )

    def _run_node(self, context: dict[str, Any], node: TypedCrystalNode, failure: str) -> NodeReplayReceipt:
        handler = self.handlers.handlers[node.handler_key]
        verifier = self.handlers.verifiers[node.verifier_key]
        started_wall, started_cpu = time.perf_counter(), time.process_time()
        effect: Mapping[str, Any] = {}
        verification: Mapping[str, bool] = {}
        rollback_attempted = rollback_successful = False
        status = "failed"
        try:
            if failure == node.node_id or failure == node.opcode:
                raise RuntimeError("injected replay failure")
            effect = dict(handler(context, node))
            verification = {key: bool(value) for key, value in verifier(context, node, effect).items()}
            verified = bool(verification) and all(verification.values())
            status = "verified" if verified else "verification_failed"
        except Exception as exc:
            effect = {"error_type": type(exc).__name__, "message_retained": False}
            verified = False
            verification = {"handler_completed": False}
            status = "handler_failed"
        if not verified and node.rollback_key:
            rollback_attempted = True
            try:
                rollback_effect = dict(self.handlers.rollbacks[node.rollback_key](context, node, effect))
                rollback_successful = bool(rollback_effect.get("rolled_back"))
            except Exception:
                rollback_successful = False
        wall_ms = (time.perf_counter() - started_wall) * 1000.0
        cpu_ms = (time.process_time() - started_cpu) * 1000.0
        if wall_ms > float(node.resource_limits.get("wall_time_ms", float("inf"))) or cpu_ms > float(node.resource_limits.get("cpu_time_ms", float("inf"))):
            verified = False
            status = "resource_envelope_exceeded"
        evidence_payload = {
            "node_id": node.node_id, "opcode": node.opcode, "handler_key": node.handler_key,
            "effect": effect, "verification": verification, "verified": verified,
            "rollback_attempted": rollback_attempted, "rollback_successful": rollback_successful,
            "cpu_time_ms": round(cpu_ms, 6), "wall_time_ms": round(wall_ms, 6), "status": status,
        }
        return NodeReplayReceipt(
            node.node_id, node.opcode, node.handler_key, True, effect, verification, verified,
            rollback_attempted, rollback_successful, round(cpu_ms, 6), round(wall_ms, 6),
            status, content_hash(evidence_payload),
        )

    @staticmethod
    def _validate_inputs(crystal: ExecutableCrystalIR, variant: ReplayVariant) -> None:
        if set(variant.parameters) != set(crystal.parameters):
            raise ValueError("variant parameters do not exactly match crystal parameters")
        for name, schema in crystal.parameters.items():
            value = variant.parameters[name]
            if schema.get("type") == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"variant parameter {name} must be an integer")
                if value < int(schema.get("minimum", value)) or value > int(schema.get("maximum", value)):
                    raise ValueError(f"variant parameter {name} is outside the allowed range")
        required = {kind for node in crystal.nodes for kind in node.descriptor_requirements}
        missing = sorted(required - set(variant.descriptors))
        if missing:
            raise ValueError(f"variant lacks required descriptors: {', '.join(missing)}")

    @staticmethod
    def _expected_checks(context: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, bool]:
        checks = {}
        if "branch" in expected:
            checks["branch"] = context.get("selected_branch") == expected["branch"]
        if "healthy" in expected:
            effects = list((context.get("outputs") or {}).values())
            observed = next((item.get("healthy") for item in reversed(effects) if "healthy" in item), None)
            checks["healthy"] = observed is expected["healthy"]
        if "state" in expected:
            checks["state"] = all(context.get("state", {}).get(key) == value for key, value in expected["state"].items())
        return checks or {"declared_expectation_present": False}
