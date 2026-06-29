"""
BEAST capability registry.

First-pass governed inventory for plugins, skills, tools, workflows, routes,
parsers, linters, databases, providers, and CLI surfaces.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.kernel.registry.provider_registry import ProviderRegistry


@dataclass
class CapabilityRecord:
    capability_id: str
    kind: str
    name: str
    command: Optional[str] = None
    endpoint: Optional[str] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = False
    read_only: bool = True
    writes_files: bool = False
    network_access: bool = False
    secret_envs: List[str] = field(default_factory=list)
    health_check: Optional[str] = None
    test_command: Optional[str] = None
    owner: str = "beast"
    promotion_status: str = "observed"
    status: str = "available"
    metadata: Dict[str, Any] = field(default_factory=dict)
    family: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CapabilityRegistry:
    """Build a local-first inventory of governed BEAST capabilities."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None, skill_tree: Any = None):
        self.policies = policies or {}
        self.skill_tree = skill_tree
        self.provider_registry = ProviderRegistry(self.policies)

    def list_capabilities(self, kind: Optional[str] = None) -> Dict[str, Any]:
        records = []
        records.extend(self._provider_capabilities())
        records.extend(self._tool_capabilities())
        records.extend(self._cli_capabilities())
        records.extend(self._mcp_tool_capabilities())
        records.extend(self._workflow_capabilities())
        records.extend(self._route_capabilities())
        records.extend(self._parser_capabilities())
        records.extend(self._linter_capabilities())
        records.extend(self._database_capabilities())
        records.extend(self._plugin_capabilities())
        records.extend(self._skill_capabilities())
        if kind:
            records = [item for item in records if item.kind == kind]
        grouped: Dict[str, int] = {}
        for item in records:
            grouped[item.kind] = grouped.get(item.kind, 0) + 1
        return {
            "beast_object_type": "capability_inventory",
            "version": "1.0",
            "count": len(records),
            "kinds": grouped,
            "families": self._family_counts(records),
            "capabilities": [item.to_dict() for item in records],
        }

    def list_families(self) -> Dict[str, Any]:
        inventory = self.list_capabilities()
        records = inventory["capabilities"]
        families: Dict[str, Dict[str, Any]] = {}
        for item in records:
            family = item.get("family") or "general"
            bucket = families.setdefault(family, {"count": 0, "kinds": {}, "capability_ids": []})
            bucket["count"] += 1
            bucket["kinds"][item["kind"]] = bucket["kinds"].get(item["kind"], 0) + 1
            bucket["capability_ids"].append(item["capability_id"])
        return {
            "beast_object_type": "capability_family_inventory",
            "version": "1.0",
            "count": len(families),
            "families": families,
        }

    def discovery_sources(
        self,
        *,
        include_inventory: bool = True,
        include_open_source_mcp: bool = True,
    ) -> Dict[str, Any]:
        """Export capability inventory as Commons discovery sources.

        CapabilityRegistry is the "what exists" map; Meta Tool Commons is the
        "what should be tried/promoted" layer. This adapter lets the static map
        feed Commons without granting execution authority.
        """
        sources: List[Dict[str, Any]] = []
        if include_inventory:
            inventory = self.list_capabilities()
            items = []
            for item in inventory.get("capabilities", []):
                capability_id = str(item.get("capability_id") or "")
                if not capability_id:
                    continue
                items.append({
                    "name": capability_id.replace(":", "_"),
                    "tool_id": capability_id,
                    "description": self._capability_description(item),
                    "inputSchema": item.get("input_schema") or {},
                    "category": item.get("family") or item.get("kind") or "capability_registry",
                    "role": self._role_for_capability(item),
                    "risk_class": self._risk_class(item.get("risk_level")),
                    "version": "capability-registry-v1",
                })
            sources.append({
                "source_type": "mcp_tool_catalog",
                "source_id": "beast_capability_registry",
                "trust_level": "local",
                "items": items,
            })
        if include_open_source_mcp:
            sources.append({
                "source_type": "mcp_tool_catalog",
                "source_id": "open_source_mcp_seed_catalog",
                "trust_level": "retrieved",
                "items": self.open_source_mcp_seed_items(),
            })
        return {
            "beast_object_type": "capability_registry_discovery_sources",
            "version": "1.0",
            "source_count": len(sources),
            "sources": sources,
            "authority": "inventory_and_public_catalog_metadata_only_no_execution",
        }

    @staticmethod
    def open_source_mcp_seed_items() -> List[Dict[str, Any]]:
        """Return generic open-source MCP tool shapes for guarded discovery.

        These are intentionally conservative metadata seeds. Installing or
        executing any real server remains a separate governed plugin/MCP step.
        """
        return [
            {
                "name": "mcp_filesystem_read",
                "description": "Bounded local filesystem read/list/search through an allowlisted MCP root.",
                "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}}},
                "category": "filesystem",
                "role": "context_reader",
                "risk_class": "low",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_filesystem_write",
                "description": "Governed file creation or patch application inside an allowlisted MCP root.",
                "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content_hash": {"type": "string"}}},
                "category": "filesystem",
                "role": "patch_writer",
                "risk_class": "high",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_git_status_diff",
                "description": "Read git status, branch, log, and diff metadata for local repository reasoning.",
                "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "rev": {"type": "string"}}},
                "category": "version_control",
                "role": "repo_cartographer",
                "risk_class": "low",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_github_pr_issues",
                "description": "Inspect GitHub issues, pull requests, checks, and code review metadata.",
                "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "number": {"type": "integer"}}},
                "category": "github",
                "role": "remote_repo_reader",
                "risk_class": "medium",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_sqlite_readonly",
                "description": "Explore SQLite schema and run safe read-only queries with limits.",
                "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}},
                "category": "database",
                "role": "data_reader",
                "risk_class": "medium",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_postgres_readonly",
                "description": "Explore Postgres schema and run safe read-only queries through an approved DSN.",
                "inputSchema": {"type": "object", "properties": {"dsn_env": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}},
                "category": "database",
                "role": "data_reader",
                "risk_class": "high",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_playwright_inspect",
                "description": "Inspect browser pages, DOM state, screenshots, and accessibility trees.",
                "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "action": {"type": "string"}}},
                "category": "browser",
                "role": "ui_verifier",
                "risk_class": "medium",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_fetch_docs",
                "description": "Fetch and summarize documentation pages with bounded retrieval and citation metadata.",
                "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}}},
                "category": "retrieval",
                "role": "docs_retriever",
                "risk_class": "medium",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_markitdown_convert",
                "description": "Convert local or remote documents into Markdown for downstream summarization.",
                "inputSchema": {"type": "object", "properties": {"source": {"type": "string"}, "source_hash": {"type": "string"}}},
                "category": "document_conversion",
                "role": "document_normalizer",
                "risk_class": "medium",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_memory_search",
                "description": "Search local memory, notes, or vector-store records for reusable context.",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}},
                "category": "memory",
                "role": "memory_retriever",
                "risk_class": "low",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_lsp_symbol_search",
                "description": "Use language-server indexes for symbol search, references, definitions, and diagnostics.",
                "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}, "language": {"type": "string"}}},
                "category": "code_intelligence",
                "role": "code_cartographer",
                "risk_class": "low",
                "version": "open-source-mcp-seed-v1",
            },
            {
                "name": "mcp_shell_dry_run",
                "description": "Prepare shell commands for review and dry-run validation without autonomous execution.",
                "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}, "working_dir": {"type": "string"}}},
                "category": "command_planning",
                "role": "command_planner",
                "risk_class": "high",
                "version": "open-source-mcp-seed-v1",
            },
        ]

    @staticmethod
    def _risk_class(value: Any) -> str:
        risk = str(value or "medium").lower()
        return risk if risk in {"low", "medium", "high", "critical"} else "medium"

    @staticmethod
    def _role_for_capability(item: Dict[str, Any]) -> str:
        family = str(item.get("family") or "")
        kind = str(item.get("kind") or "")
        if family in {"parsing", "debugging", "lint_syntax", "quality"}:
            return "verifier"
        if family in {"routing", "provider", "tool_bus"}:
            return "router"
        if kind in {"workflow", "cli", "mcp_tool"}:
            return "orchestrator"
        return "tool_router"

    @staticmethod
    def _capability_description(item: Dict[str, Any]) -> str:
        bits = [
            f"{item.get('kind') or 'capability'} capability {item.get('name') or item.get('capability_id')}",
            f"family={item.get('family') or 'general'}",
            f"read_only={bool(item.get('read_only', True))}",
            f"requires_approval={bool(item.get('requires_approval', False))}",
        ]
        return "; ".join(bits)

    def _provider_capabilities(self) -> List[CapabilityRecord]:
        records = []
        for provider in self.provider_registry.records(include_disabled=True):
            records.append(CapabilityRecord(
                capability_id=f"provider:{provider.provider_id}",
                kind="provider",
                name=provider.provider_id,
                endpoint=provider.proxy_path,
                risk_level="medium",
                network_access=provider.backend != "ollama",
                secret_envs=list(provider.env),
                health_check="/edgek/providers/registry",
                metadata={
                    "backend": provider.backend,
                    "enabled": provider.enabled,
                    "proxy_path": provider.proxy_path,
                    "managed_by": provider.managed_by,
                    "native_adapter": provider.native_adapter,
                    "openai_compatible": provider.openai_compatible,
                },
                status="available" if provider.enabled else "disabled",
                family="provider",
            ))
        return records

    def _tool_capabilities(self) -> List[CapabilityRecord]:
        tools = [
            ("tool:semantic_interceptor", "semantic_tool_interceptor", "/edgek/tools/intercept", "low", False),
            ("tool:compression_prune", "token_pruning", "/edgek/compression/prune", "low", False),
            ("tool:mcp_evaluate", "mcp_evaluate", "/edgek/mcp/evaluate", "medium", False),
            ("tool:mcp_execute", "mcp_execute", "/edgek/mcp/execute", "medium", True),
        ]
        return [
            CapabilityRecord(
                capability_id=capability_id,
                kind="tool",
                name=name,
                endpoint=endpoint,
                risk_level=risk,
                requires_approval=approval,
                read_only=not approval,
                health_check="/edgek/tools/integrations",
                family="tool_bus",
            )
            for capability_id, name, endpoint, risk, approval in tools
        ]

    def _cli_capabilities(self) -> List[CapabilityRecord]:
        commands = [
            ("cli:doctor", "beast_doctor", "beast doctor", "diagnostics", "low", False),
            ("cli:diagnose", "beast_diagnose", "beast diagnose", "diagnostics", "low", False),
            ("cli:route", "beast_route", "beast route", "routing", "low", False),
            ("cli:verify", "beast_verify", "beast verify", "quality", "low", False),
            ("cli:chronicle", "beast_chronicle", "beast chronicle", "chronicle", "low", False),
            ("cli:promote", "beast_promote", "beast promote", "promotion", "medium", True),
            ("cli:handoff_prepare", "beast_handoff_prepare", "beast handoff-prepare", "handoff", "medium", False),
            ("cli:openclaw_plan", "openclaw_plan", "beast openclaw-plan", "agentic_cli", "low", False),
            ("cli:openclaw_execute", "openclaw_execute", "beast openclaw-execute", "agentic_cli", "medium", True),
            ("cli:nemoclaw_plan", "nemoclaw_plan", "beast nemoclaw-plan", "agentic_cli", "medium", False),
            ("cli:nemoclaw_execute", "nemoclaw_execute", "beast nemoclaw-execute", "agentic_cli", "high", True),
            ("cli:zeroclaw_plan", "zeroclaw_plan", "beast zeroclaw-plan", "agentic_cli", "low", False),
            ("cli:hermes_plan", "hermes_plan", "beast hermes-plan", "swarm", "low", False),
            ("cli:hermes_execute", "hermes_execute", "beast hermes-execute", "swarm", "medium", True),
        ]
        return [
            CapabilityRecord(
                capability_id=capability_id,
                kind="cli",
                name=name,
                command=command,
                risk_level=risk,
                requires_approval=approval,
                read_only=not approval,
                writes_files=False,
                health_check="beast doctor",
                test_command="pytest -q test_beast_cli_script.py test_beast_cli_executor.py",
                family=family,
            )
            for capability_id, name, command, family, risk, approval in commands
        ]

    def _mcp_tool_capabilities(self) -> List[CapabilityRecord]:
        tools = [
            ("mcp_tool:beast_session_handshake", "beast_session_handshake", "agentic_cli", "low", False),
            ("mcp_tool:beast_openclaw_plan", "beast_openclaw_plan", "agentic_cli", "low", False),
            ("mcp_tool:beast_openclaw_execute", "beast_openclaw_execute", "agentic_cli", "medium", True),
            ("mcp_tool:beast_mcp_status", "beast_mcp_status", "tool_bus", "low", False),
            ("mcp_tool:beast_mcp_tool_catalog", "beast_mcp_tool_catalog", "tool_bus", "low", False),
            ("mcp_tool:beast_validate_canon", "beast_validate_canon", "canon", "low", False),
            ("mcp_tool:beast_check_promotion", "beast_check_promotion", "promotion", "medium", False),
            ("mcp_tool:beast_capability_exchange", "beast_capability_exchange", "learning", "medium", True),
            ("mcp_tool:beast_meta_tool_commons", "beast_meta_tool_commons", "learning", "medium", True),
            ("mcp_tool:beast_compute_shadow", "beast_compute_shadow", "compute_governance", "low", False),
        ]
        return [
            CapabilityRecord(
                capability_id=capability_id,
                kind="mcp_tool",
                name=name,
                endpoint="mcp://edgek-beast",
                risk_level=risk,
                requires_approval=approval,
                read_only=not approval,
                family=family,
                health_check="/edgek/mcp/status",
            )
            for capability_id, name, family, risk, approval in tools
        ]

    def _workflow_capabilities(self) -> List[CapabilityRecord]:
        return [
            CapabilityRecord("workflow:provider_diagnostic", "workflow", "provider_diagnostic", endpoint="/edgek/task/provider-diagnostic", risk_level="low", family="diagnostics"),
            CapabilityRecord("workflow:quality_cascade", "workflow", "quality_cascade", endpoint="/edgek/task/quality-cascade", risk_level="low", family="quality"),
            CapabilityRecord("workflow:quality_run", "workflow", "quality_run", endpoint="/edgek/quality/run", risk_level="low", family="quality"),
            CapabilityRecord("workflow:conductor_plan", "workflow", "conductor_plan", endpoint="/edgek/workflow/plan", risk_level="low", family="handoff"),
            CapabilityRecord("workflow:conductor_workflow_card", "workflow", "conductor_workflow_card", endpoint="/edgek/conductor/workflow-card", risk_level="low", family="handoff"),
            CapabilityRecord("workflow:chronicle_publish", "workflow", "chronicle_publish", endpoint="/edgek/chronicle/publish", risk_level="medium", requires_approval=True, network_access=True, family="chronicle"),
            CapabilityRecord("workflow:forge_decision", "workflow", "forge_decision", endpoint="/edgek/forge/decision", risk_level="low", family="forge"),
            CapabilityRecord("workflow:handoff_prepare", "workflow", "handoff_prepare", endpoint="/edgek/handoff/prepare", risk_level="medium", family="handoff"),
            CapabilityRecord("workflow:prec_lifecycle", "workflow", "prec_lifecycle", endpoint="/edgek/prec/lifecycle", risk_level="low", family="governance"),
            CapabilityRecord("workflow:test_failure_cascade", "workflow", "test_failure_cascade", endpoint="/edgek/task/quality-cascade", risk_level="low", family="debugging"),
            CapabilityRecord("workflow:dashboard_widget_cascade", "workflow", "dashboard_widget_cascade", endpoint="/edgek/task/quality-cascade", risk_level="low", family="quality"),
            CapabilityRecord("workflow:mcp_install", "workflow", "mcp_install", command="beast mcp-install", risk_level="medium", read_only=False, writes_files=True, family="tool_bus"),
            CapabilityRecord("workflow:provider_proxy_setup", "workflow", "provider_proxy_setup", endpoint="/edgek/providers/state", risk_level="medium", read_only=False, network_access=True, family="provider"),
        ]

    def _route_capabilities(self) -> List[CapabilityRecord]:
        return [
            CapabilityRecord("route:provider_diagnostic", "route", "provider_diagnostic_route", endpoint="/edgek/route/provider-diagnostic/{provider}", risk_level="low", family="diagnostics"),
            CapabilityRecord("route:pathfinder_route_card", "route", "pathfinder_route_card", endpoint="/edgek/pathfinder/route-card", risk_level="low", family="routing"),
            CapabilityRecord("route:route_cards", "route", "route_cards", endpoint="/edgek/route/cards", risk_level="low", family="routing"),
        ]

    def _parser_capabilities(self) -> List[CapabilityRecord]:
        return [
            CapabilityRecord("parser:tree_sitter", "parser", "tree_sitter", risk_level="low", metadata={"languages": ["python", "javascript", "typescript", "java", "c", "cpp"]}, family="parsing"),
            CapabilityRecord("parser:python_ast", "parser", "python_ast", endpoint="/edgek/compression/python", risk_level="low", family="parsing"),
            CapabilityRecord("parser:json_yaml_toml", "parser", "structured_config", risk_level="low", family="parsing"),
            CapabilityRecord("parser:markdown_sections", "parser", "markdown_sections", risk_level="low", family="parsing"),
            CapabilityRecord("parser:openapi", "parser", "openapi_schema", risk_level="low", family="parsing", promotion_status="candidate"),
            CapabilityRecord("parser:sql_schema", "parser", "sql_schema", command="psql", risk_level="medium", family="database", promotion_status="candidate"),
        ]

    def _linter_capabilities(self) -> List[CapabilityRecord]:
        checks = [
            ("linter:py_compile", "python_py_compile", "python3 -m py_compile", "low"),
            ("linter:pytest_collect", "pytest_collect", "pytest --collect-only", "low"),
            ("linter:eslint", "eslint", "eslint", "medium"),
            ("linter:tsc", "typescript", "tsc --noEmit", "medium"),
            ("linter:shellcheck", "shellcheck", "shellcheck", "medium"),
        ]
        return [
            CapabilityRecord(
                capability_id=capability_id,
                kind="linter",
                name=name,
                command=command,
                risk_level=risk,
                status="available" if shutil.which(command.split()[0]) else "missing",
                family="lint_syntax",
            )
            for capability_id, name, command, risk in checks
        ] + [
            CapabilityRecord("tool:pytest_failure_parser", "tool", "pytest_failure_parser", risk_level="low", family="debugging", promotion_status="candidate"),
            CapabilityRecord("tool:stack_trace_classifier", "tool", "stack_trace_classifier", risk_level="low", family="debugging", promotion_status="candidate"),
            CapabilityRecord("tool:log_signature_matcher", "tool", "log_signature_matcher", risk_level="low", family="debugging", promotion_status="candidate"),
        ]

    def _database_capabilities(self) -> List[CapabilityRecord]:
        return [
            CapabilityRecord("database:sqlite", "database", "sqlite", risk_level="medium", read_only=True, metadata={"local": True}, family="database"),
            CapabilityRecord("database:postgres_readonly", "database", "postgres_readonly", command="psql", risk_level="high", requires_approval=True, secret_envs=["POSTGRES_DSN"], status="available" if shutil.which("psql") else "missing", family="database"),
            CapabilityRecord("database:sqlite_local_embeddings", "database", "sqlite_local_embeddings", endpoint="/edgek/vector/adapters", risk_level="low", promotion_status="observed", family="vector"),
            CapabilityRecord("database:pgvector", "database", "pgvector", endpoint="/edgek/vector/adapters", risk_level="medium", promotion_status="candidate", family="vector"),
            CapabilityRecord("database:qdrant", "database", "qdrant", endpoint="/edgek/vector/adapters", risk_level="medium", network_access=True, promotion_status="candidate", family="vector"),
            CapabilityRecord("database:chroma", "database", "chroma", endpoint="/edgek/vector/adapters", risk_level="medium", promotion_status="candidate", family="vector"),
            CapabilityRecord("database:lancedb_duckdb_parquet", "database", "lancedb_duckdb_parquet", endpoint="/edgek/vector/adapters", risk_level="medium", promotion_status="candidate", family="vector"),
            CapabilityRecord("database:vector_store_health", "database", "vector_store_health", endpoint="/edgek/workspace/semantic-context", risk_level="low", family="vector", promotion_status="candidate"),
        ]

    def _plugin_capabilities(self) -> List[CapabilityRecord]:
        return [
            CapabilityRecord("plugin:github", "plugin", "GitHub", risk_level="medium", network_access=True, secret_envs=["GITHUB_TOKEN"], promotion_status="observed", family="plugin"),
            CapabilityRecord("plugin:gmail", "plugin", "Gmail", risk_level="medium", network_access=True, promotion_status="observed", family="plugin"),
            CapabilityRecord("plugin:provider_economist", "plugin", "Provider Economist", endpoint="/edgek/provider-economist/select", risk_level="low", promotion_status="candidate", family="plugin"),
            CapabilityRecord("plugin:tool_laziness_mcp", "plugin", "Tool Laziness MCP", endpoint="/edgek/tool-laziness/recommend-tools", risk_level="low", promotion_status="candidate", family="plugin"),
            CapabilityRecord("plugin:opentelemetry", "plugin", "OpenTelemetry Connector", endpoint="/edgek/connectors/otel/export", risk_level="medium", network_access=True, requires_approval=True, promotion_status="candidate", family="observability"),
            CapabilityRecord("plugin:marketplace", "plugin", "Extension Marketplace", endpoint="/edgek/plugins", risk_level="medium", writes_files=True, requires_approval=True, read_only=False, promotion_status="candidate", family="plugin"),
            CapabilityRecord("plugin:capability_exchange", "plugin", "Capability Exchange", endpoint="/edgek/capability-exchange", risk_level="medium", network_access=True, writes_files=True, requires_approval=True, read_only=False, promotion_status="candidate", family="learning"),
            CapabilityRecord("plugin:meta_tool_commons", "plugin", "Meta Tool Commons", endpoint="/edgek/meta-tool-commons", risk_level="medium", writes_files=True, requires_approval=True, read_only=False, promotion_status="candidate", family="learning"),
            CapabilityRecord("plugin:inference_compute_governor", "plugin", "Inference Compute Governor", endpoint="/edgek/compute", risk_level="low", read_only=True, promotion_status="observed", family="compute_governance"),
        ]

    def _skill_capabilities(self) -> List[CapabilityRecord]:
        records = [
            CapabilityRecord("skill:agent_memory_systems", "skill", "agent-memory-systems", risk_level="low", promotion_status="observed", family="skill"),
            CapabilityRecord("skill:ai_agent_development", "skill", "ai-agent-development", risk_level="low", promotion_status="observed", family="skill"),
        ]
        if self.skill_tree:
            try:
                state = self.skill_tree.state()
                records.append(CapabilityRecord(
                    "skill:learned_registry",
                    "skill",
                    "learned_skill_registry",
                    endpoint="/edgek/skills",
                    risk_level="low",
                    metadata=state.get("skills", {}),
                    promotion_status="observed",
                    family="skill",
                ))
            except Exception:
                pass
        return records

    def _family_counts(self, records: List[CapabilityRecord]) -> Dict[str, int]:
        grouped: Dict[str, int] = {}
        for item in records:
            grouped[item.family] = grouped.get(item.family, 0) + 1
        return grouped
