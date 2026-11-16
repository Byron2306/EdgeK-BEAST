"""R3.24.1 post-session evidence gate. No model calls, subprocesses or writes.

This gate is intentionally conservative: a coding SESSION_COMPLETE is not a
semantic graduation. A passing syntax-only verifier cannot confer readiness.
"""
from __future__ import annotations
import re
from typing import Any

MUTATION = frozenset({"worktree.replace_exact", "worktree.write_file"})

# R3.24.3: objective-derived target is corroborative only; ambiguity refuses.
def resolve_implementation_target(run: dict[str, Any]) -> str:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    explicit = str(request.get("implementation_target") or "").strip()
    if explicit:
        return explicit
    objective = str(run.get("objective") or "")
    patterns = (
        r"\b(?:repair|fix|correct|modify)\s+(?:the\s+)?(?:implementation|function|code)\s+(?:in|of)\s+[`\"']?([\w./-]+\.py)",
        r"\b(?:repair|fix|correct|modify)\s+[`\"']?([\w./-]+\.py)",
    )
    matches = {m.group(1) for pattern in patterns for m in re.finditer(pattern, objective, re.I)}
    return next(iter(matches)) if len(matches) == 1 else ""

def assess(run: dict[str, Any], observations: list[dict[str, Any]], post_session: dict[str, Any] | None = None) -> dict[str, Any]:
    objective = str(run.get("objective") or "")
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    completed = [o for o in observations if isinstance(o, dict) and o.get("status") == "completed"]
    modified = sorted({str((o.get("result") or {}).get("path") or (o.get("arguments") or {}).get("path") or "")
        for o in completed if o.get("tool_id") in MUTATION})
    modified = [p for p in modified if p]
    reasons: list[str] = []
    # Only operator-owned structured target is authoritative. The objective may
    # contain many filenames, including tests, so never guess a writable target.
    explicit = resolve_implementation_target(run)
    if not explicit and modified:
        reasons.append("implementation_target_not_explicit_or_unambiguous")
    if explicit and explicit not in modified:
        reasons.append("required_implementation_target_not_mutated")
    if any(re.search(r"(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.py$", path) for path in modified):
        if request.get("allow_test_changes") is not True:
            reasons.append("test_mutation_requires_separate_operator_authorization")
    verifications = [o for o in completed if o.get("tool_id") == "worktree.verify"]
    behavioral = []
    for obs in verifications:
        args = obs.get("arguments") if isinstance(obs.get("arguments"), dict) else {}
        result = obs.get("result") if isinstance(obs.get("result"), dict) else {}
        command = args.get("command") or result.get("command") or []
        command = command.split() if isinstance(command, str) else command
        tokens = [str(t) for t in command] if isinstance(command, (list, tuple)) else []
        if (("pytest" in tokens or any(t.endswith("/pytest") for t in tokens))
                and "py_compile" not in tokens and result.get("ok") is True
                and result.get("returncode") == 0):
            behavioral.append(obs)
    if modified and any(path.endswith('.py') for path in modified) and not behavioral:
        reasons.append("focused_behavioral_pytest_not_proven")
    # Receipt presence proves the draft happened, not that it is promotable.
    drafts = [o for o in completed if o.get("tool_id") == "worktree.sourceplan_draft"]
    if modified and not drafts:
        reasons.append("sourceplan_draft_missing")
    # Independently executed behavioral evidence, bound to an isolated candidate.
    # The sourceplan remains an advisory draft, never approval to promote.
    if isinstance(post_session, dict):
        status = str(post_session.get("status") or "")
        if status != "passed":
            reasons.append(str(post_session.get("reason") or "post_session_verification_not_passed"))
        elif post_session.get("candidate_unchanged") is not True:
            reasons.append("post_session_candidate_changed_during_verification")
        elif post_session.get("tests_unmodified") is not True:
            reasons.append("post_session_test_baseline_modified")
        elif post_session.get("implementation_target_verified") is not True:
            reasons.append("post_session_implementation_target_unverified")
        else:
            reasons = [reason for reason in reasons if reason != "focused_behavioral_pytest_not_proven"]
    # A focused behavioral check plus unchanged baseline tests and explicit
    # implementation target qualifies a draft for HUMAN review only.
    ready = bool(isinstance(post_session, dict) and post_session.get("status") == "passed" and not reasons and drafts)
    return {
        "schema": "beast.agent.post_session_evidence.v1",
        "session_status": "SESSION_COMPLETE",
        "graduation_status": "REFUSE" if reasons else "READY_FOR_HUMAN_APPROVAL" if ready else "NEEDS_YOU",
        "reasons": reasons if reasons else ([] if ready else ["independent_semantic_acceptance_not_yet_attested"]),
        "modified_paths": modified,
        "behavioral_verification_receipts": len(behavioral) + (1 if ready else 0),
        "post_session_verification": post_session if isinstance(post_session, dict) else None,
        "sourceplan_draft_receipts": len(drafts),
        "inference_calls": 0,
        "source_mutation_authorized": False,
        "promotion_authorized": False,
    }
