#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "structured_tool_failure": "class ToolExecutionFailed" in (ROOT / "app/kernel/agents/tool_runtime.py").read_text(),
    "repair_counter": "repair_cycles" in (ROOT / "app/kernel/agents/planner_models.py").read_text(),
    "repair_budget": "agent.repair.budget_exhausted" in (ROOT / "app/kernel/agents/planner_runtime.py").read_text(),
    "repair_required_event": "agent.repair.required" in (ROOT / "app/kernel/agents/planner_runtime.py").read_text(),
    "verification_failed_event": "agent.verification.failed" in (ROOT / "app/kernel/agents/planner_runtime.py").read_text(),
    "mutation_epoch": "worktree_mutation_epoch" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "stale_proof_refusal": "latest mutation epoch" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "no_shell_verification": "create_subprocess_exec" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
}
failed = [name for name, ok in checks.items() if not ok]
print({"status": "PASS" if not failed else "FAIL", "passed": len(checks)-len(failed), "total": len(checks), "failed": failed})
raise SystemExit(1 if failed else 0)
