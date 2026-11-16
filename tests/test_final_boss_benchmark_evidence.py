import json
from pathlib import Path

from app.kernel.compute.benchmark_evidence import RELATIVE_RECEIPT, final_boss_evidence


ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_benchmark_is_visible_as_synthetic_evidence():
    result = final_boss_evidence(ROOT)
    assert result["state"] == "VERIFIED_SYNTHETIC"
    receipt = result["receipts"][0]
    assert receipt["evidence"]["receipt_hash_valid"] is True
    assert receipt["evidence"]["production_capability_promoted"] is False
    assert receipt["evidence"]["raw_teacher_patch_count"] == 0


def test_tampered_benchmark_loses_verified_status(tmp_path):
    target = tmp_path / RELATIVE_RECEIPT
    target.parent.mkdir(parents=True)
    source = json.loads((ROOT / RELATIVE_RECEIPT).read_text())
    source["metrics"]["integration_tests_passed"] = False
    target.write_text(json.dumps(source))
    result = final_boss_evidence(tmp_path)
    assert result["state"] == "UNVERIFIED"
    assert result["receipts"][0]["evidence"]["receipt_hash_valid"] is False
