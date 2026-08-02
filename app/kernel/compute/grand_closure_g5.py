from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.kernel.compute.capsule_registry import CapsuleRegistry
from app.kernel.compute.crystal_capsule_forge import CrystalCapsuleForge
from app.kernel.compute.grand_closure_g4 import fingerprint_repository
from app.kernel.compute.residual_candidate import ResidualCandidate
from app.kernel.compute.residual_compute_governor import ResidualComputeGovernor, ResidualComputeRequest
from app.kernel.compute.residual_compute_plane import ResidualComputePlane, RouteExecutionResult
from app.kernel.compute.residual_contracts import (
    ApplicabilityState,
    ResidualAuthority,
    ResidualRoute,
    VerificationState,
    sha256_digest,
    utc_now_iso,
)
from app.kernel.crystal_bus.capsule_messages import CapsuleOffer
from app.kernel.crystal_bus.fd_transport import CrystalBusEndpoint
from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy
from app.kernel.crystals.capsule_contracts import ExecutionBounds, SealedCrystalCapsuleManifest, canonical_json
from app.kernel.crystals.capsule_contracts import sha256_digest as bytes_sha256_digest
from app.kernel.crystals.capsule_signing import Ed25519CapsuleSigner, Ed25519CapsuleVerifier
from app.kernel.crystals.capsule_verifier import CapsuleVerifier
from app.kernel.execution.capsule_execution_adapter import CapsuleExecutionAdapter
from app.kernel.execution.one_use_capability import OneUseCapabilityLedger

G5_TASK_CLASS = "grand_closure_bounded_write_rollback_canary"
G5_OPCODE = "BOUNDED_ATOMIC_FILE_WRITE"


@dataclass(frozen=True, slots=True)
class G5PhaseReceipt:
    phase: str
    status: str
    capsule_digest: str
    execution_digest: str
    authority_consumed: bool
    postconditions_verified: bool
    rollback_performed: bool
    target_digest_before: str
    target_digest_after: str
    workspace_digest_before: str
    workspace_digest_after: str
    filesystem_writes: int
    network_calls: int


@dataclass(frozen=True, slots=True)
class G5ClosureReceipt:
    canary_id: str
    request_digest: str
    successful_write: G5PhaseReceipt
    forced_rollback: G5PhaseReceipt
    successful_content_verified: bool
    rollback_restored_exact_state: bool
    provider_calls: int
    local_inference_calls: int
    network_calls: int
    authority_used: str
    raw_payload_retained: bool
    created_at: str
    evidence_digest: str



def _workspace_state_digest(root: Path) -> str:
    records = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in {".git", ".beast_backups", "__pycache__", ".pytest_cache"})
        base = Path(current)
        for name in dirnames:
            path = base / name
            rel = path.relative_to(root).as_posix()
            records.append((rel, "dir", oct(path.stat().st_mode & 0o777), None))
        for name in sorted(filenames):
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                records.append((rel, "symlink", None, os.readlink(path)))
            elif path.is_file():
                records.append((rel, "file", oct(path.stat().st_mode & 0o777), bytes_sha256_digest(path.read_bytes())))
    return bytes_sha256_digest(canonical_json(records))

def _digest_path(path: Path) -> str:
    if not path.exists():
        return sha256_digest({"state": "absent"})
    if path.is_symlink() or not path.is_file():
        raise PermissionError("G5 target must be a regular file or absent")
    return bytes_sha256_digest(path.read_bytes())


def _assert_within(root: Path, target: Path) -> None:
    resolved_root = root.resolve(strict=True)
    resolved_parent = target.parent.resolve(strict=True)
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise PermissionError("target escapes bounded workspace")
    if target.exists() and target.is_symlink():
        raise PermissionError("symlink targets are forbidden")


