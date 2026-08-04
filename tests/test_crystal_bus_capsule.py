import os
import time
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.crystal_bus import CrystalBusAuthorizer, CrystalBusTransport, CrystalMessage
from app.kernel.compute.sealed_capsule import CrystalCapsule
from app.kernel.crystals.capsule_codec import CapsuleCodec


def test_crystal_bus_messages_are_framed_and_typed():
    message = CrystalMessage("CRYSTAL_VERIFY", "msg-1", {"crystal": "crystal:test"})
    decoded = CrystalMessage.decode(message.encode())
    assert decoded.message_type == message.message_type
    assert decoded.message_id == message.message_id
    assert decoded.payload == message.payload
    assert decoded.payload_digest.startswith("sha256:")


def test_crystal_capsule_is_digest_bound_and_sealed():
    capsule = CrystalCapsule().create(b"canonical crystal ir")
    try:
        assert capsule.sealed is True
        assert CrystalCapsule().verify(capsule)
    finally:
        os.close(capsule.fd)

def test_legacy_crystal_capsule_uses_typed_capsule_envelope():
    capsule = CrystalCapsule().create(b"canonical crystal ir")
    try:
        envelope = CapsuleCodec.decode(os.pread(capsule.fd, capsule.size, 0))
        assert envelope["manifest"]["task_class"] == "crystal_capsule"
        assert envelope["manifest"]["authority"] == "artifact_only"
        assert envelope["canonical_ir"]["payload_digest"] == capsule.payload_digest
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
    left, right = CrystalBusTransport.socketpair()
    right.expected_uid = os.getuid()
    try:
        left.send(CrystalMessage("CRYSTAL_VERIFY", "msg-peer", {"ok": True}))
        assert right.receive()[0].message_id == "msg-peer"
    finally:
        left.close(); right.close()


def test_crystal_bus_authorized_mac_session_fd_handoff_accepts_valid_frame():
    lease_id = "lease:sender:1"
    capability = "cap:render:1"
    cgroup = "beast.slice/c4x"
    resolver = lambda _pid, uid, _gid: {
        "process_lease_id": lease_id,
        "uid": uid,
        "workspace_id": "workspace-1",
        "cgroup_id": cgroup,
        "executable_digest": "sha256:" + "a" * 64,
    }
    authorizer = CrystalBusAuthorizer(
        allowed_uid=os.getuid(),
        required_workspace_id="workspace-1",
        required_policy_generation="policy:7",
        process_leases={lease_id: {"uid": os.getuid(), "workspace_id": "workspace-1", "cgroup_id": cgroup}},
    )
    left, right = CrystalBusTransport.socketpair(
        session_key=b"bus-test-key",
        process_lease_resolver=resolver,
    )
    right.authorizer = authorizer
    fd = os.memfd_create("crystal-bus-authorized")
    os.write(fd, b"proof")
    try:
        left.send(
            CrystalMessage(
                "CRYSTAL_PROPOSE",
                "msg-authorized",
                {"proof_digest": "sha256:" + "b" * 64},
                capability_lease_id=capability,
                arda_appraisal_ref="arda:appraisal:1",
                sender_process_lease_id=lease_id,
                policy_generation="policy:7",
                expires_at_unix_ns=time.time_ns() + 5_000_000_000,
            ),
            fds=(fd,),
        )
        message, fds = right.receive()
        assert message.message_id == "msg-authorized"
        assert message.capability_lease_id == capability
        assert len(fds) == 1
        os.close(fds[0])
    finally:
        os.close(fd)
        left.close(); right.close()


def test_crystal_bus_authorizer_rejects_missing_authority_bindings():
    lease_id = "lease:sender:2"
    resolver = lambda _pid, uid, _gid: {
        "process_lease_id": lease_id,
        "uid": uid,
        "workspace_id": "workspace-1",
        "cgroup_id": "beast.slice/c4x",
    }
    left, right = CrystalBusTransport.socketpair(
        session_key=b"bus-test-key",
        process_lease_resolver=resolver,
    )
    right.authorizer = CrystalBusAuthorizer(
        allowed_uid=os.getuid(),
        required_workspace_id="workspace-1",
        required_policy_generation="policy:7",
        process_leases={lease_id: {"uid": os.getuid(), "workspace_id": "workspace-1", "cgroup_id": "beast.slice/c4x"}},
    )
    fd = os.memfd_create("crystal-bus-reject")
    os.write(fd, b"proof")
    try:
        left.send(CrystalMessage("CRYSTAL_PROPOSE", "msg-missing-cap", {"proof": True}), fds=(fd,))
        with pytest.raises(PermissionError, match="capability lease"):
            right.receive()
    finally:
        os.close(fd)
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
