#!/usr/bin/env python3
"""Run the Phase-2 stale-listener proof under the live X2 BPF ring observer.

This script must be launched by the user with sudo.  It does not install a
systemd service or keep privileged state running after the proof.  It:

1. starts stale/control listener children that wait before binding;
2. registers their PID-reuse-guarded leases for X2 correlation;
3. starts the X2 libbpf ring observer;
4. releases the children so socket bind events occur under observation;
5. performs the bounded stale-listener replacement with a gated replacement;
6. stops X2 and binds the correlated kernel events into the Phase-2 witness.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest
from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.phase2_acquisition import (
    phase2_acquisition_receipt,
    stale_listener_candidate_from_sophia_examples,
    write_phase2_acquisition_receipt,
)
from app.kernel.dai.phase2_commons_quorum import (
    bind_phase2_commons_quorum,
    load_ml_kem_receipt,
    write_phase2_commons_quorum_packet,
)
from app.kernel.dai.phase2_harmonic import score_stale_listener_harmonic_transfer, write_phase2_harmonic_report
from app.kernel.dai.phase2_sensorium_bpf import (
    build_phase2_sensorium_bpf_witness,
    observe_phase2_pid_cgroup,
    write_phase2_sensorium_bpf_report,
)
from app.kernel.dai.phase2_seraph import run_stale_listener_seraph_injections, write_phase2_seraph_report
from app.kernel.dai.phase2_stale_listener import (
    ListenerHandle,
    Phase2StaleListenerLab,
    acquire_phase2_world_lease,
    attempt_stale_world_replay,
    execute_phase2_stale_listener_replacement,
    write_phase2_receipt,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring"
DEFAULT_SOPHIA_EXAMPLES = ROOT / "fixtures/dai_phase2/stale_listener_acquisition_examples.json"
DEFAULT_ML_KEM = ROOT / "evidence/commons-ml-kem/physical-truth-commons-mlkem-live-container-helper-001.json"
DEFAULT_BPF_SIDECAR = ROOT / "evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json"
DEFAULT_X2_LOADER = ROOT / "bpf/build/libbeast_x2_loader.so"
DEFAULT_X2_OBJECT = ROOT / "bpf/build/beast_x1_observer.bpf.o"
REQUIRED_X2_LOADER_SYMBOLS = (
    "beast_x2_open",
    "beast_x2_poll",
    "beast_x2_loss",
    "beast_x2_close",
    "beast_x2_attachment_mask",
)
GATED_LISTENER_CODE = r"""
import json
import os
import socket
import sys

role = sys.argv[1]
port = int(sys.argv[2])
print(json.dumps({"state": "ready_before_bind", "pid": os.getpid(), "role": role}), flush=True)
sys.stdin.buffer.read(1)
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen(32)
print(json.dumps({"state": "bound", "pid": os.getpid(), "port": sock.getsockname()[1], "role": role}), flush=True)
while True:
    conn, _addr = sock.accept()
    with conn:
        conn.sendall((role + "\n").encode("utf-8"))
