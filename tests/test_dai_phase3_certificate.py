from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase3_certificate import (
    acquire_phase3_certificate_world_lease,
    certificate_temporal_status,
    execute_phase3_certificate_handshake,
    stable_certificate_world_state_digest,
    start_phase3_certificate_lab,
)


def test_phase3_certificate_refuses_expired_endpoint_and_accepts_control():
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    lab = start_phase3_certificate_lab(run_id="test-phase3-certificate", now=now)
    try:
        lease = acquire_phase3_certificate_world_lease(lab, now=now)

        receipt = execute_phase3_certificate_handshake(lab, lease)

        assert receipt.executed is True
        assert receipt.refused_reason == ""
        assert receipt.expired_certificate_refused is True
        assert receipt.expired_observation.refusal_reason == "expired_certificate"
        assert receipt.expired_observation.app_payload_received is False
        assert receipt.control_certificate_accepted is True
        assert receipt.control_observation.app_payload_received is True
        assert receipt.provider_calls_used == 0
        assert receipt.production_authority_allowed is False
        assert receipt.red_gates == ()
        assert receipt.receipt_digest.startswith("sha256:")
    finally:
        lab.cleanup()


def test_phase3_certificate_refuses_stale_evidence_before_handshake():
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    lab = start_phase3_certificate_lab(run_id="test-phase3-certificate-stale-evidence", now=now)
    try:
        lease = acquire_phase3_certificate_world_lease(lab, now=now)
        stale = replace(
            lease,
            evidence_observed_at=(now - timedelta(seconds=301)).isoformat(),
            evidence_freshness_seconds=300,
        )
        before = stable_certificate_world_state_digest(lab)

        receipt = execute_phase3_certificate_handshake(lab, stale)

        assert receipt.executed is False
        assert receipt.refused_reason == "certificate_evidence_stale"
        assert receipt.stale_evidence_refused is True
        assert receipt.expired_observation.connect_ok is False
        assert stable_certificate_world_state_digest(lab) == before
    finally:
        lab.cleanup()


def test_phase3_certificate_rejects_malformed_time_metadata():
    with pytest.raises(ValueError, match="not_after"):
        certificate_temporal_status(
            {
                "not_before": "2026-08-04T12:00:00+00:00",
                "not_after": "zzz",
            },
            evaluation_time=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        )


def test_phase3_certificate_refuses_wrong_world_digest_before_handshake():
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    lab = start_phase3_certificate_lab(run_id="test-phase3-certificate-wrong-world", now=now)
    try:
        lease = acquire_phase3_certificate_world_lease(lab, now=now)
        before = stable_certificate_world_state_digest(lab)

        receipt = execute_phase3_certificate_handshake(
            lab,
            lease,
            supplied_world_state_digest=sha256_digest({"hostile": "wrong-world"}),
        )

        assert receipt.executed is False
        assert receipt.refused_reason == "supplied_world_state_digest_mismatch"
        assert receipt.expired_observation.connect_ok is False
        assert stable_certificate_world_state_digest(lab) == before
    finally:
        lab.cleanup()


def test_phase3_certificate_refuses_certificate_digest_mismatch():
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    lab = start_phase3_certificate_lab(run_id="test-phase3-certificate-digest-mismatch", now=now)
    try:
        lease = acquire_phase3_certificate_world_lease(lab, now=now)
        hostile = replace(lease, expired_certificate_digest=sha256_digest({"hostile": "different-cert"}))
        before = stable_certificate_world_state_digest(lab)

        receipt = execute_phase3_certificate_handshake(lab, hostile)

        assert receipt.executed is False
        assert receipt.refused_reason == "expired_certificate_digest_mismatch"
        assert receipt.expired_observation.connect_ok is False
        assert stable_certificate_world_state_digest(lab) == before
    finally:
        lab.cleanup()
