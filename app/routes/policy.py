"""Policy route family for mode, Spec Covenant, and safety gates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.agents.mode_router import ModeRouter
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.policy.spec_covenant import SpecCovenantCompiler
from app.kernel.security.safety_governor import SafetyGovernor


def build_policy_router(default_root: str | Path, mode_router: ModeRouter) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    def _safe_cwd(root: Path, value: Any = None) -> Path:
        cwd = Path(value or root).expanduser().resolve()
        try:
            cwd.relative_to(root)
        except ValueError:
            return root
        return cwd if cwd.exists() and cwd.is_dir() else root

    @router.get("/edgek/architecture-decisions")
    async def edgek_architecture_decisions():
        return architecture_decision_register()

    @router.get("/edgek/mode-router/catalog")
    async def edgek_mode_router_catalog():
        return mode_router.definitions()

    @router.post("/edgek/mode-router/select")
    async def edgek_mode_router_select(payload: Dict[str, Any] = None):
        payload = payload or {}
        return mode_router.select(
            phase=str(payload.get("phase") or ""),
            risk=str(payload.get("risk") or ""),
            requested_mode=str(payload.get("requested_mode") or ""),
            provider=str(payload.get("provider") or ""),
            sourceplan=payload.get("sourceplan") if isinstance(payload.get("sourceplan"), dict) else {},
        )

    @router.post("/edgek/spec-covenant/compile")
    async def edgek_spec_covenant_compile(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SpecCovenantCompiler(root).compile(
            objective=str(payload.get("objective") or ""),
            files=[str(item) for item in (payload.get("files") or [])],
            mode=str(payload.get("mode") or ""),
            operator_notes=str(payload.get("operator_notes") or ""),
            max_rules=max(1, min(int(payload.get("max_rules", 18)), 100)),
        )

    @router.post("/edgek/spec-covenant/batches")
    async def edgek_spec_covenant_batches(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        covenant = payload.get("covenant") if isinstance(payload.get("covenant"), dict) else {}
        return SpecCovenantCompiler(root).spec_to_sourceplan_batches(
            covenant,
            batch_size=max(1, min(int(payload.get("batch_size", 5)), 50)),
        )

    @router.post("/edgek/safety-governor/classify-command")
    async def edgek_safety_governor_classify_command(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SafetyGovernor(root).classify_command(
            str(payload.get("command") or ""),
            mode=str(payload.get("mode") or ""),
            task_id=str(payload.get("task_id") or ""),
            operator_override=str(payload.get("operator_override") or ""),
        )

    @router.post("/edgek/safety-governor/execute-command")
    async def edgek_safety_governor_execute_command(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        cwd = _safe_cwd(root, payload.get("cwd"))
        command = str(payload.get("command") or "").strip()
        mode = str(payload.get("mode") or "")
        task_id = str(payload.get("task_id") or "")
        approved = bool(payload.get("approved", False))
        operator_override = str(payload.get("operator_override") or "")
        timeout = max(1.0, min(float(payload.get("timeout", 120.0)), 900.0))
        governor = SafetyGovernor(root)
        receipt = governor.classify_command(
            command,
            mode=mode,
            task_id=task_id,
            operator_override=operator_override,
        )
        decision = str(receipt.get("decision") or "allow")
        if not command:
            return {"ok": False, "error": "empty_command", "safety": receipt}
        if decision == "block":
            return {"ok": False, "error": "blocked_by_safety_governor", "safety": receipt}
        if decision in {"warn", "require_approval", "sandbox/worktree_only"} and not approved:
            return {"ok": False, "error": "approval_required", "safety": receipt}
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return {"ok": False, "error": f"invalid_command: {exc}", "safety": receipt}
        if not argv:
            return {"ok": False, "error": "empty_command", "safety": receipt}

        started = time.time()

        def execute_command() -> tuple[bool, str, str, int]:
            try:
                completed = subprocess.run(
                    argv,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                return (
                    False,
                    completed.stdout[-20000:],
                    completed.stderr[-20000:],
                    int(completed.returncode),
                )
            except subprocess.TimeoutExpired as exc:
                return (
                    True,
                    str(exc.stdout or "")[-20000:],
                    str(exc.stderr or "")[-20000:] + f"\nTimed out after {timeout:.1f}s",
                    124,
                )

        timed_out, stdout, stderr, returncode = await asyncio.to_thread(execute_command)
        finished = time.time()
        result = {
            "beast_object_type": "beast_governed_terminal_execution",
            "version": "1.0",
            "ok": returncode == 0 and not timed_out,
            "command": command,
            "argv": argv,
            "cwd": str(cwd),
            "workspace_root": str(root),
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_ms": round((finished - started) * 1000.0, 3),
            "approved": approved,
            "operator_override": operator_override,
            "safety": receipt,
            "created_at": int(finished),
        }
        out_dir = root / ".beast" / "evidence" / "terminal"
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        out_path = out_dir / f"terminal_{int(finished)}_{digest}.json"
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        evidence = EvidenceBus(root).register(
            artifact_type="beast_governed_terminal_execution",
            artifact_path=out_path,
            artifact_hash="sha256:" + hashlib.sha256(out_path.read_bytes()).hexdigest(),
            source="governed_terminal",
            task_id=task_id or str(receipt.get("task_id") or ""),
            status="ok" if result["ok"] else "failed",
            summary=command,
            relationships={"safety_receipt": receipt},
            metadata={
                "decision": decision,
                "returncode": returncode,
                "approved": approved,
                "cwd": str(cwd),
            },
        )
        result["evidence_receipt"] = evidence
        result["evidence_path"] = str(out_path)
        return result

    @router.post("/edgek/safety-governor/scan-workspace")
    async def edgek_safety_governor_scan_workspace(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SafetyGovernor(root).scan_workspace(
            files=[str(item) for item in payload.get("files") or []] or None,
            max_files=max(1, min(int(payload.get("max_files", 250)), 1000)),
        )

    return router
