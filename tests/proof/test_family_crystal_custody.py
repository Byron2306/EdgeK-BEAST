import sqlite3

import pytest

from scripts.proof.backup_family_crystal_registry import backup_registry


def test_missing_expected_crystal_fails_without_committing_backup(tmp_path):
    source = tmp_path / "registry.sqlite3"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE family_crystals (crystal_id TEXT)")
    before = source.read_bytes()
    with pytest.raises(LookupError):
        backup_registry(source, tmp_path / "archive", {"family-crystal:missing": None})
    assert source.read_bytes() == before
    assert not (tmp_path / "archive").exists()


def test_registry_backup_keeps_full_payload_and_negative_history(tmp_path):
    from app.kernel.compute import family_crystals as fc

    db = tmp_path / "live.sqlite3"
    live = fc.FamilyRegistry(db)
    family = "fix-config-constant"
    crystal = fc.FamilyCrystal("", family, fc.recipe([family]), fc.catalog_digest(),
                              "fixture-run", "sha256:" + "a" * 64).sealed()
    live.add_candidate(crystal)
    live.record_negative(family, kind="test-negative", crystal_id=crystal.crystal_id)
    before = db.read_bytes()
    folder = tmp_path / "verified"
    result = backup_registry(db, folder, {})
    assert result["negative_receipts"] == 1
    assert result["crystals"][0]["status"] == "candidate"
    restored = fc.FamilyRegistry(folder / "family_crystals.sqlite3")
    assert restored.get(crystal.crystal_id)["crystal_object"] == crystal
    assert db.read_bytes() == before
