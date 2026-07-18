import os
from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.crystal_bus import CrystalMessage
from app.kernel.compute.sealed_capsule import CrystalCapsule


def test_crystal_bus_messages_are_framed_and_typed():
    message = CrystalMessage("CRYSTAL_VERIFY", "msg-1", {"crystal": "crystal:test"})
    assert CrystalMessage.decode(message.encode()) == message


def test_crystal_capsule_is_digest_bound_and_sealed():
    capsule = CrystalCapsule().create(b"canonical crystal ir")
    try:
        assert capsule.sealed is True
        assert CrystalCapsule().verify(capsule)
    finally:
        os.close(capsule.fd)

def test_seqpacket_transport_and_fd_passing():
    from app.kernel.compute.crystal_bus import CrystalBusTransport, peer_credentials
    a, b = CrystalBusTransport.socketpair()
    credentials = peer_credentials(b.sock)
    assert len(credentials) == 3
    assert credentials[0] > 0
    assert credentials[1] == os.getuid()
    assert credentials[2] == os.getgid()
    fd = os.memfd_create("crystal-test")
    os.write(fd, b"x")
    a.send(CrystalMessage("CRYSTAL_VERIFY", "msg-2", {"ok": True}), fds=(fd,))
    msg, received = b.receive()
    assert msg.message_type == "CRYSTAL_VERIFY" and msg.payload["ok"] is True and len(received) == 1
    os.close(fd); os.close(received[0]); a.close(); b.close()


def test_seqpacket_expected_uid_accepts_legitimate_peer():
    from app.kernel.compute.crystal_bus import CrystalBusTransport
    left, right = CrystalBusTransport.socketpair()
    right.expected_uid = os.getuid()
    try:
        left.send(CrystalMessage("CRYSTAL_VERIFY", "msg-peer", {"ok": True}))
        assert right.receive()[0].message_id == "msg-peer"
    finally:
        left.close(); right.close()


def test_capsule_signature_binds_authority_metadata():
    private = Ed25519PrivateKey.generate()
    capsule = CrystalCapsule().create(
        b"canonical crystal ir", signer=private, authority_ref="forge:1",
        audience="executor:1", expires_at=9999999999, capability_ref="cap:1",
        appraisal_ref="app:1",
    )
    try:
        assert CrystalCapsule().verify(capsule, verifier=private.public_key())
        assert not CrystalCapsule().verify(replace(capsule, audience="attacker"), verifier=private.public_key())
    finally:
        os.close(capsule.fd)
