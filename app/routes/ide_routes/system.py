"""System routes for the BEAST IDE facade."""

from __future__ import annotations
import asyncio
import ast
import difflib
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, List
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from app.cli.api import ActionResult, BeastApiClient
from app.kernel.compute.action_ir import ACTION_IR_KIND, ActionIR
from app.kernel.compute.action_resolver import build_file_references, resolve_action_ir
from app.kernel.adapters.provider_handoff import build_provider_handoff, render_provider_handoff_prompt
from app.kernel.data_processing.semantic_raid import SemanticRaidStore
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.governance.governor_spine import (
    ComputeGovernorSpine,
    GovernorReceiptLog,
    Proposal,
    Episode,
    forensic_sink,
)
from app.kernel.workspaces import system_inspector
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.routes.ide_support.common import bounded_workspace_files as _bounded_workspace_files, extract_json_object as _extract_json_object, hash_text as _hash_text, is_compact_local_coder as _is_compact_local_coder, pair_programmer_limits as _pair_programmer_limits, raw_hash_text as _raw_hash_text, safe_relative as _safe_relative
from app.routes.ide_context import IdeRouteContext


def register_system_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _governed_kill = ctx._governed_kill
    _json_hash = ctx._json_hash
    _root = ctx._root

    @router.get("/edgek/ide/system-snapshot")
    async def edgek_ide_system_snapshot(root_path: str = None, process_query: str = "", port_limit: int = 60, process_limit: int = 30):
        root = _root(root_path)
        return await asyncio.to_thread(
            system_inspector.system_snapshot,
            root,
            port_limit=max(1, min(int(port_limit), 500)),
            process_limit=max(1, min(int(process_limit), 200)),
            process_query=process_query,
        )

    @router.get("/edgek/ide/ports")
    async def edgek_ide_ports(limit: int = 300):
        return await asyncio.to_thread(system_inspector.list_listening_ports, max(1, min(int(limit), 1000)))

    @router.get("/edgek/ide/processes")
    async def edgek_ide_processes(query: str = "", limit: int = 120, sort: str = "memory"):
        return await asyncio.to_thread(system_inspector.list_processes, query, max(1, min(int(limit), 500)), sort)

    @router.get("/edgek/ide/process/{pid}")
    async def edgek_ide_process_detail(pid: int):
        return await asyncio.to_thread(system_inspector.process_detail, int(pid))

    @router.get("/edgek/ide/environment")
    async def edgek_ide_environment(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.environment_report, root)

    @router.get("/edgek/ide/packages")
    async def edgek_ide_packages(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.package_report, root)

    @router.get("/edgek/ide/extensions")
    async def edgek_ide_extensions(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.extensions_report, root)

    @router.get("/edgek/ide/catalog")
    async def edgek_ide_catalog(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.catalog_report, root)

    @router.post("/edgek/ide/system/kill")
    async def edgek_ide_system_kill(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        pid = int(payload.get("pid") or 0)
        if pid <= 0:
            return {"ok": False, "error": "invalid_pid", "beast_object_type": "beast_ide_system_action"}
        return await _governed_kill(
            root,
            pid,
            str(payload.get("signal") or "TERM"),
            approved=bool(payload.get("approved", False)),
            operator_override=str(payload.get("operator_override") or ""),
            task_id=str(payload.get("task_id") or ""),
            dry_run=bool(payload.get("dry_run", False)),
            context="process_kill",
        )

    @router.post("/edgek/ide/ports/free")
    async def edgek_ide_ports_free(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        port = int(payload.get("port") or 0)
        if port <= 0:
            return {"ok": False, "error": "invalid_port", "beast_object_type": "beast_ide_system_action"}
        owners_payload = await asyncio.to_thread(system_inspector.find_port_owners, port)
        owners = owners_payload.get("owners") or []
        approved = bool(payload.get("approved", False))
        dry_run = bool(payload.get("dry_run", False))
        sig = str(payload.get("signal") or "TERM")
        if not owners:
            return {"ok": False, "error": "no_listener", "port": port, "owners": [], "beast_object_type": "beast_ide_system_action"}
        results = []
        for owner in owners:
            owner_pid = int(owner.get("pid") or 0)
            if owner_pid <= 0:
                continue
            results.append(await _governed_kill(
                root,
                owner_pid,
                sig,
                approved=approved,
                operator_override=str(payload.get("operator_override") or ""),
                task_id=str(payload.get("task_id") or ""),
                dry_run=dry_run,
                context=f"port_free:{port}",
            ))
        return {
            "ok": all(item.get("ok") for item in results) if results else False,
            "beast_object_type": "beast_ide_port_free",
            "version": "1.0",
            "port": port,
            "owner_count": len(owners),
            "results": results,
            "dry_run": dry_run,
        }

    @router.get("/edgek/ide/terminal/stream")
    async def edgek_ide_terminal_stream(
        root_path: str = None,
        command: str = "",
        cwd: str = "",
        timeout: int = 120,
        task_id: str = "",
        mode: str = "operator",
        approved: bool = False,
        operator_override: str = "",
    ):
        root = _root(root_path)
        run_cwd = Path(cwd or root).expanduser().resolve()
        try:
            run_cwd.relative_to(root)
        except ValueError:
            run_cwd = root
        bounded_timeout = max(1, min(int(timeout or 120), 900))
        command_text = str(command or "").strip()

        async def emit():
            started = time.time()

            def sse(event: str, payload: dict[str, Any]) -> str:
                return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

            if not command_text:
                yield sse("error", {"ok": False, "error": "empty command"})
                return
            # Server-side authorization is mandatory. The client-side
            # classification and caller-supplied approval flag are not trusted.
            safety = await asyncio.to_thread(
                SafetyGovernor(root).classify_command,
                command_text,
                mode=mode,
                task_id=task_id,
            )
            decision = str(safety.get("decision") or "block")
            if decision != "allow":
                yield sse("error", {
                    "ok": False,
                    "error": "terminal_stream_not_authorized",
                    "decision": decision,
                    "safety": safety,
                })
                return

            # Admit the exact command and workspace through Compute Governor.
            # Execution remains disabled until the admitted async runner is
            # integrated and tested.
            spine = ComputeGovernorSpine(
                receipts=GovernorReceiptLog(
                    root / ".beast" / "governor" / "receipts.jsonl",
                    sinks=[forensic_sink(root / ".beast" / "evidence" / "governor")],
                )
            )
            proposal = Proposal(
                kind="command",
                lane="operator",
                command=command_text,
                safety=safety,
                approved=False,
                signature_material={"cwd": str(run_cwd)},
            )
            admission = await asyncio.to_thread(
                spine.admit,
                Episode(run_id=task_id or "terminal_stream"),
                proposal,
            )
            if not admission.permits():
                yield sse("error", {
                    "ok": False,
                    "error": f"governor_{admission.outcome}",
                    "safety": safety,
                    "governor": admission.to_dict(),
                })
                return

            # V1: explicitly bounded, diagnostic-only executable commands.
            # No shell, redirects, pipes, scripts, or caller-supplied approval.
            try:
                argv = shlex.split(command_text)
            except ValueError:
                yield sse("error", {"ok": False, "error": "invalid_command_syntax"})
                return

            permitted = {
                ("pwd",),
                ("git", "--version"),
                ("node", "--version"),
                ("python", "--version"),
                ("python3", "--version"),
            }

            if tuple(argv) not in permitted:
                yield sse("error", {
                    "ok": False,
                    "error": "terminal_stream_command_not_in_v1_allowlist",
                })
                return

            if admission.outcome != "admit" or not admission.permits():
                yield sse("error", {
                    "ok": False,
                    "error": "terminal_stream_admission_not_enforced",
                    "governor": admission.to_dict(),
                })
                return

            executable = shutil.which(argv[0])
            if not executable:
                yield sse("error", {
                    "ok": False,
                    "error": "executable_not_found",
                })
                return

            import signal

            process = None
            stdout_chunks = []
            stderr_chunks = []
            timed_out = False
            returncode = None

            def terminate_group():
                if process is not None and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

            try:
                def launch():
                    return subprocess.Popen(
                        [executable, *argv[1:]],
                        cwd=str(run_cwd),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,
                        shell=False,
                    )

                # The subprocess is created inside the admitted callback.
                process = spine.run_admitted(admission, proposal, launch)

                yield sse("start", {
                    "ok": True,
                    "command": command_text,
                    "cwd": str(run_cwd),
                    "task_id": task_id,
                    "mode": mode,
                    "approved": False,
                    "timeout": bounded_timeout,
                    "governor": admission.to_dict(),
                })

                queue = asyncio.Queue()

                async def pump(stream, name, sink):
                    while True:
                        chunk = await asyncio.to_thread(stream.readline)
                        if not chunk:
                            break
                        value = chunk.decode("utf-8", errors="replace")
                        sink.append(value)
                        del sink[:-400]
                        await queue.put(("chunk", {
                            "stream": name,
                            "text": value,
                        }))

                stdout_task = asyncio.create_task(
                    pump(process.stdout, "stdout", stdout_chunks)
                )
                stderr_task = asyncio.create_task(
                    pump(process.stderr, "stderr", stderr_chunks)
                )
                wait_task = asyncio.create_task(
                    asyncio.to_thread(process.wait)
                )

                deadline = time.monotonic() + bounded_timeout

                while True:
                    if wait_task.done() and stdout_task.done() and stderr_task.done() and queue.empty():
                        break

                    if time.monotonic() >= deadline and not wait_task.done():
                        timed_out = True
                        terminate_group()

                    try:
                        event, payload = await asyncio.wait_for(
                            queue.get(), timeout=0.1
                        )
                        yield sse(event, payload)
                    except asyncio.TimeoutError:
                        yield sse("heartbeat", {
                            "running": not wait_task.done(),
                            "elapsed_ms": int((time.time() - started) * 1000),
                        })

                returncode = int(await wait_task)
                await stdout_task
                await stderr_task

            except asyncio.CancelledError:
                terminate_group()
                raise
            except Exception as exc:
                terminate_group()
                yield sse("error", {
                    "ok": False,
                    "error": "terminal_stream_execution_failed",
                    "detail": type(exc).__name__,
                    "governor": admission.to_dict(),
                })
                return
            finally:
                if process is not None:
                    if process.poll() is None:
                        terminate_group()
                    for stream in (process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()

            duration_ms = int((time.time() - started) * 1000)
            result = {
                "ok": returncode == 0 and not timed_out,
                "command": command_text,
                "cwd": str(run_cwd),
                "returncode": returncode,
                "duration_ms": duration_ms,
                "timeout": bounded_timeout,
                "timed_out": timed_out,
                "stdout": "".join(stdout_chunks)[-12000:],
                "stderr": "".join(stderr_chunks)[-12000:],
                "safety": {
                    "mode": mode,
                    "approved": False,
                    "operator_override": "",
                    "streamed": True,
                    "diagnostic_only": True,
                },
                "governor": admission.to_dict(),
            }

            out_dir = root / ".beast" / "ide" / "terminal"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / (
                f"terminal_{int(time.time())}_"
                f"{_raw_hash_text(command_text)[:10]}.json"
            )
            out_path.write_text(
                json.dumps(result, indent=2, sort_keys=True, default=str) + "\\n",
                encoding="utf-8",
            )
            receipt = EvidenceBus(root).register(
                artifact_type="beast_governed_terminal_execution",
                artifact_path=out_path,
                artifact_hash=_json_hash(result),
                source="governed_terminal",
                task_id=task_id or "desktop_terminal",
                status="ok" if result["ok"] else "failed",
                summary=f"Streamed terminal command: {command_text[:140]}",
                metadata={
                    "returncode": returncode,
                    "duration_ms": duration_ms,
                    "timed_out": timed_out,
                    "governor_receipt_id": admission.receipt_id,
                },
            )
            yield sse("done", {
                **result,
                "evidence_receipt": receipt,
                "path": str(out_path),
            })

        return StreamingResponse(emit(), media_type="text/event-stream")
    return None
