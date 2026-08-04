from dataclasses import replace

import pytest

from app.kernel.compute.operator_language import OperatorMeaningDomain, compile_bounded_meaning
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.semantic_generalizer import (
    SemanticCrystalLifecycleState,
    SemanticCrystalRegistry,
    SemanticEpisode,
    SemanticGeneralizer,
    semantic_intent_fingerprint,
)


def _digest(value):
    return sha256_digest(value)


def _episode(episode_id="episode:1", utterance="What is BEAST status?"):
    from tests.test_operator_language import _evidence

    meaning, frame = compile_bounded_meaning(
        meaning_id="meaning:beast-status",
        domain=OperatorMeaningDomain.SERVICE,
        intent="summarize_service",
        slots={"name": "beast", "status": "healthy", "title": "BEAST", "body": "BEAST is healthy."},
        evidence=(_evidence(),),
        negative_conditions=("service registry digest drift",),
    )
    return SemanticEpisode(
        episode_id=episode_id,
        utterance=utterance,
        meaning=meaning,
        answer_frame=frame,
        schema_digest=_digest({"schema": "operator-language-v1"}),
        discourse_digest=_digest({"utterance-family": "service-status"}),
        world_digest=_digest({"world": "local-runtime"}),
        capability_digest=_digest({"capability": "read_service_registry"}),
        evidence_digest=_evidence().evidence_digest,
        policy_digest=_evidence().policy_digest,
        temporal_scope_digest=_evidence().temporal_scope_digest,
        verification_evidence_digest=_evidence().binding_digest,
        verified=True,
        provider_calls=1,
    )


def test_semantic_generalizer_promotes_repeated_verified_meaning_episodes():
    first = _episode("episode:1", "What is BEAST status?")
    second = _episode("episode:2", "  what   is beast status? ")

    crystal, receipt = SemanticGeneralizer().promote(
        [second, first],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )
    outcome = SemanticGeneralizer().replay(
        crystal,
        first.reuse_key,
        expected_key_digest=receipt.semantic_key_digest,
        provider_enabled=False,
    )

    assert receipt.promoted is True
    assert receipt.provider_calls_observed == 2
    assert outcome.reused is True
    assert outcome.provider_called is False
    assert outcome.answer_frame == first.answer_frame


def test_semantic_record_replay_uses_sealed_key_not_caller_supplied_digest():
    first = _episode("episode:1", "What is BEAST status?")
    record = SemanticGeneralizer().promote_record(
        [first, _episode("episode:2", "  what   is beast status? ")],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )

    outcome = SemanticGeneralizer().replay_record(record, first.reuse_key, provider_enabled=False)

    assert record.semantic_key_digest == first.reuse_key.semantic_match_digest
    assert record.promotion_receipt_digest == record.promotion_receipt.receipt_digest
    assert record.appraisal_digest.startswith("sha256:")
    assert outcome.reused is True
    assert outcome.provider_called is False
    assert outcome.answer_frame == first.answer_frame


def test_semantic_generalizer_promotes_bounded_operator_paraphrases():
    first = _episode("episode:1", "What is BEAST status?")
    record = SemanticGeneralizer(minimum_verified_episodes=3).promote_record(
        [
            first,
            _episode("episode:2", "Is BEAST healthy?"),
            _episode("episode:3", "Give me BEAST's current state, please."),
        ],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )
    paraphrase = _episode("episode:request", "How is BEAST doing?").reuse_key
    endpoint = _episode("episode:endpoint", "Where is BEAST listening?").reuse_key

    reused = SemanticGeneralizer().replay_record(record, paraphrase, provider_enabled=False)
    refused = SemanticGeneralizer().replay_record(record, endpoint, provider_enabled=False)

    assert semantic_intent_fingerprint("What is BEAST status?") == ("beast", "status")
    assert reused.reused is True
    assert reused.answer_frame == first.answer_frame
    assert refused.reused is False
    assert "semantic_fingerprint_digest" in refused.refusal_reason


