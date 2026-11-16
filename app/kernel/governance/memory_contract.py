"""Compute Governor spine: the 4-tier memory read/write contract (no new facade over the stores).

Perceive reads cheapest-first: (1) exact/fingerprint hits — semantic compute pages, DurableInferenceStorage
credits, crystal ids, LocalSemanticCache hashes; (2) schema trees — tree-sitter/regex symbols from
``code_indexers`` plus ``SemanticCapabilityContract`` digests; (3) the L2 workspace graph; (4) local Chroma vector
RAG under ``app/data/chroma``, last. Only a *verified exact* hit is an admissible input to the governor; schema,
graph and vector hits only nominate (IEI v0.9 §7.12.1: similarity never grants). The result feeds the Task
Envelope and ``Proposal.memory``; ``ComputeGovernorSpine`` refuses any proposal claiming a grant from a nomination.

Crystallize writes a verified episode (verifier, quality and held-out checks all passed) to the matching tiers:
exact residue → pages/crystals, structure → graph/contracts, optional local-only embeddings, skills → L3,
receipts → L4, composites → lattice. Nothing is written before verification. Embeddings pass a privacy filter and
go only to a local sink; remote Qdrant, pgvector and Chroma Cloud are refused, never configured.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

TIERS = ("exact", "schema", "graph", "vector")
GRANTING_TIERS = frozenset({"exact"})
WRITE_TIERS = ("pages", "graph", "embeddings", "skills", "receipts", "lattice")
EPISODE_FIELD_FOR_SINK = {"pages": "exact_residue", "graph": "structure", "embeddings": "embeddings",
                          "skills": "skills", "receipts": "receipts", "lattice": "composites"}
VERIFICATION_KEYS = ("verifier_passed", "quality_passed", "heldout_passed")
REMOTE_VECTOR_ENV = ("CHROMA_API_KEY", "CHROMA_SERVER_HOST", "CHROMA_CLOUD_TENANT", "QDRANT_URL", "QDRANT_API_KEY",
                     "PGVECTOR_DSN", "PGVECTOR_URL")
REMOTE_VECTOR_BACKENDS = frozenset({"qdrant", "pgvector", "chroma_cloud", "chroma-cloud", "chroma_http"})
Source = Callable[[Any], Iterable["MemoryHit"]]


class MemoryContractError(ValueError):
    pass


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 default=str).encode()).hexdigest()


@dataclass(frozen=True)
class MemoryHit:
    tier: str
    source: str
    key: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    grants: bool = False

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise MemoryContractError(f"unknown_memory_tier:{self.tier}")
        if self.grants and self.tier not in GRANTING_TIERS:
            raise MemoryContractError(f"{self.tier}_hits_never_grant")

    def to_dict(self) -> dict[str, Any]:
        return {"tier": self.tier, "source": self.source, "key": self.key, "grants": self.grants,
                "payload_digest": _sha(dict(self.payload))}


@dataclass
class MemoryReadResult:
    hits: list[MemoryHit]
    trace: list[dict[str, Any]]

    def admission_inputs(self) -> dict[str, Any]:
        """Governor inputs: verified exact hits are admissible; everything else is a nomination only."""
        return {"memory_exact": [h.to_dict() for h in self.hits if h.grants],
                "memory_nominations": [h.to_dict() for h in self.hits if not h.grants]}

    def task_envelope_fields(self) -> dict[str, Any]:
        inputs = self.admission_inputs()
        return {"memory_exact": inputs["memory_exact"], "memory_nominations": inputs["memory_nominations"],
                "memory_trace": [dict(t) for t in self.trace], "memory_read_digest": _sha(inputs)}


class MemoryReader:
    """One reader, cheapest tier first; a verified exact hit stops the descent (vector RAG is never reached)."""

    def __init__(self, *, exact: Sequence[Source] = (), schema: Sequence[Source] = (), graph: Sequence[Source] = (),
                 vector: Sequence[Source] = (), stop_on_exact: bool = True):
        self.tiers = {"exact": list(exact), "schema": list(schema), "graph": list(graph), "vector": list(vector)}
        self.stop_on_exact = stop_on_exact

    def read(self, query: Any) -> MemoryReadResult:
        hits: list[MemoryHit] = []
        trace: list[dict[str, Any]] = []
        for tier in TIERS:
            for source in self.tiers[tier]:
                entry: dict[str, Any] = {"tier": tier, "source": getattr(source, "__name__", type(source).__name__)}
                try:
                    found = [self._coerce(tier, hit) for hit in (source(query) or [])]
                except MemoryContractError:
                    raise
                except Exception as exc:  # noqa: BLE001 - one broken store never breaks Perceive
                    entry["error"] = type(exc).__name__
                    found = []
                entry["hits"] = len(found)
                trace.append(entry)
                hits.extend(found)
            if self.stop_on_exact and tier == "exact" and any(h.grants for h in hits):
                break
        return MemoryReadResult(hits, trace)

    @staticmethod
    def _coerce(tier: str, hit: MemoryHit) -> MemoryHit:
        if hit.tier != tier:
            raise MemoryContractError(f"tier_mismatch:{hit.tier}!={tier}")
        if tier == "exact" and not hit.grants and bool(hit.payload.get("verified")):
            return MemoryHit(tier, hit.source, hit.key, hit.payload, grants=True)
        return hit


# -- default sources over the existing stores (duck-typed; no new facade) ------------------------------------
def _q(query: Any, key: str, default: Any = "") -> Any:
    return query.get(key, default) if isinstance(query, Mapping) else (query if key == "prompt" else default)


def crystal_source(registry: Any) -> Source:
    def crystal_ids(query: Any) -> list[MemoryHit]:
        crystal_id = str(_q(query, "crystal_id") or "")
        family = str(_q(query, "task_family") or "")
        record = None
        if crystal_id:
            try:
                record = registry.get(crystal_id)
            except (LookupError, ValueError):
                record = None
        elif family and hasattr(registry, "active_for_family"):
            candidate = registry.active_for_family(family)
            record = {"crystal_id": candidate.crystal_id, "status": "promoted"} if candidate else None
        if not record:
            return []
        verified = record.get("status") == "promoted"
        return [MemoryHit("exact", "crystal_registry", str(record["crystal_id"]),
                          {"crystal_id": record["crystal_id"], "status": record.get("status"), "verified": verified})]
    return crystal_ids


def credit_source(storage: Any) -> Source:
    def durable_credits(query: Any) -> list[MemoryHit]:
        credit = storage.lookup_reusable_credit(str(_q(query, "task_class") or "general"),
                                                _q(query, "repo_fingerprint") or None)
        if credit is None:
            return []
        return [MemoryHit("exact", "durable_inference_storage", str(credit.credit_id),
                          {"credit_id": credit.credit_id, "verified": bool(getattr(credit, "verified", True))})]
    return durable_credits


def semantic_cache_source(cache: Any) -> Source:
    def local_semantic_cache(query: Any) -> list[MemoryHit]:
        hit = cache.match(prompt=str(_q(query, "prompt") or ""), task_class=str(_q(query, "task_class") or "general"),
                          repo_fingerprint=str(_q(query, "repo_fingerprint") or ""), threshold=1.0,
                          require_verified=True)
        if hit is None:
            return []
        exact = getattr(hit, "match_type", "") in {"exact", "exact_hash"} or float(getattr(hit, "similarity", 0)) >= 1.0
        return [MemoryHit("exact", "local_semantic_cache", str(getattr(hit, "credit_id", "")),
                          {"credit_id": getattr(hit, "credit_id", ""), "verified": exact})]
    return local_semantic_cache


def page_source(store: Any) -> Source:
    def semantic_pages(query: Any) -> list[MemoryHit]:
        identity = _q(query, "page_identity", None)
        if identity is None:
            return []
        found = store.lookup(identity, record_reuse=False)
        if not found.get("hit"):
            return []
        page = found.get("page") or {}
        return [MemoryHit("exact", "semantic_compute_pages", str(page.get("page_id") or ""),
                          {"page_id": page.get("page_id"), "verified": bool(found.get("verified", True))})]
    return semantic_pages


def schema_source(root: Any = None) -> Source:
    def schema_trees(query: Any) -> list[MemoryHit]:
        from pathlib import Path

        from app.kernel.data_processing.code_indexers import extract_symbols, language_for_path

        hits: list[MemoryHit] = []
        base = Path(root) if root else None
        for rel in _q(query, "files", []) or []:
            path = (base / rel) if base else Path(rel)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for symbol in extract_symbols(text, language_for_path(path), str(rel))[:50]:
                hits.append(MemoryHit("schema", "code_indexers", f"{rel}:{symbol.get('name')}", dict(symbol)))
        contract = _q(query, "capability_contract", None)
        if contract is not None and hasattr(contract, "digest"):
            hits.append(MemoryHit("schema", "semantic_capability_contract", contract.digest,
                                  {"operation": contract.operation, "risk_tier": contract.risk_tier}))
        return hits
    return schema_trees


def graph_source(workspace_graph: Any, limit: int = 8) -> Source:
    def workspace_graph_l2(query: Any) -> list[MemoryHit]:
        text = str(_q(query, "prompt") or "")
        return [MemoryHit("graph", "workspace_graph", str(node.get("id") or node.get("node_id") or ""),
                          {"type": node.get("type"), "label": node.get("label")})
                for node in workspace_graph.search_nodes(text, limit=limit)]
    return workspace_graph_l2


def vector_source(workspace_graph: Any, limit: int = 5, env: Mapping[str, str] | None = None) -> Source:
    assert_local_vector_backend(env)

    def local_chroma(query: Any) -> list[MemoryHit]:
        return [MemoryHit("vector", "local_chroma", str(item.get("id") or item.get("node_id") or ""),
                          {"score": item.get("score"), "type": item.get("type")})
                for item in workspace_graph.vector_search(str(_q(query, "prompt") or ""), limit=limit)]
    return local_chroma


def assert_local_vector_backend(env: Mapping[str, str] | None = None) -> None:
    import os

    env = os.environ if env is None else env
    configured = [key for key in REMOTE_VECTOR_ENV if str(env.get(key) or "").strip()]
    backend = str(env.get("BEAST_VECTOR_BACKEND") or "").strip().lower()
    if configured or backend in REMOTE_VECTOR_BACKENDS:
        raise MemoryContractError(f"remote_vector_backend_refused:{','.join(configured) or backend}")


# -- Crystallize ---------------------------------------------------------------------------------------------
def privacy_filter(items: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop secret-bearing or private items before any embedding (local or not)."""
    from app.kernel.sensorium.episode_envelope import _contains_secret

    kept, dropped = [], 0
    for item in items:
        item = dict(item)
        if item.get("private") or item.get("cloud_only") or _contains_secret(json.dumps(item, default=str)):
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


