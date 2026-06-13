"""
EdgeK BEAST Gateway - Workspace Graph
Stores queryable L2 nodes and edges observed during gateway interactions.
"""

import json
import os
import re
import sqlite3
import hashlib
import time
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

try:
    import tree_sitter_language_pack as tsl
    _TREE_SITTER_PROVIDER = "tree-sitter-language-pack"
except ImportError:
    try:
        import tree_sitter_languages as tsl
        _TREE_SITTER_PROVIDER = "tree-sitter-languages"
    except ImportError:
        tsl = None
        _TREE_SITTER_PROVIDER = "unavailable"

# Initialize Tree-sitter parsers if available. The language-pack package works
# on Python 3.13; tree-sitter-languages remains a compatibility fallback.
_PARSERS = {}
if tsl is not None:
    try:
        for lang in ['python', 'javascript', 'typescript', 'java', 'c', 'cpp']:
            try:
                _PARSERS[lang] = tsl.get_parser(lang)
            except Exception:
                pass
    except Exception:
        _PARSERS = {}

EMBEDDING_MODEL = None
_EMBEDDING_MODEL_NAME = os.environ.get("EDGEK_SEMANTIC_MODEL", "all-MiniLM-L6-v2")
_EMBEDDING_ERROR: Optional[str] = None
_FILE_READ_CACHE_L1: Dict[str, tuple[str, float, str, int]] = {}
_FILE_READ_CACHE_TTL = 60.0
_FILE_READ_CACHE_L2_ENABLED = True


