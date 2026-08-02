"""Deterministic first-stage filtering and explainable evidence ranking.

Retrieval produces candidates only. It never grants compatibility or reuse authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.kernel.evidence.evidence_digest import sha256_digest
from app.kernel.evidence.evidence_ledger import EvidenceLedger
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.evidence.fingerprint_store import FingerprintStore

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]*")
_LANGUAGE_BY_SUFFIX = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".rs": "rust",
    ".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "csharp",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _tokens(value: Any) -> set[str]:
    return {item.lower() for item in _TOKEN.findall(str(value or "")) if len(item) > 1}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _path_languages(paths: list[str]) -> set[str]:
    return {_LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower(), "") for path in paths} - {""}


def _frameworks(environment: dict[str, Any]) -> set[str]:
    names = {str(item.get("path") or "") for item in environment.get("dependencies") or []}
    values: set[str] = set()
    if {"pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock"} & names:
        values.add("python")
    if {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"} & names:
        values.add("node")
    if {"Cargo.toml", "Cargo.lock"} & names:
        values.add("rust")
    if {"go.mod", "go.sum"} & names:
        values.add("go")
    return values


def _candidate_document(evidence: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    task = (bundle.get("task") or {}).get("components") or {}
    environment = (bundle.get("environment") or {}).get("components") or {}
    paths = [str(value) for value in task.get("affected_paths") or []]
    symbols: set[str] = set()
    for file_item in (environment.get("symbols") or {}).get("files") or []:
        for symbol in file_item.get("symbols") or []:
            name = str(symbol.get("name") or "").strip()
            if name:
                symbols.add(name.lower())
    operation_kinds = {str(item.get("kind") or "").lower() for item in task.get("operation_manifest") or [] if item.get("kind")}
    return {
        "objective": _norm(task.get("objective")),
        "objective_tokens": _tokens(task.get("objective")),
        "mode": _norm(task.get("mode")),
        "paths": paths,
        "path_tokens": _tokens(" ".join(paths)),
        "languages": _path_languages(paths),
        "frameworks": _frameworks(environment),
        "symbols": symbols,
        "error_terms": {str(value).lower() for value in task.get("error_terms") or []},
        "operation_kinds": operation_kinds,
        "policy_profile": str(environment.get("policy_profile") or "default"),
        "task_digest": (bundle.get("task") or {}).get("digest"),
        "environment_digest": (bundle.get("environment") or {}).get("digest"),
        "evidence_digest": evidence.get("evidence_digest"),
    }


@dataclass(frozen=True)
class RetrievalQuery:
    objective: str
    mode: str = ""
    languages: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    affected_paths: tuple[str, ...] = ()
    error_terms: tuple[str, ...] = ()
    operation_kinds: tuple[str, ...] = ()
    policy_profile: str = ""
    include_superseded: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RetrievalQuery":
        def seq(name: str) -> tuple[str, ...]:
            raw = payload.get(name) or []
            if isinstance(raw, str):
                raw = [raw]
            return tuple(sorted({_norm(value) for value in raw if _norm(value)}))
        objective = _norm(payload.get("objective"))
        if not objective:
            raise ValueError("objective is required")
        return cls(
            objective=objective,
            mode=_norm(payload.get("mode")),
            languages=seq("languages"), frameworks=seq("frameworks"), symbols=seq("symbols"),
            affected_paths=seq("affected_paths"), error_terms=seq("error_terms"),
            operation_kinds=seq("operation_kinds"), policy_profile=_norm(payload.get("policy_profile")),
            include_superseded=bool(payload.get("include_superseded", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective, "mode": self.mode, "languages": list(self.languages),
            "frameworks": list(self.frameworks), "symbols": list(self.symbols),
            "affected_paths": list(self.affected_paths), "error_terms": list(self.error_terms),
            "operation_kinds": list(self.operation_kinds), "policy_profile": self.policy_profile,
            "include_superseded": self.include_superseded,
        }


class EvidenceRetriever:
    """Returns explainable candidates after deterministic lifecycle and metadata filters."""

    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).expanduser().resolve()
        self.store = EvidenceStore(self.root)
        self.fingerprints = FingerprintStore(self.root)
        self.ledger = EvidenceLedger(self.root)

    def search(self, payload: dict[str, Any], *, limit: int = 10, minimum_score: float = 0.0) -> dict[str, Any]:
        query = RetrievalQuery.from_payload(payload)
        limit = max(1, min(int(limit), 100))
        minimum_score = max(0.0, min(float(minimum_score), 1.0))
        candidates: list[dict[str, Any]] = []
        rejected: dict[str, int] = {}
        scanned = 0
        for evidence in self.store.list(limit=500):
            scanned += 1
            evidence_id = str(evidence.get("evidence_id") or "")
            state = self.ledger.state(evidence_id)
            status = str(state.get("status") or "active")
            if status in {"revoked", "expired"} or (status == "superseded" and not query.include_superseded):
                rejected[f"ledger_{status}"] = rejected.get(f"ledger_{status}", 0) + 1
                continue
            bundle = self.fingerprints.get(evidence_id)
            if not bundle:
                rejected["missing_fingerprint"] = rejected.get("missing_fingerprint", 0) + 1
                continue
            document = _candidate_document(evidence, bundle)
            hard_failures: list[str] = []
            if query.languages and not (set(query.languages) & document["languages"]):
                hard_failures.append("language")
            if query.frameworks and not (set(query.frameworks) & document["frameworks"]):
                hard_failures.append("framework")
            if query.policy_profile and query.policy_profile != document["policy_profile"]:
                hard_failures.append("policy_profile")
            if hard_failures:
                for name in hard_failures:
                    rejected[f"filter_{name}"] = rejected.get(f"filter_{name}", 0) + 1
                continue

            query_objective = _tokens(query.objective)
            path_tokens = _tokens(" ".join(query.affected_paths))
            components = {
                "objective": _jaccard(query_objective, document["objective_tokens"]),
                "symbols": _jaccard(set(query.symbols), document["symbols"]),
                "affected_paths": _jaccard(path_tokens, document["path_tokens"]),
                "error_terms": _jaccard(set(query.error_terms), document["error_terms"]),
                "operation_kinds": _jaccard(set(query.operation_kinds), document["operation_kinds"]),
                "mode": 1.0 if query.mode and query.mode == document["mode"] else 0.0,
                "language": 1.0 if query.languages and set(query.languages) & document["languages"] else 0.0,
                "framework": 1.0 if query.frameworks and set(query.frameworks) & document["frameworks"] else 0.0,
            }
            weights = {
                "objective": 0.38, "symbols": 0.18, "affected_paths": 0.14, "error_terms": 0.10,
                "operation_kinds": 0.08, "mode": 0.04, "language": 0.04, "framework": 0.04,
            }
            query_present = {
                "objective": bool(query.objective), "symbols": bool(query.symbols),
                "affected_paths": bool(query.affected_paths), "error_terms": bool(query.error_terms),
                "operation_kinds": bool(query.operation_kinds), "mode": bool(query.mode),
                "language": bool(query.languages), "framework": bool(query.frameworks),
            }
            available = {name: weight for name, weight in weights.items() if query_present[name]}
            denominator = sum(available.values()) or 1.0
            score = sum(components[name] * weight for name, weight in available.items()) / denominator
            score = round(max(0.0, min(score, 1.0)), 6)
            if score < minimum_score:
                rejected["below_minimum_score"] = rejected.get("below_minimum_score", 0) + 1
                continue
            matched = [name for name, value in components.items() if value > 0]
            candidates.append({
                "evidence_id": evidence_id,
                "score": score,
                "ledger_status": status,
                "matched_components": matched,
                "score_components": components,
                "fingerprint": {
                    "task_digest": document["task_digest"],
                    "environment_digest": document["environment_digest"],
                },
                "explanation": self._explanation(score, matched, document),
                "authority": "candidate_only",
            })
        candidates.sort(key=lambda item: (-item["score"], item["evidence_id"]))
        candidates = candidates[:limit]
        receipt_core = {
            "version": "3.4", "query": query.as_dict(), "scanned": scanned,
            "returned": len(candidates), "rejected": rejected,
            "candidates": candidates,
        }
        return {
            "beast_object_type": "beast_evidence_retrieval_receipt",
            **receipt_core,
            "receipt_digest": sha256_digest(receipt_core),
            "reuse_authorized": False,
        }

    @staticmethod
    def _explanation(score: float, matched: list[str], document: dict[str, Any]) -> str:
        if not matched:
            return "Candidate survived lifecycle filters but has no positive deterministic match components."
        return (
            f"Deterministic score {score:.3f}; matched {', '.join(sorted(matched))}. "
            f"Languages={sorted(document['languages']) or ['unknown']}; policy={document['policy_profile']}."
        )
