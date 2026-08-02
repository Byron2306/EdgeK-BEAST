import asyncio
import subprocess
from pathlib import Path

from app.kernel.agents import worktree_tools as worktree_tools_module
from app.kernel.agents.run_engine import AgentRunEngine


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "hello.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _approved(engine: AgentRunEngine, run_id: str, approval_id: str = "mutation") -> str:
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True})
    return approval_id


def test_worktree_mutation_verification_and_sourceplan(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run = engine.create_run(session_id="session", objective="change greeting")
        run_id = run["run_id"]
        approval = _approved(engine, run_id)
        await engine.execute_tool(run_id, "worktree.bind", {"objective": "change greeting"}, approval_id=approval)
        await engine.execute_tool(run_id, "worktree.replace_exact", {
            "path": "hello.txt", "old_text": "hello", "new_text": "goodbye"
        }, approval_id=approval)
        await engine.execute_tool(run_id, "worktree.verify", {
            "command": ["python", "-c", "from pathlib import Path; assert Path('hello.txt').read_text() == 'goodbye\\n'"]
        }, approval_id=approval)
        draft = await engine.execute_tool(run_id, "worktree.sourceplan_draft", {})
        checkpoint = engine.store.get_run(run_id)["checkpoint"]
        assert checkpoint["verification"]["ok"] is True
        assert checkpoint["sourceplan"]["plan_id"]
        assert draft["status"] == "completed"
        assert engine.store.verify_chain(run_id)["ok"] is True
    asyncio.run(scenario())


def test_mutation_requires_approval_and_worktree(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="blocked")["run_id"]
        try:
            await engine.execute_tool(run_id, "worktree.bind", {"objective": "blocked"})
        except PermissionError:
            pass
        else:
            raise AssertionError("worktree.bind accepted without approval")
        approval = _approved(engine, run_id)
        try:
            await engine.execute_tool(run_id, "worktree.write_file", {"path": "x.txt", "content": "x"}, approval_id=approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("mutation accepted without bound worktree")
    asyncio.run(scenario())


def test_worktree_escape_is_rejected(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="escape")["run_id"]
        approval = _approved(engine, run_id)
        await engine.execute_tool(run_id, "worktree.bind", {"objective": "escape"}, approval_id=approval)
        try:
            await engine.execute_tool(run_id, "worktree.write_file", {"path": "../escape.txt", "content": "no"}, approval_id=approval)
        except RuntimeError as exc:
            assert "escapes isolated worktree" in str(exc)
        else:
            raise AssertionError("path escape accepted")
    asyncio.run(scenario())


def test_existing_file_requires_bounded_replacement(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        (root / "existing.txt").write_text("before", encoding="utf-8")
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="bounded") ["run_id"]
        approval = _approved(engine, run_id)
        await engine.execute_tool(run_id, "worktree.bind", {"objective": "bounded"}, approval_id=approval)
        try:
            await engine.execute_tool(run_id, "worktree.write_file", {"path": "existing.txt", "content": "whole file"}, approval_id=approval)
        except RuntimeError as exc:
            assert "replace_exact" in str(exc)
        else:
            raise AssertionError("existing file was overwritten through write_file")
    asyncio.run(scenario())


def test_remote_worktree_mutation_and_verification_execute_on_target(tmp_path, monkeypatch):
    async def scenario():
        root = _repo(tmp_path)
        calls = []

        async def fake_target_shell(context, script, *, timeout=20.0, output_limit=512000):
            calls.append({"target": context.execution_target, "script": script, "timeout": timeout})
            if "git worktree add" in script:
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": "BEAST_WORKTREE\n/repo/.beast/agent-worktrees/run-remote\nabc123\nbeast-agent-run-remote\n",
                    "stderr": "",
                    "truncated": False,
                }
            if "python3 - <<'PY'" in script:
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": "0" * 64 + "\n" + "1" * 64 + "\n",
                    "stderr": "",
                    "truncated": False,
                }
            if "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in script:
                return {"ok": True, "returncode": 0, "stdout": "remote verifier ok\n", "stderr": "", "truncated": False}
            if "BEAST_DIFF_STATUS" in script:
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": (
                        "BEAST_DIFF_STATUS\n"
                        " M hello.txt\n"
                        "BEAST_DIFF_STAT\n"
                        " hello.txt | 2 +-\n"
                        " 1 file changed, 1 insertion(+), 1 deletion(-)\n"
                        "BEAST_DIFF_NAME_ONLY\n"
                        "hello.txt\n"
                        "BEAST_DIFF_PATCH\n"
                        "diff --git a/hello.txt b/hello.txt\n"
                        "index ce01362..cc628cc 100644\n"
                        "--- a/hello.txt\n"
                        "+++ b/hello.txt\n"
                        "@@ -1 +1 @@\n"
                        "-hello\n"
                        "+goodbye\n"
                    ),
                    "stderr": "",
                    "truncated": False,
                }
            return {"ok": False, "returncode": 2, "stdout": "", "stderr": f"unexpected script: {script}", "truncated": False}

        monkeypatch.setattr(worktree_tools_module, "_run_target_shell", fake_target_shell)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="remote mutate", run_id="run-remote")["run_id"]
        approval = _approved(engine, run_id)
        target_payload = {"kind": "ssh", "sessionId": "target-ssh-mutate", "host": "devbox", "remoteRoot": "/repo"}
        bind = await engine.execute_tool(
            run_id,
            "worktree.bind",
            {"objective": "remote mutate"},
            approval_id=approval,
            execution_target="ssh",
            execution_target_payload=target_payload,
        )
        replace = await engine.execute_tool(
            run_id,
            "worktree.replace_exact",
            {"path": "hello.txt", "old_text": "hello", "new_text": "goodbye"},
            approval_id=approval,
            execution_target="ssh",
            execution_target_payload=target_payload,
        )
        verify = await engine.execute_tool(
            run_id,
            "worktree.verify",
            {"command": ["python3", "-c", "print('ok')"]},
            approval_id=approval,
            execution_target="ssh",
            execution_target_payload=target_payload,
        )
        diff = await engine.execute_tool(
            run_id,
            "worktree.diff",
            {},
            execution_target="ssh",
            execution_target_payload=target_payload,
        )
        draft = await engine.execute_tool(
            run_id,
            "worktree.sourceplan_draft",
            {},
            execution_target="ssh",
            execution_target_payload=target_payload,
        )

        checkpoint = engine.store.get_run(run_id)["checkpoint"]
        assert bind["result"]["target_execution"] == "remote_ssh"
        assert checkpoint["worktree_remote"] is True
        assert checkpoint["worktree_root"] == "/repo/.beast/agent-worktrees/run-remote"
        assert replace["result"]["target_execution"] == "remote_ssh"
        assert verify["result"]["target_execution"] == "remote_ssh"
        assert diff["result"]["target_execution"] == "remote_ssh"
        assert diff["result"]["files"] == ["hello.txt"]
        assert draft["status"] == "completed"
        assert draft["result"]["target_execution"] == "remote_ssh"
        assert draft["result"]["plan"]["requires_operator_translation"] is True
        assert checkpoint["sourceplan"]["target_execution"] == "remote_ssh"
        assert checkpoint["verification"]["ok"] is True
        assert checkpoint["verification"]["target_execution"] == "remote_ssh"
        assert any("cd '/repo/.beast/agent-worktrees/run-remote'" in call["script"] for call in calls)

    asyncio.run(scenario())
