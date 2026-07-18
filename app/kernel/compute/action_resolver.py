"""Resolve BEAST Action IR refs into local files and anchors."""

from __future__ import annotations

import hashlib
import json
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.kernel.compute.action_ir import ActionIR, ActionIntent, FileReference


@dataclass(frozen=True)
class ResolvedAction:
    action: ActionIntent
    path: str
    old: str
    new: str
    expected_sha256: str = ""
    start: Optional[int] = None
    end: Optional[int] = None
    current_text: str = ""
    next_text: str = ""
    semantic: bool = False


@dataclass(frozen=True)
class ResolvedRequest:
    action: ActionIntent
    type: str
    path: str = ""
    intent: str = ""
    parameters: Dict[str, object] | None = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.action.id,
            "type": self.type,
            "path": self.path,
            "intent": self.intent,
            "parameters": dict(self.parameters or {}),
        }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reject_placeholder_replacement(action: ActionIntent, old: str, new: str) -> None:
    """Reject model-shaped pseudo-edits before they become a SourcePlan.

    A frequent weak-model failure is to restate a function signature followed
    by ``# ... rest of function remains the same``.  That is neither a
    reviewable patch nor a faithful replacement; accepting it makes the UI
    advertise a change while showing the operator no implementation.
    """
    if old == new:
        raise ValueError(f"action {action.id} makes no material source change")
    placeholder = re.compile(
        r"(?im)^\s*(?:#|//|/\*)?\s*(?:\.\.\.|…)(?:\s*\(?\s*(?:the\s+)?rest\s+of\s+(?:the\s+)?(?:function|file|method|code).*|\s*unchanged.*)?$"
    )
    prose_placeholder = re.compile(
        r"(?i)(?:rest\s+of\s+(?:the\s+)?(?:function|file|method|code)\s+(?:remains?|is)\s+(?:the\s+)?same|implementation\s+(?:omitted|unchanged)|\[\s*unchanged\s*\])"
    )
    if placeholder.search(new) or prose_placeholder.search(new):
        raise ValueError(
            f"action {action.id} contains a placeholder instead of a complete source replacement; "
            "emit the full changed block with no ellipses or 'rest remains the same' text"
        )


def _safe_path(root: Path, rel: str) -> Path:
    rel_path = Path(str(rel))
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"unsafe path: {rel}")
    target = (root / rel_path).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"path escaped workspace: {rel}")
    return target


def _anchor_catalog(text: str, max_anchors: int = 24, max_chars: int = 500) -> Dict[str, str]:
    anchors: Dict[str, str] = {}

    def unique_line_anchor(lines: List[str], index: int) -> str:
        """Return a bounded anchor whose occurrence is unique in ``text``.

        A single line such as ``return value`` or a repeated docstring bullet
        is not a usable edit locator. Expand symmetrically with neighbouring
        source until it identifies exactly one location, otherwise omit it.
        """
        for radius in range(0, 12):
            start = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            snippet = "\n".join(lines[start:end])
            if not snippet or len(snippet) > max_chars:
                break
            if text.count(snippet) == 1:
                return snippet
        return ""

    # Light block anchors first, so long files still expose semantic edit units.
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith('"') and stripped.endswith("{")):
            continue
        block = [line]
        depth = line.count("{") - line.count("}")
        for next_line in lines[index + 1:index + 12]:
            block.append(next_line)
            depth += next_line.count("{") - next_line.count("}")
            if depth <= 0 and next_line.strip().endswith(("},", "}")):
                break
        snippet = "\n".join(block)
        if 0 < len(snippet) <= max_chars and snippet not in anchors.values():
            anchors[f"A{len(anchors) + 1}"] = snippet
        if len(anchors) >= max_anchors:
            return anchors
    # Compact line anchors catch small return/config edits after block anchors.
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped in {"{", "}", "(", ")"}:
            continue
        snippet = unique_line_anchor(lines, index)
        if snippet and snippet not in anchors.values():
            anchors[f"A{len(anchors) + 1}"] = snippet
        if len(anchors) >= max_anchors:
            return anchors
    return anchors


def build_file_references(root: Path, paths: Iterable[str], include_anchors: bool = True) -> List[FileReference]:
    refs: List[FileReference] = []
    for index, rel in enumerate(paths, start=1):
        path = _safe_path(root, str(rel))
        text = path.read_text(encoding="utf-8") if include_anchors and path.exists() and path.is_file() else ""
        refs.append(FileReference(
            ref=f"F{index}",
            path=str(rel),
            sha256=file_sha256(path) if path.exists() and path.is_file() else "",
            anchors=_anchor_catalog(text) if text else {},
        ))
    return refs


