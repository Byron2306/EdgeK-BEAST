"""Recovery Phase 4 repository perception for durable AgentRuns.

Code Cortex owns repository context discovery. The structural workspace index
adds deterministic fallback evidence, and the Sensorium invalidation bus adds
current workspace-change state. None of these observations become mutation
authority: existing source must still be read exactly through workspace.read_range
before mutation.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

from app.kernel.data_processing.code_cortex import CodeCortexRouter
from app.kernel.sensorium.workspace_invalidation import WorkspaceInvalidationBus


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "change",
    "code", "cross", "file", "files", "fix", "for", "from", "in", "into",
    "is", "it", "make", "of", "on", "or", "repair", "repository", "so",
    "that", "the", "this", "to", "use", "with", "without",
}

_SENSORIUM = WorkspaceInvalidationBus(max_files=5000, max_bytes=512 * 1024)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value or "").strip().replace("\\", "/")
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _query_terms(text: str, *, limit: int = 12) -> list[str]:
    values: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{2,}", str(text or "")):
        lowered = token.lower().strip(".-_")
        if not lowered or lowered in _STOPWORDS:
            continue
        values.append(token)
    values = sorted(
        _dedupe(values),
        key=lambda item: (
            0 if ("_" in item or "." in item or any(ch.isupper() for ch in item)) else 1,
            -len(item),
            item.lower(),
        ),
    )
    return values[:limit]


def _candidate_path(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("path") or item.get("file") or item.get("source") or "").strip()
    return str(item or "").strip()


def _index_candidates(
    structural_index: dict[str, Any],
    terms: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    wanted = [term.lower() for term in terms]

    def bump(path: str, score: int, reason: str, detail: str = "") -> None:
        path = str(path or "").strip()
        if not path:
            return
        row = scores.setdefault(path, {"path": path, "score": 0, "reasons": [], "source": "workspace_index"})
        row["score"] += int(score)
        if reason not in row["reasons"]:
            row["reasons"].append(reason)
        if detail and not row.get("detail"):
            row["detail"] = detail[:240]

    for row in structural_index.get("files") or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        lower = path.lower()
        matched = [term for term in wanted if term in lower]
        if matched:
            bump(path, 4 + len(matched), "path_match", ",".join(matched[:4]))

    for row in structural_index.get("symbols") or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or row.get("file") or "")
        name = str(row.get("name") or "")
        haystack = f"{name} {path}".lower()
        matched = [term for term in wanted if term in haystack]
        if matched:
            bump(path, 8 + 2 * len(matched), "symbol_match", name)

    for row in structural_index.get("imports") or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        target = str(row.get("target") or row.get("module") or "")
        haystack = f"{target} {path}".lower()
        matched = [term for term in wanted if term in haystack]
        if matched:
            bump(path, 5 + len(matched), "import_match", target)

    return sorted(
        scores.values(),
        key=lambda row: (-int(row.get("score") or 0), str(row.get("path") or "")),
    )[:limit]


class RepositoryPerception:
    """Compose canonical read-only repository discovery evidence."""

    def __init__(self, *, code_cortex: CodeCortexRouter | None = None) -> None:
        self.code_cortex = code_cortex or CodeCortexRouter()

    def discover(
        self,
        *,
        root: str | Path,
        objective: str,
        structural_index: dict[str, Any],
        seed_files: Iterable[str] = (),
        limit: int = 16,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        workspace = Path(root).expanduser().resolve()
        limit = max(4, min(int(limit), 40))
        terms = _query_terms(objective)
        cortex_receipts: list[dict[str, Any]] = []
        candidate_rows: dict[str, dict[str, Any]] = {}
        symbols: list[dict[str, Any]] = []

        def add_candidate(path: str, *, score: int, source: str, reason: str, detail: str = "") -> None:
            path = str(path or "").strip()
            if not path:
                return
            row = candidate_rows.setdefault(
                path,
                {"path": path, "score": 0, "sources": [], "reasons": [], "detail": ""},
            )
            row["score"] += int(score)
            if source not in row["sources"]:
                row["sources"].append(source)
            if reason not in row["reasons"]:
                row["reasons"].append(reason)
            if detail and not row["detail"]:
                row["detail"] = str(detail)[:240]

        for path in _dedupe(seed_files):
            add_candidate(path, score=20, source="operator_hint", reason="seed_file")

        try:
            context = self.code_cortex.get_editing_context(workspace, objective, limit=limit)
        except Exception as exc:
            context = {"ok": False, "error": str(exc), "adapter": "unavailable"}
        receipt = context.get("receipt") if isinstance(context.get("receipt"), dict) else {}
        if receipt:
            cortex_receipts.append(dict(receipt))
        for item in context.get("files") or []:
            path = _candidate_path(item)
            if path:
                add_candidate(path, score=10, source="code_cortex", reason="editing_context")
        for item in context.get("symbols") or []:
            if not isinstance(item, dict):
                continue
            symbols.append(dict(item))
            path = _candidate_path(item)
            if path:
                add_candidate(
                    path,
                    score=14,
                    source="code_cortex",
                    reason="symbol_context",
                    detail=str(item.get("name") or ""),
                )

        for term_index, term in enumerate(terms[:8]):
            try:
                found = self.code_cortex.search_symbols(workspace, term, limit=max(4, min(limit, 12)))
            except Exception:
                continue
            receipt = found.get("receipt") if isinstance(found.get("receipt"), dict) else {}
            if receipt:
                cortex_receipts.append(dict(receipt))
            for item in found.get("results") or []:
                if not isinstance(item, dict):
                    continue
                symbols.append(dict(item))
                path = _candidate_path(item)
                if path:
                    add_candidate(
                        path,
                        score=24 + max(0, 7 - term_index) * 3,
                        source="code_cortex",
                        reason=f"symbol_search:{term}",
                        detail=str(item.get("name") or term),
                    )

        for row in _index_candidates(structural_index, terms, limit=limit):
            add_candidate(
                str(row.get("path") or ""),
                score=int(row.get("score") or 0),
                source="workspace_index",
                reason=",".join(row.get("reasons") or ["structural_match"]),
                detail=str(row.get("detail") or ""),
            )

        dependent_rows: list[dict[str, Any]] = []
        ranked_seed = sorted(
            candidate_rows.values(),
            key=lambda row: (-int(row.get("score") or 0), str(row.get("path") or "")),
        )[:6]
        for row in ranked_seed:
            path = str(row.get("path") or "")
            try:
                found = self.code_cortex.get_dependents(workspace, path, limit=12)
            except Exception:
                continue
            receipt = found.get("receipt") if isinstance(found.get("receipt"), dict) else {}
            if receipt:
                cortex_receipts.append(dict(receipt))
            if found.get("results"):
                add_candidate(path, score=6, source="code_cortex", reason="has_dependents")
            for item in found.get("results") or []:
                if not isinstance(item, dict):
                    continue
                dep_path = _candidate_path(item)
                if not dep_path:
                    continue
                dependent_rows.append({
                    "source_path": path,
                    "path": dep_path,
                    "matched_imports": item.get("matched_imports") or [],
                })
                is_test = bool(re.search(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_|.*_test|.*\.(?:spec|test))\.", dep_path, flags=re.I))
                add_candidate(
                    dep_path,
                    score=3 if is_test else 8,
                    source="code_cortex",
                    reason=f"dependent_of:{path}",
                )

        sensorium_changes = []
        for change in _SENSORIUM.poll(workspace):
            try:
                rel = Path(change.path).resolve().relative_to(workspace).as_posix()
            except Exception:
                rel = str(change.path)
            sensorium_changes.append({
                "path": rel,
                "kind": change.kind,
                "digest": change.digest,
                "source": change.source,
                "occurred_at": change.occurred_at,
            })
            add_candidate(rel, score=4, source="sensorium", reason=f"workspace_{change.kind}")

        objective_lower = str(objective or "").lower()
        test_focused = any(term in objective_lower for term in ("test", "pytest", "spec", "assertion"))
        if not test_focused:
            for row in candidate_rows.values():
                path = str(row.get("path") or "")
                if re.search(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_|.*_test|.*\.(?:spec|test))\.", path, flags=re.I):
                    row["score"] = int(row.get("score") or 0) - 18
                    row["reasons"].append("non_test_objective_penalty")

        candidates = sorted(
            candidate_rows.values(),
            key=lambda row: (-int(row.get("score") or 0), str(row.get("path") or "")),
        )[:limit]

        body = {
            "beast_object_type": "beast_repository_perception",
            "version": "1.0",
            "objective": str(objective or ""),
            "query_terms": terms,
            "authority": "advisory_discovery_only",
            "exact_source_required_before_mutation": True,
            "code_cortex": {
                "owner": "Code Cortex",
                "active_adapter": self.code_cortex.status(workspace).get("active_adapter"),
                "receipts": cortex_receipts[:24],
            },
            "structural_index": {
                "index_digest": structural_index.get("index_digest"),
                "summary": structural_index.get("summary") or {},
                "truncated": bool(structural_index.get("truncated")),
            },
            "sensorium": {
                "owner": "WorkspaceInvalidationBus",
                "change_count": len(sensorium_changes),
                "changes": sensorium_changes[:20],
                "baseline_or_current": "current",
            },
            "candidates": candidates,
            "candidate_paths": [str(row.get("path") or "") for row in candidates],
            "symbols": symbols[:24],
            "dependents": dependent_rows[:24],
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        body["perception_digest"] = f"sha256:{digest}"
        body["duration_ms"] = max(0, int((time.perf_counter() - started) * 1000))
        return body
