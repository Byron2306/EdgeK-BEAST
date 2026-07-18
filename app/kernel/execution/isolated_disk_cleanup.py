"""Race-free cgroup+namespace execution for a sealed cleanup manifest."""
from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.disk_pressure_cleanup import CleanupManifest
from app.kernel.execution.race_free_cgroup_launcher import (
    NativeCgroupLauncherCompiler, RaceFreeCgroupLauncher, RaceFreeLaunchAuthorization,
)
from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class IsolatedDiskCleanupReceipt:
    mission_id: str
    manifest_digest: str
    cgroup_path: str
    worker_digest: str
    launch_receipt_digest: str
    files_removed: int
    bytes_removed: int
    targets_absent: bool
    clone3_into_cgroup: bool
    namespace_isolation: bool
    filesystem_secret_isolation: bool
    ambient_network_denied: bool
    root_cleanup_confirmed: bool
    verified: bool
    receipt_digest: str = ""

    def sealed(self):
        value=asdict(self);value.pop("receipt_digest",None);return replace(self,receipt_digest=content_hash(value))
    def validate(self):
        value=asdict(self);value.pop("receipt_digest",None)
        if self.receipt_digest!=content_hash(value):raise ValueError("isolated cleanup receipt is tampered")
        complete=all((self.targets_absent,self.clone3_into_cgroup,self.namespace_isolation,
                      self.filesystem_secret_isolation,self.ambient_network_denied,self.root_cleanup_confirmed))
        if self.verified!=complete:raise ValueError("isolated destructive cleanup claim is incomplete")


class IsolatedDiskCleanupRunner:
    def __init__(self, capsule: Any, launcher: Path, build_root: Path):
        self.capsule,self.launcher,self.build_root=capsule,Path(launcher),Path(build_root)

    @staticmethod
    def _manifest_bytes(manifest: CleanupManifest) -> bytes:
        manifest.validate()
        rows=[f"BEAST_DISK_V1\t{len(manifest.entries)}\t{manifest.total_bytes}\t{manifest.manifest_digest}"]
        for item in manifest.entries:
            rows.append(f"{item.relative_path}\t{item.device}\t{item.inode}\t{item.size}\t{item.mtime_ns}\t{item.sha256.removeprefix('sha256:')}")
        return ("\n".join(rows)+"\n").encode()

    def run(self, *, mission_id: str, workspace: Path, manifest: CleanupManifest,
            approved_by: str, approval_receipt_id: str) -> IsolatedDiskCleanupReceipt:
        workspace=Path(workspace).resolve();manifest.validate()
        compiler=NativeCgroupLauncherCompiler();worker=compiler.compile_disk_cleanup_worker(self.build_root/"beast-disk-cleanup-worker")
        runner=RaceFreeCgroupLauncher(self.launcher);worker_digest=runner._digest(worker)
        descriptor,path=tempfile.mkstemp(prefix="beast-cleanup-manifest-",dir=self.build_root)
        try:
            os.write(descriptor,self._manifest_bytes(manifest));os.fsync(descriptor);os.lseek(descriptor,0,os.SEEK_SET)
            workspace_fd=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
            try:
                launch=runner.launch(mission_id,self.capsule.path,worker,
                    RaceFreeLaunchAuthorization(mission_id,str(self.capsule.path),worker_digest,approved_by,
                        approval_receipt_id,"descriptor-bound destructive cleanup"),
                    timeout_seconds=15,inherited_data_fds=(workspace_fd,descriptor))
            finally:os.close(workspace_fd)
        finally:
            os.close(descriptor);Path(path).unlink(missing_ok=True)
        evidence=launch.worker_evidence
        targets_absent=all(not (workspace/item.relative_path).exists() for item in manifest.entries)
        value=IsolatedDiskCleanupReceipt(mission_id,manifest.manifest_digest,str(self.capsule.path),worker_digest,
            launch.receipt_digest,int(evidence.get("files_removed") or 0),int(evidence.get("bytes_removed") or 0),targets_absent,
            launch.placement_method=="clone3_into_cgroup" and launch.membership_observed_before_release,
            launch.combined_cgroup_namespace_proven,launch.filesystem_secret_isolation_proven,
            evidence.get("ambient_network_denied") is True,launch.root_cleanup_confirmed,
            bool(targets_absent and evidence.get("cleanup_verified") is True and evidence.get("manifest_digest")==manifest.manifest_digest
                 and int(evidence.get("files_removed") or 0)==len(manifest.entries)
                 and int(evidence.get("bytes_removed") or 0)==manifest.total_bytes
                 and launch.combined_cgroup_namespace_proven and launch.filesystem_secret_isolation_proven
                 and launch.root_cleanup_confirmed)).sealed()
        value.validate();return value


class ProductionIsolatedDiskCleanupDelegate:
    """ComputePlane adapter that preserves proof and authority bindings."""

    def __init__(self, runner: IsolatedDiskCleanupRunner, *, approved_by: str):
        self.runner = runner
        self.approved_by = approved_by

    def __call__(self, *, mission_id: str, workspace: Path, manifest: CleanupManifest,
                 approval_receipt: str, applicability_proof: Any,
                 execution_authorization: Any) -> Mapping[str, Any]:
        if not approval_receipt or not self.approved_by:
            raise PermissionError("production cleanup delegate lacks destructive approval")
        if getattr(applicability_proof, "proof_digest", "") == "":
            raise PermissionError("production cleanup delegate lacks applicability proof")
        if getattr(execution_authorization, "request_digest", "") != getattr(
                applicability_proof, "execution_request_digest", ""):
            raise PermissionError("production cleanup authority is not bound to applicability")
        receipt = self.runner.run(
            mission_id=mission_id, workspace=workspace, manifest=manifest,
            approved_by=self.approved_by, approval_receipt_id=approval_receipt,
        )
        receipt.validate()
        return asdict(receipt)
