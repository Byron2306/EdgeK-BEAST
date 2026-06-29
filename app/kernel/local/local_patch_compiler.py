"""Compile resolved BEAST actions into deterministic file operations."""

from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Dict, Iterable, List

from app.kernel.compute.action_resolver import ResolvedAction


def compile_resolved_actions(root: Path, actions: Iterable[ResolvedAction], max_old_chars: int = 800, max_new_chars: int = 1600) -> List[Dict[str, str]]:
    staged: Dict[str, str] = {}
    descriptions: Dict[str, str] = {}
    expected_hashes: Dict[str, str] = {}
    for item in actions:
        if not item.semantic and len(item.old) > max_old_chars:
            raise ValueError(f"action {item.action.id} old snippet exceeded {max_old_chars} chars")
        if not item.semantic and len(item.new) > max_new_chars:
            raise ValueError(f"action {item.action.id} new snippet exceeded {max_new_chars} chars")
        current = staged.get(item.path)
        if current is None:
            path = root / item.path
            if not path.exists():
                raise ValueError(f"action target did not exist: {item.path}")
            current = path.read_text(encoding="utf-8")
            if item.expected_sha256:
                actual = hashlib.sha256(current.encode("utf-8")).hexdigest()
                if actual != item.expected_sha256:
                    raise ValueError(f"action {item.action.id} target file changed since resolution: {item.path}")
                expected_hashes[item.path] = item.expected_sha256
        elif item.expected_sha256 and expected_hashes.get(item.path) and item.expected_sha256 != expected_hashes[item.path]:
            # Later semantic actions may have been resolved against the original
            # file. Staging is still safe because each action carries a unique
            # block anchor that must match the staged content exactly once.
            pass
        count = current.count(item.old)
        if count != 1:
            raise ValueError(f"action {item.action.id} old snippet matched {count} times in {item.path}")
        staged[item.path] = current.replace(item.old, item.new, 1)
        descriptions[item.path] = item.action.intent
    return [
        {"path": path, "content": content, "description": descriptions.get(path, "")}
        for path, content in sorted(staged.items())
    ]
