from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.kernel.compute.capsule_registry import CapsuleRegistry
from app.kernel.compute.crystal_capsule_forge import CrystalCapsuleForge
from app.kernel.compute.residual_candidate import ResidualCandidate
from app.kernel.compute.residual_compute_governor import (
    ResidualComputeGovernor,
    ResidualComputeRequest,
)
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
from app.kernel.crystals.capsule_contracts import (
    ExecutionBounds,
    SealedCrystalCapsuleManifest,
    canonical_json,
    sha256_digest as bytes_sha256_digest,
)
from app.kernel.crystals.capsule_signing import Ed25519CapsuleSigner, Ed25519CapsuleVerifier
from app.kernel.crystals.capsule_verifier import CapsuleVerifier
from app.kernel.execution.capsule_execution_adapter import CapsuleExecutionAdapter
from app.kernel.execution.one_use_capability import OneUseCapabilityLedger


READ_ONLY_TASK_CLASS = "grand_closure_read_only_capsule_canary"
READ_ONLY_OPCODE = "READ_ONLY_REPOSITORY_SUMMARY"


@dataclass(frozen=True, slots=True)
class RepositoryFingerprint:
    root_digest: str
    file_count: int
    directory_count: int
    byte_count: int
    entries_sampled: int


@dataclass(frozen=True, slots=True)
class G4CanaryReceipt:
    canary_id: str
    request_digest: str
    decision_digest: str
    capsule_digest: str
    execution_digest: str
    pre_fingerprint: str
    post_fingerprint: str
    repository_unchanged: bool
    provider_calls: int
    local_inference_calls: int
    filesystem_writes: int
    network_calls: int
    authority_used: str
    capability_consumed: bool
    postconditions_verified: bool
    raw_payload_retained: bool
    created_at: str
    evidence_digest: str


def _entry_record(path: Path, root: Path) -> tuple[str, str, int, int]:
    st = path.lstat()
    rel = "." if path == root else path.relative_to(root).as_posix()
    mode = stat.S_IFMT(st.st_mode)
    size = st.st_size if stat.S_ISREG(st.st_mode) else 0
    return rel, oct(mode), size, st.st_mtime_ns


def fingerprint_repository(root: str | os.PathLike[str], *, max_entries: int = 10_000) -> RepositoryFingerprint:
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise ValueError("canary root must be a directory")
    records: list[tuple[str, str, int, int]] = [_entry_record(base, base)]
    file_count = 0
    directory_count = 1
    byte_count = 0
    for current, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in {".git", ".beast_backups", "__pycache__", ".pytest_cache"})
        for name in dirnames:
            path = Path(current) / name
            records.append(_entry_record(path, base))
            directory_count += 1
            if len(records) >= max_entries:
                break
        if len(records) >= max_entries:
            break
        for name in sorted(filenames):
            path = Path(current) / name
            try:
                record = _entry_record(path, base)
            except FileNotFoundError:
                continue
            records.append(record)
            file_count += 1
            byte_count += record[2]
            if len(records) >= max_entries:
                break
        if len(records) >= max_entries:
            break
    digest = bytes_sha256_digest(canonical_json(records))
    return RepositoryFingerprint(digest, file_count, directory_count, byte_count, len(records))


def _readonly_actuator(plan: Mapping[str, Any], bounds: Mapping[str, Any]) -> Mapping[str, Any]:
    if plan.get("opcode") != READ_ONLY_OPCODE:
        raise PermissionError("G4 canary accepts only the read-only repository summary opcode")
    if tuple(bounds.get("network_scope", ())) != ():
        raise PermissionError("G4 canary forbids network scope")
    root = str(plan["root"])
    max_entries = min(int(plan.get("max_entries", 10_000)), 10_000)
    before = fingerprint_repository(root, max_entries=max_entries)
    # The operation is intentionally observational. It computes a stable summary only.
    summary = {
        "root_digest": before.root_digest,
        "file_count": before.file_count,
        "directory_count": before.directory_count,
        "byte_count": before.byte_count,
        "entries_sampled": before.entries_sampled,
    }
    after = fingerprint_repository(root, max_entries=max_entries)
    return {
        "summary": summary,
        "pre_fingerprint": before.root_digest,
        "post_fingerprint": after.root_digest,
        "repository_unchanged": before.root_digest == after.root_digest,
        "filesystem_writes": 0,
        "network_calls": 0,
    }


