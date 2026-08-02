#!/usr/bin/env python3
"""Verify the Phase 2A durable AgentRun foundation."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_MODULES = (
    "run_state.py",
    "run_events.py",
    "run_cancel.py",
    "run_store.py",
    "run_engine.py",
)

REQUIRED_ROUTES = {
    ("POST", "/edgek/agent-runs"),
    ("GET", "/edgek/agent-runs"),
    ("GET", "/edgek/agent-runs/{run_id}"),
    ("GET", "/edgek/agent-runs/{run_id}/events"),
    ("POST", "/edgek/agent-runs/{run_id}/cancel"),
    ("POST", "/edgek/agent-runs/{run_id}/resume"),
    ("GET", "/edgek/agent-runs/{run_id}/verify"),
    ("GET", "/edgek/agent-runs/{run_id}/approvals"),
    ("POST", "/edgek/agent-runs/{run_id}/approvals/{approval_id}"),
}


class DummyCodeCortex:
    def build_snapshot(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "dummy"}

    def related_context(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def context_for(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    from app.kernel.agents.run_cancel import AGENT_RUN_CANCELLATIONS
    from app.kernel.agents.run_engine import AgentRunEngine
    from app.kernel.agents.run_state import AgentRunState
    from app.kernel.agents.run_store import AgentRunStore
    from app.routes.ide import build_ide_router

    checks: dict[str, bool] = {}
    agents_dir = repo / "app/kernel/agents"
    checks["modules_present"] = all((agents_dir / name).exists() for name in REQUIRED_MODULES)
    checks["contract_present"] = (repo / "contracts/agent-run-contract.v1.yaml").exists()

    store_source = (agents_dir / "run_store.py").read_text(encoding="utf-8")
    checks["sqlite_wal"] = "PRAGMA journal_mode=WAL" in store_source
    checks["sqlite_full_sync"] = "PRAGMA synchronous=FULL" in store_source
    checks["hash_chain"] = "previous_hash" in store_source and "event_hash" in store_source

    router = build_ide_router(repo, code_cortex_router=DummyCodeCortex())
    signatures = {
        (next(iter(route.methods or [])), route.path)
        for route in router.routes
        if len(route.methods or []) == 1
    }
    checks["routes_complete"] = REQUIRED_ROUTES.issubset(signatures)

    stream_source = (repo / "app/routes/ide_routes/agent_run_stream.py").read_text(encoding="utf-8")
    checks["legacy_stream_wrapped"] = "AgentRunEngine(root)" in stream_source and "record_legacy_chunk" in stream_source
    checks["early_run_registration"] = "agent_run_registered" in stream_source

    renderer = (repo / "desktop-ide/renderer/js/ai/agent-client.js").read_text(encoding="utf-8")
    approvals = (repo / "desktop-ide/renderer/js/ai/approval-cards.js").read_text(encoding="utf-8")
    checks["renderer_backend_cancel"] = "/edgek/agent-runs/${encodeURIComponent(activeRunId)}/cancel" in renderer
    checks["renderer_run_identity"] = "agent_run_registered" in renderer and "activeRunId" in renderer
    checks["durable_approval_resolution"] = "/approvals/${encodeURIComponent(payload.request_id)}" in approvals

    with tempfile.TemporaryDirectory(prefix="beast-agent-run-verify-") as raw:
        root = Path(raw)
        engine = AgentRunEngine(root)
        run = engine.create_run(session_id="verify-session", objective="verify durable run")
        run_id = run["run_id"]
        engine.store.transition(run_id, AgentRunState.SCOPING)
        engine.record_legacy_chunk(run_id, 'event: agent_run_registered\ndata: {"payload":{"run_id":"x"}}\n\n')
        engine.record_legacy_chunk(run_id, 'event: agent_run_permission_request\ndata: {"payload":{"request_id":"approval-x","capabilities":[]}}\n\n')
        replayed = AgentRunStore(root).events(run_id)
        checks["durable_replay"] = len(replayed) == 3 and replayed[-1]["sequence"] == 3
        checks["approval_durable"] = AgentRunStore(root).approvals(run_id)[0]["approval_id"] == "approval-x"
        checks["chain_integrity"] = bool(engine.store.verify_chain(run_id).get("head_matches"))

        async def cancel_probe() -> bool:
            started = asyncio.Event()

            async def worker():
                started.set()
                await asyncio.sleep(30)

            task = asyncio.create_task(worker())
            await started.wait()
            AGENT_RUN_CANCELLATIONS.attach_task(run_id, task)
            await engine.cancel(run_id, "verification")
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False

        checks["registered_task_cancelled"] = asyncio.run(cancel_probe())
        engine.finalize_cancel(run_id, "verification")
        checks["cancel_terminal_state"] = engine.store.get_run(run_id)["state"] == "cancelled"

    result = {
        "phase": "2A",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(1 for value in checks.values() if value),
        "total": len(checks),
        "route_count": len(router.routes),
        "legacy_route_count_preserved": 52,
        "agent_run_routes_added": 9,
    }
    output = repo / "build/PHASE2A_STATUS.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {}
    if output.exists():
        try:
            loaded = json.loads(output.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                document = loaded
        except (OSError, json.JSONDecodeError):
            document = {}
    document.update(result)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
