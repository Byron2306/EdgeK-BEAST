"""One Coder trial profile and conservative, exact-context negative scopes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

PROFILE_ENV = "BEAST_CODER_CRYSTAL_TRIAL"
PROFILE = "native_crystal_feedback_v1"


def trial_enabled(env):
    return str(env.get(PROFILE_ENV, "")).lower() in {"1", "yes", "true", "on"}


def trial_request(mode, files, *, enabled):
    if not enabled or mode not in {"agent", "edit"}:
        return {}
    tests, targets = [], []
    for name in files:
        if not name.endswith(".py"):
            continue
        if Path(name).name.startswith("test_"):
            if not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", name):
                return {}
            tests.append(name)
        else:
            targets.append(name)
    if len(targets) != 1 or not tests:
        return {}
    return {"launch_strategy": "direct_coder", "crystal_trial_profile": PROFILE,
            "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
            "implementation_target": targets[0], "required_test_files": tests}


def scope_digest(root: Path, run) -> str:
    request = run.get("request") or {}
    if request.get("crystal_trial_profile") != PROFILE:
        return ""
    names = [request.get("implementation_target"), *(request.get("required_test_files") or [])]
    if len(names) < 2:
        return ""
    root = root.resolve()
    files = []
    for name in names:
        if not isinstance(name, str) or not name or not name.endswith(".py"):
            return ""
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            return ""
        path = root / relative
        try:
            if path.resolve() != path or not path.is_file() or path.stat().st_size > 262144:
                return ""
            with path.open("rb") as fh:
                raw = fh.read(262145)
            if len(raw) > 262144:
                return ""
        except OSError:
            return ""
        files.append((relative.as_posix(), hashlib.sha256(raw).hexdigest()))
    identity = [PROFILE, request.get("post_session_test_runner"), files]
    return "sha256:" + hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def verifier_outcome(observation, command):
    """Recognize an executed canonical unittest result, not a tool/infrastructure failure."""
    if observation.get("tool_id") != "worktree.verify":
        return None
    if (observation.get("arguments") or {}).get("command") != command:
        return None
    result = observation.get("result") or {}
    rc = result.get("returncode")
    output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    if not re.search(r"^Ran [1-9][0-9]* tests?\b", output, re.M):
        return None
    if type(rc) is not int:
        return None
    if rc == 0 and observation.get("status") == "completed" and result.get("ok") is True:
        return rc
    if rc == 1 and observation.get("status") == "failed" and re.search(
            r"^FAILED \((?=[^)]*(?:failures|errors)=[1-9][0-9]*)[^)]*\)$", output, re.M):
        return rc
    return None


def observed_trial_family(request, observations):
    """Classify only after a canonical failing verifier and exact target source were observed.

    The legacy v1 coding crystal is a constant-replacement recipe. Do not label
    arbitrary unittest failures as that family merely because they use unittest.
    Broader repair families live in family_crystals and have their own applicability matcher.
    """
    target = str((request or {}).get("implementation_target") or "")
    if not target:
        return ""
    verify = read = None
    for item in observations or ():
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool_id") or "")
        if tool == "worktree.verify" and item.get("status") == "failed":
            verify = item
        elif tool == "workspace.read_range" and item.get("status") == "completed":
            args = item.get("arguments") or {}
            if args.get("path") == target:
                read = item
    if not verify or not read:
        return ""
    result = verify.get("result") if isinstance(verify.get("result"), dict) else {}
    output = "\n".join(str(result.get(key) or "") for key in ("stdout", "stderr")).strip()
    read_result = read.get("result") if isinstance(read.get("result"), dict) else {}
    content = str(read_result.get("content") or "")
    from app.kernel.compute.coding_crystals import resolve_constant
    return "fix-failing-assertion" if resolve_constant(output, content) else ""
