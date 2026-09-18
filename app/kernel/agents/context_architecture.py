"""Recovery Phase 5 canonical planner context architecture.

This module keeps model-visible context separate from mutation authority.
Repository discovery, semantic summaries and compressed evidence may help the
planner choose what to inspect, but only exact workspace.read_range observations
may supply editable source bytes.

The contract is deterministic and deliberately small for local models.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


MUTATION_TOOLS = {"worktree.write_file", "worktree.replace_exact"}
EXACT_SOURCE_TOOL = "workspace.read_range"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _exact_source_rows(state: Any, *, max_files: int = 8, max_chars_per_file: int = 2200) -> list[dict[str, Any]]:
    observations = getattr(state, "observations", []) if state is not None else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in reversed(observations if isinstance(observations, list) else []):
        if not isinstance(item, dict):
            continue
        if str(item.get("tool_id") or "") != EXACT_SOURCE_TOOL:
            continue
        if str(item.get("status") or "") != "completed":
            continue
        result = _mapping(item.get("result"))
        path = str(result.get("path") or "").strip()
        content = str(result.get("content") or "")
        if not path or not content or path in seen:
            continue
        seen.add(path)
        content_hash = str(result.get("content_hash") or result.get("sha256") or "").strip()
        if not content_hash:
            content_hash = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        rows.append({
            "path": path,
            "start_line": int(result.get("start_line") or 1),
            "content_hash": content_hash,
            "content": content[:max_chars_per_file],
            "truncated": len(content) > max_chars_per_file,
            "authority": "exact_source_evidence",
        })
        if len(rows) >= max_files:
            break
    rows.reverse()
    return rows


def _discovery_view(run: dict[str, Any]) -> dict[str, Any]:
    checkpoint = _mapping(run.get("checkpoint"))
    discovery = _mapping(checkpoint.get("repository_discovery"))
    if not discovery:
        return {}
    return {
        "canonical_owner": str(discovery.get("canonical_owner") or "code_cortex"),
        "authority": "advisory_discovery_only",
        "hint_paths": _dedupe([str(x) for x in (discovery.get("hint_paths") or [])])[:8],
        "discovered_paths": _dedupe([str(x) for x in (discovery.get("discovered_paths") or [])])[:16],
        "required_evidence_paths": _dedupe([str(x) for x in (discovery.get("required_evidence_paths") or [])])[:16],
        "path_reasons": {
            str(path): list(reasons)[:6] if isinstance(reasons, list) else []
            for path, reasons in list(_mapping(discovery.get("path_reasons")).items())[:20]
        },
        "discovery_digest": str(discovery.get("discovery_digest") or ""),
        "mutation_authority": False,
    }


def _operational_view(state: Any) -> dict[str, Any]:
    observations = getattr(state, "observations", []) if state is not None else []
    if not isinstance(observations, list):
        observations = []
    latest: dict[str, dict[str, Any]] = {}
    for item in observations:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or "")
        if tool_id in {"worktree.bind", *MUTATION_TOOLS, "worktree.verify", "worktree.sourceplan_draft"}:
            result = _mapping(item.get("result"))
            latest[tool_id] = {
                "status": str(item.get("status") or ""),
                "path": str(result.get("path") or ""),
                "returncode": result.get("returncode"),
                "evidence_digest": str(item.get("evidence_digest") or ""),
            }
    return latest


def build_canonical_context_packet(
    run: dict[str, Any],
    state: Any,
    *,
    max_exact_files: int = 8,
    max_exact_chars_per_file: int = 2200,
) -> dict[str, Any]:
    """Build the Phase 5 model handoff packet.

    The packet has explicit authority classes:
    discovery is advisory, exact_source is editable evidence, and operational
    state is control-plane evidence. Compression never upgrades authority.
    """
    exact_source = _exact_source_rows(
        state,
        max_files=max_exact_files,
        max_chars_per_file=max_exact_chars_per_file,
    )
    discovery = _discovery_view(run)
    body = {
        "beast_object_type": "beast_agent_context_packet",
        "version": "2.0",
        "run_id": str(run.get("run_id") or getattr(state, "run_id", "") or ""),
        "objective": str(run.get("objective") or ""),
        "authority_model": {
            "discovery": "advisory_only",
            "compressed_context": "advisory_only",
            "exact_source": "workspace.read_range_only",
            "mutation": "worktree_tools_only",
            "rule": "No summary, semantic match, compressed chunk, memory item or model output becomes mutation authority.",
        },
        "repository_discovery": discovery,
        "exact_source": exact_source,
        "operational_state": _operational_view(state),
        "budget": {
            "max_exact_files": max_exact_files,
            "max_exact_chars_per_file": max_exact_chars_per_file,
            "exact_file_count": len(exact_source),
        },
    }
    body["packet_digest"] = _stable_digest(body)
    return body


def _shrink_packet(packet: dict[str, Any], char_limit: int) -> dict[str, Any]:
    """Deterministically shed advisory detail before exact source evidence."""
    candidate = json.loads(json.dumps(packet, default=str))
    discovery = _mapping(candidate.get("repository_discovery"))

    for key in ("path_reasons", "discovered_paths", "hint_paths"):
        if len(json.dumps(candidate, sort_keys=True, separators=(",", ":"))) <= char_limit:
            break
        if key == "path_reasons":
            discovery[key] = {}
        else:
            discovery[key] = list(discovery.get(key) or [])[:4]

    exact = candidate.get("exact_source") if isinstance(candidate.get("exact_source"), list) else []
    while len(json.dumps(candidate, sort_keys=True, separators=(",", ":"))) > char_limit and exact:
        longest = max(range(len(exact)), key=lambda i: len(str(exact[i].get("content") or "")))
        content = str(exact[longest].get("content") or "")
        if len(content) <= 320:
            break
        exact[longest]["content"] = content[: max(320, len(content) // 2)]
        exact[longest]["truncated"] = True

    candidate["compaction"] = {
        "applied": True,
        "authority_preserved": True,
        "policy": "drop_advisory_detail_before_exact_source_content",
    }
    candidate["packet_digest"] = _stable_digest({k: v for k, v in candidate.items() if k != "packet_digest"})
    return candidate


def render_context_contract(packet: dict[str, Any], *, char_limit: int = 4800) -> str:
    """Render one bounded planner contract while preserving authority labels."""
    limit = max(1600, int(char_limit))
    candidate = _shrink_packet(packet, limit)
    encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str)
    if len(encoded) > limit:
        # Last-resort bound. Keep the authority model and exact-source hashes even
        # when source content itself must be omitted.
        exact_refs = [
            {
                "path": row.get("path"),
                "content_hash": row.get("content_hash"),
                "authority": row.get("authority"),
                "content_omitted_for_budget": True,
            }
            for row in candidate.get("exact_source", [])
            if isinstance(row, dict)
        ]
        candidate = {
            "beast_object_type": candidate.get("beast_object_type"),
            "version": candidate.get("version"),
            "run_id": candidate.get("run_id"),
            "objective": candidate.get("objective"),
            "authority_model": candidate.get("authority_model"),
            "repository_discovery": {
                "authority": "advisory_discovery_only",
                "required_evidence_paths": _mapping(candidate.get("repository_discovery")).get("required_evidence_paths", [])[:8],
            },
            "exact_source": exact_refs,
            "operational_state": candidate.get("operational_state"),
            "compaction": {
                "applied": True,
                "authority_preserved": True,
                "content_omitted": True,
            },
        }
        candidate["packet_digest"] = _stable_digest(candidate)
        encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str)
    return "\nCANONICAL_CONTEXT:" + encoded[:limit]


def canonical_context_contract(
    run: dict[str, Any],
    state: Any,
    *,
    char_limit: int = 4800,
) -> str:
    return render_context_contract(
        build_canonical_context_packet(run, state),
        char_limit=char_limit,
    )
