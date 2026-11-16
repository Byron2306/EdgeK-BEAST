"""Deterministic, scope-aware Python symbol rename (BEAST governed tool ``code.rename_symbol``).

The model (or an operator) decides only WHAT to rename -- ``{symbol, file, new_name}``; this module decides WHERE.
It uses libcst's FullRepoManager + FullyQualifiedNameProvider so every reference is resolved to a fully qualified
name before it is touched:

* the definition (top-level ``def`` / ``class`` / module-level assignment) in ``file``;
* every Name that resolves to it (locals that merely share the spelling are left alone);
* ``from pkg.mod import symbol`` / relative ``from .mod import symbol`` (aliases keep their ``as`` name);
* attribute access through a module binding (``core.symbol``, ``pkg.core.symbol``) and through package re-exports
  (``pkg/__init__.py: from .core import symbol`` -> ``pkg.symbol``), iterated to a fixpoint;
* ``__all__`` string entries in modules where the name is bound to the target.

Plain strings, docstrings and comments that mention the symbol are FLAGGED, never rewritten. Unresolvable attribute
access (``obj.symbol`` on a non-module) is flagged. ``import *`` of the defining module is flagged.

Edits are planned in memory, every result must re-parse and compile, the post-rename tree is re-scanned (zero
remaining resolved references), and only then are files swapped in with ``os.replace`` (rollback on any error).
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import keyword
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import libcst as cst
from libcst.helpers import get_absolute_module_from_package_for_import
from libcst.metadata import FullRepoManager, FullyQualifiedNameProvider, PositionProvider, ScopeProvider

TOOL_ID = "code.rename_symbol"
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache", "build", "dist"}
DEFAULT_EXCLUDE: tuple[str, ...] = ()
RENAME_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["renames"],
    "properties": {
        "renames": {"type": "array", "minItems": 0, "maxItems": 4, "items": {
            "type": "object", "additionalProperties": False, "required": ["symbol", "file", "new_name"],
            "properties": {"symbol": {"type": "string"}, "file": {"type": "string"}, "new_name": {"type": "string"}}}},
        "edits": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False, "required": ["path", "old_text", "new_text"],
            "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"},
                           "anchor_line": {"type": "integer", "minimum": 1},
                           "before_context": {"type": "string"}, "after_context": {"type": "string"},
                           "occurrence": {"type": "integer", "minimum": 1}}}},
    },
}


class RenameError(ValueError):
    """Refusal: the rename is unsafe or not applicable (nothing is written)."""


@dataclass
class Ref:
    path: str
    line: int
    col: int
    kind: str          # definition | name | import | attribute | __all__ | string | comment | unresolved_attribute | star_import
    changed: bool
    text: str = ""


@dataclass
class RenamePlan:
    symbol: str
    file: str
    new_name: str
    target: str
    aliases: list[str]
    refs: list[Ref] = field(default_factory=list)
    new_text: dict[str, str] = field(default_factory=dict)
    old_text: dict[str, str] = field(default_factory=dict)

    @property
    def changed_files(self) -> list[str]:
        return sorted(p for p in self.new_text if self.new_text[p] != self.old_text[p])

    def diff(self) -> str:
        return "".join("".join(difflib.unified_diff(self.old_text[p].splitlines(True), self.new_text[p].splitlines(True),
                                                    f"a/{p}", f"b/{p}")) for p in self.changed_files)

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for r in self.refs:
            key = r.kind + ("" if r.changed else ":flagged")
            counts[key] = counts.get(key, 0) + 1
        return {"tool": TOOL_ID, "symbol": self.symbol, "file": self.file, "new_name": self.new_name, "target": self.target,
                "aliases": self.aliases, "changed_files": self.changed_files, "counts": counts,
                "flagged": [asdict(r) for r in self.refs if not r.changed]}


def _module_name(rel: str) -> str:
    parts = list(Path(rel).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _excluded(rel: str, exclude: Sequence[str]) -> bool:
    name = Path(rel).name
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(name, g) for g in exclude)


def python_files(root: Path, exclude: Sequence[str] = DEFAULT_EXCLUDE) -> list[str]:
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(p in SKIP_DIRS for p in rel.parts) or path.is_symlink() or not path.is_file():
            continue
        if not _excluded(str(rel), exclude):
            out.append(str(rel))
    return out


def _abs_import(module_rel: str, node: cst.ImportFrom) -> str | None:
    try:
        return get_absolute_module_from_package_for_import(_package_of(module_rel), node)
    except Exception:  # noqa: BLE001 - malformed relative import beyond top level
        return None


def _package_of(rel: str) -> str | None:
    mod = _module_name(rel)
    if Path(rel).name == "__init__.py":
        return mod or None
    return mod.rpartition(".")[0] or None


def _dotted(node: cst.BaseExpression) -> str:
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        return f"{_dotted(node.value)}.{node.attr.value}"
    return ""


def _top_level_bindings(module: cst.Module) -> set[str]:
    names: set[str] = set()
    for stmt in module.body:
        if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)):
            names.add(stmt.name.value)
        elif isinstance(stmt, cst.SimpleStatementLine):
            for small in stmt.body:
                if isinstance(small, (cst.Assign, cst.AnnAssign)):
                    targets = [t.target for t in small.targets] if isinstance(small, cst.Assign) else [small.target]
                    names.update(t.value for t in targets if isinstance(t, cst.Name))
                elif isinstance(small, cst.ImportFrom) and not isinstance(small.names, cst.ImportStar):
                    for a in small.names:
                        names.add(a.asname.name.value if a.asname and isinstance(a.asname.name, cst.Name) else _dotted(a.name))
                elif isinstance(small, cst.Import):
                    for a in small.names:
                        names.add(a.asname.name.value if a.asname and isinstance(a.asname.name, cst.Name) else _dotted(a.name).split(".")[0])
    return names


class _Renamer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (FullyQualifiedNameProvider, PositionProvider)

    def __init__(self, rel: str, symbol: str, new: str, targets: set[str], refs: list[Ref], modules: set[str]):
        self.rel, self.symbol, self.new, self.targets, self.refs, self.modules = rel, symbol, new, targets, refs, modules
        self.in_all = False
        self.bound_here = False  # module binds ``symbol`` to the target (def or unaliased import)
        self._attr_names: set[int] = set()

    def _pos(self, node: cst.CSTNode) -> tuple[int, int]:
        p = self.get_metadata(PositionProvider, node).start
        return p.line, p.column

    def _hit(self, node: cst.CSTNode) -> bool:
        names = self.get_metadata(FullyQualifiedNameProvider, node, set()) or set()
        return any(q.name in self.targets for q in names)

    def _add(self, node: cst.CSTNode, kind: str, changed: bool, text: str = "") -> None:
        line, col = self._pos(node)
        self.refs.append(Ref(self.rel, line, col, kind, changed, text[:120]))

    # -- definitions and imports ---------------------------------------------------------------------------------------
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._attr_names.add(id(node.name))

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._attr_names.add(id(node.name))

    def leave_FunctionDef(self, original: cst.FunctionDef, updated: cst.FunctionDef) -> cst.FunctionDef:
        if original.name.value == self.symbol and self._hit(original):
            self.bound_here = True
            self._add(original, "definition", True)
            return updated.with_changes(name=updated.name.with_changes(value=self.new))
        return updated

    def leave_ClassDef(self, original: cst.ClassDef, updated: cst.ClassDef) -> cst.ClassDef:
        if original.name.value == self.symbol and self._hit(original):
            self.bound_here = True
            self._add(original, "definition", True)
            return updated.with_changes(name=updated.name.with_changes(value=self.new))
        return updated

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        mod = _abs_import(self.rel, node)
        if isinstance(node.names, cst.ImportStar) and mod and any(t == f"{mod}.{self.symbol}" for t in self.targets):
            self._add(node, "star_import", False, f"from {mod} import *")

    def leave_ImportAlias(self, original: cst.ImportAlias, updated: cst.ImportAlias) -> cst.ImportAlias:
        parent_mod = getattr(self, "_current_from", None)
        if parent_mod and _dotted(original.name) == self.symbol and f"{parent_mod}.{self.symbol}" in self.targets:
            if original.asname is None:
                self.bound_here = True
            self._add(original, "import", True, f"from {parent_mod} import {self.symbol}")
            return updated.with_changes(name=cst.Name(self.new))
        return updated

    # -- uses ------------------------------------------------------------------------------------------------------
    def visit_Attribute(self, node: cst.Attribute) -> None:
        self._attr_names.add(id(node.attr))

    def leave_Attribute(self, original: cst.Attribute, updated: cst.Attribute) -> cst.BaseExpression:
        if original.attr.value != self.symbol:
            return updated
        if self._hit(original):
            self._add(original, "attribute", True, _dotted(original))
            return updated.with_changes(attr=cst.Name(self.new))
        base = _dotted(original.value)
        self._add(original, "unresolved_attribute", False, (base + "." if base else "?.") + self.symbol)
        return updated

    def leave_Name(self, original: cst.Name, updated: cst.Name) -> cst.Name:
        if original.value != self.symbol or id(original) in self._attr_names:
            return updated
        if self._hit(original):
            self._add(original, "name", True)
            return updated.with_changes(value=self.new)
        return updated

    # -- __all__, strings, comments ------------------------------------------------------------------------------------
    def visit_Assign(self, node: cst.Assign) -> None:
        self.in_all = any(isinstance(t.target, cst.Name) and t.target.value == "__all__" for t in node.targets)

    def leave_Assign(self, original: cst.Assign, updated: cst.Assign) -> cst.Assign:
        self.in_all = False
        return updated

    def visit_AugAssign(self, node: cst.AugAssign) -> None:
        self.in_all = isinstance(node.target, cst.Name) and node.target.value == "__all__"

    def leave_AugAssign(self, original: cst.AugAssign, updated: cst.AugAssign) -> cst.AugAssign:
        self.in_all = False
        return updated

    def leave_SimpleString(self, original: cst.SimpleString, updated: cst.SimpleString) -> cst.SimpleString:
        try:
            value = original.evaluated_value
        except Exception:  # noqa: BLE001
            return updated
        if not isinstance(value, str):
            return updated
        if self.in_all and value == self.symbol:
            self._all_strings.append((original, updated))
            return updated  # decided at module end (only if this module binds the target)
        if re.search(rf"\b{re.escape(self.symbol)}\b", value):
            self._add(original, "string", False, value)
        return updated

    def visit_Module(self, node: cst.Module) -> None:
        self._all_strings: list[tuple[cst.SimpleString, cst.SimpleString]] = []

    def leave_Comment(self, original: cst.Comment, updated: cst.Comment) -> cst.Comment:
        if re.search(rf"\b{re.escape(self.symbol)}\b", original.value):
            self._add(original, "comment", False, original.value)
        return updated

    def leave_Module(self, original: cst.Module, updated: cst.Module) -> cst.Module:
        module_binds_target = self.bound_here or f"{_module_name(self.rel)}.{self.symbol}" in self.targets
        if not self._all_strings:
            return updated
        quote_new = {}
        for orig, _ in self._all_strings:
            q = orig.quote
            quote_new[id(orig)] = f"{orig.prefix}{q}{self.new}{q}"
            self._add(orig, "__all__", module_binds_target, orig.value)
        if not module_binds_target:
            return updated
        wanted = {orig.value for orig, _ in self._all_strings}

        class _AllFix(cst.CSTTransformer):
            def __init__(self, sym: str, new: str):
                self.sym, self.new, self.in_all = sym, new, False

            def visit_Assign(self, node: cst.Assign) -> None:
                self.in_all = any(isinstance(t.target, cst.Name) and t.target.value == "__all__" for t in node.targets)

            def leave_Assign(self, o: cst.Assign, u: cst.Assign) -> cst.Assign:
                self.in_all = False
                return u

            def visit_AugAssign(self, node: cst.AugAssign) -> None:
                self.in_all = isinstance(node.target, cst.Name) and node.target.value == "__all__"

            def leave_AugAssign(self, o: cst.AugAssign, u: cst.AugAssign) -> cst.AugAssign:
                self.in_all = False
                return u

            def leave_SimpleString(self, o: cst.SimpleString, u: cst.SimpleString) -> cst.SimpleString:
                if self.in_all and o.value in wanted:
                    return u.with_changes(value=f"{o.prefix}{o.quote}{self.new}{o.quote}")
                return u

        return updated.visit(_AllFix(self.symbol, self.new))


class _FromTracker(_Renamer):
    """libcst has no visit_<Node>_<field> for ImportFrom.names in every version; track via visit/leave ImportFrom."""

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:  # type: ignore[override]
        super().visit_ImportFrom(node)
        self._current_from = _abs_import(self.rel, node)

    def leave_ImportFrom(self, original: cst.ImportFrom, updated: cst.ImportFrom) -> cst.ImportFrom:
        self._current_from = None
        return updated


def _load(root: Path, files: Sequence[str]) -> tuple[FullRepoManager, dict[str, str]]:
    texts = {rel: (root / rel).read_text(encoding="utf-8") for rel in files}
    return FullRepoManager(str(root), [str(root / f) for f in files], {FullyQualifiedNameProvider, ScopeProvider}), texts


def _target_kind(module: cst.Module, symbol: str) -> str:
    for stmt in module.body:
        if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)) and stmt.name.value == symbol:
            return "function" if isinstance(stmt, cst.FunctionDef) else "class"
        if isinstance(stmt, cst.SimpleStatementLine):
            for small in stmt.body:
                if isinstance(small, cst.Assign) and any(isinstance(t.target, cst.Name) and t.target.value == symbol for t in small.targets):
                    return "variable"
                if isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name) and small.target.value == symbol:
                    return "variable"
    return ""


def _reexport_aliases(root: Path, files: Sequence[str], texts: dict[str, str], target: str, symbol: str) -> list[str]:
    """Modules that bind ``symbol`` by an unaliased ``from X import symbol`` of a target expose ``mod.symbol`` too."""
    targets = {target}
    parsed = {rel: cst.parse_module(texts[rel]) for rel in files}
    changed = True
    while changed:
        changed = False
        for rel, module in parsed.items():
            mod = _module_name(rel)
            for stmt in module.body:
                if not isinstance(stmt, cst.SimpleStatementLine):
                    continue
                for small in stmt.body:
                    if not isinstance(small, cst.ImportFrom) or isinstance(small.names, cst.ImportStar):
                        continue
                    src = _abs_import(rel, small)
                    for a in small.names:
                        if src and _dotted(a.name) == symbol and a.asname is None and f"{src}.{symbol}" in targets \
                                and f"{mod}.{symbol}" not in targets:
                            targets.add(f"{mod}.{symbol}")
                            changed = True
    return sorted(targets - {target})


def plan_rename(root: str | Path, file: str, symbol: str, new_name: str, *,
                exclude: Sequence[str] = DEFAULT_EXCLUDE) -> RenamePlan:
    root = Path(root).resolve()
    rel = str(Path(file))
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise RenameError("file must be repo-relative")
    if not symbol.isidentifier() or keyword.iskeyword(symbol):
        raise RenameError("symbol must be an identifier")
    if not new_name.isidentifier() or keyword.iskeyword(new_name) or new_name == symbol:
        raise RenameError("new_name must be a different, non-keyword identifier")
    if not (root / rel).is_file():
        raise RenameError(f"no such file: {rel}")
    files = python_files(root, exclude)
    if rel not in files:
        raise RenameError("file is excluded or not a regular .py file")
    try:
        manager, texts = _load(root, files)
        defining = cst.parse_module(texts[rel])
    except cst.ParserSyntaxError as exc:
        raise RenameError(f"parse_error:{exc.message}") from exc
    if not _target_kind(defining, symbol):
        raise RenameError(f"{symbol!r} is not a top-level def/class/assignment in {rel}")
    target = f"{_module_name(rel)}.{symbol}"
    aliases = _reexport_aliases(root, files, texts, target, symbol)
    plan = RenamePlan(symbol=symbol, file=rel, new_name=new_name, target=target, aliases=aliases)
    targets = {target, *aliases}
    for path in files:
        wrapper = manager.get_metadata_wrapper_for_path(str(root / path))
        renamer = _FromTracker(path, symbol, new_name, targets, plan.refs, set())
        new_module = wrapper.visit(renamer)
        plan.old_text[path] = texts[path]
        plan.new_text[path] = new_module.code
        if plan.new_text[path] != texts[path] and (renamer.bound_here or path == rel) \
                and new_name in _top_level_bindings(wrapper.module):
            raise RenameError(f"conflict: {new_name!r} is already bound at module level in {path}")
    for path in plan.changed_files:
        try:
            compile(plan.new_text[path], path, "exec")
        except SyntaxError as exc:  # pragma: no cover - libcst round-trips
            raise RenameError(f"post_rename_syntax_error:{path}:{exc.msg}") from exc
    if not plan.changed_files:
        raise RenameError("no references found")
    return plan


def remaining_references(root: Path, plan: RenamePlan, *, exclude: Sequence[str] = DEFAULT_EXCLUDE) -> list[dict[str, Any]]:
    """Re-scan an applied (or simulated) tree: resolved references to the old target must be zero."""
    root = Path(root).resolve()
    files = python_files(root, exclude)
    manager, _ = _load(root, files)
    left = []
    targets = {plan.target, *plan.aliases}
    for path in files:
        wrapper = manager.get_metadata_wrapper_for_path(str(root / path))
        fq = wrapper.resolve(FullyQualifiedNameProvider)
        pos = wrapper.resolve(PositionProvider)
        for node, names in fq.items():
            if isinstance(node, (cst.Name, cst.Attribute, cst.FunctionDef, cst.ClassDef)) and any(q.name in targets for q in names):
                label = node.value if isinstance(node, cst.Name) else (node.attr.value if isinstance(node, cst.Attribute) else node.name.value)
                if label == plan.symbol:
                    left.append({"path": path, "line": pos[node].start.line, "node": type(node).__name__})
    return left


def apply_rename(root: str | Path, plan: RenamePlan, *, verify_remaining: bool = True,
                 exclude: Sequence[str] = DEFAULT_EXCLUDE) -> dict[str, Any]:
    """Atomically write the plan (all files or none); re-scan; roll back if any resolved reference remains."""
    root = Path(root).resolve()
    for path in plan.changed_files:
        if (root / path).read_text(encoding="utf-8") != plan.old_text[path]:
            raise RenameError(f"stale_plan: {path} changed since planning")
    staged: list[tuple[Path, Path]] = []
    try:
        for path in plan.changed_files:
            dest = root / path
            fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".rename", dir=dest.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(plan.new_text[path])
            os.chmod(tmp, dest.stat().st_mode & 0o777)
            staged.append((Path(tmp), dest))
        for tmp, dest in staged:
            os.replace(tmp, dest)
    except BaseException:
        for tmp, dest in staged:
            if tmp.exists():
                tmp.unlink()
        for path in plan.changed_files:
            (root / path).write_text(plan.old_text[path], encoding="utf-8")
        raise
    left = remaining_references(root, plan, exclude=exclude) if verify_remaining else []
    if left:
        for path in plan.changed_files:
            (root / path).write_text(plan.old_text[path], encoding="utf-8")
        raise RenameError(f"rolled_back: {len(left)} resolved reference(s) remained")
    return {**plan.summary(), "applied": True, "remaining_references": 0}


def rename_symbol(root: str | Path, file: str, symbol: str, new_name: str, *, dry_run: bool = False,
                  exclude: Sequence[str] = DEFAULT_EXCLUDE) -> dict[str, Any]:
    plan = plan_rename(root, file, symbol, new_name, exclude=exclude)
    if dry_run:
        return {**plan.summary(), "applied": False, "diff": plan.diff()}
    out = apply_rename(root, plan, exclude=exclude)
    out["diff"] = plan.diff()
    return out


def find_symbol(root: str | Path, symbol: str, *, exclude: Sequence[str] = DEFAULT_EXCLUDE) -> list[str]:
    """Files that define ``symbol`` at top level (helps the model/operator pick ``file``)."""
    root = Path(root)
    hits = []
    for rel in python_files(root, exclude):
        try:
            if _target_kind(cst.parse_module((root / rel).read_text(encoding="utf-8")), symbol):
                hits.append(rel)
        except cst.ParserSyntaxError:
            continue
    return hits


def _rebase_edit(edit: dict[str, Any], renames: Sequence[tuple[str, str]]) -> dict[str, Any] | None:
    """Rewrite an edit written against pre-rename names onto the renamed tree; drop pure-rename edits."""
    old, new = str(edit.get("old_text", "")), str(edit.get("new_text", ""))
    for sym, repl in renames:
        old = re.sub(rf"\b{re.escape(sym)}\b", repl, old)
        new = re.sub(rf"\b{re.escape(sym)}\b", repl, new)
    if old == new:
        return None  # the edit only performed a rename the tool already did
    return {**edit, "old_text": old, "new_text": new}


def apply_action(root: str | Path, action: dict[str, Any], *, exclude: Sequence[str] = ("test_*.py",),
                 apply_edits=None) -> dict[str, Any]:
    """Governed-path actuator: model-chosen ``renames`` (tool does every reference) + optional exact ``edits``.

    Order: deterministic renames first, then the exact edits. Edits may be written against either the original or the
    new names: an edit whose old_text no longer matches is rebased onto the renamed tree (old name -> new name inside
    old_text/new_text, applied only to the edit text); edits that merely repeat a rename are dropped. Raises
    RenameError on refusal; the caller works on a disposable copy.
    """
    root = Path(root)
    renames = list(action.get("renames") or [])
    edits = [dict(e) for e in (action.get("edits") or []) if isinstance(e, dict)]
    if not renames and not edits:
        raise RenameError("empty_action")
    for e in edits:
        if _excluded(str(e.get("path", "")), exclude):
            raise RenameError("edit_touches_excluded_file")
    changed: set[str] = set()
    results, done = [], []
    for r in renames:
        if not isinstance(r, dict):
            raise RenameError("malformed_rename")
        file = str(r.get("file") or "")
        symbol, new = str(r.get("symbol") or ""), str(r.get("new_name") or "")
        if not file or not (root / file).is_file() or not _target_kind(cst.parse_module((root / file).read_text(encoding="utf-8")), symbol):
            found = find_symbol(root, symbol, exclude=exclude)
            if len(found) != 1:
                raise RenameError(f"cannot locate unique top-level definition of {symbol!r}")
            file = found[0]
        res = rename_symbol(root, file, symbol, new, exclude=exclude)
        changed.update(res["changed_files"])
        results.append({k: v for k, v in res.items() if k != "diff"})
        done.append((symbol, new))
    if edits:
        if apply_edits is None:
            raise RenameError("edits need an apply_edits actuator")
        rebased = []
        for e in edits:
            path = root / str(e.get("path", ""))
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if done and str(e.get("old_text", "")).rstrip("\n") and text.count(str(e["old_text"]).rstrip("\n")) != 1:
                e = _rebase_edit(e, done)
                if e is None:
                    continue
            elif done:
                r2 = _rebase_edit(e, done)
                if r2 is None:
                    continue
            rebased.append(e)
        if rebased:
            changed.update(apply_edits(root, rebased))
    return {"tool": TOOL_ID, "renames": results, "changed": sorted(changed)}


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="beast rename", description=__doc__.splitlines()[0])
    ap.add_argument("symbol")
    ap.add_argument("new_name")
    ap.add_argument("--file", default="", help="defining file (repo-relative); auto-detected if unique")
    ap.add_argument("--root", default=".")
    ap.add_argument("--exclude", action="append", default=[], help="glob(s) to skip, e.g. 'test_*.py'")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run, print diff)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(list(argv) if argv is not None else None)
    root = Path(a.root)
    file = a.file
    try:
        if not file:
            found = find_symbol(root, a.symbol, exclude=a.exclude)
            if len(found) != 1:
                raise RenameError(f"definition of {a.symbol!r} found in {found or 'no files'}; pass --file")
            file = found[0]
        res = rename_symbol(root, file, a.symbol, a.new_name, dry_run=not a.apply, exclude=a.exclude)
    except RenameError as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}) if a.json else f"refused: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(res["diff"], end="")
        print(json.dumps({k: v for k, v in res.items() if k not in {"diff", "flagged"}}), file=sys.stderr)
        for f in res["flagged"]:
            print(f"flagged {f['kind']}: {f['path']}:{f['line']} {f['text']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
