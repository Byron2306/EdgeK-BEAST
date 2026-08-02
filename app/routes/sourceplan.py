"""SourcePlan route family."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.cli.api import BeastApiClient
from app.kernel.workspaces.agent_session_store import AgentSessionStore


def build_sourceplan_router(default_root: str | Path) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    def _post_apply_workspace_feedback(root: Path, applied: list[str]) -> Dict[str, Any]:
        """Collect bounded, read-only facts for the originating agent's next turn."""
        feedback: Dict[str, Any] = {
            "applied_files": applied[:32],
            "git": {"available": False},
            "test_candidates": [],
            "recommended_verifiers": [],
        }
        try:
            status = subprocess.run(
                ["git", "status", "--short"], cwd=root, text=True, capture_output=True,
                timeout=5, check=False,
            )
            diffstat = subprocess.run(
                ["git", "diff", "--stat"], cwd=root, text=True, capture_output=True,
                timeout=5, check=False,
            )
            if status.returncode == 0:
                feedback["git"] = {
                    "available": True,
                    "status": [line[:300] for line in status.stdout.splitlines()[:40]],
                    "diffstat": [line[:300] for line in diffstat.stdout.splitlines()[:20]] if diffstat.returncode == 0 else [],
                }
        except (OSError, subprocess.SubprocessError):
            pass
        candidates: list[str] = []
        ignored = {".git", ".beast", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"}
        for rel in applied[:16]:
            path = Path(rel)
            stem, suffix = path.stem, path.suffix.lower()
            names = (
                [f"test_{stem}.py", f"{stem}_test.py"] if suffix == ".py"
                else [f"{stem}.test{suffix}", f"{stem}.spec{suffix}"] if suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx"}
                else []
            )
            for name in names:
                for candidate in (path.with_name(name), Path("tests") / name, Path("test") / name):
                    absolute = root / candidate
                    if absolute.is_file() and candidate.as_posix() not in candidates:
                        candidates.append(candidate.as_posix())
            # Accommodate common nested test layouts while maintaining a hard
            # ceiling and never following excluded dependency/build trees.
            if names and len(candidates) < 24:
                for directory, dirs, files in os.walk(root):
                    dirs[:] = [item for item in dirs if item not in ignored]
                    for name in names:
                        if name in files:
                            relative = (Path(directory) / name).relative_to(root).as_posix()
                            if relative not in candidates:
                                candidates.append(relative)
                                if len(candidates) >= 24:
                                    break
                    if len(candidates) >= 24:
                        break
        feedback["test_candidates"] = candidates[:24]
        feedback["recommended_verifiers"] = [
            (f"python -m pytest {path}" if path.endswith(".py") else f"node --test {path}")
            for path in candidates[:8]
        ]
        return feedback

    @router.post("/edgek/sourceplan/scorecard")
    async def edgek_sourceplan_scorecard(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).sourceplan_scorecard(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "scorecard failed")
        return result.data

    @router.post("/edgek/sourceplan/preview")
    async def edgek_sourceplan_preview(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).render_patch_diff(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "preview failed")
        return result.data

    @router.post("/edgek/sourceplan/verify")
    async def edgek_sourceplan_verify(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).verify_patch_plan(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "verification failed")
        return result.data

    @router.post("/edgek/sourceplan/apply")
    async def edgek_sourceplan_apply(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).apply_patch_plan(
            plan,
            approved=bool(payload.get("approved", False)),
        )
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "apply failed")
        data = result.data if isinstance(result.data, dict) else {}
        session_id = str(plan.get("agent_session_id") or "")
        if session_id:
            # Applying a plan is the decisive point in an agentic coding
            # loop. Record the actual receipt in the originating session so
            # a later follow-up sees applied files and verification facts,
            # never an assumed model-side success.
            applied = [str(item) for item in (data.get("applied") or data.get("files") or []) if item]
            verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
            feedback = _post_apply_workspace_feedback(root, applied)
            changed = ", ".join(feedback.get("git", {}).get("status") or []) or "no Git status entries available"
            test_targets = ", ".join(feedback.get("test_candidates") or []) or "no focused test candidate found"
            summary = (
                f"SourcePlan {plan.get('plan_id') or 'draft'} applied. "
                f"Files: {', '.join(applied) if applied else 'none reported'}. "
                f"Verification: {'passed' if verification.get('ok') else 'recorded'}. "
                f"Post-apply workspace status: {changed}. Focused test candidates: {test_targets}"
            )
            update = AgentSessionStore(root).update(
                session_id,
                status="active",
                files=list(dict.fromkeys([*(plan.get("files_allowed") or []), *applied])),
                output={
                    "kind": "agent_sourceplan_apply",
                    "text": summary,
                    "plan_id": str(plan.get("plan_id") or ""),
                    "applied": applied,
                    "verification": verification,
                    "workspace_feedback": feedback,
                    "apply_receipt": data,
                },
                evidence=[{
                    "beast_object_type": "beast_agent_sourceplan_apply_receipt",
                    "session_id": session_id,
                    "plan_id": str(plan.get("plan_id") or ""),
                    "applied": applied,
                    "verification_ok": bool(verification.get("ok")),
                }],
            )
            data = {**data, "workspace_feedback": feedback, "agent_session": update.get("session") if update.get("ok") else {"session_id": session_id}, "agent_followup_ready": bool(update.get("ok"))}
        return data

    @router.post("/edgek/sourceplan/rollback-latest")
    async def edgek_sourceplan_rollback_latest(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        result = BeastApiClient("http://gateway-local", workspace=root).rollback_last_patch()
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "rollback failed")
        return result.data

    @router.post("/edgek/sourceplan/lattice-replay")
    async def edgek_sourceplan_lattice_replay(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else None
        return BeastApiClient("http://gateway-local", workspace=root).mission_lattice_replay_scaffold(
            plan,
            scorecard=scorecard,
            limit=max(1, min(int(payload.get("limit", 5)), 50)),
        )

    return router
