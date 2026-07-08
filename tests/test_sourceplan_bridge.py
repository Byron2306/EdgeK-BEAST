import json

from app.cli.api import BeastApiClient
from app.kernel.adapters.provider_handoff import build_provider_handoff


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
    assert result.data["provider_handoff"]["governance"]["spec_covenant"]["covenant_hash"].startswith("sha256:")
    assert result.data["provider_handoff"]["governance"]["safety_governor"]["decision"] in {"allow", "warn", "require_approval", "sandbox/worktree_only", "block"}


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


def test_sourceplan_provider_action_ir_compiles_to_exact_operation(tmp_path):
    target = tmp_path / "app.py"
    target.write_text(
        "def value():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    client = BeastApiClient("http://offline", workspace=tmp_path)
    handoff = build_provider_handoff(
        tmp_path,
        "Update value",
        ["app.py"],
        "huggingface",
        task_name="sourceplan",
    )
    handoff_hash = handoff["trace"]["provider_handoff_hash"]
    provider_text = {
        "kind": "beast.action_intent.v1",
        "objective": "Update value",
        "provider_handoff_hash": handoff_hash,
        "actions": [
            {
                "id": "a1",
                "type": "replace_exact",
                "target": {"file_ref": "F1"},
                "intent": "Change return value only",
                "old": "return 1",
                "new": "return 2",
            }
        ],
    }

    result = client.build_source_patch_plan(
        "Update value",
        ["app.py"],
        provider="huggingface",
        provider_text=json.dumps(provider_text),
        expected_handoff_hash=handoff_hash,
        provider_handoff=handoff,
    )
    preview = client.preview_patch_plan(result.data)

    assert result.ok is True
    assert result.data["kind"] == "beast_provider_action_ir_source_patch_plan"
    assert result.data["operations"][0]["op"] == "replace_exact"
    assert result.data["operations"][0]["action_ir_id"] == "a1"
    assert "return 2" in preview.data["operations"][0]["new_text"]
    assert "def value" in preview.data["operations"][0]["new_text"]


def test_sourceplan_action_ir_rejects_non_unique_anchor(tmp_path):
    target = tmp_path / "app.py"
    target.write_text(
        "def a():\n"
        "    return 1\n\n"
        "def b():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    client = BeastApiClient("http://offline", workspace=tmp_path)
    handoff = build_provider_handoff(tmp_path, "Update value", ["app.py"], "huggingface", task_name="sourceplan")
    handoff_hash = handoff["trace"]["provider_handoff_hash"]
    provider_text = {
        "kind": "beast.action_intent.v1",
        "objective": "Update value",
        "provider_handoff_hash": handoff_hash,
        "actions": [
            {
                "id": "a1",
                "type": "replace_exact",
                "target": {"file_ref": "F1"},
                "intent": "Ambiguous replacement",
                "old": "return 1",
                "new": "return 2",
            }
        ],
    }

    result = client.build_source_patch_plan(
        "Update value",
        ["app.py"],
        provider="huggingface",
        provider_text=json.dumps(provider_text),
        expected_handoff_hash=handoff_hash,
        provider_handoff=handoff,
    )

    assert result.ok is True
    assert result.data["provider_generated"] is False
    assert "did not compile" in result.data.get("provider_fallback_reason", "")


def test_sourceplan_scorecard_surfaces_code_cortex_impact(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)

    def fake_dependents(path, limit=80):
        return {
            "ok": True,
            "adapter": "gortex",
            "results": [{"file_path": "tests/test_app.py"}],
            "receipt": {
                "adapter": "gortex",
                "method": "get_dependents",
                "ok": True,
                "fallback_used": False,
                "latency_ms": 1.2,
                "result_count": 1,
            },
        }

    monkeypatch.setattr(client, "code_cortex_dependents", fake_dependents)
    plan = {
        "kind": "beast_source_patch_plan",
        "operations": [{
            "id": "op1",
            "path": "app.py",
            "op": "replace_exact",
            "old_text": "old",
            "new_text": "new",
            "selected": True,
        }],
    }

    scorecard = client.sourceplan_scorecard(plan)

    assert scorecard.ok is True
    cortex = scorecard.data["graph_impact"]["code_cortex"]
    assert cortex["adapters"] == ["gortex"]
    assert cortex["dependent_files"] == ["tests/test_app.py"]
    assert cortex["receipts"][0]["adapter"] == "gortex"
