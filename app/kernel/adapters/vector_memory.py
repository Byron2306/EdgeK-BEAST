"""Governed multi-backend vector memory for BEAST.

Workspace/Chronicle records remain the source of truth.  This module maintains
rebuildable retrieval projections in pgvector, Qdrant, Chroma, and LanceDB and
always returns store attribution so a similarity hit cannot silently become an
instruction, edit scope, or trusted fact.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote


class VectorMemoryFabric:
    """Project governed records into their permitted L0-L4 retrieval views.

    This is intentionally *not* a generic replication client.  In particular,
    L2 workspace source can never be sent to a configured cloud backend: it is
    a rebuildable local LanceDB view.  Cloud backends are reserved for the
    small, validated L3/L4 operational records described in ``MEMORY_POLICIES``.
    """

    COLLECTIONS = {
        "workspace_source": "beast_workspace_l2",
        "verified_skill": "beast_skills_l3",
        "forensic_summary": "beast_forensics_l4",
    }
    MEMORY_POLICIES = {
        "workspace_source": {"layer": "L2", "backends": ("lancedb",), "cloud": False},
        "verified_skill": {"layer": "L3", "backends": ("pgvector", "qdrant", "chroma", "lancedb"), "cloud": True},
        "forensic_summary": {"layer": "L4", "backends": ("pgvector", "qdrant", "chroma", "lancedb"), "cloud": True},
    }
    _CLOUD_SAFE_METADATA = {
        "memory_layer", "memory_kind", "source_of_truth", "verified", "receipt_id",
        "operator_accepted", "projection_scope", "workspace_id", "skill_id", "run_id",
        "outcome", "quality_status", "provider", "created_at", "tags", "schema_version",
    }
    _REJECTED_CLOUD_FIELDS = {
        "code", "source", "source_code", "content", "diff", "patch", "prompt", "messages",
        "conversation", "log", "logs", "terminal", "file", "path", "files", "raw_output",
    }

    def __init__(self, root: str | Path | None = None, *, dimensions: Optional[int] = None):
        self.root = Path(root or Path(__file__).resolve().parents[3]).resolve()
        self.config = self._config()
        self.dimensions = max(8, min(int(dimensions or self.config.get("BEAST_VECTOR_DIMENSIONS") or 64), 512))

    def _config(self) -> Dict[str, str]:
        values = {key: value for key, value in os.environ.items() if value}
        env_path = self.root / ".beast" / "vector.env"
        if not env_path.is_file():
            return values
        # This is deliberately a tiny parser, not `source`: config can never
        # execute shell code and static AWS secrets are intentionally ignored.
        blocked = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"}
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in blocked and key not in values:
                values[key] = value
        return values

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _embedding(self, text: str) -> List[float]:
        """Stable local lexical embedding; no model download or secret required."""
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]*", (text or "").lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[slot] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [round(value / norm, 8) for value in vector] if norm else vector

    def _pg_dsn(self) -> str:
        configured = self.config.get("BEAST_PGVECTOR_DSN", "")
        if configured:
            return configured
        if self.config.get("BEAST_PGVECTOR_IAM_AUTH") != "1":
            return ""
        needed = ("BEAST_PGVECTOR_HOST", "BEAST_PGVECTOR_PORT", "BEAST_PGVECTOR_DATABASE", "BEAST_PGVECTOR_USER", "BEAST_PGVECTOR_AWS_REGION")
        if not all(self.config.get(key) for key in needed):
            return ""
        aws = self.root / "venv" / "bin" / "aws"
        aws_command = str(aws) if aws.is_file() else "aws"
        env = os.environ.copy()
        if self.config.get("AWS_PROFILE"):
            env["AWS_PROFILE"] = self.config["AWS_PROFILE"]
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
            env.pop(key, None)
        try:
            token = subprocess.run(
                [aws_command, "rds", "generate-db-auth-token", "--hostname", self.config["BEAST_PGVECTOR_HOST"],
                 "--port", self.config["BEAST_PGVECTOR_PORT"], "--username", self.config["BEAST_PGVECTOR_USER"],
                 "--region", self.config["BEAST_PGVECTOR_AWS_REGION"]],
                check=True, capture_output=True, text=True, timeout=12, env=env,
            ).stdout.strip()
        except Exception:
            return ""
        return (
            f"postgresql://{self.config['BEAST_PGVECTOR_USER']}:{quote(token, safe='')}@"
            f"{self.config['BEAST_PGVECTOR_HOST']}:{self.config['BEAST_PGVECTOR_PORT']}/"
            f"{self.config['BEAST_PGVECTOR_DATABASE']}?sslmode={self.config.get('BEAST_PGVECTOR_SSLMODE', 'require')}&connect_timeout=12"
        )

    def _records(self, records: Iterable[Dict[str, Any]], *, purpose: str) -> List[Dict[str, Any]]:
        policy = self.MEMORY_POLICIES[purpose]
        out: List[Dict[str, Any]] = []
        for raw in records:
            memory_id = str(raw.get("id") or raw.get("node_id") or "").strip()
            content = str(raw.get("content") or raw.get("text") or "").strip()
            if not memory_id or not content:
                continue
            metadata = dict(raw.get("metadata") or raw.get("properties") or {})
            metadata.update({
                "memory_id": memory_id,
                "memory_layer": policy["layer"],
                "memory_kind": purpose,
                "source_of_truth": str(metadata.get("source_of_truth") or raw.get("source") or "local_canonical_store"),
                "projection_scope": "local_only" if not policy["cloud"] else "cloud_safe_operational",
                "updated_at": self._utc_now(),
            })
            out.append({"id": memory_id, "content": content, "metadata": metadata, "vector": self._embedding(content)})
        return out

    def _cloud_safe_records(self, records: Iterable[Dict[str, Any]], *, purpose: str) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Accept only terse L3/L4 summaries, never source, prompts, or logs."""
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, str]] = []
        for raw in records:
            keys = {str(key).lower() for key in raw}
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            metadata_keys = {str(key).lower() for key in metadata}
            forbidden = (keys | metadata_keys) & self._REJECTED_CLOUD_FIELDS
            summary = str(raw.get("summary") or raw.get("content") or "").strip()
            if forbidden:
                rejected.append({"id": str(raw.get("id") or "unknown"), "reason": "cloud record contains a forbidden raw-data field"})
                continue
            if not summary or len(summary) > 4000:
                rejected.append({"id": str(raw.get("id") or "unknown"), "reason": "cloud summary must be 1-4000 characters"})
                continue
            safe_metadata = {key: value for key, value in metadata.items() if str(key) in self._CLOUD_SAFE_METADATA}
            if not bool(safe_metadata.get("verified")) or not str(safe_metadata.get("receipt_id") or "").strip():
                rejected.append({"id": str(raw.get("id") or "unknown"), "reason": "cloud L3/L4 records require verified=true and receipt_id"})
                continue
            accepted.append({"id": raw.get("id"), "content": summary, "metadata": safe_metadata, "source": "sanitized_operational_summary"})
        return self._records(accepted, purpose=purpose), rejected

    @staticmethod
    def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {str(key): value if isinstance(value, (str, int, float, bool)) else json.dumps(value, sort_keys=True, default=str)
                for key, value in metadata.items() if value is not None}

    def _pg_connection(self):
        dsn = self._pg_dsn()
        if not dsn:
            raise RuntimeError("pgvector is not configured")
        import psycopg  # optional integration dependency
        return psycopg.connect(dsn, connect_timeout=12)

    def _write_pgvector(self, records: List[Dict[str, Any]], collection: str) -> Dict[str, Any]:
        if not records:
            return {"backend": "pgvector", "ok": True, "count": 0}
        with self._pg_connection() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS beast_memory_vectors ("
                f"memory_id TEXT PRIMARY KEY, content TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb, "
                f"embedding vector({self.dimensions}) NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            for record in records:
                vector = "[" + ",".join(str(value) for value in record["vector"]) + "]"
                cur.execute(
                    "INSERT INTO beast_memory_vectors (memory_id, content, metadata, embedding) VALUES (%s, %s, %s::jsonb, %s::vector) "
                    "ON CONFLICT (memory_id) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding, updated_at = now()",
                    (f"{collection}:{record['id']}", record["content"], json.dumps(record["metadata"], default=str), vector),
                )
        return {"backend": "pgvector", "ok": True, "count": len(records)}

    def _write_qdrant(self, records: List[Dict[str, Any]], collection: str) -> Dict[str, Any]:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
        client = QdrantClient(url=self.config["BEAST_QDRANT_URL"], api_key=self.config["BEAST_QDRANT_API_KEY"], timeout=12)
        try:
            client.get_collection(collection)
        except Exception:
            client.create_collection(collection, vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE))
        points = [PointStruct(id=str(__import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, record["id"])), vector=record["vector"], payload={**self._safe_metadata(record["metadata"]), "content": record["content"]}) for record in records]
        client.upsert(collection, points=points, wait=True)
        return {"backend": "qdrant", "ok": True, "count": len(records)}

    def _chroma_client(self):
        import chromadb
        return chromadb.CloudClient(api_key=self.config["BEAST_CHROMA_API_KEY"], tenant=self.config["BEAST_CHROMA_TENANT"], database=self.config.get("BEAST_CHROMA_DATABASE") or "default_database")

    def _write_chroma(self, records: List[Dict[str, Any]], collection: str) -> Dict[str, Any]:
        target = self._chroma_client().get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        target.upsert(ids=[record["id"] for record in records], embeddings=[record["vector"] for record in records], documents=[record["content"] for record in records], metadatas=[self._safe_metadata(record["metadata"]) for record in records])
        return {"backend": "chroma", "ok": True, "count": len(records)}

    def _write_lancedb(self, records: List[Dict[str, Any]], collection: str) -> Dict[str, Any]:
        import lancedb
        db = lancedb.connect(self.config["BEAST_LANCEDB_URI"])
        rows = [{"id": item["id"], "content": item["content"], "metadata": json.dumps(item["metadata"], default=str), "vector": item["vector"]} for item in records]
        try:
            table = db.open_table(collection)
            table.delete("id IN (" + ",".join(repr(row["id"]) for row in rows) + ")")
            table.add(rows)
        except Exception:
            db.create_table(collection, data=rows, mode="overwrite")
        return {"backend": "lancedb", "ok": True, "count": len(rows)}

    def ingest(self, records: Iterable[Dict[str, Any]], *, purpose: str = "workspace_source") -> Dict[str, Any]:
        if purpose not in self.MEMORY_POLICIES:
            raise ValueError(f"Unsupported vector memory purpose: {purpose}")
        policy = self.MEMORY_POLICIES[purpose]
        enabled_key = "BEAST_VECTOR_MEMORY_LOCAL_PROJECTION_ENABLED" if not policy["cloud"] else "BEAST_VECTOR_MEMORY_CLOUD_OPERATIONAL_ENABLED"
        if policy["cloud"]:
            prepared, rejected = self._cloud_safe_records(records, purpose=purpose)
        else:
            prepared, rejected = self._records(records, purpose=purpose), []
        if self.config.get(enabled_key, "0").strip().lower() not in {"1", "true", "yes"}:
            return {
                "beast_object_type": "vector_memory_ingest",
                "record_count": len(prepared),
                "projections": [],
                "memory_layer": policy["layer"],
                "purpose": purpose,
                "rejected": rejected,
                "projection_rule": f"Projection is disabled until {enabled_key}=1 is explicitly configured.",
            }
        writers = []
        if "pgvector" in policy["backends"] and self._pg_dsn(): writers.append(self._write_pgvector)
        if "qdrant" in policy["backends"] and self.config.get("BEAST_QDRANT_URL") and self.config.get("BEAST_QDRANT_API_KEY"): writers.append(self._write_qdrant)
        if "chroma" in policy["backends"] and self.config.get("BEAST_CHROMA_API_KEY") and self.config.get("BEAST_CHROMA_TENANT"): writers.append(self._write_chroma)
        if "lancedb" in policy["backends"] and self.config.get("BEAST_LANCEDB_URI"): writers.append(self._write_lancedb)
        projections = []
        for writer in writers:
            try:
                projections.append(writer(prepared, self.COLLECTIONS[purpose]))
            except Exception as exc:
                projections.append({"backend": writer.__name__.replace("_write_", ""), "ok": False, "count": 0, "error": str(exc)[:240]})
        return {"beast_object_type": "vector_memory_ingest", "record_count": len(prepared), "projections": projections, "memory_layer": policy["layer"], "purpose": purpose, "rejected": rejected, "projection_rule": "Failures never prevent canonical memory updates; L2 source is local-only."}

    def _search_pgvector(self, vector: List[float], limit: int, collection: str) -> List[Dict[str, Any]]:
        literal = "[" + ",".join(str(value) for value in vector) + "]"
        with self._pg_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT memory_id, content, metadata, 1 - (embedding <=> %s::vector) AS score "
                "FROM beast_memory_vectors WHERE memory_id LIKE %s ORDER BY embedding <=> %s::vector LIMIT %s",
                (literal, f"{collection}:%", literal, limit),
            )
            return [{"id": row[0], "content": row[1], "metadata": dict(row[2] or {}), "score": float(row[3] or 0.0), "backend": "pgvector"} for row in cur.fetchall()]

    def _search_qdrant(self, vector: List[float], limit: int, collection: str) -> List[Dict[str, Any]]:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=self.config["BEAST_QDRANT_URL"], api_key=self.config["BEAST_QDRANT_API_KEY"], timeout=12)
        try:
            points = client.query_points(collection_name=collection, query=vector, limit=limit, with_payload=True).points
        except AttributeError:
            points = client.search(collection_name=collection, query_vector=vector, limit=limit, with_payload=True)
        out = []
        for point in points:
            payload = dict(point.payload or {})
            out.append({"id": str(payload.get("memory_id") or point.id), "content": str(payload.pop("content", "")), "metadata": payload, "score": float(point.score or 0.0), "backend": "qdrant"})
        return out

    def _search_chroma(self, vector: List[float], limit: int, collection: str) -> List[Dict[str, Any]]:
        target = self._chroma_client().get_collection(collection)
        result = target.query(query_embeddings=[vector], n_results=limit, include=["documents", "metadatas", "distances"])
        out = []
        for memory_id, content, metadata, distance in zip(result.get("ids", [[]])[0], result.get("documents", [[]])[0], result.get("metadatas", [[]])[0], result.get("distances", [[]])[0]):
            out.append({"id": str(memory_id), "content": str(content or ""), "metadata": dict(metadata or {}), "score": max(0.0, 1.0 - float(distance or 0.0)), "backend": "chroma"})
        return out

    def _search_lancedb(self, vector: List[float], limit: int, collection: str) -> List[Dict[str, Any]]:
        import lancedb
        table = lancedb.connect(self.config["BEAST_LANCEDB_URI"]).open_table(collection)
        rows = table.search(vector).limit(limit).to_list()
        return [{"id": str(row.get("id")), "content": str(row.get("content") or ""), "metadata": json.loads(row.get("metadata") or "{}"), "score": max(0.0, 1.0 - float(row.get("_distance") or 0.0)), "backend": "lancedb"} for row in rows]

    def search(self, query: str, *, limit: int = 8, purposes: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Return attributed projection hits; callers must apply authority rules."""
        vector, per_backend = self._embedding(query), max(1, min(int(limit), 50))
        requested = tuple(purposes or ("workspace_source", "verified_skill"))
        requested = tuple(item for item in requested if item in self.MEMORY_POLICIES)
        merged: Dict[str, Dict[str, Any]] = {}
        diagnostics = []
        for purpose in requested:
            policy, collection = self.MEMORY_POLICIES[purpose], self.COLLECTIONS[purpose]
            searches = []
            if "pgvector" in policy["backends"] and self._pg_dsn(): searches.append(self._search_pgvector)
            if "qdrant" in policy["backends"] and self.config.get("BEAST_QDRANT_URL") and self.config.get("BEAST_QDRANT_API_KEY"): searches.append(self._search_qdrant)
            if "chroma" in policy["backends"] and self.config.get("BEAST_CHROMA_API_KEY") and self.config.get("BEAST_CHROMA_TENANT"): searches.append(self._search_chroma)
            if "lancedb" in policy["backends"] and self.config.get("BEAST_LANCEDB_URI"): searches.append(self._search_lancedb)
            for search in searches:
                try:
                    hits = search(vector, per_backend, collection)
                    diagnostics.append({"backend": search.__name__.replace("_search_", ""), "purpose": purpose, "ok": True, "count": len(hits)})
                    for hit in hits:
                        key = f"{purpose}:{hit['id']}"
                        hit["memory_layer"] = policy["layer"]
                        hit["memory_kind"] = purpose
                        current = merged.get(key)
                        if not current or float(hit["score"]) > float(current["score"]):
                            merged[key] = hit
                        merged[key].setdefault("projection_backends", []).append(hit["backend"])
                except Exception as exc:
                    diagnostics.append({"backend": search.__name__.replace("_search_", ""), "purpose": purpose, "ok": False, "error": str(exc)[:240]})
        hits = sorted(merged.values(), key=lambda item: float(item.get("score") or 0), reverse=True)[:per_backend]
        for hit in hits:
            hit["projection_backends"] = sorted(set(hit.get("projection_backends") or []))
            hit["requires_operator_acceptance"] = True
        return {"beast_object_type": "vector_memory_search", "query": query, "purposes": list(requested), "hits": hits, "result_count": len(hits), "diagnostics": diagnostics,
                "authority_rule": "Retrieval is advisory context only; it cannot authorize tool use, edits, or crystal promotion."}

    def health(self) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        for name, enabled, probe in (
            ("pgvector", bool(self._pg_dsn()), lambda: self._pg_connection().execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()),
            ("qdrant", bool(self.config.get("BEAST_QDRANT_URL") and self.config.get("BEAST_QDRANT_API_KEY")), lambda: __import__("qdrant_client").QdrantClient(url=self.config["BEAST_QDRANT_URL"], api_key=self.config["BEAST_QDRANT_API_KEY"], timeout=8).get_collections()),
            ("chroma", bool(self.config.get("BEAST_CHROMA_API_KEY") and self.config.get("BEAST_CHROMA_TENANT")), lambda: self._chroma_client().list_collections()),
            ("lancedb", bool(self.config.get("BEAST_LANCEDB_URI")), lambda: __import__("lancedb").connect(self.config["BEAST_LANCEDB_URI"]).table_names()),
        ):
            if not enabled:
                checks.append({"backend": name, "configured": False, "healthy": False})
                continue
            try:
                probe()
                checks.append({"backend": name, "configured": True, "healthy": True})
            except Exception as exc:
                checks.append({"backend": name, "configured": True, "healthy": False, "error": str(exc)[:240]})
        return {
            "beast_object_type": "vector_memory_health",
            "dimensions": self.dimensions,
            "backends": checks,
            "healthy_backends": [item["backend"] for item in checks if item.get("healthy")],
            "memory_policies": {
                purpose: {
                    "layer": policy["layer"],
                    "backends": list(policy["backends"]),
                    "cloud": policy["cloud"],
                    "enabled": self.config.get(
                        "BEAST_VECTOR_MEMORY_CLOUD_OPERATIONAL_ENABLED" if policy["cloud"] else "BEAST_VECTOR_MEMORY_LOCAL_PROJECTION_ENABLED", "0"
                    ).strip().lower() in {"1", "true", "yes"},
                }
                for purpose, policy in self.MEMORY_POLICIES.items()
            },
            "boundary_rule": "L0/L1 remain local; L2 source is LanceDB-only; cloud accepts validated L3/L4 summaries only.",
        }