class WorkspaceGraph:
    """SQLite-backed graph for sessions, providers, models, policies, traces, and artifacts."""

    PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.@-]+(?:\.[A-Za-z0-9]+)?")
    PYTHON_SYMBOL_PATTERN = re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)

    # Tree-sitter query patterns for symbol extraction
    TS_SYMBOL_QUERIES = {
        'python': """
            (function_definition) @function
            (class_definition) @class
        """,
        'javascript': """
            (function_declaration) @function
            (class_declaration) @class
            (method_definition) @method
        """,
        'typescript': """
            (function_declaration) @function
            (class_declaration) @class
            (method_definition) @method
            (interface_declaration) @interface
        """,
        'java': """
            (method_declaration) @method
            (class_declaration) @class
            (interface_declaration) @interface
        """,
        'c': """
            (function_definition) @function
            (struct_specification) @struct
        """,
        'cpp': """
            (function_definition) @function
            (class_specifier) @class
            (struct_specifier) @struct
        """
    }

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "workspace_graph.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    observation_count INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    observation_count INTEGER DEFAULT 1,
                    UNIQUE(source_id, target_id, relation)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_contents (
                    file_path TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    size_bytes INTEGER,
                    mtime_ns INTEGER DEFAULT 0,
                    hit_count INTEGER DEFAULT 0,
                    last_hit_at TEXT
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(file_contents)").fetchall()}
            if "mtime_ns" not in columns:
                conn.execute("ALTER TABLE file_contents ADD COLUMN mtime_ns INTEGER DEFAULT 0")
            if "hit_count" not in columns:
                conn.execute("ALTER TABLE file_contents ADD COLUMN hit_count INTEGER DEFAULT 0")
            if "last_hit_at" not in columns:
                conn.execute("ALTER TABLE file_contents ADD COLUMN last_hit_at TEXT")

            # New table for embeddings linked to nodes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    vector BLOB NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (id) REFERENCES nodes(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_payload_fingerprints (
                    payload_hash TEXT PRIMARY KEY,
                    representative_hash TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    observation_count INTEGER DEFAULT 1
                )
            """)

    def observe_trace(self, trace_record: Dict[str, Any]) -> Dict[str, Any]:
        """Extract graph entities from a trace and upsert them."""
        timestamp = trace_record["timestamp"]
        session_id = f"session:{trace_record['session_id']}"
        trace_id = f"trace:{trace_record['trace_id']}"
        provider_id = f"provider:{trace_record['provider_type']}"
        ir = trace_record.get("edgek_ir", {})
        model = ir.get("model", "unknown")
        model_id = f"model:{model}"
        governance = trace_record.get("governance_result", {})
        context_economy = ir.get("metadata", {}).get("context_economy", {})

        nodes = [
            self.upsert_node(session_id, "session", trace_record["session_id"], {}, timestamp),
            self.upsert_node(trace_id, "trace", trace_record["trace_id"], {
                "decision": governance.get("decision"),
                "estimated_cost_usd": governance.get("budget_impact", {}).get("estimated_cost_usd", 0.0)
            }, timestamp),
            self.upsert_node(provider_id, "provider", trace_record["provider_type"], {}, timestamp),
            self.upsert_node(model_id, "model", model, {}, timestamp),
        ]
        edges = [
            self.upsert_edge(session_id, trace_id, "produced_trace", {}, timestamp),
            self.upsert_edge(trace_id, provider_id, "used_provider", {}, timestamp),
            self.upsert_edge(provider_id, model_id, "served_model", {}, timestamp),
            self.upsert_edge(trace_id, model_id, "used_model", {}, timestamp),
        ]

        for policy in governance.get("policies_applied", []):
            policy_id = f"policy:{policy}"
            nodes.append(self.upsert_node(policy_id, "policy", policy, {}, timestamp))
            edges.append(self.upsert_edge(trace_id, policy_id, "applied_policy", {}, timestamp))

        if context_economy:
            economy_id = f"context_economy:{'changed' if context_economy.get('changed') else 'unchanged'}"
            nodes.append(self.upsert_node(economy_id, "context_economy", economy_id.split(":", 1)[1], {
                "strategy": context_economy.get("strategy"),
                "within_input_budget": context_economy.get("within_input_budget")
            }, timestamp))
            edges.append(self.upsert_edge(trace_id, economy_id, "had_context_economy", {
                "original_tokens": context_economy.get("original_tokens", 0),
                "final_tokens": context_economy.get("final_tokens", 0)
            }, timestamp))

        file_nodes = self._extract_file_nodes(ir)
        for file_path in file_nodes:
            file_id = f"file:{file_path}"
            nodes.append(self.upsert_node(file_id, "file", file_path, {}, timestamp))
            edges.append(self.upsert_edge(trace_id, file_id, "mentioned_file", {}, timestamp))

        return {
            "nodes_added": nodes,
            "edges_added": edges,
            "node_count": len(nodes),
            "edge_count": len(edges)
        }

    def upsert_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        properties: Dict[str, Any],
        timestamp: str
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            existing = conn.execute("SELECT properties FROM nodes WHERE id = ?", (node_id,)).fetchone()
            merged_properties = properties
            if existing:
                merged_properties = self._merge_properties(json.loads(existing[0] or "{}"), properties)
                conn.execute("""
                    UPDATE nodes
                    SET label = ?, properties = ?, last_seen = ?, observation_count = observation_count + 1
                    WHERE id = ?
                """, (label, json.dumps(merged_properties, sort_keys=True), timestamp, node_id))
            else:
                conn.execute("""
                    INSERT INTO nodes (id, type, label, properties, first_seen, last_seen, observation_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (node_id, node_type, label, json.dumps(properties, sort_keys=True), timestamp, timestamp))
        return {"id": node_id, "type": node_type, "label": label}

    def upsert_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: Dict[str, Any],
        timestamp: str
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            existing = conn.execute("""
                SELECT id, properties FROM edges
                WHERE source_id = ? AND target_id = ? AND relation = ?
            """, (source_id, target_id, relation)).fetchone()
            if existing:
                merged_properties = self._merge_properties(json.loads(existing[1] or "{}"), properties)
                conn.execute("""
                    UPDATE edges
                    SET properties = ?, last_seen = ?, observation_count = observation_count + 1
                    WHERE id = ?
                """, (json.dumps(merged_properties, sort_keys=True), timestamp, existing[0]))
            else:
                conn.execute("""
                    INSERT INTO edges
                    (source_id, target_id, relation, properties, first_seen, last_seen, observation_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (source_id, target_id, relation, json.dumps(properties, sort_keys=True), timestamp, timestamp))
        return {"source": source_id, "target": target_id, "relation": relation}

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            node_types = conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall()
            edge_types = conn.execute("SELECT relation, COUNT(*) FROM edges GROUP BY relation").fetchall()
            cached_files = conn.execute("SELECT COUNT(*) FROM file_contents").fetchone()[0]
            cache_hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM file_contents").fetchone()[0]
            embedding_rows = conn.execute("SELECT COUNT(*), COUNT(DISTINCT model) FROM embeddings").fetchone()
            semantic_chunks = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'semantic_chunk'").fetchone()[0]
            dedupe_rows = conn.execute("SELECT COUNT(*) FROM semantic_payload_fingerprints").fetchone()[0]
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "node_types": {row[0]: row[1] for row in node_types},
            "edge_types": {row[0]: row[1] for row in edge_types},
            "tree_sitter": {
                "available": bool(_PARSERS),
                "provider": _TREE_SITTER_PROVIDER,
                "languages": sorted(_PARSERS.keys()),
            },
            "file_read_cache": {
                "l1_entries": len(_FILE_READ_CACHE_L1),
                "l2_entries": cached_files,
                "l2_hit_count": cache_hits or 0,
            },
            "semantic": {
                "available": self.semantic_available(load_model=False),
                "model": _EMBEDDING_MODEL_NAME,
                "loaded": EMBEDDING_MODEL is not None,
                "error": _EMBEDDING_ERROR,
                "embeddings": embedding_rows[0] or 0,
                "models": embedding_rows[1] or 0,
                "chunks": semantic_chunks,
                "payload_fingerprints": dedupe_rows,
            },
        }

    def recent_nodes(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, type, label, properties, last_seen, observation_count
                FROM nodes
                ORDER BY last_seen DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "id": row[0],
                "type": row[1],
                "label": row[2],
                "properties": json.loads(row[3] or "{}"),
                "last_seen": row[4],
                "observation_count": row[5]
            }
            for row in rows
        ]

    def export_graph(self, node_limit: int = 1000, edge_limit: int = 2000) -> Dict[str, Any]:
        """Export a bounded graph snapshot for visualization or inspection."""
        with self._connect() as conn:
            node_rows = conn.execute("""
                SELECT id, type, label, properties, first_seen, last_seen, observation_count
                FROM nodes
                ORDER BY observation_count DESC, last_seen DESC
                LIMIT ?
            """, (node_limit,)).fetchall()
            edge_rows = conn.execute("""
                SELECT source_id, target_id, relation, properties, first_seen, last_seen, observation_count
                FROM edges
                ORDER BY observation_count DESC, last_seen DESC
                LIMIT ?
            """, (edge_limit,)).fetchall()

        return {
            "stats": self.stats(),
            "node_limit": node_limit,
            "edge_limit": edge_limit,
            "nodes": [self._row_to_node(row) for row in node_rows],
            "edges": [self._row_to_edge(row) for row in edge_rows],
        }

    def integrity_report(self, sample_limit: int = 20) -> Dict[str, Any]:
        """Return graph integrity checks useful after indexing or trace backfills."""
        with self._connect() as conn:
            orphan_rows = conn.execute("""
                SELECT e.source_id, e.target_id, e.relation
                FROM edges e
                LEFT JOIN nodes source ON source.id = e.source_id
                LEFT JOIN nodes target ON target.id = e.target_id
                WHERE source.id IS NULL OR target.id IS NULL
                ORDER BY e.last_seen DESC
                LIMIT ?
            """, (sample_limit,)).fetchall()
            orphan_count = conn.execute("""
                SELECT COUNT(*)
                FROM edges e
                LEFT JOIN nodes source ON source.id = e.source_id
                LEFT JOIN nodes target ON target.id = e.target_id
                WHERE source.id IS NULL OR target.id IS NULL
            """).fetchone()[0]
            isolated_rows = conn.execute("""
                SELECT n.id, n.type, n.label, n.properties, n.first_seen, n.last_seen, n.observation_count
                FROM nodes n
                LEFT JOIN edges outgoing ON outgoing.source_id = n.id
                LEFT JOIN edges incoming ON incoming.target_id = n.id
                WHERE outgoing.id IS NULL AND incoming.id IS NULL
                ORDER BY n.last_seen DESC
                LIMIT ?
            """, (sample_limit,)).fetchall()
            isolated_count = conn.execute("""
                SELECT COUNT(*)
                FROM nodes n
                LEFT JOIN edges outgoing ON outgoing.source_id = n.id
                LEFT JOIN edges incoming ON incoming.target_id = n.id
                WHERE outgoing.id IS NULL AND incoming.id IS NULL
            """).fetchone()[0]

        return {
            "ok": orphan_count == 0,
            "orphan_edge_count": orphan_count,
            "orphan_edges": [
                {"source": row[0], "target": row[1], "relation": row[2]}
                for row in orphan_rows
            ],
            "isolated_node_count": isolated_count,
            "isolated_nodes": [self._row_to_node(row) for row in isolated_rows],
        }

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return a graph node by id."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT id, type, label, properties, first_seen, last_seen, observation_count
                FROM nodes
                WHERE id = ?
            """, (node_id,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def search_nodes(
        self,
        query: str,
        node_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search nodes by id or label."""
        like_query = f"%{query}%"
        params: List[Any] = [like_query, like_query]
        type_clause = ""
        if node_type:
            type_clause = "AND type = ?"
            params.append(node_type)
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT id, type, label, properties, first_seen, last_seen, observation_count
                FROM nodes
                WHERE (id LIKE ? OR label LIKE ?)
                {type_clause}
                ORDER BY observation_count DESC, last_seen DESC
                LIMIT ?
            """, params).fetchall()
        return [self._row_to_node(row) for row in rows]

    def neighborhood(self, node_id: str, limit: int = 50) -> Dict[str, Any]:
        """Return a one-hop graph neighborhood for a node."""
        center = self.get_node(node_id)
        if not center:
            return {"center": None, "nodes": [], "edges": []}

        with self._connect() as conn:
            edge_rows = conn.execute("""
                SELECT source_id, target_id, relation, properties, first_seen, last_seen, observation_count
                FROM edges
                WHERE source_id = ? OR target_id = ?
                ORDER BY last_seen DESC
                LIMIT ?
            """, (node_id, node_id, limit)).fetchall()

            neighbor_ids = set()
            for row in edge_rows:
                neighbor_ids.add(row[0])
                neighbor_ids.add(row[1])
            neighbor_ids.discard(node_id)

            nodes = [center]
            if neighbor_ids:
                placeholders = ",".join("?" for _ in neighbor_ids)
                node_rows = conn.execute(f"""
                    SELECT id, type, label, properties, first_seen, last_seen, observation_count
                    FROM nodes
                    WHERE id IN ({placeholders})
                """, tuple(neighbor_ids)).fetchall()
                nodes.extend(self._row_to_node(row) for row in node_rows)

        return {
            "center": center,
            "nodes": nodes,
            "edges": [self._row_to_edge(row) for row in edge_rows]
        }

    def context_for_ir(self, ir: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
        """Find graph context relevant to an IR-shaped dict."""
        files = self._extract_file_nodes(ir)
        matched_nodes = []
        seen = set()

        for file_path in files:
            node = self.get_node(f"file:{file_path}")
            if node and node["id"] not in seen:
                matched_nodes.append(node)
                seen.add(node["id"])

        if len(matched_nodes) < limit:
            model = ir.get("model")
            if model:
                node = self.get_node(f"model:{model}")
                if node and node["id"] not in seen:
                    matched_nodes.append(node)
                    seen.add(node["id"])

        query_text = self._query_text_from_ir(ir)
        semantic_matches = self.semantic_context(query_text, limit=limit, include_content=False)["results"] if query_text else []

        return {
            "matched_nodes": matched_nodes[:limit],
            "matched_node_count": len(matched_nodes),
            "mentioned_files": files,
            "semantic_matches": semantic_matches,
            "semantic_match_count": len(semantic_matches),
        }

    def index_repository(
        self,
        root_path: str,
        max_files: int = 1000,
        include_patterns: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Index repository files, directories, and lightweight symbols into the graph."""
        root = Path(root_path).resolve()
        timestamp = self._utc_now()
        include_patterns = include_patterns or [
            "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.md", "*.yaml", "*.yml", "*.json", "*.toml"
        ]
        exclude_dirs = set(exclude_dirs or [
            ".git", "__pycache__", ".pytest_cache", "venv", "node_modules", "data"
        ])

        root_id = f"repo:{root}"
        nodes = [
            self.upsert_node(root_id, "repository", root.name or str(root), {"path": str(root)}, timestamp)
        ]
        edges = []
        indexed_files = 0
        indexed_dirs = 0
        indexed_symbols = 0

        for path in root.rglob("*"):
            rel_path = path.relative_to(root).as_posix()
            if any(part in exclude_dirs for part in path.relative_to(root).parts):
                continue

            if path.is_dir():
                dir_id = f"directory:{rel_path}"
                nodes.append(self.upsert_node(dir_id, "directory", rel_path, {"path": rel_path}, timestamp))
                edges.append(self.upsert_edge(root_id, dir_id, "contains", {}, timestamp))
                parent_id = self._parent_directory_id(path, root)
                if parent_id:
                    edges.append(self.upsert_edge(parent_id, dir_id, "contains", {}, timestamp))
                indexed_dirs += 1
                continue

            if not path.is_file() or indexed_files >= max_files:
                continue
            if not any(path.match(pattern) for pattern in include_patterns):
                continue

            file_id = f"file:{rel_path}"
            stat = path.stat()
            nodes.append(self.upsert_node(file_id, "file", rel_path, {
                "path": rel_path,
                "suffix": path.suffix,
                "size_bytes": stat.st_size,
                "mtime": int(stat.st_mtime)
            }, timestamp))
            edges.append(self.upsert_edge(root_id, file_id, "contains", {}, timestamp))
            parent_id = self._parent_directory_id(path, root)
            if parent_id:
                edges.append(self.upsert_edge(parent_id, file_id, "contains", {}, timestamp))
            indexed_files += 1

            if stat.st_size <= 200000:
                symbol_count = self._index_symbols(path, rel_path, file_id, timestamp)
                indexed_symbols += symbol_count

        return {
            "repository": str(root),
            "indexed_files": indexed_files,
            "indexed_directories": indexed_dirs,
            "indexed_symbols": indexed_symbols,
            "nodes_touched": len(nodes) + indexed_symbols,
            "edges_touched": len(edges) + indexed_symbols
        }

    def semantic_index_repository(
        self,
        root_path: str,
        max_files: int = 200,
        max_chunks: int = 1000,
        include_patterns: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build a semantic chunk index for RAG/context selection."""
        root = Path(root_path).resolve()
        include_patterns = include_patterns or [
            "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.md", "*.yaml", "*.yml", "*.json", "*.toml", "*.java", "*.c", "*.cpp", "*.h", "*.hpp"
        ]
        exclude_dirs = set(exclude_dirs or [
            ".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules", "data"
        ])
        timestamp = self._utc_now()
        self.upsert_node(f"repo:{root}", "repository", root.name or str(root), {"path": str(root)}, timestamp)

        indexed_files = 0
        indexed_chunks = 0
        skipped_files = 0
        errors = 0
        if not self.semantic_available(load_model=True):
            return {
                "repository": str(root),
                "semantic_available": False,
                "model": _EMBEDDING_MODEL_NAME,
                "error": _EMBEDDING_ERROR,
                "indexed_files": 0,
                "indexed_chunks": 0,
                "skipped_files": 0,
                "errors": 0,
            }

        for path in root.rglob("*"):
            if indexed_files >= max_files or indexed_chunks >= max_chunks:
                break
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if any(part in exclude_dirs for part in rel.parts):
                continue
            if not path.is_file() or not any(path.match(pattern) for pattern in include_patterns):
                continue
            try:
                stat = path.stat()
                if stat.st_size <= 0 or stat.st_size > 1024 * 1024:
                    skipped_files += 1
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errors += 1
                continue

            rel_path = rel.as_posix()
            file_id = f"file:{rel_path}"
            self.upsert_node(file_id, "file", rel_path, {
                "path": rel_path,
                "suffix": path.suffix,
                "size_bytes": stat.st_size,
                "mtime": int(stat.st_mtime),
            }, timestamp)
            indexed_files += 1

            chunks = self._chunk_text(content, rel_path)
            for chunk in chunks:
                if indexed_chunks >= max_chunks:
                    break
                chunk_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
                chunk_id = f"semantic_chunk:{rel_path}:{chunk['start_line']}:{chunk_hash[:12]}"
                self.upsert_node(chunk_id, "semantic_chunk", f"{rel_path}:{chunk['start_line']}-{chunk['end_line']}", {
                    "file": rel_path,
                    "absolute_path": str(path),
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "content_hash": chunk_hash,
                    "preview": chunk["text"][:320],
                }, timestamp)
                self.upsert_edge(file_id, chunk_id, "has_semantic_chunk", {}, timestamp)
                embedding = self._generate_embedding(chunk["text"])
                if embedding:
                    self._store_embedding(chunk_id, embedding)
                    indexed_chunks += 1

        return {
            "repository": str(root),
            "semantic_available": True,
            "model": _EMBEDDING_MODEL_NAME,
            "indexed_files": indexed_files,
            "indexed_chunks": indexed_chunks,
            "skipped_files": skipped_files,
            "errors": errors,
        }

    def rebuild_from_traces(self, trace_path: str, clear_existing: bool = False) -> Dict[str, Any]:
        """Rebuild or backfill graph observations from a JSONL trace archive."""
        path = Path(trace_path)
        if clear_existing:
            self.clear()
        if not path.exists():
            return {"trace_path": str(path), "processed_traces": 0, "errors": 0}

        processed = 0
        errors = 0
        nodes_touched = 0
        edges_touched = 0
        with path.open("r", encoding="utf-8") as trace_file:
            for line in trace_file:
                if not line.strip():
                    continue
                try:
                    result = self.observe_trace(json.loads(line))
                    processed += 1
                    nodes_touched += result["node_count"]
                    edges_touched += result["edge_count"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    errors += 1

        return {
            "trace_path": str(path),
            "processed_traces": processed,
            "errors": errors,
            "nodes_touched": nodes_touched,
            "edges_touched": edges_touched
        }

    def clear(self):
        """Clear graph nodes and edges."""
        with self._connect() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")

    def _extract_file_nodes(self, ir: Dict[str, Any]) -> List[str]:
        files = set()
        for message in ir.get("messages") or []:
            content = message.get("content", "")
            if not isinstance(content, str):
                continue
            for match in self.PATH_PATTERN.findall(content):
                if len(match) <= 240:
                    files.add(match.strip(".,:;)'\"]"))
        return sorted(files)

    def _merge_properties(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(existing)
        for key, value in new.items():
            if value is not None:
                merged[key] = value
        return merged

    def _get_language_from_path(self, path: Path) -> Optional[str]:
        """Map file extension to language name for Tree-sitter."""
        suffix = path.suffix.lower()
        if suffix == '.py':
            return 'python'
        elif suffix in ['.js', '.jsx']:
            return 'javascript'
        elif suffix in ['.ts', '.tsx']:
            return 'typescript'
        elif suffix == '.java':
            return 'java'
        elif suffix in ['.c', '.h']:
            return 'c'
        elif suffix in ['.cpp', '.cc', '.cxx', '.hpp', '.hxx']:
            return 'cpp'
        else:
            return None

    def _index_symbols(self, path: Path, rel_path: str, file_id: str, timestamp: str, language: Optional[str] = None) -> int:
        """Index symbols in a file using Tree-sitter when available, fallback to regex."""
        if language is None:
            language = self._get_language_from_path(path)
        if language is None:
            return 0

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return 0

        # Use Tree-sitter if available for this language
        if language in _PARSERS and _PARSERS[language] is not None:
            try:
                parser = _PARSERS[language]
                tree = parser.parse(bytes(content, "utf8"))
                root_node = tree.root_node

                count = 0
                # Define capture queries for different languages
                # This is a simplified version - in production we'd use proper Tree-sitter queries
                query_string = self.TS_SYMBOL_QUERIES.get(language, "")
                if query_string:
                    # For simplicity, we're extracting all nodes and filtering by type
                    # A real implementation would use Tree-sitter query API
                    def walk_tree(node):
                        nonlocal count
                        if node.type in ['function_definition', 'class_definition', 'method_definition',
                                       'function_declaration', 'class_declaration', 'interface_declaration',
                                       'struct_specification', 'class_specifier']:
                            # Extract symbol name based on node type and language
                            symbol_name = None
                            if language == 'python':
                                if node.type == 'function_definition':
                                    # Look for identifier child
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                                elif node.type == 'class_definition':
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                            elif language in ['javascript', 'typescript']:
                                if node.type in ['function_declaration', 'class_declaration', 'method_definition']:
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                                elif node.type == 'interface_declaration':
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                            elif language == 'java':
                                if node.type in ['method_declaration', 'class_declaration', 'interface_declaration']:
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                            elif language == 'c':
                                if node.type == 'function_definition':
                                    for child in node.children:
                                        if child.type == 'function_declarator':
                                            for grandchild in child.children:
                                                if grandchild.type == 'identifier':
                                                    symbol_name = grandchild.text.decode('utf8')
                                                    break
                                            break
                                elif node.type == 'struct_specification':
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break
                            elif language == 'cpp':
                                if node.type == 'function_definition':
                                    for child in node.children:
                                        if child.type == 'function_declarator':
                                            for grandchild in child.children:
                                                if grandchild.type == 'identifier':
                                                    symbol_name = grandchild.text.decode('utf8')
                                                    break
                                            break
                                elif node.type in ['class_specifier', 'struct_specifier']:
                                    for child in node.children:
                                        if child.type == 'identifier':
                                            symbol_name = child.text.decode('utf8')
                                            break

                            if symbol_name:
                                line_number = content.count("\n", 0, node.start_byte) + 1
                                symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_number}"
                                self.upsert_node(symbol_id, "symbol", symbol_name, {
                                    "file": rel_path,
                                    "line": line_number,
                                    "language": language
                                }, timestamp)
                                self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                                count += 1

                        for child in node.children:
                            walk_tree(child)

                    walk_tree(root_node)
                    return count
            except Exception:
                # Fall back to regex-based extraction on any Tree-sitter error
                pass

        # Fallback regex-based symbol extraction
        return self._index_symbols_regex(content, rel_path, file_id, timestamp, language)

    def _index_symbols_regex(self, content: str, rel_path: str, file_id: str, timestamp: str, language: str) -> int:
        """Fallback regex-based symbol extraction for when Tree-sitter is not available or fails."""
        count = 0
        lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if language == 'python':
                # Function definitions
                if stripped.startswith(('def ', 'async def ')):
                    # Extract function name
                    parts = stripped.split()[1].split('(')[0]
                    if parts:
                        symbol_name = parts
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1
                # Class definitions
                elif stripped.startswith('class '):
                    # Extract class name
                    parts = stripped.split()[1].split('(')[0].split(':')[0]
                    if parts:
                        symbol_name = parts
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1

            elif language in ['javascript', 'typescript']:
                # Function declarations
                if stripped.startswith(('function ', 'async function ')):
                    # Extract function name
                    parts = stripped.split()[1].split('(')[0]
                    if parts:
                        symbol_name = parts
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1
                # Class declarations
                elif stripped.startswith('class '):
                    # Extract class name
                    parts = stripped.split()[1].split('(')[0].split(':')[0]
                    if parts:
                        symbol_name = parts
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1
                # Method definitions (crude)
                elif ' function ' in stripped or ' => ' in stripped:
                    # Very basic method detection
                    pass

            elif language == 'java':
                # Method declarations (crude)
                if (' public ' in stripped or ' private ' in stripped or ' protected ' in stripped) and '(' in stripped and ')' in stripped:
                    # Extract method name - very basic
                    before_paren = stripped.split('(')[0]
                    parts = before_paren.split()
                    if parts:
                        symbol_name = parts[-1]
                        # Filter out Java keywords
                        if symbol_name not in ['if', 'for', 'while', 'switch', 'return', 'new']:
                            symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                            self.upsert_node(symbol_id, "symbol", symbol_name, {
                                "file": rel_path,
                                "line": line_num,
                                "language": language
                            }, timestamp)
                            self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                            count += 1
                # Class declarations
                elif stripped.startswith(('public class ', 'private class ', 'class ')):
                    # Extract class name
                    parts = stripped.split()
                    for i, part in enumerate(parts):
                        if part == 'class':
                            if i+1 < len(parts):
                                symbol_name = parts[i+1].split('(')[0].split(':')[0]
                                symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                                self.upsert_node(symbol_id, "symbol", symbol_name, {
                                    "file": rel_path,
                                    "line": line_num,
                                    "language": language
                                }, timestamp)
                                self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                                count += 1
                            break

            elif language == 'c':
                # Function definitions
                if stripped.startswith(('int ', 'void ', 'char ', 'float ', 'double ')) and '(' in stripped:
                    # Extract function name - very basic
                    before_paren = stripped.split('(')[0]
                    parts = before_paren.split()
                    if parts:
                        symbol_name = parts[-1]
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1
                # Struct definitions
                elif stripped.startswith('struct '):
                    # Extract struct name
                    parts = stripped.split()
                    if len(parts) >= 2:
                        symbol_name = parts[1].split('{')[0]
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1

            elif language == 'cpp':
                # Function definitions
                if any(stripped.startswith(prefix) for prefix in ('int ', 'void ', 'char ', 'float ', 'double ', 'bool ', 'auto ')) and '(' in stripped:
                    # Extract function name - very basic
                    before_paren = stripped.split('(')[0]
                    parts = before_paren.split()
                    if parts:
                        symbol_name = parts[-1]
                        # Filter out template stuff and operators
                        if not any(c in symbol_name for c in '<>~'):
                            symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                            self.upsert_node(symbol_id, "symbol", symbol_name, {
                                "file": rel_path,
                                "line": line_num,
                                "language": language
                            }, timestamp)
                            self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                            count += 1
                # Class definitions
                elif any(stripped.startswith(prefix) for prefix in ('class ', 'struct ')):
                    # Extract class/struct name
                    parts = stripped.split()
                    if len(parts) >= 2:
                        symbol_name = parts[1].split('{')[0].split(':')[0]
                        symbol_id = f"symbol:{rel_path}:{symbol_name}:{line_num}"
                        self.upsert_node(symbol_id, "symbol", symbol_name, {
                            "file": rel_path,
                            "line": line_num,
                            "language": language
                        }, timestamp)
                        self.upsert_edge(file_id, symbol_id, "defines_symbol", {}, timestamp)
                        count += 1

        return count

    def _parent_directory_id(self, path: Path, root: Path) -> Optional[str]:
        parent = path.parent
        if parent == root:
            return f"repo:{root}"
        try:
            rel_parent = parent.relative_to(root).as_posix()
        except ValueError:
            return None
        return f"directory:{rel_parent}"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # New methods for Tree-sitter based symbol extraction
    def _extract_symbols_tree_sitter(self, content: str, language: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract symbols using Tree-sitter parser for supported languages."""
        if language not in _PARSERS or not _PARSERS[language]:
            return []

        try:
            parser = _PARSERS[language]
            tree = parser.parse(bytes(content, "utf8"))
            root_node = tree.root_node

            symbols = []
            query_string = self.TS_SYMBOL_QUERIES.get(language, "")
            if not query_string:
                return symbols

            # Note: In a real implementation, we'd use the tree_sitter Language API for queries
            # For now, we'll fall back to regex-based extraction for simplicity
            # This is a placeholder that demonstrates the integration point
            return self._extract_symbols_regex_fallback(content, language, file_path)
        except Exception:
            # Fall back to regex-based extraction on any error
            return self._extract_symbols_regex_fallback(content, language, file_path)

    def _extract_symbols_regex_fallback(self, content: str, language: str, file_path: str) -> List[Dict[str, Any]]:
        """Fallback regex-based symbol extraction when Tree-sitter is not available."""
        symbols = []
        line_number = 1

        for line in content.split('\n'):
            # Python-specific patterns
            if language == 'python':
                # Function definitions
                func_match = re.match(r'^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', line)
                if func_match:
                    symbols.append({
                        'name': func_match.group(1),
                        'type': 'function',
                        'line': line_number,
                        'file': file_path
                    })

                # Class definitions
                class_match = re.match(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]', line)
                if class_match:
                    symbols.append({
                        'name': class_match.group(1),
                        'type': 'class',
                        'line': line_number,
                        'file': file_path
                    })
            # JavaScript/TypeScript patterns
            elif language in ['javascript', 'typescript']:
                # Function declarations
                func_match = re.match(r'^\s*(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', line)
                if func_match:
                    symbols.append({
                        'name': func_match.group(1),
                        'type': 'function',
                        'line': line_number,
                        'file': file_path
                    })

                # Class declarations
                class_match = re.match(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)', line)
                if class_match:
                    symbols.append({
                        'name': class_match.group(1),
                        'type': 'class',
                        'line': line_number,
                        'file': file_path
                    })

                # Method definitions (in classes)
                method_match = re.match(r'^\s*\w+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*{', line)
                if method_match:
                    symbols.append({
                        'name': method_match.group(1),
                        'type': 'method',
                        'line': line_number,
                        'file': file_path
                    })
            # Java patterns
            elif language == 'java':
                # Method declarations
                method_match = re.match(r'^\s*(?:public\s+|private\s+|protected\s+|static\s+)+(?:[\w\<\>\[\]]+\s+)+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*{', line)
                if method_match:
                    symbols.append({
                        'name': method_match.group(1),
                        'type': 'method',
                        'line': line_number,
                        'file': file_path
                    })

                # Class declarations
                class_match = re.match(r'^\s*(?:public\s+|private\s+|protected\s+)?\s*class\s+([A-Za-z_][A-Za-z0-9_]*)', line)
                if class_match:
                    symbols.append({
                        'name': class_match.group(1),
                        'type': 'class',
                        'line': line_number,
                        'file': file_path
                    })

            line_number += 1

        return symbols

    def _query_text_from_ir(self, ir: Dict[str, Any]) -> str:
        parts = []
        for message in ir.get("messages") or []:
            content = message.get("content", "")
            if isinstance(content, str):
                parts.append(content)
        metadata = ir.get("metadata") or {}
        for key in ("objective", "task", "query"):
            if metadata.get(key):
                parts.append(str(metadata[key]))
        return "\n".join(parts).strip()

    def semantic_available(self, load_model: bool = False) -> bool:
        if load_model:
            return self._ensure_embedding_model() is not None
        if EMBEDDING_MODEL is not None:
            return True
        return importlib.util.find_spec("sentence_transformers") is not None

    def _ensure_embedding_model(self):
        global EMBEDDING_MODEL, _EMBEDDING_ERROR
        if EMBEDDING_MODEL is not None:
            return EMBEDDING_MODEL
        try:
            from sentence_transformers import SentenceTransformer
            EMBEDDING_MODEL = SentenceTransformer(_EMBEDDING_MODEL_NAME)
            _EMBEDDING_ERROR = None
        except Exception as exc:
            _EMBEDDING_ERROR = f"{type(exc).__name__}: {exc}"
            EMBEDDING_MODEL = None
        return EMBEDDING_MODEL

    def _chunk_text(self, content: str, file_path: str, max_chars: int = 1800, overlap_lines: int = 8) -> List[Dict[str, Any]]:
        lines = content.splitlines()
        chunks: List[Dict[str, Any]] = []
        start = 0
        while start < len(lines):
            current = []
            chars = 0
            end = start
            while end < len(lines) and chars + len(lines[end]) + 1 <= max_chars:
                current.append(lines[end])
                chars += len(lines[end]) + 1
                end += 1
            if not current and end < len(lines):
                current.append(lines[end][:max_chars])
                end += 1
            text = "\n".join(current).strip()
            if text:
                chunks.append({
                    "file": file_path,
                    "start_line": start + 1,
                    "end_line": end,
                    "text": text,
                })
            if end >= len(lines):
                break
            start = max(end - overlap_lines, start + 1)
        return chunks

    # New methods for semantic embedding generation
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate semantic embedding for text using sentence-transformers."""
        model = self._ensure_embedding_model()
        if model is None or not text.strip():
            return None

        try:
            embedding = model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception:
            return None

    def _store_embedding(self, node_id: str, embedding: List[float], model_name: str = "all-MiniLM-L6-v2"):
        """Store embedding in the database."""
        if not embedding:
            return

        import numpy as np

        try:
            # Convert list of floats to numpy array then to bytes
            vector_bytes = np.array(embedding, dtype=np.float32).tobytes()

            with self._connect() as conn:
                # Ensure foreign key constraints are enforced
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("""
                    INSERT OR REPLACE INTO embeddings (id, vector, model, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    node_id,
                    vector_bytes,
                    model_name,
                    self._utc_now()
                ))
        except Exception:
            # Silently fail if embedding storage fails
            pass

    def _get_embedding(self, node_id: str) -> Optional[List[float]]:
        """Retrieve embedding from database."""
        try:
            with self._connect() as conn:
                row = conn.execute("""
                    SELECT vector FROM embeddings WHERE id = ?
                """, (node_id,)).fetchone()

                if row:
                    import numpy as np
                    vector_bytes = row[0]
                    vector = np.frombuffer(vector_bytes, dtype=np.float32)
                    return vector.tolist()
        except Exception:
            pass
        return None

    def _vector_search(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Perform vector similarity search against stored embeddings."""
        if self._ensure_embedding_model() is None:
            return []

        query_embedding = self._generate_embedding(query_text)
        if not query_embedding:
            return []

        try:
            import numpy as np

            # Get all embeddings with their node info
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT n.id, n.type, n.label, n.properties, e.vector, e.model
                    FROM embeddings e
                    JOIN nodes n ON e.id = n.id
                """).fetchall()

                # Calculate similarities
                similarities = []
                query_vector = np.array(query_embedding, dtype=np.float32)

                for row in rows:
                    node_id, node_type, label, properties, vector_bytes, model = row
                    try:
                        vector = np.frombuffer(vector_bytes, dtype=np.float32)
                        # Cosine similarity
                        similarity = np.dot(query_vector, vector) / (np.linalg.norm(query_vector) * np.linalg.norm(vector))
                        similarities.append({
                            'node_id': node_id,
                            'type': node_type,
                            'label': label,
                            'properties': json.loads(properties or "{}"),
                            'similarity': float(similarity),
                            'model': model
                        })
                    except Exception:
                        continue

                # Sort by similarity descending and return top results
                similarities.sort(key=lambda x: x['similarity'], reverse=True)
                return similarities[:limit]
        except Exception:
            return []

    def vector_search(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Public method for vector similarity search."""
        return self._vector_search(query_text, limit)

    def semantic_context(self, query_text: str, limit: int = 8, include_content: bool = True, max_chars_per_chunk: int = 900) -> Dict[str, Any]:
        """Return compact semantic context chunks for a natural-language query."""
        results = self.vector_search(query_text, limit=limit)
        context = []
        for item in results:
            props = item.get("properties") or {}
            text = props.get("preview", "")
            if include_content and item["type"] == "semantic_chunk":
                text = self._content_for_semantic_chunk(props, max_chars_per_chunk=max_chars_per_chunk) or text
            context.append({
                "node_id": item["node_id"],
                "type": item["type"],
                "label": item["label"],
                "similarity": round(item["similarity"], 5),
                "file": props.get("file"),
                "start_line": props.get("start_line"),
                "end_line": props.get("end_line"),
                "content": text[:max_chars_per_chunk] if include_content else None,
            })
        return {
            "query": query_text,
            "semantic_available": self.semantic_available(load_model=False),
            "model": _EMBEDDING_MODEL_NAME,
            "results": context,
            "result_count": len(context),
        }

    def _content_for_semantic_chunk(self, props: Dict[str, Any], max_chars_per_chunk: int = 900) -> str:
        file_path = props.get("absolute_path") or props.get("file")
        if not file_path:
            return ""
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return str(props.get("preview") or "")
        start = max(1, int(props.get("start_line") or 1))
        end = max(start, int(props.get("end_line") or start))
        return "\n".join(lines[start - 1:end])[:max_chars_per_chunk]

    def semantic_dedupe_payloads(self, payloads: List[Any], similarity_threshold: float = 0.92) -> Dict[str, Any]:
        """Cluster repeated payloads by semantic similarity and exact hash."""
        seen_hashes: Dict[str, int] = {}
        representatives: List[Dict[str, Any]] = []
        decisions = []
        for idx, payload in enumerate(payloads):
            text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, default=str)
            payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if payload_hash in seen_hashes:
                decisions.append({
                    "index": idx,
                    "decision": "duplicate_exact",
                    "representative": seen_hashes[payload_hash],
                    "similarity": 1.0,
                    "payload_hash": payload_hash,
                })
                continue
            embedding = self._generate_embedding(text)
            matched = None
            matched_similarity = 0.0
            if embedding:
                import numpy as np
                vector = np.array(embedding, dtype=np.float32)
                for rep in representatives:
                    rep_vector = rep.get("vector")
                    if rep_vector is None:
                        continue
                    similarity = float(np.dot(vector, rep_vector) / (np.linalg.norm(vector) * np.linalg.norm(rep_vector)))
                    if similarity > matched_similarity:
                        matched_similarity = similarity
                        matched = rep
            if matched and matched_similarity >= similarity_threshold:
                decisions.append({
                    "index": idx,
                    "decision": "duplicate_semantic",
                    "representative": matched["index"],
                    "similarity": round(matched_similarity, 5),
                    "payload_hash": payload_hash,
                })
            else:
                seen_hashes[payload_hash] = idx
                representatives.append({
                    "index": idx,
                    "hash": payload_hash,
                    "text": text,
                    "vector": None if embedding is None else __import__("numpy").array(embedding, dtype=__import__("numpy").float32),
                })
                decisions.append({
                    "index": idx,
                    "decision": "representative",
                    "representative": idx,
                    "similarity": 1.0,
                    "payload_hash": payload_hash,
                })
                self._record_payload_fingerprint(payload_hash, payload_hash, text[:500])
        duplicates = sum(1 for item in decisions if item["decision"].startswith("duplicate"))
        raw_chars = sum(len(str(item if isinstance(item, str) else json.dumps(item, sort_keys=True, default=str))) for item in payloads)
        kept_chars = sum(len(representative["text"]) for representative in representatives)
        return {
            "semantic_available": self.semantic_available(load_model=False),
            "model": _EMBEDDING_MODEL_NAME,
            "payloads": len(payloads),
            "representatives": len(representatives),
            "duplicates": duplicates,
            "raw_chars": raw_chars,
            "deduped_chars": kept_chars,
            "char_reduction_percent": round(((raw_chars - kept_chars) / raw_chars) * 100, 4) if raw_chars else 0.0,
            "decisions": decisions,
        }

    def _record_payload_fingerprint(self, payload_hash: str, representative_hash: str, summary: str) -> None:
        now = self._utc_now()
        try:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT observation_count FROM semantic_payload_fingerprints WHERE payload_hash = ?",
                    (payload_hash,)
                ).fetchone()
                if existing:
                    conn.execute("""
                        UPDATE semantic_payload_fingerprints
                        SET last_seen = ?, observation_count = observation_count + 1
                        WHERE payload_hash = ?
                    """, (now, payload_hash))
                else:
                    conn.execute("""
                        INSERT INTO semantic_payload_fingerprints
                        (payload_hash, representative_hash, summary, first_seen, last_seen, observation_count)
                        VALUES (?, ?, ?, ?, ?, 1)
                    """, (payload_hash, representative_hash, summary, now, now))
        except Exception:
            pass

    def _row_to_node(self, row) -> Dict[str, Any]:
        return {
            "id": row[0],
            "type": row[1],
            "label": row[2],
            "properties": json.loads(row[3] or "{}"),
            "first_seen": row[4],
            "last_seen": row[5],
            "observation_count": row[6]
        }

    def _row_to_edge(self, row) -> Dict[str, Any]:
        return {
            "source": row[0],
            "target": row[1],
            "relation": row[2],
            "properties": json.loads(row[3] or "{}"),
            "first_seen": row[4],
            "last_seen": row[5],
            "observation_count": row[6]
        }

    # Same-file read-loop cache serving from L1/L2
    def get_file_content_cached(
        self,
        file_path: str,
        max_bytes: int = 20000,
        query_text: Optional[str] = None,
        semantic_limit: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Return file content using L1/L2 cache with stale-content protection."""
        path = Path(file_path).resolve()
        key = str(path)
        current_time = time.time()
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            return None
        stat = path.stat()
        mtime_ns = int(stat.st_mtime_ns)
        size_bytes = int(stat.st_size)

        cached = _FILE_READ_CACHE_L1.get(key)
        if cached:
            content, cached_at, content_hash, cached_mtime_ns = cached
            if current_time - cached_at < _FILE_READ_CACHE_TTL and cached_mtime_ns == mtime_ns:
                result = {
                    "content": content[:max_bytes],
                    "source": "l1",
                    "cache_hit": True,
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                }
                if query_text:
                    result["semantic_related"] = self.semantic_context(query_text, limit=semantic_limit, include_content=False)["results"]
                return result
            _FILE_READ_CACHE_L1.pop(key, None)

        if _FILE_READ_CACHE_L2_ENABLED:
            row = self._get_file_content_cache_row(key)
            if row and int(row["mtime_ns"]) == mtime_ns and int(row["size_bytes"]) == size_bytes:
                content = row["content"]
                _FILE_READ_CACHE_L1[key] = (content, current_time, row["content_hash"], mtime_ns)
                self._record_file_cache_hit(key)
                result = {
                    "content": content[:max_bytes],
                    "source": "l2",
                    "cache_hit": True,
                    "content_hash": row["content_hash"],
                    "size_bytes": size_bytes,
                }
                if query_text:
                    result["semantic_related"] = self.semantic_context(query_text, limit=semantic_limit, include_content=False)["results"]
                return result

        content = path.read_text(encoding="utf-8", errors="replace")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _FILE_READ_CACHE_L1[key] = (content, current_time, content_hash, mtime_ns)
        if _FILE_READ_CACHE_L2_ENABLED:
            self._cache_file_content(key, content, content_hash, size_bytes, mtime_ns)
        result = {
            "content": content[:max_bytes],
            "source": "disk",
            "cache_hit": False,
            "content_hash": content_hash,
            "size_bytes": size_bytes,
        }
        if query_text:
            result["semantic_related"] = self.semantic_context(query_text, limit=semantic_limit, include_content=False)["results"]
        return result

    def _get_file_content_cache_row(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get cached file content row from L2 cache."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT content, content_hash, size_bytes, mtime_ns FROM file_contents WHERE file_path = ?",
                    (file_path,)
                ).fetchone()
            if not row:
                return None
            return {
                "content": row[0],
                "content_hash": row[1],
                "size_bytes": row[2],
                "mtime_ns": row[3],
            }
        except Exception:
            return None

    def _cache_file_content(self, file_path: str, content: str, content_hash: str, size_bytes: int, mtime_ns: int) -> None:
        """Cache file content in workspace graph L2 cache."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO file_contents
                    (file_path, content, content_hash, indexed_at, size_bytes, mtime_ns, hit_count, last_hit_at)
                    VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT hit_count FROM file_contents WHERE file_path = ?), 0), NULL)
                """, (
                    file_path,
                    content,
                    content_hash,
                    self._utc_now(),
                    size_bytes,
                    mtime_ns,
                    file_path,
                ))
        except Exception:
            pass  # Silently fail for caching

    def _record_file_cache_hit(self, file_path: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE file_contents
                    SET hit_count = hit_count + 1, last_hit_at = ?
                    WHERE file_path = ?
                """, (self._utc_now(), file_path))
        except Exception:
            pass

workspace_graph = WorkspaceGraph()
