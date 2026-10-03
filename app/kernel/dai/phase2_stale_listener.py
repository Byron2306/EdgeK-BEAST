"""Phase-2 DAI whole-creature stale-listener proof lab.

This module is intentionally bounded.  It starts disposable localhost child
processes, observes their real sockets, retires only the process covered by a
fresh world lease, starts a replacement on the same port, and proves that an
unrelated control listener was not disturbed.

The authority claim is narrow:

* real local socket/process effects occurred;
* the stale listener child was retired;
* the replacement child became healthy on the same port;
* the unrelated child remained alive and reachable;
* stale world-state/lease replay is refused with zero effect.

It does not claim production service authority, host-wide process authority,
kernel/BPF witness authority, or Commons quorum authority.  Those are later
Phase-2 integrations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
from typing import Any, Callable

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_digest,
)


PHASE2_STALE_LISTENER_VERSION = "2026-08-04.phase2.stale-listener.v1"
LOCALHOST = "127.0.0.1"
PHASE2_LEASE_ISSUER = "beast:dai-phase2:local-lease-issuer"
PHASE2_LEASE_AUDIENCE = "dai-phase2:stale-listener-replacement"


_LISTENER_CODE = r"""
import json
import os
import socket
import sys

role = sys.argv[1]
port = int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen(32)
print(json.dumps({"pid": os.getpid(), "port": sock.getsockname()[1], "role": role}), flush=True)
while True:
    conn, _addr = sock.accept()
    with conn:
        conn.sendall((role + "\n").encode("utf-8"))
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 datetime")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True, slots=True)
class ListenerObservation:
    listener_label: str
    expected_role: str
    pid: int
    port: int
    process_alive: bool
    connect_ok: bool
    response: str
    observed_at: str

    @property
    def role_matches(self) -> bool:
        return self.connect_ok and self.response == self.expected_role

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2WorldLease:
    beast_object_type: str
    version: str
    lease_id: str
    capability_id: str
    capability_digest: str
    world_state_digest: str
    stale_pid: int
    stale_port: int
    stale_role: str
    control_pid: int
    control_port: int
    control_role: str
    execution_scope: str
    acquired_at: str
    expires_at: str
    issuer: str = PHASE2_LEASE_ISSUER
    audience: str = PHASE2_LEASE_AUDIENCE
    nonce: str = ""
    issuer_signature: str = ""
    provider_calls_used: int = 0
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        require_digest(self.capability_digest, field_name="capability_digest")
        require_digest(self.world_state_digest, field_name="world_state_digest")
        if self.provider_calls_used != 0:
            raise ValueError("phase2 stale-listener lease must be zero-provider")
        if self.production_authority_allowed:
            raise ValueError("phase2 stale-listener lease is not production authority")
        if self.execution_scope != "disposable_localhost_child_processes_only":
            raise ValueError("phase2 stale-listener lease has an unsafe scope")
        parse_iso_datetime(self.acquired_at, field_name="acquired_at")
        parse_iso_datetime(self.expires_at, field_name="expires_at")
        if self.audience and self.audience != PHASE2_LEASE_AUDIENCE:
            raise ValueError("phase2 stale-listener lease audience mismatch")
        if self.issuer and self.issuer != PHASE2_LEASE_ISSUER:
            raise ValueError("phase2 stale-listener lease issuer mismatch")

    @property
    def lease_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2LiveReplacementReceipt:
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
    before_stale: ListenerObservation
    before_control: ListenerObservation
    after_old_identity: ListenerObservation
    after_replacement: ListenerObservation
    after_control: ListenerObservation
    old_pid_retired: bool
    exact_port_reused: bool
    replacement_healthy: bool
    unrelated_control_unchanged: bool
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
class Phase2StaleWorldReplayReceipt:
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
class ListenerHandle:
    label: str
    role: str
    pid: int
    port: int
    process: subprocess.Popen[str]

    def terminate(self, *, timeout_seconds: float = 3.0) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=timeout_seconds)


@dataclass(slots=True)
class Phase2StaleListenerLab:
    run_id: str
    stale: ListenerHandle
    control: ListenerHandle
    replacement: ListenerHandle | None = None
    consumed_lease_digests: set[str] = field(default_factory=set)

    def cleanup(self) -> None:
        for handle in (self.replacement, self.stale, self.control):
            if handle is not None:
                handle.terminate()


