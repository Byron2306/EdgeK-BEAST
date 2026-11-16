from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.kernel.compute import ide_model_inventory as inv
from app.kernel.compute.ide_model_inventory import AUTO_ID, build_inventory, resolve_route


FORBIDDEN_SUBSTRINGS = (
    "sk-", "nvapi-", "Bearer ", "api_key=", "API_KEY=",
    "BEGIN PRIVATE",
)


def _assert_redacted(payload: dict) -> None:
    blob = json.dumps(payload)
    for needle in FORBIDDEN_SUBSTRINGS:
        assert needle not in blob
    # Values of secrets must never appear even if a test env sets a dummy.
    for row in payload.get("registry") or []:
        assert "key" not in {k.lower() for k in row} - {"key_env"}
        if row.get("key_env"):
            assert row["key_env"].isupper() or "_" in row["key_env"]
            assert not row["key_env"].endswith("=")


def test_inventory_starts_with_auto_and_is_redacted(monkeypatch):
    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)
    payload = build_inventory(env={"PATH": "/usr/bin"}, probe_live=False)
    assert payload["registry"][0]["id"] == AUTO_ID
    assert payload["registry"][0]["label"] == "Auto (BEAST governed)"
    assert payload["registry"][0]["governed_auto"] is True
    assert payload["default_id"] == AUTO_ID
    assert all(row["provider"] != "fireworks" for row in payload["registry"])
    assert all(row["provider"] != "nim" for row in payload["registry"])
    _assert_redacted(payload)


def test_inventory_lists_fireworks_when_key_present_but_not_the_value(monkeypatch):
    dummy = "DUMMY_FIREWORKS_VALUE_NEVER_PRINTED"
    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)
    payload = build_inventory(env={"FIREWORKS_API_KEY": dummy, "PATH": "/usr/bin"}, probe_live=False)
    fireworks = [row for row in payload["registry"] if row["provider"] == "fireworks"]
    assert fireworks, "credentialed Fireworks lanes should appear"
    assert all(row["key_env"] == "FIREWORKS_API_KEY" for row in fireworks)
    blob = json.dumps(payload)
    assert dummy not in blob
    assert "deepseek-v4p1-flash" in blob or any("deepseek" in row["model"] for row in fireworks)
    _assert_redacted(payload)


def test_resolve_auto_picks_a_candidate(monkeypatch):
    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)
    # Auto with no live locals and no keys should fail honestly, not invent a provider.
    payload, cand = resolve_route({"model": "auto", "provider": "beast", "family": "rename"},
                                  env={"PATH": "/usr/bin"}, probe_live=False)
    if payload.get("ok"):
        assert payload["resolved"]["via"] == "capability_router"
        assert payload["resolved"]["provider"] in {"ollama", "tgi"}
        assert payload["requested"]["auto"] is True
        assert "candidate" not in payload
        assert cand is not None
        assert getattr(cand, "key_env", "") or cand.provider in {"ollama", "tgi"}
    else:
        assert payload["resolved"] is None
        assert cand is None


def test_resolve_unknown_route_is_refused(monkeypatch):
    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)
    payload, cand = resolve_route({"id": "missing::not-a-model", "provider": "missing", "model": "not-a-model"},
                                  env={"PATH": "/usr/bin"}, probe_live=False)
    assert payload["ok"] is False
    assert payload["resolved"] is None
    assert cand is None

def test_blocked_providers_are_marked_not_hidden(monkeypatch):
    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)
    env = {
        "PATH": "/usr/bin",
        "SAMBANOVA_API_KEY": "DUMMY_SAMBA_NEVER_PRINTED",
        "FIREWORKS_API_KEY": "DUMMY_FW_NEVER_PRINTED",
    }
    payload = build_inventory(env=env, probe_live=False)
    samba = [row for row in payload["registry"] if row["provider"] == "sambanova"]
    fireworks = [row for row in payload["registry"] if row["provider"] == "fireworks"]
    assert samba, "blocked lanes must stay visible"
    assert all(row.get("blocked") is True for row in samba)
    assert all("402" in str(row.get("status") or "") for row in samba)
    assert "sambanova" in payload.get("blocked_providers", [])
    assert fireworks and not any(row.get("blocked") for row in fireworks)
    blob = json.dumps(payload)
    assert "DUMMY_SAMBA_NEVER_PRINTED" not in blob
    assert "DUMMY_FW_NEVER_PRINTED" not in blob
    _assert_redacted(payload)


def test_auto_skips_blocked_and_rename_alias_picks_fireworks(tmp_path, monkeypatch):
    from app.kernel.compute.capability_scorecard import CapabilityScorecard, Cell, cell_key

    monkeypatch.setattr(inv, "dotenv_value", lambda *a, **k: None)
    monkeypatch.setattr("app.kernel.compute.governed_client.dotenv_value", lambda *a, **k: None)

    card = CapabilityScorecard(tmp_path / "scorecard.json", persist=True)
    fw_model = "accounts/fireworks/models/glm-5p3-flash"
    nim_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
    # Strong family evidence for Fireworks rename; NIM only has a tiny aggregate win.
    card.cells[cell_key("fireworks", fw_model, "refactor-rename-symbol", "cloud")] = Cell(
        attempts=8.0, passes=8.0, json_valid=8.0, accepted=8.0, tokens_accepted=800.0,
        latency_ms_ewma=2700.0, raw_attempts=8, last_ts=10.0,
    )
    card.cells[cell_key("nim", nim_model, "*", "cloud")] = Cell(
        attempts=1.0, passes=1.0, json_valid=1.0, accepted=1.0, tokens_accepted=18.0,
        latency_ms_ewma=1100.0, raw_attempts=1, last_ts=10.0,
    )
    card.save()
    monkeypatch.setattr(inv, "_load_scorecard", lambda path=None: CapabilityScorecard(card.path))

    env = {
        "PATH": "/usr/bin",
        "FIREWORKS_API_KEY": "DUMMY_FW_NEVER_PRINTED",
        "NVIDIA_API_KEY": "DUMMY_NIM_NEVER_PRINTED",
        "SAMBANOVA_API_KEY": "DUMMY_SAMBA_NEVER_PRINTED",
    }
    payload, cand = resolve_route(
        {"model": "auto", "provider": "beast", "family": "rename"},
        env=env, probe_live=False,
    )
    assert payload["ok"] is True
    assert payload["requested"]["family"] == "refactor-rename-symbol"
    assert payload["resolved"]["provider"] == "fireworks"
    assert payload["resolved"]["model"] == fw_model
    assert payload["resolved"]["blocked"] is False
    assert cand is not None and cand.provider == "fireworks"
    assert "DUMMY_FW_NEVER_PRINTED" not in json.dumps(payload)