def _provider_record_snippet(provider_id: str, backend: str, default_model: str, env: List[str], indent: str = "        ") -> str:
    env_text = ", ".join(json.dumps(str(item)) for item in env)
    return (
        f'{indent}{json.dumps(provider_id)}: {{\n'
        f'{indent}    "backend": {json.dumps(str(backend))},\n'
        f'{indent}    "default_model": {json.dumps(str(default_model))},\n'
        f'{indent}    "env": [{env_text}],\n'
        f'{indent}}},\n'
    )


def _defaults_block(text: str) -> tuple[int, int, List[str]]:
    lines = text.splitlines(keepends=True)
    start = -1
    depth = 0
    for index, line in enumerate(lines):
        if "DEFAULTS" in line and "{" in line:
            start = index
            depth = line.count("{") - line.count("}")
            break
    if start < 0:
        raise ValueError("ProviderRegistry.DEFAULTS block was not found")
    for index in range(start + 1, len(lines)):
        depth += lines[index].count("{") - lines[index].count("}")
        if depth <= 0:
            return start, index, lines
    raise ValueError("ProviderRegistry.DEFAULTS block was not closed")


def _defaults_mapping(text: str) -> Dict[str, object]:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULTS":
                    value = ast.literal_eval(node.value)
                    return value if isinstance(value, dict) else {}
                if isinstance(target, ast.Attribute) and target.attr == "DEFAULTS":
                    value = ast.literal_eval(node.value)
                    return value if isinstance(value, dict) else {}
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "DEFAULTS":
                value = ast.literal_eval(node.value)
                return value if isinstance(value, dict) else {}
            if isinstance(target, ast.Attribute) and target.attr == "DEFAULTS":
                value = ast.literal_eval(node.value)
                return value if isinstance(value, dict) else {}
    return {}


def _python_dict_literal(value: object, indent: str = "        ") -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = []
        child_indent = indent + "    "
        for key, item in value.items():
            inner.append(f"{child_indent}{json.dumps(str(key))}: {_python_dict_literal(item, child_indent)},")
        return "{\n" + "\n".join(inner) + f"\n{indent}" + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_python_dict_literal(item, indent) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    return repr(value)


def _resolve_add_provider_record(action: ActionIntent, path: str, current: str) -> ResolvedAction:
    params = action.parameters or {}
    provider_id = str(params.get("provider_id") or params.get("id") or params.get("name") or "").replace("-", "_")
    backend = str(params.get("backend") or "openai_compatible")
    default_model = str(params.get("default_model") or params.get("model") or provider_id)
    raw_env = params.get("env") or params.get("env_vars") or []
    env = [str(item) for item in raw_env] if isinstance(raw_env, list) else [str(raw_env)] if raw_env else []
    if not provider_id:
        raise ValueError(f"action {action.id} missing provider_id")
    if f'"{provider_id}"' in current:
        return ResolvedAction(action=action, path=path, old=current, new=current)
    start, end, lines = _defaults_block(current)
    old_block = "".join(lines[start:end + 1])
    closing = lines[end]
    indent = closing[: len(closing) - len(closing.lstrip())] + "    "
    snippet = _provider_record_snippet(provider_id, backend, default_model, env, indent=indent)
    new_block = "".join(lines[start:end]) + snippet + closing
    return ResolvedAction(
        action=action,
        path=path,
        old=old_block,
        new=new_block,
        expected_sha256=_sha256_text(current),
        semantic=True,
    )


def _resolve_set_default_model(action: ActionIntent, path: str, current: str) -> ResolvedAction:
    params = action.parameters or {}
    provider_id = str(params.get("provider_id") or params.get("id") or params.get("name") or "").replace("-", "_")
    default_model = str(params.get("default_model") or params.get("model") or "")
    if not provider_id or not default_model:
        raise ValueError(f"action {action.id} missing provider_id/default_model")
    _, _, lines = _defaults_block(current)
    text = "".join(lines)
    marker = f'"{provider_id}": {{'
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"action {action.id} provider record was not found: {provider_id}")
    next_record = text.find('\n        "', start + len(marker))
    end = next_record if next_record >= 0 else text.find("\n    }", start)
    block = text[start:end if end >= 0 else len(text)]
    if '"default_model"' in block:
        old_line = next(line for line in block.splitlines(keepends=True) if '"default_model"' in line)
        indent = old_line[: len(old_line) - len(old_line.lstrip())]
        updated_block = block.replace(old_line, f'{indent}"default_model": {json.dumps(str(default_model))},\n', 1)
        return ResolvedAction(action=action, path=path, old=block, new=updated_block, expected_sha256=_sha256_text(current), semantic=True)
    backend_line = next((line for line in block.splitlines(keepends=True) if '"backend"' in line), "")
    if not backend_line:
        raise ValueError(f"action {action.id} provider backend line was not found: {provider_id}")
    indent = backend_line[: len(backend_line) - len(backend_line.lstrip())]
    updated_block = block.replace(backend_line, backend_line + f'{indent}"default_model": {json.dumps(str(default_model))},\n', 1)
    return ResolvedAction(action=action, path=path, old=block, new=updated_block, expected_sha256=_sha256_text(current), semantic=True)


