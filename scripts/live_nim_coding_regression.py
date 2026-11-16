"""Explicit live NIM coding proof in a disposable git repository; no promotion."""
import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.security.secret_vault import SecretVault


async def main():
    SecretVault().load()
    root = Path(tempfile.mkdtemp(prefix="beast-nim-coding-regression-"))
    (root / "answer.py").write_text("VALUE = 1\n")
    (root / "test_answer.py").write_text("from answer import VALUE\n\ndef test_answer():\n    assert VALUE == 2\n")
    for args in (["init", "-q"], ["config", "user.email", "beast@example.test"],
                 ["config", "user.name", "BEAST Regression"], ["add", "."], ["commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="nim-regression", objective="Fix answer.py: change VALUE from 1 to 2 and verify test_answer.py passes. Do not modify tests.",
        mode="agent", provider="nvidia_nim", model="nvidia/nemotron-3.5-lightning-30b-a3b",
        request={"context_files":["answer.py"], "implementation_target":"answer.py", "required_test_files":["test_answer.py"]})
    rid = run["run_id"]
    engine.store.create_approval(rid, {"request_id":"fixture-worktree", "capabilities":[{"id":"worktree_mutation"}]})
    engine.store.resolve_approval(rid,"fixture-worktree",{"approved":True,"scope":"run"})
    print(json.dumps({"workspace":str(root), "run_id":rid}),flush=True)
    provider = NIMPlannerProvider(model=run["model"],timeout_seconds=30,max_retries=1)
    result = await AgentPlannerRuntime(engine,provider,max_turns=12).run(rid)
    planner = result.get("checkpoint",{}).get("planner",{})
    print(json.dumps({"state":result["state"], "blocker":planner.get("blocker"), "summary":planner.get("final_summary"),
        "observations":[{"tool":o.get("tool_id"),"status":o.get("status"),"error":o.get("error")} for o in planner.get("observations",[])]}),flush=True)
    assert (root / "answer.py").read_text() == "VALUE = 1\n", "Source repository was changed"
    assert result["state"] == "completed", "Coding proof did not complete"


if __name__ == "__main__":
    asyncio.run(main())
