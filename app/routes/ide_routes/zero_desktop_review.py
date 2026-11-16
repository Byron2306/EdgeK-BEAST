"""Narrow phone-facing entry point to Desktop's grounded file-review lane."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

ROUTE = "/edgek/zero/reviews"
BOARD = "/edgek/zero/review-board"
ID = re.compile(r"zero-review-[a-f0-9]{32}")
BOARD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
AUDIT = "zero_desktop_review_v1"
ORIGINS = {"zero_phone", "desktop_panel", "zero_cli"}


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str = Field(max_length=44)
    path: str = Field(min_length=1, max_length=320)
    question: str = Field(min_length=1, max_length=2000)
    origin: Literal["zero_phone", "desktop_panel", "zero_cli"] = "zero_cli"
    workspace: str | None = Field(default=None, max_length=4096)


def _workspace(requested: str | None = None):
    """Resolve the Desktop Review root.

    ``BEAST_ZERO_REVIEW_ROOT`` remains authoritative when set. Otherwise the
    IDE workspace passed as a query or body field is used, so the Review board
    works once a workspace is open instead of returning 503.
    """
    configured = str(os.environ.get("BEAST_ZERO_REVIEW_ROOT", "") or "").strip()
    raw = configured or str(requested or "").strip() or "/"
    root = Path(raw)
    if not root.is_absolute() or root == Path("/") or not root.is_dir():
        raise HTTPException(503, "Desktop Review workspace is not configured")
    root = root.resolve()
    if root == Path("/"):
        raise HTTPException(503, "Desktop Review workspace is not configured")
    return root


def _source(root, name):
    raw_parts = name.split("/")
    path = PurePosixPath(name)
    if (path.is_absolute() or any(not part or part.startswith(".") for part in raw_parts)
            or not re.fullmatch(r"[\w .+/-]+", name, flags=re.ASCII)):
        raise HTTPException(422, "Use one visible file relative to the Desktop workspace")
    target = root
    for part in raw_parts:
        target = target / part
        if target.is_symlink():
            raise HTTPException(422, "Symlinks are not accepted in Desktop Review")
    if not target.is_file() or not target.resolve().is_relative_to(root):
        raise HTTPException(422, "Desktop review file is not available in the workspace")
    return path.as_posix()


def _identity(run_id):
    if not ID.fullmatch(run_id):
        raise HTTPException(404, "Unknown Zero Desktop Review run")


def _owned(run):
    return (isinstance(run, dict) and run.get("mode") == "analysis"
            and run.get("provider") == "ollama"
            and isinstance(run.get("request"), dict)
            and run["request"].get("zero_review_contract") == AUDIT)


def _board_origin(run, root):
    if not isinstance(run, dict) or run.get("root_path") != str(root):
        return ""
    if not BOARD_ID.fullmatch(str(run.get("run_id") or "")):
        return ""
    request = run.get("request")
    if _owned(run):
        origin = request.get("zero_review_origin")
        return origin if isinstance(origin, str) and origin in ORIGINS else "zero_cli"
    if (run.get("mode") == "analysis" and isinstance(request, dict)
            and request.get("read_only_file_review") is True
            and isinstance(request.get("context_files"), list)
            and any(isinstance(path, str) and path.strip() for path in request["context_files"])):
        return "desktop_pair_programmer"
    return ""


def _check_board_workspace(workspace, root):
    if not workspace:
        return
    try:
        matches = len(workspace) <= 4096 and Path(workspace).is_absolute() and Path(workspace).resolve() == root
    except (OSError, RuntimeError, ValueError):
        matches = False
    if not matches:
        raise HTTPException(409, "Open the configured Desktop Review workspace in the IDE")


def _projection(engine, run):
    result = {"ok": True}
    for key in ("run_id", "state", "root_path", "provider", "model"):
        result[key] = run.get(key, "")
    if run.get("state") == "failed":
        result["error"] = str(run.get("error") or "Desktop review failed.")[:1400]
    if run.get("state") == "completed":
        # Only return an accepted advisory, never a raw provider delta or tool payload.
        cursor, advisory, completion = max(0, int(run.get("last_sequence") or 0) - 512), {}, False
        for _ in range(8):
            batch = engine.store.events(run["run_id"], after=cursor, limit=64)
            for event in batch:
                kind = event.get("event_type")
                payload = event.get("payload") or {}
                if kind == "agent.run.advisory":
                    advisory = payload
                if kind == "agent.planner.completed":
                    completion = payload.get("completion_mode") == "read_only_advisory"
                cursor = event["sequence"]
            if len(batch) < 64:
                break
        if completion and isinstance(advisory.get("text"), str) and advisory["text"].strip():
            result["answer"] = advisory["text"][:24000]
            result["coverage"] = str(advisory.get("coverage") or "")[:2000]
        else:
            result["error"] = "Desktop finished without a grounded review receipt."
    return result


def _submit_projection(engine, run, origin):
    if origin == "zero_cli":
        return _projection(engine, run)
    return {"ok": True, **{key: run.get(key, "") for key in ("run_id", "state", "root_path")}}


def register_zero_review(router, engine_factory, session_factory, launch, *, supported):
    def require_local(request):
        if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Use the Desktop loopback gateway through SSH")

    @router.get(ROUTE)
    async def zero_review_status(request: Request, workspace: str = ""):
        require_local(request)
        if not supported():
            raise HTTPException(503, "Install Desktop's grounded file-review support first")
        return {"ok": True, "workspace": str(_workspace(workspace)), "provider": "ollama",
                "model": os.environ.get("BEAST_ZERO_REVIEW_MODEL", "qwen3:4b").strip()}

    @router.post(ROUTE)
    async def create_zero_review(request: Request, body: ReviewRequest):
        require_local(request)
        if not supported():
            raise HTTPException(503, "Install Desktop's grounded file-review support first")
        root = _workspace(body.workspace)
        configured = str(os.environ.get("BEAST_ZERO_REVIEW_ROOT", "") or "").strip()
        if configured and body.workspace is not None and body.workspace != str(root):
            raise HTTPException(409, "Desktop Review is configured for a different workspace")
        _identity(body.run_id)
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "Enter a review question")
        digest = hashlib.sha256(json.dumps([body.path, question], ensure_ascii=False).encode()).hexdigest()
        engine = engine_factory(root)
        prior = engine.store.get_run(body.run_id)
        if prior:
            if (not _owned(prior) or prior.get("root_path") != str(root)
                    or prior["request"].get("zero_review_digest") != digest):
                raise HTTPException(409, "That run ID belongs to another request")
            return _submit_projection(engine, prior, body.origin)
        path = _source(root, body.path)
        model = os.environ.get("BEAST_ZERO_REVIEW_MODEL", "qwen3:4b").strip()
        if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", model):
            raise HTTPException(503, "Invalid Desktop Review Ollama model setting")
        objective = f"Review {path} only. Cite source evidence. Do not edit files or run commands.\nQuestion: {question}"
        budget = {"tokens": 12000, "seconds": 180, "cost_usd": 0, "max_turns": 8}
        session = session_factory(root).create(
            objective=objective, mode="analysis", budget=budget, tools=["Workspace File Read"],
            files=[path], provider="ollama", model=model, execution_target="local",
        )
        session_id = (session.get("session") or {}).get("session_id")
        if session.get("ok") is not True or not session_id:
            raise HTTPException(503, "Desktop could not create the review session")
        run = engine.create_run(
            session_id=session_id, objective=objective, mode="analysis",
            provider="ollama", model=model, budget=budget, run_id=body.run_id,
            request={
                "prompt": objective, "workspace_root": str(root), "execution_target": "local",
                "context_files": [path], "launch_strategy": "typed_planner",
                "read_only_file_review": True, "zero_review_contract": AUDIT,
                "zero_review_digest": digest, "zero_review_origin": body.origin,
                "max_tokens": 1200, "max_turns": 8,
            },
        )
        # If another server worker inserted the same primary key, only the
        # session that owns the inserted row may launch it.
        if run.get("session_id") != session_id:
            if not _owned(run) or run["request"].get("zero_review_digest") != digest:
                raise HTTPException(409, "That run ID belongs to another request")
            return _submit_projection(engine, run, body.origin)
        try:
            launch(request.app, root, run)
        except Exception:
            engine.fail(body.run_id, "Desktop review could not start.")
        return _submit_projection(engine, engine.store.get_run(body.run_id) or run, body.origin)

    @router.get(ROUTE + "/{run_id}")
    async def get_zero_review(run_id: str, request: Request, workspace: str = ""):
        require_local(request)
        root = _workspace(workspace)
        _identity(run_id)
        engine = engine_factory(root)
        run = engine.store.get_run(run_id)
        if not _owned(run) or run.get("root_path") != str(root):
            raise HTTPException(404, "Unknown Zero Desktop Review run")
        return _projection(engine, run)

    @router.get(BOARD)
    def zero_review_board(request: Request, workspace: str = ""):
        require_local(request)
        if not supported():
            raise HTTPException(503, "Install Desktop's grounded file-review support first")
        root = _workspace(workspace)
        configured = str(os.environ.get("BEAST_ZERO_REVIEW_ROOT", "") or "").strip()
        if configured:
            _check_board_workspace(workspace, root)
        store = engine_factory(root).store
        rows = []
        for run in store.list_runs(limit=100):
            origin = _board_origin(run, root)
            if origin:
                rows.append({**{key: run.get(key) for key in
                                ("run_id", "state", "provider", "model", "updated_at")}, "origin": origin})
                if len(rows) == 20:
                    break
        return {"ok": True, "workspace": str(root), "provider": "ollama",
                "model": os.environ.get("BEAST_ZERO_REVIEW_MODEL", "qwen3:4b").strip(), "runs": rows}

    @router.get(BOARD + "/{run_id}")
    def zero_review_board_detail(run_id: str, request: Request, workspace: str = ""):
        require_local(request)
        root = _workspace(workspace)
        configured = str(os.environ.get("BEAST_ZERO_REVIEW_ROOT", "") or "").strip()
        if configured:
            _check_board_workspace(workspace, root)
        if not BOARD_ID.fullmatch(run_id):
            raise HTTPException(404, "Unknown shared review")
        engine = engine_factory(root)
        run = engine.store.get_run(run_id)
        origin = _board_origin(run, root)
        if not origin:
            raise HTTPException(404, "Unknown shared review")
        result = _projection(engine, run)
        # On the shared UI, provider failures can include details intended for Desktop logs.
        if result.get("state") == "failed":
            result["error"] = "Desktop review failed. See the Desktop run for details."
        return {**result, "origin": origin}
