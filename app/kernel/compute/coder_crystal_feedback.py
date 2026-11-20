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
    return {"launch_strategy": "typed_planner", "crystal_trial_profile": PROFILE,
            "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
            "implementation_target": targets[0], "required_test_files": tests,
            # A nomination only. The native resolver must see a live failure before any edit.
            "task_family": "fix-failing-assertion"}


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
