#!/usr/bin/env python3
"""Amazon RDS/Postgres RAG adapter for the C4-X benchmark.

This is a command adapter for:

    python3 scripts/run_c4x_external_breakthrough_benchmark.py \
      --external-rag-command "python3 scripts/run_c4x_rds_rag_adapter.py"

It reads one public C4-X scenario request JSON object on stdin and writes one
benchmark output JSON object on stdout. The independent oracle is never sent to
this adapter.

Environment:

- BEAST_RDS_RAG_DSN, AMAZON_RDS_DSN, RDS_DSN, or POSTGRES_DSN
- Or IAM auth mode:
  BEAST_RDS_RAG_IAM_AUTH=1
  BEAST_RDS_RAG_HOST / RDSHOST
  BEAST_RDS_RAG_REGION / AWS_REGION
  BEAST_RDS_RAG_USER default postgres
  BEAST_RDS_RAG_DBNAME default postgres
  BEAST_RDS_RAG_PORT default 5432
  Existing BEAST_PGVECTOR_* names from .beast/vector.env are also accepted.
- BEAST_RDS_RAG_SQL optional custom query. Named placeholders supported:
  %(query)s, %(query_like)s, %(source)s, %(target)s, %(family)s, %(limit)s.
- Or simple table mode:
  BEAST_RDS_RAG_TABLE default beast_rag_chunks
  BEAST_RDS_RAG_TEXT_COLUMN default content
  BEAST_RDS_RAG_METADATA_COLUMN optional metadata
  BEAST_RDS_RAG_SCORE_COLUMN optional score
  BEAST_RDS_RAG_LIMIT default 5

If query rows include answer_text, reported_status, reported_class, or
reported_current_claim_allowed, those fields are passed through for scoring.
Otherwise the adapter returns retrieved chunks only.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Iterable, Mapping


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    try:
        output = run_rds_rag(request)
    except Exception as exc:
        output = {
            "answer_text": f"Amazon RDS RAG adapter failed: {type(exc).__name__}: {exc}",
            "retrieved_chunks": [],
            "provider_calls_used": 0,
            "current_claim_valid": False,
            "visual_present": False,
            "rds_rag_error": type(exc).__name__,
        }
    print(json.dumps(output, sort_keys=True))
    return 0


def run_rds_rag(request: Mapping[str, Any]) -> dict[str, Any]:
    connection_config = _connection_config()
    if not connection_config["configured"]:
        return _not_configured(str(connection_config["reason"]))
    try:
        import psycopg
        from psycopg import rows
    except ModuleNotFoundError:
        return _not_configured("psycopg_not_installed")

    limit = _positive_int(os.environ.get("BEAST_RDS_RAG_LIMIT"), default=5)
    params = {
        "query": str(request.get("question") or ""),
        "query_like": "%" + _like_terms(request) + "%",
        "source": str(request.get("source") or ""),
        "source_like": "%" + str(request.get("source") or "") + "%",
        "target": str(request.get("target") or ""),
        "target_like": "%" + str(request.get("target") or "") + "%",
        "family": str(request.get("family") or ""),
        "family_like": "%" + str(request.get("family") or "") + "%",
        "operation_like": "%" + _operation_term(str(request.get("family") or ""), str(request.get("question") or "")) + "%",
        "limit": limit,
    }
    custom_sql = os.environ.get("BEAST_RDS_RAG_SQL")
    query: Any
    if custom_sql:
        query = custom_sql
    else:
        table = os.environ.get("BEAST_RDS_RAG_TABLE") or "beast_rag_chunks"
        text_column = os.environ.get("BEAST_RDS_RAG_TEXT_COLUMN") or "content"
        metadata_column = os.environ.get("BEAST_RDS_RAG_METADATA_COLUMN") or ""
        score_column = os.environ.get("BEAST_RDS_RAG_SCORE_COLUMN") or ""
        select_items = [_quote_ident(text_column) + " AS content"]
        if metadata_column:
            select_items.append(_quote_ident(metadata_column) + " AS metadata")
        if score_column:
            select_items.append(_quote_ident(score_column) + " AS score")
        query = (
            "SELECT " + ", ".join(select_items)
            + " FROM " + _quote_ident(table)
            + " WHERE ("
            + _quote_ident(text_column) + " ILIKE %(query_like)s OR "
            + _quote_ident(text_column) + " ILIKE %(source_like)s OR "
            + _quote_ident(text_column) + " ILIKE %(target_like)s OR "
            + _quote_ident(text_column) + " ILIKE %(family_like)s OR "
            + _quote_ident(text_column) + " ILIKE %(operation_like)s"
            + ") ORDER BY "
            + (_quote_ident(score_column) + " DESC NULLS LAST, " if score_column else "")
            + _source_target_rank_expression(text_column) + " DESC LIMIT %(limit)s"
        )

    if "dsn" in connection_config:
        connect_args = {"conninfo": connection_config["dsn"]}
    else:
        connect_args = dict(connection_config["kwargs"])
    with psycopg.connect(**connect_args, row_factory=rows.dict_row, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows_out = list(cursor.fetchall())
    chunks = [_chunk(row, index) for index, row in enumerate(rows_out[:limit], start=1)]
    first = rows_out[0] if rows_out else {}
    answer_text = str(first.get("answer_text") or "") if isinstance(first, Mapping) else ""
    if not answer_text:
        answer_text = _synthesize_from_public_facts(request, chunks) or "\n".join(
            chunk["text"] for chunk in chunks if chunk.get("text")
        )[:4000]
    output = {
        "answer_text": answer_text,
        "retrieved_chunks": chunks,
        "provider_calls_used": 0,
        "current_claim_valid": (
            bool(first.get("current_claim_valid"))
            if isinstance(first, Mapping) and "current_claim_valid" in first
            else _current_claim_valid_from_public_facts(request, chunks)
        ),
        "visual_present": bool(first.get("visual_present")) if isinstance(first, Mapping) and "visual_present" in first else False,
        "artifact_custody_valid": False,
        "proof_first": False,
        "rds_rag_configured": True,
        "rds_rag_auth_mode": connection_config["auth_mode"],
        "rds_rag_host_digest": connection_config.get("host_digest", ""),
        "rds_rag_row_count": len(rows_out),
        "rds_rag_request_digest": _digest({
            "case_id": request.get("case_id"),
            "question": request.get("question"),
            "source": request.get("source"),
            "target": request.get("target"),
            "family": request.get("family"),
        }),
    }
    for key in ("reported_status", "reported_class", "reported_current_claim_allowed"):
        if isinstance(first, Mapping) and key in first:
            output[key] = first[key]
    return output


def _connection_config() -> dict[str, Any]:
    dsn = _first_env(("BEAST_RDS_RAG_DSN", "BEAST_PGVECTOR_DSN", "AMAZON_RDS_DSN", "RDS_DSN", "POSTGRES_DSN"))
    if dsn:
        return {"configured": True, "auth_mode": "dsn_password_or_dsn_token", "dsn": dsn}
    iam_auth = os.environ.get("BEAST_RDS_RAG_IAM_AUTH") or os.environ.get("BEAST_PGVECTOR_IAM_AUTH")
    if iam_auth not in {"1", "true", "TRUE", "yes", "YES"}:
        return {"configured": False, "reason": "missing_rds_dsn"}
    host = _first_env(("BEAST_RDS_RAG_HOST", "BEAST_PGVECTOR_HOST", "RDSHOST", "RDS_HOST"))
    region = _first_env(("BEAST_RDS_RAG_REGION", "BEAST_PGVECTOR_AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"))
    user = os.environ.get("BEAST_RDS_RAG_USER") or os.environ.get("BEAST_PGVECTOR_USER") or os.environ.get("RDSUSER") or "postgres"
    dbname = os.environ.get("BEAST_RDS_RAG_DBNAME") or os.environ.get("BEAST_PGVECTOR_DATABASE") or os.environ.get("RDSDB") or "postgres"
    port = _port_int(os.environ.get("BEAST_RDS_RAG_PORT") or os.environ.get("BEAST_PGVECTOR_PORT") or os.environ.get("RDSPORT"), default=5432)
    if not host:
        return {"configured": False, "reason": "missing_rds_iam_host"}
    if not region:
        return {"configured": False, "reason": "missing_rds_iam_region"}
    token = _generate_iam_token(host=host, port=port, user=user, region=region)
    if not token:
        return {"configured": False, "reason": "rds_iam_token_generation_failed"}
    return {
        "configured": True,
        "auth_mode": "rds_iam_auth_token",
        "host_digest": _digest({"host": host, "region": region, "port": port}),
        "kwargs": {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": token,
            "sslmode": os.environ.get("BEAST_RDS_RAG_SSLMODE") or os.environ.get("BEAST_PGVECTOR_SSLMODE") or "require",
        },
    }


def _generate_iam_token(*, host: str, port: int, user: str, region: str) -> str:
    command = [
        os.environ.get("AWS_CLI") or "aws",
        "rds",
        "generate-db-auth-token",
        "--hostname",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--region",
        region,
    ]
    try:
        env = dict(os.environ)
        env.setdefault("PYTHONNOUSERSITE", "1")
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=15, env=env)
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _not_configured(reason: str) -> dict[str, Any]:
    return {
        "answer_text": f"Amazon RDS RAG adapter not configured: {reason}.",
        "retrieved_chunks": [],
        "provider_calls_used": 0,
        "current_claim_valid": False,
        "visual_present": False,
        "artifact_custody_valid": False,
        "proof_first": False,
        "rds_rag_configured": False,
        "rds_rag_refusal_reason": reason,
    }


def _chunk(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    text = str(row.get("text") or row.get("content") or row.get("body") or "")
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return {
        "rank": index,
        "text": text[:2000],
        "score": _float_or_none(row.get("score")),
        "metadata": dict(metadata or {}),
        "row_digest": _digest({key: str(value)[:500] for key, value in sorted(row.items())}),
    }


def _synthesize_from_public_facts(request: Mapping[str, Any], chunks: Iterable[Mapping[str, Any]]) -> str:
    """Produce a bounded RAG answer from retrieved guidance plus public case facts.

    This is intentionally not a BEAST proof path: it has no artifact custody and
    no joined verification. It lets the external RAG lane be a stronger,
    non-blind competitor by using public facts/rules/policies that the benchmark
    sends to every external command.
    """
    chunks = tuple(chunks)
    if not chunks:
        return ""
    scenario = request.get("scenario") if isinstance(request.get("scenario"), Mapping) else {}
    facts = tuple(item for item in scenario.get("facts") or () if isinstance(item, Mapping))
    rules = tuple(item for item in scenario.get("rules") or () if isinstance(item, Mapping))
    policies = tuple(item for item in scenario.get("policies") or () if isinstance(item, Mapping))
    if not facts:
        return ""
    family = str(request.get("family") or scenario.get("family") or "")
    source = str(request.get("source") or scenario.get("source") or "")
    target = str(request.get("target") or scenario.get("target") or "")
    metadata = scenario.get("metadata") if isinstance(scenario.get("metadata"), Mapping) else {}
    if metadata.get("temporal_state") == "stale":
        return f"RDS RAG cannot establish current state for {source} to {target}: stale evidence requires residual verification."
    status, klass, current = _status_class_from_public_scenario(
        family=family,
        source=source,
        target=target,
        facts=facts,
        rules=rules,
        policies=policies,
        metadata=metadata,
    )
    if not status:
        return ""
    if not current:
        if status == "residual_required":
            return f"RDS RAG marks {source} to {target} as residual_required: missing rule leaves class {klass}."
        return f"RDS RAG cannot establish {source} to {target}; class {klass}."
    return f"RDS RAG says {source} to {target} is {status}; class {klass}; derived from retrieved operational guidance and public facts."


def _current_claim_valid_from_public_facts(request: Mapping[str, Any], chunks: Iterable[Mapping[str, Any]]) -> bool:
    chunks = tuple(chunks)
    if not chunks:
        return False
    scenario = request.get("scenario") if isinstance(request.get("scenario"), Mapping) else {}
    facts = tuple(item for item in scenario.get("facts") or () if isinstance(item, Mapping))
    if not facts:
        return True
    metadata = scenario.get("metadata") if isinstance(scenario.get("metadata"), Mapping) else {}
    if metadata.get("temporal_state") == "stale":
        return False
    status, _klass, current = _status_class_from_public_scenario(
        family=str(request.get("family") or scenario.get("family") or ""),
        source=str(request.get("source") or scenario.get("source") or ""),
        target=str(request.get("target") or scenario.get("target") or ""),
        facts=facts,
        rules=tuple(item for item in scenario.get("rules") or () if isinstance(item, Mapping)),
        policies=tuple(item for item in scenario.get("policies") or () if isinstance(item, Mapping)),
        metadata=metadata,
    )
    return bool(status and current)


def _status_class_from_public_scenario(
    *,
    family: str,
    source: str,
    target: str,
    facts: tuple[Mapping[str, Any], ...],
    rules: tuple[Mapping[str, Any], ...],
    policies: tuple[Mapping[str, Any], ...],
    metadata: Mapping[str, Any],
) -> tuple[str, str, bool]:
    if family == "restart_risk":
        source_health = _public_fact(facts, "service_health", source)
        target_health = _public_fact(facts, "service_health", target)
        dependency = _public_fact(facts, "dependency_topology", target, object_=source)
        policy_fact = _public_fact(facts, "restart_policy", source)
        evidence = _public_fact(facts, "current_evidence", "runtime")
        rule = _public_rule(rules, "restart_destabilization")
        if any(item is None for item in (source_health, target_health, dependency, policy_fact, evidence)):
            return "unsupported", "unsupported", False
        if rule is None:
            return "residual_required", "unsupported_without_causal_rule", False
        source_state = str(_public_value(source_health).get("state", "unknown"))
        target_state = str(_public_value(target_health).get("state", "unknown"))
        mode = str(_public_value(policy_fact).get("mode", ""))
        dependency_kind = str(_public_value(dependency).get("relation", ""))
        if dependency_kind not in {"depends_on", "routes_through"}:
            return "unsupported", "unknown_dependency_semantics", False
        low = source_state == "healthy" and target_state == "healthy" and mode in {"rolling_with_healthcheck", "blue_green"}
        return "supported", "low" if low else "elevated", True
    if family == "traffic_shift":
        target_capacity = _public_fact(facts, "capacity_state", target)
        route = _public_fact(facts, "traffic_route", source, object_=target)
        evidence = _public_fact(facts, "current_evidence", "runtime")
        rule = _public_rule(rules, "traffic_shift_capacity")
        policy = policies[0] if policies else None
        if any(item is None for item in (target_capacity, route, evidence, policy)):
            return "unsupported", "unsupported", False
        if rule is None:
            return "residual_required", "unsupported_without_capacity_rule", False
        target_spare = float(_public_value(target_capacity).get("spare_percent", 0))
        shift = float(metadata.get("shift_percent", 0))
        reserve = float((policy or {}).get("parameters", {}).get("minimum_reserve_percent", 0))
        route_state = str(_public_value(route).get("state", "unknown"))
        safe = route_state == "healthy" and target_spare >= shift + reserve
        return "supported", "safe" if safe else "unsafe", True
    if family == "deployment_safety":
        stage = _public_fact(facts, "deployment_stage", source)
        health_gate = _public_fact(facts, "health_gate", source)
        rollback = _public_fact(facts, "rollback_state", source)
        target_health = _public_fact(facts, "service_health", target)
        evidence = _public_fact(facts, "current_evidence", "runtime")
        rule = _public_rule(rules, "deployment_rollout_safety")
        policy = policies[0] if policies else None
        if any(item is None for item in (stage, health_gate, rollback, target_health, evidence, policy)):
            return "unsupported", "unsupported", False
        if rule is None:
            return "residual_required", "unsupported_without_rollout_rule", False
        gate_passed = bool(_public_value(health_gate).get("passed"))
        rollback_ready = bool(_public_value(rollback).get("ready"))
        target_state = str(_public_value(target_health).get("state", "unknown"))
        max_error = float((policy or {}).get("parameters", {}).get("max_error_rate_percent", 100))
        observed_error = float(_public_value(health_gate).get("error_rate_percent", 100))
        safe = gate_passed and rollback_ready and target_state == "healthy" and observed_error <= max_error
        return "supported", "safe_to_continue" if safe else "halt_or_rollback", True
    return "", "", False


def _public_fact(
    facts: tuple[Mapping[str, Any], ...],
    fact_type: str,
    subject: str,
    *,
    object_: str | None = None,
) -> Mapping[str, Any] | None:
    for fact in facts:
        if fact.get("fact_type") != fact_type or fact.get("subject") != subject:
            continue
        if object_ is not None and fact.get("object") != object_:
            continue
        return fact
    return None


def _public_rule(rules: tuple[Mapping[str, Any], ...], predicate: str) -> Mapping[str, Any] | None:
    for rule in rules:
        if rule.get("predicate") == predicate:
            return rule
    return None


def _public_value(fact: Mapping[str, Any] | None) -> Mapping[str, Any]:
    value = fact.get("value") if isinstance(fact, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _like_terms(request: Mapping[str, Any]) -> str:
    terms = " ".join(str(request.get(key) or "") for key in ("question", "source", "target", "family"))
    return terms.replace("%", " ").replace("_", " ").strip()


def _operation_term(family: str, question: str) -> str:
    family = family.casefold()
    if "restart" in family or "restart" in question.casefold():
        return "restart"
    if "traffic" in family or "traffic" in question.casefold():
        return "traffic"
    if "deployment" in family or "deployment" in question.casefold():
        return "deployment"
    return family.replace("_", " ")


def _source_target_rank_expression(text_column: str) -> str:
    escaped = _quote_ident(text_column)
    return (
        "((CASE WHEN " + escaped + " ILIKE %(source_like)s THEN 1 ELSE 0 END) + "
        "(CASE WHEN " + escaped + " ILIKE %(target_like)s THEN 1 ELSE 0 END) + "
        "(CASE WHEN " + escaped + " ILIKE %(family_like)s THEN 1 ELSE 0 END))"
    )


def _quote_ident(value: str) -> str:
    parts = [part for part in str(value or "").split(".") if part]
    if not parts:
        raise ValueError("SQL identifier cannot be empty")
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 50))


def _port_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 65535))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
