from dataclasses import replace
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_commons_online import (
    DIO_COMMONS_ONLINE_VERSION,
    DIOCommonsAdmissionPolicy,
    DIOCommonsCapabilityManifest,
    DIOCommonsChallenge,
    DIOCommonsRegisteredSpace,
    DIOCommonsSpaceIdentity,
    admit_commons_online_space,
    issue_commons_lease,
    sign_commons_identity,
    verify_commons_identity,
    verify_commons_lease,
)
from app.kernel.dai.dio_distributed_quorum import DIOWitnessRole, public_key_b64, public_key_fingerprint


def _identity_and_manifest():
    node_key = Ed25519PrivateKey.generate()
    return _identity_and_manifest_for(
        node_key,
        node_id="dio:hf:semantic-witness-01",
        role=DIOWitnessRole.SEMANTIC,
        operator_root="hf:Byron230686",
        platform="huggingface-docker-space",
        provider="huggingface",
        attestation_class="signed_software_runtime",
        authority="remote_signed_software_witness_only",
    )


def _identity_and_manifest_for(node_key, *, node_id, role, operator_root, platform, provider, attestation_class, authority):
    verifier = sha256_digest({"verifier": "hf"})
    manifest = DIOCommonsCapabilityManifest(
        "dio_commons_capability_manifest", DIO_COMMONS_ONLINE_VERSION,
        node_id, verifier, ("semantic_vote", "challenge_attestation"),
        authority, True,
    )
    pub = public_key_b64(node_key.public_key())
    identity = DIOCommonsSpaceIdentity(
        "dio_commons_space_identity", DIO_COMMONS_ONLINE_VERSION,
        node_id, role, operator_root,
        platform, provider, pub, public_key_fingerprint(pub), verifier,
        manifest.manifest_digest, attestation_class, authority,
        "dio-phase4-online-001",
    )
    return node_key, identity, manifest


def _challenge(now=None):
    now = now or datetime.now(timezone.utc)
    return DIOCommonsChallenge(
        "dio_commons_challenge", DIO_COMMONS_ONLINE_VERSION,
        sha256_digest({"proposal": 1}), sha256_digest({"evidence": 1}), sha256_digest({"world": 1}),
        "dio-phase4-online-001", "fresh-online-challenge-" + "x" * 24,
        now.isoformat(), (now + timedelta(minutes=5)).isoformat(),
    )


def _policy(identity, coordinator):
    return DIOCommonsAdmissionPolicy(
        "dio_commons_admission_policy",
        DIO_COMMONS_ONLINE_VERSION,
        "dio-phase4-online-001",
        public_key_b64(coordinator.public_key()),
        (
            DIOCommonsRegisteredSpace(
                identity.node_id,
                identity.role,
                identity.operator_root,
                identity.key_fingerprint,
                identity.verifier_digest,
                identity.capability_manifest_digest,
                identity.attestation_class,
                identity.maximum_authority,
            ),
        ),
        (DIOWitnessRole.SEMANTIC,),
    )


def test_online_space_identity_is_signed_and_manifest_bound():
    key, identity, manifest = _identity_and_manifest()
    signature = sign_commons_identity(identity, key)

    assert verify_commons_identity(identity, signature) is True
    assert identity.capability_manifest_digest == manifest.manifest_digest
    assert verify_commons_identity(replace(identity, governance_epoch="wrong"), signature) is False


def test_active_lease_binds_identity_manifest_challenge_epoch_and_freshness():
    _key, identity, manifest = _identity_and_manifest()
    challenge = _challenge()
    coordinator = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    lease = issue_commons_lease(identity, manifest, challenge, coordinator, issued_at=now.isoformat(), expires_at=(now + timedelta(minutes=2)).isoformat())

    assert verify_commons_lease(lease, now=now) is True
    assert verify_commons_lease(replace(lease, governance_epoch="stale-epoch"), now=now) is False
    assert verify_commons_lease(lease, now=now + timedelta(minutes=3)) is False


def test_online_admission_mints_lease_only_for_registered_fresh_identity():
    key, identity, manifest = _identity_and_manifest()
    coordinator = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    report, lease = admit_commons_online_space(
        identity=identity,
        identity_signature=sign_commons_identity(identity, key),
        manifest=manifest,
        challenge=_challenge(now),
        policy=_policy(identity, coordinator),
        coordinator=coordinator,
        now=now,
    )

    assert report.admitted is True
    assert report.red_gates == ()
    assert lease is not None
    assert report.active_lease_digest == lease.lease_digest
    assert verify_commons_lease(lease, now=now) is True
    assert report.execution_authority_allowed is False
    assert report.production_authority_allowed is False


def test_online_admission_rejects_attestation_downgrade_with_valid_signature():
    key, identity, manifest = _identity_and_manifest()
    coordinator = Ed25519PrivateKey.generate()
    downgraded = replace(identity, attestation_class="provider_hardware_attestation")
    report, lease = admit_commons_online_space(
        identity=downgraded,
        identity_signature=sign_commons_identity(downgraded, key),
        manifest=manifest,
        challenge=_challenge(),
        policy=_policy(identity, coordinator),
        coordinator=coordinator,
        now=datetime.now(timezone.utc),
    )

    assert report.admitted is False
    assert lease is None
    assert "registered_attestation_class_bound" in report.red_gates


def test_online_admission_rejects_wrong_manifest_stale_challenge_and_duplicate_role():
    key, identity, manifest = _identity_and_manifest()
    coordinator = Ed25519PrivateKey.generate()
    stale = DIOCommonsChallenge(
        "dio_commons_challenge", DIO_COMMONS_ONLINE_VERSION,
        sha256_digest({"proposal": 1}), sha256_digest({"evidence": 1}), sha256_digest({"world": 1}),
        "dio-phase4-online-001", "fresh-online-challenge-" + "y" * 24,
        "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00",
    )
    wrong_manifest = replace(manifest, node_id="dio:other")
    report, lease = admit_commons_online_space(
        identity=identity,
        identity_signature=sign_commons_identity(identity, key),
        manifest=wrong_manifest,
        challenge=stale,
        policy=_policy(identity, coordinator),
        coordinator=coordinator,
        now=datetime(2026, 8, 4, tzinfo=timezone.utc),
        active_identities=(identity,),
    )

    assert report.admitted is False
    assert lease is None
    assert "challenge_fresh" in report.red_gates
    assert "manifest_node_matches_identity" in report.red_gates
    assert "role_not_already_active" in report.red_gates