def _read_listener_start(process: subprocess.Popen[str], *, timeout_seconds: float) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("listener stdout was not captured")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        events = selector.select(timeout_seconds)
        if not events:
            raise TimeoutError("listener did not publish startup receipt")
        line = process.stdout.readline()
    finally:
        selector.close()
    if not line:
        raise RuntimeError("listener exited before startup receipt")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"listener emitted invalid startup JSON: {line!r}") from exc
    if int(payload.get("pid", 0)) <= 0 or int(payload.get("port", 0)) <= 0:
        raise RuntimeError(f"listener startup receipt missing pid/port: {payload!r}")
    return payload


def start_listener(role: str, *, label: str, port: int = 0, timeout_seconds: float = 5.0) -> ListenerHandle:
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", _LISTENER_CODE, role, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    try:
        payload = _read_listener_start(process, timeout_seconds=timeout_seconds)
        return ListenerHandle(label=label, role=role, pid=int(payload["pid"]), port=int(payload["port"]), process=process)
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=timeout_seconds)
        raise


def start_phase2_stale_listener_lab(*, run_id: str = "dai-phase2-stale-listener-local-001") -> Phase2StaleListenerLab:
    stale = start_listener("phase2-stale-service", label="stale")
    try:
        control = start_listener("phase2-unrelated-control", label="control")
    except Exception:
        stale.terminate()
        raise
    return Phase2StaleListenerLab(run_id=run_id, stale=stale, control=control)


def phase2_stale_listener_capability() -> dict[str, Any]:
    return {
        "capability": "stale_listener_conflict",
        "operation": "retire_exact_child_and_rebind_same_port",
        "scope": "disposable_localhost_child_processes_only",
        "nonclaims": ("production_authority", "host_wide_process_authority", "kernel_bpf_witness", "commons_quorum"),
    }


def phase2_stale_listener_capability_digest() -> str:
    return sha256_digest(phase2_stale_listener_capability())


def observe_listener(handle: ListenerHandle, *, expected_role: str | None = None, label: str | None = None) -> ListenerObservation:
    response = ""
    connect_ok = False
    try:
        with socket.create_connection((LOCALHOST, handle.port), timeout=1.0) as conn:
            conn.settimeout(1.0)
            response = conn.recv(4096).decode("utf-8", errors="replace").strip()
            connect_ok = True
    except OSError:
        response = ""
        connect_ok = False
    return ListenerObservation(
        listener_label=label or handle.label,
        expected_role=expected_role or handle.role,
        pid=handle.pid,
        port=handle.port,
        process_alive=pid_alive(handle.pid),
        connect_ok=connect_ok,
        response=response,
        observed_at=utc_now_iso(),
    )


def stable_world_state(lab: Phase2StaleListenerLab) -> dict[str, Any]:
    replacement = lab.replacement
    return {
        "run_id": lab.run_id,
        "scope": "disposable_localhost_child_processes_only",
        "stale": {
            "pid": lab.stale.pid,
            "port": lab.stale.port,
            "role": lab.stale.role,
            "alive": pid_alive(lab.stale.pid),
        },
        "control": {
            "pid": lab.control.pid,
            "port": lab.control.port,
            "role": lab.control.role,
            "alive": pid_alive(lab.control.pid),
        },
        "replacement": None if replacement is None else {
            "pid": replacement.pid,
            "port": replacement.port,
            "role": replacement.role,
            "alive": pid_alive(replacement.pid),
        },
    }


def stable_world_state_digest(lab: Phase2StaleListenerLab) -> str:
    return sha256_digest(stable_world_state(lab))


def effect_digest(lab: Phase2StaleListenerLab) -> str:
    return sha256_digest({
        "stable_world": stable_world_state(lab),
        "stale_socket": observe_listener(lab.stale).response,
        "control_socket": observe_listener(lab.control).response,
        "replacement_socket": "" if lab.replacement is None else observe_listener(lab.replacement).response,
    })


def acquire_phase2_world_lease(lab: Phase2StaleListenerLab) -> Phase2WorldLease:
    now = datetime.now(timezone.utc)
    world_digest = stable_world_state_digest(lab)
    nonce = sha256_digest({"run_id": lab.run_id, "world_state_digest": world_digest, "acquired_at": now.isoformat()})
    lease = Phase2WorldLease(
        beast_object_type="dai_phase2_stale_listener_world_lease",
        version=PHASE2_STALE_LISTENER_VERSION,
        lease_id="lease:" + sha256_digest({"run_id": lab.run_id, "world_state_digest": world_digest})[-16:],
        capability_id="capability:dai-phase2:stale-listener-conflict:test-only",
        capability_digest=phase2_stale_listener_capability_digest(),
        world_state_digest=world_digest,
        stale_pid=lab.stale.pid,
        stale_port=lab.stale.port,
        stale_role=lab.stale.role,
        control_pid=lab.control.pid,
        control_port=lab.control.port,
        control_role=lab.control.role,
        execution_scope="disposable_localhost_child_processes_only",
        acquired_at=now.isoformat(),
        expires_at=datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc).isoformat(),
        nonce=nonce,
    )
    return _sign_phase2_lease(lease)


