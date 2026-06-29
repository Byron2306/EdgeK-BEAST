from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity
from app.kernel.data_processing.semantic_compute_pages import (
    SemanticComputePageStore,
    SemanticPageIdentity,
    build_phase3_semantic_pages,
)


def _identity(page_kind: str = "route_card") -> SemanticPageIdentity:
    inference_identity = InferenceArtifactIdentity.from_prompts(
        model="beast-crystal-test",
        tokenizer="test-tokenizer",
        prompt_prefix="prefix",
        system_prompt="system",
        engine="pytest",
        engine_version="1",
        model_revision="rev-a",
        tokenizer_revision="tok-a",
        precision="cpu",
        quantization="none",
        policy_fingerprint="policy-a",
        tool_schema_fingerprint="tools-a",
        skill_tree_fingerprint="skills-a",
        repository_fingerprint="repo-a",
        tenant_privacy_class="local_metadata_only",
    )
    return SemanticPageIdentity(
        inference_identity=inference_identity,
        task_family="unit_test",
        task_class="semantic_pages",
        page_kind=page_kind,
        verifier_fingerprint="verifier-a",
        behavior_contract_hash="contract-a",
        commons_space_id="local",
    )


def test_semantic_page_reuse_and_identity_mutation_miss(tmp_path: Path) -> None:
    store = SemanticComputePageStore(tmp_path)
    identity = _identity()
    put = store.put_page(identity, {"route": "local_replay", "authority": "proposal_only"}, verifier_refs=["schema"])

    lookup = store.lookup(identity)
    assert lookup["hit"] is True
    assert lookup["page"]["reuse_count"] == 1
    assert put["page"]["content_hash"] == lookup["page"]["content_hash"]

    mutated = identity.mutated(inference_identity={"tool_schema_fingerprint": "tools-b"})
    miss = store.lookup(mutated, record_reuse=False)
    assert miss["hit"] is False
    assert miss["reason"] == "identity_or_kind_miss"

    gauntlet = store.mutation_gauntlet(identity)
    assert gauntlet["passed"] is True


def test_semantic_page_invalidation_and_content_tamper_fail_closed(tmp_path: Path) -> None:
    store = SemanticComputePageStore(tmp_path)
    identity = _identity("verifier_plan")
    page = store.put_page(identity, {"required": ["schema", "pytest"]})["page"]
    page_path = tmp_path / "pages" / f"{page['page_id']}.json"

    raw = json.loads(page_path.read_text(encoding="utf-8"))
    raw["content"]["required"].append("tampered")
    page_path.write_text(json.dumps(raw), encoding="utf-8")

    miss = store.lookup(identity, record_reuse=False)
    assert miss["hit"] is False
    assert "content_hash_mismatch" in miss["validation"]["errors"]

    raw["content"] = page["content"]
    raw["content_hash"] = page["content_hash"]
    page_path.write_text(json.dumps(raw), encoding="utf-8")
    assert store.invalidate(page["page_id"])["invalidated"] is True
    invalid = store.lookup(identity, record_reuse=False)
    assert invalid["hit"] is False
    assert "page_state_invalidated" in invalid["validation"]["errors"]


def test_semantic_page_privacy_scan_blocks_private_payloads(tmp_path: Path) -> None:
    store = SemanticComputePageStore(tmp_path)
    with pytest.raises(ValueError):
        store.put_page(_identity("intermediate_summary"), {"raw_prompt": "/home/byron/private_fixture"})


def test_phase3_builder_exit_criteria(tmp_path: Path) -> None:
    receipt = build_phase3_semantic_pages(
        store=SemanticComputePageStore(tmp_path),
        ttl_seconds=60,
        reuse_repetitions=2,
    )
    assert receipt["status"] == "implemented"
    assert receipt["page_count"] == 4
    assert all(receipt["exit_criteria"].values())
