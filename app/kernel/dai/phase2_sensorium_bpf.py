"""Phase-2 Sensorium/BPF witness binding for the stale-listener proof.

The Phase-2 stale-listener lab starts real localhost child processes.  The
first proof slice observed those children from process-local socket probes.
This module strengthens the witness path by binding:

* exact child PID/port/cgroup snapshots from procfs;
* the source-bound C4-X BPF authority sidecar;
* optional exact Phase-2 kernel event digests when a live cgroup observer is
  mounted and supplies them.

It deliberately separates "BPF substrate authority is present" from "exact
Phase-2 kernel events were captured".  Absence of exact events lowers authority
instead of being laundered into a kernel-truth claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_bytes, sha256_digest
from app.kernel.dai.contracts import AuthorityScope
from app.kernel.dai.phase2_stale_listener import ListenerHandle, Phase2StaleListenerLab


PHASE2_SENSORIUM_BPF_VERSION = "2026-08-04.phase2.sensorium-bpf.v1"


@dataclass(frozen=True, slots=True)
class Phase2ProcessCgroupObservation:
    phase: str
    label: str
    pid: int
    port: int
    role: str
    process_alive: bool
    procfs_cgroup_present: bool
    cgroup_raw_digest: str
    cgroup_line_count: int
    cgroup_path_digest: str

    def __post_init__(self) -> None:
        if self.cgroup_raw_digest:
            require_digest(self.cgroup_raw_digest, field_name="cgroup_raw_digest")
        if self.cgroup_path_digest:
            require_digest(self.cgroup_path_digest, field_name="cgroup_path_digest")

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2SensoriumBpfWitnessReport:
    beast_object_type: str
    version: str
    report_id: str
    phase2_world_state_digest: str
    proposal_digest: str
    live_replacement_receipt_digest: str
    bpf_sidecar_digest: str
    bpf_receipt_digest: str
    bpf_receipt_recomputed: bool
    bpf_authority_bound: bool
    bpf_cgroup_bound: bool
    bpf_read_only: bool
    bpf_ring_loss_explicit: bool
    raw_packet_payload_retained: bool
    loaded_bpf_program_count: int
    process_cgroup_snapshots: tuple[Phase2ProcessCgroupObservation, ...]
    exact_kernel_event_digests: tuple[str, ...]
    exact_phase2_kernel_events_bound: bool
    provider_calls_used: int
    execution_authority_allowed: bool
    production_authority_allowed: bool
    authority_level: str
    red_gates: tuple[str, ...]
    maximum_authority: AuthorityScope = AuthorityScope.PHYSICAL_ATTESTATION_ONLY

    def __post_init__(self) -> None:
        for field_name in (
            "phase2_world_state_digest",
            "proposal_digest",
            "live_replacement_receipt_digest",
            "bpf_sidecar_digest",
            "bpf_receipt_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        for digest in self.exact_kernel_event_digests:
            require_digest(digest, field_name="exact_kernel_event_digests")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def process_cgroup_snapshot_digest(self) -> str:
        return sha256_digest(self.process_cgroup_snapshots)

    @property
    def passed(self) -> bool:
        return (
            self.bpf_authority_bound
            and self.bpf_receipt_recomputed
            and self.bpf_cgroup_bound
            and self.bpf_read_only
            and self.bpf_ring_loss_explicit
            and not self.raw_packet_payload_retained
            and self.loaded_bpf_program_count > 0
            and bool(self.process_cgroup_snapshots)
            and not self.execution_authority_allowed
            and not self.production_authority_allowed
            and self.provider_calls_used == 0
        )

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def capture_phase2_cgroup_snapshot(
    lab: Phase2StaleListenerLab,
    *,
    phase: str,
    proc_root: str | Path = "/proc",
) -> tuple[Phase2ProcessCgroupObservation, ...]:
    observations: list[Phase2ProcessCgroupObservation] = []
    for handle in (lab.stale, lab.control, lab.replacement):
        if handle is None:
            continue
        observations.append(_observe_handle_cgroup(handle, phase=phase, proc_root=Path(proc_root)))
    return tuple(observations)


def observe_phase2_pid_cgroup(
    *,
    phase: str,
    label: str,
    pid: int,
    port: int,
    role: str,
    proc_root: str | Path = "/proc",
) -> Phase2ProcessCgroupObservation:
    handle = ListenerHandle(
        label=label,
        role=role,
        pid=pid,
        port=port,
        process=_PidOnlyProcess(pid),
    )
    return _observe_handle_cgroup(handle, phase=phase, proc_root=Path(proc_root))


def build_phase2_sensorium_bpf_witness(
    *,
    phase2_world_state_digest: str,
    proposal_digest: str,
    live_replacement_receipt_digest: str,
    before_cgroups: Iterable[Phase2ProcessCgroupObservation],
    after_cgroups: Iterable[Phase2ProcessCgroupObservation],
    bpf_sidecar_path: str | Path,
    exact_kernel_events: Iterable[Mapping[str, Any]] = (),
    exact_kernel_event_expectations: Iterable[Mapping[str, Any]] = (),
) -> Phase2SensoriumBpfWitnessReport:
    require_digest(phase2_world_state_digest, field_name="phase2_world_state_digest")
    require_digest(proposal_digest, field_name="proposal_digest")
    require_digest(live_replacement_receipt_digest, field_name="live_replacement_receipt_digest")
    sidecar = Path(bpf_sidecar_path).expanduser().resolve()
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(sidecar_payload, Mapping):
        raise ValueError("BPF sidecar must be a JSON object")
    bpf_receipt = dict(sidecar_payload.get("bpf_receipt") or {})
    claimed_bpf_digest = str(bpf_receipt.get("receipt_digest") or "")
    receipt_without_digest = dict(bpf_receipt)
    receipt_without_digest.pop("receipt_digest", None)
    recomputed_bpf_digest = sha256_digest(receipt_without_digest) if receipt_without_digest else ""
    process_cgroups = tuple(before_cgroups) + tuple(after_cgroups)
    exact_events = tuple(dict(event) for event in exact_kernel_events)
    exact_expectations = tuple(dict(expectation) for expectation in exact_kernel_event_expectations)
    exact_event_digests = tuple(sorted(sha256_digest({"phase2_kernel_event": event}) for event in exact_events))
    bpf_receipt_recomputed = bool(claimed_bpf_digest and claimed_bpf_digest == recomputed_bpf_digest)
    bpf_authority_bound = bool(
        bpf_receipt.get("bpf_authority_present")
        and bpf_receipt.get("arda_bpf_authoritative")
        and bpf_receipt_recomputed
    )
    exact_bound = _exact_kernel_events_bind_expected_leases(exact_events, exact_expectations)
    gates = {
        "bpf_sidecar_present": sidecar.is_file(),
        "bpf_receipt_recomputed": bpf_receipt_recomputed,
        "bpf_authority_bound": bpf_authority_bound,
        "bpf_cgroup_bound": bool(bpf_receipt.get("cgroup_bound")),
        "bpf_read_only": bool(bpf_receipt.get("read_only_program")),
        "bpf_ring_loss_explicit": bool(bpf_receipt.get("ring_loss_explicit")),
        "raw_packet_payload_absent": bpf_receipt.get("raw_packet_payload_retained") is False,
        "loaded_bpf_programs_present": int(bpf_receipt.get("loaded_bpf_program_count") or 0) > 0,
        "process_cgroup_snapshots_present": bool(process_cgroups),
        "exact_phase2_kernel_events_bound": exact_bound,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    authority_level = "exact_phase2_cgroup_kernel_witness" if exact_bound else "bpf_substrate_plus_procfs_cgroup_witness"
    return Phase2SensoriumBpfWitnessReport(
        beast_object_type="dai_phase2_sensorium_bpf_witness_report",
        version=PHASE2_SENSORIUM_BPF_VERSION,
        report_id="sensorium:phase2:stale-listener-bpf-witness:v1",
        phase2_world_state_digest=phase2_world_state_digest,
        proposal_digest=proposal_digest,
        live_replacement_receipt_digest=live_replacement_receipt_digest,
        bpf_sidecar_digest=sha256_bytes(sidecar.read_bytes()),
        bpf_receipt_digest=claimed_bpf_digest,
        bpf_receipt_recomputed=bpf_receipt_recomputed,
        bpf_authority_bound=bpf_authority_bound,
        bpf_cgroup_bound=bool(bpf_receipt.get("cgroup_bound")),
        bpf_read_only=bool(bpf_receipt.get("read_only_program")),
        bpf_ring_loss_explicit=bool(bpf_receipt.get("ring_loss_explicit")),
        raw_packet_payload_retained=bool(bpf_receipt.get("raw_packet_payload_retained")),
        loaded_bpf_program_count=int(bpf_receipt.get("loaded_bpf_program_count") or 0),
        process_cgroup_snapshots=process_cgroups,
        exact_kernel_event_digests=exact_event_digests,
        exact_phase2_kernel_events_bound=exact_bound,
        provider_calls_used=0,
        execution_authority_allowed=False,
        production_authority_allowed=False,
        authority_level=authority_level,
        red_gates=red_gates,
    )


def sensorium_bpf_report_to_dict(report: Phase2SensoriumBpfWitnessReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["maximum_authority"] = report.maximum_authority.value
    payload["process_cgroup_snapshot_digest"] = report.process_cgroup_snapshot_digest
    payload["passed"] = report.passed
    payload["report_digest"] = report.report_digest
    return payload


def write_phase2_sensorium_bpf_report(path: str | Path, report: Phase2SensoriumBpfWitnessReport) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(sensorium_bpf_report_to_dict(report)) + "\n", encoding="utf-8")
    return target


def _exact_kernel_events_bind_expected_leases(
    events: tuple[Mapping[str, Any], ...],
    expectations: tuple[Mapping[str, Any], ...],
) -> bool:
    if not events or not expectations:
        return False
    matched_event_digests: set[str] = set()
    for expectation in expectations:
        matching = [
            event for event in events
            if _event_matches_expected_lease(event, expectation)
            and str(event.get("observation_digest") or "") not in matched_event_digests
        ]
        if len(matching) != 1:
            return False
        matched_event_digests.add(str(matching[0].get("observation_digest") or ""))
    return len(matched_event_digests) == len(expectations)


def _event_matches_expected_lease(event: Mapping[str, Any], expectation: Mapping[str, Any]) -> bool:
    if event.get("event_type") != "kernel.bpf.socket_bind":
        return False
    if int(event.get("pid") or 0) != int(expectation.get("pid") or expectation.get("tgid") or 0):
        return False
    if int(event.get("tgid") or 0) != int(expectation.get("tgid") or expectation.get("pid") or 0):
        return False
    for field_name in ("process_lease_id", "role", "cgroup_raw_digest"):
        if str(event.get(field_name) or "") != str(expectation.get(field_name) or ""):
            return False
    if int(event.get("start_time_ticks") or -1) != int(expectation.get("start_time_ticks") or -2):
        return False
    if str(event.get("observation_digest") or "").startswith("sha256:") is False:
        return False
    expected_port = int(expectation.get("requested_port") or 0)
    if int(event.get("normalized_port") or 0) != expected_port:
        return False
    expected_address = int(expectation.get("expected_address") or 16777343)
    if int(event.get("normalized_address") or 0) != expected_address:
        return False
    return True


def _observe_handle_cgroup(handle: ListenerHandle, *, phase: str, proc_root: Path) -> Phase2ProcessCgroupObservation:
    cgroup_path = proc_root / str(handle.pid) / "cgroup"
    raw = b""
    try:
        raw = cgroup_path.read_bytes()
    except OSError:
        raw = b""
    text = raw.decode("utf-8", errors="replace")
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    return Phase2ProcessCgroupObservation(
        phase=phase,
        label=handle.label,
        pid=handle.pid,
        port=handle.port,
        role=handle.role,
        process_alive=handle.process.poll() is None,
        procfs_cgroup_present=bool(raw),
        cgroup_raw_digest=sha256_bytes(raw) if raw else "",
        cgroup_line_count=len(lines),
        cgroup_path_digest=sha256_digest({"pid": handle.pid, "path": str(cgroup_path)}),
    )


class _PidOnlyProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        try:
            import os

            os.kill(self.pid, 0)
        except ProcessLookupError:
            return 1
        except PermissionError:
            return None
        return None
