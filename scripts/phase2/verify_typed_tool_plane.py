from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.agents.run_engine import AgentRunEngine


def main() -> int:
    checks: list[dict[str, object]] = []
    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(condition), "detail": detail})

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "sample.py").write_text("def sample():\n    return 7\n", encoding="utf-8")
        engine = AgentRunEngine(root)
        run = engine.create_run(session_id="phase2c1", objective="verify typed tool plane")
        run_id = str(run["run_id"])
        tools = engine.list_tools()
        ids = {item["tool_id"] for item in tools}
        check("builtin tools registered", {"workspace.list", "workspace.read_range", "workspace.search_text", "git.status"} <= ids)
        check("all builtins typed", all(item.get("input_schema") and item.get("risk") and item.get("effect") for item in tools))
        observation = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "sample.py"}))
        check("structured observation", observation.get("status") == "completed" and observation.get("tool_id") == "workspace.read_range")
        check("evidence digest", len(str(observation.get("evidence_digest") or "")) == 64)
        events = engine.store.events(run_id, after=0, limit=100)
        event_types = {item["event_type"] for item in events}
        check("tool lifecycle events", {"agent.tool.started", "agent.tool.completed"} <= event_types)
        check("event chain valid", bool(engine.store.verify_chain(run_id).get("ok")))
        escaped = False
        try:
            asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "../escape"}))
        except RuntimeError:
            escaped = True
        check("path escape denied", escaped)
        checkpoint = engine.store.get_run(run_id).get("checkpoint") or {}
        check("observation checkpointed", bool(checkpoint.get("last_observation_id")))

    result = {
        "schema": "beast.phase2c1-verification.v1",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "passed": sum(1 for item in checks if item["ok"]),
        "total": len(checks),
    }
    Path("build").mkdir(exist_ok=True)
    Path("build/PHASE2C1_STATUS.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
