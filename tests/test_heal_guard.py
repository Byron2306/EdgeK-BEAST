"""beast heal: full-stack restart by default, protected services never touched, beast ide dry-run only."""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
from pathlib import Path

import pytest

from app.kernel.execution import heal_guard, heal_restart

ROOT = Path(__file__).resolve().parents[1]
UID = os.getuid()


def _facts(pid, cmd, comm="python", cgroup="0::/user.slice/user-1000.slice/user@1000.service/app.slice/x.scope", uid=UID):
    return {"pid": pid, "uid": uid, "comm": comm, "cmdline": cmd, "cgroup": cgroup}


GATEWAY = _facts(2059397, ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8101")
MCP = _facts(2060459, ".venv/bin/python bin/beast mcp-http --host 127.0.0.1 --port 8765")
GUARDIAN = _facts(
    1370363,
    ".venv/bin/python -m app.kernel.execution.socket_guardian_daemon --config /tmp/socket-guardian.yaml",
    cgroup="0::/user.slice/user-1000.slice/user@1000.service/app.slice/beast-socket-guardian.service",
)
CONSUMER = _facts(
    1370366,
    ".venv/bin/python bin/beast gateway --socket-mode guardian --guardian-service beast",
    cgroup="0::/user.slice/user-1000.slice/user@1000.service/app.slice/beast-beast-guardian-consumer.service",
)
LITELLM = _facts(830027, ".venv/bin/python .venv/bin/litellm --config deploy/generated/litellm.config.yaml --port 4000")
OLLAMA = _facts(2426, "/usr/local/bin/ollama serve", comm="ollama", cgroup="0::/system.slice/ollama.service", uid=997)
ARDA = _facts(2421, "python -m uvicorn backend.services.arda_phase4_verifier_service:app --port 8094",
              cgroup="0::/system.slice/arda-acer-reciprocal-verifier.service")
SERAPH = _facts(3001, "seraph backend worker", comm="python")
TGI_LOGS = _facts(1666459, "docker logs -f beast-tgi", comm="docker")
DOCKER_UVICORN = _facts(455885, "uvicorn server:app --port 8001", cgroup="0::/system.slice/docker-abc.scope", uid=0)
IDE = _facts(2011248, "electron --no-sandbox .../desktop-ide", comm="electron")
FOREIGN = _facts(4002, "python -m uvicorn app.main:app --port 8101", uid=0)


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
    d = dict(host="127.0.0.1", gateway_port=8101, mcp_port=8765, litellm_port=4000, nginx_port=80,
             ollama_host="127.0.0.1:11434", dry_run="false", selective="false", restart_all="false",
             kill_address_pids="false")
    d.update(kw)
    return argparse.Namespace(**d)


# -- selection (fakes only; no real signals) -------------------------------------------------------

def _discover(procs, listeners, pidfiles=(), installed=(), main_pids=None, tmp_path=None):
    root = tmp_path or Path("/tmp")
    return heal_restart.discover_targets(
        root=root,
        processes=procs,
        listeners=lambda port: listeners.get(port, []),
        facts_for=lambda pid: next((dict(p) for p in procs if p["pid"] == pid),
                                   {"pid": pid, "uid": None, "comm": "", "cmdline": "", "cgroup": ""}),
        pidfiles=list(pidfiles),
        unit_installed=lambda u: u in set(installed),
        unit_main_pid=(lambda u: (main_pids or {}).get(u)),
    )


def test_selects_beast_servers_and_excludes_protected_set(tmp_path):
    procs = [GATEWAY, MCP, GUARDIAN, CONSUMER, LITELLM, OLLAMA, ARDA, SERAPH, TGI_LOGS, DOCKER_UVICORN, IDE, FOREIGN]
    listeners = {8101: [2059397], 8765: [2060459], 8131: [1370363, 1370366], 4000: [830027]}
    out = _discover(procs, listeners, installed=list(heal_restart.LAB_UNITS),
                    main_pids={"beast-socket-guardian.service": 1370363,
                               "beast-beast-guardian-consumer.service": 1370366},
                    tmp_path=tmp_path)
    selected = {r["pid"]: r["role"] for r in out["selected"]}
    assert selected == {
        2059397: "gateway",
        2060459: "mcp_http",
        1370363: "socket_guardian",
        1370366: "gateway_guardian",
    }
    reasons = {r["pid"]: r["reason"] for r in out["reported"]}
    assert reasons[830027] == "litellm_report_only"
    assert reasons[2426] == "system_ollama"
    assert reasons[2421].startswith("protected_owner:arda") or reasons[2421] == "foreign_cgroup"
    assert reasons[3001] == "protected_owner:seraph"
    assert reasons[1666459] == "beast_tgi"
    assert 455885 in reasons  # docker / foreign
    assert 4002 in reasons    # foreign uid
    assert 2011248 not in selected  # IDE is not a server
    assert all(r["restart_via"] == "systemd" for r in out["selected"] if r["role"] in {"socket_guardian", "gateway_guardian"})
    assert all(r["restart_via"] == "nohup" for r in out["selected"] if r["role"] in {"gateway", "mcp_http"})


def test_stale_pidfiles_cleared_live_litellm_kept(tmp_path):
    dead = tmp_path / "gateway.pid"
    dead.write_text("830042\n")
    live = tmp_path / "litellm.pid"
    live.write_text("830027\n")
    procs = [LITELLM]
    out = _discover(procs, {4000: [830027]}, pidfiles=[dead, live], tmp_path=tmp_path)
    stale_paths = {r["path"] for r in out["stale_pidfiles"]}
    assert str(dead) in stale_paths
    assert str(live) not in stale_paths
    assert any(r["pid"] == 830027 and r["reason"] == "litellm_report_only" for r in out["reported"])


def test_kernel_threads_are_not_listed_in_reported(tmp_path):
    kthreadd = _facts(2, "kthreadd", comm="kthreadd", uid=0)
    out = _discover([kthreadd, GATEWAY, LITELLM, OLLAMA], {8101: [2059397], 4000: [830027]}, tmp_path=tmp_path)
    pids = {r["pid"] for r in out["reported"]}
    assert 2 not in pids
    assert 830027 in pids and 2426 in pids
    assert {r["pid"] for r in out["selected"]} == {2059397}


def test_unknown_listener_on_8101_is_reported_not_selected(tmp_path):
    unknown = _facts(7777, "python some-other-server.py --port 8101")
    out = _discover([unknown], {8101: [7777]}, tmp_path=tmp_path)
    assert out["selected"] == []
    assert any(r["pid"] == 7777 and r["reason"] == "unknown_listener" for r in out["unknown"])


def test_pid_protection_always_excludes_protected_set():
    cases = [
        (ARDA, "protected_owner:arda"),
        (SERAPH, "protected_owner:seraph"),
        (OLLAMA, "system_ollama"),
        (TGI_LOGS, "beast_tgi"),
        (LITELLM, "litellm_report_only"),
        (FOREIGN, "foreign_uid"),
        (DOCKER_UVICORN, "foreign_uid"),  # uid 0 is decided before cgroup
        (_facts(1, "init", comm="init", uid=0), "init_or_self"),
    ]
    for facts, reason in cases:
        protected, got = heal_guard.pid_protection(facts["pid"], facts=facts, mode="full")
        assert protected and got == reason, (facts["pid"], got, reason)
        # still protected in selective mode
        protected, _ = heal_guard.pid_protection(facts["pid"], facts=facts, mode="selective")
        assert protected


def test_selective_mode_protects_8101_and_8131_even_for_beast_servers():
    protected, reason = heal_guard.pid_protection(GATEWAY["pid"], port=8101, facts=GATEWAY, mode="selective")
    assert protected and reason == "protected_port:8101"
    protected, reason = heal_guard.pid_protection(GUARDIAN["pid"], port=8131, facts=GUARDIAN, mode="selective")
    assert protected and reason == "protected_port:8131"
    # full mode: same processes are not port-protected
    assert heal_guard.pid_protection(GATEWAY["pid"], port=8101, facts=GATEWAY, mode="full") == (False, "")
    assert heal_guard.pid_protection(GUARDIAN["pid"], port=8131, facts=GUARDIAN, mode="full") == (False, "")


def test_filter_killable_full_vs_selective():
    allowed, refused = heal_guard.filter_killable(
        [2059397, 830027, 2426], port=8101, mode="full",
        facts_by_pid={2059397: GATEWAY, 830027: LITELLM, 2426: OLLAMA},
    )
    assert allowed == [2059397]
    assert {r["pid"] for r in refused} == {830027, 2426}
    allowed, refused = heal_guard.filter_killable(
        [2059397], port=8101, mode="selective", facts_by_pid={2059397: GATEWAY},
    )
    assert allowed == [] and refused[0]["reason"] == "protected_port:8101"


# -- execution plan with fakes (dry_run=False but no real signals) ---------------------------------

class FakeLifecycle:
    def __init__(self):
        self.adopted = []
        self.terminated = []

    def adopt(self, pid, *, label):
        rec = {"pid": pid, "label": label}
        self.adopted.append(rec)
        return rec

    def terminate(self, handle, *, reason, grace_s, measure_vram=False):
        assert reason == "operator_request"
        self.terminated.append({"pid": handle["pid"], "grace_s": grace_s, "vram": measure_vram})
        return {"ok": True, "pid": handle["pid"], "signal_path": ["pidfd:SIGTERM"], "grace_s": grace_s}


def test_full_heal_dry_run_plans_kills_and_nohup_restarts_but_does_not_call_lifecycle(tmp_path):
    life = FakeLifecycle()
    sys_calls = []
    spawn_calls = []
    procs = [GATEWAY, MCP, GUARDIAN, CONSUMER, LITELLM]
    listeners = {8101: [2059397], 8765: [2060459], 8131: [1370363, 1370366], 4000: [830027]}
    out = heal_restart.run_full_heal(
        root=tmp_path,
        dry_run=True,
        python="/tmp/fake-python",
        beast_bin=tmp_path / "bin" / "beast",
        processes=procs,
        listeners=lambda port: listeners.get(port, []),
        facts_for=lambda pid: next(dict(p) for p in procs if p["pid"] == pid),
        pidfiles=[],
        unit_installed=lambda u: u in set(heal_restart.LAB_UNITS),
        unit_main_pid=lambda u: {"beast-socket-guardian.service": 1370363,
                                 "beast-beast-guardian-consumer.service": 1370366}.get(u),
        lifecycle_factory=lambda: life,
        systemctl_restart=lambda units: sys_calls.append(list(units)) or {"ok": True, "units": list(units)},
        spawn=lambda **k: spawn_calls.append(k) or {"ok": True, "pid": 1},
        proxy_getter=lambda url: {"status": "healthy", "providers": ["tgi"], "base_url": "http://127.0.0.1:8101/proxy"},
        mcp_poster=lambda url, payload: {"result": {"tools": []}},
        sleeper=lambda _s: None,
    )
    assert out["mode"] == "full_restart" and out["status"] == "dry_run" and out["changed"] is False
    assert life.terminated == [] and sys_calls == [] and spawn_calls == []
    pids = {r["pid"] for r in out["would_kill"]}
    assert pids == {2059397, 2060459, 1370363, 1370366}
    methods = {r["service"]: r["method"] for r in out["restarts"]}
    assert methods["gateway"] == "nohup" and methods["mcp_http"] == "nohup" and methods["lab_8131"] == "systemd"
    assert any("fireworks=no" in out["summary_table"] for _ in [0])
    assert out["health"]["before"]["proxy"]["fireworks"] is False
    assert "uvicorn app.main:app" in " ".join(out["restarts"][0]["command"])
    assert out["grace_seconds"] == 8.0


def test_full_heal_execute_uses_pidfd_for_nohup_targets_and_systemctl_for_units(tmp_path):
    life = FakeLifecycle()
    sys_calls = []
    spawn_calls = []
    unlinked = []
    stale = tmp_path / "gateway.pid"
    stale.write_text("830042\n")
    procs = [GATEWAY, MCP, GUARDIAN, CONSUMER, LITELLM]
    listeners_state = {8101: [2059397], 8765: [2060459], 8131: [1370363, 1370366], 4000: [830027]}

    def listeners(port):
        dead = {item["pid"] for item in life.terminated}
        return [pid for pid in listeners_state.get(port, []) if pid not in dead]

    def systemctl(units):
        sys_calls.append(list(units))
        for p in (8131,):
            listeners_state[p] = []
        return {"ok": True, "units": list(units)}

    def spawn(**k):
        spawn_calls.append(k)
        if "uvicorn" in k["command"]:
            listeners_state[8101] = [9991]
        if "mcp-http" in k["command"]:
            listeners_state[8765] = [9992]
        return {"ok": True, "pid": 9990}

    health_cycle = {"n": 0}

    def proxy_getter(url):
        health_cycle["n"] += 1
        providers = ["tgi"] if health_cycle["n"] < 3 else ["tgi", "fireworks"]
        return {"status": "healthy", "providers": providers, "base_url": "http://127.0.0.1:8101/proxy"}

    def mcp_poster(url, payload):
        tools = [] if health_cycle["n"] < 3 else [{}] * 69
        return {"result": {"tools": tools}}

    out = heal_restart.run_full_heal(
        root=tmp_path,
        dry_run=False,
        python="/tmp/fake-python",
        beast_bin=tmp_path / "bin" / "beast",
        processes=procs,
        listeners=listeners,
        facts_for=lambda pid: next((dict(p) for p in procs if p["pid"] == pid),
                                   {"pid": pid, "uid": None, "comm": "", "cmdline": "", "cgroup": ""}),
        pidfiles=[stale],
        unit_installed=lambda u: u in set(heal_restart.LAB_UNITS),
        unit_main_pid=lambda u: {"beast-socket-guardian.service": 1370363,
                                 "beast-beast-guardian-consumer.service": 1370366}.get(u),
        lifecycle_factory=lambda: life,
        systemctl_restart=systemctl,
        spawn=spawn,
        unlink=lambda path: unlinked.append(path) or path.unlink(missing_ok=True),
        proxy_getter=proxy_getter,
        mcp_poster=mcp_poster,
        sleeper=lambda _s: None,
    )
    assert out["status"] == "healed" and out["changed"] is True
    # systemd covers 8131 pids; pidfd is used for gateway + mcp only
    term_pids = {t["pid"] for t in life.terminated}
    assert term_pids == {2059397, 2060459}
    assert all(t["grace_s"] == 8.0 for t in life.terminated)
    assert any(set(heal_restart.LAB_UNITS) == set(c) or set(c) <= set(heal_restart.LAB_UNITS) for c in sys_calls)
    assert any("uvicorn" in c["command"] for c in spawn_calls)
    assert any("mcp-http" in c["command"] for c in spawn_calls)
    assert stale in unlinked or any(getattr(p, "name", None) == "gateway.pid" or str(p).endswith("gateway.pid") for p in unlinked)
    assert out["health"]["after"]["proxy"]["fireworks"] is True
    assert out["health"]["after"]["mcp"]["count"] == 69
    # LiteLLM was never adopted or spawned
    assert 830027 not in term_pids
    assert not any("litellm" in str(c).lower() for c in spawn_calls)


def test_pytest_refuses_real_heal_without_fakes(tmp_path):
    with pytest.raises(RuntimeError, match="refusing to run a real heal from pytest"):
        heal_restart.run_full_heal(root=tmp_path, dry_run=False, processes=[], listeners=lambda p: [],
                                   pidfiles=[], unit_installed=lambda u: False)


# -- CLI wrapper / previous selective behaviour ----------------------------------------------------

def test_default_command_heal_is_full_restart_dry_run(beast, monkeypatch, tmp_path):
    monkeypatch.setattr(beast, "stack_checks", _checks())
    # Isolate discovery from the live machine.
    monkeypatch.setattr(heal_restart, "run_full_heal", lambda **k: {
        "command": "heal", "mode": "full_restart", "status": "dry_run", "dry_run": True,
        "would_kill": [], "restarts": [], "actions": [], "reported": [], "unknown": [],
        "stale_pidfiles": [], "health": {"before": {}, "after": {}}, "changed": False,
        "summary_table": "BEAST heal  mode=full_restart  status=dry_run\n",
        "operator_commands": [],
    })
    out = beast.command_heal(_args(dry_run="true"))
    assert out["mode"] == "full_restart" and out["status"] == "dry_run"
    assert beast._calls["kill"] == [] and beast._calls["start"] == []


def test_selective_is_opt_in_and_never_kills_when_healthy(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks())
    out = beast.command_heal(_args(selective="true"))
    assert out["mode"] == "selective" and out["actions"] == [] and beast._calls["kill"] == [] and beast._calls["start"] == []


def test_unhealthy_gateway_8101_and_ollama_are_reported_not_restarted_in_selective(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(gateway={"ok": False}, ollama={"ok": False}))
    out = beast.command_heal(_args(selective="true", restart_all="true", kill_address_pids="true"))
    statuses = {a["service"]: a["status"] for a in out["actions"]}
    assert statuses["gateway"] == "protected_not_touched" and statuses["ollama"] == "protected_not_touched"
    assert "start_gateway_daemon" not in beast._calls["start"] and not any(s.startswith("spawn:ollama") for s in beast._calls["start"])
    assert all(4242 + 8101 not in pids and 4242 + 11434 not in pids for pids in beast._calls["kill"])
    assert "sudo systemctl restart ollama.service" in out["operator_commands"]


def test_selective_restarts_only_unhealthy_beast_managed(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(mcp_http={"ok": False}))
    out = beast.command_heal(_args(selective="true"))
    assert beast._calls["start"] == ["start_mcp_http_daemon"] and beast._calls["kill"] == []
    assert out["mode"] == "selective"


def test_selective_kill_address_pids_skips_protected_and_litellm(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks())
    beast.command_heal(_args(selective="true", restart_all="true", kill_address_pids="true"))
    killed = [p for pids in beast._calls["kill"] for p in pids]
    assert 4242 + 8101 not in killed
    assert 4242 + 4000 not in killed  # LiteLLM is report-only
    assert set(killed) <= {4242 + 8765}


def test_8131_protected_in_selective_even_if_configured(beast, monkeypatch):
    monkeypatch.setattr(beast, "stack_checks", _checks(mcp_http={"ok": False}))
    out = beast.command_heal(_args(selective="true", mcp_port=8131, restart_all="true", kill_address_pids="true"))
    assert any(a["service"] == "mcp_http" and a["status"] == "protected_not_touched" for a in out["actions"])
    assert "start_mcp_http_daemon" not in beast._calls["start"]


def test_nginx_on_80_generates_config_and_gives_operator_command(beast, monkeypatch):
    nginx = heal_guard.nginx_check(80, probe=lambda url: 404)
    assert nginx["listening"] and not nginx["ok"] and "sites-enabled/edgek-beast" in nginx["operator_command"]
    monkeypatch.setattr(beast, "stack_checks", _checks(nginx=nginx))
    out = beast.command_heal(_args(selective="true"))
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
    assert heal_guard.pid_protection(99999, facts={"pid": 99999, **facts}, mode="full") == (True, reason)
    assert heal_guard.pid_protection(99999, port=8101, facts={"pid": 99999, **facts}, mode="selective") == (True, reason)


def test_start_ollama_never_spawns_second_when_system_service(beast, monkeypatch):
    monkeypatch.setattr(beast, "url_ready", lambda *a, **k: False)
    out = beast.start_ollama_daemon("127.0.0.1:11434")
    assert out["status"] == "system_service_not_started" and beast._calls["start"] == []


def test_beast_ide_runs_heal_dry_run_only():
    text = (ROOT / "bin" / "beast").read_text()
    block = text[text.index("def command_ide("):text.index("def stack_checks(")]
    assert 'dry_run="true"' in block and 'dry_run="false"' not in block
    assert 'selective="true"' in block


def test_heal_cli_has_full_restart_defaults_and_selective_flag():
    text = (ROOT / "bin" / "beast").read_text()
    assert 'heal_parser.add_argument("--selective"' in text
    assert 'heal_parser.add_argument("--restart-all", default="false"' in text
    assert 'heal_parser.add_argument("--kill-address-pids", default="false"' in text
    assert 'heal_parser.add_argument("--nginx-port", type=int, default=80)' in text
    assert 'default="false"' in text[text.index("heal_parser.add_argument(\"--dry-run\""):text.index("heal_parser.add_argument(\"--selective\"")]


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


def test_is_beast_owned_server_roles():
    assert heal_restart.is_beast_owned_server(GATEWAY) == (True, "gateway")
    assert heal_restart.is_beast_owned_server(MCP) == (True, "mcp_http")
    assert heal_restart.is_beast_owned_server(GUARDIAN) == (True, "socket_guardian")
    assert heal_restart.is_beast_owned_server(CONSUMER) == (True, "gateway_guardian")
    assert heal_restart.is_beast_owned_server(LITELLM) == (False, "")
    assert heal_restart.is_beast_owned_server(IDE) == (False, "")
    assert heal_restart.is_beast_owned_server(ARDA) == (False, "")
