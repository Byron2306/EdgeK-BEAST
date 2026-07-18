"""Python governance boundary for the descriptor-only clone3 launcher."""

from __future__ import annotations

import hashlib
import json
import os
import select
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


@dataclass(frozen=True)
class RaceFreeLaunchAuthorization:
    mission_id: str
    cgroup_path: str
    worker_digest: str
    approved_by: str
    approval_receipt_id: str
    reason: str

    def validate(self, *, mission_id: str, cgroup_path: Path, worker_digest: str) -> None:
        if (
            self.mission_id != mission_id
            or self.cgroup_path != str(cgroup_path)
            or self.worker_digest != worker_digest
            or not all((self.approved_by, self.approval_receipt_id, self.reason))
        ):
            raise PermissionError("race-free launch authority binding mismatch")


@dataclass(frozen=True)
class RaceFreeLaunchReceipt:
    mission_id: str
    cgroup_path: str
    worker_digest: str
    child_pid: int
    placement_method: str
    membership_observed_before_release: bool
    child_exit_code: int
    parent_namespace_inodes: dict[str, int]
    worker_evidence: dict[str, Any]
    combined_cgroup_namespace_proven: bool
    filesystem_secret_isolation_proven: bool
    root_cleanup_confirmed: bool
    stderr_retained: bool
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def sealed(self) -> "RaceFreeLaunchReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("race-free launch receipt is tampered")
        if not (
            self.child_pid > 0
            and self.placement_method == "clone3_into_cgroup"
            and self.membership_observed_before_release
            and self.stderr_retained is False
        ):
            raise ValueError("race-free cgroup placement claim is incomplete")
        if self.combined_cgroup_namespace_proven and not (
            self.worker_evidence.get("beast_object_type") == "isolated_worker_evidence"
            and self.worker_evidence.get("private_proc_mounted") is True
            and int(self.worker_evidence.get("non_loopback_interface_count") or 0) == 0
            and len(self.worker_evidence.get("namespace_inodes") or {}) == 4
            and all(
                int((self.worker_evidence.get("namespace_inodes") or {}).get(name) or 0)
                != int(self.parent_namespace_inodes.get(name) or 0)
                for name in ("mnt", "pid", "net", "user")
            )
        ):
            raise ValueError("combined cgroup/namespace claim is incomplete")
        if self.filesystem_secret_isolation_proven and not (
            self.combined_cgroup_namespace_proven
            and self.worker_evidence.get("filesystem_root_isolated") is True
            and self.worker_evidence.get("secrets_denied") is True
            and self.worker_evidence.get("isolated_loopback_service_verified") is True
            and self.worker_evidence.get("ambient_network_denied") is True
            and self.root_cleanup_confirmed
        ):
            raise ValueError("filesystem/secret isolation claim is incomplete")


@dataclass(frozen=True)
class LaunchFallbackBoundary:
    mission_id: str
    requested_method: str
    fallback_method: str
    destructive_execution_allowed: bool
    reason: str
    receipt_digest: str = ""

    def sealed(self) -> "LaunchFallbackBoundary":
        body = asdict(self); body.pop("receipt_digest", None)
        return replace(self, receipt_digest=content_hash(body))

    def validate(self) -> None:
        body = asdict(self); body.pop("receipt_digest", None)
        if self.receipt_digest != content_hash(body) or self.destructive_execution_allowed:
            raise ValueError("unsafe clone3 fallback boundary")


class NativeCgroupLauncherCompiler:
    def __init__(self, source: Path | None = None):
        self.source = source or Path(__file__).parents[3] / "native" / "beast_cgroup_launcher.c"

    def compile(self, output: Path) -> Path:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(output), str(self.source)],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("native cgroup launcher compilation failed")
        output.chmod(0o500)
        return output

    def compile_worker(self, output: Path) -> Path:
        source = self.source.with_name("beast_isolated_worker.c")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(output), str(source)],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("native isolated worker compilation failed")
        output.chmod(0o500)
        return output

    def compile_fault_worker(self, output: Path, mode: int) -> Path:
        if int(mode) not in {1, 2, 3, 4, 5}:
            raise ValueError("unsupported reviewed fault-worker mode")
        source = self.source.with_name("beast_mission_fault_worker.c")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             f"-DWORKER_MODE={int(mode)}", "-o", str(output), str(source)],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("native mission fault worker compilation failed")
        output.chmod(0o500)
        return output

    def compile_disk_cleanup_worker(self, output: Path) -> Path:
        source = self.source.with_name("beast_disk_cleanup_worker.c")
        output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(output), str(source), "-lcrypto"],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("native disk cleanup worker compilation failed")
        output.chmod(0o500); return output


