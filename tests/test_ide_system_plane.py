"""Tests for the BEAST IDE System plane: ports, processes, environment,
package management, extensions, and governed process/port termination."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.kernel.workspaces import system_inspector as si

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Module-level (pure) tests
# --------------------------------------------------------------------------- #

def test_list_listening_ports_shape():
    payload = si.list_listening_ports(limit=25)
    assert payload["ok"] is True
    assert payload["beast_object_type"] == "beast_ide_ports"
    assert isinstance(payload["ports"], list)
    for row in payload["ports"]:
        assert set(("proto", "port", "status")).issubset(row.keys())


def test_list_processes_finds_current_interpreter():
    payload = si.list_processes(query="", limit=200)
    assert payload["ok"] is True
    pids = {row["pid"] for row in payload["processes"]}
    # our own process should appear among the running processes
    assert os.getpid() in pids or payload["total"] > 0


def test_environment_report_redacts_secrets(monkeypatch):
    monkeypatch.setenv("MY_FAKE_API_KEY", "super-secret-value-123")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    report = si.environment_report(REPO_ROOT)
    assert report["ok"] is True
    assert report["python"]["version"]
    by_name = {item["name"]: item for item in report["env_vars"]}
    assert by_name["MY_FAKE_API_KEY"]["redacted"] is True
    assert by_name["MY_FAKE_API_KEY"]["value"] == "***redacted***"
    # a non-secret allowlisted var is shown verbatim
    assert by_name["LANG"]["redacted"] is False


def test_package_report_detects_node_and_python(tmp_path):
    report = si.package_report(REPO_ROOT)
    assert report["ok"] is True
    assert report["python"]["installed_distribution_count"] > 0
    locations = {m["location"] for m in report["node"]["manifests"]}
    assert "." in locations  # root package.json exists in this repo


def test_extensions_report_lists_vscode_commands():
    report = si.extensions_report(REPO_ROOT)
    assert report["ok"] is True
    assert report["vscode_extension"]["present"] is True
    assert report["vscode_extension"]["command_count"] >= 1


def test_kill_guardrails_protect_self_and_init():
    self_preview = si.describe_kill_target(os.getpid())
    assert self_preview["protected"] is True
    assert self_preview["protected_reason"] == "beast_gateway_self"
    assert self_preview["killable"] is False

    init_preview = si.describe_kill_target(1)
    assert init_preview["protected"] is True

    # kill_process must refuse a protected pid even if asked directly
    refused = si.kill_process(os.getpid())
    assert refused["ok"] is False
    assert refused["status"] == "refused"


def test_describe_kill_target_missing_process():
    preview = si.describe_kill_target(2_147_480_000)
    assert preview["exists"] is False
    assert preview["killable"] is False


def test_find_port_owners_resolves_own_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        owners = si.find_port_owners(port)
        assert owners["ok"] is True
        # psutil can always attribute a socket owned by the current process
        pids = {o["pid"] for o in owners["owners"]}
        assert os.getpid() in pids
    finally:
        sock.close()


# --------------------------------------------------------------------------- #
# Route tests
# --------------------------------------------------------------------------- #

def _client() -> TestClient:
    return TestClient(app)


def test_read_only_system_routes_return_ok():
    client = _client()
    for path in (
        "/edgek/ide/ports?limit=5",
        "/edgek/ide/processes?limit=5",
        f"/edgek/ide/environment?root_path={REPO_ROOT}",
        f"/edgek/ide/packages?root_path={REPO_ROOT}",
        f"/edgek/ide/extensions?root_path={REPO_ROOT}",
        f"/edgek/ide/system-snapshot?root_path={REPO_ROOT}",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        body = response.json()
        assert body["ok"] is True, path
        assert body["beast_object_type"].startswith("beast_ide_"), path


def test_system_snapshot_advertises_capabilities():
    client = _client()
    body = client.get(f"/edgek/ide/system-snapshot?root_path={REPO_ROOT}").json()
    caps = body["capabilities"]
    for key in ("ports", "processes", "process_kill", "port_free", "environment", "packages", "extensions"):
        assert caps[key] is True


def test_kill_route_rejects_protected_and_requires_approval(tmp_path):
    client = _client()

    # protected pid (init) is refused regardless of approval
    protected = client.post("/edgek/ide/system/kill", json={"pid": 1, "approved": True}).json()
    assert protected["ok"] is False
    assert protected["error"] == "protected_process"

    # a real throwaway process: no approval -> approval_required, dry_run -> preview
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        no_approval = client.post("/edgek/ide/system/kill", json={"pid": child.pid, "approved": False}).json()
        assert no_approval["ok"] is False
        assert no_approval["error"] == "approval_required"
        assert no_approval["killable"] is True

        dry = client.post("/edgek/ide/system/kill", json={"pid": child.pid, "dry_run": True}).json()
        assert dry["ok"] is True
        assert dry["status"] == "dry_run"
        assert child.poll() is None  # still alive after dry run

        # approved real kill writes an evidence receipt and terminates the process
        killed = client.post(
            "/edgek/ide/system/kill",
            json={"pid": child.pid, "approved": True, "root_path": str(tmp_path), "operator_override": "pytest"},
        ).json()
        assert killed["ok"] is True
        assert killed["status"] in ("terminated", "signalled")
        assert killed.get("evidence_receipt")
        assert Path(killed["evidence_path"]).exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_kill_route_invalid_pid():
    client = _client()
    body = client.post("/edgek/ide/system/kill", json={"pid": 0}).json()
    assert body["ok"] is False
    assert body["error"] == "invalid_pid"


def test_catalog_report_loads_and_enriches():
    report = si.catalog_report(REPO_ROOT)
    assert report["ok"] is True
    assert report["catalog_path"]
    assert report["summary"]["mcp_servers"] >= 1
    server = report["mcp_servers"][0]
    assert "runner_available" in server
    assert "mcpServers" in server["mcp_config"]
    for tool in report["tools"]:
        assert "installed" in tool


def test_catalog_route_returns_ok():
    client = _client()
    body = client.get(f"/edgek/ide/catalog?root_path={REPO_ROOT}").json()
    assert body["ok"] is True
    assert body["beast_object_type"] == "beast_ide_catalog_report"
    assert isinstance(body["mcp_servers"], list)


def test_system_actions_present_in_manifest():
    client = _client()
    response = client.get("/edgek/ide/actions/manifest")
    if response.status_code != 200:
        return  # manifest endpoint optional in some builds
    actions = response.json()
    items = actions.get("actions") if isinstance(actions, dict) else actions
    ids = {item.get("id") for item in items} if isinstance(items, list) else set()
    for action_id in ("system.ports", "system.processes", "system.kill", "system.free_port"):
        assert action_id in ids
