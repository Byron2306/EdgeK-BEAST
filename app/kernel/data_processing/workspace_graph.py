import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from app.kernel.compute.container import container

class WorkspaceGraph:
    """SQLite-backed graph for sessions, providers, models, policies, traces, and artifacts."""

    PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.@-]+(?:\.[A-Za-z0-9]+)?")
    PYTHON_SYMBOL_PATTERN = re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)

    def __init__(self, db_path: Optional[str] = None):
        self._use_container = db_path is None
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "workspace_graph.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_initialized = False
        self._file_read_l1: Dict[str, Dict[str, Any]] = {}

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self):
        conn = container.get("observation_store").get_skills_conn() if self._use_container else sqlite3.connect(self.db_path)
        return conn

    def ensure_db(self):
        if not self._db_initialized:
            self._init_db()
            self._db_initialized = True

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES nodes(id),
                    FOREIGN KEY (target_id) REFERENCES nodes(id)
                )
            """)
            conn.execute("CREATE TABLE IF NOT EXISTS embeddings (node_id TEXT PRIMARY KEY, embedding BLOB)")

    def upsert_node(self, id: str, type: str, label: str, properties: Dict[str, Any], timestamp: str):
        self.ensure_db()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO nodes (id, type, label, properties, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    properties = excluded.properties,
                    last_seen = excluded.last_seen
            """, (id, type, label, json.dumps(properties), timestamp, timestamp))

    def upsert_edge(self, source_id: str, target_id: str, type: str, properties: Dict[str, Any], timestamp: str):
        self.ensure_db()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO edges (source_id, target_id, type, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (source_id, target_id, type, json.dumps(properties), timestamp))

    def semantic_available(self, load_model: bool = False) -> bool:
        try:
            import sentence_transformers  # noqa: F401
            return True
        except Exception:
            return False

    def _chunk_text(self, content: str, rel_path: str) -> List[Dict[str, Any]]:
        lines = content.splitlines()
        suffix = Path(rel_path).suffix.lower()
        if suffix in {".md", ".markdown"}:
            chunks: List[Dict[str, Any]] = []
            current_header = ""
            start = 1
            buf: List[str] = []
            for idx, line in enumerate(lines, start=1):
                if line.lstrip().startswith("#"):
                    if buf:
                        chunks.append({
                            "text": "\n".join(buf).strip(),
                            "start_line": start,
                            "end_line": idx - 1,
                            "chunk_kind": "markdown_section",
                            "context_header": current_header,
                        })
                    current_header = line.strip("# ").strip()
                    start = idx
                    buf = [line]
                else:
                    buf.append(line)
            if buf:
                chunks.append({
                    "text": "\n".join(buf).strip(),
                    "start_line": start,
                    "end_line": len(lines),
                    "chunk_kind": "markdown_section",
                    "context_header": current_header,
                })
            return [chunk for chunk in chunks if chunk.get("text")] or [{"text": content, "start_line": 1, "end_line": len(lines), "chunk_kind": "markdown_section", "context_header": current_header}]
        return [{"text": content, "start_line": 1, "end_line": len(lines), "chunk_kind": "code_window", "context_header": ""}]

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:16]]

    def _store_embedding(self, node_id: str, embedding: List[float]):
        self.ensure_db()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (node_id, embedding) VALUES (?, ?)",
                (node_id, json.dumps(embedding)),
            )

    def vector_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []

    def _lexical_semantic_search(self, query: str, limit: int = 5, node_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return []

    def _content_for_semantic_chunk(self, props: Dict[str, Any], max_chars_per_chunk: int = 900) -> str:
        return props.get("preview", "")

    def semantic_context(
        self,
        query_text: str,
        limit: int = 8,
        include_content: bool = True,
        max_chars_per_chunk: int = 900,
        file_glob: Optional[str] = None,
        node_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return compact semantic context chunks for a natural-language query."""
        results = self.vector_search(query_text, limit=limit)
        if not results:
            results = self._lexical_semantic_search(query_text, limit=limit, node_types=node_types)
        
        context = []
        for item in results:
            props = item.get("properties") or {}
            if node_types and item.get("type") not in set(node_types):
                continue
            text = props.get("preview", "")
            if include_content and item["type"] == "semantic_chunk":
                text = self._content_for_semantic_chunk(props, max_chars_per_chunk=max_chars_per_chunk) or text
            context.append({
                "node_id": item.get("id"),
                "type": item["type"],
                "label": item["label"],
                "similarity": 0.0,
                "content": text,
            })
        return {"context": context, "query": query_text}

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
            "*.py", "*.md", "*.json", "*.yaml", "*.yml"
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
        embedded_chunks = 0
        semantic_ready = self.semantic_available(load_model=True)

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
                embedding_text = chunk.get("context_text") or chunk["text"]
                chunk_hash = hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
                chunk_id = f"semantic_chunk:{rel_path}:{chunk.get('start_line', 1)}:{chunk_hash[:12]}"
                self.upsert_node(chunk_id, "semantic_chunk", f"{rel_path}:{chunk.get('start_line', 1)}-{chunk.get('end_line', 1)}", {
                    "file": rel_path,
                    "absolute_path": str(path),
                    "start_line": chunk.get("start_line", 1),
                    "end_line": chunk.get("end_line", 1),
                    "content_hash": chunk_hash,
                    "preview": chunk["text"][:320],
                    "content": chunk["text"],
                    "chunk_kind": chunk.get("chunk_kind") or ("markdown_section" if path.suffix.lower() in {".md", ".markdown"} else "code_window"),
                    "context_header": chunk.get("context_header") or "",
                }, timestamp)
                self.upsert_edge(file_id, chunk_id, "has_semantic_chunk", {}, timestamp)
                indexed_chunks += 1
                embedding = self._generate_embedding(embedding_text) if semantic_ready else None
                if embedding:
                    self._store_embedding(chunk_id, embedding)
                    embedded_chunks += 1

        return {
            "repository": str(root),
            "semantic_available": semantic_ready,
            "model": "unknown",
            "error": "none",
            "indexed_files": indexed_files,
            "indexed_chunks": indexed_chunks,
            "embedded_chunks": embedded_chunks,
            "skipped_files": skipped_files,
            "errors": errors,
        }

    def _row_to_node(self, row: Any) -> Dict[str, Any]:
        node = {
            "id": row[0],
            "type": row[1],
            "label": row[2],
            "properties": json.loads(row[3] or "{}"),
            "first_seen": row[4],
            "last_seen": row[5],
        }
        return node

    def _row_to_edge(self, row: Any) -> Dict[str, Any]:
        return {
            "id": row[0],
            "source": row[1],
            "target": row[2],
            "relation": row[3],
            "type": row[3],
            "properties": json.loads(row[4] or "{}"),
            "created_at": row[5],
        }

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_db()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, type, label, properties, first_seen, last_seen FROM nodes WHERE id = ?",
                (node_id,),
            ).fetchone()
        return self._row_to_node(row) if row else None

    def recent_nodes(self, limit: int = 50) -> List[Dict[str, Any]]:
        self.ensure_db()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, type, label, properties, first_seen, last_seen FROM nodes ORDER BY last_seen DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def search_nodes(self, query: str, node_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        self.ensure_db()
        needle = f"%{str(query or '').lower()}%"
        sql = (
            "SELECT id, type, label, properties, first_seen, last_seen FROM nodes "
            "WHERE (lower(id) LIKE ? OR lower(label) LIKE ? OR lower(properties) LIKE ?)"
        )
        params: List[Any] = [needle, needle, needle]
        if node_type:
            sql += " AND type = ?"
            params.append(node_type)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_node(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        self.ensure_db()
        with self._connect() as conn:
            node_rows = conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall()
            total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            embeddings = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        return {
            "total_nodes": int(total_nodes),
            "total_edges": int(total_edges),
            "node_types": {str(row[0]): int(row[1]) for row in node_rows},
            "semantic": {"embeddings": int(embeddings)},
            "tree_sitter": {"available": False, "mode": "regex_fallback"},
            "file_read_cache": {
                "l1_entries": len(self._file_read_l1),
                "l2_entries": 0,
            },
        }

    def _paths_from_text(self, text: str) -> List[str]:
        paths = []
        for match in self.PATH_PATTERN.findall(text or ""):
            paths.append(match)
        dotted = re.findall(r"\b(?:app|tests|scripts|docs|benchmarks)(?:\.[A-Za-z0-9_]+)+(?:\.py)?\b", text or "")
        paths.extend(dotted)
        return sorted(dict.fromkeys(paths))

    def observe_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_db()
        timestamp = str(trace.get("timestamp") or self._utc_now())
        trace_id = str(trace.get("trace_id") or hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()[:16])
        ir = trace.get("edgek_ir") if isinstance(trace.get("edgek_ir"), dict) else {}
        governance = trace.get("governance_result") if isinstance(trace.get("governance_result"), dict) else {}
        self.upsert_node(f"trace:{trace_id}", "trace", trace_id, trace, timestamp)
        if trace.get("session_id"):
            sid = f"session:{trace.get('session_id')}"
            self.upsert_node(sid, "session", str(trace.get("session_id")), {}, timestamp)
            self.upsert_edge(f"trace:{trace_id}", sid, "session", {}, timestamp)
        if trace.get("provider_type"):
            pid = f"provider:{trace.get('provider_type')}"
            self.upsert_node(pid, "provider", str(trace.get("provider_type")), {}, timestamp)
            self.upsert_edge(f"trace:{trace_id}", pid, "provider", {}, timestamp)
        if ir.get("model"):
            mid = f"model:{ir.get('model')}"
            self.upsert_node(mid, "model", str(ir.get("model")), {}, timestamp)
            self.upsert_edge(f"trace:{trace_id}", mid, "model", {}, timestamp)
        for policy in governance.get("policies_applied") or []:
            policy_id = f"policy:{policy}"
            self.upsert_node(policy_id, "policy", str(policy), {}, timestamp)
            self.upsert_edge(f"trace:{trace_id}", policy_id, "policy_applied", {}, timestamp)
        text = json.dumps(ir, sort_keys=True)
        for path in self._paths_from_text(text):
            file_id = f"file:{path}"
            self.upsert_node(file_id, "file", path, {"path": path}, timestamp)
            self.upsert_edge(f"trace:{trace_id}", file_id, "mentioned_file", {}, timestamp)
        return {"beast_object_type": "workspace_graph_observation", "trace_id": trace_id, "node_count": self.stats()["total_nodes"]}

    def neighborhood(self, node_id: str, limit: int = 50) -> Dict[str, Any]:
        self.ensure_db()
        center = self.get_node(node_id)
        if center is None:
            return {"center": None, "edges": [], "nodes": []}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, source_id, target_id, type, properties, created_at FROM edges "
                "WHERE source_id = ? OR target_id = ? ORDER BY created_at DESC LIMIT ?",
                (node_id, node_id, max(1, min(int(limit), 500))),
            ).fetchall()
        edges = [self._row_to_edge(row) for row in rows]
        node_ids = sorted({edge["source"] for edge in edges} | {edge["target"] for edge in edges})
        nodes = [node for nid in node_ids if (node := self.get_node(nid))]
        return {"center": center, "edges": edges, "nodes": nodes}

    def export_graph(self, node_limit: int = 100, edge_limit: int = 200) -> Dict[str, Any]:
        self.ensure_db()
        with self._connect() as conn:
            nodes = [
                self._row_to_node(row)
                for row in conn.execute(
                    "SELECT id, type, label, properties, first_seen, last_seen FROM nodes ORDER BY last_seen DESC LIMIT ?",
                    (max(1, min(int(node_limit), 5000)),),
                ).fetchall()
            ]
            edges = [
                self._row_to_edge(row)
                for row in conn.execute(
                    "SELECT id, source_id, target_id, type, properties, created_at FROM edges ORDER BY created_at DESC LIMIT ?",
                    (max(1, min(int(edge_limit), 10000)),),
                ).fetchall()
            ]
        return {"beast_object_type": "workspace_graph_export", "stats": self.stats(), "nodes": nodes, "edges": edges}

    def integrity_report(self) -> Dict[str, Any]:
        self.ensure_db()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.source_id, e.target_id, e.type, e.properties, e.created_at
                FROM edges e
                LEFT JOIN nodes s ON s.id = e.source_id
                LEFT JOIN nodes t ON t.id = e.target_id
                WHERE s.id IS NULL OR t.id IS NULL
                ORDER BY e.created_at DESC
                """
            ).fetchall()
        orphan_edges = [self._row_to_edge(row) for row in rows]
        return {"beast_object_type": "workspace_graph_integrity", "ok": not orphan_edges, "orphan_edge_count": len(orphan_edges), "orphan_edges": orphan_edges}

    def _extract_symbols_tree_sitter(self, content: str, language: str, rel_path: str) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        if language in {"python", "py"}:
            for idx, line in enumerate(content.splitlines(), start=1):
                match = re.match(r"\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if match:
                    symbols.append({"name": match.group(1), "kind": "symbol", "file": rel_path, "line": idx})
        elif language in {"javascript", "typescript", "js", "ts"}:
            patterns = [
                r"\bclass\s+([A-Za-z_$][A-Za-z0-9_$]*)",
                r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)",
                r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\(",
                r"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*\{",
            ]
            for idx, line in enumerate(content.splitlines(), start=1):
                for pattern in patterns:
                    match = re.search(pattern, line)
                    if match:
                        symbols.append({"name": match.group(1), "kind": "symbol", "file": rel_path, "line": idx})
                        break
        return symbols

    def index_repository(self, root_path: str, max_files: int = 200) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        timestamp = self._utc_now()
        self.upsert_node(f"repo:{root}", "repository", root.name or str(root), {"path": str(root)}, timestamp)
        indexed_files = 0
        indexed_symbols = 0
        for path in root.rglob("*"):
            if indexed_files >= max_files:
                break
            if not path.is_file() or path.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".jsx"}:
                continue
            rel = path.relative_to(root).as_posix()
            parts = rel.split("/")[:-1]
            parent_id = f"repo:{root}"
            accum = []
            for part in parts:
                accum.append(part)
                did = "dir:" + "/".join(accum)
                self.upsert_node(did, "directory", "/".join(accum), {"path": "/".join(accum)}, timestamp)
                self.upsert_edge(parent_id, did, "contains", {}, timestamp)
                parent_id = did
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            file_id = f"file:{rel}"
            self.upsert_node(file_id, "file", rel, {"path": rel, "preview": content[:500]}, timestamp)
            self.upsert_edge(parent_id, file_id, "contains", {}, timestamp)
            indexed_files += 1
            language = "python" if path.suffix == ".py" else "javascript"
            for symbol in self._extract_symbols_tree_sitter(content, language, rel):
                sid = f"symbol:{rel}:{symbol['name']}:{symbol['line']}"
                self.upsert_node(sid, "symbol", symbol["name"], symbol, timestamp)
                self.upsert_edge(file_id, sid, "defines_symbol", {}, timestamp)
                indexed_symbols += 1
        return {"beast_object_type": "workspace_graph_repository_index", "indexed_files": indexed_files, "indexed_symbols": indexed_symbols}

    def context_for_ir(self, ir: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
        text = json.dumps(ir or {}, sort_keys=True)
        mentioned = self._paths_from_text(text)
        matched: List[Dict[str, Any]] = []
        seen = set()
        for path in mentioned:
            variants = [path, path.replace(".", "/")]
            for variant in variants:
                for node in self.search_nodes(variant, limit=limit):
                    if node["id"] not in seen and node["type"] in {"file", "symbol", "beast_artifact", "semantic_chunk"}:
                        matched.append(node)
                        seen.add(node["id"])
                    if len(matched) >= limit:
                        break
                if len(matched) >= limit:
                    break
        if not matched:
            words = [w for w in re.findall(r"[A-Za-z0-9_./-]{4,}", text) if len(w) >= 4][:8]
            for word in words:
                for node in self.search_nodes(word, limit=limit):
                    if node["id"] not in seen:
                        matched.append(node)
                        seen.add(node["id"])
                    if len(matched) >= limit:
                        break
                if len(matched) >= limit:
                    break
        semantic = self.semantic_context(text, limit=limit, include_content=False)
        return {
            "matched_nodes": matched[:limit],
            "matched_node_count": len(matched[:limit]),
            "mentioned_files": mentioned,
            "semantic_matches": semantic.get("results", [])[:limit],
            "semantic_match_count": int(semantic.get("result_count") or 0),
        }

    def _lexical_semantic_search(self, query: str, limit: int = 5, node_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        types = node_types or ["semantic_chunk"]
        candidates: List[Dict[str, Any]] = []
        for node_type in types:
            candidates.extend(self.search_nodes(query, node_type=node_type, limit=limit * 5))
        if not candidates:
            self.ensure_db()
            placeholders = ",".join("?" for _ in types)
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT id, type, label, properties, first_seen, last_seen FROM nodes WHERE type IN ({placeholders}) ORDER BY last_seen DESC LIMIT ?",
                    tuple(types + [max(1, min(int(limit) * 20, 500))]),
                ).fetchall()
            candidates = [self._row_to_node(row) for row in rows]
        terms = set(re.findall(r"[A-Za-z0-9_]{3,}", (query or "").lower()))
        scored = []
        for node in candidates:
            props = node.get("properties") or {}
            hay = " ".join([node.get("label", ""), str(props.get("content") or props.get("preview") or "")]).lower()
            score = sum(1 for term in terms if term in hay)
            if score:
                node = dict(node)
                node["score"] = score
                scored.append(node)
        return sorted(scored or candidates, key=lambda item: item.get("score", 0), reverse=True)[:limit]

    def semantic_context(
        self,
        query_text: str,
        limit: int = 8,
        include_content: bool = True,
        max_chars_per_chunk: int = 900,
        file_glob: Optional[str] = None,
        node_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        results = self.vector_search(query_text, limit=limit) or self._lexical_semantic_search(query_text, limit=limit, node_types=node_types)
        out = []
        for item in results[:limit]:
            props = item.get("properties") or {}
            content = str(props.get("content") or props.get("preview") or "")
            file_path = str(props.get("file") or props.get("path") or item.get("label") or "")
            out.append({
                "node_id": item.get("id"),
                "id": item.get("id"),
                "type": item.get("type"),
                "label": item.get("label"),
                "file": file_path,
                "path": file_path,
                "source_path": file_path,
                "similarity": float(item.get("score") or 0),
                "content": content[:max_chars_per_chunk] if include_content else "",
                "chunk_kind": props.get("chunk_kind") or "code_window",
                "context_header": props.get("context_header") or "",
                "properties": props,
            })
        return {
            "beast_object_type": "workspace_semantic_context",
            "query": query_text,
            "results": out,
            "context": out,
            "result_count": len(out),
            "retrieval_mode": "lexical_bm25_fallback",
        }

    def semantic_dedupe_payloads(self, payloads: List[str]) -> Dict[str, Any]:
        seen: Dict[str, int] = {}
        duplicates = 0
        for payload in payloads:
            key = hashlib.sha256(str(payload).strip().lower().encode()).hexdigest()
            if key in seen:
                duplicates += 1
            seen[key] = seen.get(key, 0) + 1
        return {"beast_object_type": "workspace_semantic_dedupe", "count": len(payloads), "unique": len(seen), "duplicates": duplicates}

    def rebuild_from_traces(self, trace_archive: str, clear_existing: bool = False) -> Dict[str, Any]:
        self.ensure_db()
        if clear_existing:
            with self._connect() as conn:
                conn.execute("DELETE FROM edges")
                conn.execute("DELETE FROM nodes")
                conn.execute("DELETE FROM embeddings")
        processed = 0
        errors = 0
        for line in Path(trace_archive).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                self.observe_trace(json.loads(line))
                processed += 1
            except Exception:
                errors += 1
        return {"beast_object_type": "workspace_graph_rebuild", "processed_traces": processed, "errors": errors}

    def index_beast_artifacts(self, data_dir: str, include_embeddings: bool = False) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(data_dir)
        timestamp = self._utc_now()
        indexed = 0
        for path in root.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            text = json.dumps(payload, sort_keys=True)
            artifact_id = f"artifact:{path.relative_to(root).as_posix()}"
            self.upsert_node(artifact_id, "beast_artifact", path.stem, {"path": str(path), "preview": text[:1200]}, timestamp)
            indexed += 1
            if isinstance(payload.get("envelope"), dict):
                envelope = payload["envelope"]
                envelope_id = f"artifact:{path.relative_to(root).as_posix()}:envelope"
                self.upsert_node(
                    envelope_id,
                    "beast_artifact",
                    str(envelope.get("task_id") or path.stem) + ":envelope",
                    {"path": str(path), "preview": json.dumps(envelope, sort_keys=True)[:1200]},
                    timestamp,
                )
                self.upsert_edge(artifact_id, envelope_id, "contains_envelope", {}, timestamp)
                indexed += 1
            provider = payload.get("provider")
            if provider:
                provider_id = f"provider:{provider}"
                self.upsert_node(provider_id, "provider", str(provider), {}, timestamp)
                self.upsert_edge(artifact_id, provider_id, "mentions_provider", {}, timestamp)
                indexed += 1
            for term in self._paths_from_text(text):
                file_id = f"file:{term}"
                self.upsert_node(file_id, "file", term, {"path": term}, timestamp)
                self.upsert_edge(artifact_id, file_id, "mentions_file", {}, timestamp)
                indexed += 1
        return {"beast_object_type": "workspace_graph_beast_artifact_index", "indexed_artifacts": indexed}

    def get_file_content_cached(
        self,
        path: str,
        *,
        max_bytes: int = 20_000,
        query_text: Optional[str] = None,
        semantic_limit: int = 3,
    ) -> Dict[str, Any]:
        """Read a file through a small workspace-local cache.

        MCP and context-packet callers use this as an L1 cache to avoid
        repeatedly touching disk for the same bounded file view. The cache key
        includes path, mtime, size, and max byte bound so stale content is not
        reused after edits.
        """
        file_path = Path(path).resolve()
        stat = file_path.stat()
        cache_key = f"{file_path}:{int(stat.st_mtime_ns)}:{stat.st_size}:{int(max_bytes)}"
        cached = self._file_read_l1.get(cache_key)
        if cached:
            return {**cached, "cache_hit": True, "source": "l1"}
        content = file_path.read_text(encoding="utf-8", errors="replace")[: max(1, int(max_bytes))]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        semantic_related: List[Dict[str, Any]] = []
        if query_text:
            try:
                semantic_related = self.semantic_context(
                    query_text,
                    limit=max(1, int(semantic_limit)),
                    include_content=False,
                ).get("results", [])
            except Exception:
                semantic_related = []
        payload = {
            "content": content,
            "content_hash": content_hash,
            "semantic_related": semantic_related,
            "cache_hit": False,
            "source": "disk",
        }
        self._file_read_l1[cache_key] = payload
        return payload

    def artifact_context(self, query_text: str, limit: int = 5) -> Dict[str, Any]:
        """Return BEAST artifact memories relevant to a task query."""
        self.ensure_db()
        matches = self._lexical_semantic_search(
            query_text,
            limit=max(1, int(limit)),
            node_types=["beast_artifact"],
        )
        results = []
        for node in matches[: max(1, int(limit))]:
            props = node.get("properties") or {}
            try:
                payload = json.loads(str(props.get("preview") or "{}"))
            except Exception:
                payload = {}
            results.append({
                "node_id": node.get("id"),
                "label": node.get("label"),
                "artifact_type": payload.get("chronicle_type") or payload.get("beast_object_type") or payload.get("artifact_type"),
                "task_id": payload.get("task_id"),
                "provider": payload.get("provider"),
                "category": payload.get("category"),
                "score": node.get("score", 0),
                "source_path": props.get("path"),
                "preview": props.get("preview") or "",
            })
        return {
            "beast_object_type": "workspace_artifact_context",
            "query": query_text,
            "results": results,
            "result_count": len(results),
        }