class RaceFreeCgroupLauncher:
    def __init__(self, launcher: Path, *, sensorium: SensoriumRuntime | None = None):
        self.launcher = Path(launcher)
        self.sensorium = sensorium

    def launch(
        self,
        mission_id: str,
        cgroup_path: Path,
        worker: Path,
        authorization: RaceFreeLaunchAuthorization,
        *,
        timeout_seconds: float = 5.0,
        inherited_data_fds: tuple[int, int] | None = None,
    ) -> RaceFreeLaunchReceipt:
        cgroup_path, worker = Path(cgroup_path), Path(worker)
        worker_digest = self._digest(worker)
        parent_namespaces = {
            name: int(os.stat(f"/proc/self/ns/{name}").st_ino)
            for name in ("mnt", "pid", "net", "user")
        }
        authorization.validate(mission_id=mission_id, cgroup_path=cgroup_path, worker_digest=worker_digest)
        if not self.launcher.is_file() or not os.access(self.launcher, os.X_OK):
            raise RuntimeError("reviewed native cgroup launcher is unavailable")
        cgroup_fd = os.open(cgroup_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        worker_fd = os.open(worker, os.O_RDONLY | os.O_CLOEXEC)
        gate_read, gate_write = os.pipe2(os.O_CLOEXEC)
        process = None
        try:
            command = [str(self.launcher), str(cgroup_fd), str(worker_fd), str(gate_read)]
            inherited = tuple(inherited_data_fds or ())
            if inherited and len(inherited) != 2:
                raise ValueError("cleanup launcher requires workspace and manifest descriptors")
            command.extend(str(item) for item in inherited)
            process = subprocess.Popen(
                command,
                pass_fds=(cgroup_fd, worker_fd, gate_read, *inherited),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            os.close(gate_read)
            gate_read = -1
            assert process.stdout is not None
            ready, _, _ = select.select([process.stdout], [], [], max(0.1, timeout_seconds))
            if not ready:
                raise TimeoutError("native launcher did not report child placement")
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("native launcher refused child placement")
            try:
                report = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("native launcher emitted an invalid placement report") from exc
            child_pid = int(report.get("pid") or 0)
            placement = str(report.get("placement") or "")
            membership = child_pid in self._member_pids(cgroup_path / "cgroup.procs")
            if child_pid <= 0 or placement != "clone3_into_cgroup" or not membership:
                raise RuntimeError("child cgroup membership was not observed before release")
            os.write(gate_write, b"R")
            os.close(gate_write)
            gate_write = -1
            exit_code = process.wait(timeout=max(0.1, timeout_seconds))
            remaining = process.stdout.read()
            worker_evidence: dict[str, Any] = {}
            cleanup_evidence: dict[str, Any] = {}
            for candidate in remaining.splitlines():
                try:
                    value = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if value.get("beast_object_type") == "isolated_worker_evidence":
                    worker_evidence = value
                elif value.get("beast_object_type") == "mission_fault_evidence":
                    worker_evidence = value
                elif value.get("beast_object_type") == "isolated_worker_cleanup":
                    cleanup_evidence = value
            combined = bool(
                exit_code == 0
                and worker_evidence.get("private_proc_mounted") is True
                and int(worker_evidence.get("non_loopback_interface_count") or 0) == 0
                and len(worker_evidence.get("namespace_inodes") or {}) == 4
                and all(
                    int((worker_evidence.get("namespace_inodes") or {}).get(name) or 0)
                    != parent_namespaces[name]
                    for name in ("mnt", "pid", "net", "user")
                )
            )
            root_cleanup = cleanup_evidence.get("root_cleanup_confirmed") is True
            filesystem_proven = bool(
                combined
                and worker_evidence.get("filesystem_root_isolated") is True
                and worker_evidence.get("secrets_denied") is True
                and root_cleanup
            )
            receipt = RaceFreeLaunchReceipt(
                mission_id, str(cgroup_path), worker_digest, child_pid, placement,
                membership, exit_code, parent_namespaces, worker_evidence, combined,
                filesystem_proven, root_cleanup, False,
            ).sealed()
            receipt.validate()
            self._observe(receipt)
            return receipt
        finally:
            for fd in (cgroup_fd, worker_fd, gate_read, gate_write):
                if fd >= 0:
                    try: os.close(fd)
                    except OSError: pass
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=2)

    @staticmethod
    def refused_fallback(mission_id: str, reason: str) -> LaunchFallbackBoundary:
        """Never disguise post-fork cgroup attachment as race-free placement."""
        if not mission_id or not reason:
            raise ValueError("fallback refusal requires mission and reason")
        receipt = LaunchFallbackBoundary(
            mission_id, "clone3_into_cgroup", "stopped_child_then_cgroup_procs",
            False, reason,
        ).sealed()
        receipt.validate()
        return receipt

    def _observe(self, receipt: RaceFreeLaunchReceipt) -> None:
        if self.sensorium is None:
            return
        self.sensorium.observe_physical(
            event_type="isolation.worker_born_in_cgroup",
            source="race_free_cgroup_launcher",
            payload_schema="beast.sensor.isolation.worker_birth.v1",
            operation="isolation.worker_birth",
            phase="verification",
            subject=f"mission:{receipt.mission_id}",
            result="success",
            payload={
                "receipt_digest": receipt.receipt_digest,
                "worker_digest": receipt.worker_digest,
                "child_pid": receipt.child_pid,
                "placement_method": receipt.placement_method,
                "membership_observed_before_release": receipt.membership_observed_before_release,
                "combined_cgroup_namespace_proven": receipt.combined_cgroup_namespace_proven,
                "filesystem_secret_isolation_proven": receipt.filesystem_secret_isolation_proven,
                "root_cleanup_confirmed": receipt.root_cleanup_confirmed,
                "namespace_inodes": dict(receipt.worker_evidence.get("namespace_inodes") or {}),
                "non_loopback_interface_count": receipt.worker_evidence.get("non_loopback_interface_count"),
                "filesystem_root_isolated": receipt.worker_evidence.get("filesystem_root_isolated", False),
                "secrets_denied": receipt.worker_evidence.get("secrets_denied", False),
                "reads": [f"cgroup_membership:{receipt.cgroup_path}"],
                "produces": [f"worker_birth_receipt:{receipt.receipt_digest}"],
                "descriptor_refs": [f"cgroup:{receipt.mission_id}"],
            },
            mission_id=receipt.mission_id,
            confidence_method="clone3_into_cgroup_and_cgroup_procs_readback",
        )

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _member_pids(path: Path) -> tuple[int, ...]:
        try:
            return tuple(int(item) for item in path.read_text(encoding="utf-8").split())
        except (OSError, ValueError):
            return ()
