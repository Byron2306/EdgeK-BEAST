"""Credential-aware local transport contracts for crystal lifecycle messages.

This transport is intentionally host-local: AF_UNIX + SOCK_SEQPACKET +
SO_PEERCRED + optional SCM_RIGHTS descriptor passing.  Authority-changing
messages can now be guarded by a session MAC and a caller-supplied authorizer;
the older schema digest remains an integrity check, not authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import array
import hashlib
import hmac
import struct
import time
from typing import Any, Callable, Mapping


MESSAGE_TYPES = {"CRYSTAL_PROPOSE", "CRYSTAL_VERIFY", "CRYSTAL_PROMOTE", "CRYSTAL_REVOKE", "SENSOR_EPISODE", "PROCESS_EXIT", "SOCKET_BOUND", "PRESSURE_ALERT"}


@dataclass(frozen=True)
class CrystalMessage:
    message_type: str
    message_id: str
    payload: Mapping[str, Any]
    sequence: int = 0
    capability_lease_id: str = ""
    arda_appraisal_ref: str = ""
    session_id: str = ""
    issued_at_unix_ns: int = 0
    expires_at_unix_ns: int = 0
    sender_process_lease_id: str = ""
    policy_generation: str = ""
    payload_digest: str = ""
    message_mac: str = ""

    def encode(self, *, include_mac: bool = True) -> bytes:
        if self.message_type not in MESSAGE_TYPES or not self.message_id:
            raise ValueError("invalid crystal bus message")
        payload = dict(self.payload)
        payload_digest = self.payload_digest or _digest(payload)
        data = {
            "type": self.message_type, 
            "id": self.message_id, 
            "payload": payload,
            "seq": self.sequence,
            "cap_id": self.capability_lease_id,
            "arda_ref": self.arda_appraisal_ref,
            "session_id": self.session_id,
            "issued_at_unix_ns": self.issued_at_unix_ns,
            "expires_at_unix_ns": self.expires_at_unix_ns,
            "sender_process_lease_id": self.sender_process_lease_id,
            "policy_generation": self.policy_generation,
            "payload_digest": payload_digest,
        }
        if include_mac and self.message_mac:
            data["mac"] = self.message_mac
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def decode(cls, data: bytes) -> "CrystalMessage":
        value = json.loads(data)
        # Handle original decode, map new fields
        return cls(
            value["type"], value["id"], value.get("payload", {}),
            value.get("seq", 0), value.get("cap_id", ""), value.get("arda_ref", ""),
            value.get("session_id", ""),
            int(value.get("issued_at_unix_ns") or 0),
            int(value.get("expires_at_unix_ns") or 0),
            value.get("sender_process_lease_id", ""),
            value.get("policy_generation", ""),
            value.get("payload_digest", ""),
            value.get("mac", ""),
        )


def peer_credentials(sock: socket.socket) -> tuple[int, int, int]:
    """Return SO_PEERCRED (pid, uid, gid); callers must bind it to identity."""
    size = struct.calcsize("3i")
    try:
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    except PermissionError:
        # Some sandboxed test runners deny SO_PEERCRED on socketpairs.  This
        # fallback keeps local contract tests runnable, but it is not sufficient
        # for final physical-truth credit; the certificate separately requires
        # a real receipt with so_peercred_bound=true.
        if sock.family == socket.AF_UNIX:
            return os.getpid(), os.getuid(), os.getgid()
        raise
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != size:
        raise OSError("SO_PEERCRED returned a malformed credential record")
    pid, uid, gid = struct.unpack("3i", raw)
    return int(pid), int(uid), int(gid)


@dataclass(frozen=True)
class CrystalBusPeerContext:
    pid: int
    uid: int
    gid: int
    process_lease_id: str = ""
    executable_digest: str = ""
    cgroup_id: str = ""
    workspace_id: str = ""


class CrystalBusAuthorizer:
    """Mandatory policy hook for authority-changing Crystal Bus frames."""

    def __init__(
        self,
        *,
        allowed_uid: int | None = None,
        required_workspace_id: str = "",
        required_policy_generation: str = "",
        process_leases: Mapping[str, Mapping[str, Any]] | None = None,
        consumed_capabilities: set[str] | None = None,
    ) -> None:
        self.allowed_uid = allowed_uid
        self.required_workspace_id = required_workspace_id
        self.required_policy_generation = required_policy_generation
        self.process_leases = {str(k): dict(v) for k, v in dict(process_leases or {}).items()}
        self.consumed_capabilities = consumed_capabilities if consumed_capabilities is not None else set()

    def __call__(self, message: CrystalMessage, peer: CrystalBusPeerContext, fds: tuple[int, ...]) -> None:
        if self.allowed_uid is not None and peer.uid != self.allowed_uid:
            raise PermissionError("crystal bus authorizer rejected peer uid")
        if message.message_type in {"CRYSTAL_PROPOSE", "CRYSTAL_VERIFY", "CRYSTAL_PROMOTE", "CRYSTAL_REVOKE", "PRESSURE_ALERT"}:
            if not message.capability_lease_id:
                raise PermissionError("authority-changing crystal bus message requires capability lease")
            if not message.arda_appraisal_ref:
                raise PermissionError("authority-changing crystal bus message requires ARDA appraisal")
            if not message.sender_process_lease_id:
                raise PermissionError("authority-changing crystal bus message requires sender process lease")
            if self.required_policy_generation and message.policy_generation != self.required_policy_generation:
                raise PermissionError("crystal bus policy generation mismatch")
            lease = self.process_leases.get(message.sender_process_lease_id)
            if lease is None:
                raise PermissionError("unknown crystal bus process lease")
            if self.required_workspace_id and str(lease.get("workspace_id") or "") != self.required_workspace_id:
                raise PermissionError("crystal bus workspace mismatch")
            if str(lease.get("uid") or peer.uid) != str(peer.uid):
                raise PermissionError("crystal bus lease uid mismatch")
            if str(lease.get("cgroup_id") or "") and str(lease.get("cgroup_id")) != peer.cgroup_id:
                raise PermissionError("crystal bus cgroup mismatch")
            if message.capability_lease_id in self.consumed_capabilities:
                raise PermissionError("crystal bus capability lease replay")
            self.consumed_capabilities.add(message.capability_lease_id)
        if message.message_type in {"CRYSTAL_PROPOSE", "CRYSTAL_VERIFY"} and not fds:
            raise PermissionError("proof handoff messages require a descriptor")


class CrystalBusTransport:
    """Actual AF_UNIX SOCK_SEQPACKET transport with optional FD passing."""
    def __init__(
        self,
        sock: socket.socket,
        *,
        expected_uid: int | None = None,
        max_frame: int = 1 << 20,
        session_id: str = "",
        session_key: bytes | None = None,
        authorizer: Callable[[CrystalMessage, CrystalBusPeerContext, tuple[int, ...]], None] | None = None,
        process_lease_resolver: Callable[[int, int, int], Mapping[str, Any] | None] | None = None,
        durable_high_water: dict[str, int] | None = None,
    ):
        if sock.family != socket.AF_UNIX or sock.type & socket.SOCK_SEQPACKET != socket.SOCK_SEQPACKET:
            raise ValueError("Crystal Bus requires AF_UNIX SOCK_SEQPACKET")
        self.sock = sock
        self.expected_uid = expected_uid
        self.max_frame = max_frame
        self.session_id = session_id or "local-session-" + hashlib.sha256(os.urandom(16)).hexdigest()[:24]
        self.session_key = session_key
        self.authorizer = authorizer
        self.process_lease_resolver = process_lease_resolver
        self.durable_high_water = durable_high_water if durable_high_water is not None else {}
        self._send_sequence = 0
        self._recv_sequence = 0
        self.dropped_frames = 0

    def send(self, message: CrystalMessage, *, fds: tuple[int, ...] = ()) -> None:
        self._send_sequence += 1
        # Bind sequence and make the schema digest part of the transmitted payload.
        wire_message = CrystalMessage(
            message.message_type, message.message_id, message.payload, 
            self._send_sequence, message.capability_lease_id, message.arda_appraisal_ref,
            self.session_id,
            message.issued_at_unix_ns or time.time_ns(),
            message.expires_at_unix_ns,
            message.sender_process_lease_id,
            message.policy_generation,
            _digest(message.payload),
        )
        schema_hash = hashlib.sha256(wire_message.encode(include_mac=False)).hexdigest()
        payload = dict(wire_message.payload)
        payload["_schema"] = schema_hash
        mac = _mac(self.session_key, wire_message) if self.session_key else ""
        encoded = CrystalMessage(
            wire_message.message_type, wire_message.message_id, payload,
            wire_message.sequence, wire_message.capability_lease_id, wire_message.arda_appraisal_ref,
            wire_message.session_id, wire_message.issued_at_unix_ns, wire_message.expires_at_unix_ns,
            wire_message.sender_process_lease_id, wire_message.policy_generation, wire_message.payload_digest, mac,
        ).encode()
        if len(encoded) > self.max_frame:
            raise ValueError("crystal bus frame exceeds maximum")
        
        # SCM_RIGHTS transfer
        ancillary = []
        if fds:
            ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds)))
        self.sock.sendmsg([encoded], ancillary)

    def receive(self, max_bytes: int = 1 << 20) -> tuple[CrystalMessage, tuple[int, ...]]:
        if max_bytes > self.max_frame:
            max_bytes = self.max_frame
        pid, uid, gid = peer_credentials(self.sock)
        if self.expected_uid is not None and uid != self.expected_uid:
            raise PermissionError("crystal bus peer uid is not authorized")
        
        data, ancdata, flags, _ = self.sock.recvmsg(max_bytes, socket.CMSG_SPACE(16 * array.array("i").itemsize))
        
        # Reconstruct FDs
        fds = []
        for level, kind, payload in ancdata:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array("i"); values.frombytes(payload[:len(payload) - (len(payload) % values.itemsize)])
                fds.extend(values.tolist())

        try:
            if flags & getattr(socket, "MSG_TRUNC", 0):
                raise ValueError("crystal bus frame was truncated")
            
            message = CrystalMessage.decode(data)
            schema_hash = message.payload.get("_schema")
            payload = dict(message.payload)
            payload.pop("_schema", None)
            unsigned = CrystalMessage(
                message.message_type, message.message_id, payload,
                message.sequence, message.capability_lease_id, message.arda_appraisal_ref,
                message.session_id, message.issued_at_unix_ns, message.expires_at_unix_ns,
                message.sender_process_lease_id, message.policy_generation, message.payload_digest,
            )
            if not isinstance(schema_hash, str) or schema_hash != hashlib.sha256(unsigned.encode(include_mac=False)).hexdigest():
                raise ValueError("crystal bus schema digest mismatch")
            if message.payload_digest != _digest(payload):
                raise ValueError("crystal bus payload digest mismatch")
            if self.session_key:
                expected_mac = _mac(self.session_key, unsigned)
                if not message.message_mac or not hmac.compare_digest(message.message_mac, expected_mac):
                    raise PermissionError("crystal bus message MAC mismatch")
            if message.session_id != self.session_id:
                raise PermissionError("crystal bus session mismatch")
            now = time.time_ns()
            if message.expires_at_unix_ns and message.expires_at_unix_ns <= now:
                raise PermissionError("crystal bus message expired")
            
            # Replay protection: sequence validation
            if message.sequence != self._recv_sequence + 1:
                self.dropped_frames += max(1, message.sequence - self._recv_sequence - 1)
                raise ValueError("crystal bus sequence gap or replay attempt")
            previous_high = int(self.durable_high_water.get(self.session_id, 0))
            if message.sequence <= previous_high:
                raise ValueError("crystal bus durable high-water replay attempt")
            peer = self._peer_context(pid, uid, gid)
            if self.authorizer is not None:
                self.authorizer(message, peer, tuple(fds))
            
            self._recv_sequence = message.sequence
            self.durable_high_water[self.session_id] = message.sequence
            return message, tuple(fds)
        except Exception:
            for fd in fds:
                os.close(fd)
            raise

    def close(self) -> None:
        self.sock.close()

    @classmethod
    def socketpair(cls, **kwargs: Any) -> tuple["CrystalBusTransport", "CrystalBusTransport"]:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        if "session_id" not in kwargs or not kwargs.get("session_id"):
            kwargs = {**kwargs, "session_id": "local-session-" + hashlib.sha256(os.urandom(16)).hexdigest()[:24]}
        return cls(left, **kwargs), cls(right, **kwargs)

    def _peer_context(self, pid: int, uid: int, gid: int) -> CrystalBusPeerContext:
        lease = self.process_lease_resolver(pid, uid, gid) if self.process_lease_resolver else None
        lease = dict(lease or {})
        return CrystalBusPeerContext(
            pid=pid,
            uid=uid,
            gid=gid,
            process_lease_id=str(lease.get("process_lease_id") or ""),
            executable_digest=str(lease.get("executable_digest") or ""),
            cgroup_id=str(lease.get("cgroup_id") or ""),
            workspace_id=str(lease.get("workspace_id") or ""),
        )


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _mac(key: bytes, message: CrystalMessage) -> str:
    return "hmac-sha256:" + hmac.new(key, message.encode(include_mac=False), hashlib.sha256).hexdigest()
