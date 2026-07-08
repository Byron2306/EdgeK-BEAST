"""BEAST Code Cortex adapters.

This module normalizes local and optional external code-intelligence engines
behind a read-oriented adapter contract. Adapters may propose edit intent, but
they never write files; BEAST SourcePlan remains the mutation path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.compute.action_ir import ACTION_IR_KIND
from app.kernel.data_processing.code_indexers import (
    SOURCE_SUFFIXES,
    extract_imports,
    extract_routes,
    extract_symbols,
    file_metadata,
    language_for_path,
)


SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", "dist", "build", ".next", ".cache", ".tox", "data", "logs",
    "tmp", "temp", ".idea",
}


@dataclass(frozen=True)
class CodeCortexReceipt:
    adapter: str
    method: str
    ok: bool
    latency_ms: float
    fallback_used: bool = False
    command: List[str] | None = None
    error: str = ""
    result_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "code_cortex_adapter_receipt",
            "version": "1.0",
            "adapter": self.adapter,
            "method": self.method,
            "ok": self.ok,
            "latency_ms": round(float(self.latency_ms or 0.0), 3),
            "fallback_used": bool(self.fallback_used),
            "command": list(self.command or []),
            "error": self.error,
            "result_count": int(self.result_count or 0),
        }


class CodeCortexAdapter:
    adapter_id = "base"

    def available(self) -> bool:
        return False

    def status(self, root: Path) -> Dict[str, Any]:
        return {"adapter": self.adapter_id, "available": self.available()}

    def search_symbols(self, root: Path, query: str, limit: int = 20) -> Dict[str, Any]:
        return self._empty("search_symbols")

    def get_file_summary(self, root: Path, path: str) -> Dict[str, Any]:
        return self._empty("get_file_summary")

    def get_dependents(self, root: Path, path: str, limit: int = 80) -> Dict[str, Any]:
        return self._empty("get_dependents")

    def get_editing_context(self, root: Path, query: str, limit: int = 12) -> Dict[str, Any]:
        return self._empty("get_editing_context")

    def propose_symbol_edit(self, root: Path, path: str, symbol: str, replacement: str) -> Dict[str, Any]:
        return self._empty("propose_symbol_edit")

    def _empty(self, method: str) -> Dict[str, Any]:
        receipt = CodeCortexReceipt(self.adapter_id, method, False, 0.0, error="adapter unavailable")
        return {"ok": False, "adapter": self.adapter_id, "receipt": receipt.to_dict(), "results": []}


def _safe_path(root: Path, rel: str) -> Path:
    rel_path = Path(str(rel))
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"unsafe path: {rel}")
    target = (root / rel_path).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"path escaped workspace: {rel}")
    return target


def _iter_source_files(root: Path, limit: int = 1500) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        try:
            rel_parts = path.relative_to(root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if path.stat().st_size > 240_000:
                continue
            yield path
            count += 1
            if limit and count >= limit:
                return
        except Exception:
            continue


def _module_names_for_path(rel_path: str) -> List[str]:
    path = Path(rel_path)
    stem_path = path.with_suffix("")
    dotted = ".".join(part for part in stem_path.parts if part)
    names = [dotted]
    if path.stem:
        names.append(path.stem)
    if path.parent != Path("."):
        names.append(".".join(part for part in path.parent.parts if part))
    return [name for name in dict.fromkeys(names) if name]


def _import_matches(module: str, module_names: Iterable[str]) -> bool:
    normalized = str(module or "").strip().strip(".")
    if not normalized:
        return False
    for name in module_names:
        if normalized == name or normalized.startswith(f"{name}.") or name.startswith(f"{normalized}."):
            return True
    return False


class LocalCodeCortexAdapter(CodeCortexAdapter):
    adapter_id = "local_code_cortex"

    def available(self) -> bool:
        return True

    def status(self, root: Path) -> Dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "available": True,
            "workspace": str(root),
            "capabilities": [
                "search_symbols",
                "get_file_summary",
                "get_dependents",
                "get_editing_context",
                "propose_symbol_edit",
            ],
        }

    def search_symbols(self, root: Path, query: str, limit: int = 20) -> Dict[str, Any]:
        started = time.perf_counter()
        wanted = str(query or "").strip().lower()
        results: List[Dict[str, Any]] = []
        for path in _iter_source_files(root):
            try:
                rel = path.relative_to(root).as_posix()
                text = path.read_text(encoding="utf-8", errors="replace")
                language = language_for_path(path)
                for item in extract_symbols(text, language, rel):
                    haystack = f"{item.get('name')} {item.get('kind')} {rel}".lower()
                    if not wanted or wanted in haystack:
                        results.append({**item, "adapter": self.adapter_id, "language": language})
                    if len(results) >= limit:
                        break
            except Exception:
                continue
            if len(results) >= limit:
                break
        receipt = CodeCortexReceipt(self.adapter_id, "search_symbols", True, (time.perf_counter() - started) * 1000, result_count=len(results))
        return {"ok": True, "adapter": self.adapter_id, "query": query, "results": results, "receipt": receipt.to_dict()}

    def get_file_summary(self, root: Path, path: str) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            target = _safe_path(root, path)
            text = target.read_text(encoding="utf-8", errors="replace")
            rel = target.relative_to(root).as_posix()
            language = language_for_path(target)
            data = {
                **file_metadata(target, root, text),
                "symbols": extract_symbols(text, language, rel),
                "imports": extract_imports(text, language, rel),
                "routes": extract_routes(text, language, rel),
            }
            receipt = CodeCortexReceipt(self.adapter_id, "get_file_summary", True, (time.perf_counter() - started) * 1000, result_count=1)
            return {"ok": True, "adapter": self.adapter_id, "summary": data, "receipt": receipt.to_dict()}
        except Exception as exc:
            receipt = CodeCortexReceipt(self.adapter_id, "get_file_summary", False, (time.perf_counter() - started) * 1000, error=str(exc))
            return {"ok": False, "adapter": self.adapter_id, "error": str(exc), "receipt": receipt.to_dict()}

    def get_dependents(self, root: Path, path: str, limit: int = 80) -> Dict[str, Any]:
        started = time.perf_counter()
        modules = _module_names_for_path(path)
        results: List[Dict[str, Any]] = []
        for candidate in _iter_source_files(root):
            try:
                rel = candidate.relative_to(root).as_posix()
                if rel == path:
                    continue
                text = candidate.read_text(encoding="utf-8", errors="replace")
                language = language_for_path(candidate)
                imports = extract_imports(text, language, rel)
                matched = [
                    item for item in imports
                    if _import_matches(str(item.get("module") or item.get("name") or ""), modules)
                ]
                if matched:
                    results.append({"path": rel, "language": language, "matched_imports": matched, "adapter": self.adapter_id})
                if len(results) >= limit:
                    break
            except Exception:
                continue
        receipt = CodeCortexReceipt(self.adapter_id, "get_dependents", True, (time.perf_counter() - started) * 1000, result_count=len(results))
        return {"ok": True, "adapter": self.adapter_id, "path": path, "module_names": modules, "results": results, "receipt": receipt.to_dict()}

    def get_editing_context(self, root: Path, query: str, limit: int = 12) -> Dict[str, Any]:
        started = time.perf_counter()
        symbols = self.search_symbols(root, query, limit=limit).get("results") or []
        file_matches: List[Dict[str, Any]] = []
        wanted = str(query or "").strip().lower()
        for path in _iter_source_files(root):
            if len(file_matches) >= limit:
                break
            try:
                rel = path.relative_to(root).as_posix()
                text = path.read_text(encoding="utf-8", errors="replace")
                if wanted and wanted not in rel.lower() and wanted not in text[:8000].lower():
                    continue
                file_matches.append({
                    "path": rel,
                    "language": language_for_path(path),
                    "preview": text[:1200],
                    "adapter": self.adapter_id,
                })
            except Exception:
                continue
        receipt = CodeCortexReceipt(self.adapter_id, "get_editing_context", True, (time.perf_counter() - started) * 1000, result_count=len(symbols) + len(file_matches))
        return {
            "ok": True,
            "adapter": self.adapter_id,
            "query": query,
            "symbols": symbols,
            "files": file_matches,
            "receipt": receipt.to_dict(),
        }

    def propose_symbol_edit(self, root: Path, path: str, symbol: str, replacement: str) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            target = _safe_path(root, path)
            current = target.read_text(encoding="utf-8", errors="replace")
            rel = target.relative_to(root).as_posix()
            language = language_for_path(target)
            matches = [
                item for item in extract_symbols(current, language, rel)
                if str(item.get("name") or "") == str(symbol or "")
            ]
            if len(matches) != 1:
                raise ValueError(f"symbol match count for {symbol!r} in {rel}: {len(matches)}")
            match = matches[0]
            start = max(1, int(match.get("line") or 1))
            end = max(start, int(match.get("end_line") or start))
            lines = current.splitlines(keepends=True)
            old = "".join(lines[start - 1:end])
            new = str(replacement or "")
            if old.endswith("\n") and not new.endswith("\n"):
                new += "\n"
            proposal = {
                "kind": ACTION_IR_KIND,
                "objective": f"Modify symbol {symbol}",
                "actions": [{
                    "id": "symbol_001",
                    "type": "modify_symbol",
                    "target": {"path": rel, "symbol": symbol},
                    "intent": f"Replace symbol block for {symbol}",
                    "old": old,
                    "new": new,
                    "parameters": {
                        "adapter": self.adapter_id,
                        "line": start,
                        "end_line": end,
                        "language": language,
                    },
                }],
            }
            receipt = CodeCortexReceipt(self.adapter_id, "propose_symbol_edit", True, (time.perf_counter() - started) * 1000, result_count=1)
            return {
                "ok": True,
                "adapter": self.adapter_id,
                "path": rel,
                "symbol": symbol,
                "language": language,
                "old": old,
                "new": new,
                "proposal": proposal,
                "receipt": receipt.to_dict(),
            }
        except Exception as exc:
            receipt = CodeCortexReceipt(self.adapter_id, "propose_symbol_edit", False, (time.perf_counter() - started) * 1000, error=str(exc))
            return {"ok": False, "adapter": self.adapter_id, "error": str(exc), "receipt": receipt.to_dict()}


class GortexAdapter(CodeCortexAdapter):
    adapter_id = "gortex"
    _health_cache: Dict[str, tuple[float, bool]] = {}

    def __init__(self, binary: Optional[str] = None, timeout: float = 4.0):
        local_bin = Path.home() / ".local" / "bin" / "gortex"
        self.binary = (
            binary
            or os.environ.get("BEAST_GORTEX_BIN")
            or shutil.which("gortex")
            or (str(local_bin) if local_bin.exists() else None)
        )
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.binary) and os.environ.get("BEAST_GORTEX_DISABLE", "").lower() not in {"1", "true", "yes"}

    def healthy(self, root: Path) -> bool:
        if not self.available():
            return False
        key = f"{self.binary}:{root.resolve()}"
        now = time.monotonic()
        cached = self._health_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        result = self._run(["status"], "status", parse_json=False, timeout=0.8)
        text = str(result.get("text") or (result.get("data") or {}).get("text") or "")
        ok = bool(result.get("ok")) and str(root.resolve()) in text
        self._health_cache[key] = (now + 15.0, ok)
        return ok

    def status(self, root: Path) -> Dict[str, Any]:
        if not self.available():
            return {"adapter": self.adapter_id, "available": False, "reason": "gortex binary not found"}
        result = self._run(["status"], "status", parse_json=False, timeout=1.0)
        text = str(result.get("text") or (result.get("data") or {}).get("text") or "")
        result["data"] = {"text": text}
        tracked = str(root) in text or str(root.resolve()) in text
        return {**result, "available": bool(result.get("ok")), "binary": self.binary, "tracked": tracked}

    def search_symbols(self, root: Path, query: str, limit: int = 20) -> Dict[str, Any]:
        return self._run([
            "query", "symbol", str(query or ""),
            "--index", str(root),
            "--format", "json",
            "--limit", str(limit),
        ], "search_symbols")

    def get_file_summary(self, root: Path, path: str) -> Dict[str, Any]:
        result = self.get_editing_context(root, path, limit=1)
        receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
        receipt["method"] = "get_file_summary"
        result["receipt"] = receipt
        if result.get("ok"):
            result["summary"] = {
                "file": result.get("file"),
                "defines": result.get("defines") or [],
                "imports": result.get("imports") or [],
                "calls": result.get("calls") or [],
                "called_by": result.get("called_by") or [],
                "etag": result.get("etag"),
            }
        return result

    def get_dependents(self, root: Path, path: str, limit: int = 80) -> Dict[str, Any]:
        return self._run([
            "query", "dependents", str(path or ""),
            "--index", str(root),
            "--format", "json",
            "--limit", str(limit),
        ], "get_dependents")

    def get_editing_context(self, root: Path, query: str, limit: int = 12) -> Dict[str, Any]:
        args = [
            "edit", "context", str(query or ""),
            "--index", str(root),
            "--format", "json",
            "--detail", "brief",
        ]
        return self._run(args, "get_editing_context")

    def _run(self, args: List[str], method: str, parse_json: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
        started = time.perf_counter()
        if not self.available():
            receipt = CodeCortexReceipt(self.adapter_id, method, False, 0.0, error="gortex binary not found")
            return {"ok": False, "adapter": self.adapter_id, "error": receipt.error, "receipt": receipt.to_dict()}
        command = [str(self.binary), *args]
        try:
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout if timeout is None else timeout,
                check=False,
            )
            raw = process.stdout.strip()
            if parse_json:
                data = json.loads(raw) if raw else {}
            else:
                data = {"text": raw}
            ok = process.returncode == 0
            result_count = 0
            if isinstance(data, dict):
                for key in ("results", "symbols", "files", "dependents", "context", "defines", "calls", "called_by"):
                    value = data.get(key)
                    if isinstance(value, list):
                        result_count = max(result_count, len(value))
            receipt = CodeCortexReceipt(
                self.adapter_id,
                method,
                ok,
                (time.perf_counter() - started) * 1000,
                command=command,
                error="" if ok else (process.stderr.strip() or f"exit {process.returncode}"),
                result_count=result_count,
            )
            if isinstance(data, dict):
                return {**data, "ok": ok, "adapter": self.adapter_id, "receipt": receipt.to_dict()}
            return {"ok": ok, "adapter": self.adapter_id, "data": data, "receipt": receipt.to_dict()}
        except Exception as exc:
            receipt = CodeCortexReceipt(self.adapter_id, method, False, (time.perf_counter() - started) * 1000, command=command, error=str(exc))
            return {"ok": False, "adapter": self.adapter_id, "error": str(exc), "receipt": receipt.to_dict()}


class CodeCortexRouter:
    """Route Code Cortex reads through optional adapters with local fallback."""

    def __init__(self, adapters: Optional[List[CodeCortexAdapter]] = None):
        self.local = LocalCodeCortexAdapter()
        self.adapters = adapters if adapters is not None else [GortexAdapter(), self.local]

    def status(self, root: Path) -> Dict[str, Any]:
        rows = [adapter.status(root) for adapter in self.adapters]
        return {
            "beast_object_type": "code_cortex_status",
            "version": "1.0",
            "workspace": str(root),
            "adapters": rows,
            "active_adapter": self._first_available(root).adapter_id,
        }

    def _first_available(self, root: Optional[Path] = None) -> CodeCortexAdapter:
        for adapter in self.adapters:
            if isinstance(adapter, GortexAdapter) and root is not None:
                if adapter.healthy(root):
                    return adapter
                continue
            if adapter.available():
                return adapter
        return self.local

    def _skipped_external_adapters(self, root: Path) -> List[str]:
        skipped: List[str] = []
        for adapter in self.adapters:
            if isinstance(adapter, GortexAdapter) and adapter.available() and not adapter.healthy(root):
                skipped.append(adapter.adapter_id)
        return skipped

    def _with_fallback(self, method: str, root: Path, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        primary = self._first_available(root)
        result = getattr(primary, method)(root, *args, **kwargs)
        if result.get("ok") or primary.adapter_id == self.local.adapter_id:
            if primary.adapter_id == self.local.adapter_id:
                skipped = self._skipped_external_adapters(root)
                if skipped:
                    receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
                    receipt["fallback_used"] = True
                    result["receipt"] = receipt
                    result["fallback_from"] = ",".join(skipped)
            return result
        fallback = getattr(self.local, method)(root, *args, **kwargs)
        receipt = fallback.get("receipt") if isinstance(fallback.get("receipt"), dict) else {}
        receipt["fallback_used"] = True
        fallback["receipt"] = receipt
        fallback["fallback_from"] = primary.adapter_id
        return fallback

    def search_symbols(self, root: Path, query: str, limit: int = 20) -> Dict[str, Any]:
        return self._with_fallback("search_symbols", root, query, limit=limit)

    def get_file_summary(self, root: Path, path: str) -> Dict[str, Any]:
        return self._with_fallback("get_file_summary", root, path)

    def get_dependents(self, root: Path, path: str, limit: int = 80) -> Dict[str, Any]:
        return self._with_fallback("get_dependents", root, path, limit=limit)

    def get_editing_context(self, root: Path, query: str, limit: int = 12) -> Dict[str, Any]:
        return self._with_fallback("get_editing_context", root, query, limit=limit)

    def propose_symbol_edit(self, root: Path, path: str, symbol: str, replacement: str) -> Dict[str, Any]:
        # Symbol edit proposals must be locally resolvable for hash/line safety.
        return self.local.propose_symbol_edit(root, path, symbol, replacement)
