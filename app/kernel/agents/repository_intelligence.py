"""Recovery Phase 4 repository perception for BEAST AgentRuns.

Code Cortex is the canonical selector for code work/context. This module turns
its read-only Context Packet evidence into one durable discovery contract for
the coding agent. Discovery is advisory: exact source bytes must still be read
through workspace.read_range before mutation authority may be exercised.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_MAX_DISCOVERY_PATHS = 32


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip().replace("\\", "/")
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _safe_rel(root: Path, value: Any) -> str:
    text = str(value or "").strip().strip(chr(96)).replace("\\", "/")
    if not text:
        return ""
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        return ""
    normalized = Path(*[part for part in path.parts if part not in ("", ".")]).as_posix()
    if not normalized:
        return ""
    target = (root / normalized).resolve()
    if target != root and root not in target.parents:
        return ""
    if not target.exists() or not target.is_file():
        return ""
    return normalized


def repository_hint_paths(run: dict[str, Any], root: Path) -> list[str]:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    semantic = request.get("semantic_context") if isinstance(request.get("semantic_context"), dict) else {}
    values: list[Any] = []
    for key in ("active_file", "selected_file", "target_file"):
        values.append(semantic.get(key))
    if isinstance(request.get("context_files"), list):
        values.extend(request["context_files"])
    if isinstance(run.get("files"), list):
        values.extend(run["files"])
    return _dedupe(_safe_rel(root, value) for value in values if value)


def _add_reason(reasons: dict[str, list[str]], root: Path, value: Any, reason: str) -> None:
    path = _safe_rel(root, value)
    if not path:
        return
    rows = reasons.setdefault(path, [])
    if reason not in rows:
        rows.append(reason)


def _packet_paths(packet: dict[str, Any], root: Path, reasons: dict[str, list[str]]) -> None:
    workspace = packet.get("workspace_context") if isinstance(packet.get("workspace_context"), dict) else {}
    cortex = workspace.get("code_cortex") if isinstance(workspace.get("code_cortex"), dict) else {}
    for value in cortex.get("files") or []:
        _add_reason(reasons, root, value, "code_cortex_editing_context")
    for symbol in cortex.get("symbols") or []:
        if isinstance(symbol, dict):
            _add_reason(
                reasons,
                root,
                symbol.get("file") or symbol.get("path") or symbol.get("source"),
                "code_cortex_symbol",
            )
    for node in workspace.get("matched_nodes") or []:
        if isinstance(node, dict) and str(node.get("type") or "") == "file":
            _add_reason(reasons, root, node.get("label") or node.get("file"), "workspace_graph_match")
    for match in workspace.get("semantic_matches") or []:
        if isinstance(match, dict):
            _add_reason(reasons, root, match.get("file") or match.get("label"), "semantic_match")
    for item in packet.get("included_evidence") or []:
        if isinstance(item, dict) and str(item.get("kind") or "") in {"file_snippet", "semantic_match"}:
            _add_reason(reasons, root, item.get("source"), f"context_packet_{item.get('kind')}")


def build_repository_discovery(
    *,
    context_packet_builder: Any,
    run: dict[str, Any],
    workspace_root: str | Path,
    semantic_limit: int = 12,
    max_files: int = 24,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    hints = repository_hint_paths(run, root)
    objective = str(run.get("objective") or "").strip()
    hint_clause = ", ".join(hints)
    query = objective if not hint_clause else f"{objective}\nInitial repository hints: {hint_clause}"
    envelope = {
        "beast_object_type": "task_envelope",
        "version": "1.0",
        "task_id": str(run.get("run_id") or ""),
        "intent": objective,
        "task_class": "coding_agent_repository_discovery",
        "privacy_class": "internal",
        "inputs": {
            "user_request": query,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
        },
        "context_budget": {
            "max_tokens": 6000,
            "max_files": max(1, min(int(max_files), _MAX_DISCOVERY_PATHS)),
            "allow_full_files": False,
        },
    }
    packet = context_packet_builder.build(
        envelope,
        workspace_root=str(root),
        semantic_limit=max(1, min(int(semantic_limit), 24)),
        include_content=False,
        max_files=max(1, min(int(max_files), _MAX_DISCOVERY_PATHS)),
    )

    reasons: dict[str, list[str]] = {}
    for hint in hints:
        _add_reason(reasons, root, hint, "operator_hint")
    _packet_paths(packet, root, reasons)

    cortex = getattr(context_packet_builder, "code_cortex", None)
    dependent_receipts: list[dict[str, Any]] = []
    if cortex is not None and hasattr(cortex, "get_dependents"):
        for hint in hints[:8]:
            try:
                result = cortex.get_dependents(root, hint, limit=12)
            except Exception as exc:
                dependent_receipts.append({
                    "hint": hint,
                    "ok": False,
                    "reason": type(exc).__name__,
                })
                continue
            receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
            dependent_receipts.append({
                "hint": hint,
                "ok": bool(result.get("ok")),
                "adapter": str(result.get("adapter") or ""),
                "fallback_from": result.get("fallback_from") or [],
                "receipt": {key: value for key, value in receipt.items() if key != "latency_ms"},
            })
            for item in result.get("results") or []:
                if isinstance(item, dict):
                    _add_reason(reasons, root, item.get("path"), f"dependent_of:{hint}")

    hint_set = set(hints)
    ordered = _dedupe([*hints, *sorted(path for path in reasons if path not in hint_set)])
    ordered = ordered[:_MAX_DISCOVERY_PATHS]
    discovered = [path for path in ordered if path not in hint_set]
    workspace = packet.get("workspace_context") if isinstance(packet.get("workspace_context"), dict) else {}
    code_context = workspace.get("code_cortex") if isinstance(workspace.get("code_cortex"), dict) else {}

    body = {
        "beast_object_type": "beast_agent_repository_discovery",
        "version": "1.0",
        "run_id": str(run.get("run_id") or ""),
        "canonical_owner": "code_cortex",
        "authority": "advisory_discovery_only",
        "mutation_authority": False,
        "exact_source_read_required_before_mutation": True,
        "objective": objective,
        "hint_paths": hints,
        "candidate_paths": ordered,
        "discovered_paths": discovered,
        "path_reasons": {path: reasons.get(path, []) for path in ordered},
        "context_packet_id": str(packet.get("packet_id") or ""),
        "context_packet_hash": str(packet.get("handoff_hash") or ""),
        "code_cortex": {
            "available": bool(code_context.get("available")),
            "adapter": str(code_context.get("adapter") or ""),
            "fallback_from": code_context.get("fallback_from") or [],
            "receipt": code_context.get("receipt") if isinstance(code_context.get("receipt"), dict) else {},
            "result_count": int(code_context.get("result_count") or 0),
        },
        "dependent_receipts": dependent_receipts,
        "workspace_graph": {
            "matched_node_count": int(workspace.get("matched_node_count") or 0),
            "semantic_match_count": int(workspace.get("semantic_match_count") or 0),
            "semantic_available": bool(workspace.get("semantic_available")),
        },
        "packet_stats": packet.get("packet_stats") if isinstance(packet.get("packet_stats"), dict) else {},
        "sensorium_world_state": {
            "authority": "observation_only",
            "admission": "pending",
        },
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    body["discovery_digest"] = f"sha256:{digest}"
    return body


def discovery_observation(
    *,
    run_id: str,
    discovery: dict[str, Any],
    sensorium: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(discovery)
    result["sensorium_world_state"] = dict(sensorium or {
        "admitted": False,
        "authority": "observation_only",
        "reason": "sensorium_admission_unavailable",
    })
    digest = str(discovery.get("discovery_digest") or "").removeprefix("sha256:")
    return {
        "observation_id": f"repo-discovery-{digest[:20] or 'unavailable'}",
        "run_id": run_id,
        "tool_id": "code_cortex.discover",
        "tool_version": "1",
        "status": "completed",
        "arguments": {
            "hint_paths": list(discovery.get("hint_paths") or []),
        },
        "result": result,
        "error": "",
        "truncated": False,
        "evidence_digest": digest,
    }
