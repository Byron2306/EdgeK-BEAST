#!/usr/bin/env python3
"""Verify Phase 2B AgentRun execution ownership and replay migration."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import asyncio
import httpx
from fastapi import FastAPI


class DummyCodeCortex:
    def build_snapshot(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "dummy"}

    def related_context(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def context_for(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def get_editing_context(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"results": []}

    def get_file_summary(self, _root: Path, path: str) -> dict[str, Any]:
        return {
            "ok": True,
            "summary": {
                "path": path,
                "language": "python",
                "symbols": [{"name": "example", "kind": "function", "line": 1, "end_line": 2}],
                "imports": [],
                "routes": [],
            },
        }

    def get_dependents(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"results": []}


async def wait_for_state(client: httpx.AsyncClient, root: Path, run_id: str, states: set[str], timeout: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = (await client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(root)})).json()["run"]
        if str(last.get("state")) in states:
            return last
        await asyncio.sleep(0.05)
    raise RuntimeError(f"run did not reach {states}; last={last}")


async def main_async() -> int:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    from app.routes.ide import build_ide_router

    checks: dict[str, bool] = {}
    checks["contract_v2_present"] = (repo / "contracts/agent-run-contract.v2.yaml").exists()
    checks["worker_module_present"] = (repo / "app/kernel/agents/run_worker.py").exists()

    routes_source = (repo / "app/routes/ide_routes/agent_runs.py").read_text(encoding="utf-8")
    stream_source = (repo / "app/routes/ide_routes/agent_run_stream.py").read_text(encoding="utf-8")
    renderer_source = (repo / "desktop-ide/renderer/js/ai/agent-client.js").read_text(encoding="utf-8")
    gateway_source = (repo / "desktop-ide/main/gateway-event-stream-host.js").read_text(encoding="utf-8")
    transport_source = (repo / "desktop-ide/renderer/js/ai/beast-ai-transport.js").read_text(encoding="utf-8")
    store_source = (repo / "desktop-ide/renderer/js/ai/agent-store.js").read_text(encoding="utf-8")

    checks["post_launch_path"] = "launch:true" in renderer_source and "BeastRuntime.request('/edgek/agent-runs'" in renderer_source
    checks["renderer_subscribes_by_run_id"] = "durableRunEventUrl(durableRunId, 0)" in renderer_source
    checks["prompt_not_in_renderer_sse_query"] = "/agent-sessions/${encodeURIComponent(sessionId)}/run-events?" not in renderer_source
    checks["internal_worker_adapter"] = "httpx.ASGITransport" in routes_source and "AGENT_RUN_WORKERS.launch" in routes_source
    checks["resume_relaunches"] = "execution = _launch(request.app, root, run_id)" in routes_source
    checks["legacy_projection"] = 'projection: str = Query(default="canonical"' in routes_source
    checks["approval_wait_is_durable"] = "waiting for durable operator approval" in stream_source and "time.monotonic() + 4.0" not in stream_source
    checks["gateway_forwards_event_id"] = "lastEventId" in gateway_source and "field === 'id'" in gateway_source
    checks["renderer_persists_cursor"] = "activeRunSequence" in store_source and "reconnectActiveRun" in renderer_source
    checks["disconnect_preserves_run_identity"] = "Run continues in backend" in renderer_source and "status:'interrupted'" in renderer_source
    checks["transport_forwards_event_id"] = "lastEventId:String(message.lastEventId || '')" in transport_source

    with tempfile.TemporaryDirectory(prefix="beast-phase2b-") as raw:
        root = Path(raw)
        app = FastAPI()
        app.include_router(build_ide_router(root, code_cortex_router=DummyCodeCortex()))
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://beast.test", timeout=httpx.Timeout(None)) as client:
            session_response = await client.post("/edgek/ide/agent-sessions/create", json={
                "root_path": str(root),
                "objective": "Explain the workspace",
                "mode": "analysis",
            })
            session = session_response.json()["session"]
            created = await client.post("/edgek/agent-runs", json={
                "root_path": str(root),
                "session_id": session["session_id"],
                "objective": "Explain the workspace",
                "mode": "analysis",
                "launch": True,
                "request": {
                    "transport": "durable_agent_run_v2",
                    "prompt": "Explain the workspace",
                    "simulate": True,
                    "approval_timeout_seconds": 30,
                },
            })
            checks["launch_response_ok"] = created.status_code == 200 and bool(created.json().get("execution", {}).get("active"))
            run_id = str(created.json().get("run", {}).get("run_id") or "")
            final = await wait_for_state(client, root, run_id, {"completed"})
            checks["worker_reaches_terminal"] = final.get("state") == "completed" and not final.get("execution", {}).get("active")

            events = (await client.get(f"/edgek/agent-runs/{run_id}/events", params={"root_path": str(root)})).json()["events"]
            types = [event["event_type"] for event in events]
            checks["worker_event_recorded"] = "agent.run.worker.started" in types
            checks["legacy_events_recorded"] = "agent.run.started" in types and "agent.run.completed" in types

            async with client.stream("GET", f"/edgek/agent-runs/{run_id}/events", params={
                "root_path": str(root),
                "after": 0,
                "follow": "true",
                "projection": "legacy",
            }) as response:
                replay_parts = []
                async for chunk in response.aiter_text():
                    replay_parts.append(chunk)
                replay = "".join(replay_parts)
            checks["legacy_replay_works"] = response.status_code == 200 and "event: agent_run_started" in replay and "event: agent_run_done" in replay and "id: " in replay

    result = {
        "phase": "2B",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(1 for value in checks.values() if value),
        "total": len(checks),
    }
    output = repo / "build/PHASE2B_STATUS.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if output.exists():
        try:
            loaded = json.loads(output.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    if "summary" in existing or "verification" in existing:
        existing["status"] = result["status"]
        existing.setdefault("verification", {})["phase2b_execution"] = {
            "passed": result["passed"],
            "total": result["total"],
        }
        existing["contract_checks"] = checks
        output.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    else:
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main_async())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
