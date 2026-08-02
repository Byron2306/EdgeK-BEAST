from pathlib import Path

import pytest

from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionError, CrystalExecutionRequest, ground_crystal_ir


def ir_payload(path: str = "target.py"):
    return {
        "version": "crystal.ir.v1",
        "mission": {"objective": "bounded return repair"},
        "target": {"file": path, "symbol": "value"},
        "observed_failure": {"class": "wrong_return"},
        "required_transform": {"pipeline": ["replace_expression"]},
        "authority": {"writable_files": [path], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid", "target_tests_pass"],
        "rollback": {"required": True},
    }


def request(tmp_path: Path, *commands: tuple[str, ...]) -> CrystalExecutionRequest:
    return CrystalExecutionRequest(ir_payload(), "return 1", "return 2", "approval-1", "task-1", str(tmp_path), commands)


def test_crystal_execution_preflights_applies_and_receipts(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("def value():\n    return 1\n")
    receipt = CrystalExecutionEngine().execute(request(tmp_path, ("python", "-c", "import target")))
    assert receipt["status"] == "verified"
    assert receipt["rollback_performed"] is False
    assert "return 2" in target.read_text()
    assert receipt["receipt_digest"].startswith("sha256:")


def test_crystal_execution_rolls_back_failed_verification(tmp_path):
    target = tmp_path / "target.py"
    original = "def value():\n    return 1\n"
    target.write_text(original)
    with pytest.raises(CrystalExecutionError) as exc:
        CrystalExecutionEngine().execute(request(tmp_path, ("python", "-c", "raise SystemExit(1)")))
    assert '"status": "rolled_back"' in str(exc.value)
    assert target.read_text() == original


def test_crystal_execution_rejects_missing_approval_before_mutation(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("def value():\n    return 1\n")
    req = request(tmp_path, ("python", "-c", "import target"))
    req = CrystalExecutionRequest(req.crystal_ir, req.old, req.new, "", req.worktree_task_id, req.worktree_root, req.verification_commands)
    with pytest.raises(CrystalExecutionError, match="approval"):
        CrystalExecutionEngine().execute(req)
    assert target.read_text().endswith("return 1\n")


def test_crystal_grounding_returns_exact_symbol_span_and_fingerprint(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 9\n\ndef value():\n    return 1\n")
    grounded = ground_crystal_ir(ir_payload(), str(tmp_path))
    assert grounded.old == "def value():\n    return 1\n"
    assert grounded.file_sha256.startswith("sha256:")
