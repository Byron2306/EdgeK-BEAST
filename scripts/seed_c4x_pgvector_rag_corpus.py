#!/usr/bin/env python3
"""Seed a small C4-X operational-pattern corpus into Aurora/Postgres pgvector.

The seed rows are deliberately generic: they do not contain held-out service
names or expected answers. They give the external RDS RAG baseline family-level
operational guidance, while the benchmark request supplies the public randomized
facts needed to answer a particular case.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_c4x_rds_rag_adapter import _connection_config, _digest, _quote_ident  # noqa: E402


TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class CorpusRow:
    memory_id: str
    content: str
    metadata: dict[str, Any]


CORPUS: tuple[CorpusRow, ...] = (
    CorpusRow(
        memory_id="c4x:pattern:restart-risk:dependency-policy-current-evidence",
        content=(
            "C4-X restart_risk guidance: restart questions require source service health, "
            "target service health, dependency_topology showing the target depends_on or "
            "routes_through the source, a restart_policy, current_evidence, and the "
            "restart_destabilization rule. Healthy source and target with "
            "rolling_with_healthcheck or blue_green restart policy imply low class; "
            "otherwise supported restarts are elevated. Stale evidence or missing rules "
            "must be refused or sent to residual verification."
        ),
        metadata={
            "source": "beast_c4x_baseline_corpus",
            "family": "restart_risk",
            "chunk_kind": "operational_pattern",
            "claim_boundary": "generic guidance only; no held-out service names or oracle labels",
        },
    ),
    CorpusRow(
        memory_id="c4x:pattern:traffic-shift:capacity-route-reserve",
        content=(
            "C4-X traffic_shift guidance: traffic movement requires source and target "
            "capacity_state, a healthy traffic_route from source to target, current_evidence, "
            "a minimum reserve policy, and the traffic_shift_capacity rule. The target is "
            "safe only when route state is healthy and target spare percent is at least "
            "shift percent plus minimum reserve percent. Otherwise the supported class is "
            "unsafe; missing capacity rule requires residual verification."
        ),
        metadata={
            "source": "beast_c4x_baseline_corpus",
            "family": "traffic_shift",
            "chunk_kind": "operational_pattern",
            "claim_boundary": "generic guidance only; no held-out service names or oracle labels",
        },
    ),
    CorpusRow(
        memory_id="c4x:pattern:deployment-safety:gates-rollback-error-budget",
        content=(
            "C4-X deployment_safety guidance: rollout decisions require deployment_stage, "
            "health_gate, rollback_state, target service_health, current_evidence, a maximum "
            "error rate policy, and the deployment_rollout_safety rule. Continue only when "
            "the health gate passed, rollback is ready, target is healthy, and observed error "
            "rate is within policy. Otherwise halt_or_rollback; missing rollout rule requires "
            "residual verification."
        ),
        metadata={
            "source": "beast_c4x_baseline_corpus",
            "family": "deployment_safety",
            "chunk_kind": "operational_pattern",
            "claim_boundary": "generic guidance only; no held-out service names or oracle labels",
        },
    ),
    CorpusRow(
        memory_id="c4x:pattern:temporal-freshness:stale-refusal",
        content=(
            "C4-X temporal guidance: if scenario metadata marks temporal_state stale, the "
            "system must not assert a current operational claim. It should say it cannot "
            "establish current state and require fresh evidence or residual verification."
        ),
        metadata={
            "source": "beast_c4x_baseline_corpus",
            "family": "all",
            "chunk_kind": "temporal_policy",
            "claim_boundary": "generic guidance only; no held-out service names or oracle labels",
        },
    ),
    CorpusRow(
        memory_id="c4x:pattern:visual-proof-boundary:no-text-to-image-cheat",
        content=(
            "C4-X visual guidance: a visual artifact should be a sibling projection from "
            "verified proof or public facts, not an image generated from the text answer. "
            "External RAG may retrieve diagram guidance but does not gain artifact custody "
            "unless it proves deterministic scene custody."
        ),
        metadata={
            "source": "beast_c4x_baseline_corpus",
            "family": "all",
            "chunk_kind": "visual_boundary",
            "claim_boundary": "generic guidance only; no held-out service names or oracle labels",
        },
    ),
)


def main() -> int:
    try:
        receipt = seed_corpus()
    except Exception as exc:
        receipt = {
            "beast_object_type": "c4x_pgvector_rag_seed_receipt",
            "seed_success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(receipt, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


def seed_corpus() -> dict[str, Any]:
    connection_config = _connection_config()
    if not connection_config["configured"]:
        return {
            "beast_object_type": "c4x_pgvector_rag_seed_receipt",
            "seed_success": False,
            "reason": connection_config["reason"],
        }
    try:
        import psycopg
        from psycopg import rows
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg_not_installed") from exc

    table = os.environ.get("BEAST_RDS_RAG_TABLE") or "public.beast_memory_vectors"
    text_column = os.environ.get("BEAST_RDS_RAG_TEXT_COLUMN") or "content"
    metadata_column = os.environ.get("BEAST_RDS_RAG_METADATA_COLUMN") or "metadata"
    id_column = os.environ.get("BEAST_RDS_RAG_ID_COLUMN") or "memory_id"
    embedding_column = os.environ.get("BEAST_RDS_RAG_EMBEDDING_COLUMN") or "embedding"

    if "dsn" in connection_config:
        connect_args = {"conninfo": connection_config["dsn"]}
    else:
        connect_args = dict(connection_config["kwargs"])
    with psycopg.connect(**connect_args, row_factory=rows.dict_row, connect_timeout=10) as connection:
        dims = _embedding_dims(connection, table=table, embedding_column=embedding_column)
        inserted = _upsert_rows(
            connection,
            table=table,
            id_column=id_column,
            text_column=text_column,
            metadata_column=metadata_column,
            embedding_column=embedding_column,
            dims=dims,
        )
        connection.commit()

    receipt_core = {
        "beast_object_type": "c4x_pgvector_rag_seed_receipt",
        "version": "1.0",
        "seed_success": True,
        "auth_mode": connection_config["auth_mode"],
        "host_digest": connection_config.get("host_digest", ""),
        "table": table,
        "embedding_dims": dims,
        "upserted_count": inserted,
        "memory_ids": [row.memory_id for row in CORPUS],
        "claim_boundary": "upserted generic c4x:* baseline RAG corpus rows only; no held-out answers or secrets serialized",
        "corpus_digest": _digest([{"memory_id": row.memory_id, "content": row.content, "metadata": row.metadata} for row in CORPUS]),
    }
    return {**receipt_core, "receipt_digest": _digest(receipt_core)}


def _embedding_dims(connection: Any, *, table: str, embedding_column: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT vector_dims(" + _quote_ident(embedding_column) + ") AS dims FROM "
            + _quote_ident(table)
            + " WHERE "
            + _quote_ident(embedding_column)
            + " IS NOT NULL LIMIT 1"
        )
        row = cursor.fetchone()
    if row and row.get("dims"):
        return int(row["dims"])
    return _positive_embedding_dims(os.environ.get("BEAST_RDS_RAG_EMBEDDING_DIMS"), default=64)


def _upsert_rows(
    connection: Any,
    *,
    table: str,
    id_column: str,
    text_column: str,
    metadata_column: str,
    embedding_column: str,
    dims: int,
) -> int:
    sql = (
        "INSERT INTO " + _quote_ident(table)
        + " (" + ", ".join(_quote_ident(name) for name in (id_column, text_column, metadata_column, embedding_column)) + ") "
        + "VALUES (%s, %s, %s::jsonb, %s::vector) "
        + "ON CONFLICT (" + _quote_ident(id_column) + ") DO UPDATE SET "
        + _quote_ident(text_column) + " = EXCLUDED." + _quote_ident(text_column) + ", "
        + _quote_ident(metadata_column) + " = EXCLUDED." + _quote_ident(metadata_column) + ", "
        + _quote_ident(embedding_column) + " = EXCLUDED." + _quote_ident(embedding_column) + ", "
        + '"updated_at" = now()'
    )
    with connection.cursor() as cursor:
        for row in CORPUS:
            metadata = {**row.metadata, "memory_id": row.memory_id}
            cursor.execute(sql, (row.memory_id, row.content, json.dumps(metadata, sort_keys=True), _embedding_literal(row.content, dims)))
    return len(CORPUS)


def _embedding_literal(text: str, dims: int) -> str:
    values = [0.0] * dims
    for token in TOKEN_RE.findall(text.casefold()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[index] += sign
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return "[" + ",".join(f"{value / norm:.6f}" for value in values) + "]"


def _positive_embedding_dims(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 4096))


if __name__ == "__main__":
    raise SystemExit(main())
