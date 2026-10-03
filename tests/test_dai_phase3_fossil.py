import json
import shutil
from pathlib import Path

import pytest

from app.kernel.dai.phase3_fossil import (
    PHASE2_EXPECTED_SUMMARY_DIGEST,
    PHASE2_RELEASE_ID,
    Phase3FossilError,
    load_phase2_exact_fossil,
    phase3_fossil_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
PHASE2_BUNDLE = ROOT / "artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04"
PHASE2_ZIP = ROOT / "artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04.zip"


def test_phase3_loads_phase2_exact_fossil_with_authority_boundary():
    fossil = load_phase2_exact_fossil(PHASE2_BUNDLE, zip_path=PHASE2_ZIP)

    assert fossil.release_id == PHASE2_RELEASE_ID
    assert fossil.summary_digest == PHASE2_EXPECTED_SUMMARY_DIGEST
    assert fossil.sensorium_authority_level == "exact_phase2_cgroup_kernel_witness"
    assert fossil.correlated_socket_bind_event_count == 3
    assert fossil.provider_calls_used == 0
    assert fossil.production_authority_allowed is False
    assert fossil.maximum_authority == "frozen_capability_reference_only"
    assert fossil.zip_digest.startswith("sha256:")


def test_phase3_fossil_receipt_allows_composition_not_execution():
    fossil = load_phase2_exact_fossil(PHASE2_BUNDLE, zip_path=PHASE2_ZIP)
    receipt = phase3_fossil_receipt(fossil)

    assert receipt["composition_use_allowed"] is True
    assert receipt["execution_authority_allowed"] is False
    assert receipt["provider_calls_used"] == 0
    assert receipt["receipt_digest"].startswith("sha256:")


def test_phase3_rejects_tampered_phase2_summary(tmp_path):
    copied = tmp_path / PHASE2_BUNDLE.name
    shutil.copytree(PHASE2_BUNDLE, copied)
    summary_path = copied / "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring/phase2_x2_exact_ring_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["green"] = False
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(Phase3FossilError, match="file manifest digest mismatch"):
        load_phase2_exact_fossil(copied)


def test_phase3_rejects_stale_failure_diagnostic(tmp_path):
    copied = tmp_path / PHASE2_BUNDLE.name
    shutil.copytree(PHASE2_BUNDLE, copied)
    failure = copied / "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring/x2_exact_ring_failure.json"
    failure.write_text('{"stale":"failure"}\n', encoding="utf-8")

    with pytest.raises(Phase3FossilError, match="stale failure"):
        load_phase2_exact_fossil(copied)
