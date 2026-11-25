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
    LATTICE_ENV,
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


def test_verified_agent_episode_forms_lattice_crystal_then_reuses_without_provider(tmp_path):
    """Catches a fake event-only promotion with no durable artifact or no-model reuse."""
    import asyncio

    from crystal_fabric_support import CountingProvider, create_assertion_run, learn_script, make_assertion_repo
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime

    key = _key(tmp_path / "keys" / "runtime.pem")
    workspace = make_assertion_repo(tmp_path / "workspace")
    env = {
        ENABLE_ENV: "1",
        KEY_ENV: str(key),
        "BEAST_CODING_CRYSTAL_AUTO_PROMOTE": "1",
        LATTICE_ENV: "1",
        "BEAST_CRYSTAL_LATTICE_LEDGER_ROOT": str(tmp_path / "lattice-ledger"),
        "BEAST_COMMONS_ROOT": str(tmp_path / "commons"),
    }

    engine, source_run_id = create_assertion_run(workspace)
    source_provider = CountingProvider(learn_script())
    source_extras = planner_runtime_extras(workspace, env=env)
    source = asyncio.run(AgentPlannerRuntime(
        engine, source_provider, max_turns=14, **source_extras,
    ).run(source_run_id))
    assert source["state"] == "completed"

    source_events = engine.store.events(source_run_id, limit=2000)
    formed = [e for e in source_events if e["event_type"] == "agent.crystal.formed"]
    assert len(formed) == 1
    formation = formed[0]["payload"]
    assert formation["status"] == "promoted"
    assert formation["source_run_id"] == source_run_id
    assert formation["heldout_successes"] == 3
    assert formation["lattice_admitted"] is True
    assert formation["registry_record_digest"].startswith("sha256:")
    assert formation["lattice_checkpoint_hash"].startswith("sha256:")
    assert formation["crystal_chain_block_hash"].startswith("sha256:")

    planner = source_extras["crystal_planner"]
    record = planner.registry.get(formation["crystal_id"])
    assert record["status"] == "promoted"
    assert record["candidate"]["source_run_id"] == source_run_id
    assert record["reuse_count"] == 0
    node = planner.lattice.node(formation["crystal_id"])
    assert node["status"] == "admitted"
    assert planner.lattice.verify()["valid"] is True

    reuse_engine, reuse_run_id = create_assertion_run(workspace)
    fail_if_called = CountingProvider()
    reuse_extras = planner_runtime_extras(workspace, env=env)
    reuse = asyncio.run(AgentPlannerRuntime(
        reuse_engine, fail_if_called, max_turns=14, **reuse_extras,
    ).run(reuse_run_id))
    assert reuse["state"] == "completed"
    assert fail_if_called.calls == 0
    reuse_events = reuse_engine.store.events(reuse_run_id, limit=2000)
    assert any(e["event_type"] == "agent.crystal.activated" for e in reuse_events)
    assert any(e["event_type"] == "agent.crystal.completed" for e in reuse_events)
    assert any(e["event_type"] == "agent.crystal.reduction_receipt" for e in reuse_events)
    assert not any(e["event_type"] == "agent.crystal.formed" for e in reuse_events)

    reused_record = reuse_extras["crystal_planner"].registry.get(formation["crystal_id"])
    assert reused_record["reuse_count"] == 1
    assert len(reuse_extras["crystal_planner"].lattice.nodes()) == 1


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
