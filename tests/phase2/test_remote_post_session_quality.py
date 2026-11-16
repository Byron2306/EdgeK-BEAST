"""Bounded SSH post-session verification; no network or model in these tests."""
import json
import shlex
import subprocess
from pathlib import Path

from app.kernel.agents.remote_post_session_quality import verify_remote


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text(".beast/\n__pycache__/\n")
    (root / "calc.py").write_text("def add(a,b):\n    return a-b\n")
    (root / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n"
        "class TestAdd(unittest.TestCase):\n"
        "    def test_add(self): self.assertEqual(add(2,3),5)\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@local",
                    "commit", "-qm", "Initial"], cwd=root, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_id = "quality-check-2a"
    worktree = root / ".beast" / "agent-worktrees" / run_id
    worktree.parent.mkdir(parents=True)
    subprocess.run(["git", "worktree", "add", "-qb", "beast-test-" + run_id, str(worktree)], cwd=root, check=True)
    (worktree / "calc.py").write_text("def add(a,b):\n    return a+b\n")
    return root, worktree, base, run_id


def _run(root, worktree, base, run_id):
    target = {"kind": "ssh", "host": "beast-test-ssh", "remoteRoot": str(root)}
    return {
        "run_id": run_id, "objective": "repair calc.py", "mode": "agent",
        "request": {"execution_target": "ssh", "execution_target_payload": target,
                    "implementation_target": "calc.py", "required_test_files": ["test_calc.py"],
                    "post_session_test_runner": "unittest"},
        "checkpoint": {"worktree_remote": True, "worktree_root": str(worktree),
                       "worktree_base_commit": base, "worktree_execution_target": "ssh",
                       "worktree_execution_target_payload": target},
    }


def _observations():
    return [{"status": "completed", "tool_id": "worktree.replace_exact", "arguments": {"path": "calc.py"},
             "result": {"path": "calc.py", "target_execution": "remote_ssh"}}]


def _fake_ssh(monkeypatch):
    # Execute only the fixed verifier script locally, so this test requires no
    # network, SSH daemon, or remote host. It exercises real source/test bytes.
    import app.kernel.agents.remote_post_session_quality as module
    real_run = subprocess.run
    def intercepted(command, *args, **kwargs):
        if isinstance(command, list) and command and command[0] == "ssh":
            remote_command = shlex.split(command[-1])
            assert remote_command[:3] == ["python3", "-I", "-c"]
            return real_run(remote_command, *args, **kwargs)
        return real_run(command, *args, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", intercepted)


def test_refuse_unbound_or_switched_target(tmp_path):
    root, worktree, base, run_id = _repo(tmp_path)
    run = _run(root, worktree, base, run_id)
    run["checkpoint"]["worktree_remote"] = False
    assert verify_remote(run, _observations())["status"] == "refused"
    run["checkpoint"]["worktree_remote"] = True
    run["checkpoint"]["worktree_execution_target_payload"] = {"kind": "ssh", "host": "elsewhere"}
    result = verify_remote(run, _observations())
    assert result["reason"] == "remote_execution_target_identity_mismatch"


def test_missing_test_manifest_refuses_without_ssh(tmp_path):
    root, worktree, base, run_id = _repo(tmp_path)
    run = _run(root, worktree, base, run_id)
    run["request"].pop("required_test_files")
    assert verify_remote(run, _observations())["reason"] == "explicit_test_files_required"


def test_remote_verifier_executes_real_behavioral_tests(tmp_path, monkeypatch):
    root, worktree, base, run_id = _repo(tmp_path)
    _fake_ssh(monkeypatch)
    run = _run(root, worktree, base, run_id)
    result = verify_remote(run, _observations())
    assert result["status"] == "passed", result
    assert result["target_execution"] == "remote_ssh"
    assert result["candidate_unchanged"] is True
    assert result["tests_unmodified"] is True
    assert result["implementation_target_verified"] is True
    assert result["checks"][0]["test_count"] == 1
    assert result["promotion_authorized"] is False


def test_modified_baseline_test_refuses(tmp_path, monkeypatch):
    root, worktree, base, run_id = _repo(tmp_path)
    (worktree / "test_calc.py").write_text((worktree / "test_calc.py").read_text() + "#tamper\n")
    _fake_ssh(monkeypatch)
    result = verify_remote(_run(root, worktree, base, run_id), _observations())
    assert result["status"] == "refused"
    assert result["reason"] == "test_baseline_modified"


def test_no_unapproved_test_file_mutation(tmp_path):
    root, worktree, base, run_id = _repo(tmp_path)
    observations = _observations() + [{"status": "completed", "tool_id": "worktree.write_file", "arguments": {"path": "test_calc.py"}}]
    assert verify_remote(_run(root, worktree, base, run_id), observations)["reason"] == "test_mutation_refused"


def test_opt_in_quality_dispatch_and_human_only_graduation(tmp_path, monkeypatch):
    from app.kernel.agents.post_session_quality import verify
    from app.kernel.agents.post_session_graduation import assess

    root, worktree, base, run_id = _repo(tmp_path)
    _fake_ssh(monkeypatch)
    run = _run(root, worktree, base, run_id)
    observations = _observations() + [
        {"status": "completed", "tool_id": "worktree.verify",
         "arguments": {"command": ["python3", "-m", "py_compile", "calc.py"]},
         "result": {"ok": True, "returncode": 0}},
        {"status": "completed", "tool_id": "worktree.sourceplan_draft", "result": {"ok": True}},
    ]
    # Existing remote sessions must remain fail-closed until expressly opted in.
    assert verify(run, observations)["reason"] == "remote_post_session_verifier_not_bound"
    run["request"]["post_session_closure"] = "verified_handoff"
    quality = verify(run, observations)
    assert quality["status"] == "passed", quality
    graduation = assess(run, observations, quality)
    assert graduation["graduation_status"] == "READY_FOR_HUMAN_APPROVAL"
    assert graduation["reasons"] == []
    assert graduation["promotion_authorized"] is False


def test_independent_behavioral_failure_refuses(tmp_path, monkeypatch):
    root, worktree, base, run_id = _repo(tmp_path)
    # Syntactically valid, modified code that still fails its behavioral tests.
    (worktree / "calc.py").write_text("def add(a,b):\n    return a*b\n")
    _fake_ssh(monkeypatch)
    result = verify_remote(_run(root, worktree, base, run_id), _observations())
    assert result["status"] == "refused"
    assert result["reason"] == "behavioral_tests_failed_or_empty"


def test_original_implementation_drift_refuses(tmp_path, monkeypatch):
    root, worktree, base, run_id = _repo(tmp_path)
    (root / "calc.py").write_text("def add(a,b):\n    return 999\n")
    _fake_ssh(monkeypatch)
    result = verify_remote(_run(root, worktree, base, run_id), _observations())
    assert result["status"] == "refused"
    assert result["reason"] == "origin_implementation_changed"
