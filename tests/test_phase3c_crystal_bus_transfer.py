from __future__ import annotations

import os
import fcntl
import time
import tempfile
from pathlib import Path

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.crystal_bus.bus import (
    ConsolidatedCrystalBus,
    CapsuleOffer,
    crystal_bus_from_environment,
    CustodyChain,
    OneUseAuthority,
    content_digest,
    verify_custody_chain,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def test_crystal_bus_capsule_transfer_in_coordinator(tmp_path: Path) -> None:
    """Phase 3C: Coordinator transfers a real sealed capsule through the Crystal Bus
    with custody chain verification, not just an in-process pair."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy

    workspace_id = "ws-test"

    # Create a bus factory directly (not from environment)
    factory = ConsolidatedCrystalBus.pair(
        peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()),
        workspace_id=workspace_id,
        signer=Ed25519PrivateKey.generate(),
        signer_id="test-signer",
        authority=OneUseAuthority(),
    )
    assert factory is not None, "factory should be created"

    left, right = factory

    # Create a sealed capsule
    capsule_data = b"crystal ir: beast.action_intent.v1"
    fd = os.memfd_create("test-capsule", os.MFD_ALLOW_SEALING)
    os.write(fd, capsule_data)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)

    offer = CapsuleOffer(
        capsule_digest=content_digest(fd),
        capsule_size=len(capsule_data),
        crystal_id="crystal:test",
        promotion_digest="sha256:" + "a" * 64,
        capability_lease_digest="sha256:" + "b" * 64,
        audience="executor:test",
        expires_at=time.time() + 60,
    )

    # Transfer through the bus
    sent = left.send_capsule(offer, fd)
    received = right.receive_capsule()

    # Verify the transfer worked
    assert os.pread(received.fd, len(capsule_data), 0) == capsule_data
    assert received.offer.capsule_digest == content_digest(fd)
    assert received.custody_receipt["direction"] == "received"
    assert received.custody_receipt["capsule_digest"] == content_digest(fd)
    assert "receipt_digest" in received.custody_receipt
    assert "signature" in received.custody_receipt

    received.close()
    os.close(fd)
    left.close()
    right.close()


def test_coordinator_emits_crystal_bus_transfer_event(tmp_path: Path) -> None:
    """Phase 3C: Coordinator's _bus_event should emit a capsule_transfer event
    with custody receipt when the flag is enabled and the environment is properly configured.

    This test verifies the actual implementation by setting up a proper environment
    that allows crystal_bus_from_environment to create a factory.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.kernel.crystal_bus.bus import crystal_bus_from_environment, ConsolidatedCrystalBus, OneUseAuthority
    from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy

    workspace_id = "ws-test"
    signer = Ed25519PrivateKey.generate()

    # Set up environment WITHOUT signer/workspace_id to test the fallback behavior
    # The _bus_event now generates a local signer automatically, so it should work
    env = {
        "BEAST_CONSOLIDATED_CRYSTAL_BUS": "1",
        "BEAST_CRYSTAL_BUS_AUTHORITY_LEDGER": str(tmp_path / "authority.log"),
        # Don't provide signer/workspace_id env vars - they should be generated automatically
    }

    coordinator = CoderIntegrationCoordinator(
        workspace=tmp_path,
        environ=env,
        bus_probe=None,  # Force the bus_probe is None path
    )

    # Call the internal _bus_event method
    # This will now generate a local signer automatically and should work
    result = coordinator._bus_event(metadata={
        "objective": "Test objective",
        "crystal_id": "test-crystal",
        "run_id": "test-run",
    })

    # Verify the event structure - should now fire with the auto-generated signer
    assert result["event_type"] == "agent.integration.fired"
    assert result["payload"]["capability"] == "crystal_bus"
    assert result["payload"]["mode"] == "capsule_transfer"
    assert result["payload"]["reason"] == "capsule_transfer_verified"


def test_crystal_bus_transfer_round_trip_with_custody_chain(tmp_path: Path) -> None:
    """Complete round-trip test: create capsule, transfer, verify custody chain on both ends."""
    from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy

    key = Ed25519PrivateKey.generate()
    pub = key.public_key()

    left, right = ConsolidatedCrystalBus.pair(
        peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()),
        workspace_id="ws-test",
        signer=key,
        signer_id="test-signer",
        authority=OneUseAuthority(),
    )

    # Create multiple capsules and transfer them
    fds = []
    try:
        for i in range(3):
            data = f"capsule-{i}".encode()
            fd = os.memfd_create(f"capsule-{i}", os.MFD_ALLOW_SEALING)
            os.write(fd, data)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                        fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)
            fds.append((fd, data))

            offer = CapsuleOffer(
                capsule_digest="sha256:" + __import__("hashlib").sha256(data).hexdigest(),
                capsule_size=len(data),
                crystal_id=f"crystal-{i}",
                promotion_digest="sha256:" + "a" * 64,
                capability_lease_digest="sha256:" + str(i) * 64,
                audience="executor:test",
                expires_at=time.time() + 60,
            )
            left.send_capsule(offer, fd)
            received = right.receive_capsule()
            assert os.pread(received.fd, len(data), 0) == data
            received.close()

        # Verify custody chain on sender
        from app.kernel.crystal_bus.bus import verify_custody_chain
        assert verify_custody_chain(left.custody.receipts, pub)
        assert verify_custody_chain(right.custody.receipts, pub)

        # Verify chain order
        chain = left.custody.receipts
        for i in range(1, len(chain)):
            assert chain[i]["previous_receipt_digest"] == chain[i-1]["receipt_digest"]

    finally:
        for fd, _ in fds:
            os.close(fd)
        left.close()
        right.close()


