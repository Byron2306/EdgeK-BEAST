import hashlib
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import os
from app.kernel.compute.container import container
from app.kernel.data_processing.code_indexers import (
    SOURCE_SUFFIXES,
    extract_imports,
    extract_routes,
    extract_symbols,
    file_metadata,
    language_for_path,
    sha256_text,
    tree_sitter_status,
)

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
        self._bulk_conn = None
        self._bulk_node_ids = None
        self._bulk_edge_keys = None

        try:
            import chromadb
            chroma_dir = self.db_path.parent / "chroma"
            chroma_dir.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name="workspace_nodes",
                metadata={"hnsw:space": "cosine"}
            )
            self._chroma_available = True
        except ImportError:
            self._chroma_available = False

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
        active = getattr(self, "_bulk_conn", None)
        if active is not None:
            node_ids = getattr(self, "_bulk_node_ids", None)
            if node_ids is not None:
                if id in node_ids:
                    return
                node_ids.add(id)
            active.execute("""
                INSERT INTO nodes (id, type, label, properties, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    properties = excluded.properties,
                    last_seen = excluded.last_seen
            """, (id, type, label, json.dumps(properties), timestamp, timestamp))
            return
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
        active = getattr(self, "_bulk_conn", None)
        if active is not None:
            edge_keys = getattr(self, "_bulk_edge_keys", None)
            if edge_keys is not None:
                edge_key = (source_id, target_id, type, json.dumps(properties, sort_keys=True))
                if edge_key in edge_keys:
                    return
                edge_keys.add(edge_key)
            active.execute("""
                INSERT INTO edges (source_id, target_id, type, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (source_id, target_id, type, json.dumps(properties), timestamp))
            return
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO edges (source_id, target_id, type, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (source_id, target_id, type, json.dumps(properties), timestamp))

    def semantic_available(self, load_model: bool = False) -> bool:
        return getattr(self, "_chroma_available", False)

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

    def _get_embedding_model(self):
        if not hasattr(self, "_embedding_model"):
            # Embedding downloads are not allowed on the foreground IDE path.
            # Operators can opt into a pre-cached local model explicitly.
            if os.environ.get("BEAST_ENABLE_LOCAL_EMBEDDINGS", "0") != "1":
                raise RuntimeError("local embeddings disabled; using lexical retrieval")
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedding_model

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        if not self.semantic_available():
            return None
        if getattr(self, "_embedding_unavailable", False):
            return None
        try:
            model = self._get_embedding_model()
            return model.encode(text).tolist()
        except Exception:
            # A semantic miss must degrade to local lexical search, never block
            # a mission on network access or a multi-gigabyte model load.
            self._embedding_unavailable = True
            return None

    def _store_embedding(self, node_id: str, embedding: List[float]):
        self.ensure_db()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (node_id, embedding) VALUES (?, ?)",
                (node_id, json.dumps(embedding)),
            )
        if getattr(self, "_chroma_available", False):
            node = self.get_node(node_id)
            if node:
                meta = {k: str(v) for k, v in node.get("properties", {}).items() if v is not None and isinstance(v, (str, int, float, bool))}
                text_content = node.get("properties", {}).get("content") or node.get("label", "")
                self._chroma_collection.upsert(
                    ids=[node_id],
                    embeddings=[embedding],
                    documents=[text_content],
                    metadatas=[meta] if meta else None
                )

    def vector_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not getattr(self, "_chroma_available", False):
            return []
        try:
            model = self._get_embedding_model()
            query_embedding = model.encode(query).tolist()
            
            results = self._chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            if not results or not results['ids'] or not results['ids'][0]:
                return []
                
            nodes = []
            for i, node_id in enumerate(results['ids'][0]):
                node = self.get_node(node_id)
                if node:
                    if 'distances' in results and results['distances'] and len(results['distances'][0]) > i:
                        node['similarity'] = 1.0 - results['distances'][0][i]
                    nodes.append(node)
            return nodes
        except Exception as e:
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
        raw_query = str(query or "").lower()
        needle = f"%{raw_query}%"
        sql = (
            "SELECT id, type, label, properties, first_seen, last_seen FROM nodes "
            "WHERE (lower(id) LIKE ? OR lower(label) LIKE ? OR lower(properties) LIKE ?)"
        )
        params: List[Any] = [needle, needle, needle]
        if node_type:
            sql += " AND type = ?"
            params.append(node_type)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        fetch_limit = max(1, min(max(int(limit) * 25, int(limit)), 5000))
        params.append(fetch_limit)
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        nodes = [self._row_to_node(row) for row in rows]

        def _rank(node: Dict[str, Any]) -> tuple:
            props = node.get("properties") or {}
            label = str(node.get("label") or "").lower()
            node_id = str(node.get("id") or "").lower()
            path = str(props.get("path") or props.get("file") or "").lower()
            if raw_query and raw_query in {label, path, node_id}:
                tier = 0
            elif raw_query and (label.endswith(f"/{raw_query}") or path.endswith(f"/{raw_query}") or node_id.endswith(f":{raw_query}")):
                tier = 1
            elif raw_query and (raw_query in label or raw_query in path):
                tier = 2
            elif raw_query and raw_query in node_id:
                tier = 3
            else:
                tier = 4
            return (tier, str(node.get("last_seen") or ""))

        return sorted(nodes, key=_rank)[: max(1, min(int(limit), 500))]

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
            "tree_sitter": tree_sitter_status(),
            "file_read_cache": {
                "l1_entries": len(self._file_read_l1),
                "l2_entries": 0,
            },
        }

    def graph_snapshot(self, *, node_limit: int = 80, edge_limit: int = 160) -> Dict[str, Any]:
        """Return a bounded graph payload for the IDE Semantic Map."""
        self.ensure_db()
        with self._connect() as conn:
            node_rows = conn.execute(
                "SELECT id, type, label, properties, first_seen, last_seen FROM nodes ORDER BY last_seen DESC LIMIT ?",
                (max(1, min(int(node_limit), 500)),),
            ).fetchall()
            edge_rows = conn.execute(
                "SELECT id, source_id, target_id, type, properties, created_at FROM edges ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(edge_limit), 1000)),),
            ).fetchall()
        nodes = [self._row_to_node(row) for row in node_rows]
        known = {node["id"] for node in nodes}
        edges = [self._row_to_edge(row) for row in edge_rows if row[1] in known and row[2] in known]
        return {"nodes": nodes, "edges": edges, "stats": self.stats(), "coverage": 100 if nodes else 0}

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
        """Compatibility hook around the parser-backed symbol indexer."""
        return extract_symbols(content, language, rel_path)

    def _dir_node_id(self, repo_id: str, path: str) -> str:
        return f"{repo_id}:dir:{path}" if path else repo_id

    def _file_node_id(self, repo_id: str, rel_path: str) -> str:
        return f"{repo_id}:file:{rel_path}"

    def _import_node_id(self, module: str) -> str:
        return f"import:{module}"

    def _route_node_id(self, repo_id: str, method: str, route_path: str) -> str:
        route_key = hashlib.sha256(f"{method.upper()} {route_path}".encode("utf-8")).hexdigest()[:16]
        return f"{repo_id}:route:{route_key}"

    def _tokenize(self, text: str) -> List[str]:
        return [token.lower() for token in re.findall(r"[A-Za-z0-9_./:-]{2,}", text or "")]

    def _node_search_text(self, node: Dict[str, Any]) -> str:
        props = node.get("properties") or {}
        values = [
            str(node.get("id") or ""),
            str(node.get("label") or ""),
            str(props.get("path") or ""),
            str(props.get("file") or ""),
            str(props.get("language") or ""),
            str(props.get("kind") or ""),
            str(props.get("module") or ""),
            str(props.get("preview") or ""),
            str(props.get("content") or ""),
        ]
        return " ".join(values)

    def _score_nodes(self, query: str, candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        terms = self._tokenize(query)
        if not terms:
            return candidates[:limit]
        query_terms = set(terms)
        doc_tokens = [self._tokenize(self._node_search_text(node)) for node in candidates]
        total_docs = max(1, len(candidates))
        doc_freq: Dict[str, int] = {}
        for tokens in doc_tokens:
            for term in set(tokens):
                if term in query_terms:
                    doc_freq[term] = doc_freq.get(term, 0) + 1
        scored: List[Dict[str, Any]] = []
        for node, tokens in zip(candidates, doc_tokens):
            if not tokens:
                continue
            token_counts: Dict[str, int] = {}
            for token in tokens:
                token_counts[token] = token_counts.get(token, 0) + 1
            score = 0.0
            hay = self._node_search_text(node).lower()
            label = str(node.get("label") or "").lower()
            for term in query_terms:
                tf = token_counts.get(term, 0)
                if tf:
                    idf = math.log((total_docs + 1) / (1 + doc_freq.get(term, 0))) + 1.0
                    score += (1.0 + math.log(tf)) * idf
                elif term in hay:
                    score += 0.35
                if term in label:
                    score += 1.25
            if score > 0:
                item = dict(node)
                item["score"] = round(score, 4)
                scored.append(item)
        return sorted(scored, key=lambda item: (float(item.get("score") or 0), str(item.get("last_seen") or "")), reverse=True)[:limit]

    def _all_nodes_for_types(self, node_types: List[str], limit: int) -> List[Dict[str, Any]]:
        self.ensure_db()
        placeholders = ",".join("?" for _ in node_types)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, type, label, properties, first_seen, last_seen FROM nodes WHERE type IN ({placeholders}) ORDER BY last_seen DESC LIMIT ?",
                tuple(node_types + [max(1, min(int(limit), 5000))]),
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def _local_import_target(self, root: Path, rel: str, module: str) -> str:
        module = str(module or "").strip()
        if not module:
            return ""
        current_dir = Path(rel).parent
        candidates: List[Path] = []
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            remainder = module.lstrip(".").replace(".", "/")
            base = current_dir
            for _ in range(max(0, dots - 1)):
                base = base.parent
            if remainder:
                candidates.append(base / f"{remainder}.py")
                candidates.append(base / remainder / "__init__.py")
        else:
            pathish = module.replace(".", "/")
            candidates.extend([
                Path(f"{pathish}.py"),
                Path(pathish) / "__init__.py",
                Path(pathish) / "index.js",
                Path(pathish) / "index.ts",
                Path(f"{pathish}.js"),
                Path(f"{pathish}.ts"),
                Path(f"{pathish}.tsx"),
                Path(f"{pathish}.jsx"),
            ])
        for candidate in candidates:
            target = (root / candidate).resolve()
            try:
                rel_target = target.relative_to(root).as_posix()
            except ValueError:
                continue
            if target.exists() and target.is_file():
                return rel_target
        return ""

    def index_repository(
        self,
        root_path: str,
        max_files: int = 200,
        include_patterns: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        include_patterns = include_patterns or ["*.py", "*.js", "*.jsx", "*.ts", "*.tsx", "*.md", "*.json", "*.yaml", "*.yml", "*.toml"]
        excluded = set(exclude_dirs or [".git", ".beast", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules", "dist", "build", ".next", "data"])
        timestamp = self._utc_now()
        repo_id = f"repo:{root}"
        bulk_cm = self._connect()
        previous_bulk_conn = self._bulk_conn
        previous_bulk_node_ids = self._bulk_node_ids
        previous_bulk_edge_keys = self._bulk_edge_keys
        self._bulk_conn = bulk_cm.__enter__()
        self._bulk_node_ids = set()
        self._bulk_edge_keys = set()
        self.upsert_node(repo_id, "repository", root.name or str(root), {"path": str(root)}, timestamp)
        indexed_files = 0
        indexed_symbols = 0
        indexed_imports = 0
        indexed_tests = 0
        indexed_routes = 0
        indexed_dependencies = 0
        indexed_dirs = 0
        skipped_files = 0
        errors = 0
        for path in root.rglob("*"):
            if indexed_files >= max_files:
                break
            try:
                rel_path = path.relative_to(root)
            except ValueError:
                skipped_files += 1
                continue
            if any(part in excluded for part in rel_path.parts):
                continue
            if (
                not path.is_file()
                or path.suffix.lower() not in SOURCE_SUFFIXES
                or not any(path.match(pattern) or rel_path.match(pattern) for pattern in include_patterns)
            ):
                if path.is_file():
                    skipped_files += 1
                continue
            rel = rel_path.as_posix()
            parent_id = repo_id
            accum: List[str] = []
            for part in rel.split("/")[:-1]:
                accum.append(part)
                dir_path = "/".join(accum)
                did = self._dir_node_id(repo_id, dir_path)
                self.upsert_node(did, "directory", dir_path, {"path": dir_path, "repo": str(root), "repo_id": repo_id}, timestamp)
                self.upsert_edge(parent_id, did, "contains", {}, timestamp)
                parent_id = did
                indexed_dirs += 1
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errors += 1
                continue
            metadata = file_metadata(path, root, content)
            metadata["repo"] = str(root)
            metadata["repo_id"] = repo_id
            language = str(metadata.get("language") or language_for_path(path))
            file_id = self._file_node_id(repo_id, rel)
            legacy_file_id = f"file:{rel}"
            self.upsert_node(file_id, "file", rel, metadata, timestamp)
            if legacy_file_id != file_id:
                self.upsert_node(legacy_file_id, "file", rel, metadata, timestamp)
                self.upsert_edge(legacy_file_id, file_id, "repo_file_alias", {"repo_id": repo_id}, timestamp)
            self.upsert_edge(parent_id, file_id, "contains", {}, timestamp)
            indexed_files += 1
            if metadata.get("is_test"):
                runner = str(metadata.get("test_runner") or "test")
                test_id = f"{repo_id}:test:{rel}"
                self.upsert_node(test_id, "test", rel, {
                    "path": rel,
                    "file": rel,
                    "repo": str(root),
                    "repo_id": repo_id,
                    "test_runner": runner,
                }, timestamp)
                self.upsert_edge(file_id, test_id, "tests", {"test_runner": runner}, timestamp)
                indexed_tests += 1
            for item in extract_imports(content, language, rel):
                module = str(item.get("module") or item.get("name") or "").strip()
                if not module:
                    continue
                import_id = self._import_node_id(module)
                payload = dict(item)
                payload.update({"repo": str(root), "repo_id": repo_id})
                self.upsert_node(import_id, "import", module, {"module": module, "name": module}, timestamp)
                self.upsert_edge(file_id, import_id, "imports", payload, timestamp)
                target_rel = self._local_import_target(root, rel, module)
                if target_rel and target_rel != rel:
                    target_file_id = self._file_node_id(repo_id, target_rel)
                    self.upsert_edge(file_id, target_file_id, "depends_on", {"module": module, "line": item.get("line")}, timestamp)
                    self.upsert_edge(target_file_id, file_id, "used_by", {"module": module, "line": item.get("line")}, timestamp)
                    indexed_dependencies += 1
                indexed_imports += 1
            for route in extract_routes(content, language, rel):
                route_path = str(route.get("path") or "").strip()
                method = str(route.get("method") or "GET").upper()
                if not route_path:
                    continue
                route_id = self._route_node_id(repo_id, method, route_path)
                payload = dict(route)
                payload.update({"repo": str(root), "repo_id": repo_id})
                self.upsert_node(route_id, "route", f"{method} {route_path}", payload, timestamp)
                self.upsert_edge(file_id, route_id, "defines_route", {"line": route.get("line")}, timestamp)
                indexed_routes += 1
            for symbol in self._extract_symbols_tree_sitter(content, language, rel):
                sid = f"symbol:{rel}:{symbol['name']}:{symbol['line']}"
                symbol_payload = dict(symbol)
                symbol_payload.update({
                    "repo": str(root),
                    "repo_id": repo_id,
                    "language": language,
                    "content_hash": metadata.get("content_hash"),
                    "is_test": bool(metadata.get("is_test")),
                    "test_runner": metadata.get("test_runner") or "",
                })
                self.upsert_node(sid, "symbol", symbol["name"], symbol_payload, timestamp)
                self.upsert_edge(file_id, sid, "defines_symbol", {}, timestamp)
                if metadata.get("is_test"):
                    self.upsert_edge(sid, f"{repo_id}:test:{rel}", "tests", {"test_runner": metadata.get("test_runner")}, timestamp)
                indexed_symbols += 1
        result = {
            "beast_object_type": "workspace_graph_repository_index",
            "repository": str(root),
            "repo_id": repo_id,
            "indexed_files": indexed_files,
            "indexed_symbols": indexed_symbols,
            "indexed_imports": indexed_imports,
            "indexed_tests": indexed_tests,
            "indexed_routes": indexed_routes,
            "indexed_dependencies": indexed_dependencies,
            "indexed_directories": indexed_dirs,
            "skipped_files": skipped_files,
            "errors": errors,
        }
        self._bulk_conn = previous_bulk_conn
        self._bulk_node_ids = previous_bulk_node_ids
        self._bulk_edge_keys = previous_bulk_edge_keys
        bulk_cm.__exit__(None, None, None)
        return result

    def benchmark_index_repository(
        self,
        root_path: str,
        max_files: int = 5000,
        target_seconds: float = 15.0,
        include_patterns: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        result = self.index_repository(
            root_path=root_path,
            max_files=max_files,
            include_patterns=include_patterns,
            exclude_dirs=exclude_dirs,
        )
        elapsed = time.perf_counter() - started
        return {
            **result,
            "beast_object_type": "workspace_graph_index_benchmark",
            "elapsed_seconds": round(elapsed, 4),
            "target_seconds": float(target_seconds),
            "meets_target": elapsed <= float(target_seconds),
            "files_per_second": round(float(result.get("indexed_files") or 0) / elapsed, 2) if elapsed > 0 else 0.0,
        }

    def file_status(self, root_path: str, rel_path: str) -> Dict[str, Any]:
        root = Path(root_path).resolve()
        rel = str(rel_path)
        target = (root / rel).resolve()
        repo_id = f"repo:{root}"
        node = self.get_node(self._file_node_id(repo_id, rel)) or self.get_node(f"file:{rel}")
        props = node.get("properties") if isinstance(node, dict) else {}
        exists = target.exists() and target.is_file()
        current_hash = ""
        current_mtime_ns = 0
        current_size = 0
        if exists:
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                current_hash = sha256_text(content)
                stat = target.stat()
                current_mtime_ns = int(stat.st_mtime_ns)
                current_size = int(stat.st_size)
            except OSError:
                pass
        indexed_hash = str((props or {}).get("content_hash") or (props or {}).get("sha256") or "")
        stale_context_warning = False
        if indexed_hash and current_hash and indexed_hash != current_hash:
            try:
                self.ensure_db()
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT properties FROM edges WHERE target_id IN (?, ?) AND type = ? ORDER BY created_at DESC LIMIT 100",
                        (self._file_node_id(repo_id, rel), f"file:{rel}", "consumed"),
                    ).fetchall()
                stale_context_warning = any(
                    str((json.loads(row[0] or "{}")).get("content_hash") or "") not in {"", current_hash}
                    for row in rows
                )
            except Exception:
                stale_context_warning = False
        return {
            "beast_object_type": "workspace_file_status",
            "path": rel,
            "repo": str(root),
            "repo_id": repo_id,
            "indexed": bool(node),
            "exists": exists,
            "changed": bool(indexed_hash and current_hash and indexed_hash != current_hash),
            "indexed_hash": indexed_hash,
            "current_hash": current_hash,
            "indexed_mtime_ns": int((props or {}).get("mtime_ns") or 0),
            "current_mtime_ns": current_mtime_ns,
            "indexed_size_bytes": int((props or {}).get("size_bytes") or 0),
            "current_size_bytes": current_size,
            "language": str((props or {}).get("language") or language_for_path(target)),
            "test_runner": str((props or {}).get("test_runner") or ""),
            "stale_context_warning": stale_context_warning,
        }

    def record_context_consumption(
        self,
        session_id: str,
        root_path: str,
        paths: List[str],
        objective: str = "",
    ) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        repo_id = f"repo:{root}"
        timestamp = self._utc_now()
        sid = f"session:{session_id or 'default'}"
        self.upsert_node(sid, "session", str(session_id or "default"), {
            "session_id": str(session_id or "default"),
            "objective": str(objective or ""),
            "repo": str(root),
            "repo_id": repo_id,
        }, timestamp)
        recorded = 0
        for raw in paths or []:
            rel = str(raw or "").strip()
            if not rel:
                continue
            file_id = self._file_node_id(repo_id, rel)
            node = self.get_node(file_id) or self.get_node(f"file:{rel}")
            if not self.get_node(file_id):
                target = root / rel
                if target.exists() and target.is_file():
                    try:
                        content = target.read_text(encoding="utf-8", errors="replace")
                        metadata = file_metadata(target, root, content)
                        metadata.update({"repo": str(root), "repo_id": repo_id})
                        self.upsert_node(file_id, "file", rel, metadata, timestamp)
                    except OSError:
                        continue
                else:
                    continue
            if not node:
                node = self.get_node(file_id)
            status = self.file_status(str(root), rel)
            self.upsert_edge(sid, file_id, "consumed", {
                "path": rel,
                "content_hash": status.get("current_hash") or status.get("indexed_hash"),
                "mtime_ns": status.get("current_mtime_ns") or status.get("indexed_mtime_ns"),
                "objective": str(objective or ""),
            }, timestamp)
            recorded += 1
        return {
            "beast_object_type": "workspace_graph_context_consumption",
            "session_id": str(session_id or "default"),
            "repo": str(root),
            "repo_id": repo_id,
            "recorded": recorded,
        }

    def stale_context_events(self, root_path: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        repo_id = f"repo:{root}"
        params: List[Any] = ["consumed"]
        sql = (
            "SELECT e.source_id, e.target_id, e.properties, e.created_at "
            "FROM edges e WHERE e.type = ?"
        )
        if session_id:
            sql += " AND e.source_id = ?"
            params.append(f"session:{session_id}")
        sql += " ORDER BY e.created_at DESC LIMIT 1000"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        events: List[Dict[str, Any]] = []
        seen = set()
        for source_id, target_id, props_json, created_at in rows:
            props = json.loads(props_json or "{}")
            rel = str(props.get("path") or "")
            if not rel or (source_id, rel) in seen:
                continue
            seen.add((source_id, rel))
            node = self.get_node(str(target_id))
            node_props = node.get("properties") if isinstance(node, dict) else {}
            if node_props and node_props.get("repo_id") != repo_id:
                continue
            status = self.file_status(str(root), rel)
            consumed_hash = str(props.get("content_hash") or "")
            current_hash = str(status.get("current_hash") or "")
            stale = bool(consumed_hash and current_hash and consumed_hash != current_hash)
            if stale:
                events.append({
                    "event": "stale_context_warning",
                    "session_id": str(source_id).replace("session:", "", 1),
                    "path": rel,
                    "repo": str(root),
                    "repo_id": repo_id,
                    "consumed_hash": consumed_hash,
                    "current_hash": current_hash,
                    "consumed_at": created_at,
                    "status": status,
                })
        return {
            "beast_object_type": "workspace_graph_stale_context_events",
            "repo": str(root),
            "repo_id": repo_id,
            "session_id": session_id or "",
            "events": events,
            "event_count": len(events),
        }

    def changed_since(self, root_path: str, timestamp_ns: int = 0) -> Dict[str, Any]:
        root = Path(root_path).resolve()
        repo_id = f"repo:{root}"
        threshold = int(timestamp_ns or 0)
        changed: List[Dict[str, Any]] = []
        indexed = [
            node for node in self.search_nodes(str(root), node_type="file", limit=500)
            if (node.get("properties") or {}).get("repo_id") == repo_id
        ]
        for node in indexed:
            props = node.get("properties") or {}
            rel = str(props.get("path") or node.get("label") or "")
            if not rel or node.get("id") == f"file:{rel}":
                continue
            status = self.file_status(str(root), rel)
            if status["changed"] or int(status.get("current_mtime_ns") or 0) > threshold:
                changed.append(status)
        return {
            "beast_object_type": "workspace_graph_changed_since",
            "repo": str(root),
            "repo_id": repo_id,
            "timestamp_ns": threshold,
            "changed": changed,
            "changed_count": len(changed),
        }

    def graph_context_for_task(
        self,
        objective: str,
        selected_files: Optional[List[str]] = None,
        token_budget: int = 3000,
        limit: int = 8,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = str(objective or "")
        selected_files = [str(item) for item in (selected_files or []) if item]
        results: List[Dict[str, Any]] = []
        seen = set()
        for rel in selected_files:
            for node in self.search_nodes(rel, node_type="file", limit=3):
                if node["id"] not in seen:
                    results.append({"reason": "selected_file", "node": node})
                    seen.add(node["id"])
        for node_type in ["symbol", "file", "route", "semantic_chunk", "beast_artifact"]:
            for node in self._lexical_semantic_search(query, limit=limit, node_types=[node_type]):
                if node["id"] not in seen:
                    results.append({"reason": f"{node_type}_match", "node": node})
                    seen.add(node["id"])
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        budget = max(256, int(token_budget or 3000))
        packed: List[Dict[str, Any]] = []
        used_chars = 0
        max_chars = budget * 4
        for item in results[:limit]:
            node = item["node"]
            props = node.get("properties") or {}
            content = str(props.get("content") or props.get("preview") or "")
            remaining = max(0, max_chars - used_chars)
            if remaining <= 0:
                break
            snippet = content[: min(len(content), remaining, 1200)]
            used_chars += len(snippet)
            packed.append({
                "reason": item["reason"],
                "node_id": node.get("id"),
                "type": node.get("type"),
                "label": node.get("label"),
                "path": props.get("path") or props.get("file") or node.get("label"),
                "language": props.get("language") or "",
                "line": props.get("line"),
                "end_line": props.get("end_line"),
                "content": snippet,
            })
        consumed_paths = sorted({
            str(item.get("path") or "")
            for item in packed
            if item.get("path") and not str(item.get("path")).startswith("artifact:")
        })
        consumption = None
        if session_id and consumed_paths:
            roots = [
                (item.get("node", {}).get("properties") or {}).get("repo")
                for item in results
                if isinstance(item.get("node"), dict)
            ]
            root = next((str(item) for item in roots if item), "")
            if root:
                consumption = self.record_context_consumption(session_id, root, consumed_paths, objective=query)
        return {
            "beast_object_type": "workspace_graph_task_context",
            "query": query,
            "selected_files": selected_files,
            "token_budget": budget,
            "estimated_tokens": max(1, used_chars // 4),
            "results": packed,
            "result_count": len(packed),
            "context_consumption": consumption,
        }

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
            candidates.extend(self.search_nodes(query, node_type=node_type, limit=max(10, limit * 10)))
        candidates.extend(self._all_nodes_for_types(types, max(50, limit * 25)))
        deduped: Dict[str, Dict[str, Any]] = {}
        for node in candidates:
            deduped[str(node.get("id"))] = node
        scored = self._score_nodes(query, list(deduped.values()), limit)
        return scored or list(deduped.values())[:limit]

    def vector_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search embedded semantic chunks, falling back to local lexical scoring."""
        self.ensure_db()
        query_embedding = self._generate_embedding(query or "")
        if not query_embedding:
            return self._lexical_semantic_search(
                query, limit=limit,
                node_types=["semantic_chunk", "file", "symbol", "route", "beast_artifact"],
            )
        scored: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT node_id, embedding FROM embeddings LIMIT 2000").fetchall()
        for node_id, embedding_json in rows:
            try:
                embedding = json.loads(embedding_json or "[]")
            except Exception:
                embedding = []
            if not embedding or not query_embedding:
                continue
            dot = sum(float(a) * float(b) for a, b in zip(query_embedding, embedding))
            qn = math.sqrt(sum(float(a) * float(a) for a in query_embedding))
            en = math.sqrt(sum(float(a) * float(a) for a in embedding))
            similarity = dot / (qn * en) if qn and en else 0.0
            node = self.get_node(str(node_id))
            if node:
                item = dict(node)
                item["score"] = round(float(similarity), 6)
                scored.append(item)
        if scored:
            return sorted(scored, key=lambda item: float(item.get("score") or 0), reverse=True)[:limit]
        return self._lexical_semantic_search(query, limit=limit, node_types=["semantic_chunk", "file", "symbol", "route", "beast_artifact"])

    def record_sourceplan_apply(
        self,
        root_path: str,
        plan: Dict[str, Any],
        applied_paths: List[str],
        verification: Optional[Dict[str, Any]] = None,
        rollback_path: str = "",
    ) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        repo_id = f"repo:{root}"
        timestamp = self._utc_now()
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        plan_node = f"sourceplan:{plan_id}"
        self.upsert_node(plan_node, "sourceplan", plan_id, {
            "plan_id": plan_id,
            "objective": plan.get("objective") or "",
            "provider": plan.get("provider") or "",
            "repo": str(root),
            "repo_id": repo_id,
            "rollback_path": rollback_path,
            "applied_paths": applied_paths,
        }, timestamp)
        verification_node = ""
        if verification is not None:
            verification_node = f"verification:{plan_id}:{hashlib.sha256(json.dumps(verification, sort_keys=True, default=str).encode()).hexdigest()[:12]}"
            self.upsert_node(verification_node, "verification", f"{plan_id}:verification", {
                "plan_id": plan_id,
                "ok": bool(verification.get("ok")) if isinstance(verification, dict) else False,
                "verification": verification,
                "repo": str(root),
                "repo_id": repo_id,
            }, timestamp)
            self.upsert_edge(plan_node, verification_node, "verified_by", {}, timestamp)
        for rel in applied_paths or []:
            file_id = self._file_node_id(repo_id, str(rel))
            if not self.get_node(file_id) and (root / str(rel)).exists():
                try:
                    content = (root / str(rel)).read_text(encoding="utf-8", errors="replace")
                    metadata = file_metadata(root / str(rel), root, content)
                    metadata.update({"repo": str(root), "repo_id": repo_id})
                    self.upsert_node(file_id, "file", str(rel), metadata, timestamp)
                except OSError:
                    pass
            self.upsert_edge(file_id, plan_node, "changed_by", {"plan_id": plan_id, "rollback_path": rollback_path}, timestamp)
            if verification_node:
                self.upsert_edge(file_id, verification_node, "verified_by", {"plan_id": plan_id}, timestamp)
        return {
            "beast_object_type": "workspace_graph_sourceplan_apply",
            "plan_id": plan_id,
            "repo": str(root),
            "repo_id": repo_id,
            "applied_count": len(applied_paths or []),
            "verification_node": verification_node,
        }

    def record_sourceplan_rollback(
        self,
        root_path: str,
        rollback: Dict[str, Any],
        restored: List[str],
        deleted: List[str],
    ) -> Dict[str, Any]:
        self.ensure_db()
        root = Path(root_path).resolve()
        repo_id = f"repo:{root}"
        timestamp = self._utc_now()
        plan_id = str(rollback.get("plan_id") or f"rollback_{int(time.time())}")
        rollback_node = f"rollback:{plan_id}:{int(time.time())}"
        affected = list(restored or []) + list(deleted or [])
        self.upsert_node(rollback_node, "rollback", plan_id, {
            "plan_id": plan_id,
            "repo": str(root),
            "repo_id": repo_id,
            "restored": restored,
            "deleted": deleted,
        }, timestamp)
        for rel in affected:
            file_id = self._file_node_id(repo_id, str(rel))
            self.upsert_edge(file_id, rollback_node, "changed_by", {"plan_id": plan_id, "rollback": True}, timestamp)
        return {
            "beast_object_type": "workspace_graph_sourceplan_rollback",
            "plan_id": plan_id,
            "repo": str(root),
            "repo_id": repo_id,
            "affected_count": len(affected),
        }

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

    def semantic_projection_records(self, limit: int = 10000) -> List[Dict[str, Any]]:
        """Expose indexed chunks as rebuildable, non-authoritative projections."""
        self.ensure_db()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, type, label, properties, first_seen, last_seen FROM nodes WHERE type = ? ORDER BY last_seen DESC LIMIT ?",
                ("semantic_chunk", max(1, min(int(limit), 50000))),
            ).fetchall()
        records = []
        for row in rows:
            node = self._row_to_node(row)
            props = node.get("properties") or {}
            content = str(props.get("content") or props.get("preview") or "")
            if not content:
                continue
            records.append({
                "id": node["id"],
                "content": content,
                "metadata": {
                    "file": props.get("file") or props.get("path") or "",
                    "start_line": props.get("start_line"),
                    "end_line": props.get("end_line"),
                    "chunk_kind": props.get("chunk_kind") or "code_window",
                    "context_header": props.get("context_header") or "",
                    "node_type": node["type"],
                },
                "source": "workspace_graph",
            })
        return records

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
