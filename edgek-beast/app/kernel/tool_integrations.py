"""
Required tool-call integration surfaces for BEAST.

The gateway treats these as named integration contracts. A dependency can be
not-ready on a host, but the integration still exists, is health checked, and
has a stable policy/execution surface.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class IntegrationStatus:
    name: str
    required: bool
    ready: bool
    kind: str
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RequiredIntegrationRegistry:
    """Health/readiness checks for BEAST required integrations."""

    DEFAULTS = {
        "semantic_tool_interceptor": {"kind": "local", "required": True},
        "github": {"kind": "api", "required": True, "env": "GITHUB_TOKEN"},
        "postgres": {"kind": "database", "required": True, "env": "POSTGRES_DSN"},
        "rtk": {"kind": "compressor", "required": True, "binary": "rtk"},
        "sqz": {"kind": "compressor", "required": True, "binary": "sqz"},
        "longcodezip": {"kind": "compressor", "required": True, "binary": "longcodezip"},
        "reporelay": {"kind": "repository", "required": True, "binary": "reporelay"},
    }

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.policies = policies or {}

    def status(self) -> Dict[str, Any]:
        configured = self.policies.get("required_integrations") or self.DEFAULTS
        statuses = [self._status_one(name, config or {}) for name, config in configured.items()]
        return {
            "required_integrations": [item.to_dict() for item in statuses],
            "ready": all(item.ready for item in statuses if item.required),
            "not_ready": [item.name for item in statuses if item.required and not item.ready],
        }

    def _status_one(self, name: str, config: Dict[str, Any]) -> IntegrationStatus:
        kind = str(config.get("kind") or self.DEFAULTS.get(name, {}).get("kind") or "external")
        required = bool(config.get("required", True))
        env_name = config.get("env") or self.DEFAULTS.get(name, {}).get("env")
        binary = config.get("binary") or self.DEFAULTS.get(name, {}).get("binary")
        detail: Dict[str, Any] = {}
        ready = True
        if env_name:
            ready = bool(os.environ.get(str(env_name)))
            detail["env"] = str(env_name)
            detail["env_present"] = ready
            if not ready and name == "github" and shutil.which("gh"):
                auth = subprocess.run(
                    ["gh", "auth", "status"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                ready = auth.returncode == 0
                detail["gh_auth_present"] = ready
                detail["gh_path"] = shutil.which("gh")
            if not ready and name == "postgres":
                pg_ready = self._postgres_local_ready()
                ready = pg_ready["ready"]
                detail.update(pg_ready)
        if binary:
            path = shutil.which(str(binary))
            ready = bool(path)
            detail["binary"] = str(binary)
            detail["binary_path"] = path
        if name == "semantic_tool_interceptor":
            detail["backends"] = ["workspace_graph_vectors", "basic_semantic_grep"]
            ready = True
        return IntegrationStatus(name=name, required=required, ready=ready, kind=kind, detail=detail)

    def _postgres_local_ready(self) -> Dict[str, Any]:
        pg_isready = shutil.which("pg_isready")
        psql = shutil.which("psql")
        detail = {
            "local_socket_supported": True,
            "pg_isready_path": pg_isready,
            "psql_path": psql,
            "ready": False,
        }
        if pg_isready:
            probe = subprocess.run(
                [pg_isready, "-h", "/var/run/postgresql", "-p", "5432"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            detail["pg_isready_returncode"] = probe.returncode
            detail["pg_isready_output"] = (probe.stdout or probe.stderr).strip()
            if probe.returncode == 0:
                detail["ready"] = True
        elif psql:
            probe = subprocess.run(
                [psql, "-h", "/var/run/postgresql", "-d", "postgres", "-c", "select 1"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            detail["psql_returncode"] = probe.returncode
            detail["ready"] = probe.returncode == 0
        return detail


class ToolCallInterceptor:
    """Interception and compression for local read/tool payloads."""

    def __init__(self, workspace_graph: Optional[Any] = None, policies: Optional[Dict[str, Any]] = None):
        self.workspace_graph = workspace_graph
        self.policies = policies or {}

    def intercept(self, payload: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        tool_name = str(payload.get("tool_name") or payload.get("name") or "").lower()
        action = str(payload.get("action") or "").lower()
        if self._is_read_file(tool_name, action, payload):
            return self.intercept_read_file(payload, workspace_root)
        text = payload.get("content") or payload.get("text") or payload.get("payload")
        if isinstance(text, str):
            return self.compress_text(text, algorithm=str(payload.get("algorithm") or "edgek_prune"))
        return {
            "intercepted": False,
            "reason": "No supported tool-call interception rule matched",
            "tool_name": tool_name,
        }

    def intercept_read_file(self, payload: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        target = str(payload.get("target") or payload.get("path") or payload.get("file") or "")
        if not target:
            raise ValueError("target/path/file is required for read interception")
        root = Path(workspace_root).resolve()
        path = (root / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        try:
            rel_path = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("Target path escapes workspace root") from exc
        if not path.exists() or not path.is_file():
            return {"intercepted": True, "executed": False, "reason": "File target does not exist", "target": rel_path}

        query = str(payload.get("query") or payload.get("objective") or payload.get("reason") or rel_path)
        limit = max(1, min(int(payload.get("limit", 3)), 10))
        max_chars = max(240, min(int(payload.get("max_chars_per_snippet", 900)), 4000))
        raw = path.read_text(encoding="utf-8", errors="replace")
        raw_bytes = len(raw.encode("utf-8"))

        snippets = self._semantic_graph_snippets(rel_path, query, limit, max_chars)
        backend = "workspace_graph_vectors"
        if not snippets:
            snippets = self._basic_semantic_grep(raw, query, limit, max_chars, rel_path)
            backend = "basic_semantic_grep"

        content = "\n\n".join(
            f"[{item['file']}:{item['start_line']}-{item['end_line']} score={item['score']}]\n{item['content']}"
            for item in snippets
        )
        compressed_bytes = len(content.encode("utf-8"))
        return {
            "intercepted": True,
            "executed": True,
            "mode": "semantic_read_intercept",
            "backend": backend,
            "target": rel_path,
            "query": query,
            "snippets": snippets,
            "content": content,
            "raw_bytes": raw_bytes,
            "bytes_returned": compressed_bytes,
            "reduction_percent": self._reduction(raw_bytes, compressed_bytes),
            "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }

    def compress_text(self, text: str, algorithm: str = "edgek_prune") -> Dict[str, Any]:
        algorithm = algorithm.lower()
        binary = {
            "rtk": "rtk",
            "sqz": "sqz",
            "longcodezip": "longcodezip",
            "reporelay": "reporelay",
        }.get(algorithm)
        if binary and shutil.which(binary):
            completed = subprocess.run(
                [binary],
                input=text,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout:
                output = completed.stdout
                return self._compression_response(text, output, algorithm, f"{algorithm}_binary")

        output = self._edge_prune(text)
        return self._compression_response(text, output, algorithm, "edgek_builtin_prune")

    def _semantic_graph_snippets(self, rel_path: str, query: str, limit: int, max_chars: int) -> List[Dict[str, Any]]:
        if self.workspace_graph is None:
            return []
        try:
            result = self.workspace_graph.semantic_context(query, limit=max(limit * 4, 8), include_content=True, max_chars_per_chunk=max_chars)
        except Exception:
            return []
        snippets = []
        for item in result.get("results", []):
            if item.get("file") != rel_path or not item.get("content"):
                continue
            snippets.append({
                "file": rel_path,
                "start_line": item.get("start_line") or 1,
                "end_line": item.get("end_line") or item.get("start_line") or 1,
                "score": round(float(item.get("similarity") or 0), 5),
                "content": str(item.get("content"))[:max_chars],
            })
            if len(snippets) >= limit:
                break
        return snippets

    def _basic_semantic_grep(self, text: str, query: str, limit: int, max_chars: int, rel_path: str) -> List[Dict[str, Any]]:
        terms = [term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)]
        paragraphs = self._paragraphs(text)
        scored = []
        for idx, para in enumerate(paragraphs):
            lowered = para["content"].lower()
            score = sum(lowered.count(term) for term in terms)
            score += 0.1 if any(term in lowered for term in terms) else 0.0
            if score <= 0 and terms:
                continue
            scored.append((score, idx, para))
        if not scored:
            scored = [(0.0, idx, para) for idx, para in enumerate(paragraphs[:limit])]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            {
                "file": rel_path,
                "start_line": para["start_line"],
                "end_line": para["end_line"],
                "score": round(float(score), 5),
                "content": para["content"][:max_chars],
            }
            for score, _, para in scored[:limit]
        ]

    def _paragraphs(self, text: str) -> List[Dict[str, Any]]:
        paragraphs = []
        current = []
        start = 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                if not current:
                    start = lineno
                current.append(line)
            elif current:
                paragraphs.append({"start_line": start, "end_line": lineno - 1, "content": "\n".join(current)})
                current = []
        if current:
            paragraphs.append({"start_line": start, "end_line": start + len(current) - 1, "content": "\n".join(current)})
        return paragraphs or [{"start_line": 1, "end_line": 1, "content": text}]

    def _edge_prune(self, text: str) -> str:
        lines = text.splitlines()
        kept = []
        previous = None
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "//", "/*", "*")) and len(stripped) > 80:
                continue
            if stripped == previous:
                continue
            kept.append(line.rstrip())
            previous = stripped
        if len("\n".join(kept)) > 6000:
            head = kept[:120]
            tail = kept[-60:]
            kept = head + ["# ... edgek_prune omitted middle low-density lines ..."] + tail
        return "\n".join(kept)

    def _compression_response(self, original: str, output: str, algorithm: str, backend: str) -> Dict[str, Any]:
        original_bytes = len(original.encode("utf-8"))
        compressed_bytes = len(output.encode("utf-8"))
        return {
            "intercepted": True,
            "mode": "token_pruning",
            "algorithm": algorithm,
            "backend": backend,
            "content": output,
            "original_bytes": original_bytes,
            "bytes_returned": compressed_bytes,
            "reduction_percent": self._reduction(original_bytes, compressed_bytes),
            "content_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        }

    def _is_read_file(self, tool_name: str, action: str, payload: Dict[str, Any]) -> bool:
        text = " ".join([tool_name, action, str(payload.get("command") or "")]).lower()
        return "read_file" in text or "read file" in text or (text.strip() == "read" and any(k in payload for k in ("target", "path", "file")))

    def _reduction(self, original_bytes: int, compressed_bytes: int) -> float:
        if original_bytes <= 0:
            return 0.0
        return round(((original_bytes - compressed_bytes) / original_bytes) * 100.0, 4)
