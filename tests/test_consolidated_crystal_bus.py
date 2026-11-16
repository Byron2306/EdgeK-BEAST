"""Delivery 4: consolidated Crystal Bus (default-off) with custody receipts on every descriptor transfer."""
from __future__ import annotations

import fcntl
import hashlib
import os
import socket
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.crystal_bus import CapsuleOffer, PeerAdmissionPolicy
from app.kernel.crystal_bus.bus import (
    ENV_FLAG,
    ConsolidatedCrystalBus,
    CustodyChain,
    OneUseAuthority,
    content_digest,
    crystal_bus_from_environment,
    strict_peer_credentials,
    verify_custody_chain,
)

KEY = Ed25519PrivateKey.generate()
PUB = KEY.public_key()


def _capsule(data: bytes = b"canonical crystal ir", *, seal: bool = True) -> int:
    fd = os.memfd_create("d4-capsule", os.MFD_ALLOW_SEALING)
    os.write(fd, data)
    if seal:
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)
    return fd


def _offer(fd: int, *, lease: str = "sha256:" + "1" * 64, expires: float | None = None, size: int | None = None,
           digest: str | None = None) -> CapsuleOffer:
    return CapsuleOffer(
        capsule_digest=digest or content_digest(fd),
        capsule_size=size if size is not None else os.fstat(fd).st_size,
        crystal_id="crystal:d4",
        promotion_digest="sha256:" + "2" * 64,
        capability_lease_digest=lease,
        audience="executor:d4",
        expires_at=expires if expires is not None else time.time() + 60,
    )


def _pair(**overrides):
    kwargs = {"peer_policy": PeerAdmissionPolicy(expected_uid=os.getuid()), "workspace_id": "ws-1",
              "policy_generation": "policy:7", "signer": KEY, "signer_id": "bus-test", "authority": OneUseAuthority()}
    kwargs.update(overrides)
    return ConsolidatedCrystalBus.pair(**kwargs)


def _transfer(sender, receiver, offer, fd):
    sender.send_capsule(offer, fd)
    return receiver.receive_capsule()


def test_flag_is_default_off():
    assert ENV_FLAG == "BEAST_CONSOLIDATED_CRYSTAL_BUS"
    assert crystal_bus_from_environment({}) is None
    assert crystal_bus_from_environment({ENV_FLAG: "0"}) is None


def test_flag_on_requires_signer_and_builds_factory():
    with pytest.raises(RuntimeError, match="signer"):
        crystal_bus_from_environment({ENV_FLAG: "1"})
    factory = crystal_bus_from_environment({ENV_FLAG: "1"}, signer=KEY, signer_id="bus", workspace_id="ws-1",
                                           peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()))
    left, right = factory.pair()
    assert isinstance(left, ConsolidatedCrystalBus) and isinstance(right, ConsolidatedCrystalBus)
    left.close()
    right.close()


def test_round_trip_emits_signed_chained_custody_receipts_on_both_ends():
    sender, receiver = _pair()
    fd = _capsule()
    try:
        received = _transfer(sender, receiver, _offer(fd), fd)
        assert os.pread(received.fd, 64, 0) == b"canonical crystal ir"
        sent_receipt = sender.custody.receipts[-1]
        recv_receipt = received.custody_receipt
        assert sent_receipt["direction"] == "sent" and recv_receipt["direction"] == "received"
        assert recv_receipt["capsule_digest"] == content_digest(fd)
        assert recv_receipt["peer"]["uid"] == os.getuid()
        assert recv_receipt["workspace_id"] == "ws-1" and recv_receipt["policy_generation"] == "policy:7"
        blob = repr(recv_receipt)
        assert "canonical crystal ir" not in blob and "PRIVATE" not in blob
        assert verify_custody_chain(sender.custody.receipts, PUB)
        assert verify_custody_chain(receiver.custody.receipts, PUB)
        received.close()
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_custody_chain_detects_tamper_and_reorder():
    sender, receiver = _pair()
    fds = [_capsule(b"a"), _capsule(b"bb")]
    try:
        for i, fd in enumerate(fds):
            _transfer(sender, receiver, _offer(fd, lease="sha256:" + str(i) * 64), fd).close()
        chain = [dict(r) for r in receiver.custody.receipts]
        assert chain[1]["previous_receipt_digest"] == chain[0]["receipt_digest"]
        tampered = [dict(chain[0], capsule_digest="sha256:" + "f" * 64), chain[1]]
        assert not verify_custody_chain(tampered, PUB)
        assert not verify_custody_chain(list(reversed(chain)), PUB)
        assert not verify_custody_chain(chain, Ed25519PrivateKey.generate().public_key())
    finally:
        for fd in fds:
            os.close(fd)
        sender.close()
        receiver.close()


