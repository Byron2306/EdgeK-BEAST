from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI
import uvicorn

from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.routes.ide import build_ide_router


class DummyCodeCortex:
    def build_snapshot(self, *_args, **_kwargs):
        return {"status": "dummy"}

    def related_context(self, *_args, **_kwargs):
        return []

    def context_for(self, *_args, **_kwargs):
        return []


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_live_desktop_renderer_creates_backend_agent_session(tmp_path: Path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    app = FastAPI()
    app.include_router(build_ide_router(tmp_path, code_cortex_router=DummyCodeCortex()))
    port = _port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "temporary BEAST gateway did not start"

    repo = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env.update({
        "BEAST_PHASE2_GATEWAY_URL": f"http://127.0.0.1:{port}",
        "BEAST_PHASE2_WORKSPACE": str(tmp_path),
        "BEAST_PHASE2_AGENT_CLIENT": str(repo / "desktop-ide" / "renderer" / "js" / "ai" / "agent-client.js"),
    })
    try:
        completed = subprocess.run(
            ["node", str(repo / "tests" / "phase2" / "desktop_agent_ingress_harness.js")],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    receipt = json.loads(completed.stdout.strip().splitlines()[-1])
    assert receipt["ok"] is True
    assert receipt["request_path"] == "/edgek/ide/agent-sessions/create"
    session = AgentSessionStore(tmp_path).get(receipt["session_id"])
    assert session["ok"] is True
    stored = session["session"]
    assert stored["objective"] == "Phase 2 desktop ingress acceptance"
    assert stored["mode"] == "analysis"
    assert stored["provider"] == "phase2-provider"
    assert stored["model"] == "phase2-model"
    assert stored["files"] == ["sample.py"]

    output = Path(os.environ.get("BEAST_PHASE2_DESKTOP_RECEIPT", "/tmp/BEAST_PHASE2_DESKTOP_INGRESS.json"))
    output.write_text(json.dumps({
        **receipt,
        "backend_receipt": {
            "session_id": stored["session_id"],
            "objective": stored["objective"],
            "mode": stored["mode"],
            "provider": stored["provider"],
            "model": stored["model"],
            "files": stored["files"],
        },
        "edge": "desktop_renderer_to_production_ide_router",
        "verified": True,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