def _atomic_write(target: Path, content: bytes) -> None:
    tmp = target.with_name(f".{target.name}.g5.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(tmp, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short G5 write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)
    directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _write_actuator(plan: Mapping[str, Any], bounds: Mapping[str, Any]) -> Mapping[str, Any]:
    if plan.get("opcode") != G5_OPCODE:
        raise PermissionError("G5 accepts only bounded atomic file writes")
    if tuple(bounds.get("network_scope", ())) != ():
        raise PermissionError("G5 forbids network scope")
    root = Path(str(plan["workspace_root"])).resolve(strict=True)
    target = root / str(plan["relative_path"])
    _assert_within(root, target)
    allowed = {str(Path(p).resolve()) for p in bounds.get("filesystem_scope", ())}
    if str(target.resolve(strict=False)) not in allowed:
        raise PermissionError("target is outside signed filesystem scope")
    before = _digest_path(target)
    previous = target.read_bytes() if target.exists() else None
    content = bytes.fromhex(str(plan["content_hex"]))
    max_output = int(bounds.get("max_output_bytes", 0))
    if len(content) > max_output:
        raise PermissionError("bounded write exceeds signed output limit")
    _atomic_write(target, content)
    return {
        "target": str(target),
        "target_digest_before": before,
        "target_digest_after": _digest_path(target),
        "expected_digest": bytes_sha256_digest(content),
        "previous_hex": None if previous is None else previous.hex(),
        "previous_absent": previous is None,
        "filesystem_writes": 1,
        "network_calls": 0,
    }


def _postconditions(plan: Mapping[str, Any], effect: Mapping[str, Any], verifier_manifest: Mapping[str, Any]) -> bool:
    if verifier_manifest.get("verifier_id") != "g5-bounded-write-v1":
        return False
    if plan.get("force_postcondition_failure"):
        return False
    target = Path(str(effect["target"]))
    return bool(
        target.is_file()
        and _digest_path(target) == effect.get("expected_digest")
        and effect.get("filesystem_writes") == 1
        and effect.get("network_calls") == 0
    )


def _rollback(plan: Mapping[str, Any], effect: Mapping[str, Any]) -> Mapping[str, Any]:
    target = Path(str(effect["target"]))
    root = Path(str(plan["workspace_root"])).resolve(strict=True)
    _assert_within(root, target)
    if effect.get("previous_absent"):
        target.unlink(missing_ok=True)
    else:
        previous = bytes.fromhex(str(effect["previous_hex"]))
        _atomic_write(target, previous)
    return {
        "restored_digest": _digest_path(target),
        "expected_digest": effect["target_digest_before"],
        "restored": _digest_path(target) == effect["target_digest_before"],
    }


class G5BoundedWriteRollbackCanary:
    """Execute a successful bounded write and a forced-failure rollback ceremony."""

    def __init__(
        self,
        *,
        sensorium_sink: Callable[[Mapping[str, Any]], str] | None = None,
        process_lease_resolver: Callable[[int], Mapping[str, Any]] | None = None,
        arda_checker: Callable[[Mapping[str, Any], str], bool] | None = None,
    ) -> None:
        self.sensorium_sink = sensorium_sink or (lambda event: sha256_digest(event))
        self.process_lease_resolver = process_lease_resolver or (
            lambda pid: {"lease_id": f"g5-process:{pid}", "active": True, "workspace": ""}
        )
        self.arda_checker = arda_checker or (lambda lease, appraisal: appraisal == "arda:g5-bounded-write-approved")

    def run(
        self,
        *,
        workspace_root: str | os.PathLike[str],
        workspace_id: str,
        privacy_domain: str,
        policy_digest: str,
        source_state_digest: str,
        relative_path: str = "g5-canary.txt",
        successful_content: bytes = b"BEAST G5 bounded write\n",
        rollback_content: bytes = b"BEAST G5 forced rollback\n",
        arda_ref: str = "arda:g5-bounded-write-approved",
    ) -> G5ClosureReceipt:
        root = Path(workspace_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("G5 workspace root must be a directory")
        target = root / relative_path
        _assert_within(root, target)
        initial_workspace = _workspace_state_digest(root)
        initial_target = _digest_path(target)

        success = self._run_phase(
            phase="successful_write",
            root=root,
            target=target,
            content=successful_content,
            force_failure=False,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            policy_digest=policy_digest,
            source_state_digest=source_state_digest,
            arda_ref=arda_ref,
        )
        successful_content_verified = _digest_path(target) == bytes_sha256_digest(successful_content)
        state_before_rollback = _workspace_state_digest(root)
        target_before_rollback = _digest_path(target)

        rollback = self._run_phase(
            phase="forced_rollback",
            root=root,
            target=target,
            content=rollback_content,
            force_failure=True,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            policy_digest=policy_digest,
            source_state_digest=source_state_digest,
            arda_ref=arda_ref,
        )
        final_workspace = _workspace_state_digest(root)
        final_target = _digest_path(target)
        rollback_restored = (
            final_target == target_before_rollback
            and final_workspace == state_before_rollback
            and rollback.rollback_performed
        )
        if not successful_content_verified:
            raise RuntimeError("G5 successful write did not verify")
        if not rollback_restored:
            raise RuntimeError("G5 rollback did not restore exact pre-phase state")
        body = {
            "canary_id": "g5-bounded-write-rollback",
            "request_digest": sha256_digest({
                "root": str(root), "target": relative_path, "policy": policy_digest, "source": source_state_digest
            }),
            "successful_write": success,
            "forced_rollback": rollback,
            "successful_content_verified": True,
            "rollback_restored_exact_state": True,
            "provider_calls": 0,
            "local_inference_calls": 0,
            "network_calls": 0,
            "authority_used": ResidualAuthority.ONE_USE_EXECUTE.value,
            "raw_payload_retained": False,
            "created_at": utc_now_iso(),
        }
        serial = {**body, "successful_write": asdict(success), "forced_rollback": asdict(rollback)}
        return G5ClosureReceipt(**body, evidence_digest=sha256_digest(serial))

    def _run_phase(
        self,
        *,
        phase: str,
        root: Path,
        target: Path,
        content: bytes,
        force_failure: bool,
        workspace_id: str,
        privacy_domain: str,
        policy_digest: str,
        source_state_digest: str,
        arda_ref: str,
    ) -> G5PhaseReceipt:
        before_workspace = _workspace_state_digest(root)
        before_target = _digest_path(target)
        signer = Ed25519CapsuleSigner(f"g5-forge:{phase}")
        capsule_verifier = CapsuleVerifier(Ed25519CapsuleVerifier({signer.signer_id: signer.public_key}))
        registry = CapsuleRegistry(max_entries=2)
        forge = CrystalCapsuleForge(registry=registry, event_sink=self.sensorium_sink)
        ledger = OneUseCapabilityLedger()
        plan = {
            "version": 1,
            "opcode": G5_OPCODE,
            "workspace_root": str(root),
            "relative_path": target.relative_to(root).as_posix(),
            "content_hex": content.hex(),
            "force_postcondition_failure": force_failure,
        }
        artifact_digest = bytes_sha256_digest(canonical_json(plan))
        promotion_digest = sha256_digest({"class": G5_TASK_CLASS, "artifact": artifact_digest})
        manifest = SealedCrystalCapsuleManifest(
            crystal_id=f"grand-closure-g5:{phase}",
            crystal_ir_version=1,
            artifact_digest=artifact_digest,
            promotion_digest=promotion_digest,
            policy_digest=policy_digest,
            source_state_digest=source_state_digest,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            task_class=G5_TASK_CLASS,
            audience_class="executor:g5-bounded-write",
            required_capability="crystal.execute.bounded_write",
            one_use_required=True,
            expires_at=time.time() + 300,
            verifier_id="g5-bounded-write-v1",
            rollback_contract_digest=sha256_digest({"rollback": "restore_exact_pre_state"}),
            signer_id=signer.signer_id,
            execution_bounds=ExecutionBounds(
                max_runtime_ms=10_000,
                max_memory_bytes=64 * 1024 * 1024,
                max_output_bytes=max(4096, len(content)),
                filesystem_scope=(str(target.resolve(strict=False)),),
                network_scope=(),
            ),
        )
        handle, _ = forge.prepare(
            manifest=manifest,
            crystal_ir=plan,
            verifier_manifest={"verifier_id": "g5-bounded-write-v1", "rollback": "exact"},
            signer=signer,
            ttl_seconds=300,
            predicted_reuse_count=1,
        )
        sender = receiver = None
        try:
            entry = registry.get(handle.receipt.capsule_id, workspace_id=workspace_id, privacy_domain=privacy_domain)
            if entry is None:
                raise RuntimeError("prepared G5 capsule missing")
            request = ResidualComputeRequest(
                request_id=f"g5:{phase}",
                request_digest=sha256_digest({"phase": phase, "artifact": artifact_digest}),
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                task_class=G5_TASK_CLASS,
                payload={"capsule_id": entry.capsule_id},
                policy_digest=policy_digest,
            )
            candidate = ResidualCandidate(
                candidate_id=f"g5-crystal:{phase}",
                route=ResidualRoute.PROMOTED_CRYSTAL,
                applicability=ApplicabilityState.APPLICABLE,
                verification=VerificationState.VERIFIED,
                authority=ResidualAuthority.ONE_USE_EXECUTE,
                predicted_latency_ms=8.0,
                predicted_cpu_ms=3.0,
                predicted_memory_bytes=entry.size_bytes,
                predicted_monetary_cost=0.0,
                confidence=1.0,
                expected_quality=1.0,
                failure_probability=0.0,
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                evidence_digest=sha256_digest({"promotion": promotion_digest, "capsule": entry.capsule_digest}),
                metadata={"capsule_id": entry.capsule_id, "bounded_write": True, "phase": phase},
            )
            policy = PeerAdmissionPolicy(
                expected_uid=os.getuid(),
                process_lease_resolver=lambda pid: self._resolve_lease(pid, workspace_id),
                workspace_checker=lambda lease, ws: bool(lease.get("active")) and lease.get("workspace") == ws,
                arda_checker=self.arda_checker,
            )
            sender, receiver = CrystalBusEndpoint.pair(peer_policy=policy, workspace_id=workspace_id, arda_ref=arda_ref)
            adapter = CapsuleExecutionAdapter(capsule_verifier=capsule_verifier, capability_ledger=ledger)

            def execute_route(req: ResidualComputeRequest, decision_digest: str) -> RouteExecutionResult:
                lease = ledger.issue(
                    crystal_id=entry.crystal_id,
                    capsule_digest=entry.capsule_digest,
                    audience="executor:g5-bounded-write",
                    capability="crystal.execute.bounded_write",
                    ttl=60,
                )
                sender.send_capsule(CapsuleOffer(
                    capsule_digest=entry.capsule_digest,
                    capsule_size=entry.size_bytes,
                    crystal_id=entry.crystal_id,
                    promotion_digest=entry.promotion_digest,
                    capability_lease_digest=lease.digest,
                    audience="executor:g5-bounded-write",
                    expires_at=time.time() + 60,
                ), entry.fd)
                received = receiver.receive_capsule()
                started = time.monotonic_ns()
                try:
                    execution = adapter.execute(
                        received,
                        expected_workspace=workspace_id,
                        expected_privacy_domain=privacy_domain,
                        expected_audience="executor:g5-bounded-write",
                        active_policy_digest=policy_digest,
                        active_source_state_digest=source_state_digest,
                        promotion_is_valid=lambda digest: digest == promotion_digest,
                        actuator=_write_actuator,
                        postcondition_verifier=_postconditions,
                        rollback=_rollback,
                    )
                finally:
                    received.close()
                verified = execution.postconditions_verified or (
                    force_failure and execution.rollback_performed and execution.final_status == "rolled_back_after_verification_failure"
                )
                return RouteExecutionResult(
                    route=ResidualRoute.PROMOTED_CRYSTAL,
                    authority_used=ResidualAuthority.ONE_USE_EXECUTE,
                    output=execution,
                    verified=verified,
                    execution_digest=execution.execution_digest,
                    actual_latency_ms=(time.monotonic_ns() - started) / 1_000_000,
                    actual_cpu_ms=0.0,
                    provider_calls=0,
                    local_inference_calls=0,
                    physical_effects=1,
                )

            plane = ResidualComputePlane(
                ResidualComputeGovernor({"g5_crystal": lambda req: (candidate,)}),
                {ResidualRoute.PROMOTED_CRYSTAL: execute_route},
                sensorium_sink=self.sensorium_sink,
            )
            output, closure = plane.run(request)
            execution = output
            after_workspace = _workspace_state_digest(root)
            after_target = _digest_path(target)
            return G5PhaseReceipt(
                phase=phase,
                status=execution.final_status,
                capsule_digest=entry.capsule_digest,
                execution_digest=execution.execution_digest,
                authority_consumed=execution.authority_consumed,
                postconditions_verified=execution.postconditions_verified,
                rollback_performed=execution.rollback_performed,
                target_digest_before=before_target,
                target_digest_after=after_target,
                workspace_digest_before=before_workspace,
                workspace_digest_after=after_workspace,
                filesystem_writes=1,
                network_calls=0,
            )
        finally:
            if sender is not None:
                sender.sock.close()
            if receiver is not None:
                receiver.sock.close()
            registry.close_all()
            handle.close()

    def _resolve_lease(self, pid: int, workspace_id: str) -> Mapping[str, Any]:
        lease = dict(self.process_lease_resolver(pid))
        if not lease.get("workspace"):
            lease["workspace"] = workspace_id
        return lease