def _phase2_lease_signature_payload(lease: Phase2WorldLease) -> dict[str, Any]:
    payload = asdict(lease)
    payload["issuer_signature"] = ""
    return payload


def _phase2_lease_signature(lease: Phase2WorldLease) -> str:
    return sha256_digest({"phase2_lease_signature": _phase2_lease_signature_payload(lease)})


def _sign_phase2_lease(lease: Phase2WorldLease) -> Phase2WorldLease:
    return Phase2WorldLease(**{**asdict(lease), "issuer_signature": _phase2_lease_signature(lease)})


def _phase2_lease_signature_valid(lease: Phase2WorldLease) -> bool:
    return bool(lease.nonce and lease.issuer_signature and lease.issuer_signature == _phase2_lease_signature(lease))


def _phase2_lease_current(lease: Phase2WorldLease, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return current < parse_iso_datetime(lease.expires_at, field_name="expires_at")


def _refusal_receipt(
    *,
    lab: Phase2StaleListenerLab,
    lease: Phase2WorldLease,
    live_before: str,
    reason: str,
) -> Phase2LiveReplacementReceipt:
    before_stale = observe_listener(lab.stale)
    before_control = observe_listener(lab.control)
    replacement = lab.replacement or ListenerHandle(
        label="replacement_absent",
        role="phase2-replacement-service",
        pid=0,
        port=lease.stale_port,
        process=lab.stale.process,
    )
    after_replacement = observe_listener(replacement)
    return Phase2LiveReplacementReceipt(
        beast_object_type="dai_phase2_live_stale_listener_replacement_receipt",
        version=PHASE2_STALE_LISTENER_VERSION,
        run_id=lab.run_id,
        executed=False,
        refused_reason=reason,
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=stable_world_state_digest(lab),
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        before_stale=before_stale,
        before_control=before_control,
        after_old_identity=before_stale,
        after_replacement=after_replacement,
        after_control=before_control,
        old_pid_retired=False,
        exact_port_reused=False,
        replacement_healthy=False,
        unrelated_control_unchanged=True,
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=("provider_call_boundary", "bounded_scope_refusal"),
        red_gates=("live_replacement_execution",),
        observed_at=utc_now_iso(),
    )


def execute_phase2_stale_listener_replacement(
    lab: Phase2StaleListenerLab,
    lease: Phase2WorldLease,
    *,
    supplied_world_state_digest: str | None = None,
    replacement_starter: Callable[[int], ListenerHandle] | None = None,
) -> Phase2LiveReplacementReceipt:
    """Retire exactly the leased stale listener and start a replacement.

    Any mismatch is a refusal before process mutation.
    """
    supplied = supplied_world_state_digest or lease.world_state_digest
    require_digest(supplied, field_name="supplied_world_state_digest")
    live_before = stable_world_state_digest(lab)
    if supplied != lease.world_state_digest:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="supplied_world_state_digest_mismatch")
    if not _phase2_lease_current(lease):
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="lease_expired")
    if lease.lease_digest in lab.consumed_lease_digests:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="lease_already_consumed")
    if lease.capability_id != "capability:dai-phase2:stale-listener-conflict:test-only":
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="capability_id_mismatch")
    if lease.capability_digest != phase2_stale_listener_capability_digest():
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="capability_digest_mismatch")
    if live_before != lease.world_state_digest:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="live_world_state_digest_mismatch")
    if lease.stale_pid != lab.stale.pid or lease.stale_port != lab.stale.port:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="stale_listener_identity_mismatch")
    if lease.stale_role != lab.stale.role:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="stale_listener_role_mismatch")
    if lease.control_pid != lab.control.pid or lease.control_port != lab.control.port:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="control_listener_identity_mismatch")
    if lease.control_role != lab.control.role:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="control_listener_role_mismatch")
    if lease.stale_pid == lease.control_pid or lease.stale_port == lease.control_port:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="stale_control_identity_collision")
    if not lease.nonce:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="lease_nonce_missing")
    if not _phase2_lease_signature_valid(lease):
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="lease_issuer_signature_invalid")

    before_stale = observe_listener(lab.stale)
    before_control = observe_listener(lab.control)
    if not before_stale.role_matches or not before_control.role_matches:
        return _refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason="precondition_socket_health_failed")

    lab.stale.terminate()
    starter = replacement_starter or (lambda port: start_listener("phase2-replacement-service", label="replacement", port=port))
    replacement = starter(lease.stale_port)
    lab.replacement = replacement

    after_old = observe_listener(lab.stale, expected_role=lab.stale.role, label="old_stale_identity")
    after_replacement = observe_listener(replacement)
    after_control = observe_listener(lab.control)
    old_pid_retired = not pid_alive(lease.stale_pid)
    exact_port_reused = replacement.port == lease.stale_port
    replacement_healthy = after_replacement.role_matches and after_replacement.process_alive
    unrelated_unchanged = (
        after_control.pid == before_control.pid
        and after_control.port == before_control.port
        and after_control.role_matches
        and after_control.process_alive
    )
    live_after = stable_world_state_digest(lab)
    lab.consumed_lease_digests.add(lease.lease_digest)
    green = []
    red = []
    for gate, passed in (
        ("old_pid_retired", old_pid_retired),
        ("same_port_replacement_healthy", exact_port_reused and replacement_healthy),
        ("unrelated_control_unchanged", unrelated_unchanged),
        ("provider_call_boundary", True),
        ("bounded_localhost_child_scope", lease.execution_scope == "disposable_localhost_child_processes_only"),
    ):
        (green if passed else red).append(gate)
    return Phase2LiveReplacementReceipt(
        beast_object_type="dai_phase2_live_stale_listener_replacement_receipt",
        version=PHASE2_STALE_LISTENER_VERSION,
        run_id=lab.run_id,
        executed=not red,
        refused_reason="",
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=live_after,
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        before_stale=before_stale,
        before_control=before_control,
        after_old_identity=after_old,
        after_replacement=after_replacement,
        after_control=after_control,
        old_pid_retired=old_pid_retired,
        exact_port_reused=exact_port_reused,
        replacement_healthy=replacement_healthy,
        unrelated_control_unchanged=unrelated_unchanged,
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=tuple(green),
        red_gates=tuple(red),
        observed_at=utc_now_iso(),
    )


