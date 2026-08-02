#!/usr/bin/env python3
"""Static architecture verifier for Phase 2C.2."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = []

def check(name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

models = ROOT / "app/kernel/agents/planner_models.py"
provider = ROOT / "app/kernel/agents/planner_provider.py"
runtime = ROOT / "app/kernel/agents/planner_runtime.py"
routes = ROOT / "app/routes/ide_routes/agent_runs.py"
for path in (models, provider, runtime, routes):
    check(f"exists:{path.relative_to(ROOT)}", path.is_file())

model_text = models.read_text() if models.exists() else ""
provider_text = provider.read_text() if provider.exists() else ""
runtime_text = runtime.read_text() if runtime.exists() else ""
route_text = routes.read_text() if routes.exists() else ""
check("three-decision contract", all(x in model_text for x in ('TOOL = "tool"', 'COMPLETE = "complete"', 'BLOCKED = "blocked"')))
check("strict parser", "parse_planner_decision" in provider_text and "did not contain a JSON object" in provider_text)
check("bounded loop", "while state.turn < state.max_turns" in runtime_text and "BUDGET_EXHAUSTED" in runtime_text)
check("typed tool execution", "self.engine.execute_tool" in runtime_text)
check("durable planner checkpoint", 'checkpoint["planner"]' in runtime_text)
check("planner execute route", '/edgek/agent-runs/{run_id}/planner/execute' in route_text)
check("planner state route", '/edgek/agent-runs/{run_id}/planner' in route_text)
check("no promotion authority", "never request promotion" in runtime_text)

payload = {"status": "PASS" if all(c["ok"] for c in checks) else "FAIL", "checks": checks, "passed": sum(c["ok"] for c in checks), "total": len(checks)}
print(json.dumps(payload, indent=2))
raise SystemExit(0 if payload["status"] == "PASS" else 1)
