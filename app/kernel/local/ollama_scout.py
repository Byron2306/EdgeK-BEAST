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

    def __init__(
        self,
        workspace_graph: Optional[Any] = None,
        mcp_broker: Optional[Any] = None,
        policies: Optional[Dict[str, Any]] = None,
        forensic_memory: Optional[Any] = None,
        data_dir: Optional[str] = None,
    ):
        self.workspace_graph = workspace_graph
        self.mcp_broker = mcp_broker
        self.policies = policies or {}
        self.forensic_memory = forensic_memory
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        scout = self.policies.get("ollama_scout", {})
        self.base_url = os.environ.get("OLLAMA_BASE_URL", scout.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.default_model = os.environ.get("OLLAMA_SCOUT_MODEL", scout.get("default_model", "qwen2.5:0.5b"))
        self.max_prompt_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_PROMPT_CHARS", scout.get("max_prompt_chars", 9000)))
        self.max_chunk_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_CHUNK_CHARS", scout.get("max_chunk_chars", 420)))
        self.max_exact_chars = int(os.environ.get("OLLAMA_SCOUT_MAX_EXACT_CHARS", scout.get("max_exact_chars", 520)))
        self.num_ctx = int(os.environ.get("OLLAMA_SCOUT_NUM_CTX", scout.get("num_ctx", 2048)))
        self.timeout_seconds = float(os.environ.get("OLLAMA_SCOUT_TIMEOUT_SECONDS", scout.get("timeout_seconds", 45.0)))
        self._last_ollama_error = ""
        self._postgres_schema_cache: Optional[Dict[str, Any]] = None
        self._postgres_schema_cached_at = 0.0
        self._postgres_schema_ttl = float(scout.get("postgres_schema_ttl_seconds", 300.0))

    def status(self, timeout_seconds: float = 2.0) -> Dict[str, Any]:
        installed = self._ollama_installed()
        models: List[str] = []
        error = ""
        server_ready = False
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=max(0.01, float(timeout_seconds)))
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
        provider: Optional[str] = None,
        task_class: Optional[str] = None,
        task_envelope: Optional[Dict[str, Any]] = None,
        context_limit: int = 6,
        tool_limit: int = 5,
        include_postgres_schema: bool = True,
        include_github_context: bool = True,
        include_forensic_context: bool = True,
        forensic_limit: int = 5,
        forensic_layer: Optional[str] = None,
        forensic_event_kind: Optional[str] = None,
        forensic_provider: Optional[str] = None,
        forensic_status: Optional[str] = None,
        agent_awareness: Optional[Dict[str, Any]] = None,
        status_timeout_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        retrieved = self._retrieve_context(task, context_limit)
        exact_context = self._exact_context(retrieved, max_items=3)
        memory_state = self._memory_state()
        local_analysis = self._fallback_decision(task, retrieved)
        envelope = self._economized_task_envelope(
            task=task,
            provider=provider,
            task_class=task_class,
            task_envelope=task_envelope,
            local_analysis=local_analysis,
        )
        ranked_chunks = self._rank_retrieved_chunks(task, retrieved)
        chronicle_summary = self._chronicle_summary(task)
        forensic_context = self._forensic_context(
            task,
            limit=forensic_limit,
            layer=forensic_layer,
            event_kind=forensic_event_kind,
            provider=forensic_provider,
            status=forensic_status,
        ) if include_forensic_context else {"available": False, "source": "disabled"}
        packet = {
            "goal": task,
            "task_envelope": envelope["task_envelope"],
            "economized_task_envelope": envelope["economized_task_envelope"],
            "compression_contract": envelope["compression_contract"],
            "local_analysis": local_analysis,
            "memory_state": memory_state,
            "retrieved_chunks": retrieved,
            "ranked_chunks": ranked_chunks,
            "exact_context": exact_context,
            "tool_menu": self._tool_menu(task, tool_limit),
            "postgres_schema": self._postgres_schema() if include_postgres_schema else {"available": False},
            "github_context": self._github_context(task) if include_github_context else {"available": False},
            "forensic_context": forensic_context,
            "chronicle_summary": chronicle_summary,
            "fallback_recommendations": self._fallback_recommendations(task, local_analysis, forensic_context, chronicle_summary),
            "constraints": [
                "Treat economized_task_envelope as the primary input.",
                "Use retrieved chunks and tool menus only as supporting evidence.",
                "Do not expose secrets or .env contents.",
                "Use read-only database access unless explicitly approved.",
                "Return compact, source-referenced context.",
                "Prefer local verification before cloud escalation.",
            ],
            "agent_awareness": agent_awareness or {},
            "handoff_hash": "",
        }
        if agent_awareness:
            packet["constraints"].insert(0, str(agent_awareness.get("agent_instruction") or "Operate inside BEAST."))
        packet["decision_contract"] = self._decision_contract(packet["local_analysis"], packet)
        packet["handoff_hash"] = self._hash(packet)
        packet["decision_contract"]["packet_hash"] = packet["handoff_hash"]
        packet["ollama"] = self.status(timeout_seconds=status_timeout_seconds)
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
            provider=payload.get("provider"),
            task_class=payload.get("task_class"),
            task_envelope=payload.get("task_envelope") if isinstance(payload.get("task_envelope"), dict) else None,
            context_limit=max(1, min(int(payload.get("context_limit", 6)), 20)),
            tool_limit=max(1, min(int(payload.get("tool_limit", 5)), 10)),
            include_postgres_schema=bool(payload.get("include_postgres_schema", True)),
            include_github_context=bool(payload.get("include_github_context", True)),
            include_forensic_context=bool(payload.get("include_forensic_context", True)),
            forensic_limit=max(1, min(int(payload.get("forensic_limit", 5)), 20)),
            forensic_layer=payload.get("forensic_layer"),
            forensic_event_kind=payload.get("forensic_event_kind"),
            forensic_provider=payload.get("forensic_provider"),
            forensic_status=payload.get("forensic_status"),
            agent_awareness=payload.get("agent_awareness") if isinstance(payload.get("agent_awareness"), dict) else None,
            status_timeout_seconds=max(0.01, float(payload.get("status_timeout_seconds", 2.0))),
        )
        decision = None
        if payload.get("use_ollama", True) and packet["ollama"]["server_ready"]:
            decision = self._call_ollama(
                packet,
                model=str(model),
                timeout_seconds=max(0.01, float(payload.get("timeout_seconds", self.timeout_seconds))),
            )
        if not decision:
            decision = packet["local_analysis"]
            decision["source"] = "edgek_fallback"
            if self._last_ollama_error:
                packet["ollama"]["scout_error"] = self._last_ollama_error
        packet["local_analysis"] = decision
        packet["decision_contract"] = self._decision_contract(decision, packet)
        return {
            "mode": "ollama_scout_handoff",
            "packet": packet,
            "ready_for_cloud": bool(decision.get("needs_cloud", True)),
            "selected_tools": decision.get("needed_tools", [])[: max(1, min(int(payload.get("tool_limit", 5)), 10))],
            "decision_contract": packet["decision_contract"],
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

    def _rank_retrieved_chunks(self, task: str, retrieved: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tokens = self._tokens(task)
        ranked = []
        for index, item in enumerate(retrieved):
            text = " ".join(str(value or "") for value in [
                item.get("file"),
                item.get("reason"),
                item.get("content"),
            ]).lower()
            lexical_hits = sum(text.count(token) for token in tokens)
            semantic = float(item.get("similarity") or 0.0)
            score = round(min(1.0, semantic * 0.65 + min(lexical_hits / max(len(tokens), 1), 1.0) * 0.3 + 0.05), 5)
            ranked.append({
                "rank": 0,
                "file": item.get("file"),
                "lines": item.get("lines"),
                "score": score,
                "semantic_similarity": item.get("similarity"),
                "lexical_hits": lexical_hits,
                "reason": item.get("reason") or "retrieved context",
                "content_hash": f"sha256:{hashlib.sha256(str(item.get('content') or '').encode('utf-8')).hexdigest()[:16]}",
            })
        ranked.sort(key=lambda row: (row["score"], row["lexical_hits"]), reverse=True)
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked

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

    def _chronicle_summary(self, task: str, limit: int = 6) -> Dict[str, Any]:
        paths: List[Path] = []
        for dirname in ("chronicles", "evidence_chronicles"):
            root = self.data_dir / dirname
            if root.exists():
                paths.extend(root.glob("*.json"))
        tokens = self._tokens(task)
        records = []
        for path in sorted(paths, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:80]:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
            summary = str(evidence.get("summary") or record.get("summary") or record.get("root_cause") or "")
            haystack = " ".join([
                summary,
                str(evidence.get("provider") or record.get("provider") or ""),
                str(evidence.get("capability_family") or record.get("category") or ""),
                " ".join(str(item) for item in evidence.get("signals", []) if item),
            ]).lower()
            hits = sum(haystack.count(token) for token in tokens)
            if hits <= 0 and len(records) >= limit:
                continue
            records.append({
                "source_uri": str(path),
                "summary": self._truncate(summary, 220),
                "provider": evidence.get("provider") or record.get("provider"),
                "severity": evidence.get("severity") or record.get("severity"),
                "capability_family": evidence.get("capability_family") or record.get("category"),
                "priority_score": evidence.get("priority_score") or record.get("priority_score"),
                "created_at": evidence.get("created_at") or record.get("created_at"),
                "lexical_hits": hits,
            })
        records.sort(key=lambda item: (item["lexical_hits"], float(item.get("priority_score") or 0.0), str(item.get("created_at") or "")), reverse=True)
        top = records[:limit]
        return {
            "available": bool(top),
            "source": "chronicle_files",
            "record_count": len(top),
            "records": top,
            "summary": self._summarize_chronicle_records(top),
        }

    def _summarize_chronicle_records(self, records: List[Dict[str, Any]]) -> str:
        if not records:
            return "No matching Chronicle memory found."
        families: Dict[str, int] = {}
        providers: Dict[str, int] = {}
        for item in records:
            if item.get("capability_family"):
                families[str(item["capability_family"])] = families.get(str(item["capability_family"]), 0) + 1
            if item.get("provider"):
                providers[str(item["provider"])] = providers.get(str(item["provider"]), 0) + 1
        top_family = max(families, key=families.get) if families else "general"
        top_provider = max(providers, key=providers.get) if providers else "none"
        return f"{len(records)} matching Chronicle records; top family={top_family}; top provider={top_provider}."

    def _fallback_recommendations(
        self,
        task: str,
        decision: Dict[str, Any],
        forensic_context: Dict[str, Any],
        chronicle_summary: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        lowered = task.lower()
        recommendations = []
        if (forensic_context.get("result_count") or 0) > 0:
            recommendations.append({
                "action": "inspect_forensic_l4",
                "reason": "L4 contains local events matching the current task.",
                "risk": "low",
            })
        if chronicle_summary.get("available"):
            recommendations.append({
                "action": "reuse_chronicle_pattern",
                "reason": chronicle_summary.get("summary"),
                "risk": "low",
            })
        if any(word in lowered for word in ("provider", "timeout", "rate", "credential", "circuit")):
            recommendations.append({
                "action": "run_provider_diagnostic",
                "reason": "Provider/circuit/credential wording suggests a local diagnostic route before escalation.",
                "risk": "low",
            })
        if any(word in lowered for word in ("test", "lint", "syntax", "import", "failure")):
            recommendations.append({
                "action": "run_quality_cascade",
                "reason": "Local verification can narrow the failure before cloud handoff.",
                "risk": "low",
            })
        if decision.get("privacy_level") == "local_only":
            recommendations.append({
                "action": "block_cloud_handoff_until_redacted",
                "reason": "The local classifier marked this task as local-only.",
                "risk": "medium",
            })
        if not recommendations:
            recommendations.append({
                "action": "build_current_task_markup",
                "reason": "Task objective/scope/success criteria should be explicit before any handoff.",
                "risk": "low",
            })
        return recommendations[:6]

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
            "role_hints": self._role_hints(task_type, risk, tools),
            "summary": "BEAST built a deterministic local scout decision from retrieved context.",
        }

    def _economized_task_envelope(
        self,
        *,
        task: str,
        provider: Optional[str],
        task_class: Optional[str],
        task_envelope: Optional[Dict[str, Any]],
        local_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        envelope = dict(task_envelope or {})
        inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
        budget = envelope.get("context_budget") if isinstance(envelope.get("context_budget"), dict) else {}
        if not envelope:
            envelope = {
                "beast_object_type": "task_envelope",
                "version": "1.0",
                "task_id": f"tsk_{hashlib.sha256(task.encode('utf-8')).hexdigest()[:12]}",
                "intent": self._truncate(task, 240),
                "task_class": task_class or local_analysis.get("task_type") or "coding_environment_optimization",
                "project": "edgek-beast",
                "risk_level": local_analysis.get("risk", "medium"),
                "privacy_class": local_analysis.get("privacy_level", "redacted_cloud_ok"),
                "inputs": {
                    "user_request": task,
                    "provider": provider or "local_ollama_scout",
                    "active_service": "edgek-beast-gateway",
                },
                "context_budget": {
                    "max_tokens": 8000,
                    "max_files": 8,
                    "allow_full_files": False,
                },
                "allowed_actions": ["read_files", "read_logs", "summarize", "draft_patch"],
                "approval_required_for": [
                    "external_write",
                    "database_write",
                    "git_push",
                    "production_config_change",
                    "provider_account_change",
                ],
                "success_criteria": [
                    "task scope bounded",
                    "required evidence identified",
                    "local verification plan attached",
                    "chronicle summary generated",
                ],
                "dry_run": True,
            }
            inputs = envelope["inputs"]
            budget = envelope["context_budget"]
        economized = {
            "beast_object_type": "economized_task_envelope",
            "version": "1.0",
            "task_id": envelope.get("task_id"),
            "intent": self._truncate(envelope.get("intent") or inputs.get("user_request") or task, 260),
            "task_class": envelope.get("task_class") or task_class or local_analysis.get("task_type"),
            "provider": inputs.get("provider") or provider or "local_ollama_scout",
            "risk_level": envelope.get("risk_level") or local_analysis.get("risk"),
            "privacy_class": envelope.get("privacy_class") or local_analysis.get("privacy_level"),
            "context_budget": {
                "max_tokens": budget.get("max_tokens", 8000),
                "max_files": budget.get("max_files", 8),
                "allow_full_files": bool(budget.get("allow_full_files", False)),
            },
            "allowed_actions": list(envelope.get("allowed_actions") or [])[:8],
            "approval_required_for": list(envelope.get("approval_required_for") or [])[:8],
            "success_criteria": list(envelope.get("success_criteria") or [])[:6],
            "local_decision_seed": {
                "task_type": local_analysis.get("task_type"),
                "risk": local_analysis.get("risk"),
                "privacy_level": local_analysis.get("privacy_level"),
                "needed_tools": (local_analysis.get("needed_tools") or [])[:6],
                "relevant_files": (local_analysis.get("relevant_files") or [])[:6],
            },
        }
        contract = {
            "beast_object_type": "compression_contract",
            "version": "1.0",
            "primary_input": "economized_task_envelope",
            "preserved": ["intent", "task_class", "risk_level", "privacy_class", "context_budget", "allowed_actions", "approval_required_for", "success_criteria"],
            "pruned": ["raw_logs", "full_file_contents", "secret_values", "unbounded_history"],
            "supporting_inputs": ["ranked_chunks", "tool_menu", "chronicle_summary", "forensic_context"],
        }
        return {
            "task_envelope": envelope,
            "economized_task_envelope": economized,
            "compression_contract": contract,
        }

    def _call_ollama(
        self,
        packet: Dict[str, Any],
        model: str,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        self._last_ollama_error = ""
        scout_view = self._scout_view(packet)
        prompt = (
            "You are BEAST's local Ollama scout for coding-environment optimization. "
            "The economized_task_envelope is the primary input; do not infer from raw chat when the envelope differs. "
            "Use retrieved chunks, tools, Chronicle, and forensic context only as supporting evidence. "
            "Return only JSON matching the schema.\n\n"
            + json.dumps(scout_view, separators=(",", ":"), default=str)
        )
        prompt = self._truncate(prompt, self.max_prompt_chars)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": SCOUT_SCHEMA,
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 128},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=max(0.01, float(timeout_seconds or self.timeout_seconds)),
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            try:
                data = json.loads(content)
            except Exception as exc:
                self._last_ollama_error = f"ollama returned unstructured scout text: {exc}"
                return self._coerce_ollama_text_decision(packet, content)
            data["source"] = "ollama"
            data.setdefault("role_hints", self._role_hints(
                str(data.get("task_type") or "general"),
                str(data.get("risk") or "medium"),
                data.get("needed_tools") or [],
            ))
            return data
        except Exception as exc:
            self._last_ollama_error = str(exc)
            return None

    def _coerce_ollama_text_decision(self, packet: Dict[str, Any], content: str) -> Dict[str, Any]:
        decision = dict(packet.get("local_analysis") or {})
        summary = self._truncate(str(content or "").strip(), 420)
        decision["source"] = "ollama_unstructured"
        decision["summary"] = summary or decision.get("summary") or "Ollama responded without valid scout JSON."
        decision.setdefault("confidence", 0.5)
        return decision

    def _decision_contract(self, decision: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
        risk = str(decision.get("risk") or "medium").lower()
        privacy = str(decision.get("privacy_level") or "redacted_cloud_ok")
        needs_cloud = bool(decision.get("needs_cloud", risk != "low"))
        redaction_required = bool(decision.get("redaction_required") or privacy == "local_only")
        role_hints = decision.get("role_hints") or self._role_hints(
            str(decision.get("task_type") or "general"),
            risk,
            decision.get("needed_tools") or [],
        )
        if privacy == "local_only":
            cloud_handoff = "blocked"
        elif needs_cloud:
            cloud_handoff = "redacted_allowed" if redaction_required else "allowed"
        else:
            cloud_handoff = "not_needed"
        return {
            "beast_object_type": "ollama_local_decision_contract",
            "version": "1.0",
            "source": decision.get("source", "edgek_fallback"),
            "task_type": decision.get("task_type", "general"),
            "risk": risk,
            "privacy_level": privacy,
            "needs_cloud": needs_cloud,
            "cloud_handoff": cloud_handoff,
            "redaction_required": redaction_required,
            "recommended_profile": self._recommended_profile(risk, privacy, decision),
            "selected_tools": (decision.get("needed_tools") or [])[:8],
            "relevant_files": (decision.get("relevant_files") or [])[:8],
            "role_hints": role_hints,
            "confidence": float(decision.get("confidence") or 0.0),
            "memory_available": bool((packet.get("memory_state") or {}).get("available")),
            "packet_hash": packet.get("handoff_hash", ""),
        }

    def _recommended_profile(self, risk: str, privacy: str, decision: Dict[str, Any]) -> str:
        task_type = str(decision.get("task_type") or "").lower()
        if privacy == "local_only" or risk == "high":
            return "openclaw"
        if "plan" in task_type or not decision.get("needed_tools"):
            return "zeroclaw"
        return "openclaw"

    def _role_hints(self, task_type: str, risk: str, tools: List[str]) -> List[str]:
        hints = ["cartographer", "compressor"]
        lowered_tools = " ".join(str(tool).lower() for tool in tools)
        lowered_type = str(task_type).lower()
        if risk in ("medium", "high") or any(word in lowered_type for word in ("security", "secret", "credential")):
            hints.append("sentinel")
        if any(word in lowered_type for word in ("test", "bug", "failure", "code", "refactor")):
            hints.append("verifier")
        if "compress" in lowered_tools or "context" in lowered_tools:
            hints.append("compressor")
        hints.append("scribe")
        if risk == "high" or "failure" in lowered_type:
            hints.append("critic")
        return list(dict.fromkeys(hints))

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

    def _forensic_context(
        self,
        task: str,
        *,
        limit: int = 5,
        layer: Optional[str] = None,
        event_kind: Optional[str] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.forensic_memory:
            return {"available": False, "source": "none"}
        try:
            result = self.forensic_memory.query(
                query=task,
                event_kind=event_kind,
                layer=layer,
                provider=provider,
                status=status,
                limit=limit,
            )
        except Exception as exc:
            return {"available": False, "source": "forensic_l4", "error": str(exc)}
        rows = result.get("results", []) if isinstance(result, dict) else []
        compact = []
        for item in rows[:limit]:
            evidence = item.get("evidence") or {}
            event = item.get("event") or {}
            compact.append({
                "event_id": item.get("event_id"),
                "event_kind": item.get("event_kind"),
                "layer": item.get("layer") or evidence.get("interception_layer"),
                "provider": item.get("provider"),
                "status": item.get("status"),
                "severity": item.get("severity"),
                "priority_score": item.get("priority_score"),
                "lexical_score": item.get("lexical_score"),
                "source_uri": item.get("source_uri"),
                "summary": self._truncate(evidence.get("summary") or event.get("summary") or event.get("message"), 220),
                "signals": (evidence.get("signals") or [])[:8],
                "recommended_actions": (evidence.get("recommended_actions") or [])[:4],
            })
        return {
            "available": True,
            "source": "forensic_l4",
            "retrieval_mode": result.get("retrieval_mode"),
            "vector_available": bool(result.get("vector_available")),
            "filters": result.get("filters", {}),
            "result_count": result.get("result_count", len(compact)),
            "results": compact,
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
            "agent_awareness": packet.get("agent_awareness", {}),
            "economized_task_envelope": packet.get("economized_task_envelope", {}),
            "compression_contract": packet.get("compression_contract", {}),
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
            "ranked_chunks": packet.get("ranked_chunks", [])[:6],
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
            "forensic_context": {
                "available": bool((packet.get("forensic_context") or {}).get("available")),
                "source": (packet.get("forensic_context") or {}).get("source"),
                "retrieval_mode": (packet.get("forensic_context") or {}).get("retrieval_mode"),
                "result_count": (packet.get("forensic_context") or {}).get("result_count", 0),
                "results": (packet.get("forensic_context") or {}).get("results", [])[:4],
            },
            "chronicle_summary": {
                "available": bool((packet.get("chronicle_summary") or {}).get("available")),
                "record_count": (packet.get("chronicle_summary") or {}).get("record_count", 0),
                "summary": (packet.get("chronicle_summary") or {}).get("summary"),
                "records": (packet.get("chronicle_summary") or {}).get("records", [])[:4],
            },
            "fallback_recommendations": packet.get("fallback_recommendations", [])[:6],
            "constraints": packet.get("constraints", []),
            "packet_stats": packet.get("packet_stats", {}),
            "decision_contract": packet.get("decision_contract", {}),
        }

    def _packet_stats(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        full = json.dumps({key: value for key, value in packet.items() if key != "ollama"}, default=str)
        scout_view = json.dumps(self._scout_view({**packet, "packet_stats": {}}), default=str)
        return {
            "full_packet_chars": len(full),
            "ollama_scout_view_chars": len(scout_view),
            "ollama_prompt_char_limit": self.max_prompt_chars,
            "economized_task_envelope_chars": len(json.dumps(packet.get("economized_task_envelope", {}), default=str)),
            "retrieved_chunks": len(packet.get("retrieved_chunks", [])),
            "ranked_chunks": len(packet.get("ranked_chunks", [])),
            "exact_context_items": len(packet.get("exact_context", [])),
            "forensic_results": int((packet.get("forensic_context") or {}).get("result_count") or 0),
            "chronicle_records": int((packet.get("chronicle_summary") or {}).get("record_count") or 0),
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

    def _tokens(self, text: str) -> List[str]:
        return [
            token.lower()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", text or "")
            if len(token) >= 3
        ][:24]