"""


@dataclass(slots=True)
class GatedListener:
    label: str
    role: str
    requested_port: int
    pid: int
    process: subprocess.Popen[str]

    def release(self, *, timeout_seconds: float = 5.0) -> ListenerHandle:
        if self.process.stdin is None:
            raise RuntimeError("gated listener stdin unavailable")
        self.process.stdin.write("x")
        self.process.stdin.flush()
        payload = _read_json_line(self.process, timeout_seconds=timeout_seconds)
        if payload.get("state") != "bound":
            raise RuntimeError(f"gated listener did not bind: {payload!r}")
        return ListenerHandle(
            label=self.label,
            role=self.role,
            pid=int(payload["pid"]),
            port=int(payload["port"]),
            process=self.process,
        )

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sophia-examples", type=Path, default=DEFAULT_SOPHIA_EXAMPLES)
    parser.add_argument("--ml-kem-receipt", type=Path, default=DEFAULT_ML_KEM)
    parser.add_argument("--bpf-sidecar", type=Path, default=DEFAULT_BPF_SIDECAR)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--run-id", default="dai-phase2-x2-exact-ring-local-001")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Run with sudo so X2 can attach BPF tracepoints: sudo .venv/bin/python scripts/run_dai_phase2_x2_exact_ring_buffer.py", file=sys.stderr)
        return 77
    try:
        summary = run(
            out=args.out,
            sophia_examples=args.sophia_examples,
            ml_kem_receipt_path=args.ml_kem_receipt,
            bpf_sidecar_path=args.bpf_sidecar,
            python=args.python,
            run_id=args.run_id,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("green") else 1
    finally:
        _restore_owner(args.out)


def run(
    *,
    out: Path,
    sophia_examples: Path,
    ml_kem_receipt_path: Path,
    bpf_sidecar_path: Path,
    python: str,
    run_id: str,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    _verify_x2_loader_abi(DEFAULT_X2_LOADER)
    x2_manifest = _write_phase2_bind_manifest(out / "x2_phase2_bind_attach_manifest.json")
    copied_examples = out / "phase2_sophia_stale_listener_examples.json"
    shutil.copy2(sophia_examples, copied_examples)
    sophia_receipt = ArtifactReceipt.from_file(
        copied_examples,
        organ=DAIOrgan.SOPHIA,
        artifact_schema="dai.phase2.sophia_stale_listener_examples.v1",
        summary={"phase": "DAI-Diode-Phase-2", "domain": "stale_listener_conflict", "x2_exact_ring": True},
    )
    candidate, acquisition_summary = stale_listener_candidate_from_sophia_examples(copied_examples, source_receipt=sophia_receipt)
    acquisition_payload = phase2_acquisition_receipt(candidate, acquisition_summary)
    write_phase2_acquisition_receipt(out / "phase2_sophia_acquisition_receipt.json", candidate, acquisition_summary)
    harmonic_report = score_stale_listener_harmonic_transfer(
        copied_examples,
        candidate_digest=candidate.candidate_digest,
        source_receipt_digest=sha256_digest(acquisition_payload),
        source_artifact_digest=sophia_receipt.artifact_digest,
    )
    write_phase2_harmonic_report(out / "phase2_harmonic_transfer_report.json", harmonic_report)
    seraph_report = run_stale_listener_seraph_injections(
        candidate_digest=candidate.candidate_digest,
        source_receipt_digest=sha256_digest(acquisition_payload),
    )
    write_phase2_seraph_report(str(out / "phase2_seraph_injection_report.json"), seraph_report)

    event_log = out / "x2_observations.jsonl"
    x2_receipt = out / "x2_runtime_receipt.json"
    x2_registry = out / "x2_process_leases.json"
    x2_audit = out / "x2_correlation_audit.jsonl"
    x2_stdout = out / "x2_observer.stdout.log"
    x2_stderr = out / "x2_observer.stderr.log"
    failure_diag = out / "x2_exact_ring_failure.json"
    failure_diag.unlink(missing_ok=True)
    observer: subprocess.Popen[str] | None = None
    gated: list[GatedListener] = []
    lab: Phase2StaleListenerLab | None = None
    registry_entries: list[dict[str, Any]] = []
    try:
        stale_gate = start_gated_listener("phase2-stale-service", label="stale", python=python)
        control_gate = start_gated_listener("phase2-unrelated-control", label="control", python=python)
        gated.extend([stale_gate, control_gate])
        registry_entries.append(_lease_entry(stale_gate, run_id=run_id))
        registry_entries.append(_lease_entry(control_gate, run_id=run_id))
        _write_registry(x2_registry, registry_entries)
        observer = _start_x2_observer(
            python=python,
            manifest=x2_manifest,
            event_log=event_log,
            registry=x2_registry,
            audit=x2_audit,
            receipt=x2_receipt,
            stdout_log=x2_stdout,
            stderr_log=x2_stderr,
        )
        time.sleep(1.0)
        _assert_observer_running(observer, stdout_log=x2_stdout, stderr_log=x2_stderr)
        stale = stale_gate.release()
        control = control_gate.release()
        _probe_listener(stale)
        _probe_listener(control)
        lab = Phase2StaleListenerLab(run_id=run_id, stale=stale, control=control)
        lease = acquire_phase2_world_lease(lab)
        before_cgroups = (
            observe_phase2_pid_cgroup(phase="before_replacement", label=stale.label, pid=stale.pid, port=stale.port, role=stale.role),
            observe_phase2_pid_cgroup(phase="before_replacement", label=control.label, pid=control.pid, port=control.port, role=control.role),
        )

        def replacement_starter(port: int) -> ListenerHandle:
            replacement_gate = start_gated_listener("phase2-replacement-service", label="replacement", port=port, python=python)
            gated.append(replacement_gate)
            registry_entries.append(_lease_entry(replacement_gate, run_id=run_id))
            _write_registry(x2_registry, registry_entries)
            time.sleep(0.2)
            replacement = replacement_gate.release()
            _probe_listener(replacement)
            return replacement

        replacement_receipt = execute_phase2_stale_listener_replacement(
            lab,
            lease,
            replacement_starter=replacement_starter,
        )
        time.sleep(1.0)
        after_cgroups = (
            observe_phase2_pid_cgroup(phase="after_replacement", label=lab.replacement.label, pid=lab.replacement.pid, port=lab.replacement.port, role=lab.replacement.role),
            observe_phase2_pid_cgroup(phase="after_replacement", label=control.label, pid=control.pid, port=control.port, role=control.role),
        )
        replay_receipt = attempt_stale_world_replay(lab, lease)
        proposal_digest = sha256_digest({
            "phase": "DAI-Diode-Phase-2-X2-exact-ring",
            "candidate_digest": candidate.candidate_digest,
            "harmonic_transfer_report_digest": harmonic_report.report_digest,
            "seraph_injection_report_digest": seraph_report.report_digest,
            "world_state_digest": replacement_receipt.world_state_digest,
            "capability_digest": replacement_receipt.capability_digest,
            "authority": "exact_x2_ring_buffer_witness_no_execution_authority",
        })
        commons_admission, quorum_decision, commons_report = bind_phase2_commons_quorum(
            ml_kem_receipt=load_ml_kem_receipt(ml_kem_receipt_path),
            phase2_world_state_digest=replacement_receipt.world_state_digest,
            proposal_digest=proposal_digest,
            evidence_digests={
                "sophia_acquisition": sha256_digest(acquisition_payload),
                "harmonic_transfer": harmonic_report.report_digest,
                "seraph_injections": seraph_report.report_digest,
                "live_replacement": replacement_receipt.receipt_digest,
                "stale_world_replay": replay_receipt.receipt_digest,
            },
        )
        _stop_observer(observer, stdout_log=x2_stdout, stderr_log=x2_stderr)
        observer = None
        exact_events = _load_correlated_x2_events(event_log, registry_entries)
        exact_event_payload = {
            "beast_object_type": "dai_phase2_x2_exact_kernel_events",
            "run_id": run_id,
            "event_log_digest": sha256_bytes(event_log.read_bytes()) if event_log.exists() else "",
            "x2_runtime_receipt_digest": sha256_bytes(x2_receipt.read_bytes()) if x2_receipt.exists() else "",
            "events": exact_events,
        }
        exact_event_payload["receipt_digest"] = sha256_digest(exact_event_payload)
        (out / "phase2_x2_exact_kernel_events.json").write_text(canonical_json(exact_event_payload) + "\n", encoding="utf-8")
        sensorium_bpf_report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement_receipt.world_state_digest,
            proposal_digest=proposal_digest,
            live_replacement_receipt_digest=replacement_receipt.receipt_digest,
            before_cgroups=before_cgroups,
            after_cgroups=after_cgroups,
            bpf_sidecar_path=bpf_sidecar_path,
            exact_kernel_events=exact_events,
            exact_kernel_event_expectations=registry_entries,
        )
        write_phase2_sensorium_bpf_report(out / "phase2_sensorium_bpf_exact_witness_report.json", sensorium_bpf_report)
        write_phase2_commons_quorum_packet(
            out / "phase2_commons_quorum_packet.json",
            admission=commons_admission,
            quorum=quorum_decision,
            report=commons_report,
        )
        write_phase2_receipt(out / "phase2_live_replacement_receipt.json", replacement_receipt)
        write_phase2_receipt(out / "phase2_stale_world_replay_receipt.json", replay_receipt)
        (out / "phase2_world_lease.json").write_text(canonical_json({"lease": lease, "lease_digest": lease.lease_digest}) + "\n", encoding="utf-8")
        bind_events = [event for event in exact_events if event.get("event_type") == "kernel.bpf.socket_bind"]
        summary = {
            "beast_object_type": "dai_phase2_x2_exact_ring_summary",
            "run_id": run_id,
            "green": bool(
                replacement_receipt.executed
                and replay_receipt.refused
                and commons_report.passed
                and sensorium_bpf_report.passed
                and sensorium_bpf_report.exact_phase2_kernel_events_bound
                and len(bind_events) >= 3
            ),
            "sensorium_exact_phase2_kernel_events_bound": sensorium_bpf_report.exact_phase2_kernel_events_bound,
            "sensorium_bpf_authority_level": sensorium_bpf_report.authority_level,
            "correlated_x2_event_count": len(exact_events),
            "correlated_socket_bind_event_count": len(bind_events),
            "proposal_digest": proposal_digest,
            "sensorium_bpf_exact_witness_report_digest": sensorium_bpf_report.report_digest,
            "x2_exact_kernel_events_receipt_digest": exact_event_payload["receipt_digest"],
            "provider_calls_used": 0,
            "production_authority_allowed": False,
        }
        summary["summary_digest"] = sha256_digest(summary)
        (out / "phase2_x2_exact_ring_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
        return summary
    finally:
        original_error = sys.exc_info()[1]
        stop_error = None
        if observer is not None:
            try:
                _stop_observer(observer, stdout_log=x2_stdout, stderr_log=x2_stderr)
            except Exception as exc:
                stop_error = exc
        if lab is not None:
            lab.cleanup()
        else:
            for item in gated:
                item.terminate()
        if original_error is not None or stop_error is not None:
            diagnostic = {
                "beast_object_type": "dai_phase2_x2_exact_ring_failure",
                "original_error": "" if original_error is None else f"{type(original_error).__name__}: {original_error}",
                "observer_stop_error": "" if stop_error is None else f"{type(stop_error).__name__}: {stop_error}",
                "x2_stdout_log": str(x2_stdout),
                "x2_stderr_log": str(x2_stderr),
                "x2_stdout_tail": _read_tail(x2_stdout),
                "x2_stderr_tail": _read_tail(x2_stderr),
                "event_log_exists": event_log.exists(),
                "x2_receipt_exists": x2_receipt.exists(),
                "x2_registry_exists": x2_registry.exists(),
            }
            diagnostic["diagnostic_digest"] = sha256_digest(diagnostic)
            failure_diag.write_text(canonical_json(diagnostic) + "\n", encoding="utf-8")
        if original_error is None and stop_error is not None:
            raise stop_error


def start_gated_listener(role: str, *, label: str, python: str, port: int = 0) -> GatedListener:
    process = subprocess.Popen(
        [python, "-u", "-c", GATED_LISTENER_CODE, role, str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    try:
        payload = _read_json_line(process, timeout_seconds=5)
        if payload.get("state") != "ready_before_bind":
            raise RuntimeError(f"gated listener did not become ready: {payload!r}")
        return GatedListener(label=label, role=role, requested_port=port, pid=int(payload["pid"]), process=process)
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        raise


def _read_json_line(process: subprocess.Popen[str], *, timeout_seconds: float) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("process stdout unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        events = selector.select(timeout_seconds)
        if not events:
            raise TimeoutError("process did not emit JSON line")
        line = process.stdout.readline()
    finally:
        selector.close()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"process exited before JSON line: {stderr}")
    return json.loads(line)


def _lease_entry(listener: GatedListener, *, run_id: str) -> dict[str, Any]:
    lease = LinuxProcessIdentityCollector().collect(listener.pid, owner_scope="dai_phase2_x2_exact_ring")
    raw = Path(f"/proc/{listener.pid}/cgroup").read_bytes()
    return {
        "tgid": listener.pid,
        "start_time_ticks": lease.start_time_ticks,
        "process_lease_id": lease.lease_id,
        "mission_id": run_id,
        "workspace_id": str(ROOT),
        "allow_prevalidated_exit_correlation": True,
        "exit_correlation_expires_at_epoch": time.time() + 120,
        "label": listener.label,
        "role": listener.role,
        "requested_port": listener.requested_port,
        "cgroup_raw_digest": sha256_bytes(raw),
    }


def _write_registry(path: Path, entries: list[dict[str, Any]]) -> None:
    payload = {
        "beast_object_type": "x2_observation_lease_registry",
        "version": "1.0",
        "authority": "observation_correlation_only",
        "leases": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".x2-process-leases.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _start_x2_observer(
    *,
    python: str,
    manifest: Path,
    event_log: Path,
    registry: Path,
    audit: Path,
    receipt: Path,
    stdout_log: Path,
    stderr_log: Path,
) -> subprocess.Popen[str]:
    _raise_memlock_limit()
    event_log.unlink(missing_ok=True)
    audit.unlink(missing_ok=True)
    receipt.unlink(missing_ok=True)
    stdout_log.unlink(missing_ok=True)
    stderr_log.unlink(missing_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PYTHONNOUSERSITE": "1",
        "BEAST_X2_EVENT_LOG": str(event_log),
        "BEAST_X2_LEASE_REGISTRY": str(registry),
        "BEAST_X2_CORRELATION_AUDIT": str(audit),
    }
    stdout_handle = stdout_log.open("w", encoding="utf-8")
    stderr_handle = stderr_log.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
        [
            python,
            "-s",
            "-m",
            "app.kernel.sensorium.bpf.x2_cli",
            "--manifest",
            str(manifest),
            "--loader",
            str(DEFAULT_X2_LOADER),
            "--sink",
            "app.kernel.sensorium.bpf.live_hooks:append_observation",
            "--lease-resolver",
            "app.kernel.sensorium.bpf.live_hooks:resolve_process_lease",
            "--receipt",
            str(receipt),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        close_fds=True,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return process


def _write_phase2_bind_manifest(path: Path) -> Path:
    attachment = _select_bind_attachment()
    payload = {
        "object_path": str(DEFAULT_X2_OBJECT),
        "ring_map": "events",
        "loss_map": "loss_counters",
        "poll_timeout_ms": 100,
        "health_interval_s": 5.0,
        "attachments": [attachment],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _select_bind_attachment() -> dict[str, Any]:
    if Path("/sys/fs/cgroup").exists():
        return {"program": "on_cgroup_bind4", "kind": "cgroup", "target": "/sys/fs/cgroup", "required": True}
    if _kernel_symbol_present("__x64_sys_bind"):
        return {"program": "on_bind_kprobe", "kind": "kprobe", "target": "__x64_sys_bind", "required": True}
    if _kernel_symbol_present("__sys_bind"):
        return {"program": "on_bind_kprobe", "kind": "kprobe", "target": "__sys_bind", "required": True}
    if _tracepoint_id_present("syscalls/sys_enter_bind"):
        return {"program": "on_bind", "kind": "tracepoint", "target": "syscalls/sys_enter_bind", "required": True}
    raise RuntimeError(
        "No bind-capable kernel witness hook found. Expected kprobe symbol __x64_sys_bind "
        "or tracepoint syscalls/sys_enter_bind."
    )


def _kernel_symbol_present(symbol: str) -> bool:
    kallsyms = Path("/proc/kallsyms")
    if not kallsyms.exists():
        return False
    needle = f" {symbol}\n"
    try:
        with kallsyms.open("r", encoding="utf-8", errors="replace") as handle:
            return any(line.endswith(needle) for line in handle)
    except OSError:
        return False


def _tracepoint_id_present(target: str) -> bool:
    category, name = target.split("/", 1)
    for root in (Path("/sys/kernel/tracing/events"), Path("/sys/kernel/debug/tracing/events")):
        if (root / category / name / "id").exists():
            return True
    return False


def _verify_x2_loader_abi(loader_path: Path) -> None:
    if not loader_path.exists():
        raise RuntimeError(f"X2 loader is missing: {loader_path}; rebuild with: make -C bpf build/libbeast_x2_loader.so")
    try:
        lib = ctypes.CDLL(str(loader_path))
    except OSError as exc:
        raise RuntimeError(f"X2 loader could not be opened: {loader_path}: {exc}") from exc
    missing = [symbol for symbol in REQUIRED_X2_LOADER_SYMBOLS if not hasattr(lib, symbol)]
    if missing:
        raise RuntimeError(
            "X2 loader ABI is stale or incomplete: "
            f"{loader_path} missing {', '.join(missing)}; rebuild with: make -C bpf build/libbeast_x2_loader.so"
        )


def _assert_observer_running(process: subprocess.Popen[str], *, stdout_log: Path, stderr_log: Path) -> None:
    if process.poll() is not None:
        raise RuntimeError(
            f"X2 observer exited during startup rc={process.returncode}\n"
            f"STDOUT:\n{_read_tail(stdout_log)}\nSTDERR:\n{_read_tail(stderr_log)}"
        )


def _stop_observer(process: subprocess.Popen[str], *, stdout_log: Path, stderr_log: Path) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if process.returncode not in (0, -15):
        raise RuntimeError(
            f"X2 observer failed rc={process.returncode}\n"
            f"STDOUT:\n{_read_tail(stdout_log)}\nSTDERR:\n{_read_tail(stderr_log)}"
        )


def _probe_listener(handle: ListenerHandle) -> str:
    with socket.create_connection(("127.0.0.1", handle.port), timeout=2) as conn:
        conn.settimeout(2)
        return conn.recv(4096).decode("utf-8", errors="replace").strip()


def _load_correlated_x2_events(event_log: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_lease = {entry["process_lease_id"]: entry for entry in entries}
    by_tgid = {int(entry["tgid"]): entry for entry in entries}
    events: list[dict[str, Any]] = []
    if not event_log.exists():
        return events
    for line in event_log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        body = item.get("body") if isinstance(item.get("body"), Mapping) else {}
        lease_id = str(item.get("process_lease_id") or "")
        entry = by_lease.get(lease_id) or by_tgid.get(int(body.get("tgid") or 0))
        if not entry:
            continue
        if not lease_id:
            lease_id = str(entry.get("process_lease_id") or "")
        attributes = body.get("attributes") if isinstance(body.get("attributes"), Mapping) else {}
        requested_port = int(entry.get("requested_port") or 0)
        events.append({
            "event_type": str(item.get("event_type") or ""),
            "observation_digest": str(item.get("observation_digest") or ""),
            "process_lease_id": lease_id,
            "pid": int(body.get("pid") or 0),
            "tgid": int(body.get("tgid") or 0),
            "start_time_ticks": int(entry.get("start_time_ticks") or 0),
            "kernel_cgroup_id": int(body.get("cgroup_id") or 0),
            "cgroup_raw_digest": entry["cgroup_raw_digest"],
            "label": entry["label"],
            "role": entry["role"],
            "requested_port": requested_port,
            "normalized_port": _normalize_u16(int(attributes.get("arg0") or 0), expected=requested_port),
            "normalized_address": int(attributes.get("arg1") or 0),
            "correlation_method": str(body.get("correlation_method") or ""),
            "x2_projection_digest": sha256_digest(item),
        })
    return events


def _normalize_u16(value: int, *, expected: int = 0) -> int:
    value &= 0xFFFF
    swapped = ((value & 0xFF) << 8) | (value >> 8)
    expected &= 0xFFFF
    if expected and expected in (value, swapped):
        return expected
    # cgroup/bind4 reports user_port in network order on this kernel. Dynamic
    # ephemeral binds report 0 and remain 0 under either representation.
    return swapped if value else 0


def _restore_owner(path: Path) -> None:
    uid = os.environ.get("SUDO_UID")
    gid = os.environ.get("SUDO_GID")
    if not uid or not gid:
        return
    try:
        for root, dirs, files in os.walk(path):
            for name in dirs + files:
                os.chown(os.path.join(root, name), int(uid), int(gid))
        os.chown(path, int(uid), int(gid))
    except OSError:
        return


def _raise_memlock_limit() -> None:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        target = max(soft, 64 * 1024 * 1024)
        if hard != resource.RLIM_INFINITY:
            target = min(target, hard)
        resource.setrlimit(resource.RLIMIT_MEMLOCK, (target, hard))
    except (OSError, ValueError):
        return


def _read_tail(path: Path, *, max_bytes: int = 8192) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-max_bytes:].decode("utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