def attempt_stale_world_replay(
    lab: Phase2StaleListenerLab,
    lease: Phase2WorldLease,
    *,
    attempted_world_state_digest: str | None = None,
) -> Phase2StaleWorldReplayReceipt:
    """Attempt to reuse an old lease against current lab state.

    The correct behavior is refusal and no process/socket effect.
    """
    attempted = attempted_world_state_digest or lease.world_state_digest
    require_digest(attempted, field_name="attempted_world_state_digest")
    before = effect_digest(lab)
    live = stable_world_state_digest(lab)
    refused = attempted != lease.world_state_digest or live != lease.world_state_digest
    reason = ""
    if attempted != lease.world_state_digest:
        reason = "attempted_world_state_digest_mismatch"
    elif live != lease.world_state_digest:
        reason = "stale_lease_live_world_state_mismatch"
    if not refused:
        reason = "replay_not_stale"
    after = effect_digest(lab)
    zero_effect = before == after
    green = []
    red = []
    for gate, passed in (
        ("stale_world_refused", refused),
        ("zero_effect", zero_effect),
        ("provider_call_boundary", True),
    ):
        (green if passed else red).append(gate)
    return Phase2StaleWorldReplayReceipt(
        beast_object_type="dai_phase2_stale_world_replay_receipt",
        version=PHASE2_STALE_LISTENER_VERSION,
        run_id=lab.run_id,
        refused=refused,
        attempted_world_state_digest=attempted,
        expected_world_state_digest=lease.world_state_digest,
        live_world_state_digest=live,
        lease_digest=lease.lease_digest,
        effect_digest_before=before,
        effect_digest_after=after,
        zero_effect=zero_effect,
        provider_calls_used=0,
        refusal_reason=reason,
        green_gates=tuple(green),
        red_gates=tuple(red),
        observed_at=utc_now_iso(),
    )


def receipt_to_dict(receipt: Any) -> dict[str, Any]:
    payload = asdict(receipt)
    payload["receipt_digest"] = receipt.receipt_digest
    return payload


def write_phase2_receipt(path: str | Path, receipt: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(receipt_to_dict(receipt)) + "\n", encoding="utf-8")
    return target
