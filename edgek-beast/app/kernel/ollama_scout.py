"""
Ollama scout layer for BEAST.

BEAST gathers exact context; Ollama acts as a local classifier/ranker/packet
builder. The scout never executes risky tools directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


SCOUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "needs_cloud": {"type": "boolean"},
        "privacy_level": {"type": "string", "enum": ["local_only", "redacted_cloud_ok", "cloud_ok"]},
        "confidence": {"type": "number"},
        "relevant_files": {"type": "array", "items": {"type": "string"}},
        "needed_tools": {"type": "array", "items": {"type": "string"}},
        "redaction_required": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": [
        "task_type",
        "risk",
        "needs_cloud",
        "privacy_level",
        "confidence",
        "relevant_files",
        "needed_tools",
        "redaction_required",
        "summary",
    ],
}


@dataclass
class OllamaStatus:
    installed: bool
    server_ready: bool
    base_url: str
    default_model: str
    models: List[str]
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OllamaScout:
    """Build compact handoff packets and optionally ask Ollama to rank them."""

    def __init__(self, workspace_graph: Optional[Any] = None, mcp_broker: Optional[Any] = None, policies: Optional[Dict[str, Any]] = None):
        self.workspace_graph = workspace_graph
        self.mcp_broker = mcp_broker
        self.policies = policies or {}
        scout = self.policies.get("ollama_scout", {})
        self.base_url = os.environ.get("OLLAMA_BASE_URL", scout.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.default_model = os.environ.get("OLLAMA_SCOUT_MODEL", scout.get("default_model", "llama3.2:3b"))
        self.max_prompt_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_PROMPT_CHARS", scout.get("max_prompt_chars", 9000)))
        self.max_chunk_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_CHUNK_CHARS", scout.get("max_chunk_chars", 420)))
        self.max_exact_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_EXACT_CHARS", scout.get("max_exact_chars", 520)))
        self.num_ctx = int(os.environ.get("OLLAMA_SCOUT_NUM_CTX", scout.get("num_ctx", 2048)))
        self.timeout_seconds = float(os.environ.get("OLLAMA_SCOUT_TIMEOUT_SECONDS", scout.get("timeout_seconds", 20.0)))
        self._postgres_schema_cache: Optional[Dict[str, Any]] = None
        self._postgres_schema_cached_at = 0.0
        self._postgres_schema_ttl = float(scout.get("postgres_schema_ttl_seconds", 300.0))

    def status(self) -> Dict[str, Any]:
        installed = self._ollama_installed()
        models: List[str] = []
        error = ""
        server_ready = False
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            server_ready = response.status_code < 400
            if server_ready:
                data = response.json()
                models = [item.get("name", "") for item in data.get("models", []) if item.get("name")]
        except Exception as exc:
            error = str(exc)
        return OllamaStatus(
            installed=installed,
            server_ready=server_ready,
            base_url=self.base_url,
            default_model=self.default_model,
            models=models,
            error=error,
        ).to_dict()

    def build_packet(
        self,
        *,
        task: str,
        workspace_root: str,
        model: Optional[str] = None,
        context_limit: int = 6,
        tool_limit: int = 5,
        include_postgres_schema: bool = True,
        include_github_context: bool = True,
    ) -> Dict[str, Any]:
        retrieved = self._retrieve_context(task, context_limit)
        exact_context = self._exact_context(retrieved, max_items=3)
        memory_state = self._memory_state()
        packet = {
            "goal": task,
            "local_analysis": self._fallback_decision(task, retrieved),
            "memory_state": memory_state,
            "retrieved_chunks": retrieved,
            "exact_context": exact_context,
            "tool_menu": self._tool_menu(task, tool_limit),
            "postgres_schema": self._postgres_schema() if include_postgres_schema else {"available": False},
            "github_context": self._github_context(task) if include_github_context else {"available": False},
            "constraints": [
                "Do not expose secrets or .env contents.",
                "Use read-only database access unless explicitly approved.",
                "Return compact, source-referenced context.",
                "Prefer local verification before cloud escalation.",
            ],
            "handoff_hash": "",
        }
        packet["handoff_hash"] = self._hash(packet)
        packet["ollama"] = self.status()
        packet["model"] = model or self.default_model
        packet["packet_stats"] = self._packet_stats(packet)
        return packet

    def scout(self, payload: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        task = str(payload.get("task") or payload.get("goal") or payload.get("query") or "").strip()
        if not task:
            raise ValueError("task/goal/query is required")
        model = payload.get("model") or self.default_model
        packet = self.build_packet(
            task=task,
            workspace_root=workspace_root,
            model=model,
            context_limit=max(1, min(int(payload.get("context_limit", 6)), 20)),
            tool_limit=max(1, min(int(payload.get("tool_limit", 5)), 10)),
            include_postgres_schema=bool(payload.get("include_postgres_schema", True)),
            include_github_context=bool(payload.get("include_github_context", True)),
        )
        decision = None
        if payload.get("use_ollama", True) and packet["ollama"]["server_ready"]:
            decision = self._call_ollama(packet, model=str(model))
        if not decision:
            decision = packet["local_analysis"]
            decision["source"] = "edgek_fallback"
        packet["local_analysis"] = decision
        return {
            "mode": "ollama_scout_handoff",
            "packet": packet,
            "ready_for_cloud": bool(decision.get("needs_cloud", True)),
            "selected_tools": decision.get("needed_tools", [])[: max(1, min(int(payload.get("tool_limit", 5)), 10))],
        }

    def _retrieve_context(self, task: str, limit: int) -> List[Dict[str, Any]]:
        if not self.workspace_graph:
            return []
        try:
            result = self.workspace_graph.semantic_context(
                task,
                limit=limit,
                include_content=True,
                max_chars_per_chunk=self.max_chunk_chars,
            )
            chunks = result.get("results", [])
        except Exception:
            chunks = []
        if chunks:
            return [
                {
                    "file": item.get("file"),
                    "lines": f"{item.get('start_line')}-{item.get('end_line')}",
                    "similarity": item.get("similarity"),
                    "reason": "semantic match to task",
                    "content": self._truncate(item.get("content"), self.max_chunk_chars),
                }
                for item in chunks
            ]
        matches = []
        if self.workspace_graph:
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", task)[:8]:
                for node in self.workspace_graph.search_nodes(token, limit=3):
                    props = node.get("properties", {})
                    if node.get("type") == "file" or props.get("path"):
                        matches.append({
                            "file": props.get("path") or node.get("label"),
                            "lines": None,
                            "similarity": 0.0,
                            "reason": f"workspace graph match for {token}",
                            "content": None,
                        })
        dedup = []
        seen = set()
        for item in matches:
            key = item.get("file")
            if key and key not in seen:
                seen.add(key)
                dedup.append(item)
        return dedup[:limit]

    def _exact_context(self, retrieved: List[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
        exact = []
        for item in retrieved:
            content = item.get("content")
            file_name = item.get("file")
            if not content or not file_name:
                continue
            exact.append({
                "file": file_name,
                "lines": item.get("lines"),
                "hash": f"sha256:{hashlib.sha256(str(content).encode('utf-8')).hexdigest()}",
                "content": self._truncate(content, self.max_exact_chars),
            })
            if len(exact) >= max_items:
                break
        return exact

    def _tool_menu(self, task: str, limit: int) -> List[Dict[str, Any]]:
        candidates = [
            ("repo.semantic_context", "Retrieve top code/document chunks by meaning"),
            ("repo.search_symbols", "Search indexed tree-sitter/workspace symbols"),
            ("repo.read_semantic", "Read top file snippets instead of full file"),
            ("postgres.schema", "Inspect local read-only Postgres schema"),
            ("postgres.query_readonly", "Run approved read-only SQL"),
            ("github.issue", "Fetch compact issue/PR context"),
            ("github.pr_diff", "Fetch compact PR diff context"),
            ("compress.sqz", "Prune noisy tool output"),
            ("compress.longcodezip", "Compress long source context"),
            ("compress.rtk", "Kill redundant tokens"),
        ]
        text = task.lower()
        scored = []
        for name, description in candidates:
            score = 0
            for part in name.split(".") + description.lower().split():
                if part.strip("_-") and part.strip("_-") in text:
                    score += 1
            if "sql" in text or "database" in text or "postgres" in text:
                score += 3 if name.startswith("postgres") else 0
            if "github" in text or "issue" in text or "pr" in text:
                score += 3 if name.startswith("github") else 0
            if "log" in text or "trace" in text or "compress" in text:
                score += 2 if name.startswith("compress") else 0
            scored.append((score, name, description))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [{"name": name, "description": description} for _, name, description in scored[:limit]]

    def _postgres_schema(self) -> Dict[str, Any]:
        now = time.time()
        if self._postgres_schema_cache and (now - self._postgres_schema_cached_at) < self._postgres_schema_ttl:
            return {**self._postgres_schema_cache, "cache": "hit"}
        try:
            completed = subprocess.run(
                [
                    "psql",
                    "-h",
                    "/var/run/postgresql",
                    "-d",
                    "postgres",
                    "-Atc",
                    "select table_schema||'.'||table_name||':'||string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_schema not in ('pg_catalog','information_schema') group by table_schema, table_name order by 1 limit 50",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode != 0:
                return {"available": False, "error": completed.stderr.strip()[:500]}
            tables = {}
            for line in completed.stdout.splitlines():
                if ":" in line:
                    table, cols = line.split(":", 1)
                    tables[table] = [col for col in cols.split(",") if col]
            result = {"available": True, "tables": tables, "relationships": [], "cache": "miss"}
            self._postgres_schema_cache = result
            self._postgres_schema_cached_at = now
            return result
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _github_context(self, task: str) -> Dict[str, Any]:
        if not shutil.which("gh"):
            return {"available": False, "error": "gh not installed"}
        issue_refs = re.findall(r"#(\d+)", task)
        return {
            "available": True,
            "auth": "gh",
            "issue_refs": issue_refs[:5],
            "summary": "GitHub CLI authenticated context is available; fetch only explicit issues/PRs through governed MCP.",
        }

    def _fallback_decision(self, task: str, retrieved: List[Dict[str, Any]]) -> Dict[str, Any]:
        lowered = task.lower()
        risk = "high" if any(word in lowered for word in ["delete", "drop", "credential", "secret", "production"]) else "medium"
        task_type = "bug_fix"
        if "test" in lowered or "failure" in lowered:
            task_type = "test_failure"
        elif "explain" in lowered:
            task_type = "explain"
        elif "refactor" in lowered:
            task_type = "refactor"
        tools = [item["name"] for item in self._tool_menu(task, 5)]
        return {
            "task_type": task_type,
            "risk": risk,
            "needs_cloud": risk != "low",
            "privacy_level": "redacted_cloud_ok" if risk != "high" else "local_only",
            "confidence": 0.62 if retrieved else 0.38,
            "relevant_files": [item.get("file") for item in retrieved if item.get("file")][:5],
            "needed_tools": tools,
            "redaction_required": risk == "high",
            "summary": "BEAST built a deterministic local scout decision from retrieved context.",
        }

    def _call_ollama(self, packet: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        scout_view = self._scout_view(packet)
        prompt = (
            "You are BEAST's local Ollama scout. Classify and rank this packet. "
            "Return only JSON matching the schema.\n\n"
            + json.dumps(scout_view, separators=(",", ":"), default=str)
        )
        prompt = self._truncate(prompt, self.max_prompt_chars)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": SCOUT_SCHEMA,
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 256},
        }
        try:
            response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            data = json.loads(content)
            data["source"] = "ollama"
            return data
        except Exception:
            return None

    def _memory_state(self) -> Dict[str, Any]:
        if not self.workspace_graph:
            return {"available": False, "source": "none"}
        try:
            stats = self.workspace_graph.stats()
        except Exception as exc:
            return {"available": False, "source": "workspace_graph", "error": str(exc)}
        return {
            "available": True,
            "source": "workspace_graph",
            "nodes": stats.get("total_nodes", 0),
            "edges": stats.get("total_edges", 0),
            "node_types": stats.get("node_types", {}),
            "file_read_cache": stats.get("file_read_cache", {}),
            "semantic": stats.get("semantic", {}),
            "tree_sitter": stats.get("tree_sitter", {}),
        }

    def _scout_view(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        schema = packet.get("postgres_schema", {})
        tables = schema.get("tables", {}) if isinstance(schema, dict) else {}
        compact_schema = {
            "available": bool(schema.get("available")) if isinstance(schema, dict) else False,
            "table_count": len(tables),
            "tables": {
                table: columns[:8]
                for table, columns in list(tables.items())[:8]
            },
            "cache": schema.get("cache") if isinstance(schema, dict) else None,
        }
        return {
            "goal": packet.get("goal"),
            "memory_state": packet.get("memory_state", {}),
            "retrieved_chunks": [
                {
                    "file": item.get("file"),
                    "lines": item.get("lines"),
                    "similarity": item.get("similarity"),
                    "reason": item.get("reason"),
                    "content": self._truncate(item.get("content"), self.max_chunk_chars),
                }
                for item in packet.get("retrieved_chunks", [])[:6]
            ],
            "exact_context": [
                {
                    "file": item.get("file"),
                    "lines": item.get("lines"),
                    "hash": item.get("hash"),
                    "content": self._truncate(item.get("content"), self.max_exact_chars),
                }
                for item in packet.get("exact_context", [])[:3]
            ],
            "tool_menu": packet.get("tool_menu", [])[:6],
            "postgres_schema": compact_schema,
            "github_context": packet.get("github_context", {}),
            "constraints": packet.get("constraints", []),
            "packet_stats": packet.get("packet_stats", {}),
        }

    def _packet_stats(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        full = json.dumps({key: value for key, value in packet.items() if key != "ollama"}, default=str)
        scout_view = json.dumps(self._scout_view({**packet, "packet_stats": {}}), default=str)
        return {
            "full_packet_chars": len(full),
            "ollama_scout_view_chars": len(scout_view),
            "ollama_prompt_char_limit": self.max_prompt_chars,
            "retrieved_chunks": len(packet.get("retrieved_chunks", [])),
            "exact_context_items": len(packet.get("exact_context", [])),
        }

    def _truncate(self, value: Any, limit: int) -> str:
        text = "" if value is None else str(value)
        if len(text) <= limit:
            return text
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
        keep = max(0, limit - 48)
        return f"{text[:keep]}\n...[truncated:{len(text)} chars sha256:{digest}]"

    def _ollama_installed(self) -> bool:
        return shutil.which("ollama") is not None

    def _hash(self, packet: Dict[str, Any]) -> str:
        clone = dict(packet)
        clone["handoff_hash"] = ""
        return "sha256:" + hashlib.sha256(json.dumps(clone, sort_keys=True, default=str).encode("utf-8")).hexdigest()
