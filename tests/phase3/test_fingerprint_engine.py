from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.kernel.evidence.evidence_builder import EvidenceBuilder
from app.kernel.evidence.fingerprint_engine import build_fingerprint_bundle, compare_fingerprints
from app.kernel.evidence.fingerprint_store import FingerprintStore
from tests.phase3.test_evidence_crystallization import _promoted_run


def test_crystallization_creates_verified_fingerprint(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    evidence = EvidenceBuilder(root).crystallize(run_id)
    store = FingerprintStore(root)
    bundle = store.get(evidence["evidence_id"])
    assert bundle is not None
    assert bundle["task"]["algorithm"] == "beast.task.v1"
    assert bundle["environment"]["algorithm"] == "beast.environment.v1"
    assert store.verify(evidence["evidence_id"])["ok"] is True


def test_fingerprint_is_deterministic_for_same_inputs(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    builder = EvidenceBuilder(root)
    run, checkpoint = builder._eligible_run(run_id)
    first = build_fingerprint_bundle(root, run, checkpoint)
    second = build_fingerprint_bundle(root, run, checkpoint)
    assert first == second


def test_comparison_explains_dependency_drift(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    builder = EvidenceBuilder(root)
    run, checkpoint = builder._eligible_run(run_id)
    (root / "requirements.txt").write_text("fastapi==1\n", encoding="utf-8")
    left = build_fingerprint_bundle(root, run, checkpoint)
    (root / "requirements.txt").write_text("fastapi==2\n", encoding="utf-8")
    right = build_fingerprint_bundle(root, run, checkpoint)
    result = compare_fingerprints(left, right)
    assert result["classification"] in {"same_task_changed_context", "environment_drift"}
    assert result["checks"]["task"] is True
    assert result["checks"]["dependency_digest"] is False
    assert "dependency_digest" in result["changed_components"]


def test_fingerprint_is_immutable_per_crystal(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    evidence = EvidenceBuilder(root).crystallize(run_id)
    store = FingerprintStore(root)
    bundle = store.get(evidence["evidence_id"])
    altered = dict(bundle)
    altered["task"] = dict(bundle["task"])
    altered["task"]["digest"] = "sha256:altered"
    from app.kernel.evidence.evidence_digest import sha256_digest
    altered["bundle_digest"] = sha256_digest({k: v for k, v in altered.items() if k != "bundle_digest"})
    with pytest.raises(PermissionError):
        store.put(evidence["evidence_id"], altered)
