from dataclasses import replace

from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase2_commons_quorum import (
    PHASE2_COMMONS_ROLES,
    bind_phase2_commons_quorum,
)


def _node(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "algorithm": ML_KEM_ALGORITHM,
        "confirmed": True,
        "secret_exported": False,
        "health_ok": True,
        "public_key_digest": sha256_digest({"public_key": node_id}),
        "public_key_document_digest": sha256_digest({"public_key_document": node_id}),
        "public_key_signature_digest": sha256_digest({"public_key_signature": node_id}),
        "challenge_confirmation_digest": sha256_digest({"challenge_confirmation": node_id}),
        "challenge_signature_digest": sha256_digest({"challenge_signature": node_id}),
        "ciphertext_digest": sha256_digest({"ciphertext": node_id}),
        "ciphertext_size_bytes": 1088,
        "shared_secret_size_bytes": 32,
        "transcript_digest": sha256_digest({"transcript": node_id}),
        "health_digest": sha256_digest({"health": node_id}),
    }


def _ml_kem_receipt() -> dict:
    payload = {
        "beast_object_type": "commons_ml_kem_gauntlet_receipt",
        "status": "passed",
        "algorithm": ML_KEM_ALGORITHM,
        "secret_storage_policy": "shared_secret_bytes_never_serialized",
        "nodes": [_node("commons-node-a"), _node("commons-node-b"), _node("commons-node-c")],
        "nodes_requested": ["http://127.0.0.1:8111", "http://127.0.0.1:8112", "http://127.0.0.1:8113"],
        "pairwise_transcript_matrix": [
            {
                "from_node_id": source,
                "to_node_id": target,
                "algorithm": ML_KEM_ALGORITHM,
                "pair_transcript_digest": sha256_digest({"pair": source, "target": target}),
                "source_health_digest": sha256_digest({"health": source}),
                "target_public_key_digest": sha256_digest({"public_key": target}),
            }
            for source in ("commons-node-a", "commons-node-b", "commons-node-c")
            for target in ("commons-node-a", "commons-node-b", "commons-node-c")
            if source != target
        ],
    }
    payload["receipt_digest"] = sha256_digest(payload)
    return payload


def _digests() -> dict[str, str]:
    return {
        "sophia_acquisition": sha256_digest({"receipt": "sophia"}),
        "harmonic_transfer": sha256_digest({"receipt": "harmonic"}),
        "seraph_injections": sha256_digest({"receipt": "seraph"}),
        "live_replacement": sha256_digest({"receipt": "live"}),
        "stale_replay": sha256_digest({"receipt": "replay"}),
    }


def _bind(**kwargs):
    return bind_phase2_commons_quorum(
        ml_kem_receipt=kwargs.pop("ml_kem_receipt", _ml_kem_receipt()),
        phase2_world_state_digest=kwargs.pop("phase2_world_state_digest", sha256_digest({"phase2": "world"})),
        proposal_digest=kwargs.pop("proposal_digest", sha256_digest({"proposal": "phase2-stale-listener"})),
        evidence_digests=kwargs.pop("evidence_digests", _digests()),
        **kwargs,
    )


def test_phase2_commons_quorum_binds_exact_world_digest_and_roles():
    phase2_world = sha256_digest({"phase2": "exact-live-world"})
    admission, quorum, report = _bind(phase2_world_state_digest=phase2_world)

    assert admission.admitted is True
    assert admission.world_state_digest == phase2_world
    assert all(node.world_state_digest == phase2_world for node in admission.admitted_nodes)
    assert quorum.decision.value == "approved"
    assert quorum.world_state_digest == phase2_world
    assert report.passed is True
    assert report.phase2_world_state_digest == phase2_world
    assert report.witness_roles == ("adversarial", "physical", "semantic")
    assert report.quorum_evidence_class == "local_world_bound_quorum_simulation"
    assert report.independent_attested_quorum is False
    assert report.provider_calls_used == 0
    assert report.execution_authority_allowed is False


def test_phase2_commons_quorum_rejects_synthetic_minimal_ml_kem_receipt():
    synthetic = {
        "beast_object_type": "commons_ml_kem_gauntlet_receipt",
        "status": "passed",
        "algorithm": ML_KEM_ALGORITHM,
        "secret_storage_policy": "shared_secret_bytes_never_serialized",
        "nodes": [
            {
                "node_id": "commons-node-a",
                "algorithm": ML_KEM_ALGORITHM,
                "confirmed": True,
                "secret_exported": False,
                "health_ok": True,
                "public_key_digest": sha256_digest({"public": "a"}),
                "transcript_digest": sha256_digest({"transcript": "a"}),
                "health_digest": sha256_digest({"health": "a"}),
            },
            {
                "node_id": "commons-node-b",
                "algorithm": ML_KEM_ALGORITHM,
                "confirmed": True,
                "secret_exported": False,
                "health_ok": True,
                "public_key_digest": sha256_digest({"public": "b"}),
                "transcript_digest": sha256_digest({"transcript": "b"}),
                "health_digest": sha256_digest({"health": "b"}),
            },
            {
                "node_id": "commons-node-c",
                "algorithm": ML_KEM_ALGORITHM,
                "confirmed": True,
                "secret_exported": False,
                "health_ok": True,
                "public_key_digest": sha256_digest({"public": "c"}),
                "transcript_digest": sha256_digest({"transcript": "c"}),
                "health_digest": sha256_digest({"health": "c"}),
            },
        ],
    }
    synthetic["receipt_digest"] = sha256_digest(synthetic)

    _admission, quorum, report = _bind(ml_kem_receipt=synthetic)

    assert quorum.decision.value == "quorum_unavailable"
    assert report.passed is False
    assert "ml_kem_pairwise_matrix_present" in report.red_gates
    assert "all_nodes_confirmed_and_healthy" in report.red_gates


def test_phase2_commons_quorum_rejects_secret_exported_node():
    ml_kem = _ml_kem_receipt()
    ml_kem["nodes"][1]["secret_exported"] = True

    _admission, quorum, report = _bind(ml_kem_receipt=ml_kem)

    assert quorum.decision.value == "quorum_unavailable"
    assert report.passed is False
    assert "all_nodes_confirmed_and_healthy" in report.red_gates


def test_phase2_commons_quorum_rejects_non_diverse_roles():
    _admission, quorum, report = _bind(
        role_by_node={
            "commons-node-a": "semantic",
            "commons-node-b": "semantic",
            "commons-node-c": "semantic",
        }
    )

    assert quorum.decision.value == "quorum_unavailable"
    assert report.passed is False
    assert "role_diverse_minimum" in report.red_gates


def test_phase2_commons_quorum_rejects_missing_vote_secret():
    secrets = {
        "commons-node-a": b"dai-phase2-commons-node-a",
        "commons-node-b": b"dai-phase2-commons-node-b",
    }

    _admission, quorum, report = _bind(secrets=secrets)

    assert quorum.decision.value == "quorum_unavailable"
    assert report.passed is False
    assert "approval_count" in report.red_gates
