import pytest

from scripts.proof import run_stage7b_receiver as lab


def test_cold_patch_requires_exact_safe_target_line(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("LIMIT = 3\n\ndef limit():\n    return LIMIT\n")
    lab.apply_edit(target, {"old_text": "LIMIT = 3", "new_text": "LIMIT = 5"})
    assert target.read_text().startswith("LIMIT = 5\n")
    for new in ("LIMIT = __import__('os').getpid()", "OTHER = 6", "LIMIT = 5\nraise Exception()"):
        with pytest.raises(ValueError):
            lab.apply_edit(target, {"old_text": "LIMIT = 5", "new_text": new})
    assert target.read_text().startswith("LIMIT = 5\n")


def test_receiver_rejects_bytes_not_matching_local_pin():
    with pytest.raises(PermissionError, match="pin"):
        lab.load_artifact(b'{}', "sha256:" + "0" * 64, "sha256:" + "1" * 64)