def _resolve_add_provider_alias(action: ActionIntent, path: str, current: str) -> ResolvedAction:
    params = action.parameters or {}
    alias_id = str(params.get("alias") or params.get("alias_id") or params.get("provider_id") or params.get("id") or params.get("name") or "").replace("-", "_")
    target_id = str(params.get("target_provider") or params.get("alias_of") or params.get("base_provider") or params.get("provider_alias_of") or "").replace("-", "_")
    if not alias_id or not target_id:
        raise ValueError(f"action {action.id} missing alias/target provider")
    defaults = _defaults_mapping(current)
    if alias_id in defaults or f'"{alias_id}"' in current:
        return ResolvedAction(action=action, path=path, old=current, new=current, expected_sha256=_sha256_text(current), semantic=True)
    target = defaults.get(target_id)
    if not isinstance(target, dict):
        raise ValueError(f"action {action.id} alias target provider was not found: {target_id}")

    alias_record = {
        "backend": params.get("backend") or target.get("backend") or "openai_compatible",
        "env": params.get("env") or params.get("env_vars") or target.get("env") or [],
        "proxy_path": params.get("proxy_path") or f"/proxy/{alias_id.replace('_', '-')}",
        "litellm_model_prefix": params.get("litellm_model_prefix") if "litellm_model_prefix" in params else target.get("litellm_model_prefix", ""),
        "default_model": params.get("default_model") or params.get("model") or target.get("default_model"),
        "openai_compatible": params.get("openai_compatible") if "openai_compatible" in params else target.get("openai_compatible", False),
        "metadata": {
            **(target.get("metadata") if isinstance(target.get("metadata"), dict) else {}),
            "provider_alias_of": target_id,
        },
    }
    for key in ("base_url", "native_adapter", "risk_level", "requires_approval", "gateway_lane", "managed_by"):
        if key in params:
            alias_record[key] = params[key]
        elif key in target:
            alias_record[key] = target[key]

    start, end, lines = _defaults_block(current)
    old_block = "".join(lines[start:end + 1])
    closing = lines[end]
    indent = closing[: len(closing) - len(closing.lstrip())] + "    "
    snippet = f"{indent}{json.dumps(alias_id)}: {_python_dict_literal(alias_record, indent)},\n"
    new_block = "".join(lines[start:end]) + snippet + closing
    return ResolvedAction(
        action=action,
        path=path,
        old=old_block,
        new=new_block,
        expected_sha256=_sha256_text(current),
        semantic=True,
    )


def _resolve_provider_registry_model_resolver(action: ActionIntent, path: str, current: str) -> ResolvedAction:
    old = '''class BeastApiClient:
    def _chat_model_for_provider(self, provider, model="beast-auto"):
        provider_id = str(provider or "").lower().replace("-", "_")
        if model and model != "beast-auto":
            return model
        if provider_id in {"litellm", "auto", "beast_auto"}:
            return "ollama"
        if provider_id == "ollama":
            return "qwen2.5:0.5b"
        return "" if model == "beast-auto" else model
'''
    new = '''from app.kernel.registry.provider_registry import ProviderAdapterRegistry


class BeastApiClient:
    def _chat_model_for_provider(self, provider, model="beast-auto"):
        provider_id = str(provider or "").lower().replace("-", "_")
        if model and model != "beast-auto":
            return model
        if provider_id in {"auto", "beast_auto"}:
            provider_id = "litellm"
        record = ProviderAdapterRegistry().adapter_for(provider_id)
        if provider_id == "litellm":
            return "litellm/" + record.default_model
        return record.default_model
'''
    if old not in current:
        raise ValueError(f"action {action.id} provider registry resolver pattern was not found")
    return ResolvedAction(action=action, path=path, old=old, new=new, expected_sha256=_sha256_text(current), semantic=True)


