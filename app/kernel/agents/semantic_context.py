"""Compact IDE semantic evidence for planner prompts.

The desktop IDE can produce rich LSP/index/debug/navigation snapshots. The
planner should consume the useful shape without dragging the whole repository
or UI payload into the model prompt.
"""

from __future__ import annotations

import json
from typing import Any


def _items(value: Any, limit: int) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "")[:limit]


def _compact_symbol(item: Any) -> dict[str, Any]:
    row = _mapping(item)
    return {
        key: row.get(key)
        for key in ("name", "kind", "file", "line")
        if row.get(key) not in {None, ""}
    }


def _compact_diagnostic(item: Any) -> dict[str, Any]:
    row = _mapping(item)
    return {
        "file": _text(row.get("file"), 180),
        "line": int(row.get("line") or 0),
        "severity": _text(row.get("severity"), 40),
        "code": _text(row.get("code"), 80),
        "message": _text(row.get("message"), 220),
    }


def _compact_code_action(item: Any) -> dict[str, Any]:
    row = _mapping(item)
    diagnostic = _compact_diagnostic(row.get("diagnostic"))
    result = {
        "title": _text(row.get("title"), 180),
        "kind": _text(row.get("kind"), 80),
    }
    if diagnostic.get("code"):
        result["diagnostic"] = diagnostic
    return result


def build_semantic_context(run: dict[str, Any], state: Any = None, *, char_limit: int = 1600) -> dict[str, Any]:
    """Return a bounded planner-ready semantic evidence packet.

    Accepted input locations, in priority order:
    - run.request.semantic_context
    - run.request.ide_semantic_context
    - run.checkpoint.semantic_context
    """

    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    raw = (
        request.get("semantic_context")
        if isinstance(request.get("semantic_context"), dict)
        else request.get("ide_semantic_context")
        if isinstance(request.get("ide_semantic_context"), dict)
        else checkpoint.get("semantic_context")
        if isinstance(checkpoint.get("semantic_context"), dict)
        else {}
    )
    if not raw:
        return {}

    services = _mapping(raw.get("services"))
    index = _mapping(raw.get("index") or services.get("index"))
    navigation = _mapping(raw.get("navigation") or services.get("navigation"))
    diagnostics = _mapping(raw.get("diagnostics") or services.get("diagnostics"))
    refactor = _mapping(raw.get("refactor") or services.get("refactor"))
    semantic = _mapping(raw.get("semantic") or index.get("semantic"))

    packet: dict[str, Any] = {
        "status": "available",
        "digest": _text(raw.get("digest") or index.get("digest"), 120),
        "summary": {
            "symbols": int(index.get("symbolCount") or semantic.get("definitionCount") or 0),
            "references": int(index.get("referenceCount") or semantic.get("referenceCount") or 0),
            "import_edges": int(index.get("importEdgeCount") or semantic.get("importEdgeCount") or 0),
            "diagnostics": int(diagnostics.get("count") or len(_items(index.get("diagnostics"), 1000))),
            "code_actions": int(diagnostics.get("codeActionCount") or len(_items(index.get("codeActions"), 1000))),
        },
        "navigation": {
            "workspace_symbols": bool(_mapping(navigation.get("supports")).get("workspaceSymbols") or semantic.get("workspaceSymbols")),
            "definitions": bool(_mapping(navigation.get("supports")).get("definitions") or semantic.get("workspaceSymbols")),
            "references": bool(_mapping(navigation.get("supports")).get("references") or semantic.get("topReferences")),
            "dependents": bool(_mapping(navigation.get("supports")).get("dependents") or semantic.get("dependents")),
        },
        "refactor": {
            "rename_preview": bool(refactor.get("supportsRenamePreview")),
            "code_actions": bool(refactor.get("supportsCodeActions") or diagnostics.get("codeActionCount")),
        },
        "top_symbols": [_compact_symbol(item) for item in _items(semantic.get("workspaceSymbols"), 12) if _compact_symbol(item)],
        "top_references": [
            {
                "name": _text(_mapping(item).get("name"), 120),
                "count": int(_mapping(item).get("count") or 0),
                "files": [_text(file, 180) for file in _items(_mapping(item).get("files"), 8)],
            }
            for item in _items(semantic.get("topReferences"), 8)
        ],
        "diagnostics": [_compact_diagnostic(item) for item in _items(index.get("diagnostics") or diagnostics.get("recent"), 8)],
        "code_actions": [_compact_code_action(item) for item in _items(index.get("codeActions"), 8)],
    }
    packet["diagnostics"] = [item for item in packet["diagnostics"] if item.get("code") or item.get("message")]
    packet["code_actions"] = [item for item in packet["code_actions"] if item.get("title")]

    encoded = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded) > char_limit:
        packet["truncated"] = True
        packet["top_symbols"] = packet["top_symbols"][:6]
        packet["top_references"] = packet["top_references"][:4]
        packet["diagnostics"] = packet["diagnostics"][:4]
        packet["code_actions"] = packet["code_actions"][:4]
    return packet


def semantic_context_contract(run: dict[str, Any], state: Any = None, *, char_limit: int = 1600) -> str:
    packet = build_semantic_context(run, state, char_limit=char_limit)
    if not packet:
        return ""
    encoded = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded) > char_limit:
        encoded = encoded[: max(0, char_limit - 15)] + "[truncated]"
    return f"\nSEMANTIC_CONTEXT:{encoded}"
