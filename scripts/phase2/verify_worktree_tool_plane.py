#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "worktree_tools_module": (ROOT / "app/kernel/agents/worktree_tools.py").is_file(),
    "typed_context_engine": "engine: Any" in (ROOT / "app/kernel/agents/tool_models.py").read_text(),
    "checkpoint_merge": "def merge_checkpoint" in (ROOT / "app/kernel/agents/run_engine.py").read_text(),
    "registry_binding": "register_worktree_tools" in (ROOT / "app/kernel/agents/tool_runtime.py").read_text(),
    "bind_tool": "worktree.bind" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "mutation_tool": "worktree.replace_exact" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "verification_tool": "worktree.verify" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "sourceplan_tool": "worktree.sourceplan_draft" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "no_shell": "create_subprocess_exec" in (ROOT / "app/kernel/agents/worktree_tools.py").read_text(),
    "focused_tests": (ROOT / "tests/phase2/test_worktree_mutation_tools.py").is_file(),
}
result = {"status": "PASS" if all(checks.values()) else "FAIL", "passed": sum(checks.values()), "total": len(checks), "checks": checks}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["status"] == "PASS" else 1)
