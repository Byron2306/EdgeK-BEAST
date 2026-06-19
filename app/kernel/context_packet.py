"""
EdgeK BEAST Context Packet Builder.

Builds bounded, evidence-backed handoff packets from task envelopes, route cards,
quality reports, and workspace graph context. The packet is intentionally local
and auditable: every included or excluded evidence item is recorded before any
model escalation happens.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ContextPacketBuilder:
    """Pack task-local evidence into a deterministic model handoff object."""

    PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.@-]+(?:\.[A-Za-z0-9]+)?")
    SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_dsa"}
    SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt"}
    EXCLUDED_PARTS = {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
    DEFAULT_MAX_FILE_CHARS = 1800

    def __init__(
        self,
        workspace_graph: Any = None,
        max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
    ):
        self.workspace_graph = workspace_graph
        self.max_file_chars = max_file_chars

    def build(
        self,
        envelope: Dict[str, Any],
        route_card: Optional[Dict[str, Any]] = None,
        quality_report: Optional[Dict[str, Any]] = None,
        workspace_root: str = ".",
        semantic_limit: int = 5,
        include_content: bool = True,
        max_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build a context packet from already-local BEAST artifacts."""
        root = Path(workspace_root).resolve()
        budget = envelope.get("context_budget") or {}
        file_limit = max(0, int(max_files if max_files is not None else budget.get("max_files", 8)))
        max_tokens = int(budget.get("max_tokens", 8000) or 8000)
        allow_full_files = bool(budget.get("allow_full_files", False))
        query_text = self._query_text(envelope)
        ir = self._ir_for_envelope(envelope, query_text)
        workspace_context = self._workspace_context(ir, semantic_limit)

        included: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []

        if route_card:
            included.append(self._json_evidence("route_card", route_card.get("route_id", "route_card"), route_card))
        if quality_report:
            included.append(self._json_evidence(
                "quality_report",
                quality_report.get("cascade_id") or quality_report.get("task_id") or "quality_report",
                self._quality_handoff_view(quality_report),
            ))

        mentioned_files = self._mentioned_files(envelope, workspace_context)
        for index, rel_path in enumerate(mentioned_files):
            if index >= file_limit:
                excluded.append({"source": rel_path, "reason": "over max_files"})
                continue
            evidence, rejection = self._file_evidence(
                root,
                rel_path,
                include_content=include_content,
                allow_full_file=allow_full_files,
            )
            if evidence:
                included.append(evidence)
            elif rejection:
                excluded.append(rejection)

        for match in workspace_context.get("semantic_matches", [])[:semantic_limit]:
            evidence = self._semantic_evidence(match, include_content=include_content)
            if evidence:
                included.append(evidence)

        for match in workspace_context.get("artifact_matches", [])[:semantic_limit]:
            evidence = self._artifact_evidence(match, include_content=include_content)
            if evidence:
                included.append(evidence)

        stats = self._stats(included, excluded)
        packet = {
            "beast_object_type": "context_packet",
            "version": "1.0",
            "packet_id": "",
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "route_id": (route_card or {}).get("route_id"),
            "goal": envelope.get("intent") or query_text[:240],
            "privacy_class": envelope.get("privacy_class", "internal"),
            "context_budget": {
                "max_tokens": max_tokens,
                "max_files": file_limit,
                "allow_full_files": allow_full_files,
            },
            "quality_summary": self._quality_summary(quality_report),
            "workspace_context": workspace_context,
            "included_evidence": included,
            "excluded_evidence": excluded,
            "packet_stats": stats,
            "handoff_hash": "",
        }
        packet_hash = self._hash_packet(packet)
        packet["packet_id"] = f"pkt_{packet_hash[:16]}"
        packet["handoff_hash"] = f"sha256:{packet_hash}"
        return packet

    def _workspace_context(self, ir: Dict[str, Any], semantic_limit: int) -> Dict[str, Any]:
        if not self.workspace_graph:
            return {
                "matched_nodes": [],
                "matched_node_count": 0,
                "mentioned_files": self._paths_from_text(json.dumps(ir, sort_keys=True)),
                "semantic_matches": [],
                "semantic_match_count": 0,
                "artifact_matches": [],
                "artifact_match_count": 0,
                "semantic_available": False,
            }
        try:
            context = self.workspace_graph.context_for_ir(ir, limit=max(1, semantic_limit))
            context["semantic_available"] = bool(self.workspace_graph.semantic_available(load_model=False))
            if hasattr(self.workspace_graph, "artifact_context"):
                artifacts = self.workspace_graph.artifact_context(
                    self._query_text_from_ir(ir),
                    limit=max(1, semantic_limit),
                )
                context["artifact_matches"] = artifacts.get("results", [])
                context["artifact_match_count"] = artifacts.get("result_count", 0)
            return context
        except Exception as exc:
            return {
                "matched_nodes": [],
                "matched_node_count": 0,
                "mentioned_files": self._paths_from_text(json.dumps(ir, sort_keys=True)),
                "semantic_matches": [],
                "semantic_match_count": 0,
                "artifact_matches": [],
                "artifact_match_count": 0,
                "semantic_available": False,
                "error": str(exc),
            }

    def _file_evidence(
        self,
        root: Path,
        rel_path: str,
        include_content: bool,
        allow_full_file: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        normalized = self._normalize_rel_path(rel_path)
        if not normalized:
            return None, {"source": rel_path, "reason": "invalid_path"}
        if self._is_sensitive(normalized):
            return None, {"source": normalized, "reason": "sensitive_or_blocked"}
        path = (root / normalized).resolve()
        if root not in path.parents and path != root:
            return None, {"source": normalized, "reason": "outside_workspace"}
        if not path.exists():
            return None, {"source": normalized, "reason": "missing"}
        if not path.is_file():
            return None, {"source": normalized, "reason": "not_a_file"}
        try:
            stat = path.stat()
            if stat.st_size > 1024 * 1024:
                return None, {"source": normalized, "reason": "binary_or_large"}
            if self.workspace_graph and hasattr(self.workspace_graph, "get_file_content_cached"):
                cached = self.workspace_graph.get_file_content_cached(str(path), max_bytes=max(self.max_file_chars, 1))
                content = str((cached or {}).get("content") or "")
                content_hash = str((cached or {}).get("content_hash") or "")
            else:
                content = path.read_text(encoding="utf-8", errors="replace")
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        except (OSError, UnicodeError):
            return None, {"source": normalized, "reason": "unreadable"}
        if "\x00" in content:
            return None, {"source": normalized, "reason": "binary_or_large"}

        lines = content.splitlines()
        full_content = "\n".join(lines)
        snippet = full_content if allow_full_file else full_content[: self.max_file_chars]
        end_line = len(snippet.splitlines()) or 1
        if not include_content:
            snippet = ""
        if not content_hash:
            content_hash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
        return {
            "evidence_id": self._evidence_id("file_snippet", normalized, content_hash),
            "kind": "file_snippet",
            "source": normalized,
            "start_line": 1,
            "end_line": end_line,
            "content_hash": f"sha256:{content_hash}",
            "content": snippet,
        }, None

    def _semantic_evidence(self, match: Dict[str, Any], include_content: bool) -> Optional[Dict[str, Any]]:
        source = match.get("file") or match.get("label") or match.get("node_id")
        if not source:
            return None
        content = match.get("content") or ""
        payload = {
            "node_id": match.get("node_id"),
            "similarity": match.get("similarity"),
            "label": match.get("label"),
            "file": match.get("file"),
            "start_line": match.get("start_line"),
            "end_line": match.get("end_line"),
        }
        body = content if include_content and content else json.dumps(payload, sort_keys=True)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return {
            "evidence_id": self._evidence_id("semantic_match", str(source), content_hash),
            "kind": "semantic_match",
            "source": str(source),
            "start_line": match.get("start_line"),
            "end_line": match.get("end_line"),
            "content_hash": f"sha256:{content_hash}",
            "content": body,
            "metadata": payload,
        }

    def _artifact_evidence(self, match: Dict[str, Any], include_content: bool) -> Optional[Dict[str, Any]]:
        source = match.get("source_path") or match.get("label") or match.get("node_id")
        preview = str(match.get("preview") or "")
        if not source or not preview:
            return None
        payload = {
            "node_id": match.get("node_id"),
            "artifact_type": match.get("artifact_type"),
            "task_id": match.get("task_id"),
            "provider": match.get("provider"),
            "category": match.get("category"),
            "score": match.get("score"),
            "source_path": match.get("source_path"),
        }
        content = preview if include_content else json.dumps(payload, sort_keys=True)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "evidence_id": self._evidence_id("artifact_memory", str(source), content_hash),
            "kind": "artifact_memory",
            "source": str(source),
            "start_line": None,
            "end_line": None,
            "content_hash": f"sha256:{content_hash}",
            "content": content,
            "metadata": payload,
        }

    def _json_evidence(self, kind: str, source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        content = json.dumps(payload, sort_keys=True, indent=2, default=str)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "evidence_id": self._evidence_id(kind, source, content_hash),
            "kind": kind,
            "source": source,
            "start_line": None,
            "end_line": None,
            "content_hash": f"sha256:{content_hash}",
            "content": content,
        }

    def _mentioned_files(self, envelope: Dict[str, Any], workspace_context: Dict[str, Any]) -> List[str]:
        files = list(workspace_context.get("mentioned_files") or [])
        files.extend(self._paths_from_text(self._query_text(envelope)))
        for node in workspace_context.get("matched_nodes") or []:
            if node.get("type") == "file" and node.get("label"):
                files.append(str(node["label"]))
        return self._dedupe(files)

    def _paths_from_text(self, text: str) -> List[str]:
        return self._dedupe(match.strip(".,:;)'\"]") for match in self.PATH_PATTERN.findall(text or ""))

    def _query_text(self, envelope: Dict[str, Any]) -> str:
        inputs = envelope.get("inputs") or {}
        parts = [
            envelope.get("intent"),
            inputs.get("user_request"),
            inputs.get("recent_logs") if isinstance(inputs.get("recent_logs"), str) else None,
        ]
        return "\n".join(str(part) for part in parts if part).strip()

    def _query_text_from_ir(self, ir: Dict[str, Any]) -> str:
        parts = []
        for message in ir.get("messages") or []:
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
        metadata = ir.get("metadata") or {}
        for key in ("objective", "task", "query"):
            if metadata.get(key):
                parts.append(str(metadata[key]))
        return "\n".join(parts).strip()

    def _ir_for_envelope(self, envelope: Dict[str, Any], query_text: str) -> Dict[str, Any]:
        return {
            "messages": [{"role": "user", "content": query_text}],
            "model": (envelope.get("inputs") or {}).get("model"),
            "metadata": {
                "objective": envelope.get("intent"),
                "task": envelope.get("task_class"),
                "query": query_text,
            },
        }

    def _quality_summary(self, quality_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not quality_report:
            return {"status": "not_run", "check_count": 0, "failed": 0, "warnings": 0}
        summary = dict(quality_report.get("summary") or {})
        summary["status"] = quality_report.get("status", summary.get("status", "unknown"))
        return summary

    def _quality_handoff_view(self, quality_report: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "beast_object_type": quality_report.get("beast_object_type"),
            "task_id": quality_report.get("task_id"),
            "route_id": quality_report.get("route_id"),
            "status": quality_report.get("status"),
            "summary": quality_report.get("summary"),
            "checks": [
                {
                    "name": check.get("name"),
                    "status": check.get("status"),
                    "summary": check.get("summary"),
                    "evidence": check.get("evidence"),
                }
                for check in quality_report.get("checks", [])
            ],
        }

    def _stats(self, included: List[Dict[str, Any]], excluded: List[Dict[str, Any]]) -> Dict[str, int]:
        content_chars = sum(len(str(item.get("content") or "")) for item in included)
        return {
            "estimated_tokens": max(1, content_chars // 4) if content_chars else 0,
            "included_count": len(included),
            "excluded_count": len(excluded),
            "content_chars": content_chars,
        }

    def _normalize_rel_path(self, rel_path: str) -> str:
        cleaned = str(rel_path or "").strip().strip("`")
        if not cleaned or cleaned.startswith(("http://", "https://")):
            return ""
        path = Path(cleaned)
        if path.is_absolute():
            return ""
        parts = [part for part in path.parts if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            return ""
        return Path(*parts).as_posix()

    def _is_sensitive(self, rel_path: str) -> bool:
        path = Path(rel_path)
        parts = set(path.parts)
        if parts & self.EXCLUDED_PARTS:
            return True
        if path.name in self.SENSITIVE_NAMES:
            return True
        return path.suffix.lower() in self.SENSITIVE_SUFFIXES

    def _hash_packet(self, packet: Dict[str, Any]) -> str:
        stable = dict(packet)
        stable["packet_id"] = ""
        stable["handoff_hash"] = ""
        serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _evidence_id(self, kind: str, source: str, content_hash: str) -> str:
        digest = hashlib.sha256(f"{kind}:{source}:{content_hash}".encode("utf-8")).hexdigest()
        return f"ev_{kind}_{digest[:16]}"

    def _dedupe(self, values) -> List[str]:
        seen = set()
        output = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            output.append(text)
        return output
