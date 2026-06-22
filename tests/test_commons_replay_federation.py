import json
import zipfile
from pathlib import Path

import pytest

from app.kernel.commons_privacy import CommonsPrivacyScrubber
from app.kernel.commons_replay import CommonsReplayEngine
from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import export_space, import_space, package_tiny_llama_case
from app.kernel.federated_commons import FederatedCommons


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"


def prepared_registry(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(CASE, registry.root / "tiny_llama_opus_gateway_repair")
    return registry


def test_content_addressed_bundle_detects_tampering(tmp_path):
    registry = prepared_registry(tmp_path)
    bundle = tmp_path / "space.zip"

    exported = export_space(registry.root / "tiny_llama_opus_gateway_repair", bundle)
    preview = import_space(bundle, tmp_path / "imports", approved=False, dry_run=True)

    assert exported["bundle_id"].startswith("bundle_")
    assert preview["bundle_validation"]["entries_valid"] is True
    assert preview["bundle_validation"]["privacy"]["safe"] is True

    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.writestr("README.md", "tampered")
    with pytest.raises(ValueError, match="safety scan failed"):
        import_space(bundle, tmp_path / "other", approved=True, dry_run=False)


def test_privacy_scrubber_finds_nested_secrets_and_private_paths():
    report = CommonsPrivacyScrubber().scan_payload({
        "safe": {"api_key": "not-for-export"},
        "path": "/home/user/private/project.py",
    })

    assert {item["reason"] for item in report} == {"sensitive_key", "absolute_private_path"}


def test_deterministic_and_live_verifier_replay_build_trust_receipts(tmp_path):
    registry = prepared_registry(tmp_path)

    deterministic = registry.replay("tiny_llama_opus_gateway_repair")
    live = registry.replay(
        "tiny_llama_opus_gateway_repair",
        target=CASE / "case_repo",
        deterministic_only=False,
        approved=True,
    )

    assert deterministic["reproduced"] is True
    assert deterministic["trust_score"] == 0.75
    assert live["live_verifier_passed"] is True
    assert live["trust_score"] == 1.0
    assert registry.list_spaces()["spaces"][0]["local_trust_score"] == 1.0
    with pytest.raises(ValueError, match="forbidden shell"):
        CommonsReplayEngine._allowlisted_command("python -m pytest tests -q; rm -rf .")


def test_federation_requires_allowlist_tracks_reputation_and_revokes(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare(
        "tiny_llama_opus_gateway_repair",
        contributor_id="node_alpha",
        ttl_days=7,
    )

    with pytest.raises(ValueError, match="not locally allowlisted"):
        federation.ingest(envelope)
    federation.allow_contributor(
        "node_alpha", public_key_hash=envelope["signature"]["public_key_hash"],
        approved=True, reason="known test node",
    )
    ingested = federation.ingest(envelope)
    duplicate = federation.ingest(envelope)
    replay = registry.replay(
        "tiny_llama_opus_gateway_repair",
        contributor_id="node_alpha",
    )
    reproduced = federation.record_reproduction(envelope["envelope_id"], replay)
    revoked = federation.revoke(
        envelope["envelope_id"], approved=True, reason="test retirement", approved_by="test",
    )
    state = federation.state()

    assert ingested["state"] == "quarantined_hypothesis"
    assert duplicate["duplicate"] is True
    assert reproduced["reputation"]["successful_reproductions"] == 1
    assert revoked["revoked"] is True
    assert state["envelopes"][0]["state"] == "revoked"
    assert state["abuse_controls"]["max_ttl_days"] == 90


def test_federation_rate_limit_and_signature_tampering_are_rejected(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_beta")
    federation.allow_contributor(
        "node_beta", public_key_hash=envelope["signature"]["public_key_hash"],
        approved=True, reason="test",
    )
    envelope["space_id"] = "tampered"

    with pytest.raises(ValueError, match="signature did not verify"):
        federation.ingest(envelope)

    clean = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_beta")
    federation.MAX_INGESTS_PER_DAY = 0
    with pytest.raises(ValueError, match="rate limit"):
        federation.ingest(clean)


def test_federation_rejects_an_unpinned_signing_key(tmp_path):
    registry = prepared_registry(tmp_path)
    trusted = FederatedCommons(registry, tmp_path / "trusted")
    attacker = FederatedCommons(registry, tmp_path / "attacker")
    trusted_envelope = trusted.prepare("tiny_llama_opus_gateway_repair", contributor_id="same_node")
    attacker_envelope = attacker.prepare("tiny_llama_opus_gateway_repair", contributor_id="same_node")
    trusted.allow_contributor(
        "same_node", public_key_hash=trusted_envelope["signature"]["public_key_hash"],
        approved=True, reason="pin trusted node",
    )

    with pytest.raises(ValueError, match="does not match"):
        trusted.ingest(attacker_envelope)
