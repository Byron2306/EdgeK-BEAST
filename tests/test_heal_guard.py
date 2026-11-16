"""beast heal: selective by default, protected services never touched, beast ide dry-run only."""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
from pathlib import Path

import pytest

from app.kernel.execution import heal_guard

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def beast(monkeypatch, tmp_path):
    loader = importlib.machinery.SourceFileLoader("beast_cli_heal_test", str(ROOT / "bin" / "beast"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    calls = {"kill": [], "stop": [], "start": [], "nginx": []}
    monkeypatch.setattr(mod, "run_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "kill_pids", lambda pids, **k: calls["kill"].append(list(pids)) or {"pids": pids})
    monkeypatch.setattr(mod, "stop_managed_process", lambda pf, svc, **k: calls["stop"].append(svc) or {"service": svc, "status": "stopped"})
    for name in ("start_litellm_daemon", "start_mcp_http_daemon", "start_gateway_daemon"):
        monkeypatch.setattr(mod, name, (lambda n: (lambda *a, **k: calls["start"].append(n) or {"service": n, "status": "started"}))(name))
    monkeypatch.setattr(mod, "spawn_daemon", lambda *a, **k: calls["start"].append("spawn:" + a[0]) or {"status": "started"})
    monkeypatch.setattr(mod, "ensure_nginx", lambda port, apply=True: calls["nginx"].append((port, apply)) or {"service": "nginx", "status": "generated_only"})
    monkeypatch.setattr(mod, "listening_pids_on_port", lambda port: [4242 + port])
    monkeypatch.setattr(heal_guard, "ollama_is_system_service", lambda: {"system": True, "unit_state": "active", "unit_files": ["/etc/systemd/system/ollama.service"],
                                                                         "foreign_pids": [2426], "operator_command": "sudo systemctl restart ollama.service"})
    monkeypatch.setattr(heal_guard, "process_facts", lambda pid: {"pid": pid, "uid": os.getuid(), "comm": "python", "cmdline": "python x", "cgroup": "0::/user.slice/app.slice"})
    mod._calls = calls
    return mod


def _checks(**bad):
    base = {k: {"ok": True} for k in ("gateway", "proxy", "mcp_gateway", "mcp_http", "litellm", "ollama")}
    base["nginx"] = {"ok": True, "listening": True}
    for k, v in bad.items():
        base[k] = v
    return lambda *a, **k: dict(base)


def _args(**kw):
    d = dict(host="127.0.0.1", gateway_port=8101, mcp_port=8765, litellm_port=4000, nginx_port=80, ollama_host="127.0.0.1:11434")
    d.update(kw)
    return argparse.Namespace(**d)


def test_default_is_selective_and_never_kills(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks())
    out = beast.command_heal(_args())
    assert out["mode"] == "selective" and out["actions"] == [] and beast._calls["kill"] == [] and beast._calls["start"] == []


def test_unhealthy_gateway_8101_and_ollama_are_reported_not_restarted(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(gateway={"ok": False}, ollama={"ok": False}))
    out = beast.command_heal(_args(restart_all="true", kill_address_pids="true"))
    statuses = {a["service"]: a["status"] for a in out["actions"]}
    assert statuses["gateway"] == "protected_not_touched" and statuses["ollama"] == "protected_not_touched"
    assert "start_gateway_daemon" not in beast._calls["start"] and not any(s.startswith("spawn:ollama") for s in beast._calls["start"])
    assert all(4242 + 8101 not in pids and 4242 + 11434 not in pids for pids in beast._calls["kill"])
    assert "sudo systemctl restart ollama.service" in out["operator_commands"]


def test_selective_restarts_only_unhealthy_beast_managed(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(mcp_http={"ok": False}))
    out = beast.command_heal(_args())
    assert beast._calls["start"] == ["start_mcp_http_daemon"] and beast._calls["kill"] == []
    assert out["mode"] == "selective"


def test_explicit_full_restart_kills_only_unprotected(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks())
    beast.command_heal(_args(restart_all="true", kill_address_pids="true"))
    killed = [p for pids in beast._calls["kill"] for p in pids]
    assert 4242 + 8101 not in killed and set(killed) <= {4242 + 4000, 4242 + 8765}


def test_8131_protected_even_if_configured(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(mcp_http={"ok": False}))
    out = beast.command_heal(_args(mcp_port=8131, restart_all="true", kill_address_pids="true"))
    assert any(a["service"] == "mcp_http" and a["status"] == "protected_not_touched" for a in out["actions"])
    assert "start_mcp_http_daemon" not in beast._calls["start"]


def test_nginx_on_80_generates_config_and_gives_operator_command(beast, monkeypatch):
    nginx = heal_guard.nginx_check(80, probe=lambda url: 404)
    assert nginx["listening"] and not nginx["ok"] and "sites-enabled/edgek-beast" in nginx["operator_command"]
    monkeypatch.setattr(beast, "stack_checks", _checks(nginx=nginx))
    out = beast.command_heal(_args())
    assert beast._calls["nginx"] == [(80, False)]  # never reloads system nginx
    assert any("nginx -t" in c for c in out["operator_commands"])


@pytest.mark.parametrize("facts,reason", [
    ({"uid": 0, "comm": "python", "cmdline": "", "cgroup": ""}, "foreign_uid"),
    ({"uid": None, "comm": "arda-ring0", "cmdline": "", "cgroup": ""}, "protected_owner:arda"),
    ({"uid": None, "comm": "python", "cmdline": "seraph backend", "cgroup": ""}, "protected_owner:seraph"),
    ({"uid": None, "comm": "ollama", "cmdline": "ollama serve", "cgroup": ""}, "system_ollama"),
    ({"uid": None, "comm": "x", "cmdline": "", "cgroup": "0::/system.slice/docker-abc.scope"}, "foreign_cgroup"),
])
def test_pid_protection(facts, reason):
    assert heal_guard.pid_protection(99999, facts={"pid": 99999, **facts}) == (True, reason)
    assert heal_guard.pid_protection(99999, port=8101, facts={"pid": 99999, **facts}) == (True, "protected_port:8101")


def test_start_ollama_never_spawns_second_when_system_service(beast, monkeypatch):
    monkeypatch.setattr(beast, "url_ready", lambda *a, **k: False)
    out = beast.start_ollama_daemon("127.0.0.1:11434")
    assert out["status"] == "system_service_not_started" and beast._calls["start"] == []


def test_beast_ide_runs_heal_dry_run_only():
    text = (ROOT / "bin" / "beast").read_text()
    block = text[text.index("def command_ide("):text.index("def stack_checks(")]
    assert 'dry_run="true"' in block and 'dry_run="false"' not in block


def test_heal_cli_defaults_are_non_destructive():
    text = (ROOT / "bin" / "beast").read_text()
    assert 'heal_parser.add_argument("--restart-all", default="false"' in text
    assert 'heal_parser.add_argument("--kill-address-pids", default="false"' in text
    assert 'heal_parser.add_argument("--nginx-port", type=int, default=80)' in text


def test_proxy_health_advertises_serving_address():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.proxy.server import proxy_router

    app = FastAPI()
    app.include_router(proxy_router, prefix="/proxy")
    body = TestClient(app, base_url="http://127.0.0.1:8101").get("/proxy/health").json()
    assert body["base_url"] == "http://127.0.0.1:8101/proxy"


def test_generated_nginx_has_health_and_proxy_routes():
    from app.kernel.deployment.deployment import DeploymentManager
    from app.kernel.governance.reason import reasoner

    conf = DeploymentManager(reasoner.policies).generate_nginx_config(listen_port=80, server_name="localhost 127.0.0.1")
    assert "listen 80;" in conf and "location = /health" in conf and "location /proxy/" in conf
