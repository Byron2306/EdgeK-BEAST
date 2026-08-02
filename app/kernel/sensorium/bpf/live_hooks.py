"""Minimal custody hooks for the explicitly approved X2 observation service."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Mapping


def _start_time_ticks(pid: int) -> int | None:
    """Read the PID-reuse guard from procfs without importing the full runtime."""
    try:
        text = Path("/proc") / str(pid) / "stat"
        fields = text.read_text(encoding="utf-8", errors="strict")
        closing = fields.rfind(")")
        if closing < 0:
            return None
        # Field 22 (starttime) is index 19 after the parenthesized comm field.
        return int(fields[closing + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _approved_leases() -> Mapping[str, Any]:
    """Load an operator-prepared, PID-reuse-safe correlation registry.

    The registry grants no execution authority.  It only permits the observer
    to label events from a process lease that was acquired before attachment.
    A missing or malformed registry fails closed to no correlation.
    """
    location = Path(os.environ.get(
        "BEAST_X2_LEASE_REGISTRY", "/etc/edgek-beast/x2-process-leases.json"
    ))
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
        entries = raw.get("leases", [])
        return {str(item["tgid"]): item for item in entries if isinstance(item, dict)}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def _audit_correlation(tgid: int, status: str, *, observed_start_time_ticks: int | None = None) -> None:
    """Record only a lease-resolution decision for an explicitly registered PID."""
    destination = Path(os.environ.get(
        "BEAST_X2_CORRELATION_AUDIT", "/var/lib/beast-x2/correlation-audit.jsonl"
    ))
    entry: dict[str, Any] = {"tgid": tgid, "status": status}
    if observed_start_time_ticks is not None:
        entry["observed_start_time_ticks"] = observed_start_time_ticks
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        # The observation path must not fail merely because optional diagnostics
        # cannot be persisted under a hardened service policy.
        return


def append_observation(event: Mapping[str, Any]) -> None:
    """Append an already-redacted Sensorium projection to the configured JSONL sink."""
    destination = Path(os.environ.get("BEAST_X2_EVENT_LOG", "/run/beast-x2/observations.jsonl"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(event), sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(destination, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, encoded.encode("utf-8"))
    finally:
        os.close(fd)


def resolve_process_lease(*, pid: int, tgid: int, cgroup_id: int) -> Mapping[str, Any] | None:
    """Correlate only a pre-approved lease, guarded against PID reuse.

    ``cgroup_id`` is intentionally not translated from its kernel numeric form
    here.  The registered lease has already captured the human-readable
    procfs cgroup path; the start-time comparison is the authoritative reuse
    guard at this event boundary.
    """
    del pid, cgroup_id
    entry = _approved_leases().get(str(tgid))
    if not entry:
        return None
    try:
        observed_start = _start_time_ticks(tgid)
        if observed_start != int(entry["start_time_ticks"]):
            # A controlled X2 lab may receive an exit record after procfs has
            # removed the task.  The process was identity-checked immediately
            # before attachment; permit this narrow, expiring exit correlation
            # only for the dedicated one-process registry entry.  Normal and
            # production registries never set this flag.
            if (observed_start is None
                    and entry.get("allow_prevalidated_exit_correlation") is True
                    and time.time() <= float(entry.get("exit_correlation_expires_at_epoch", 0))
                    and str(entry.get("process_lease_id", "")).startswith("process:sha256:")):
                _audit_correlation(tgid, "prevalidated_exit_correlated")
                return {
                    "process_lease_id": str(entry["process_lease_id"]),
                    "mission_id": str(entry["mission_id"]),
                    "workspace_id": str(entry["workspace_id"]),
                    "correlation_method": "prevalidated_exit",
                }
            _audit_correlation(tgid, "start_time_mismatch_or_process_gone", observed_start_time_ticks=observed_start)
            return None
        process_lease_id = str(entry["process_lease_id"])
        if not process_lease_id.startswith("process:sha256:"):
            _audit_correlation(tgid, "invalid_lease_identifier", observed_start_time_ticks=observed_start)
            return None
        _audit_correlation(tgid, "correlated", observed_start_time_ticks=observed_start)
        return {
            "process_lease_id": process_lease_id,
            "mission_id": str(entry["mission_id"]),
            "workspace_id": str(entry["workspace_id"]),
            "correlation_method": "live_procfs_start_time",
        }
    except (KeyError, TypeError, ValueError):
        _audit_correlation(tgid, "malformed_registry_entry")
        return None
