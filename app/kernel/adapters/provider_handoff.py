"""Unified provider handoff: input governance mirrored with output governance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.kernel.data_processing.context_packet import ContextPacketBuilder
from app.kernel.local.ollama_scout import OllamaScout
from app.kernel.governance.output_governor import (
    ProviderOutputProfile,
    output_contract_instructions,
    output_contract_schema,
    output_reference_packet,
    provider_output_profile,
)


PROVIDER_HANDOFF_KIND = "beast.provider_handoff.v1"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _selected_file_summary(root: Path, allowed_paths: Iterable[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rel in allowed_paths:
        path = root / str(rel)
        if not path.exists() or not path.is_file():
            rows.append({"path": str(rel), "exists": False})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            rows.append({"path": str(rel), "exists": True, "readable": False, "error": str(exc)})
            continue
        rows.append({
            "path": str(rel),
            "exists": True,
            "readable": True,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "line_count": text.count("\n") + 1,
            "size": path.stat().st_size,
        })
    return rows


def _task_envelope(
    objective: str,
    provider: str,
    allowed_paths: List[str],
    task_name: str = "",
    max_tokens: int = 8000,
) -> Dict[str, Any]:
    path_text = ", ".join(allowed_paths)
    return {
        "beast_object_type": "task_envelope",
        "version": "1.0",
        "task_id": f"tsk_{hashlib.sha256((objective + provider + path_text).encode('utf-8')).hexdigest()[:16]}",
        "intent": objective,
        "task_class": "live_coding",
        "project": "edgek-beast",
        "risk_level": "high",
        "privacy_class": "internal",
        "inputs": {
            "user_request": objective,
            "provider": provider,
            "task_name": task_name,
            "mentioned_files": allowed_paths,
        },
        "context_budget": {"max_tokens": max_tokens, "max_files": max(1, len(allowed_paths)), "allow_full_files": False},
        "allowed_actions": ["read_context", "draft_action_ir", "ask_for_context", "run_verifier"],
        "approval_required_for": ["source_write", "external_write", "git_push"],
        "success_criteria": ["Return compact governed output scoped to allowed files."],
        "dry_run": True,
    }


def _safe_scout_packet(root: Path, objective: str, provider: str, envelope: Dict[str, Any]) -> Dict[str, Any]:
    try:
        scout = OllamaScout(None, policies={"ollama_scout": {"base_url": "http://127.0.0.1:9"}})
        result = scout.scout(
            {
                "task": objective,
                "provider": provider,
                "task_class": "live_coding",
                "task_envelope": envelope,
                "use_ollama": False,
                "context_limit": 4,
                "tool_limit": 6,
                "include_postgres_schema": False,
                "include_github_context": False,
                "include_forensic_context": True,
            },
            workspace_root=str(root),
        )
        packet = result.get("packet") if isinstance(result, dict) else {}
        return packet if isinstance(packet, dict) else {}
    except Exception as exc:
        return {
            "mode": "edgek_fallback",
            "local_analysis": {
                "source": "edgek_fallback",
                "task_type": "live_coding",
                "risk": "medium",
                "needs_cloud": True,
                "summary": f"Scout packet unavailable: {exc}",
            },
        }


def _local_transform_menu(profile: ProviderOutputProfile) -> List[Dict[str, Any]]:
    common = [
        {
            "type": "replace_anchor",
            "description": "Replace a small local anchor using target.file_ref and target.anchor_ref.",
            "requires": ["target.file_ref", "target.anchor_ref", "new"],
        },
        {
            "type": "ask_for_context",
            "description": "Ask BEAST for a more specific file, symbol, or verifier result.",
            "requires": ["intent"],
        },
        {
            "type": "run_verifier",
            "description": "Ask BEAST to run a local verification command before any write.",
            "requires": ["intent"],
        },
    ]
    semantic = [
        {
            "type": "add_provider_record",
            "description": "Tell BEAST to add a provider registry record locally instead of writing source.",
            "requires": ["provider_id", "backend", "default_model", "env"],
        },
        {
            "type": "set_default_model",
            "description": "Tell BEAST to set a provider default model locally.",
            "requires": ["provider_id", "default_model"],
        },
        {
            "type": "use_provider_registry_model_resolver",
            "description": "Tell BEAST to route beast-auto model resolution through ProviderAdapterRegistry locally.",
            "requires": ["target.path or target.file_ref"],
        },
    ]
    return semantic + common if profile.forbid_full_file_replacement else common


def build_provider_handoff(
    root: Path,
    objective: str,
    allowed_paths: Iterable[str],
    provider: str,
    *,
    task_name: str = "",
    mandatory_test_files: Dict[str, str] | None = None,
    failing_assertions: List[str] | None = None,
    verification: str = "python -m pytest tests -q",
    include_scout: bool = True,
    output_profile: ProviderOutputProfile | None = None,
) -> Dict[str, Any]:
    """Build the single object a provider should see for governed coding work."""

    root = Path(root)
    allowed = [str(path) for path in allowed_paths]
    profile = output_profile or provider_output_profile(provider)
    envelope = _task_envelope(objective, provider, allowed, task_name=task_name)
    context_packet = ContextPacketBuilder(max_file_chars=1400).build(
        envelope,
        workspace_root=str(root),
        semantic_limit=4,
        include_content=not profile.refs_only,
        max_files=max(1, len(allowed)),
    )
    scout_packet = _safe_scout_packet(root, objective, provider, envelope) if include_scout else {}
    output_refs = output_reference_packet(root, allowed, profile)
    handoff = {
        "kind": PROVIDER_HANDOFF_KIND,
        "version": "1.0",
        "objective": objective,
        "task": {
            "name": task_name,
            "allowed_paths": allowed,
            "selected_files": _selected_file_summary(root, allowed),
            "mandatory_test_files": mandatory_test_files or {},
            "failing_assertions": failing_assertions or [],
        },
        "input": {
            "task_envelope": envelope,
            "context_packet": context_packet,
            "context_packet_id": context_packet.get("packet_id"),
            "handoff_hash": context_packet.get("handoff_hash"),
            "scout_contract": scout_packet.get("decision_contract") or {},
            "scout_summary": (scout_packet.get("local_analysis") or {}).get("summary") if isinstance(scout_packet.get("local_analysis"), dict) else "",
            "ranked_chunks": scout_packet.get("ranked_chunks") or [],
            "tool_menu": scout_packet.get("tool_menu") or [],
            "chronicle_summary": scout_packet.get("chronicle_summary") or {},
        },
        "output": {
            "profile": profile.__dict__,
            "schema": output_contract_schema(profile),
            "instructions": output_contract_instructions(profile),
            "references": output_refs,
            "local_transforms": _local_transform_menu(profile),
            "rules": [
                "Return only the output.schema object, not this handoff object.",
                "Use refs and local_transforms before source-shaped snippets.",
                "Do not mention files outside task.allowed_paths.",
            ],
        },
        "verify": {
            "command": verification,
            "required": True,
            "chronicle_after_verify": True,
        },
        "trace": {
            "provider": provider,
            "profile_role": profile.role,
            "context_packet_id": context_packet.get("packet_id"),
            "input_handoff_hash": context_packet.get("handoff_hash"),
            "provider_handoff_hash": context_packet.get("handoff_hash"),
        },
    }
    encoded = json.dumps(handoff, separators=(",", ":"), sort_keys=True, default=str)
    handoff["packet_stats"] = {
        "chars": len(encoded),
        "estimated_tokens": _estimate_tokens(encoded),
        "allowed_path_count": len(allowed),
        "refs_only": profile.refs_only,
    }
    return handoff


def output_skeleton(handoff: Dict[str, Any]) -> Dict[str, Any]:
    """Return the minimal JSON object a provider should copy and fill."""

    output = handoff.get("output") if isinstance(handoff.get("output"), dict) else {}
    profile = output.get("profile") if isinstance(output.get("profile"), dict) else {}
    trace = handoff.get("trace") if isinstance(handoff.get("trace"), dict) else {}
    task = handoff.get("task") if isinstance(handoff.get("task"), dict) else {}
    references = output.get("references") if isinstance(output.get("references"), dict) else {}
    files = references.get("files") if isinstance(references.get("files"), list) else []
    first_ref = files[0] if files and isinstance(files[0], dict) else {}
    anchors = first_ref.get("anchors") if isinstance(first_ref.get("anchors"), list) else []
    first_anchor = anchors[0] if anchors and isinstance(anchors[0], dict) else {}
    allowed = task.get("allowed_paths") if isinstance(task.get("allowed_paths"), list) else []
    selected_files = task.get("selected_files") if isinstance(task.get("selected_files"), list) else []
    file_hash_by_path = {
        str(item.get("path") or ""): str(item.get("sha256") or "")
        for item in selected_files
        if isinstance(item, dict)
    }
    registry_path = next((str(path) for path in allowed if str(path).endswith("provider_registry.py")), "")
    api_path = next((str(path) for path in allowed if str(path).endswith("api.py")), "")
    if profile.get("forbid_full_file_replacement"):
        if registry_path and api_path and "provider/model wiring" in str(handoff.get("objective") or "").lower():
            return {
                "kind": "beast.action_intent.v1",
                "objective": str(handoff.get("objective") or ""),
                "provider_handoff_hash": str(trace.get("provider_handoff_hash") or trace.get("input_handoff_hash") or ""),
                "handoff_hash": str(trace.get("provider_handoff_hash") or trace.get("input_handoff_hash") or ""),
                "actions": [
                    {
                        "id": "a1",
                        "type": "add_provider_record",
                        "target": {"path": registry_path, "sha256": file_hash_by_path.get(registry_path, "")},
                        "intent": "add codex provider registry record",
                        "parameters": {
                            "provider_id": "codex",
                            "backend": "openai_compatible",
                            "default_model": "gpt-5-codex",
                            "env": ["OPENAI_API_KEY"],
                        },
                    },
                    {
                        "id": "a2",
                        "type": "add_provider_record",
                        "target": {"path": registry_path, "sha256": file_hash_by_path.get(registry_path, "")},
                        "intent": "add local_nim provider registry record",
                        "parameters": {
                            "provider_id": "local_nim",
                            "backend": "openai_compatible",
                            "default_model": "local-nim-model",
                            "env": ["LOCAL_NIM_BASE_URL", "LOCAL_NIM_API_KEY"],
                        },
                    },
                    {
                        "id": "a3",
                        "type": "set_default_model",
                        "target": {"path": registry_path, "sha256": file_hash_by_path.get(registry_path, "")},
                        "intent": "set OpenAI default model",
                        "parameters": {"provider_id": "openai", "default_model": "gpt-4o-mini"},
                    },
                    {
                        "id": "a4",
                        "type": "use_provider_registry_model_resolver",
                        "target": {"path": api_path, "sha256": file_hash_by_path.get(api_path, "")},
                        "intent": "resolve beast-auto through ProviderAdapterRegistry",
                        "parameters": {},
                    },
                ],
                "verify": [str((handoff.get("verify") or {}).get("command") or "python -m pytest tests -q")],
                "fallback": "",
            }
        return {
            "kind": "beast.action_intent.v1",
            "objective": str(handoff.get("objective") or ""),
            "provider_handoff_hash": str(trace.get("provider_handoff_hash") or trace.get("input_handoff_hash") or ""),
            "handoff_hash": str(trace.get("provider_handoff_hash") or trace.get("input_handoff_hash") or ""),
            "actions": [
                {
                    "id": "a1",
                    "type": "replace_anchor",
                    "target": {
                        "file_ref": str(first_ref.get("ref") or "F1"),
                        "anchor_ref": str(first_anchor.get("ref") or "A1"),
                    },
                    "intent": "state the local change BEAST should make",
                    "new": "replacement snippet only; omit old when anchor_ref is used",
                }
            ],
            "verify": [str((handoff.get("verify") or {}).get("command") or "python -m pytest tests -q")],
            "fallback": "",
        }
    return {
        "kind": "beast.patch_intent.v1",
        "operations": [
            {
                "op_id": "op_001",
                "op": "replace_exact",
                "path": str(allowed[0] if allowed else "allowed/path.py"),
                "old": "exact old snippet",
                "new": "replacement snippet",
                "why": "short reason",
            }
        ],
        "tests": [str((handoff.get("verify") or {}).get("command") or "python -m pytest tests -q")],
    }


def output_skeleton_prompt(handoff: Dict[str, Any]) -> str:
    output = handoff.get("output") if isinstance(handoff.get("output"), dict) else {}
    references = output.get("references") if isinstance(output.get("references"), dict) else {}
    files = references.get("files") if isinstance(references.get("files"), list) else []
    local_transforms = output.get("local_transforms") if isinstance(output.get("local_transforms"), list) else []
    legal_refs = []
    for item in files:
        if not isinstance(item, dict):
            continue
        anchors = item.get("anchors") if isinstance(item.get("anchors"), list) else []
        legal_refs.append({
            "file_ref": item.get("ref"),
            "path": item.get("path"),
            "anchor_refs": [anchor.get("ref") for anchor in anchors[:8] if isinstance(anchor, dict)],
        })
    legal_actions = [item.get("type") for item in local_transforms if isinstance(item, dict) and item.get("type")]
    return "\n".join([
        "STRICT OUTPUT MODE.",
        "Copy the JSON skeleton below and fill only its values.",
        "Return the filled JSON object only. No prose. No markdown. No code fences.",
        "Do not invent keys outside this skeleton unless the skeleton action type requires parameters.",
        "Legal file refs and anchor refs: " + json.dumps(legal_refs, separators=(",", ":"), sort_keys=True),
        "Legal action types: " + json.dumps(legal_actions, separators=(",", ":"), sort_keys=True),
        "JSON skeleton to copy:",
        json.dumps(output_skeleton(handoff), separators=(",", ":"), sort_keys=True),
    ])


def render_provider_handoff_prompt(handoff: Dict[str, Any], include_legacy_prompt: str = "") -> str:
    """Render a compact provider prompt from a unified handoff object."""

    output = handoff.get("output") if isinstance(handoff.get("output"), dict) else {}
    instructions = [str(item) for item in output.get("instructions") or []]
    parts = [
        output_skeleton_prompt(handoff),
    ] + instructions + [
        "Provider handoff: " + json.dumps(handoff, separators=(",", ":"), sort_keys=True, default=str),
    ]
    if include_legacy_prompt:
        parts.append("Legacy lane prompt for extra context:\n" + include_legacy_prompt)
    return "\n\n".join(parts)
