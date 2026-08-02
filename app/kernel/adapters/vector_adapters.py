"""Vector/RAG adapter status contracts for BEAST memory."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class VectorAdapterStatus:
    adapter_id: str
    name: str
    status: str
    source_of_truth: bool
    dense_vectors: bool
    lexical_fallback: bool
    metadata_filters_first: bool
    governance: str
    reason: str
    package: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VectorAdapterRegistry:
    """Report active and future vector/RAG stores without making them truth."""

    def list_adapters(self) -> Dict[str, Any]:
        adapters = [
            self._sqlite_local(),
            self._pgvector(),
            self._qdrant(),
            self._chroma(),
            self._lancedb_duckdb_parquet(),
        ]
        return {
            "beast_object_type": "vector_adapter_inventory",
            "version": "1.0",
            "source_of_truth": "sqlite_graph_and_append_only_records",
            "active_adapter": "sqlite_local_embeddings",
            "mandatory_rules": [
                "lexical_fallback_must_work_without_embeddings",
                "metadata_filters_before_scoring",
                "dense_vectors_optional",
                "append_only_truth_before_retrieval_views",
            ],
            "adapters": [adapter.to_dict() for adapter in adapters],
        }

    def _sqlite_local(self) -> VectorAdapterStatus:
        has_embeddings = importlib.util.find_spec("sentence_transformers") is not None
        return VectorAdapterStatus(
            adapter_id="sqlite_local_embeddings",
            name="SQLite plus optional local embeddings",
            status="active",
            source_of_truth=True,
            dense_vectors=has_embeddings,
            lexical_fallback=True,
            metadata_filters_first=True,
            governance="current_fit",
            reason="Matches current BEAST graph/forensic architecture; embeddings are optional.",
            package="sentence_transformers",
        )

    def _pgvector(self) -> VectorAdapterStatus:
        has_client = importlib.util.find_spec("psycopg") is not None
        configured = bool(os.environ.get("BEAST_PGVECTOR_DSN"))
        return VectorAdapterStatus(
            adapter_id="pgvector",
            name="Postgres pgvector",
            status="configured_pending_health" if configured else "adapter_target",
            source_of_truth=False,
            dense_vectors=has_client,
            lexical_fallback=True,
            metadata_filters_first=True,
            governance="best_for_shared_sql_governance",
            reason=("DSN reference configured; health check and CREATE EXTENSION vector remain required."
                    if configured else "Client dependency is ready; set BEAST_PGVECTOR_DSN for a PostgreSQL database with the pgvector extension."),
            package="psycopg",
        )

    def _qdrant(self) -> VectorAdapterStatus:
        configured = bool(os.environ.get("BEAST_QDRANT_URL") and os.environ.get("BEAST_QDRANT_API_KEY"))
        return VectorAdapterStatus(
            adapter_id="qdrant",
            name="Qdrant",
            status="configured_pending_health" if configured else "adapter_target",
            source_of_truth=False,
            dense_vectors=importlib.util.find_spec("qdrant_client") is not None,
            lexical_fallback=True,
            metadata_filters_first=True,
            governance="best_for_hybrid_dense_sparse_named_vectors",
            reason=("Endpoint and API-key reference configured; health check remains required."
                    if configured else "Set BEAST_QDRANT_URL and BEAST_QDRANT_API_KEY to enable a health-checked projection."),
            package="qdrant_client",
        )

    def _chroma(self) -> VectorAdapterStatus:
        configured = bool(os.environ.get("BEAST_CHROMA_API_KEY") and os.environ.get("BEAST_CHROMA_TENANT"))
        return VectorAdapterStatus(
            adapter_id="chroma",
            name="Chroma",
            status="configured_pending_health" if configured else "prototype_target",
            source_of_truth=False,
            dense_vectors=importlib.util.find_spec("chromadb") is not None,
            lexical_fallback=True,
            metadata_filters_first=True,
            governance="quick_local_prototype_weaker_governance",
            reason=("Cloud credential references configured; tenant/database health check remains required."
                    if configured else "Set BEAST_CHROMA_API_KEY, BEAST_CHROMA_TENANT, and BEAST_CHROMA_DATABASE for cloud Chroma."),
            package="chromadb",
        )

    def _lancedb_duckdb_parquet(self) -> VectorAdapterStatus:
        has_lancedb = importlib.util.find_spec("lancedb") is not None
        has_duckdb = importlib.util.find_spec("duckdb") is not None
        return VectorAdapterStatus(
            adapter_id="lancedb_duckdb_parquet",
            name="LanceDB/DuckDB/Parquet",
            status="configured_local" if os.environ.get("BEAST_LANCEDB_URI") else "analytical_snapshot_target",
            source_of_truth=False,
            dense_vectors=has_lancedb,
            lexical_fallback=True,
            metadata_filters_first=True,
            governance="local_analytical_memory_and_artifact_snapshots",
            reason=("Local LanceDB URI configured as a retrieval projection."
                    if os.environ.get("BEAST_LANCEDB_URI") else "Set BEAST_LANCEDB_URI (for example .beast/lancedb) for local analytical snapshots."),
            package="lancedb/duckdb",
        )
