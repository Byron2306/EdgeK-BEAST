"""
Required tool-call integration surfaces for BEAST.

The gateway treats these as named integration contracts. A dependency can be
not-ready on a host, but the integration still exists, is health checked, and
has a stable policy/execution surface.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.storage.evidence_envelope import EvidenceEnvelopeFactory
from app.kernel.storage.evidence_chronicle import EvidenceChronicleWriter


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
        compressors = self.compressor_status(configured)
        return {
            "required_integrations": [item.to_dict() for item in statuses],
            "compressors": compressors,
            "ready": all(item.ready for item in statuses if item.required),
            "not_ready": [item.name for item in statuses if item.required and not item.ready],
        }

    def compressor_status(self, configured: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return compressor backend readiness plus BEAST's local fallback."""
        configured = configured or self.policies.get("required_integrations") or self.DEFAULTS
        backends = []
        for name, config in configured.items():
            config = config or {}
            kind = str(config.get("kind") or self.DEFAULTS.get(name, {}).get("kind") or "")
            binary = config.get("binary") or self.DEFAULTS.get(name, {}).get("binary")
            if kind != "compressor" and name not in {"rtk", "sqz", "longcodezip"}:
                continue
            path = shutil.which(str(binary or name))
            backends.append({
                "name": name,
                "kind": "external_binary",
                "binary": str(binary or name),
                "ready": bool(path),
                "binary_path": path,
                "fallback": "edgek_builtin_prune",
            })
        backends.append({
            "name": "edgek_prune",
            "kind": "builtin",
            "binary": None,
            "ready": True,
            "binary_path": None,
            "fallback": None,
        })
        return {
            "ready": any(item["ready"] for item in backends),
            "default": "edgek_prune",
            "backends": backends,
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
                try:
                    auth = subprocess.run(
                        ["gh", "auth", "status"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                    ready = auth.returncode == 0
                    detail["gh_auth_returncode"] = auth.returncode
                    detail["gh_auth_output"] = (auth.stdout or auth.stderr or "").strip()[:500]
                except (subprocess.TimeoutExpired, OSError) as exc:
                    ready = False
                    detail["gh_auth_error"] = str(exc)
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
            try:
                probe = subprocess.run(
                    [pg_isready, "-h", "/var/run/postgresql", "-p", "5432"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                detail["pg_isready_returncode"] = probe.returncode
                detail["pg_isready_output"] = (probe.stdout or probe.stderr).strip()
                if probe.returncode == 0:
                    detail["ready"] = True
            except (subprocess.TimeoutExpired, OSError) as exc:
                detail["pg_isready_error"] = str(exc)
        elif psql:
            try:
                probe = subprocess.run(
                    [psql, "-h", "/var/run/postgresql", "-d", "postgres", "-c", "select 1"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                detail["psql_returncode"] = probe.returncode
                detail["ready"] = probe.returncode == 0
            except (subprocess.TimeoutExpired, OSError) as exc:
                detail["psql_error"] = str(exc)
        return detail


class ToolCallInterceptor:
    """Interception and compression for local read/tool payloads."""

    def __init__(self, workspace_graph: Optional[Any] = None, policies: Optional[Dict[str, Any]] = None):
        self.workspace_graph = workspace_graph
        self.policies = policies or {}
        self.evidence_factory = EvidenceEnvelopeFactory(self.policies)
        self.chronicle_writer = EvidenceChronicleWriter(
            enabled=bool((self.policies.get("evidence_chronicle") or {}).get("enabled", True)),
        )

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
            "interception": self._interception_metadata(
                intent="unsupported",
                risk="unknown",
                scope="tool_call",
                executed=False,
                local_first=True,
            ),
            "evidence_record": self._interception_evidence(
                source_uri=f"tool://{tool_name or 'unknown'}",
                scope="tool_call",
                summary="No supported tool-call interception rule matched",
                severity="low",
                confidence=0.3,
                relevance=0.2,
                risk=0.4,
                signals=["interception_unmatched"],
                recommended_actions=["Add an interception rule or route through MCP policy evaluation."],
            ),
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
            return {
                "intercepted": True,
                "executed": False,
                "reason": "File target does not exist",
                "target": rel_path,
                "interception": self._interception_metadata(
                    intent="file_read",
                    risk="read_only",
                    scope="file",
                    executed=False,
                    local_first=True,
                ),
                "evidence_record": self._interception_evidence(
                    source_uri=f"file://{rel_path}",
                    scope="file",
                    summary=f"Read interception target does not exist: {rel_path}",
                    severity="medium",
                    confidence=0.9,
                    relevance=0.7,
                    risk=0.25,
                    signals=["file_read_intercepted", "target_missing"],
                    recommended_actions=["Verify the requested path before cloud handoff."],
                ),
            }

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
        response = {
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
        response["interception"] = self._interception_metadata(
            intent="file_read",
            risk="read_only",
            scope="file",
            executed=True,
            local_first=True,
            backend=backend,
        )
        response["evidence_record"] = self._interception_evidence(
            source_uri=f"file://{rel_path}",
            scope="file",
            summary=f"Read intercepted and reduced via {backend}: {rel_path}",
            severity="info",
            confidence=0.88,
            relevance=0.75 if snippets else 0.4,
            risk=0.15,
            verification_strength=0.55,
            expected_value=max(0.2, min(0.9, response["reduction_percent"] / 100.0 + 0.25)),
            signals=["file_read_intercepted", "context_reduced", backend],
            relationships=[{"type": "file", "id": rel_path}],
            recommended_actions=["Use returned snippets instead of sending the full file upstream."],
        )
        response["chronicle"] = self.chronicle_writer.maybe_write(response["evidence_record"], reason="tool_interception")
        return response

    def compress_text(self, text: str, algorithm: str = "edgek_prune") -> Dict[str, Any]:
        algorithm = self._normalize_algorithm(algorithm)
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

    def _normalize_algorithm(self, algorithm: str) -> str:
        normalized = str(algorithm or "edgek_prune").strip().lower().replace("-", "_")
        aliases = {
            "builtin": "edgek_prune",
            "edge_prune": "edgek_prune",
            "edgek_builtin": "edgek_prune",
            "prune": "edgek_prune",
            "repo_relay": "reporelay",
            "long_code_zip": "longcodezip",
        }
        return aliases.get(normalized, normalized)

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
        reduction = self._reduction(original_bytes, compressed_bytes)
        response = {
            "intercepted": True,
            "mode": "token_pruning",
            "algorithm": algorithm,
            "backend": backend,
            "content": output,
            "original_bytes": original_bytes,
            "bytes_returned": compressed_bytes,
            "reduction_percent": reduction,
            "content_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        }
        response["interception"] = self._interception_metadata(
            intent="payload_compression",
            risk="low",
            scope="payload",
            executed=True,
            local_first=True,
            backend=backend,
        )
        response["evidence_record"] = self._interception_evidence(
            source_uri=f"payload://sha256/{response['content_hash']}",
            scope="payload",
            summary=f"Payload compressed with {backend} using {algorithm}",
            severity="info",
            confidence=0.86,
            relevance=0.65,
            risk=0.1,
            verification_strength=0.45,
            expected_value=max(0.1, min(0.95, reduction / 100.0 + 0.2)),
            signals=["payload_intercepted", "token_pruning", backend],
            recommended_actions=["Prefer compressed payload for model handoff when exact full text is unnecessary."],
        )
        response["chronicle"] = self.chronicle_writer.maybe_write(response["evidence_record"], reason="payload_compression")
        return response

    def _is_read_file(self, tool_name: str, action: str, payload: Dict[str, Any]) -> bool:
        text = " ".join([tool_name, action, str(payload.get("command") or "")]).lower()
        return "read_file" in text or "read file" in text or (text.strip() == "read" and any(k in payload for k in ("target", "path", "file")))

    def _interception_metadata(
        self,
        intent: str,
        risk: str,
        scope: str,
        executed: bool,
        local_first: bool,
        backend: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "intent": intent,
            "risk": risk,
            "scope": scope,
            "executed": executed,
            "local_first": local_first,
            "backend": backend,
            "policy_surface": "semantic_tool_interceptor",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _interception_evidence(
        self,
        source_uri: str,
        scope: str,
        summary: str,
        severity: str,
        confidence: float,
        relevance: float,
        risk: float,
        signals: List[str],
        recommended_actions: List[str],
        verification_strength: float = 0.35,
        expected_value: float = 0.35,
        relationships: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        stable = json.dumps({
            "source_uri": source_uri,
            "scope": scope,
            "summary": summary,
            "signals": signals,
            "created_at": created_at,
        }, sort_keys=True, default=str)
        return {
            **self.evidence_factory.build(
                source_type="tool_interception",
                source_uri=source_uri,
                scope=scope,
                artifact_type="interception_evidence",
                severity=severity,
                confidence=confidence,
                relevance=relevance,
                risk=risk,
                blast_radius=0.25 if scope in ("file", "payload") else 0.5,
                repeat_count=1,
                verification_strength=verification_strength,
                expected_value=expected_value,
                signals=signals,
                relationships=relationships or [],
                recommended_actions=recommended_actions,
                summary=summary,
                created_at=created_at,
            ),
            "evidence_id": "ev_intercept_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16],
        }

    def _reduction(self, original_bytes: int, compressed_bytes: int) -> float:
        if original_bytes <= 0:
            return 0.0
        return round(((original_bytes - compressed_bytes) / original_bytes) * 100.0, 4)
