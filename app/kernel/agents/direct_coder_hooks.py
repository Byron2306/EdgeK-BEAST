"""Optional direct-coder integrations. Hooks advise, never execute a proposed edit."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from app.kernel.agents.swarm_recovery import recover
from app.kernel.agents.swarm_specialist import specialist_enabled
from app.kernel.agents.tool_runtime import local_binding_error, local_binding_identity
from app.kernel.sensorium.episode_envelope import _contains_secret


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "yes", "true", "on"}


def swarm_requested(run: dict[str, Any]) -> bool:
    return (run.get("request") or {}).get("swarm") is True


def _role_report(root: Path, run_id: str, objective: str, files: list[str]) -> dict[str, Any]:
    from app.kernel.networking.swarm import SwarmKernel

    path = root / ".beast" / "swarm" / "direct-coder.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return SwarmKernel(db_path=str(path)).run({
        "run_id": f"{run_id}:direct-swarm",
        "profile": "zeroclaw",
        "task_type": "code_change",
        "objective": objective,
        "files": files,
        "metadata": {"parent_run_id": run_id, "proposal_only": True},
    })


def _prepare_integrations(root: Path, run_id: str, run: dict[str, Any]) -> dict[str, Any]:
    from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator

    return CoderIntegrationCoordinator(root).prepare(
        objective=str(run.get("objective") or ""),
        task_metadata={"run_id": run_id, "provider": str(run.get("provider") or "")},
    )


def _receipt(engine: Any, run_id: str, capability: str, status: str, reason: str, **fields: Any) -> None:
    engine.emit(run_id, f"agent.integration.{status}", {
        "capability": capability, "status": status, "reason": reason,
        "stage": "advisory", "effect_committed": False, **fields,
    })


async def prepare(engine: Any, run_id: str, run: dict[str, Any]) -> list[dict[str, Any]]:
    """Run requested advisory hooks once. No hook becomes an execution gate."""
    swarm = swarm_requested(run)
    integrations = _enabled("BEAST_DIRECT_CODER_INTEGRATIONS")
    if not (swarm or integrations):
        return []
    root = Path(engine.workspace_root)
    request = run.get("request") or {}
    objective = str(run.get("objective") or "")
    paths = request.get("context_files")
    files = [name[:240] for name in paths[:8] if isinstance(name, str) and not _contains_secret(name)
             ] if isinstance(paths, list) else []
    if _contains_secret(objective):
        for capability, enabled in (("swarm_roles", swarm), ("direct_coder_integrations", integrations)):
            if enabled:
                _receipt(engine, run_id, capability, "skipped", "sensitive_objective")
        return []
    advice: list[dict[str, Any]] = []
    if swarm:
        try:
            report = await asyncio.wait_for(
                asyncio.to_thread(_role_report, root, run_id, objective, files), timeout=3,
            )
            roles = [{"role": e["role"], "decision": e["decision"]} for e in report.get("events", [])]
            status = str(report.get("status") or "")
            _receipt(engine, run_id, "swarm_roles", "fired", status,
                     roles=roles, swarm_run_id=report.get("run_id"), model_calls=0,
                     proposal_only=True)
            if status == "ready":
                advice.append({"kind": "swarm_plan", "steps": report.get("plan", [])[:12]})
        except Exception as exc:
            _receipt(engine, run_id, "swarm_roles", "failed", type(exc).__name__)
    if integrations:
        try:
            prepared = await asyncio.wait_for(
                asyncio.to_thread(_prepare_integrations, root, run_id, run), timeout=3,
            )
            repo_map = str(prepared.get("repo_map") or "")[:1800]
            for event in prepared.get("events") or []:
                payload = dict(event["payload"])
                used = (payload.get("capability") == "compression.reporelay"
                        and payload.get("status") == "fired"
                        and bool(repo_map.strip()) and repo_map.strip() != str(root)
                        and not _contains_secret(repo_map))
                engine.emit(run_id, event["event_type"], {**payload, "used_in_prompt": used})
                if used:
                    advice.append({"kind": "repo_map", "navigation_only": repo_map})
        except Exception as exc:
            _receipt(engine, run_id, "direct_coder_integrations", "failed", type(exc).__name__)
    return advice


async def recover_failed_edit(engine: Any, run_id: str, run: dict[str, Any], state: dict[str, Any],
                              decision: Any, entry: dict[str, Any]) -> dict[str, Any] | None:
    if not swarm_requested(run) or decision.tool_id != "worktree.replace_exact" or entry.get("status") != "failed":
        return None
    if decision.execution_target != "local":
        return None
    target = str(decision.arguments.get("path") or "").strip()
    if not target or not specialist_enabled():
        _receipt(engine, run_id, "swarm_recovery", "skipped", "specialist_disabled" if target else "missing_target")
        return None
    identity = local_binding_identity(engine.store.get_run(run_id) or {})
    if identity is None or await asyncio.to_thread(local_binding_error, engine.workspace_root, identity):
        _receipt(engine, run_id, "swarm_recovery", "skipped", "bound_worktree_unavailable")
        return None
    if not engine.store.claim_swarm_recovery(run_id):
        return None
    _receipt(engine, run_id, "swarm_recovery", "started", "failed_exact_edit", proposal_only=True)
    try:
        timeout = max(1.0, min(60.0, float(os.environ.get("BEAST_SWARM_RECOVERY_TIMEOUT", "30"))))
        candidate, reason, receipt = await recover(
            workspace=Path(engine.workspace_root), root=Path(identity[0]),
            observations=state.get("observations") or [],
            target=target, objective=str(run.get("objective") or ""),
            cause="direct_coder_exact_edit_failed",
            run_id=run_id, env=os.environ, timeout=timeout,
        )
    except Exception as exc:
        _receipt(engine, run_id, "swarm_recovery", "failed", type(exc).__name__)
        return None
    status = "fired" if candidate else "skipped"
    _receipt(engine, run_id, "swarm_recovery", status, reason,
             model=receipt.get("model"), generated=receipt.get("generated", False),
             roles=receipt.get("roles", []), proposal_only=True)
    if candidate:
        return {"tool_id": "swarm_recovery", "status": "advisory", "result": {
            "candidate": candidate,
            "instruction": "Proposal only. Check the target and use normal worktree tools and verification.",
        }}
    return None
