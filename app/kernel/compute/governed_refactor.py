"""Governed-path tool wiring for rename / multi-file families (model decides WHAT, ``code.rename_symbol`` does WHERE).

For ``refactor-rename-symbol`` and the ``composite-refguard`` (rename + guard) / multi-file families the governed client
forces the ``RENAME_ACTION_SCHEMA``: ``{"renames": [{symbol, file, new_name}], "edits": [...]}``. The model never
writes call-site edits for a rename; the deterministic tool (``app.kernel.compute.symbol_rename``) resolves and rewrites
every reference atomically. Any other change (e.g. an empty-input guard) goes in ``edits``; renames are applied first
and edits written against the original names are rebased onto the renamed tree (pure-rename edits are dropped). The verifier (visible
tests + hidden intent check) still gates acceptance; the tool grants nothing by itself.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.kernel.compute.symbol_rename import RENAME_ACTION_SCHEMA, RenameError, TOOL_ID, apply_action

TOOL_FAMILY_PREFIXES = ("refactor-rename", "composite-refguard", "fresh-single2", "fresh-lattice2", "multi-file")
IMPORT_NAME = re.compile(r"cannot import name '(\w+)' from '([\w.]+)'")
ATTR_MISSING = re.compile(r"module '([\w.]+)' has no attribute '(\w+)'")

ACTION_SYSTEM = (
    "You are a precise refactoring agent with a deterministic rename tool. Reply with exactly one JSON object "
    '{"renames": [{"symbol": <existing top-level name>, "file": <repo-relative defining file>, "new_name": <identifier>}], '
    '"edits": [{"path": <repo-relative file>, "old_text": <exact existing text>, "new_text": <replacement>}]} and nothing else. '
    "Use renames for EVERY rename: the tool updates the definition, imports, module attribute uses, re-exports and __all__ "
    "in all files, so never write call-site edits for a rename. Use edits only for other behaviour changes (old_text copied exactly from the files shown). "
    "If an edit's old_text occurs more than once, also supply anchor_line (1-based, nearest wins), "
    "before_context/after_context, or occurrence (1-based among matches). Never edit test files. Omit edits if none are needed.")
ACTION_FEW_SHOT: tuple[tuple[str, str], ...] = (
    ("--- shop/core.py ---\ndef get_cart(user):\n    return user.items[0]\n--- shop/api.py ---\nfrom shop.core import get_cart\n\n\n"
     "def view(user):\n    return get_cart(user)\n--- failing test output ---\n"
     "ImportError: cannot import name 'load_cart' from 'shop.core'\nIndexError: list index out of range",
     '{"renames": [{"symbol": "get_cart", "file": "shop/core.py", "new_name": "load_cart"}], "edits": [{"path": "shop/core.py", '
     '"old_text": "    return user.items[0]", "new_text": "    if not user.items:\\n        return None\\n    return user.items[0]"}]}'),
)


def uses_rename_tool(family: str, failure: str = "") -> bool:
    return family.startswith(TOOL_FAMILY_PREFIXES) or bool(IMPORT_NAME.search(failure or "") or ATTR_MISSING.search(failure or ""))


def action_messages(files: Mapping[str, str], failure: str, *, target: str = "") -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": ACTION_SYSTEM}]
    for user, assistant in ACTION_FEW_SHOT:
        msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    body = "".join(f"--- {path} ---\n{content}\n" for path, content in files.items())
    head = f"Implementation target: {target}\n" if target else ""
    msgs.append({"role": "user", "content": f"{head}{body}--- failing test output ---\n{failure[-1800:]}"})
    return msgs


def _edits_actuator(root: Path, edits: Sequence[Mapping[str, str]]) -> list[str]:
    from app.kernel.compute.family_crystals import apply_plan
    from app.kernel.compute.structured_edit import degenerate_edit

    clean = []
    for e in edits:
        path, old, new = e.get("path"), e.get("old_text"), e.get("new_text")
        if not (isinstance(path, str) and isinstance(old, str) and isinstance(new, str)) or not old.strip() or old == new:
            continue
        from app.kernel.compute.structured_edit import action_optional_fields
        item = {"path": path, "old_text": old.rstrip("\n"), "new_text": new.rstrip("\n"),
                **action_optional_fields(e)}
        stub = degenerate_edit(item)
        if stub:
            raise RenameError(stub)
        clean.append(item)
    try:
        return apply_plan(root, {"edits": clean}) if clean else []
    except (PermissionError, KeyError, OSError) as exc:
        raise RenameError(f"edit_not_applicable:{exc}") from exc


def apply_action_to_copy(root: Path, action: Any, wt: Path, *, exclude: Sequence[str] = ("test_*.py",)) -> dict[str, Any]:
    """Copy ``root`` to ``wt`` and apply a model action there (never touches ``root``)."""
    if wt.exists():
        shutil.rmtree(wt)
    shutil.copytree(root, wt)
    if not isinstance(action, Mapping):
        return {"applied": False, "reason": "no_parseable_action"}
    try:
        res = apply_action(wt, dict(action), exclude=exclude, apply_edits=_edits_actuator)
    except RenameError as exc:
        detail = str(exc)
        return {"applied": False, "reason": f"tool_refused:{detail}"[:200], "output_tail": detail[-1500:]}
    return {"applied": True, "changed": res["changed"], "tool": TOOL_ID, "renames": res["renames"]}


def action_for_family(family: str, failure: str = "") -> dict[str, Any]:
    """What the governed client should force for this family: the tool action schema or plain exact edits."""
    from app.kernel.compute.structured_edit import EDITS_SCHEMA, edits_messages

    if uses_rename_tool(family, failure):
        return {"tool": TOOL_ID, "schema": RENAME_ACTION_SCHEMA, "messages": action_messages}
    return {"tool": "", "schema": EDITS_SCHEMA, "messages": edits_messages}


__all__ = ["ACTION_SYSTEM", "RENAME_ACTION_SCHEMA", "action_for_family", "action_messages", "apply_action_to_copy",
           "uses_rename_tool"]
