"""Operational Phase-3 disposable stale lockfile/PID-file domain.

This domain gives Phase 3 a second live operational proof surface beside the
Phase-2 socket listener fossil.  It is deliberately narrow: create two
lockfiles in a disposable temp directory, remove only the leased stale PID-file,
preserve an unrelated live control PID-file, and refuse stale lease replay,
current-PID cleanup and path escape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)


PHASE3_LOCKFILE_VERSION = "2026-08-04.phase3.lockfile.v1"
LOCKFILE_SCOPE = "disposable_tempdir_lockfiles_only"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class LockfileObservation:
    label: str
    path: str
    exists: bool
    inode: int
    size_bytes: int
    content_digest: str
    parsed_pid: int
    parsed_generation: str
    parsed_owner: str
    pid_alive: bool
    observed_at: str

    @property
    def is_stale_pidfile(self) -> bool:
        return self.exists and self.parsed_pid > 0 and not self.pid_alive

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3LockfileWorldLease:
    beast_object_type: str
    version: str
    lease_id: str
    capability_id: str
    capability_digest: str
    world_state_digest: str
    root_path: str
    stale_lock_path: str
    stale_lock_content_digest: str
    stale_pid: int
    control_lock_path: str
    control_lock_content_digest: str
    control_pid: int
    execution_scope: str
    acquired_at: str
    expires_at: str
    provider_calls_used: int = 0
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("capability_digest", "world_state_digest", "stale_lock_content_digest", "control_lock_content_digest"):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.execution_scope != LOCKFILE_SCOPE:
            raise ValueError("Phase-3 lockfile lease has unsafe scope")
        if self.provider_calls_used != 0:
            raise ValueError("Phase-3 lockfile lease must be zero-provider")
        if self.production_authority_allowed:
            raise ValueError("Phase-3 lockfile lease cannot grant production authority")

    @property
    def lease_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3LockfileCleanupReceipt:
    beast_object_type: str
    version: str
    run_id: str
    executed: bool
    refused_reason: str
    world_state_digest: str
    live_world_state_digest_before: str
    live_world_state_digest_after: str
    lease_digest: str
    capability_digest: str
    before_stale: LockfileObservation
    before_control: LockfileObservation
    after_stale: LockfileObservation
    after_control: LockfileObservation
    stale_lock_removed: bool
    unrelated_control_unchanged: bool
    stale_pid_was_dead: bool
    provider_calls_used: int
    execution_scope: str
    production_authority_allowed: bool
    green_gates: tuple[str, ...]
    red_gates: tuple[str, ...]
    observed_at: str

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3LockfileReplayReceipt:
    beast_object_type: str
    version: str
    run_id: str
    refused: bool
    attempted_world_state_digest: str
    expected_world_state_digest: str
    live_world_state_digest: str
    lease_digest: str
    effect_digest_before: str
    effect_digest_after: str
    zero_effect: bool
    provider_calls_used: int
    refusal_reason: str
    green_gates: tuple[str, ...]
    red_gates: tuple[str, ...]
    observed_at: str

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(slots=True)
class Phase3LockfileLab:
    run_id: str
    tempdir: tempfile.TemporaryDirectory[str]
    root: Path
    stale_lock: Path
    control_lock: Path
    stale_pid: int
    control_pid: int

    def cleanup(self) -> None:
        self.tempdir.cleanup()


def phase3_lockfile_capability() -> dict[str, Any]:
    return {
        "capability": "stale_pid_lockfile_cleanup",
        "operation": "remove_exact_stale_pidfile_only",
        "scope": LOCKFILE_SCOPE,
        "nonclaims": ("production_authority", "host_wide_file_cleanup", "current_process_cleanup", "path_escape"),
    }


def phase3_lockfile_capability_digest() -> str:
    return sha256_digest(phase3_lockfile_capability())


def start_phase3_lockfile_lab(
    *,
    run_id: str = "dai-phase3-lockfile-local-001",
    stale_pid: int | None = None,
    control_pid: int | None = None,
) -> Phase3LockfileLab:
    tempdir = tempfile.TemporaryDirectory(prefix="dai-phase3-lockfile-")
    root = Path(tempdir.name).resolve()
    stale = root / "stale-service.pidlock"
    control = root / "control-service.pidlock"
    stale_value = stale_pid if stale_pid is not None else _find_non_alive_pid()
    control_value = control_pid if control_pid is not None else os.getpid()
    _write_lockfile(stale, pid=stale_value, owner="phase3-stale-service", generation="old")
    _write_lockfile(control, pid=control_value, owner="phase3-control-service", generation="current")
    return Phase3LockfileLab(
        run_id=run_id,
        tempdir=tempdir,
        root=root,
        stale_lock=stale,
        control_lock=control,
        stale_pid=stale_value,
        control_pid=control_value,
    )


def observe_lockfile(path: str | Path, *, label: str) -> LockfileObservation:
    source = Path(path)
    exists = source.exists()
    inode = 0
    size = 0
    content_digest = sha256_bytes(b"")
    parsed_pid = 0
    parsed_generation = ""
    parsed_owner = ""
    if exists:
        stat = source.stat()
        raw = source.read_bytes()
        inode = int(stat.st_ino)
        size = int(stat.st_size)
        content_digest = sha256_bytes(raw)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            parsed_pid = int(payload.get("pid") or 0)
            parsed_generation = str(payload.get("generation") or "")
            parsed_owner = str(payload.get("owner") or "")
    return LockfileObservation(
        label=label,
        path=str(source),
        exists=exists,
        inode=inode,
        size_bytes=size,
        content_digest=content_digest,
        parsed_pid=parsed_pid,
        parsed_generation=parsed_generation,
        parsed_owner=parsed_owner,
        pid_alive=pid_alive(parsed_pid),
        observed_at=utc_now_iso(),
    )


def stable_lockfile_world_state(lab: Phase3LockfileLab) -> dict[str, Any]:
    return {
        "run_id": lab.run_id,
        "scope": LOCKFILE_SCOPE,
        "root": str(lab.root),
        "stale": _stable_observation(observe_lockfile(lab.stale_lock, label="stale")),
        "control": _stable_observation(observe_lockfile(lab.control_lock, label="control")),
    }


def stable_lockfile_world_state_digest(lab: Phase3LockfileLab) -> str:
    return sha256_digest(stable_lockfile_world_state(lab))


def lockfile_effect_digest(lab: Phase3LockfileLab) -> str:
    return sha256_digest({
        "world": stable_lockfile_world_state(lab),
        "stale_exists": lab.stale_lock.exists(),
        "control_exists": lab.control_lock.exists(),
    })


def acquire_phase3_lockfile_world_lease(lab: Phase3LockfileLab) -> Phase3LockfileWorldLease:
    now = datetime.now(timezone.utc)
    world_digest = stable_lockfile_world_state_digest(lab)
    stale = observe_lockfile(lab.stale_lock, label="stale")
    control = observe_lockfile(lab.control_lock, label="control")
    return Phase3LockfileWorldLease(
        beast_object_type="dai_phase3_lockfile_world_lease",
        version=PHASE3_LOCKFILE_VERSION,
        lease_id="lease:" + sha256_digest({"run_id": lab.run_id, "world_state_digest": world_digest})[-16:],
        capability_id="capability:dai-phase3:stale-pid-lockfile-cleanup:test-only",
        capability_digest=phase3_lockfile_capability_digest(),
        world_state_digest=world_digest,
        root_path=str(lab.root),
        stale_lock_path=str(lab.stale_lock),
        stale_lock_content_digest=stale.content_digest,
        stale_pid=stale.parsed_pid,
        control_lock_path=str(lab.control_lock),
        control_lock_content_digest=control.content_digest,
        control_pid=control.parsed_pid,
        execution_scope=LOCKFILE_SCOPE,
        acquired_at=now.isoformat(),
        expires_at=datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc).isoformat(),
    )


def execute_phase3_lockfile_cleanup(
    lab: Phase3LockfileLab,
    lease: Phase3LockfileWorldLease,
    *,
    supplied_world_state_digest: str | None = None,
) -> Phase3LockfileCleanupReceipt:
    supplied = supplied_world_state_digest or lease.world_state_digest
    require_digest(supplied, field_name="supplied_world_state_digest")
    live_before = stable_lockfile_world_state_digest(lab)
    reason = _cleanup_refusal_reason(lab, lease, supplied=supplied, live_before=live_before)
    if reason:
        return _cleanup_refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason=reason)

    before_stale = observe_lockfile(lab.stale_lock, label="stale")
    before_control = observe_lockfile(lab.control_lock, label="control")
    lab.stale_lock.unlink()
    after_stale = observe_lockfile(lab.stale_lock, label="stale")
    after_control = observe_lockfile(lab.control_lock, label="control")

    stale_removed = before_stale.exists and not after_stale.exists
    control_unchanged = _stable_observation(before_control) == _stable_observation(after_control)
    stale_was_dead = before_stale.parsed_pid == lease.stale_pid and not before_stale.pid_alive
    gates = (
        ("stale_lock_removed", stale_removed),
        ("unrelated_control_unchanged", control_unchanged),
        ("stale_pid_was_dead", stale_was_dead),
        ("provider_call_boundary", True),
        ("bounded_tempdir_scope", lease.execution_scope == LOCKFILE_SCOPE),
    )
    green = tuple(name for name, passed in gates if passed)
    red = tuple(name for name, passed in gates if not passed)
    return Phase3LockfileCleanupReceipt(
        beast_object_type="dai_phase3_lockfile_cleanup_receipt",
        version=PHASE3_LOCKFILE_VERSION,
        run_id=lab.run_id,
        executed=not red,
        refused_reason="",
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=stable_lockfile_world_state_digest(lab),
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        before_stale=before_stale,
        before_control=before_control,
        after_stale=after_stale,
        after_control=after_control,
        stale_lock_removed=stale_removed,
        unrelated_control_unchanged=control_unchanged,
        stale_pid_was_dead=stale_was_dead,
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=green,
        red_gates=red,
        observed_at=utc_now_iso(),
    )


def attempt_phase3_lockfile_stale_world_replay(
    lab: Phase3LockfileLab,
    lease: Phase3LockfileWorldLease,
    *,
    attempted_world_state_digest: str | None = None,
) -> Phase3LockfileReplayReceipt:
    attempted = attempted_world_state_digest or lease.world_state_digest
    require_digest(attempted, field_name="attempted_world_state_digest")
    before = lockfile_effect_digest(lab)
    live = stable_lockfile_world_state_digest(lab)
    refused = attempted != live
    reason = "stale_lease_live_world_state_mismatch" if refused else "live_world_matches_attempted_digest"
    after = lockfile_effect_digest(lab)
    return Phase3LockfileReplayReceipt(
        beast_object_type="dai_phase3_lockfile_stale_world_replay_receipt",
        version=PHASE3_LOCKFILE_VERSION,
        run_id=lab.run_id,
        refused=refused,
        attempted_world_state_digest=attempted,
        expected_world_state_digest=lease.world_state_digest,
        live_world_state_digest=live,
        lease_digest=lease.lease_digest,
        effect_digest_before=before,
        effect_digest_after=after,
        zero_effect=before == after,
        provider_calls_used=0,
        refusal_reason=reason,
        green_gates=("stale_world_refused", "zero_effect", "provider_call_boundary") if refused and before == after else (),
        red_gates=() if refused and before == after else ("stale_world_replay_not_refused",),
        observed_at=utc_now_iso(),
    )


def write_phase3_lockfile_receipt(path: str | Path, receipt: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _dataclass_or_mapping_to_dict(receipt)
    payload["receipt_digest"] = receipt.receipt_digest
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _cleanup_refusal_reason(
    lab: Phase3LockfileLab,
    lease: Phase3LockfileWorldLease,
    *,
    supplied: str,
    live_before: str,
) -> str:
    if supplied != lease.world_state_digest:
        return "supplied_world_state_digest_mismatch"
    if lease.capability_id != "capability:dai-phase3:stale-pid-lockfile-cleanup:test-only":
        return "capability_id_mismatch"
    if lease.capability_digest != phase3_lockfile_capability_digest():
        return "capability_digest_mismatch"
    if lease.execution_scope != LOCKFILE_SCOPE:
        return "unsafe_execution_scope"
    if not _path_inside(lab.root, Path(lease.stale_lock_path)) or not _path_inside(lab.root, Path(lease.control_lock_path)):
        return "lockfile_path_out_of_scope"
    if Path(lease.stale_lock_path).resolve() != lab.stale_lock.resolve():
        return "stale_lock_identity_mismatch"
    if Path(lease.control_lock_path).resolve() != lab.control_lock.resolve():
        return "control_lock_identity_mismatch"
    if live_before != lease.world_state_digest:
        return "live_world_state_digest_mismatch"
    before_stale = observe_lockfile(lab.stale_lock, label="stale")
    before_control = observe_lockfile(lab.control_lock, label="control")
    if not before_stale.exists:
        return "stale_lock_missing"
    if before_stale.content_digest != lease.stale_lock_content_digest or before_stale.parsed_pid != lease.stale_pid:
        return "stale_lock_content_mismatch"
    if before_control.content_digest != lease.control_lock_content_digest or before_control.parsed_pid != lease.control_pid:
        return "control_lock_content_mismatch"
    if before_stale.pid_alive:
        return "stale_pid_is_alive"
    if not before_control.exists or not before_control.pid_alive:
        return "control_pid_not_live"
    return ""


def _cleanup_refusal_receipt(
    *,
    lab: Phase3LockfileLab,
    lease: Phase3LockfileWorldLease,
    live_before: str,
    reason: str,
) -> Phase3LockfileCleanupReceipt:
    before_stale = observe_lockfile(lab.stale_lock, label="stale")
    before_control = observe_lockfile(lab.control_lock, label="control")
    return Phase3LockfileCleanupReceipt(
        beast_object_type="dai_phase3_lockfile_cleanup_receipt",
        version=PHASE3_LOCKFILE_VERSION,
        run_id=lab.run_id,
        executed=False,
        refused_reason=reason,
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=stable_lockfile_world_state_digest(lab),
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        before_stale=before_stale,
        before_control=before_control,
        after_stale=before_stale,
        after_control=before_control,
        stale_lock_removed=False,
        unrelated_control_unchanged=True,
        stale_pid_was_dead=not before_stale.pid_alive,
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=("provider_call_boundary", "bounded_scope_refusal"),
        red_gates=("live_cleanup_execution",),
        observed_at=utc_now_iso(),
    )


def _stable_observation(observation: LockfileObservation) -> dict[str, Any]:
    return {
        "label": observation.label,
        "path": observation.path,
        "exists": observation.exists,
        "inode": observation.inode,
        "size_bytes": observation.size_bytes,
        "content_digest": observation.content_digest,
        "parsed_pid": observation.parsed_pid,
        "parsed_generation": observation.parsed_generation,
        "parsed_owner": observation.parsed_owner,
        "pid_alive": observation.pid_alive,
    }


def _write_lockfile(path: Path, *, pid: int, owner: str, generation: str) -> None:
    payload = {
        "schema": "dai.phase3.pidlock.v1",
        "pid": pid,
        "owner": owner,
        "generation": generation,
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _find_non_alive_pid() -> int:
    pid_max = 4_194_304
    try:
        pid_max = int(Path("/proc/sys/kernel/pid_max").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    candidate = max(2, min(pid_max, os.getpid() + 100_000))
    for pid in range(candidate, 1, -1):
        if not pid_alive(pid):
            return pid
    raise RuntimeError("could not find a non-live PID for disposable stale lockfile lab")


def _path_inside(root: Path, path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
    except ValueError:
        return False
    return True


def _dataclass_or_mapping_to_dict(value: Any) -> dict[str, Any]:
    return json.loads(canonical_json(value))
