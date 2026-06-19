from app.cli.api import BeastApiClient


def test_sourceplan_fallback_still_carries_provider_handoff(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    monkeypatch.setenv("BEAST_WORKSPACE", str(tmp_path))

    result = BeastApiClient().build_source_patch_plan(
        "Update app.py safely",
        ["app.py"],
        provider="huggingface",
    )

    assert result.ok is True
    assert result.data["bridge_enforced"] is True
    assert result.data["provider_handoff"]["kind"] == "beast.provider_handoff.v1"
    assert result.data["provider_handoff_hash"].startswith("sha256:")
    assert result.data["provider_handoff"]["trace"]["provider_handoff_hash"] == result.data["provider_handoff_hash"]


def test_sourceplan_without_usable_files_still_builds_handoff(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_WORKSPACE", str(tmp_path))

    result = BeastApiClient().build_source_patch_plan(
        "Prepare a safe governed plan",
        ["missing.py"],
        provider="openrouter",
    )

    assert result.ok is True
    assert result.data["bridge_enforced"] is True
    assert result.data["provider_handoff"]["task"]["allowed_paths"] == ["missing.py"]
