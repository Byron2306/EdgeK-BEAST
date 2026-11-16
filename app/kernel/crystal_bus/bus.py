"""Delivery 4: consolidated Crystal Bus (default-off).

One API over AF_UNIX/SOCK_SEQPACKET + SCM_RIGHTS that unifies the compute-bus
message transport and the capsule-offer endpoint behind four checks — strict
peer credentials, sequence ledger, capsule verification, one-use capability
authority — and emits a signed, hash-chained custody receipt on every
descriptor transfer. Enabled only by ``BEAST_CONSOLIDATED_CRYSTAL_BUS=1``;
existing callers of either legacy API are unchanged.
"""
from __future__ import annotations

import array
import fcntl
import hashlib
import json
import os
import socket
import stat
import struct
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .capsule_messages import CapsuleOffer
from .peer_verification import PeerAdmissionPolicy
from .sequence_ledger import SequenceLedger

ENV_FLAG = "BEAST_CONSOLIDATED_CRYSTAL_BUS"
AUTHORITY_LEDGER_ENV = "BEAST_CRYSTAL_BUS_AUTHORITY_LEDGER"
CUSTODY_SCHEMA = "beast.crystal_bus.custody.v1"
REQUIRED_SEALS = fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def strict_peer_credentials(sock: socket.socket) -> tuple[int, int, int]:
    """SO_PEERCRED (pid, uid, gid) with no sandbox fallback: failure is refusal."""
    size = struct.calcsize("3i")
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != size:
        raise PermissionError("SO_PEERCRED returned a malformed credential record")
    pid, uid, gid = struct.unpack("3i", raw)
    return int(pid), int(uid), int(gid)


class _StrictPolicy(PeerAdmissionPolicy):
    """PeerAdmissionPolicy whose credential source is the strict reader."""

    def __init__(self, base: PeerAdmissionPolicy):
        super().__init__(expected_uid=base.expected_uid, process_lease_resolver=base.process_lease_resolver,
                         workspace_checker=base.workspace_checker, arda_checker=base.arda_checker)

    @staticmethod
    def credentials(sock):  # type: ignore[override]
        return strict_peer_credentials(sock)


def content_digest(fd: int) -> str:
    """sha256 over the descriptor's full contents (pread; offset untouched)."""
    size = os.fstat(fd).st_size
    hasher = hashlib.sha256()
    offset = 0
    while offset < size:
        chunk = os.pread(fd, min(1 << 20, size - offset), offset)
        if not chunk:
            break
        hasher.update(chunk)
        offset += len(chunk)
    return "sha256:" + hasher.hexdigest()


class OneUseAuthority:
    """Capability lease digests are consumed exactly once (optionally durable, 0600 append-only log)."""

    def __init__(self, path: str | Path | None = None):
        self._lock = threading.Lock()
        self._consumed: set[str] = set()
        self.path = Path(path).expanduser() if path else None

    def _load(self) -> set[str]:
        if self.path is None or not self.path.exists():
            return set()
        if self.path.is_symlink():
            raise PermissionError("crystal bus authority ledger must not be a symlink")
        return {line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()}

    def consume(self, capability_digest: str) -> None:
        if not capability_digest:
            raise PermissionError("crystal bus transfer requires a capability lease")
        with self._lock:
            if self.path is None:
                if capability_digest in self._consumed:
                    raise PermissionError("crystal bus capability lease replay")
                self._consumed.add(capability_digest)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
                    raise PermissionError("crystal bus authority ledger must be mode 0600")
                fcntl.flock(fd, fcntl.LOCK_EX)
                if capability_digest in self._consumed or capability_digest in self._load():
                    raise PermissionError("crystal bus capability lease replay")
                os.write(fd, (capability_digest + "\n").encode())
                os.fsync(fd)
                self._consumed.add(capability_digest)
            finally:
                os.close(fd)