def resolve_action_ir(
    root: Path,
    action_ir: ActionIR,
    file_refs: Iterable[FileReference],
    allowed_paths: Iterable[str],
    expected_handoff_hash: str = "",
) -> tuple[List[ResolvedAction], List[ResolvedRequest]]:
    if expected_handoff_hash and action_ir.handoff_hash != expected_handoff_hash:
        raise ValueError("Action IR handoff_hash did not match provider handoff")
    by_ref: Dict[str, FileReference] = {item.ref: item for item in file_refs}
    allowed = {str(path) for path in allowed_paths}
    resolved: List[ResolvedAction] = []
    requests: List[ResolvedRequest] = []
    semantic_staged: Dict[str, str] = {}
    for action in action_ir.actions:
        path = action.target.path
        if not path and action.target.file_ref:
            path = by_ref.get(action.target.file_ref, FileReference("", "")).path
        if not path and action.parameters.get("path"):
            path = str(action.parameters.get("path") or "")
        if action.type in {"ask_for_context", "run_verifier"}:
            if path:
                if path not in allowed:
                    raise ValueError(f"action {action.id} target path was not allowed: {path}")
                _safe_path(root, path)
            requests.append(ResolvedRequest(
                action=action,
                type=action.type,
                path=path,
                intent=action.intent,
                parameters=action.parameters,
            ))
            continue
        if path not in allowed:
            raise ValueError(f"action {action.id} target path was not allowed: {path}")
        target = _safe_path(root, path)
        ref = by_ref.get(action.target.file_ref) if action.target.file_ref else None
        expected_target_hash = str(action.target.sha256 or (ref.sha256 if ref else "") or "")
        if expected_target_hash and target.exists() and file_sha256(target) != expected_target_hash:
            raise ValueError(f"action {action.id} target file changed since handoff: {path}")
        if action.type not in {"replace_anchor", "replace_exact", "modify_symbol", "add_provider_record", "set_default_model", "add_provider_alias", "use_provider_registry_model_resolver"}:
            raise ValueError(f"action {action.id} type was not allowed: {action.type}")
        if action.type in {"add_provider_record", "set_default_model", "add_provider_alias", "use_provider_registry_model_resolver"}:
            current = semantic_staged.get(path)
            if current is None:
                current = target.read_text(encoding="utf-8")
            if action.type == "add_provider_record":
                item = _resolve_add_provider_record(action, path, current)
                resolved.append(item)
                if current.count(item.old) == 1:
                    semantic_staged[path] = current.replace(item.old, item.new, 1)
                continue
            if action.type == "set_default_model":
                item = _resolve_set_default_model(action, path, current)
                resolved.append(item)
                if current.count(item.old) == 1:
                    semantic_staged[path] = current.replace(item.old, item.new, 1)
                continue
            if action.type == "use_provider_registry_model_resolver":
                item = _resolve_provider_registry_model_resolver(action, path, current)
                resolved.append(item)
                if current.count(item.old) == 1:
                    semantic_staged[path] = current.replace(item.old, item.new, 1)
                continue
            if action.type == "add_provider_alias":
                item = _resolve_add_provider_alias(action, path, current)
                resolved.append(item)
                if current.count(item.old) == 1:
                    semantic_staged[path] = current.replace(item.old, item.new, 1)
                continue
        old = action.old
        new = action.new
        if action.target.anchor_ref and not old:
            old = (ref.anchors or {}).get(action.target.anchor_ref, "") if ref else ""
        if not old or not isinstance(new, str):
            raise ValueError(f"action {action.id} did not include resolvable old/new snippets")
        _reject_placeholder_replacement(action, old, new)
        current = target.read_text(encoding="utf-8")
        if current.count(old) != 1:
            raise ValueError(f"action {action.id} anchor was not unique in {path}")
        resolved.append(ResolvedAction(action=action, path=path, old=old, new=new, expected_sha256=_sha256_text(current)))
    return resolved, requests


def resolve_actions(
    root: Path,
    action_ir: ActionIR,
    file_refs: Iterable[FileReference],
    allowed_paths: Iterable[str],
    expected_handoff_hash: str = "",
) -> List[ResolvedAction]:
    resolved, _requests = resolve_action_ir(
        root,
        action_ir,
        file_refs,
        allowed_paths,
        expected_handoff_hash=expected_handoff_hash,
    )
    return resolved