def _readonly_postconditions(plan: Mapping[str, Any], effect: Mapping[str, Any], verifier_manifest: Mapping[str, Any]) -> bool:
    return bool(
        verifier_manifest.get("verifier_id") == "g4-readonly-v1"
        and plan.get("opcode") == READ_ONLY_OPCODE
        and effect.get("repository_unchanged") is True
        and effect.get("filesystem_writes") == 0
        and effect.get("network_calls") == 0
        and effect.get("pre_fingerprint") == effect.get("post_fingerprint")
    )


class G4ReadOnlyCanary:
    """Run one real sealed-capsule, descriptor-bus, one-use-authority read-only canary."""

    def __init__(
        self,
        *,
        sensorium_sink: Callable[[Mapping[str, Any]], str] | None = None,
        process_lease_resolver: Callable[[int], Mapping[str, Any]] | None = None,
        arda_checker: Callable[[Mapping[str, Any], str], bool] | None = None,
    ) -> None:
        self.sensorium_sink = sensorium_sink or (lambda event: sha256_digest(event))
        self.process_lease_resolver = process_lease_resolver or (
            lambda pid: {"lease_id": f"g4-process:{pid}", "active": True, "workspace": ""}
        )
        self.arda_checker = arda_checker or (lambda lease, appraisal: appraisal == "arda:g4-read-only-approved")

    def run(
        self,
        *,
        repository_root: str | os.PathLike[str],
        workspace_id: str,
        privacy_domain: str,
        policy_digest: str,
        source_state_digest: str,
        arda_ref: str = "arda:g4-read-only-approved",
        max_entries: int = 10_000,
    ) -> G4CanaryReceipt:
        root = str(Path(repository_root).resolve(strict=True))
        pre = fingerprint_repository(root, max_entries=max_entries)
        signer = Ed25519CapsuleSigner("g4-forge")
        capsule_verifier = CapsuleVerifier(Ed25519CapsuleVerifier({"g4-forge": signer.public_key}))
        registry = CapsuleRegistry(max_entries=4)
        forge = CrystalCapsuleForge(registry=registry, event_sink=self.sensorium_sink)
        ledger = OneUseCapabilityLedger()
        plan = {"version": 1, "opcode": READ_ONLY_OPCODE, "root": root, "max_entries": int(max_entries)}
        artifact_digest = bytes_sha256_digest(canonical_json(plan))
        promotion_digest = sha256_digest({"class": READ_ONLY_TASK_CLASS, "artifact": artifact_digest})
        manifest = SealedCrystalCapsuleManifest(
            crystal_id="grand-closure-g4-read-only",
            crystal_ir_version=1,
            artifact_digest=artifact_digest,
            promotion_digest=promotion_digest,
            policy_digest=policy_digest,
            source_state_digest=source_state_digest,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            task_class=READ_ONLY_TASK_CLASS,
            audience_class="executor:g4-read-only",
            required_capability="crystal.execute.read_only",
            one_use_required=True,
            expires_at=time.time() + 300,
            verifier_id="g4-readonly-v1",
            rollback_contract_digest=sha256_digest({"rollback": "none_required_read_only"}),
            signer_id="g4-forge",
            execution_bounds=ExecutionBounds(
                max_runtime_ms=10_000,
                max_memory_bytes=64 * 1024 * 1024,
                max_output_bytes=256 * 1024,
                filesystem_scope=(root,),
                network_scope=(),
            ),
        )
        handle, _ = forge.prepare(
            manifest=manifest,
            crystal_ir=plan,
            verifier_manifest={"verifier_id": "g4-readonly-v1", "postconditions": ["repository unchanged"]},
            signer=signer,
            ttl_seconds=300,
            predicted_reuse_count=1,
        )
        try:
            entry = registry.get(handle.receipt.capsule_id, workspace_id=workspace_id, privacy_domain=privacy_domain)
            if entry is None:
                raise RuntimeError("prepared G4 capsule was not registered")
            request = ResidualComputeRequest(
                request_id="g4-read-only-canary",
                request_digest=sha256_digest({"root": root, "source": source_state_digest, "policy": policy_digest}),
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                task_class=READ_ONLY_TASK_CLASS,
                payload={"capsule_id": entry.capsule_id},
                policy_digest=policy_digest,
            )
            candidate = ResidualCandidate(
                candidate_id="g4-promoted-crystal",
                route=ResidualRoute.PROMOTED_CRYSTAL,
                applicability=ApplicabilityState.APPLICABLE,
                verification=VerificationState.VERIFIED,
                authority=ResidualAuthority.ONE_USE_EXECUTE,
                predicted_latency_ms=5.0,
                predicted_cpu_ms=2.0,
                predicted_memory_bytes=entry.size_bytes,
                predicted_monetary_cost=0.0,
                confidence=1.0,
                expected_quality=1.0,
                failure_probability=0.0,
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                evidence_digest=sha256_digest({"promotion": promotion_digest, "capsule": entry.capsule_digest}),
                metadata={"capsule_id": entry.capsule_id, "read_only": True},
            )
            policy = PeerAdmissionPolicy(
                expected_uid=os.getuid(),
                process_lease_resolver=lambda pid: self._resolve_lease(pid, workspace_id),
                workspace_checker=lambda lease, ws: bool(lease.get("active")) and lease.get("workspace") == ws,
                arda_checker=self.arda_checker,
            )
            sender, receiver = CrystalBusEndpoint.pair(
                peer_policy=policy,
                workspace_id=workspace_id,
                arda_ref=arda_ref,
            )
            execution_adapter = CapsuleExecutionAdapter(capsule_verifier=capsule_verifier, capability_ledger=ledger)

            def execute_route(req: ResidualComputeRequest, decision_digest: str) -> RouteExecutionResult:
                lease = ledger.issue(
                    crystal_id=entry.crystal_id,
                    capsule_digest=entry.capsule_digest,
                    audience="executor:g4-read-only",
                    capability="crystal.execute.read_only",
                    ttl=60,
                )
                offer = CapsuleOffer(
                    capsule_digest=entry.capsule_digest,
                    capsule_size=entry.size_bytes,
                    crystal_id=entry.crystal_id,
                    promotion_digest=entry.promotion_digest,
                    capability_lease_digest=lease.digest,
                    audience="executor:g4-read-only",
                    expires_at=time.time() + 60,
                )
                sender.send_capsule(offer, entry.fd)
                received = receiver.receive_capsule()
                started = time.monotonic_ns()
                try:
                    execution = execution_adapter.execute(
                        received,
                        expected_workspace=workspace_id,
                        expected_privacy_domain=privacy_domain,
                        expected_audience="executor:g4-read-only",
                        active_policy_digest=policy_digest,
                        active_source_state_digest=source_state_digest,
                        promotion_is_valid=lambda digest: digest == promotion_digest,
                        actuator=_readonly_actuator,
                        postcondition_verifier=_readonly_postconditions,
                        rollback=None,
                    )
                finally:
                    received.close()
                elapsed = (time.monotonic_ns() - started) / 1_000_000
                return RouteExecutionResult(
                    route=ResidualRoute.PROMOTED_CRYSTAL,
                    authority_used=ResidualAuthority.ONE_USE_EXECUTE,
                    output=execution,
                    verified=execution.postconditions_verified,
                    execution_digest=execution.execution_digest,
                    actual_latency_ms=elapsed,
                    actual_cpu_ms=0.0,
                    provider_calls=0,
                    local_inference_calls=0,
                    physical_effects=0,
                )

            governor = ResidualComputeGovernor({"g4_crystal": lambda req: (candidate,)})
            plane = ResidualComputePlane(
                governor,
                {ResidualRoute.PROMOTED_CRYSTAL: execute_route},
                sensorium_sink=self.sensorium_sink,
            )
            output, closure = plane.run(request)
            post = fingerprint_repository(root, max_entries=max_entries)
            body = {
                "canary_id": "g4-read-only-canary",
                "request_digest": request.request_digest,
                "decision_digest": closure.decision_digest,
                "capsule_digest": entry.capsule_digest,
                "execution_digest": output.execution_digest,
                "pre_fingerprint": pre.root_digest,
                "post_fingerprint": post.root_digest,
                "repository_unchanged": pre.root_digest == post.root_digest,
                "provider_calls": 0,
                "local_inference_calls": 0,
                "filesystem_writes": 0,
                "network_calls": 0,
                "authority_used": ResidualAuthority.ONE_USE_EXECUTE.value,
                "capability_consumed": output.authority_consumed,
                "postconditions_verified": output.postconditions_verified,
                "raw_payload_retained": False,
                "created_at": utc_now_iso(),
            }
            if not body["repository_unchanged"]:
                raise RuntimeError("G4 canary repository fingerprint changed")
            if not body["postconditions_verified"] or not body["capability_consumed"]:
                raise RuntimeError("G4 canary execution did not close lawfully")
            return G4CanaryReceipt(**body, evidence_digest=sha256_digest(body))
        finally:
            try:
                sender.sock.close()  # type: ignore[name-defined]
                receiver.sock.close()  # type: ignore[name-defined]
            except Exception:
                pass
            registry.close_all()
            handle.close()

    def _resolve_lease(self, pid: int, workspace_id: str) -> Mapping[str, Any]:
        lease = dict(self.process_lease_resolver(pid))
        if not lease.get("workspace"):
            lease["workspace"] = workspace_id
        return lease
