"""Workspace, Code Cortex, registry, and worktree route family."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.cli.api import BeastApiClient
from app.kernel.data_processing.workspace_registry import repo_id_for_root
from app.kernel.workspaces.worktree_forge import WorktreeForge


def _quick_workspace_file_candidates(root: Path, limit: int) -> list[dict[str, Any]]:
    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
        ".next",
        ".cache",
        ".tox",
        "data",
        "logs",
        "tmp",
        "temp",
        ".idea",
    }
    allowed_ext = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
        ".txt",
        ".css",
        ".html",
        ".sh",
        ".ini",
        ".cfg",
        ".nginx",
        ".conf",
    }
    allowed_names = {"Dockerfile", "Makefile", "requirements.txt", "pyproject.toml"}
    secret_markers = ("secret", "token", "key", "credential", ".env", "vault")
    priority_roots = [
        "README.md",
        "requirements.txt",
        "pyproject.toml",
        "bin",
        "app",
        "desktop-ide",
        "tests",
        "docs",
        "catalog",
        "benchmarks",
        "vscode-extension",
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_file(path: Path, priority: int = 0) -> bool:
        try:
            if not path.is_file():
                return False
            rel = str(path.relative_to(root))
            rel_lower = rel.lower()
            if rel in seen or any(marker in rel_lower for marker in secret_markers):
                return False
            if path.suffix.lower() not in allowed_ext and path.name not in allowed_names:
                return False
            size = path.stat().st_size
            if size > 180_000:
                return False
            seen.add(rel)
            rows.append({"path": rel, "size": size, "ext": path.suffix.lower() or path.name, "priority": priority})
            return len(rows) >= limit
        except Exception:
            return False

    def walk_dir(path: Path, priority: int = 0) -> bool:
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [name for name in sorted(dirnames) if name not in skip_dirs]
                for name in sorted(filenames):
                    if add_file(Path(dirpath) / name, priority):
                        return True
        except Exception:
            return False
        return False

    for name in priority_roots:
        target = root / name
        if target.is_file():
            if add_file(target, -50):
                break
        elif target.is_dir() and walk_dir(target, -10):
            break
    if len(rows) < limit:
        walk_dir(root, 0)
    rows.sort(key=lambda item: (item.get("priority", 0), str(item.get("path", ""))))
    return rows[:limit]


def build_workspace_router(
    default_root: str | Path,
    *,
    workspace_graph_service: Any,
    workspace_graph: Any,
    workspace_registry: Any,
    code_cortex_router: Any,
    vector_memory: Any = None,
    trace_path: str | Path | None = None,
) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    @router.get("/edgek/workspace")
    async def edgek_workspace(limit: int = 20):
        return {
            "service": workspace_graph_service.status(),
            "stats": workspace_graph.stats(),
            "recent_nodes": workspace_graph.recent_nodes(limit=max(1, min(limit, 100))),
        }

    @router.get("/edgek/workspace/service")
    async def edgek_workspace_service(root_path: str = None):
        return workspace_graph_service.status(root_path)

    @router.get("/edgek/workspace/graph/stats")
    async def edgek_workspace_graph_stats():
        return workspace_graph_service.status()

    @router.get("/edgek/workspace/graph")
    async def edgek_workspace_graph(node_limit: int = 80, edge_limit: int = 160):
        return await asyncio.to_thread(
            workspace_graph.graph_snapshot,
            node_limit=max(1, min(int(node_limit), 500)),
            edge_limit=max(1, min(int(edge_limit), 1000)),
        )

    @router.post("/edgek/workspace/index")
    async def edgek_workspace_index(payload: Dict[str, Any] = None):
        payload = payload or {}
        return workspace_graph_service.index(
            root_path=payload.get("root_path") or str(fallback_root),
            max_files=max(1, min(int(payload.get("max_files", 1000)), 5000)),
            include_patterns=payload.get("include_patterns"),
            exclude_dirs=payload.get("exclude_dirs"),
        )

    @router.post("/edgek/workspace/poll")
    async def edgek_workspace_poll(payload: Dict[str, Any] = None):
        payload = payload or {}
        return workspace_graph_service.poll(
            root_path=payload.get("root_path") or str(fallback_root),
            max_files=max(1, min(int(payload.get("max_files", 1000)), 5000)),
            reindex=bool(payload.get("reindex", True)),
        )

    @router.post("/edgek/workspace/index-benchmark")
    async def edgek_workspace_index_benchmark(payload: Dict[str, Any] = None):
        payload = payload or {}
        return workspace_graph.benchmark_index_repository(
            root_path=payload.get("root_path") or str(fallback_root),
            max_files=max(1, min(int(payload.get("max_files", 5000)), 20000)),
            target_seconds=float(payload.get("target_seconds", 15.0)),
            include_patterns=payload.get("include_patterns"),
            exclude_dirs=payload.get("exclude_dirs"),
        )

    @router.get("/edgek/workspace/file-status")
    async def edgek_workspace_file_status(path: str, root_path: str = None):
        return workspace_graph.file_status(str(_root(root_path)), path)

    @router.get("/edgek/workspace/files")
    async def edgek_workspace_files(root_path: str = None, limit: int = 200):
        root = _root(root_path)
        capped_limit = max(1, min(limit, 2000))
        fallback = _quick_workspace_file_candidates(root, capped_limit)
        if not fallback:
            fallback = BeastApiClient("http://gateway-local", workspace=root).workspace_file_candidates(limit=capped_limit)
        normalized = [{**row, "source": "local_candidates"} for row in fallback]
        payload: Dict[str, Any] = {
            "beast_object_type": "workspace_files",
            "root_path": str(root),
            "files": normalized,
            "count": len(normalized),
            "fallback_used": True,
            "context_front_door": "local_candidates",
        }
        if normalized:
            return payload

        graph_payload = workspace_graph_service.files(str(root), limit=max(1, min(limit, 1000)))
        graph_files = graph_payload.get("files") if isinstance(graph_payload.get("files"), list) else []
        graph_rows = []
        for item in graph_files:
            if not isinstance(item, dict):
                continue
            props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            path = str(item.get("path") or item.get("file") or props.get("path") or props.get("relative_path") or props.get("file") or item.get("id") or "")
            if path:
                row = dict(item)
                row["path"] = path
                row["source"] = row.get("source") or "workspace_graph"
                graph_rows.append(row)
        return {
            **graph_payload,
            "beast_object_type": "workspace_files",
            "root_path": str(root),
            "files": graph_rows,
            "count": len(graph_rows),
            "fallback_used": False,
            "context_front_door": "workspace_graph",
        }

    @router.get("/edgek/workspace/file")
    async def edgek_workspace_file(path: str, root_path: str = None, max_chars: int = 12000):
        return workspace_graph_service.file(str(_root(root_path)), path, max_chars=max(1, min(max_chars, 100000)))

    @router.get("/edgek/workspace/symbols")
    async def edgek_workspace_symbols(root_path: str = None, q: str = "", limit: int = 100):
        return workspace_graph_service.symbols(str(_root(root_path)), q=q, limit=max(1, min(limit, 1000)))

    @router.post("/edgek/workspace/context")
    async def edgek_workspace_context(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        objective = str(payload.get("objective") or payload.get("query") or "")
        selected_files = [str(item) for item in (payload.get("selected_files") or payload.get("files") or [])]
        token_budget = max(256, min(int(payload.get("token_budget", 3000)), 32000))
        limit = max(1, min(int(payload.get("limit", 8)), 50))
        # Both reads may invoke an external indexer. Run them off the event
        # loop and in parallel: serial execution was enough to trip the
        # desktop's context-expansion timeout before a coding run even began.
        graph_task = asyncio.create_task(asyncio.to_thread(
            workspace_graph_service.context,
            objective=objective,
            root_path=str(root),
            selected_files=selected_files,
            token_budget=token_budget,
            limit=limit,
            session_id=str(payload.get("session_id") or "") or None,
        ))
        cortex_task = asyncio.create_task(asyncio.to_thread(
            code_cortex_router.get_editing_context,
            root,
            objective,
            limit=limit,
        ))
        interactive_timeout_ms = max(0, min(int(payload.get("interactive_timeout_ms", 0)), 10000))
        if interactive_timeout_ms:
            await asyncio.wait({graph_task, cortex_task}, timeout=interactive_timeout_ms / 1000)
        else:
            await asyncio.gather(graph_task, cortex_task)
        graph_context: Dict[str, Any] = {
            "beast_object_type": "workspace_graph_context",
            "selected_files": [{"path": path} for path in selected_files],
            "context_pending": True,
        }
        cortex_context: Dict[str, Any] = {
            "ok": False,
            "adapter": "pending",
            "files": [{"path": path} for path in selected_files],
            "context_pending": True,
        }
        if graph_task.done():
            try:
                graph_context = graph_task.result()
            except Exception as exc:
                graph_context["error"] = str(exc)
        if cortex_task.done():
            try:
                cortex_context = cortex_task.result()
            except Exception as exc:
                cortex_context["error"] = str(exc)
        graph_context["code_cortex"] = cortex_context
        graph_context["context_pending"] = not (graph_task.done() and cortex_task.done())
        graph_context["context_front_door"] = "code_cortex"
        return graph_context

    @router.post("/edgek/workspace/context-header")
    async def edgek_workspace_context_header(payload: Dict[str, Any] = None):
        """Return one explicit, metadata-first context suggestion contract.

        This endpoint is intentionally non-mutating: callers may show its
        ranked files/chunks, but must receive an operator's explicit selection
        before adding any suggestion to a provider prompt or edit scope.
        """
        payload = payload or {}
        root = _root(payload.get("root_path"))
        objective = str(payload.get("objective") or payload.get("query") or "").strip()
        selected_files = [str(item) for item in (payload.get("selected_files") or payload.get("files") or []) if item]
        limit = max(1, min(int(payload.get("limit", 8)), 24))
        token_budget = max(256, min(int(payload.get("token_budget", 3000)), 16000))
        context = await asyncio.to_thread(
            workspace_graph_service.context,
            objective=objective,
            root_path=str(root),
            selected_files=selected_files,
            token_budget=token_budget,
            limit=limit,
            session_id=None,
        )
        seen = set(selected_files)
        suggestions = []
        for item in context.get("results") or []:
            path = str(item.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            suggestions.append({
                "path": path,
                "reason": str(item.get("reason") or "retrieval_match"),
                "language": str(item.get("language") or ""),
                "line": item.get("line"),
                "end_line": item.get("end_line"),
                "selected": False,
                "requires_operator_acceptance": True,
            })
        vector_memory_result = {"result_count": 0, "hits": []}
        if vector_memory is not None and objective:
            vector_memory_result = await asyncio.to_thread(vector_memory.search, objective, limit=limit)
            for item in vector_memory_result.get("hits") or []:
                metadata = item.get("metadata") or {}
                path = str(metadata.get("file") or "")
                if not path or path in seen:
                    continue
                seen.add(path)
                suggestions.append({
                    "path": path,
                    "reason": "vector_memory_projection",
                    "language": "",
                    "line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "selected": False,
                    "requires_operator_acceptance": True,
                    "projection_backends": item.get("projection_backends") or [item.get("backend")],
                })
        return {
            "beast_object_type": "beast_context_header.v1",
            "version": "1.0",
            "objective": objective,
            "workspace": str(root),
            "retrieval_mode": "workspace_graph_metadata_first",
            "selected_files": selected_files,
            "suggestions": suggestions[:limit],
            "suggestion_count": min(len(suggestions), limit),
            "estimated_tokens": int(context.get("estimated_tokens") or 0),
            "operator_rule": "Suggestions are not provider context until explicitly accepted.",
            "context_receipt": {
                "result_count": int(context.get("result_count") or 0),
                "query": str(context.get("query") or objective),
            },
            "vector_memory": {
                "result_count": int(vector_memory_result.get("result_count") or 0),
                "diagnostics": vector_memory_result.get("diagnostics") or [],
                "authority_rule": vector_memory_result.get("authority_rule", "Retrieval remains advisory context."),
            },
        }

    @router.get("/edgek/code-cortex/status")
    async def edgek_code_cortex_status(root_path: str = None):
        return code_cortex_router.status(_root(root_path))

    @router.get("/edgek/code-cortex/symbols")
    async def edgek_code_cortex_symbols(q: str = "", root_path: str = None, limit: int = 50):
        return code_cortex_router.search_symbols(_root(root_path), q, limit=max(1, min(int(limit), 500)))

    @router.get("/edgek/code-cortex/file-summary")
    async def edgek_code_cortex_file_summary(path: str, root_path: str = None):
        return code_cortex_router.get_file_summary(_root(root_path), path)

    @router.get("/edgek/code-cortex/dependents")
    async def edgek_code_cortex_dependents(path: str, root_path: str = None, limit: int = 80):
        return code_cortex_router.get_dependents(_root(root_path), path, limit=max(1, min(int(limit), 500)))

    @router.get("/edgek/code-cortex/editing-context")
    async def edgek_code_cortex_editing_context(q: str, root_path: str = None, limit: int = 12):
        return code_cortex_router.get_editing_context(_root(root_path), q, limit=max(1, min(int(limit), 100)))

    @router.post("/edgek/code-cortex/symbol-plan")
    async def edgek_code_cortex_symbol_plan(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        result = BeastApiClient("http://gateway-local", workspace=root).build_symbol_surgeon_plan(
            str(payload.get("path") or ""),
            str(payload.get("symbol") or ""),
            str(payload.get("replacement") or ""),
            objective=str(payload.get("objective") or ""),
            provider=str(payload.get("provider") or "local_symbol_surgeon"),
        )
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "symbol plan failed")
        return result.data

    @router.get("/edgek/workspace/registry")
    async def edgek_workspace_registry():
        return workspace_registry.list()

    @router.post("/edgek/workspace/register")
    async def edgek_workspace_register(payload: Dict[str, Any] = None):
        payload = payload or {}
        root_path = payload.get("root_path") or str(fallback_root)
        graph_stats = {}
        if bool(payload.get("index", False)):
            graph_stats = workspace_graph_service.index(
                root_path=root_path,
                max_files=max(1, min(int(payload.get("max_files", 1000)), 5000)),
            )
        return workspace_registry.register(
            root_path=root_path,
            trust_level=str(payload.get("trust_level") or "local"),
            allowed_edit_scope=str(payload.get("allowed_edit_scope") or "read_write"),
            role=str(payload.get("role") or "primary"),
            graph_stats=graph_stats,
            contract_scan=bool(payload.get("contract_scan", True)),
        )

    @router.post("/edgek/workspace/context-pack")
    async def edgek_workspace_context_pack(payload: Dict[str, Any] = None):
        payload = payload or {}
        edit_root = payload.get("edit_root_path")
        edit_repo_id = str(payload.get("edit_repo_id") or (repo_id_for_root(edit_root) if edit_root else ""))
        files_by_repo = payload.get("files_by_repo") if isinstance(payload.get("files_by_repo"), dict) else {}
        return workspace_registry.build_context_pack(
            edit_repo_id=edit_repo_id,
            reference_repo_ids=[str(item) for item in (payload.get("reference_repo_ids") or [])],
            files_by_repo={
                str(key): [str(item) for item in value]
                for key, value in files_by_repo.items()
                if isinstance(value, list)
            },
            max_chars_each=max(1, min(int(payload.get("max_chars_each", 4000)), 50000)),
        )

    @router.post("/edgek/workspace/contract-mismatch")
    async def edgek_workspace_contract_mismatch(payload: Dict[str, Any] = None):
        payload = payload or {}
        provider_repo_id = str(payload.get("provider_repo_id") or "")
        consumer_repo_id = str(payload.get("consumer_repo_id") or "")
        if not provider_repo_id or not consumer_repo_id:
            raise HTTPException(status_code=400, detail="provider_repo_id and consumer_repo_id are required")
        return workspace_registry.contract_mismatch_receipt(provider_repo_id, consumer_repo_id)

    @router.post("/edgek/workspace/validate-sourceplan-scope")
    async def edgek_workspace_validate_sourceplan_scope(payload: Dict[str, Any] = None):
        payload = payload or {}
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        edit_repo_id = str(payload.get("edit_repo_id") or plan.get("edit_repo_id") or "")
        if not edit_repo_id and payload.get("edit_root_path"):
            edit_repo_id = repo_id_for_root(payload.get("edit_root_path"))
        if not edit_repo_id:
            raise HTTPException(status_code=400, detail="edit_repo_id or edit_root_path is required")
        return workspace_registry.validate_sourceplan_scope(
            plan,
            edit_repo_id=edit_repo_id,
            approved_multi_repo=bool(payload.get("approved_multi_repo") or plan.get("approved_multi_repo")),
        )

    @router.get("/edgek/workspace/changed-since")
    async def edgek_workspace_changed_since(root_path: str = None, timestamp_ns: int = 0):
        return workspace_graph.changed_since(str(_root(root_path)), timestamp_ns=timestamp_ns)

    @router.post("/edgek/workspace/context-consumption")
    async def edgek_workspace_context_consumption(payload: Dict[str, Any] = None):
        payload = payload or {}
        return workspace_graph.record_context_consumption(
            session_id=str(payload.get("session_id") or "default"),
            root_path=str(_root(payload.get("root_path"))),
            paths=[str(item) for item in (payload.get("paths") or payload.get("files") or [])],
            objective=str(payload.get("objective") or ""),
        )

    @router.get("/edgek/workspace/stale-context")
    async def edgek_workspace_stale_context(root_path: str = None, session_id: str = None):
        return workspace_graph.stale_context_events(str(_root(root_path)), session_id=session_id)

    @router.post("/edgek/workspace/rebuild")
    async def edgek_workspace_rebuild(payload: Dict[str, Any] = None):
        payload = payload or {}
        return workspace_graph.rebuild_from_traces(
            trace_path=payload.get("trace_path") or str(trace_path or fallback_root / "app" / "data" / "traces.jsonl"),
            clear_existing=bool(payload.get("clear_existing", False)),
        )

    @router.get("/edgek/workspace/export")
    async def edgek_workspace_export(node_limit: int = 1000, edge_limit: int = 2000):
        return workspace_graph.export_graph(
            node_limit=max(1, min(node_limit, 5000)),
            edge_limit=max(1, min(edge_limit, 10000)),
        )

    @router.get("/edgek/workspace/integrity")
    async def edgek_workspace_integrity(sample_limit: int = 20):
        return workspace_graph.integrity_report(sample_limit=max(1, min(sample_limit, 100)))

    @router.get("/edgek/workspace/search")
    async def edgek_workspace_search(q: str, node_type: str = None, limit: int = 20):
        return {
            "query": q,
            "node_type": node_type,
            "context_front_door": "code_cortex",
            "code_cortex": code_cortex_router.get_editing_context(_root(), q, limit=max(1, min(limit, 50))),
            "results": workspace_graph.search_nodes(
                query=q,
                node_type=node_type,
                limit=max(1, min(limit, 100)),
            ),
        }

    @router.get("/edgek/workspace/vector_search")
    async def edgek_workspace_vector_search(q: str, limit: int = 10):
        return {
            "query": q,
            "limit": limit,
            "context_front_door": "code_cortex",
            "code_cortex": code_cortex_router.get_editing_context(_root(), q, limit=max(1, min(limit, 50))),
            "results": workspace_graph.vector_search(
                query_text=q,
                limit=max(1, min(limit, 50)),
            ),
        }

    @router.post("/edgek/workspace/semantic-index")
    async def edgek_workspace_semantic_index(payload: Dict[str, Any] = None):
        payload = payload or {}
        result = workspace_graph.semantic_index_repository(
            root_path=payload.get("root_path") or str(fallback_root),
            max_files=max(1, min(int(payload.get("max_files", 200)), 2000)),
            max_chunks=max(1, min(int(payload.get("max_chunks", 1000)), 10000)),
            include_patterns=payload.get("include_patterns"),
            exclude_dirs=payload.get("exclude_dirs"),
        )
        if vector_memory is not None:
            projection_limit = max(1, min(int(payload.get("projection_limit", result.get("indexed_chunks", 0) or 1)), 50000))
            result["vector_memory"] = await asyncio.to_thread(
                vector_memory.ingest,
                workspace_graph.semantic_projection_records(limit=projection_limit),
                purpose="workspace_source",
            )
        return result

    @router.get("/edgek/workspace/semantic-context")
    async def edgek_workspace_semantic_context(
        q: str,
        limit: int = 8,
        include_content: bool = True,
        file_glob: str = None,
        node_type: str = None,
    ):
        vector_memory_result = await asyncio.to_thread(
            vector_memory.search, q, limit=max(1, min(limit, 50)), purposes=("workspace_source", "verified_skill")
        ) if vector_memory is not None else None
        return {
            "context_front_door": "code_cortex",
            "code_cortex": code_cortex_router.get_editing_context(_root(), q, limit=max(1, min(limit, 50))),
            "semantic_context": workspace_graph.semantic_context(
                query_text=q,
                limit=max(1, min(limit, 50)),
                include_content=include_content,
                file_glob=file_glob,
                node_types=[node_type] if node_type else None,
            ),
            "vector_memory": vector_memory_result,
        }

    @router.get("/edgek/vector/memory/health")
    async def edgek_vector_memory_health():
        if vector_memory is None:
            return {"beast_object_type": "vector_memory_health", "enabled": False, "backends": []}
        return await asyncio.to_thread(vector_memory.health)

    @router.post("/edgek/vector/memory/search")
    async def edgek_vector_memory_search(payload: Dict[str, Any] = None):
        payload = payload or {}
        query = str(payload.get("query") or payload.get("q") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        if vector_memory is None:
            return {"beast_object_type": "vector_memory_search", "query": query, "hits": [], "result_count": 0, "diagnostics": []}
        requested = payload.get("purposes") or ("workspace_source", "verified_skill")
        if not isinstance(requested, list | tuple):
            raise HTTPException(status_code=400, detail="purposes must be a list")
        return await asyncio.to_thread(
            vector_memory.search, query, limit=max(1, min(int(payload.get("limit", 8)), 50)), purposes=tuple(str(item) for item in requested)
        )

    @router.post("/edgek/vector/memory/operational-record")
    async def edgek_vector_memory_operational_record(payload: Dict[str, Any] = None):
        """Store a verified, sanitized L3 or L4 summary if cloud projection is enabled.

        This endpoint deliberately has no workspace-file input.  The adapter
        rejects raw source, prompts, patches, and logs before any backend call.
        """
        payload = payload or {}
        if vector_memory is None:
            return {"beast_object_type": "vector_memory_ingest", "enabled": False, "projections": []}
        purpose = str(payload.get("purpose") or "verified_skill")
        if purpose not in {"verified_skill", "forensic_summary"}:
            raise HTTPException(status_code=400, detail="purpose must be verified_skill or forensic_summary")
        record = payload.get("record") if isinstance(payload.get("record"), dict) else payload
        return await asyncio.to_thread(vector_memory.ingest, [record], purpose=purpose)

    @router.get("/edgek/workspace/nodes/{node_id:path}")
    async def edgek_workspace_node(node_id: str):
        node = workspace_graph.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Workspace graph node not found: {node_id}")
        return workspace_graph.neighborhood(node_id)

    @router.get("/edgek/worktree-forge/list")
    async def edgek_worktree_forge_list(root_path: str = None):
        return WorktreeForge(_root(root_path)).list()

    @router.get("/edgek/worktree-forge/status")
    async def edgek_worktree_forge_status(task_id: str, root_path: str = None):
        return WorktreeForge(_root(root_path)).status(task_id)

    @router.get("/edgek/worktree-forge/diff")
    async def edgek_worktree_forge_diff(task_id: str, root_path: str = None, max_chars: int = 40000):
        return WorktreeForge(_root(root_path)).diff(task_id, max_chars=max(1, min(int(max_chars), 200000)))

    @router.post("/edgek/worktree-forge/create")
    async def edgek_worktree_forge_create(payload: Dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).create(
            objective=str(payload.get("objective") or "BEAST isolated mission"),
            risk=str(payload.get("risk") or "medium"),
            provider=str(payload.get("provider") or ""),
            mode=str(payload.get("mode") or "implementer"),
            base_ref=str(payload.get("base_ref") or "HEAD"),
            task_id=str(payload.get("task_id") or ""),
        )

    @router.post("/edgek/worktree-forge/test")
    async def edgek_worktree_forge_test(payload: Dict[str, Any] = None):
        payload = payload or {}
        task_id = str(payload.get("task_id") or "")
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")
        command = payload.get("command") if isinstance(payload.get("command"), list) else None
        return WorktreeForge(_root(payload.get("root_path"))).test(
            task_id,
            command=[str(item) for item in command] if command else None,
            timeout=float(payload.get("timeout", 120.0)),
        )

    @router.post("/edgek/worktree-forge/promote")
    async def edgek_worktree_forge_promote(payload: Dict[str, Any] = None):
        payload = payload or {}
        task_id = str(payload.get("task_id") or "")
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")
        return WorktreeForge(_root(payload.get("root_path"))).promote(
            task_id,
            approved=bool(payload.get("approved", False)),
            require_tests=bool(payload.get("require_tests", True)),
        )

    @router.post("/edgek/worktree-forge/archive")
    async def edgek_worktree_forge_archive(payload: Dict[str, Any] = None):
        payload = payload or {}
        task_id = str(payload.get("task_id") or "")
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")
        return WorktreeForge(_root(payload.get("root_path"))).archive(task_id, reason=str(payload.get("reason") or ""))

    return router