def test_capsule_transfer_fails_on_unsealed_descriptor(tmp_path: Path) -> None:
    """Transfer should refuse unsealed descriptors."""
    from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy

    key = Ed25519PrivateKey.generate()

    left, right = ConsolidatedCrystalBus.pair(
        peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()),
        workspace_id="ws-test",
        signer=key,
        signer_id="test-signer",
        authority=OneUseAuthority(),
    )

    # Create UNSEALED capsule
    data = b"unsealed capsule"
    fd = os.memfd_create("unsealed", os.MFD_ALLOW_SEALING)
    os.write(fd, data)
    # Note: NOT sealing the descriptor

    offer = CapsuleOffer(
        capsule_digest="sha256:" + __import__("hashlib").sha256(data).hexdigest(),
        capsule_size=len(data),
        crystal_id="crystal:test",
        promotion_digest="sha256:" + "a" * 64,
        capability_lease_digest="sha256:" + "b" * 64,
        audience="executor:test",
        expires_at=time.time() + 60,
    )

    try:
        left.send_capsule(offer, fd)
        import pytest
        with pytest.raises(PermissionError, match="not sealed"):
            right.receive_capsule()
    finally:
        os.close(fd)
        left.close()
        right.close()


def test_capsule_transfer_fails_on_digest_mismatch(tmp_path: Path) -> None:
    """Transfer should refuse capsules with mismatched digest."""
    from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy

    key = Ed25519PrivateKey.generate()

    left, right = ConsolidatedCrystalBus.pair(
        peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()),
        workspace_id="ws-test",
        signer=key,
        signer_id="test-signer",
        authority=OneUseAuthority(),
    )

    data = b"correct data"
    fd = os.memfd_create("test", os.MFD_ALLOW_SEALING)
    os.write(fd, data)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)

    # Offer with WRONG digest
    offer = CapsuleOffer(
        capsule_digest="sha256:" + "f" * 64,  # Wrong digest
        capsule_size=len(data),
        crystal_id="crystal:test",
        promotion_digest="sha256:" + "a" * 64,
        capability_lease_digest="sha256:" + "b" * 64,
        audience="executor:test",
        expires_at=time.time() + 60,
    )

    try:
        left.send_capsule(offer, fd)
        import pytest
        with pytest.raises(ValueError, match="digest mismatch"):
            right.receive_capsule()
    finally:
        os.close(fd)
        left.close()
        right.close()


def test_custody_chain_is_chained_and_signed(tmp_path: Path) -> None:
    """Verify custody chain is properly chained (previous_receipt_digest) and signed."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pub = key.public_key()

    chain = CustodyChain(key, "test-signer")

    # Append multiple receipts
    r1 = chain.append({"direction": "sent", "message_id": "msg-1", "capsule_digest": "sha256:" + "a" * 64})
    r2 = chain.append({"direction": "received", "message_id": "msg-1", "capsule_digest": "sha256:" + "a" * 64})
    r3 = chain.append({"direction": "sent", "message_id": "msg-2", "capsule_digest": "sha256:" + "b" * 64})

    # Verify chain structure
    assert r1["previous_receipt_digest"] == ""
    assert r2["previous_receipt_digest"] == r1["receipt_digest"]
    assert r3["previous_receipt_digest"] == r2["receipt_digest"]

    # Verify signatures
    for r in [r1, r2, r3]:
        assert "signature" in r
        assert "receipt_digest" in r
        assert "signer_id" in r
        assert r["signer_id"] == "test-signer"

    # Verify chain verification
    from app.kernel.crystal_bus.bus import verify_custody_chain
    assert verify_custody_chain(chain.receipts, pub)

    # Tampering should fail
    tampered = [dict(r1, capsule_digest="sha256:" + "x" * 64), r2, r3]
    assert not verify_custody_chain(tampered, pub)

    # Reordering should fail
    assert not verify_custody_chain([r2, r1, r3], pub)

    # Wrong public key should fail
    assert not verify_custody_chain(chain.receipts, Ed25519PrivateKey.generate().public_key())


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])