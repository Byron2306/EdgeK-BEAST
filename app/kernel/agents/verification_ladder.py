"""Phase 3 cheapest-first verification ladder for AgentRun worktrees."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.kernel.agents.verification_planner import (
    changed_paths_from_observations,
    execution_target_descriptor,
    plan_verification,
)


def verification_ladder_enabled(run: dict[str, Any]) -> bool:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    return bool(
        request.get("verification_ladder")
        or request.get("phase3_verification_ladder")
    )


def _target_python(run: dict[str, Any]) -> list[str]:
    kind = str(execution_target_descriptor(run).get("kind") or "local")
    return ["python3", "-m"] if kind in {"ssh", "container", "devcontainer"} else ["python", "-m"]


def _stage(stage: str, command: list[str], reason: str, scope: str) -> dict[str, Any]:
    canonical = json.dumps(command, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "stage_id": f"{stage}:{digest[:12]}",
        "stage": stage,
        "command": list(command),
        "reason": reason,
        "scope": scope,
        "required": True,
    }


def _syntax_stages(run: dict[str, Any], changed: list[str]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    py = [path for path in changed if path.endswith(".py")]
    js = [path for path in changed if path.endswith((".js", ".jsx", ".mjs", ".cjs"))]
    ts = [path for path in changed if path.endswith((".ts", ".tsx", ".mts", ".cts"))]
    if py:
        stages.append(_stage(
            "syntax",
            [*_target_python(run), "py_compile", *py[:12]],
            "python_compile_for_changed_sources",
            "changed_files",
        ))
    if js:
        # node --check accepts one source file per invocation. Keep the first
        # changed source as the mandatory cheap check; focused JS tests remain
        # a later stage when the test catalog can identify them.
        stages.append(_stage(
            "syntax",
            ["node", "--check", js[0]],
            "node_syntax_check_for_changed_sources",
            "changed_files",
        ))
    if ts:
        stages.append(_stage(
            "typecheck",
            ["npx", "tsc", "--noEmit"],
            "typescript_check_for_changed_sources",
            "changed_files",
        ))
    return stages


def build_verification_ladder(run: dict[str, Any]) -> list[dict[str, Any]]:
    changed = changed_paths_from_observations(run)
    if not changed:
        return []

    stages: list[dict[str, Any]] = [
        _stage(
            "content_safety",
            ["git", "diff", "--check"],
            "worktree_diff_conflict_and_whitespace_safety",
            "worktree_diff",
        )
    ]
    stages.extend(_syntax_stages(run, changed))

    focused = plan_verification(run)
    command = focused.get("command") if isinstance(focused.get("command"), list) else []
    if command:
        existing = {tuple(item["command"]) for item in stages}
        if tuple(command) not in existing:
            stages.append(_stage(
                "focused_verification",
                command,
                str(focused.get("reason") or "focused_affected_verification"),
                str(focused.get("scope") or "affected_scope"),
            ))
    return stages


def _completed_commands(run: dict[str, Any]) -> set[tuple[str, ...]]:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
    observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
    completed: set[tuple[str, ...]] = set()
    for item in observations:
        if not isinstance(item, dict):
            continue
        if str(item.get("tool_id") or "") != "worktree.verify":
            continue
        if str(item.get("status") or "") != "completed":
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        command = result.get("command") if isinstance(result.get("command"), list) else arguments.get("command")
        if isinstance(command, list) and command and all(isinstance(part, str) for part in command):
            completed.add(tuple(command))
    return completed


def verification_ladder_receipt(run: dict[str, Any]) -> dict[str, Any]:
    stages = build_verification_ladder(run)
    completed_commands = _completed_commands(run)
    rows = []
    for item in stages:
        row = dict(item)
        row["completed"] = tuple(item["command"]) in completed_commands
        rows.append(row)
    complete = bool(rows) and all(item["completed"] for item in rows)
    body = {
        "run_id": str(run.get("run_id") or ""),
        "enabled": verification_ladder_enabled(run),
        "stages": rows,
        "completed_stage_ids": [item["stage_id"] for item in rows if item["completed"]],
        "remaining_stage_ids": [item["stage_id"] for item in rows if not item["completed"]],
        "complete": complete,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "beast_object_type": "agent_verification_ladder_receipt",
        "version": "1.0",
        "receipt_id": f"verify_ladder_{digest[:20]}",
        "receipt_hash": f"sha256:{digest}",
        **body,
    }


def next_verification_stage(run: dict[str, Any]) -> dict[str, Any] | None:
    receipt = verification_ladder_receipt(run)
    for stage in receipt["stages"]:
        if not stage["completed"]:
            return stage
    return None
