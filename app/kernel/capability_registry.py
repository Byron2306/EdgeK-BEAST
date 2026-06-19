"""
BEAST capability registry.

First-pass governed inventory for plugins, skills, tools, workflows, routes,
parsers, linters, databases, providers, and CLI surfaces.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.kernel.provider_registry import ProviderRegistry


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
            ("mcp_tool:beast_openclaw_plan", "beast_openclaw_plan", "agentic_cli", "low", False),
            ("mcp_tool:beast_openclaw_execute", "beast_openclaw_execute", "agentic_cli", "medium", True),
            ("mcp_tool:beast_mcp_status", "beast_mcp_status", "tool_bus", "low", False),
            ("mcp_tool:beast_mcp_tool_catalog", "beast_mcp_tool_catalog", "tool_bus", "low", False),
            ("mcp_tool:beast_validate_canon", "beast_validate_canon", "canon", "low", False),
            ("mcp_tool:beast_check_promotion", "beast_check_promotion", "promotion", "medium", False),
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