class CustodyChain:
    """Signed, hash-chained custody receipts (digests only; never capsule bytes or keys)."""

    def __init__(self, signer: Ed25519PrivateKey, signer_id: str):
        self._signer = signer
        self.signer_id = signer_id
        self.receipts: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def append(self, body: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous = self.receipts[-1]["receipt_digest"] if self.receipts else ""
            receipt = {**dict(body), "schema": CUSTODY_SCHEMA, "signer_id": self.signer_id,
                       "issued_at": time.time(), "previous_receipt_digest": previous}
            receipt["receipt_digest"] = _digest(receipt)
            receipt["signature"] = self._signer.sign(receipt["receipt_digest"].encode()).hex()
            self.receipts.append(receipt)
            return dict(receipt)


def verify_custody_chain(receipts: list[Mapping[str, Any]], public_key: Ed25519PublicKey) -> bool:
    previous = ""
    for receipt in receipts:
        body = {k: v for k, v in receipt.items() if k not in {"receipt_digest", "signature"}}
        if body.get("schema") != CUSTODY_SCHEMA or body.get("previous_receipt_digest") != previous:
            return False
        if _digest(body) != receipt.get("receipt_digest"):
            return False
        try:
            public_key.verify(bytes.fromhex(str(receipt.get("signature") or "")), str(receipt["receipt_digest"]).encode())
        except (InvalidSignature, ValueError):
            return False
        previous = str(receipt["receipt_digest"])
    return True


@dataclass
class ReceivedTransfer:
    offer: CapsuleOffer
    fd: int
    peer_receipt: Any
    custody_receipt: dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class ConsolidatedCrystalBus:
    """Capsule descriptor transfer with peer credentials, sequence, verify, one-use authority, custody."""

    def __init__(self, sock: socket.socket, *, peer_policy: PeerAdmissionPolicy, workspace_id: str,
                 signer: Ed25519PrivateKey, signer_id: str, authority: OneUseAuthority, policy_generation: str = "",
                 arda_ref: str = "", expected_audience: str = "", require_sealed: bool = True,
                 capsule_verifier: Callable[[int, CapsuleOffer], bool] | None = None, max_frame: int = 65536,
                 custody: CustodyChain | None = None):
        if sock.family != socket.AF_UNIX or (sock.type & socket.SOCK_SEQPACKET) != socket.SOCK_SEQPACKET:
            raise ValueError("consolidated Crystal Bus requires AF_UNIX SOCK_SEQPACKET")
        if not workspace_id:
            raise ValueError("consolidated Crystal Bus requires a workspace id")
        self.sock = sock
        self.peer_policy = _StrictPolicy(peer_policy)
        self.workspace_id = workspace_id
        self.policy_generation = policy_generation
        self.arda_ref = arda_ref
        self.expected_audience = expected_audience
        self.require_sealed = require_sealed
        self.capsule_verifier = capsule_verifier
        self.max_frame = max_frame
        self.authority = authority
        self.custody = custody or CustodyChain(signer, signer_id)
        self.sequence = SequenceLedger()

    @classmethod
    def pair(cls, **kwargs: Any) -> tuple[ConsolidatedCrystalBus, ConsolidatedCrystalBus]:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        return cls(left, **kwargs), cls(right, **kwargs)

    def close(self) -> None:
        self.sock.close()

    def _receipt_body(self, direction: str, offer: CapsuleOffer, peer: Mapping[str, Any]) -> dict[str, Any]:
        return {"direction": direction, "message_id": offer.message_id, "sequence": offer.sequence,
                "control_digest": offer.control_digest, "capsule_digest": offer.capsule_digest,
                "capsule_size": offer.capsule_size, "crystal_id": offer.crystal_id,
                "promotion_digest": offer.promotion_digest, "capability_lease_digest": offer.capability_lease_digest,
                "audience": offer.audience, "peer": dict(peer), "workspace_id": self.workspace_id,
                "policy_generation": self.policy_generation}

    def send_capsule(self, offer: CapsuleOffer, fd: int) -> CapsuleOffer:
        if os.fstat(fd).st_size != offer.capsule_size:
            raise ValueError("capsule size mismatch")
        if offer.expires_at <= time.time():
            raise PermissionError("capsule offer expired")
        pid, uid, gid = strict_peer_credentials(self.sock)
        wire = offer.with_sequence(self.sequence.next_send())
        data = wire.encode()
        if len(data) > self.max_frame:
            raise ValueError("frame too large")
        self.sock.sendmsg([data], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
        self.custody.append(self._receipt_body("sent", wire, {"pid": pid, "uid": uid, "gid": gid}))
        return wire

    def receive_capsule(self) -> ReceivedTransfer:
        peer = self.peer_policy.admit(self.sock, workspace_id=self.workspace_id, arda_ref=self.arda_ref)
        if not peer.admitted:
            raise PermissionError(peer.reason)
        data, ancdata, flags, _ = self.sock.recvmsg(self.max_frame, socket.CMSG_SPACE(8 * array.array("i").itemsize))
        fds: list[int] = []
        for level, kind, payload in ancdata:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array("i")
                values.frombytes(payload[: len(payload) - len(payload) % values.itemsize])
                fds.extend(values)
        try:
            if flags & getattr(socket, "MSG_TRUNC", 0):
                raise ValueError("truncated frame")
            offer = CapsuleOffer.decode(data)
            self.sequence.accept(offer.sequence)
            if len(fds) != 1 or offer.fd_count != 1:
                raise ValueError("exactly one descriptor required")
            fd = fds[0]
            if offer.expires_at <= time.time():
                raise PermissionError("capsule offer expired")
            if self.expected_audience and offer.audience != self.expected_audience:
                raise PermissionError("capsule audience mismatch")
            if os.fstat(fd).st_size != offer.capsule_size:
                raise ValueError("capsule size mismatch")
            if self.require_sealed:
                try:
                    seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
                except OSError:
                    seals = 0
                if seals & REQUIRED_SEALS != REQUIRED_SEALS:
                    raise PermissionError("capsule descriptor is not sealed")
            if self.capsule_verifier is not None:
                if not self.capsule_verifier(fd, offer):
                    raise ValueError("capsule digest mismatch")
            elif content_digest(fd) != offer.capsule_digest:
                raise ValueError("capsule digest mismatch")
            self.authority.consume(offer.capability_lease_digest)
            receipt = self.custody.append(self._receipt_body(
                "received", offer, {"pid": peer.pid, "uid": peer.uid, "gid": peer.gid,
                                    "process_lease_id": peer.process_lease_id}))
            return ReceivedTransfer(offer, fd, peer, receipt)
        except Exception:
            for item in fds:
                os.close(item)
            raise


@dataclass
class CrystalBusFactory:
    options: dict[str, Any]

    def pair(self) -> tuple[ConsolidatedCrystalBus, ConsolidatedCrystalBus]:
        return ConsolidatedCrystalBus.pair(**self.options)

    def wrap(self, sock: socket.socket) -> ConsolidatedCrystalBus:
        return ConsolidatedCrystalBus(sock, **self.options)


def crystal_bus_from_environment(env: Mapping[str, str] | None = None, *, signer: Ed25519PrivateKey | None = None,
                                 signer_id: str = "", workspace_id: str = "",
                                 peer_policy: PeerAdmissionPolicy | None = None, **options: Any) -> CrystalBusFactory | None:
    """Return a factory only when ``BEAST_CONSOLIDATED_CRYSTAL_BUS=1``; otherwise ``None`` (default-off)."""
    env = os.environ if env is None else env
    if str(env.get(ENV_FLAG, "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if signer is None or not signer_id:
        raise RuntimeError("consolidated Crystal Bus requires a custody signer and signer id")
    if not workspace_id:
        raise RuntimeError("consolidated Crystal Bus requires a workspace id")
    authority = options.pop("authority", None) or OneUseAuthority(env.get(AUTHORITY_LEDGER_ENV) or None)
    return CrystalBusFactory({"peer_policy": peer_policy or PeerAdmissionPolicy(expected_uid=os.getuid()),
                              "workspace_id": workspace_id, "signer": signer, "signer_id": signer_id,
                              "authority": authority, **options})
