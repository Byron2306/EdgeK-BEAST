"""Production wiring for coding crystals: default-off flag, existing ARDA runtime key by path, durable .beast registry."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.kernel.compute.coding_crystal_runtime import (  # noqa: E402
    DEFAULT_KEY_PATH,
    ENABLE_ENV,
    KEY_ENV,
    crystal_runtime_status,
    learn_from_run,
    planner_runtime_extras,
)


def _key(path: Path, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(path, mode)
    return path


def test_default_key_is_the_existing_arda_runtime_key():
    assert Path("~/.local/state/beast/compute_plane/authority/arda-runtime-ed25519.pem").expanduser() == DEFAULT_KEY_PATH


def test_crystals_are_off_by_default(tmp_path):
    extras = planner_runtime_extras(tmp_path, env={})
    assert extras == {}
    status = crystal_runtime_status(tmp_path, env={})
    assert status["enabled"] is False and status["reason"] == "disabled"
    assert not (tmp_path / ".beast" / "crystals").exists()


def test_enabled_with_private_key_builds_planner_and_durable_paths(tmp_path):
    key = _key(tmp_path / "keys" / "runtime.pem")
    env = {ENABLE_ENV: "1", KEY_ENV: str(key)}
    extras = planner_runtime_extras(tmp_path / "ws", env=env)
    planner = extras["crystal_planner"]
    assert planner.registry.path == tmp_path / "ws" / ".beast" / "crystals" / "coding_crystals.sqlite3"
    assert planner.ledger.path == tmp_path / "ws" / ".beast" / "crystals" / "coding_crystal_capabilities.sqlite3"
    assert extras["envelope_store"].path == tmp_path / "ws" / ".beast" / "sensorium" / "episode_envelopes.sqlite3"
    assert planner.authority.key_id.startswith("arda-runtime-ed25519:")
    status = crystal_runtime_status(tmp_path / "ws", env=env)
    assert status["enabled"] is True and status["reason"] == "ready"
    assert "PRIVATE" not in repr(status) and key.read_bytes().decode() not in repr(status)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


@pytest.mark.parametrize("mode", [0o644, 0o640])
def test_open_key_permissions_fail_closed_without_chmod(tmp_path, mode):
    key = _key(tmp_path / "keys" / "runtime.pem", mode)
    env = {ENABLE_ENV: "true", KEY_ENV: str(key)}
    assert planner_runtime_extras(tmp_path / "ws", env=env) == {}
    assert crystal_runtime_status(tmp_path / "ws", env=env)["reason"] == "key_permissions_too_open"
    assert stat.S_IMODE(key.stat().st_mode) == mode


def test_missing_or_non_ed25519_key_fails_closed(tmp_path):
    assert crystal_runtime_status(tmp_path, env={ENABLE_ENV: "1", KEY_ENV: str(tmp_path / "nope.pem")})["reason"] == "key_missing"
    bogus = tmp_path / "bogus.pem"
    bogus.write_text("not a key")
    os.chmod(bogus, 0o600)
    assert crystal_runtime_status(tmp_path, env={ENABLE_ENV: "1", KEY_ENV: str(bogus)})["reason"] == "key_invalid"


def test_learn_from_run_extracts_replays_three_variants_and_promotes(tmp_path):
    from crystal_fabric_support import run_learn

    key = _key(tmp_path / "keys" / "runtime.pem")
    env = {ENABLE_ENV: "1", KEY_ENV: str(key)}
    workspace = tmp_path / "ws"
    learned = run_learn(workspace, workspace / ".beast" / "sensorium" / "episode_envelopes.sqlite3")
    # PGEC 2.4 Promotion Sovereignty: a passing held-out replay alone does not promote in production.
    pending = learn_from_run(workspace, learned["run_id"], env=env, scratch=tmp_path / "scratch")
    assert pending["status"] == "verified_awaiting_operator_promotion" and pending["receipt"]["successes"] == 3
    planner = planner_runtime_extras(workspace, env=env)["crystal_planner"]
    assert planner.registry.active_for_family("fix-failing-assertion") is None
    report = learn_from_run(workspace, learned["run_id"], env=env, scratch=tmp_path / "scratch2", approved_by="byron")
    assert report["status"] == "promoted" and report["approved_by"] == "byron"
    assert report["receipt"]["successes"] == 3 and report["receipt"]["promoted"] is True
    planner = planner_runtime_extras(workspace, env=env)["crystal_planner"]
    assert planner.registry.active_for_family("fix-failing-assertion").crystal_id == report["crystal_id"]
    kinds = [e["kind"] for e in planner.economy.ledger.entries()]
    assert kinds.count("reproduction") == 6 and all(e["units"] == 0 for e in planner.economy.ledger.entries())


def test_learn_from_run_refuses_when_disabled(tmp_path):
    with pytest.raises(PermissionError):
        learn_from_run(tmp_path, "run-x", env={}, scratch=tmp_path / "scratch")


@pytest.mark.parametrize("module_name", ["app.routes.agent_runs", "app.routes.ide_routes.agent_runs"])
def test_planner_routes_pass_crystal_extras_to_runtime(monkeypatch, tmp_path, module_name):
    import asyncio
    import importlib

    from app.kernel.agents.run_engine import AgentRunEngine

    module = importlib.import_module(module_name)
    captured: dict = {}
    sentinel = object()

    class _Runtime:
        def __init__(self, engine, provider, **kwargs):
            captured.update(kwargs)

        async def run(self, run_id):
            return {}

    monkeypatch.setattr(module, "AgentPlannerRuntime", _Runtime)
    monkeypatch.setattr(module, "planner_runtime_extras", lambda root: {"crystal_planner": sentinel})
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(session_id="s", objective="o", mode="analysis", provider="simulated", model="m")["run_id"]
    asyncio.run(module._execute_planner_run(tmp_path, run_id, base_url="http://127.0.0.1:9", scripted_decisions=[]))
    assert captured.get("crystal_planner") is sentinel


def test_cli_status_reports_disabled_without_secrets(tmp_path):
    import json
    import subprocess

    env = {k: v for k, v in os.environ.items() if k not in {ENABLE_ENV, KEY_ENV}}
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / "scripts" / "coding_crystals.py"), "status", "--workspace", str(tmp_path)],
                         cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    status = json.loads(out.stdout)
    assert status["enabled"] is False and status["reason"] == "disabled"