class MemoryWriter:
    def __init__(self, **sinks: Callable[[dict[str, Any]], Any] | None):
        unknown = set(sinks) - set(WRITE_TIERS)
        if unknown:
            raise MemoryContractError(f"unknown_write_tier:{sorted(unknown)}")
        embeddings = sinks.get("embeddings")
        if embeddings is not None and getattr(embeddings, "local", False) is not True:
            raise MemoryContractError("embedding_sink_must_be_local")
        self.sinks = {k: v for k, v in sinks.items() if v is not None}

    def crystallize(self, episode: Mapping[str, Any], verification: Mapping[str, Any]) -> dict[str, Any]:
        failed = [k for k in VERIFICATION_KEYS if verification.get(k) is not True]
        if failed:
            raise MemoryContractError(f"crystallize_requires_verified_episode:{','.join(failed)}")
        plan: dict[str, list[dict[str, Any]]] = {}
        dropped = 0
        for sink in self.sinks:
            items = [dict(i) for i in episode.get(EPISODE_FIELD_FOR_SINK[sink]) or []]
            if sink == "embeddings":
                items, dropped = privacy_filter(items)
            plan[sink] = items
        written = {}
        for sink, items in plan.items():  # all filtering done first; writes only after the plan is complete
            for item in items:
                self.sinks[sink](item)
            written[sink] = len(items)
        return {"schema": "beast.memory_crystallize.v1", "episode_digest": str(verification.get("episode_digest") or ""),
                "written": written, "privacy_dropped": dropped, "plan_digest": _sha(plan)}


__all__ = ["GRANTING_TIERS", "TIERS", "MemoryContractError", "MemoryHit", "MemoryReadResult", "MemoryReader",
           "MemoryWriter", "assert_local_vector_backend", "credit_source", "crystal_source", "graph_source",
           "page_source", "privacy_filter", "schema_source", "semantic_cache_source", "vector_source"]
