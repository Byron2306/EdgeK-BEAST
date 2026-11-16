"""Read-only, independently executed SSH post-session quality evidence.

This does not authorize a remote target, execute model-selected commands, or
promote a SourcePlan. The caller must already hold a locked remote worktree.
Missing identity, scope or test-runner evidence refuses graduation.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any

from app.kernel.agents.post_session_graduation import resolve_implementation_target
from app.kernel.agents.tool_runtime import _remote_target_descriptor


def _refuse(reason: str) -> dict[str, Any]:
    return {"schema": "beast.post_session.quality.v1", "status": "refused",
            "reason": reason, "model_calls": 0, "promotion_authorized": False}


def _relative_file(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 220 or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and len(path.parts) > 0 and
            all(part not in {".", "..", ".git", ".beast"} for part in path.parts))


# Remote-owned script is fixed source code, not model text or a shell command.
# Values are injected exclusively as JSON data, never interpolated as code.
_REMOTE_SCRIPT = r'''
import hashlib, json, os, pathlib, re, subprocess, sys

D = json.loads(sys.stdin.readline())
def refuse(reason):
    print("BEAST_ATTESTATION=" + json.dumps({"status":"refused", "reason":reason}, sort_keys=True))
    sys.exit(0)
def run_git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, timeout=12, env={**os.environ, "GIT_OPTIONAL_LOCKS":"0"})
    if result.returncode: refuse("git_identity_unavailable")
    return result.stdout.strip()
def file_path(root, rel):
    path = root.joinpath(*rel.split("/"))
    if path.is_symlink(): refuse("symlink_file_refused")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        refuse("required_file_missing_or_escaped")
    return resolved
def snapshot(root):
    result = {}
    for path in root.rglob("*.py"):
        if ".git" in path.relative_to(root).parts or ".beast" in path.relative_to(root).parts: continue
        if path.is_symlink(): refuse("source_symlink_refused")
        canonical = path.resolve()
        if not canonical.is_relative_to(root): refuse("source_escaped_worktree")
        if path.stat().st_size > 32 * 1024 * 1024: refuse("source_file_too_large")
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        if len(result) > 1500: refuse("source_snapshot_too_large")
    return result

try:
    origin = pathlib.Path(D["origin"])
    candidate = pathlib.Path(D["candidate"])
    if not origin.is_absolute() or not candidate.is_absolute() or origin.is_symlink() or candidate.is_symlink():
        refuse("invalid_root_identity")
    origin, candidate = origin.resolve(strict=True), candidate.resolve(strict=True)
    expected = origin / ".beast" / "agent-worktrees" / D["safe_run"]
    if origin == candidate or candidate != expected or not (candidate / ".git").is_file():
        refuse("isolated_worktree_identity_mismatch")
    if run_git(origin, "rev-parse", "--show-toplevel") != str(origin):
        refuse("origin_git_identity_mismatch")
    if run_git(candidate, "rev-parse", "--show-toplevel") != str(candidate):
        refuse("candidate_git_identity_mismatch")
    base = D["base_commit"]
    if not re.fullmatch(r"[a-f0-9]{40,64}", base): refuse("base_commit_unbound")
    if run_git(origin, "rev-parse", "HEAD") != base or run_git(candidate, "rev-parse", "HEAD") != base:
        refuse("worktree_base_commit_changed")
    implementation = D["implementation"]
    baseline = file_path(origin, implementation)
    changed = file_path(candidate, implementation)
    if baseline.read_bytes() == changed.read_bytes():
        refuse("implementation_not_changed")
    committed = subprocess.run(["git", "-C", str(origin), "show", "HEAD:" + implementation],
                               capture_output=True, timeout=12)
    if committed.returncode or committed.stdout != baseline.read_bytes():
        refuse("origin_implementation_changed")
    tests = D["tests"]
    for rel in tests:
        if file_path(origin, rel).read_bytes() != file_path(candidate, rel).read_bytes():
            refuse("test_baseline_modified")
    before = snapshot(candidate)
    if not before: refuse("empty_source_snapshot")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE":"1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1", "GIT_OPTIONAL_LOCKS":"0"}
    checks = []
    for rel in tests:
        if D["runner"] == "unittest":
            if "/" in rel or not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", rel):
                refuse("unittest_test_path_invalid")
            cmd = ["python3", "-m", "unittest", "discover", "-p", rel, "-v"]
        else:
            cmd = ["python3", "-m", "pytest", "-q", rel]
        try:
            check = subprocess.run(cmd, cwd=candidate, env=env, text=True,
                                   capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            refuse("behavioral_test_timeout")
        output = check.stdout + "\n" + check.stderr
        test_count = None
        if D["runner"] == "unittest":
            match = re.search(r"Ran\s+(\d+)\s+tests?", output)
            test_count = int(match.group(1)) if match else 0
        checks.append({"path": rel, "returncode":check.returncode,
                       "test_count": test_count,
                       "output_sha256":hashlib.sha256(output.encode()).hexdigest()})
        if check.returncode or test_count == 0:
            refuse("behavioral_tests_failed_or_empty")
    after = snapshot(candidate)
    if before != after: refuse("candidate_changed_during_verification")
    for rel in tests:
        if file_path(origin, rel).read_bytes() != file_path(candidate, rel).read_bytes():
            refuse("test_baseline_modified_during_verification")
    print("BEAST_ATTESTATION=" + json.dumps({
        "status":"passed", "reason":"passed", "tested_paths":tests,
        "candidate_unchanged":True, "tests_unmodified":True,
        "implementation_target_verified":True, "candidate_root":str(candidate),
        "base_commit":base, "checks":checks, "source_file_count":len(after),
    }, sort_keys=True))
except Exception as exc:
    refuse("remote_verifier_error:" + type(exc).__name__)
'''


def verify_remote(run: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    if str(request.get("execution_target") or "") != "ssh" or checkpoint.get("worktree_remote") is not True:
        return _refuse("unsupported_or_unbound_remote_quality_target")
    payload = request.get("execution_target_payload")
    if (not isinstance(payload, dict) or payload != checkpoint.get("worktree_execution_target_payload")
            or checkpoint.get("worktree_execution_target") != "ssh"):
        return _refuse("remote_execution_target_identity_mismatch")
    try:
        descriptor = _remote_target_descriptor(SimpleNamespace(
            execution_target="ssh", execution_target_payload=payload))
    except (ValueError, TypeError) as exc:
        return _refuse("invalid_locked_ssh_target:" + type(exc).__name__)
    if descriptor.get("kind") != "ssh" or not descriptor["base"].startswith("/"):
        return _refuse("ssh_absolute_root_required")
    run_id = str(run.get("run_id") or "")
    safe_run = re.sub(r"[^A-Za-z0-9_.-]", "-", run_id)[:80]
    candidate = str(checkpoint.get("worktree_root") or "")
    expected = descriptor["base"].rstrip("/") + "/.beast/agent-worktrees/" + safe_run
    if not safe_run or candidate != expected:
        return _refuse("remote_candidate_not_locked_to_run")
    implementation = str(request.get("implementation_target") or "")
    if not implementation or implementation != resolve_implementation_target(run) or not _relative_file(implementation):
        return _refuse("explicit_implementation_target_required")
    # No graduation for a workspace that has not been observably modified.
    modified = {str((item.get("result") or {}).get("path") or (item.get("arguments") or {}).get("path") or "")
                for item in observations if isinstance(item, dict) and item.get("status") == "completed"
                and item.get("tool_id") in {"worktree.replace_exact", "worktree.write_file"}}
    if implementation not in modified:
        return _refuse("implementation_target_not_mutated")
    if any(name.startswith("test_") or name.endswith("_test.py") for name in modified):
        return _refuse("test_mutation_refused")
    tests = request.get("required_test_files")
    if (not isinstance(tests, list) or not 1 <= len(tests) <= 16
            or len(set(map(str, tests))) != len(tests)
            or not all(_relative_file(path) for path in tests)):
        return _refuse("explicit_test_files_required")
    runner = str(request.get("post_session_test_runner") or "pytest")
    if runner not in {"pytest", "unittest"}:
        return _refuse("unsupported_quality_test_runner")
    if runner == "unittest" and any("/" in rel or not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", rel) for rel in tests):
        return _refuse("unittest_requires_root_level_test_file")
    base_commit = str(checkpoint.get("worktree_base_commit") or "")
    if not re.fullmatch(r"[a-f0-9]{40,64}", base_commit):
        return _refuse("worktree_base_commit_unbound")
    data = {"origin": descriptor["base"], "candidate": candidate, "safe_run": safe_run,
            "implementation": implementation, "tests": tests, "runner": runner,
            "base_commit": base_commit}
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=7", "-o", "StrictHostKeyChecking=yes"]
    if descriptor.get("known_hosts"):
        options += ["-o", "UserKnownHostsFile=" + descriptor["known_hosts"]]
    if descriptor.get("identity_file"):
        options += ["-i", descriptor["identity_file"]]
    if descriptor.get("port"):
        options += ["-p", descriptor["port"]]
    try:
        # The fixed script is supplied over stdin; SSH executes no user supplied shell text.
        process = subprocess.run(
            ["ssh", *options, descriptor["host"], "python3 -I -c " + shlex.quote(_REMOTE_SCRIPT)],
            input=json.dumps(data, sort_keys=True) + "\n",
            capture_output=True, text=True, timeout=160,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _refuse("ssh_quality_transport_failed:" + type(exc).__name__)
    if process.returncode:
        return _refuse("ssh_quality_transport_failed")
    prefix = "BEAST_ATTESTATION="
    evidence = [line[len(prefix):] for line in process.stdout.splitlines() if line.startswith(prefix)]
    if len(evidence) != 1:
        return _refuse("remote_quality_attestation_missing_or_ambiguous")
    try:
        outcome = json.loads(evidence[0])
    except (ValueError, TypeError):
        return _refuse("remote_quality_attestation_invalid_json")
    if not isinstance(outcome, dict) or outcome.get("status") != "passed":
        return _refuse(str(outcome.get("reason") or "remote_quality_refused") if isinstance(outcome, dict) else "remote_quality_invalid")
    # Fail closed if the remote evidence contradicts the exact locked target.
    if (outcome.get("candidate_root") != candidate or outcome.get("base_commit") != base_commit
            or outcome.get("tested_paths") != tests
            or outcome.get("candidate_unchanged") is not True
            or outcome.get("tests_unmodified") is not True
            or outcome.get("implementation_target_verified") is not True):
        return _refuse("remote_quality_attestation_mismatch")
    return {"schema": "beast.post_session.quality.v1", **outcome,
            "target_execution": "remote_ssh", "execution_target_payload": payload,
            "model_calls": 0, "promotion_authorized": False}
