"""Per-trial lazy graph for the isolated navigation experiment."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from app.kernel.data_processing.workspace_graph import WorkspaceGraph

GRAPH_TOOL = "worktree.graph_lookup"
MAX_LOOKUPS = 3
MAX_BYTES = 1200


def _size(value):
    return len(json.dumps(value, ensure_ascii=True).encode())


class BoundedWorktreeGraph:
    def __init__(self, root: Path, tracked_paths: set[str], db_path: Path):
        self.root = root.resolve(strict=True)
        self.paths = frozenset(tracked_paths)
        self.db_path = db_path
        self.graph = None
        self.index_seconds = None
        self.lookup_seconds = []
        self.requests = self.builds = self.successes = self.result_bytes = 0

    def stats(self):
        return {
            "graph_lookup_requests": self.requests,
            "graph_lookup_successes": self.successes,
            "graph_lookup_result_bytes": self.result_bytes,
            "graph_index_builds": self.builds,
            "cold_index_seconds": self.index_seconds,
            "indexed_snapshot_lookup_seconds": sum(self.lookup_seconds) if self.lookup_seconds else None,
        }

    def lookup(self, query: str, *, pristine: bool = True) -> dict:
        if self.requests >= MAX_LOOKUPS:
            raise ValueError("graph lookup limit reached")
        self.requests += 1
        if not pristine:
            raise ValueError("graph lookup is only available on the initial worktree revision")
        is_path = query in self.paths
        if not is_path and not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,95}", query):
            raise ValueError("use an exact tracked Python path or exact symbol name")

        if self.graph is None:
            if self.db_path.exists():
                raise ValueError("graph index already exists outside the current trial")
            start = time.perf_counter()
            self.builds += 1
            graph = WorkspaceGraph(str(self.db_path))
            try:
                indexed = graph.index_repository(str(self.root), max_files=60, include_patterns=["*.py"])
                if indexed["errors"] or indexed["indexed_files"] != len(self.paths):
                    raise ValueError("bounded graph did not index the expected worktree")
                self.graph = graph
            finally:
                self.index_seconds = round(time.perf_counter() - start, 6)

        start = time.perf_counter()
        repo_id = f"repo:{self.root}"
        if is_path:
            anchors = [query]
        else:
            anchors = sorted({
                node["properties"]["file"]
                for node in self.graph.search_nodes(query, node_type="symbol", limit=30)
                if node["label"] == query and node["properties"].get("file") in self.paths
            })[:3]

        edges, symbols = set(), set()
        for anchor in anchors:
            center = self.graph._file_node_id(repo_id, anchor)
            hood = self.graph.neighborhood(center, limit=96)
            nodes = {node["id"]: node for node in hood["nodes"]}
            for edge in hood["edges"]:
                origin, target = nodes.get(edge["source"]), nodes.get(edge["target"])
                if origin is None or target is None:
                    continue
                if edge["relation"] == "depends_on" and origin["label"] in self.paths and target["label"] in self.paths:
                    edges.add((origin["label"], target["label"]))
                if edge["relation"] == "defines_symbol" and edge["source"] == center:
                    line = target["properties"].get("line")
                    if isinstance(line, int):
                        symbols.add((anchor, line, target["label"]))

        result = {"files": anchors, "edges": [], "symbols": []}
        for src, dst in sorted(edges)[:8]:
            result["edges"].append({"from": src, "to": dst})
            if _size(result) > MAX_BYTES:
                result["edges"].pop()
                break
        for path, line, name in sorted(symbols, key=lambda x: (x[2] != query, x))[:6]:
            result["symbols"].append({"path": path, "line": line, "name": name})
            if _size(result) > MAX_BYTES:
                result["symbols"].pop()
                break
        self.lookup_seconds.append(round(time.perf_counter() - start, 6))
        self.successes += bool(anchors)
        self.result_bytes += _size(result)
        return result
