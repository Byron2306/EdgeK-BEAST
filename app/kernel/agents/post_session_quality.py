"""R3.24.2 deterministic post-session verification, no model, no promotion.

The caller owns the frozen worktree and supplies the exact run checkpoint.
Fail closed for remote or unbound worktrees and when no root-level test is
available. QualityCascade executes actual pytest; worktree bytes are checked
before and after. This creates no new execution authorization.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from app.kernel.data_processing.quality_cascade import QualityCascade


def _failure(reason: str) -> dict[str, Any]:
    return {"schema":"beast.post_session.quality.v1", "status":"refused",
            "reason":reason, "model_calls":0, "promotion_authorized":False}


def verify(run: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    if checkpoint.get("worktree_remote") or str(request.get("execution_target") or "local") not in {"", "local"}:
        # Preserve the historic fail-closed behavior unless the operator's
        # durable run explicitly opts into the bounded SSH evidence contract.
        if (str(request.get("execution_target") or "") != "ssh"
                or request.get("post_session_closure") != "verified_handoff"):
            return _failure("remote_post_session_verifier_not_bound")
        from app.kernel.agents.remote_post_session_quality import verify_remote
        return verify_remote(run, observations)
    origin_str = str(run.get("root_path") or run.get("workspace_root") or "")
    candidate_str = str(checkpoint.get("worktree_root") or "")
    if not origin_str or not candidate_str:
        return _failure("worktree_or_origin_not_bound")
    origin, candidate = Path(origin_str).expanduser().resolve(), Path(candidate_str).expanduser().resolve()
    if not candidate.is_dir() or not origin.is_dir() or origin == candidate:
        return _failure("isolated_candidate_not_proven")
    if candidate.is_symlink() or not (candidate / ".git").exists():
        return _failure("candidate_is_not_git_worktree")
    modified = {str((o.get("result") or {}).get("path") or (o.get("arguments") or {}).get("path") or "")
                for o in observations if isinstance(o,dict) and o.get("status")=="completed"
                and o.get("tool_id") in {"worktree.replace_exact","worktree.write_file"}}
    modified.discard("")
    from app.kernel.agents.post_session_graduation import assess
    preliminary = assess(run, observations)
    if any(r in preliminary["reasons"] for r in ("required_implementation_target_not_mutated", "test_mutation_requires_separate_operator_authorization")):
        return _failure("implementation_scope_or_test_integrity_refused")
    from app.kernel.agents.post_session_graduation import resolve_implementation_target
    explicit = resolve_implementation_target(run)
    if not explicit or explicit not in modified or explicit.startswith("/") or ".." in Path(explicit).parts:
        return _failure("exact_implementation_target_unverified")
    target=(candidate/explicit).resolve()
    if not target.is_file() or not target.is_relative_to(candidate):
        return _failure("implementation_target_missing")
    tests=[]
    required=request.get("required_test_files")
    if isinstance(required,list) and required:
        tests=[str(item) for item in required]
    else:
        tests=[path.name for path in sorted(origin.glob("test_*.py")) if path.is_file()]
    if not tests:
        return _failure("focused_test_target_missing")
    if len(tests)>16:
        return _failure("too_many_test_targets")
    for rel in tests:
        if rel.startswith("/") or ".." in Path(rel).parts or not (candidate/rel).resolve().is_relative_to(candidate):
            return _failure("unsafe_test_target")
        ref=(origin/rel).resolve(); test=(candidate/rel).resolve()
        if not ref.is_file() or not test.is_file() or not ref.is_relative_to(origin):
            return _failure("test_baseline_missing")
        if ref.read_bytes()!=test.read_bytes():
            return _failure("test_baseline_modified")
    # Freeze all Python source before test execution. No model calls, no mutations.
    before={str(f.relative_to(candidate)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in candidate.rglob("*.py") if f.is_file() and ".git" not in f.parts}
    # Do not allow a broad source tree to exhaust the post-session verifier.
    if len(before)>1500: return _failure("source_snapshot_too_large")
    check=QualityCascade().check_pytest(candidate, ["-q", *tests], timeout_seconds=120)
    after={str(f.relative_to(candidate)):hashlib.sha256(f.read_bytes()).hexdigest()
           for f in candidate.rglob("*.py") if f.is_file() and ".git" not in f.parts}
    unchanged=before==after
    return {"schema":"beast.post_session.quality.v1",
            "status":"passed" if check.status=="passed" and unchanged else "refused",
            "reason":"passed" if check.status=="passed" and unchanged else "pytest_failed_or_candidate_changed",
            "check":check.to_dict(), "tested_paths":tests,
            "candidate_unchanged":unchanged, "tests_unmodified":True,
            "implementation_target_verified":True,
            "candidate_root":str(candidate), "model_calls":0,
            "promotion_authorized":False}
