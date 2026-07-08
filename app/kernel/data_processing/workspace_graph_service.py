"""Long-lived workspace graph service for gateway/TUI/MCP callers.

This is intentionally dependency-free. It provides a polling watcher and cached
workspace state around WorkspaceGraph before BEAST grows a separate daemon
process.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.data_processing.workspace_graph import WorkspaceGraph


class WorkspaceGraphService:
    """Small in-process service wrapper around WorkspaceGraph."""

    def __init__(self, graph: WorkspaceGraph, default_root: str | Path = ".") -> None:
        self.graph = graph
        self.default_root = Path(default_root).resolve()
        self.roots: Dict[str, Dict[str, Any]] = {}
        self.last_events: List[Dict[str, Any]] = []

    def _root(self, root_path: str | Path | None = None) -> Path:
        return Path(root_path or self.default_root).expanduser().resolve()

    def _root_state(self, root: Path) -> Dict[str, Any]:
        key = str(root)
        state = self.roots.setdefault(key, {
            "root_path": key,
            "last_indexed_at": 0.0,
            "last_indexed_ns": 0,
            "last_index_result": {},
            "last_poll_at": 0.0,
            "poll_count": 0,
            "event_count": 0,
        })
        return state

    def status(self, root_path: str | Path | None = None) -> Dict[str, Any]:
        root = self._root(root_path)
        state = self._root_state(root)
        return {
            "beast_object_type": "workspace_graph_service_status",
            "root_path": str(root),
            "active_roots": sorted(self.roots),
            "state": state,
            "graph": self.graph.stats(),
            "recent_events": self.last_events[-20:],
        }

    def index(
        self,
        root_path: str | Path | None = None,
        max_files: int = 1000,
        include_patterns: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        root = self._root(root_path)
        result = self.graph.index_repository(
            str(root),
            max_files=max_files,
            include_patterns=include_patterns,
            exclude_dirs=exclude_dirs,
        )
        state = self._root_state(root)
        now = time.time()
        state["last_indexed_at"] = now
        state["last_indexed_ns"] = int(now * 1_000_000_000)
        state["last_index_result"] = result
        return {**result, "service": {"root_path": str(root), "last_indexed_at": now}}

    def poll(
        self,
        root_path: str | Path | None = None,
        *,
        max_files: int = 1000,
        reindex: bool = True,
    ) -> Dict[str, Any]:
        root = self._root(root_path)
        state = self._root_state(root)
        previous_ns = int(state.get("last_indexed_ns") or 0)
        changed = self.graph.changed_since(str(root), timestamp_ns=previous_ns)
        stale = self.graph.stale_context_events(str(root))
        index_result: Dict[str, Any] = {}
        if reindex and (changed.get("changed_count") or stale.get("event_count")):
            index_result = self.index(str(root), max_files=max_files)
        now = time.time()
        events = []
        for item in changed.get("changed", [])[:100]:
            events.append({"event": "file_changed", "path": item.get("path"), "root_path": str(root), "status": item})
        for item in stale.get("events", [])[:100]:
            events.append({"event": "stale_context_warning", **item})
        if events:
            self.last_events.extend(events)
            self.last_events = self.last_events[-200:]
        state["last_poll_at"] = now
        state["poll_count"] = int(state.get("poll_count") or 0) + 1
        state["event_count"] = int(state.get("event_count") or 0) + len(events)
        return {
            "beast_object_type": "workspace_graph_service_poll",
            "root_path": str(root),
            "changed": changed,
            "stale_context": stale,
            "events": events,
            "event_count": len(events),
            "reindexed": bool(index_result),
            "index": index_result,
            "state": state,
        }

    def files(self, root_path: str | Path | None = None, limit: int = 200) -> Dict[str, Any]:
        root = self._root(root_path)
        query = str(root)
        nodes = [
            node for node in self.graph.search_nodes(query, node_type="file", limit=max(1, min(limit, 1000)))
            if (node.get("properties") or {}).get("repo") == str(root)
        ]
        return {"beast_object_type": "workspace_graph_service_files", "root_path": str(root), "files": nodes, "count": len(nodes)}

    def symbols(self, root_path: str | Path | None = None, q: str = "", limit: int = 100) -> Dict[str, Any]:
        root = self._root(root_path)
        query = q or str(root)
        nodes = [
            node for node in self.graph.search_nodes(query, node_type="symbol", limit=max(1, min(limit, 1000)))
            if not (node.get("properties") or {}).get("repo") or (node.get("properties") or {}).get("repo") == str(root)
        ]
        return {"beast_object_type": "workspace_graph_service_symbols", "root_path": str(root), "query": query, "symbols": nodes, "count": len(nodes)}

    def file(self, root_path: str | Path | None, path: str, max_chars: int = 12000) -> Dict[str, Any]:
        root = self._root(root_path)
        rel = str(path or "")
        status = self.graph.file_status(str(root), rel)
        target = (root / rel).resolve()
        content = ""
        ok = False
        error = ""
        try:
            if root != target and root not in target.parents:
                raise ValueError("path escaped workspace")
            content = target.read_text(encoding="utf-8", errors="replace")[: max(1, int(max_chars))]
            ok = True
        except Exception as exc:
            error = str(exc)
        return {
            "beast_object_type": "workspace_graph_service_file",
            "root_path": str(root),
            "path": rel,
            "ok": ok,
            "error": error,
            "content": content,
            "status": status,
        }

    def context(
        self,
        objective: str,
        root_path: str | Path | None = None,
        selected_files: Optional[List[str]] = None,
        token_budget: int = 3000,
        limit: int = 8,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # root_path is tracked for state even though graph_context currently
        # searches the whole graph; indexing before context keeps the root warm.
        root = self._root(root_path)
        self._root_state(root)
        return self.graph.graph_context_for_task(
            objective=objective,
            selected_files=selected_files,
            token_budget=token_budget,
            limit=limit,
            session_id=session_id,
        )
