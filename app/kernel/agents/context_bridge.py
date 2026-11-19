"""Context bridge: file selection -> bounded model context (Phase 5).

The IDE sends a selection (paths, optional line ranges). The bridge resolves it
against the workspace, excludes sensitive/binary/generated files, truncates to a
character budget, and returns deterministic prompt material plus the evidence
used to build it. That keeps "what the model saw" auditable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

DEFAULT_EXCLUDED_PARTS = frozenset(
    {".git", ".hg", ".svn", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
)
DEFAULT_SENSITIVE_NAMES = frozenset({".env", ".env.local", ".env.production", "id_rsa", "id_dsa"})
DEFAULT_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".crt")
DEFAULT_PREAMBLE = (
    "You are BEAST. The following workspace files were explicitly selected by the "
    "operator. Use them as ground truth; cite paths when you refer to them."
)


@dataclass(frozen=True)
class SelectedFile:
    path: str
    start_line: int = 0
    end_line: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "start_line": self.start_line, "end_line": self.end_line}


@dataclass
class ContextBridge:
    workspace_root: Union[str, Path]
    max_files: int = 8
    max_chars_each: int = 4000
    max_total_chars: int = 24000
    preamble: str = DEFAULT_PREAMBLE
    excluded_parts: frozenset[str] = DEFAULT_EXCLUDED_PARTS
    sensitive_names: frozenset[str] = DEFAULT_SENSITIVE_NAMES
    sensitive_suffixes: tuple[str, ...] = DEFAULT_SENSITIVE_SUFFIXES

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).expanduser().resolve()

    # -- selection ---------------------------------------------------------

    def resolve(self, selection: Union[str, SelectedFile, Dict[str, Any]]) -> SelectedFile:
        item = _selection(selection)
        candidate = Path(item.path)
        target = candidate if candidate.is_absolute() else self.workspace_root / candidate
        resolved = target.resolve()
        root = Path(self.workspace_root)
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"selected path escapes the workspace: {item.path}")
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:  # pragma: no cover - covered by the check above
            raise ValueError(f"selected path escapes the workspace: {item.path}") from exc
        return SelectedFile(relative, item.start_line, item.end_line)

    def _exclusion_reason(self, relative: str) -> str:
        parts = Path(relative).parts
        if any(part in self.excluded_parts for part in parts):
            return "excluded_directory"
        name = Path(relative).name
        if name in self.sensitive_names or name.startswith(".env"):
            return "sensitive_file"
        if any(name.endswith(suffix) for suffix in self.sensitive_suffixes):
            return "sensitive_file"
        return ""

    # -- reading -----------------------------------------------------------

    def read(self, selection: Union[str, SelectedFile, Dict[str, Any]]) -> Dict[str, Any]:
        item = self.resolve(selection)
        absolute = Path(self.workspace_root) / item.path
        reason = self._exclusion_reason(item.path)
        if reason:
            return {"path": item.path, "excluded": reason}
        if not absolute.is_file():
            return {"path": item.path, "excluded": "missing"}

        raw = absolute.read_bytes()
        if b"\x00" in raw[:4096]:
            return {"path": item.path, "excluded": "binary"}
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        start = max(1, int(item.start_line or 1))
        end = int(item.end_line or 0)
        if end <= 0 or end > len(lines):
            end = len(lines)
        if start > end:
            start, end = 1, 0
        selected = "\n".join(lines[start - 1:end]) if end else ""
        truncated = False
        if len(selected) > self.max_chars_each:
            selected = selected[: self.max_chars_each] + "\n... [truncated]"
            truncated = True
        return {
            "path": item.path,
            "start_line": start,
            "end_line": end,
            "lines": max(0, end - start + 1) if end else 0,
            "content": selected,
            "chars": len(selected),
            "truncated": truncated,
            "content_hash": "sha256:" + hashlib.sha256(selected.encode("utf-8")).hexdigest(),
        }

    # -- model context -----------------------------------------------------

    def build(
        self,
        selection: Iterable[Union[str, SelectedFile, Dict[str, Any]]],
        objective: str = "",
        *,
        extra_notes: str = "",
    ) -> Dict[str, Any]:
        files: List[Dict[str, Any]] = []
        excluded: List[Dict[str, str]] = []
        seen: set[str] = set()
        total_chars = 0
        budget_exhausted = False

        for entry in selection or []:
            resolved = self.resolve(entry)
            if resolved.path in seen:
                continue
            seen.add(resolved.path)
            if len(files) >= self.max_files:
                excluded.append({"path": resolved.path, "reason": "max_files"})
                continue
            if budget_exhausted:
                excluded.append({"path": resolved.path, "reason": "max_total_chars"})
                continue

            result = self.read(resolved)
            if result.get("excluded"):
                excluded.append({"path": resolved.path, "reason": str(result["excluded"])})
                continue
            remaining = self.max_total_chars - total_chars
            if remaining <= 0:
                excluded.append({"path": resolved.path, "reason": "max_total_chars"})
                budget_exhausted = True
                continue
            content = result["content"]
            if len(content) > remaining:
                content = content[:remaining] + "\n... [truncated]"
                result["truncated"] = True
            total_chars += len(content)
            result["content"] = content
            result["chars"] = len(content)
            files.append(result)

        context_block = self._render(files, extra_notes)
        messages = [{"role": "system", "content": f"{self.preamble}\n\n{context_block}".strip()}]
        if objective:
            messages.append({"role": "user", "content": objective})
        return {
            "objective": objective,
            "files": files,
            "excluded": excluded,
            "stats": {
                "selected": len(seen),
                "included": len(files),
                "excluded": len(excluded),
                "chars": total_chars,
                "truncated": sum(1 for item in files if item.get("truncated")),
            },
            "context_block": context_block,
            "messages": messages,
        }

    @staticmethod
    def _render(files: Sequence[Dict[str, Any]], extra_notes: str = "") -> str:
        chunks: List[str] = []
        if extra_notes:
            chunks.append(extra_notes.strip())
        for item in files:
            span = ""
            if item.get("end_line"):
                span = f" (lines {item['start_line']}-{item['end_line']})"
            chunks.append(f"## {item['path']}{span}\n```\n{item.get('content', '')}\n```")
        return "\n\n".join(chunks)


def _selection(selection: Union[str, SelectedFile, Dict[str, Any]]) -> SelectedFile:
    if isinstance(selection, SelectedFile):
        return selection
    if isinstance(selection, dict):
        return SelectedFile(
            str(selection.get("path") or ""),
            int(selection.get("start_line") or 0),
            int(selection.get("end_line") or 0),
        )
    return SelectedFile(str(selection or ""))


def build_context(
    workspace_root: Union[str, Path],
    selection: Iterable[Union[str, SelectedFile, Dict[str, Any]]],
    objective: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    bridge = ContextBridge(workspace_root, **_budget_kwargs(kwargs))
    return bridge.build(selection, objective, extra_notes=str(kwargs.get("extra_notes") or ""))


def _budget_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"max_files", "max_chars_each", "max_total_chars", "preamble"}
    return {key: value for key, value in kwargs.items() if key in allowed}
