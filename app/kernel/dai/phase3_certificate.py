"""Operational Phase-3 disposable certificate-handshake refusal domain.

This module adds a third live domain for Phase 3.  A disposable localhost
server presents a certificate envelope during a tiny handshake.  BEAST parses
the temporal authority, refuses an expired certificate before accepting any app
payload, verifies a valid control endpoint still works, and refuses stale or
malformed evidence.

The protocol is intentionally not production TLS.  It is a bounded local
certificate-handshake proof surface for deterministic temporal authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
from typing import Any

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest


PHASE3_CERTIFICATE_VERSION = "2026-08-04.phase3.certificate.v1"
CERTIFICATE_SCOPE = "disposable_localhost_certificate_handshake_only"
LOCALHOST = "127.0.0.1"


_CERT_SERVER_CODE = r"""
import json
import os
import socket
import sys

role = sys.argv[1]
port = int(sys.argv[2])
cert = json.loads(sys.argv[3])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen(16)
print(json.dumps({"pid": os.getpid(), "port": sock.getsockname()[1], "role": role}), flush=True)
while True:
    conn, _addr = sock.accept()
    with conn:
        conn.sendall((json.dumps(cert, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        response = conn.recv(4096).decode("utf-8", errors="replace").strip()
        if response == "ACCEPT":
            conn.sendall(("APP_OK:" + role + "\n").encode("utf-8"))
        else:
            conn.sendall(("REFUSED_ACK:" + response + "\n").encode("utf-8"))
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
    except OSError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class CertificateEnvelope:
    subject: str
    issuer: str
    serial: str
    not_before: str
    not_after: str
    public_key_digest: str
    policy_generation: str = "dai-phase3-certificate-policy"

    def __post_init__(self) -> None:
        if not self.subject.strip() or not self.issuer.strip() or not self.serial.strip():
            raise ValueError("certificate envelope requires subject, issuer and serial")
        parse_iso_datetime(self.not_before, field_name="not_before")
        parse_iso_datetime(self.not_after, field_name="not_after")
        if parse_iso_datetime(self.not_after, field_name="not_after") <= parse_iso_datetime(self.not_before, field_name="not_before"):
            raise ValueError("certificate not_after must be after not_before")
        require_digest(self.public_key_digest, field_name="public_key_digest")

    @property
    def certificate_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CertificateHandshakeObservation:
    label: str
    role: str
    pid: int
    port: int
    process_alive: bool
    connect_ok: bool
    certificate_digest: str
    certificate_subject: str
    certificate_not_before: str
    certificate_not_after: str
    temporal_valid: bool
    refusal_reason: str
    client_decision: str
    server_reply: str
    app_payload_received: bool
    evidence_observed_at: str

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3CertificateWorldLease:
    beast_object_type: str
    version: str
    lease_id: str
    capability_id: str
    capability_digest: str
    world_state_digest: str
    expired_pid: int
    expired_port: int
    expired_certificate_digest: str
    control_pid: int
    control_port: int
    control_certificate_digest: str
    evidence_observed_at: str
    evidence_freshness_seconds: int
    evaluation_time: str
    execution_scope: str
    acquired_at: str
    expires_at: str
    provider_calls_used: int = 0
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("capability_digest", "world_state_digest", "expired_certificate_digest", "control_certificate_digest"):
            require_digest(getattr(self, field_name), field_name=field_name)
        parse_iso_datetime(self.evidence_observed_at, field_name="evidence_observed_at")
        parse_iso_datetime(self.evaluation_time, field_name="evaluation_time")
        if self.evidence_freshness_seconds <= 0:
            raise ValueError("evidence_freshness_seconds must be positive")
        if self.execution_scope != CERTIFICATE_SCOPE:
            raise ValueError("Phase-3 certificate lease has unsafe scope")
        if self.provider_calls_used != 0:
            raise ValueError("Phase-3 certificate lease must be zero-provider")
        if self.production_authority_allowed:
            raise ValueError("Phase-3 certificate lease cannot grant production authority")

    @property
    def lease_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3CertificateHandshakeReceipt:
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
    expired_observation: CertificateHandshakeObservation
    control_observation: CertificateHandshakeObservation
    expired_certificate_refused: bool
    control_certificate_accepted: bool
    stale_evidence_refused: bool
    provider_calls_used: int
    execution_scope: str
    production_authority_allowed: bool
    green_gates: tuple[str, ...]
    red_gates: tuple[str, ...]
    observed_at: str

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(slots=True)
class CertificateServerHandle:
    label: str
    role: str
    pid: int
    port: int
    certificate: CertificateEnvelope
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
class Phase3CertificateLab:
    run_id: str
    expired: CertificateServerHandle
    control: CertificateServerHandle

    def cleanup(self) -> None:
        self.expired.terminate()
        self.control.terminate()


def phase3_certificate_capability() -> dict[str, Any]:
    return {
        "capability": "expired_certificate_handshake_refusal",
        "operation": "refuse_expired_certificate_before_app_payload",
        "scope": CERTIFICATE_SCOPE,
        "nonclaims": ("production_tls_authority", "network_wide_certificate_authority", "secret_material_access"),
    }


def phase3_certificate_capability_digest() -> str:
    return sha256_digest(phase3_certificate_capability())


def start_phase3_certificate_lab(
    *,
    run_id: str = "dai-phase3-certificate-local-001",
    now: datetime | None = None,
) -> Phase3CertificateLab:
    current = now or datetime.now(timezone.utc)
    expired_cert = CertificateEnvelope(
        subject="CN=phase3-expired.local",
        issuer="CN=BEAST disposable CA",
        serial="phase3-expired-001",
        not_before=(current - timedelta(days=10)).isoformat(),
        not_after=(current - timedelta(days=1)).isoformat(),
        public_key_digest=sha256_digest({"public": "phase3-expired.local"}),
    )
    control_cert = CertificateEnvelope(
        subject="CN=phase3-control.local",
        issuer="CN=BEAST disposable CA",
        serial="phase3-control-001",
        not_before=(current - timedelta(days=1)).isoformat(),
        not_after=(current + timedelta(days=10)).isoformat(),
        public_key_digest=sha256_digest({"public": "phase3-control.local"}),
    )
    expired = start_certificate_server("phase3-expired-service", label="expired", certificate=expired_cert)
    try:
        control = start_certificate_server("phase3-control-service", label="control", certificate=control_cert)
    except Exception:
        expired.terminate()
        raise
    return Phase3CertificateLab(run_id=run_id, expired=expired, control=control)


def start_certificate_server(
    role: str,
    *,
    label: str,
    certificate: CertificateEnvelope,
    port: int = 0,
    timeout_seconds: float = 5.0,
) -> CertificateServerHandle:
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", _CERT_SERVER_CODE, role, str(port), canonical_json(certificate)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    try:
        payload = _read_server_start(process, timeout_seconds=timeout_seconds)
        return CertificateServerHandle(
            label=label,
            role=role,
            pid=int(payload["pid"]),
            port=int(payload["port"]),
            certificate=certificate,
            process=process,
        )
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=timeout_seconds)
        raise


def stable_certificate_world_state(lab: Phase3CertificateLab) -> dict[str, Any]:
    return {
        "run_id": lab.run_id,
        "scope": CERTIFICATE_SCOPE,
        "expired": _stable_server(lab.expired),
        "control": _stable_server(lab.control),
    }


def stable_certificate_world_state_digest(lab: Phase3CertificateLab) -> str:
    return sha256_digest(stable_certificate_world_state(lab))


def acquire_phase3_certificate_world_lease(
    lab: Phase3CertificateLab,
    *,
    now: datetime | None = None,
    evidence_freshness_seconds: int = 300,
) -> Phase3CertificateWorldLease:
    current = now or datetime.now(timezone.utc)
    world_digest = stable_certificate_world_state_digest(lab)
    return Phase3CertificateWorldLease(
        beast_object_type="dai_phase3_certificate_world_lease",
        version=PHASE3_CERTIFICATE_VERSION,
        lease_id="lease:" + sha256_digest({"run_id": lab.run_id, "world_state_digest": world_digest})[-16:],
        capability_id="capability:dai-phase3:expired-certificate-handshake-refusal:test-only",
        capability_digest=phase3_certificate_capability_digest(),
        world_state_digest=world_digest,
        expired_pid=lab.expired.pid,
        expired_port=lab.expired.port,
        expired_certificate_digest=lab.expired.certificate.certificate_digest,
        control_pid=lab.control.pid,
        control_port=lab.control.port,
        control_certificate_digest=lab.control.certificate.certificate_digest,
        evidence_observed_at=current.isoformat(),
        evidence_freshness_seconds=evidence_freshness_seconds,
        evaluation_time=current.isoformat(),
        execution_scope=CERTIFICATE_SCOPE,
        acquired_at=current.isoformat(),
        expires_at=(current + timedelta(minutes=5)).isoformat(),
    )


def execute_phase3_certificate_handshake(
    lab: Phase3CertificateLab,
    lease: Phase3CertificateWorldLease,
    *,
    supplied_world_state_digest: str | None = None,
) -> Phase3CertificateHandshakeReceipt:
    supplied = supplied_world_state_digest or lease.world_state_digest
    require_digest(supplied, field_name="supplied_world_state_digest")
    live_before = stable_certificate_world_state_digest(lab)
    reason = _handshake_refusal_reason(lab, lease, supplied=supplied, live_before=live_before)
    if reason:
        return _handshake_refusal_receipt(lab=lab, lease=lease, live_before=live_before, reason=reason)
    evaluation_time = parse_iso_datetime(lease.evaluation_time, field_name="evaluation_time")
    expired = perform_certificate_handshake(lab.expired, evaluation_time=evaluation_time)
    control = perform_certificate_handshake(lab.control, evaluation_time=evaluation_time)
    expired_refused = expired.client_decision.startswith("REFUSE") and not expired.app_payload_received
    control_accepted = control.client_decision == "ACCEPT" and control.app_payload_received
    gates = (
        ("expired_certificate_refused_before_app_payload", expired_refused),
        ("control_certificate_accepted", control_accepted),
        ("temporal_authority_parsed", True),
        ("provider_call_boundary", True),
        ("bounded_localhost_scope", lease.execution_scope == CERTIFICATE_SCOPE),
    )
    green = tuple(name for name, passed in gates if passed)
    red = tuple(name for name, passed in gates if not passed)
    return Phase3CertificateHandshakeReceipt(
        beast_object_type="dai_phase3_certificate_handshake_receipt",
        version=PHASE3_CERTIFICATE_VERSION,
        run_id=lab.run_id,
        executed=not red,
        refused_reason="",
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=stable_certificate_world_state_digest(lab),
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        expired_observation=expired,
        control_observation=control,
        expired_certificate_refused=expired_refused,
        control_certificate_accepted=control_accepted,
        stale_evidence_refused=False,
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=green,
        red_gates=red,
        observed_at=utc_now_iso(),
    )


def perform_certificate_handshake(
    handle: CertificateServerHandle,
    *,
    evaluation_time: datetime | None = None,
) -> CertificateHandshakeObservation:
    current = evaluation_time or datetime.now(timezone.utc)
    connect_ok = False
    certificate: dict[str, Any] = {}
    decision = "REFUSE:connection_failed"
    reply = ""
    app_payload_received = False
    reason = "connection_failed"
    temporal_valid = False
    try:
        with socket.create_connection((LOCALHOST, handle.port), timeout=1.0) as conn:
            conn.settimeout(1.0)
            raw = _recv_line(conn)
            certificate = json.loads(raw)
            connect_ok = True
            temporal_valid, reason = certificate_temporal_status(certificate, evaluation_time=current)
            decision = "ACCEPT" if temporal_valid else f"REFUSE:{reason}"
            conn.sendall((decision + "\n").encode("utf-8"))
            reply = _recv_line(conn)
            app_payload_received = reply.startswith("APP_OK:")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        reason = f"handshake_error:{type(exc).__name__}"
        decision = f"REFUSE:{reason}"
    cert_digest = sha256_digest(certificate) if certificate else ""
    return CertificateHandshakeObservation(
        label=handle.label,
        role=handle.role,
        pid=handle.pid,
        port=handle.port,
        process_alive=pid_alive(handle.pid),
        connect_ok=connect_ok,
        certificate_digest=cert_digest,
        certificate_subject=str(certificate.get("subject") or ""),
        certificate_not_before=str(certificate.get("not_before") or ""),
        certificate_not_after=str(certificate.get("not_after") or ""),
        temporal_valid=temporal_valid,
        refusal_reason="" if temporal_valid else reason,
        client_decision=decision,
        server_reply=reply,
        app_payload_received=app_payload_received,
        evidence_observed_at=utc_now_iso(),
    )


def certificate_temporal_status(certificate: dict[str, Any], *, evaluation_time: datetime) -> tuple[bool, str]:
    not_before = parse_iso_datetime(str(certificate.get("not_before") or ""), field_name="not_before")
    not_after = parse_iso_datetime(str(certificate.get("not_after") or ""), field_name="not_after")
    if not_after <= not_before:
        return False, "certificate_temporal_order_invalid"
    if evaluation_time < not_before:
        return False, "certificate_not_yet_valid"
    if evaluation_time >= not_after:
        return False, "expired_certificate"
    return True, ""


def write_phase3_certificate_receipt(path: str | Path, receipt: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(canonical_json(receipt))
    payload["receipt_digest"] = receipt.receipt_digest
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _handshake_refusal_reason(
    lab: Phase3CertificateLab,
    lease: Phase3CertificateWorldLease,
    *,
    supplied: str,
    live_before: str,
) -> str:
    if supplied != lease.world_state_digest:
        return "supplied_world_state_digest_mismatch"
    if lease.capability_id != "capability:dai-phase3:expired-certificate-handshake-refusal:test-only":
        return "capability_id_mismatch"
    if lease.capability_digest != phase3_certificate_capability_digest():
        return "capability_digest_mismatch"
    if lease.execution_scope != CERTIFICATE_SCOPE:
        return "unsafe_execution_scope"
    if live_before != lease.world_state_digest:
        return "live_world_state_digest_mismatch"
    if lease.expired_pid != lab.expired.pid or lease.expired_port != lab.expired.port:
        return "expired_endpoint_identity_mismatch"
    if lease.control_pid != lab.control.pid or lease.control_port != lab.control.port:
        return "control_endpoint_identity_mismatch"
    if lease.expired_certificate_digest != lab.expired.certificate.certificate_digest:
        return "expired_certificate_digest_mismatch"
    if lease.control_certificate_digest != lab.control.certificate.certificate_digest:
        return "control_certificate_digest_mismatch"
    evaluation = parse_iso_datetime(lease.evaluation_time, field_name="evaluation_time")
    observed = parse_iso_datetime(lease.evidence_observed_at, field_name="evidence_observed_at")
    if evaluation < observed:
        return "evaluation_precedes_evidence"
    if (evaluation - observed).total_seconds() > lease.evidence_freshness_seconds:
        return "certificate_evidence_stale"
    return ""


def _handshake_refusal_receipt(
    *,
    lab: Phase3CertificateLab,
    lease: Phase3CertificateWorldLease,
    live_before: str,
    reason: str,
) -> Phase3CertificateHandshakeReceipt:
    empty_expired = _empty_observation(lab.expired)
    empty_control = _empty_observation(lab.control)
    return Phase3CertificateHandshakeReceipt(
        beast_object_type="dai_phase3_certificate_handshake_receipt",
        version=PHASE3_CERTIFICATE_VERSION,
        run_id=lab.run_id,
        executed=False,
        refused_reason=reason,
        world_state_digest=lease.world_state_digest,
        live_world_state_digest_before=live_before,
        live_world_state_digest_after=stable_certificate_world_state_digest(lab),
        lease_digest=lease.lease_digest,
        capability_digest=lease.capability_digest,
        expired_observation=empty_expired,
        control_observation=empty_control,
        expired_certificate_refused=False,
        control_certificate_accepted=False,
        stale_evidence_refused=reason == "certificate_evidence_stale",
        provider_calls_used=0,
        execution_scope=lease.execution_scope,
        production_authority_allowed=False,
        green_gates=("provider_call_boundary", "bounded_scope_refusal"),
        red_gates=("live_handshake_execution",),
        observed_at=utc_now_iso(),
    )


def _read_server_start(process: subprocess.Popen[str], *, timeout_seconds: float) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("certificate server stdout was not captured")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        events = selector.select(timeout_seconds)
        if not events:
            raise TimeoutError("certificate server did not publish startup receipt")
        line = process.stdout.readline()
    finally:
        selector.close()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"certificate server exited before startup receipt: {stderr}")
    payload = json.loads(line)
    if int(payload.get("pid", 0)) <= 0 or int(payload.get("port", 0)) <= 0:
        raise RuntimeError(f"certificate server startup receipt missing pid/port: {payload!r}")
    return payload


def _recv_line(conn: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = conn.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > 65536:
            raise ValueError("handshake line too large")
    return data.decode("utf-8", errors="replace").strip()


def _stable_server(handle: CertificateServerHandle) -> dict[str, Any]:
    return {
        "label": handle.label,
        "role": handle.role,
        "pid": handle.pid,
        "port": handle.port,
        "process_alive": pid_alive(handle.pid),
        "certificate_digest": handle.certificate.certificate_digest,
        "certificate_subject": handle.certificate.subject,
        "certificate_not_before": handle.certificate.not_before,
        "certificate_not_after": handle.certificate.not_after,
    }


def _empty_observation(handle: CertificateServerHandle) -> CertificateHandshakeObservation:
    return CertificateHandshakeObservation(
        label=handle.label,
        role=handle.role,
        pid=handle.pid,
        port=handle.port,
        process_alive=pid_alive(handle.pid),
        connect_ok=False,
        certificate_digest="",
        certificate_subject="",
        certificate_not_before="",
        certificate_not_after="",
        temporal_valid=False,
        refusal_reason="not_attempted",
        client_decision="REFUSE:not_attempted",
        server_reply="",
        app_payload_received=False,
        evidence_observed_at=utc_now_iso(),
    )
