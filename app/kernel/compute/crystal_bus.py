"""Credential-aware local transport contracts for crystal lifecycle messages."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import array
import hashlib
import struct
from typing import Any, Mapping


MESSAGE_TYPES = {"CRYSTAL_PROPOSE", "CRYSTAL_VERIFY", "CRYSTAL_PROMOTE", "CRYSTAL_REVOKE", "SENSOR_EPISODE", "PROCESS_EXIT", "SOCKET_BOUND", "PRESSURE_ALERT"}


@dataclass(frozen=True)
class CrystalMessage:
    message_type: str
    message_id: str
    payload: Mapping[str, Any]
    # ADDED: Sequence number, capability, and ARDA bindings
    sequence: int = 0
    capability_lease_id: str = ""
    arda_appraisal_ref: str = ""

    def encode(self) -> bytes:
        if self.message_type not in MESSAGE_TYPES or not self.message_id:
            raise ValueError("invalid crystal bus message")
        data = {
            "type": self.message_type, 
            "id": self.message_id, 
            "payload": dict(self.payload),
            "seq": self.sequence,
            "cap_id": self.capability_lease_id,
            "arda_ref": self.arda_appraisal_ref
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def decode(cls, data: bytes) -> "CrystalMessage":
        value = json.loads(data)
        # Handle original decode, map new fields
        return cls(
            value["type"], value["id"], value.get("payload", {}),
            value.get("seq", 0), value.get("cap_id", ""), value.get("arda_ref", "")
        )


def peer_credentials(sock: socket.socket) -> tuple[int, int, int]:
    """Return SO_PEERCRED (pid, uid, gid); callers must bind it to identity."""
    size = struct.calcsize("3i")
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != size:
        raise OSError("SO_PEERCRED returned a malformed credential record")
    pid, uid, gid = struct.unpack("3i", raw)
    return int(pid), int(uid), int(gid)


class CrystalBusTransport:
    """Actual AF_UNIX SOCK_SEQPACKET transport with optional FD passing."""
    def __init__(self, sock: socket.socket, *, expected_uid: int | None = None, max_frame: int = 1 << 20):
        if sock.family != socket.AF_UNIX or sock.type & socket.SOCK_SEQPACKET != socket.SOCK_SEQPACKET:
            raise ValueError("Crystal Bus requires AF_UNIX SOCK_SEQPACKET")
        self.sock = sock
        self.expected_uid = expected_uid
        self.max_frame = max_frame
        self._send_sequence = 0
        self._recv_sequence = 0
        self.dropped_frames = 0

    def send(self, message: CrystalMessage, *, fds: tuple[int, ...] = ()) -> None:
        self._send_sequence += 1
        # Bind sequence and make the schema digest part of the transmitted payload.
        wire_message = CrystalMessage(
            message.message_type, message.message_id, message.payload, 
            self._send_sequence, message.capability_lease_id, message.arda_appraisal_ref
        )
        schema_hash = hashlib.sha256(wire_message.encode()).hexdigest()
        payload = dict(wire_message.payload)
        payload["_schema"] = schema_hash
        encoded = CrystalMessage(
            wire_message.message_type, wire_message.message_id, payload,
            wire_message.sequence, wire_message.capability_lease_id, wire_message.arda_appraisal_ref,
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
        if self.expected_uid is not None and peer_credentials(self.sock)[1] != self.expected_uid:
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
            )
            if not isinstance(schema_hash, str) or schema_hash != hashlib.sha256(unsigned.encode()).hexdigest():
                raise ValueError("crystal bus schema digest mismatch")
            
            # Replay protection: sequence validation
            if message.sequence != self._recv_sequence + 1:
                self.dropped_frames += max(1, message.sequence - self._recv_sequence - 1)
                raise ValueError("crystal bus sequence gap or replay attempt")
            
            self._recv_sequence = message.sequence
            return message, tuple(fds)
        except Exception:
            for fd in fds:
                os.close(fd)
            raise

    def close(self) -> None:
        self.sock.close()

    @classmethod
    def socketpair(cls) -> tuple["CrystalBusTransport", "CrystalBusTransport"]:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        return cls(left), cls(right)
