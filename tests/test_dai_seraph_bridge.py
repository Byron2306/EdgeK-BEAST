import json

import pytest

from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.seraph_bridge import SeraphBridgeError, seraph_curriculum_from_summary


def _write_summary(tmp_path, **overrides):
    payload = {
        "schema": "metatron_honest_classification_summary.v2",
        "observed_k0_count": 654,
        "tier_distribution": {"platinum": 654, "support_only": 40, "unclassified": 1},
        "sigma": {"match_semantics": "coverage_by_attack_tag_not_live_event_match"},
        "arkime": {"forensic_replay_ready": False, "packaged_pcap_count": 0, "referenced_pcap_count": 97},
        "clamav": {"can_certify_maliciousness": False, "infected_count": 0, "files_scanned": 516},
        "artifacts": {
            "notes": [
                "Observed K0 is separated from deductive K2 support.",
                "Sigma matches are ATT&CK tag coverage records, not live event-stream detections.",
            ]
        },
    }
    payload.update(overrides)
    path = tmp_path / "seraph_summary.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _receipt(path):
    return ArtifactReceipt.from_file(path, organ=DAIOrgan.SERAPH, artifact_schema="test.seraph")


def test_seraph_summary_compiles_to_structured_curriculum(tmp_path):
    path = _write_summary(tmp_path)
    assessment, curriculum = seraph_curriculum_from_summary(path, source_receipt=_receipt(path))

    assert assessment.maximum_authority.value == "adversarial_challenge_only"
    assert assessment.result == "structured_challenge_curriculum_available_no_authority_granted"
    assert len(curriculum.challenge_cases) == 4
    assert len(assessment.challenge_receipts) == 5
    assert "telemetry_claim_boundary" in assessment.attack_families
    assert "evidence_custody_boundary" in assessment.attack_families
    assert "maliciousness_claim_boundary" in assessment.attack_families
    assert "authority_laundering" in assessment.attack_families


def test_seraph_summary_without_observed_k0_is_refused(tmp_path):
    path = _write_summary(tmp_path, observed_k0_count=0)

    with pytest.raises(SeraphBridgeError, match="observed K0"):
        seraph_curriculum_from_summary(path, source_receipt=_receipt(path))


def test_seraph_summary_without_support_only_boundary_is_refused(tmp_path):
    path = _write_summary(tmp_path, tier_distribution={"platinum": 654, "support_only": 0})

    with pytest.raises(SeraphBridgeError, match="support-only"):
        seraph_curriculum_from_summary(path, source_receipt=_receipt(path))


def test_seraph_summary_with_wrong_schema_is_refused(tmp_path):
    path = _write_summary(tmp_path, schema="legacy.unbounded")

    with pytest.raises(SeraphBridgeError, match="schema"):
        seraph_curriculum_from_summary(path, source_receipt=_receipt(path))


def test_seraph_summary_with_tampered_artifact_digest_is_refused(tmp_path):
    path = _write_summary(tmp_path)
    receipt = _receipt(path)
    path.write_text('{"schema":"metatron_honest_classification_summary.v2"}', encoding="utf-8")

    with pytest.raises(SeraphBridgeError, match="digest"):
        seraph_curriculum_from_summary(path, source_receipt=receipt)