def test_capability_lease_is_one_use():
    authority = OneUseAuthority()
    sender, receiver = _pair(authority=authority)
    fd = _capsule()
    try:
        _transfer(sender, receiver, _offer(fd), fd).close()
        sender.send_capsule(_offer(fd), fd)
        with pytest.raises(PermissionError, match="capability lease replay"):
            receiver.receive_capsule()
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_one_use_authority_is_durable_across_instances(tmp_path):
    path = tmp_path / "consumed.log"
    OneUseAuthority(path).consume("sha256:" + "a" * 64)
    with pytest.raises(PermissionError):
        OneUseAuthority(path).consume("sha256:" + "a" * 64)
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("case,match", [
    ("expired", "expired"),
    ("size", "size mismatch"),
    ("digest", "digest mismatch"),
    ("unsealed", "not sealed"),
])
def test_capsule_verification_refusals_close_descriptor(case, match):
    sender, receiver = _pair()
    fd = _capsule(seal=case != "unsealed")
    kwargs = {}
    if case == "expired":
        kwargs["expires"] = time.time() - 1
    if case == "digest":
        kwargs["digest"] = "sha256:" + "e" * 64
    offer = _offer(fd, **kwargs)
    try:
        if case in {"size", "expired"}:  # bypass the sender's own pre-checks to exercise the receiver
            raw = dict(offer.__dict__, sequence=1, **({"capsule_size": 999} if case == "size" else {}))
            sender.sock.sendmsg([CapsuleOffer(**raw).encode()],
                               [(socket.SOL_SOCKET, socket.SCM_RIGHTS, __import__("array").array("i", [fd]))])
        else:
            sender.send_capsule(offer, fd)
        before = len(os.listdir("/proc/self/fd"))
        with pytest.raises((PermissionError, ValueError), match=match):
            receiver.receive_capsule()
        assert len(os.listdir("/proc/self/fd")) <= before
        assert receiver.custody.receipts == []
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_sender_refuses_size_mismatch_or_expiry_before_transfer():
    sender, receiver = _pair()
    fd = _capsule()
    try:
        with pytest.raises(ValueError, match="size mismatch"):
            sender.send_capsule(_offer(fd, size=999), fd)
        with pytest.raises(PermissionError, match="expired"):
            sender.send_capsule(_offer(fd, expires=time.time() - 1), fd)
        assert sender.custody.receipts == []
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_peer_uid_mismatch_refused():
    sender, receiver = _pair(peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid() + 1))
    fd = _capsule()
    try:
        sender.send_capsule(_offer(fd), fd)
        with pytest.raises(PermissionError, match="uid_mismatch"):
            receiver.receive_capsule()
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_stale_process_lease_refused():
    policy = PeerAdmissionPolicy(process_lease_resolver=lambda pid: {"lease_id": f"pid:{pid}", "active": False})
    sender, receiver = _pair(peer_policy=policy)
    fd = _capsule()
    try:
        sender.send_capsule(_offer(fd), fd)
        with pytest.raises(PermissionError, match="stale_process_lease"):
            receiver.receive_capsule()
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_sequence_replay_refused():
    sender, receiver = _pair()
    fd = _capsule()
    try:
        offer = _offer(fd).with_sequence(1)
        import array
        for _ in range(2):
            sender.sock.sendmsg([offer.encode()], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
        receiver.receive_capsule().close()
        with pytest.raises(ValueError, match="sequence"):
            receiver.receive_capsule()
    finally:
        os.close(fd)
        sender.close()
        receiver.close()


def test_requires_seqpacket_and_strict_peer_credentials():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(ValueError, match="SEQPACKET"):
            ConsolidatedCrystalBus(a, peer_policy=PeerAdmissionPolicy(), workspace_id="ws", signer=KEY,
                                   signer_id="x", authority=OneUseAuthority())
    finally:
        a.close()
        b.close()
    x, y = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        pid, uid, gid = strict_peer_credentials(x)
        assert (pid, uid, gid) == (os.getpid(), os.getuid(), os.getgid())
    finally:
        x.close()
        y.close()


def test_content_digest_is_sha256_of_descriptor_bytes():
    fd = _capsule(b"xyz")
    try:
        assert content_digest(fd) == "sha256:" + hashlib.sha256(b"xyz").hexdigest()
    finally:
        os.close(fd)


def test_custody_chain_standalone_round_trip():
    chain = CustodyChain(KEY, "standalone")
    chain.append({"direction": "sent", "capsule_digest": "sha256:" + "0" * 64})
    chain.append({"direction": "sent", "capsule_digest": "sha256:" + "1" * 64})
    assert verify_custody_chain(chain.receipts, PUB)


def test_package_exposes_both_apis():
    import app.kernel.crystal_bus as bus

    for name in ("CapsuleOffer", "CrystalBusEndpoint", "PeerAdmissionPolicy", "SequenceLedger", "CrystalMessage",
                 "CrystalBusTransport", "CrystalBusAuthorizer", "peer_credentials", "ConsolidatedCrystalBus",
                 "OneUseAuthority", "verify_custody_chain", "crystal_bus_from_environment"):
        assert hasattr(bus, name), name