def test_semantic_record_replay_rejects_stale_revoked_expired_and_verifier_drift():
    first = _episode("episode:1")
    record = SemanticGeneralizer().promote_record(
        [first, _episode("episode:2")],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
        expires_at="2026-08-05T00:00:00+00:00",
    )
    stale_key = replace(first.reuse_key, world_digest=_digest({"world": "changed"}))

    stale = SemanticGeneralizer().replay_record(record, stale_key)
    expired = SemanticGeneralizer().replay_record(record, first.reuse_key, now="2026-08-06T00:00:00+00:00")
    drift = SemanticGeneralizer().replay_record(record, first.reuse_key, verifier_version="semantic-generalizer.v2")
    revoked_record = record.revoke("policy withdrew registry evidence")
    revoked = SemanticGeneralizer().replay_record(revoked_record, first.reuse_key)

    assert stale.reused is False
    assert "world_digest" in stale.refusal_reason
    assert expired.reused is False
    assert "expired" in expired.refusal_reason
    assert drift.reused is False
    assert "version drift" in drift.refusal_reason
    assert revoked.reused is False
    assert "revoked" in revoked.refusal_reason
    assert revoked_record.lifecycle_state is SemanticCrystalLifecycleState.REVOKED


def test_semantic_crystal_registry_persists_lifecycle_index_and_revocation(tmp_path):
    first = _episode("episode:1")
    record = SemanticGeneralizer().promote_record(
        [first, _episode("episode:2")],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )
    registry = SemanticCrystalRegistry(tmp_path / "semantic.jsonl")

    registry.promote(record)
    revoked = registry.revoke(record.crystal.crystal_id, reason="stale evidence")
    stored = registry.get(record.crystal.crystal_id)
    body = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")

    assert stored == revoked
    assert '"lifecycle_state":"revoked"' in body
    assert revoked.record_digest in body


def test_semantic_crystal_registry_reloads_full_records_for_replay(tmp_path):
    first = _episode("episode:1")
    second = _episode("episode:2")
    record = SemanticGeneralizer().promote_record(
        [first, second],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )
    registry = SemanticCrystalRegistry(tmp_path / "semantic.jsonl")
    registry.promote(record)

    loaded = SemanticCrystalRegistry(tmp_path / "semantic.jsonl")
    loaded.load()
    restored = loaded.get(record.crystal.crystal_id)

    assert restored is not None
    assert restored.record_digest == record.record_digest
    outcome = SemanticGeneralizer().replay_record(restored, first.reuse_key, provider_enabled=False)
    assert outcome.reused is True
    assert outcome.provider_called is False


def test_semantic_generalizer_rejects_stale_world_reuse():
    episode = _episode()
    crystal, receipt = SemanticGeneralizer().promote(
        [_episode("episode:1"), _episode("episode:2")],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )
    stale_key = replace(episode.reuse_key, world_digest=_digest({"world": "changed"}))

    outcome = SemanticGeneralizer().replay(
        crystal,
        stale_key,
        expected_key_digest=receipt.semantic_key_digest,
        provider_enabled=False,
    )

    assert outcome.reused is False
    assert outcome.provider_called is False
    assert "key digest" in outcome.refusal_reason


def test_semantic_generalizer_rejects_negative_applicability_condition():
    first = _episode("episode:1")
    crystal, receipt = SemanticGeneralizer().promote(
        [first, _episode("episode:2")],
        crystal_id="meaning-crystal:beast-status",
        verifier_id="semantic-generalizer-test",
    )

    outcome = SemanticGeneralizer().replay(
        crystal,
        first.reuse_key,
        expected_key_digest=receipt.semantic_key_digest,
        active_negative_conditions=("service registry digest drift",),
    )

    assert outcome.reused is False
    assert "negative applicability condition" in outcome.refusal_reason


def test_semantic_generalizer_requires_repeated_verified_equivalent_episodes():
    first = _episode("episode:1")
    different = _episode("episode:2")
    different = replace(
        different,
        discourse_digest=_digest({"utterance-family": "other"}),
    )

    with pytest.raises(ValueError, match="reuse key"):
        SemanticGeneralizer().promote(
            [first, different],
            crystal_id="meaning-crystal:bad",
            verifier_id="semantic-generalizer-test",
        )
