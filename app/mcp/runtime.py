"""Shared BEAST MCP tool runtime used by both HTTP and stdio transports."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.reason import reasoner
from app.kernel.runtime import runtime_governor
from app.kernel.crystallize import crystallizer
from app.kernel.task_envelope import TaskEnvelopeBuilder
from app.kernel.context_packet import ContextPacketBuilder
from app.kernel.canon_registry import CanonRegistry
from app.kernel.forge_scorecard import ForgeScorecardBuilder
from app.kernel.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.promotion_loop import PromotionLoop
from app.kernel.beast_cli_executor import BeastCLIExecutor
from app.kernel.ollama_scout import OllamaScout
from app.kernel.swarm import swarm_kernel
from app.kernel.skill_tree import skill_tree
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.provider_economist import EconomistPolicy, ProviderEconomist
from app.kernel.otel_connector import OpenTelemetryConnector
from app.kernel.plugin_marketplace import PluginMarketplace
from app.kernel.session_handshake import SessionHandshakeBuilder
from app.kernel.capability_exchange import CapabilityExchange
from app.kernel.meta_tool_commons import MetaToolCommons
from app.kernel.inference_interceptor import compute_ledger
from app.kernel.outcome_evidence import default_outcome_store
from app.kernel.network_chronicle import NetworkChronicleConnector
from app.kernel.github_pr_connector import GitHubPRConnector
from app.cli.api import BeastApiClient
from app.mcp.broker import MCPBroker

logger = logging.getLogger(__name__)


class BeastToolRuntime:
    def __init__(self) -> None:
        self.workspace_root = os.environ.get("BEAST_WORKSPACE", ".")
        self.task_envelope_builder = TaskEnvelopeBuilder(
            reasoner.policies,
            runtime_governor=runtime_governor,
        )
        self.network_chronicle_connector = NetworkChronicleConnector()
        self.github_pr_connector = GitHubPRConnector(task_envelope_builder=self.task_envelope_builder)
        self.context_packet_builder = ContextPacketBuilder(
            workspace_graph=crystallizer.workspace_graph,
        )
        self.canon_registry = CanonRegistry()
        self.forge_scorecard_builder = ForgeScorecardBuilder()
        self.conductor_workflow_builder = ConductorWorkflowBuilder(swarm_kernel=swarm_kernel)
        self.tool_laziness_learner = ToolLazinessLearner()
        self.tool_laziness_plugin = ToolLazinessPlugin(self.tool_laziness_learner)
        self.provider_economist = ProviderEconomist()
        self.crystal_compute_store = default_outcome_store()
        self.otel_connector = OpenTelemetryConnector()
        self.plugin_marketplace = PluginMarketplace()
        self.session_handshake_builder = SessionHandshakeBuilder()
        self.capability_exchange = CapabilityExchange()
        self.meta_tool_commons = MetaToolCommons(
            exchange=self.capability_exchange, skill_registry=skill_tree.skill_registry
        )
        self.mcp_broker = MCPBroker(reasoner.policies, workspace_graph=crystallizer.workspace_graph)
        self.ollama_scout = OllamaScout(crystallizer.workspace_graph, self.mcp_broker, reasoner.policies)
        self.beast_cli_executor = BeastCLIExecutor(
            ollama_scout=self.ollama_scout,
            mcp_broker=self.mcp_broker,
            canon_registry=self.canon_registry,
            runtime_governor=runtime_governor,
            tool_laziness_learner=self.tool_laziness_learner,
            tool_laziness_plugin=self.tool_laziness_plugin,
            provider_economist=self.provider_economist,
            handshake_builder=self.session_handshake_builder,
        )
        self.promotion_loop = PromotionLoop(
            task_envelope_builder=self.task_envelope_builder,
            conductor_workflow_builder=self.conductor_workflow_builder,
            canon_registry=self.canon_registry,
            tool_laziness_learner=self.tool_laziness_learner,
            skill_registry=skill_tree.skill_registry,
        )
        self.beast_api = BeastApiClient()

    def _workspace_root(self, override: Optional[str] = None) -> str:
        value = override or self.workspace_root or "."
        return str(Path(value).resolve())

    def tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "beast_prepare_task",
                "description": "Prepare a canonical BEAST task envelope from a user request.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_request": {"type": "string"},
                        "provider": {"type": "string"},
                        "task_class": {"type": "string"},
                        "project": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["user_request"],
                },
            },
            {
                "name": "beast_run_quality_cascade",
                "description": "Run the local Quality Cascade before cloud escalation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "envelope": {"type": "object"},
                        "provider": {"type": "string"},
                        "workspace_root": {"type": "string"},
                    },
                    "required": ["envelope", "provider"],
                },
            },
            {
                "name": "beast_run_maintenance_cascade",
                "description": "Run repo hygiene checks: compile, pytest collection, dependency sanity, docs links, and extension syntax.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_root": {"type": "string"},
                        "run_tests": {"type": "boolean", "default": False},
                        "pytest_args": {"type": "array", "items": {"type": "string"}},
                        "include_extension_checks": {"type": "boolean", "default": True},
                        "include_markdown": {"type": "boolean", "default": True},
                        "run_packaging": {"type": "boolean", "default": False},
                        "python_versions": {"type": "array", "items": {"type": "string"}},
                        "timeout_seconds": {"type": "integer", "default": 60},
                    },
                },
            },
            {
                "name": "beast_prepare_handoff",
                "description": "Build a bounded context packet for a cloud-model handoff.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "envelope": {"type": "object"},
                        "provider": {"type": "string"},
                        "max_tokens": {"type": "integer", "default": 8000},
                    },
                    "required": ["envelope", "provider"],
                },
            },
            {
                "name": "beast_sourceplan_prepare",
                "description": "Prepare a governed SourcePlan with output governance, bounded context, and selected files.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "files": {"type": "array", "items": {"type": "string"}},
                        "provider": {"type": "string", "default": "litellm"},
                        "provider_text": {"type": "string"},
                    },
                    "required": ["objective"],
                },
            },
            {
                "name": "beast_sourceplan_preview_hunks",
                "description": "Render a unified diff preview for a BEAST SourcePlan without applying it.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"plan": {"type": "object"}},
                    "required": ["plan"],
                },
            },
            {
                "name": "beast_sourceplan_apply_selected",
                "description": "Apply selected SourcePlan hunks with approval, verification, rollback, and Chronicle crystallization.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "plan": {"type": "object"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["plan", "approved"],
                },
            },
            {
                "name": "beast_sourceplan_rollback_latest",
                "description": "Rollback the latest BEAST SourcePlan apply using the local rollback snapshot.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "beast_provider_fitness",
                "description": "Summarize provider route fitness, Chronicle evidence, and recommended runtime role.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "beast_provider_economist_select",
                "description": "Choose the best eligible provider route for a requested role using hidden-clean economics, rescue rate, latency, auth confidence, and cost limits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "candidates": {"type": "array", "items": {"type": "object"}},
                        "requested_role": {"type": "string", "default": "primary_patch_provider"},
                        "max_latency_ms": {"type": "number"},
                        "max_usd_per_fix": {"type": "number"},
                        "min_auth_confidence": {"type": "number", "default": 0.6},
                        "require_cost_observation": {"type": "boolean", "default": False},
                        "prefer_hidden_clean": {"type": "boolean", "default": True},
                    },
                    "required": ["candidates", "requested_role"],
                },
            },
            {
                "name": "beast_tool_laziness_record",
                "description": "Record whether a tool call was useful so BEAST can learn future call/skip policy.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "scenario": {"type": "string"},
                        "called": {"type": "boolean", "default": True},
                        "useful": {"type": "boolean"},
                        "tokens_spent": {"type": "integer", "default": 0},
                        "cost_usd": {"type": "number", "default": 0},
                        "latency_ms": {"type": "number", "default": 0},
                        "value_score": {"type": "number", "default": 0},
                    },
                    "required": ["tool_name", "scenario", "useful"],
                },
            },
            {
                "name": "beast_tool_laziness_recommend",
                "description": "Given candidate tools and a scenario, explicitly identify tools not worth calling based on prior low-value outcomes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "candidate_tools": {
                            "type": "array",
                            "items": {"oneOf": [{"type": "string"}, {"type": "object"}]},
                        },
                        "scenario": {"type": "string"},
                        "required_tools": {"type": "array", "items": {"type": "string"}},
                        "min_samples": {"type": "integer", "default": 3},
                    },
                    "required": ["candidate_tools", "scenario"],
                },
            },
            {
                "name": "beast_otel_export",
                "description": "Compile Chronicle, route-card, packet-timing, and provider-fitness evidence into OTLP/HTTP spans and optionally export to Grafana Tempo, Jaeger, or another OTLP collector.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chronicles": {"type": "array", "items": {"type": "object"}},
                        "route_cards": {"type": "array", "items": {"type": "object"}},
                        "packet_evidence": {"type": "array", "items": {"type": "object"}},
                        "provider_fitness": {"type": "array", "items": {"type": "object"}},
                        "endpoint": {"type": "string"},
                        "approved": {"type": "boolean", "default": False},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "beast_plugin_manifest_validate",
                "description": "Optionally prepare schema hashes, then validate a BEAST plugin manifest's risk class, permissions, budget, approval policy, and immutable tool schema pins.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "manifest": {"type": "object"},
                        "prepare_hashes": {"type": "boolean", "default": False},
                    },
                    "required": ["manifest"],
                },
            },
            {
                "name": "beast_plugin_marketplace_install",
                "description": "Dry-run or install a valid schema-pinned BEAST plugin manifest; live installation requires explicit approval.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "manifest": {"type": "object"},
                        "approved": {"type": "boolean", "default": False},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["manifest"],
                },
            },
            {
                "name": "beast_capability_exchange",
                "description": "Prepare, contextually rank, or submit privacy-allowlisted tool/skill evidence. Submission is opt-in, approval-gated, and dry-run by default.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["state", "prepare", "rank", "submit"]},
                        "capability": {"type": "object"},
                        "outcome": {"type": "object"},
                        "evidence": {"oneOf": [{"type": "object"}, {"type": "array", "items": {"type": "object"}}]},
                        "task_class": {"type": "string"},
                        "role": {"type": "string"},
                        "approved": {"type": "boolean", "default": False},
                        "dry_run": {"type": "boolean", "default": True},
                        "persist_local": {"type": "boolean", "default": True},
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "beast_meta_tool_commons",
                "description": "Ingest and rank contextual capability priors, stage candidates, or locally approve adoption.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["state", "ingest", "discovery_ingest", "rank", "propose", "adopt", "snapshot"]},
                        "evidence": {"oneOf": [{"type": "object"}, {"type": "array", "items": {"type": "object"}}]},
                        "sources": {"type": "array", "items": {"type": "object"}},
                        "stage_candidates": {"type": "boolean", "default": True},
                        "candidate": {"type": "object"}, "candidate_id": {"type": "string"},
                        "task_class": {"type": "string"}, "role": {"type": "string"}, "kind": {"type": "string"},
                        "source": {"type": "string"}, "limit": {"type": "integer", "default": 25},
                        "approved": {"type": "boolean", "default": False},
                        "dry_run": {"type": "boolean", "default": True},
                        "approved_by": {"type": "string"}, "reason": {"type": "string"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "beast_compute_shadow",
                "description": "Inspect Phase 1 Compute Plans, gates, receipts, and counterfactual savings estimates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["state", "metrics", "savings_summary", "plans", "receipts", "receipt"]},
                        "limit": {"type": "integer", "default": 50},
                        "weekly_call_volume": {"type": "integer"},
                        "receipt_id": {"type": "string"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "beast_check_policy",
                "description": "Check whether an action is allowed under current governance rules.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "beast_build_route_card",
                "description": "Create a provider route card for diagnostics or handoffs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string"},
                        "envelope": {"type": "object"},
                        "persist": {"type": "boolean", "default": True},
                    },
                    "required": ["provider"],
                },
            },
            {
                "name": "beast_publish_chronicle",
                "description": "Persist a diagnostic or governance result to the Chronicle store.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "diagnostic_result": {"type": "object"},
                    },
                    "required": ["diagnostic_result"],
                },
            },
            {
                "name": "beast_attach_network_chronicle",
                "description": "Attach metadata-only packet-probe evidence to a provider diagnostic and optionally persist its Chronicle.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "diagnostic": {"type": "object"},
                        "probe": {"type": "object"},
                        "source": {"type": "string", "default": "packet_probe"},
                        "persist": {"type": "boolean", "default": False},
                    },
                    "required": ["diagnostic", "probe"],
                },
            },
            {
                "name": "beast_github_pr_ingest",
                "description": "Fetch a GitHub PR diff, check runs, and review comments and convert them into a bounded BEAST task envelope.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "GitHub repository in owner/name form."},
                        "pr_number": {"type": "integer", "minimum": 1},
                        "max_files": {"type": "integer", "default": 20},
                        "max_comments": {"type": "integer", "default": 30},
                    },
                    "required": ["repo", "pr_number"],
                },
            },
            {
                "name": "beast_github_pr_publish_chronicle",
                "description": "Draft or publish a bounded Chronicle summary as a GitHub PR comment; live writes require explicit approval.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "pr_number": {"type": "integer", "minimum": 1},
                        "chronicle": {"type": "object"},
                        "approved": {"type": "boolean", "default": False},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["repo", "pr_number", "chronicle"],
                },
            },
            {
                "name": "beast_get_workspace_graph",
                "description": "Return a lightweight view of the workspace graph/dependencies.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "depth": {"type": "integer", "default": 2},
                    },
                },
            },
            {
                "name": "beast_build_context_packet",
                "description": "Build a bounded evidence packet from a task envelope, route card, and quality report.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "envelope": {"type": "object"},
                        "route_card": {"type": "object"},
                        "quality_report": {"type": "object"},
                        "workspace_root": {"type": "string"},
                        "include_content": {"type": "boolean", "default": True},
                        "max_files": {"type": "integer"},
                        "semantic_limit": {"type": "integer", "default": 5},
                    },
                    "required": ["envelope"],
                },
            },
            {
                "name": "beast_score_forge",
                "description": "Build a pre-edit Forge scorecard with risk, benefit, gate, and verification signals.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "envelope": {"type": "object"},
                        "context_packet": {"type": "object"},
                        "quality_report": {"type": "object"},
                        "route_card": {"type": "object"},
                    },
                    "required": ["envelope"],
                },
            },
            {
                "name": "beast_plan_workflow",
                "description": "Build a Conductor workflow card using swarm role advice and current V2 artifacts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "envelope": {"type": "object"},
                        "context_packet": {"type": "object"},
                        "forge_scorecard": {"type": "object"},
                        "route_card": {"type": "object"},
                        "quality_report": {"type": "object"},
                        "run_swarm": {"type": "boolean", "default": True},
                        "persist": {"type": "boolean", "default": False},
                    },
                    "required": ["envelope"],
                },
            },
            {
                "name": "beast_validate_canon",
                "description": "Validate a BEAST object or artifact bundle against the V2 canon registry.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object": {"type": "object"},
                        "artifacts": {"type": "object"},
                    },
                },
            },
            {
                "name": "beast_check_promotion",
                "description": "Check whether repeated successful work is eligible for approval-gated promotion.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "artifacts": {"type": "object"},
                        "task_class": {"type": "string"},
                        "provider": {"type": "string"},
                        "category": {"type": "string"},
                        "route_id": {"type": "string"},
                        "min_repetitions": {"type": "integer", "default": 2},
                        "persist": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "beast_session_handshake",
                "description": "Tell an attached agent it is operating inside BEAST and provide local capabilities, cooperation rules, and strict preflight/scout latency budgets.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "mode": {"type": "string", "default": "openclaw"},
                        "workspace_root": {"type": "string"},
                        "candidate_tools": {"type": "array", "items": {"type": "string"}},
                        "preflight_budget_ms": {"type": "integer", "default": 500},
                        "scout_budget_ms": {"type": "integer", "default": 300},
                        "session_id": {"type": "string"},
                    },
                    "required": ["objective"],
                },
            },
            {
                "name": "beast_openclaw_plan",
                "description": "Create an Ollama-first Openclaw/Nemoclaw execution plan from workflow artifacts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "workflow": {"type": "object"},
                        "context_packet": {"type": "object"},
                        "mode": {"type": "string", "default": "openclaw"},
                        "workspace_root": {"type": "string"},
                        "use_ollama": {"type": "boolean", "default": True},
                        "candidate_tools": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object"}]}},
                        "required_tools": {"type": "array", "items": {"type": "string"}},
                        "provider_candidates": {"type": "array", "items": {"type": "object"}},
                        "requested_role": {"type": "string", "default": "primary_patch_provider"},
                        "preflight_budget_ms": {"type": "integer", "default": 500},
                        "scout_budget_ms": {"type": "integer", "default": 300},
                    },
                    "required": ["objective"],
                },
            },
            {
                "name": "beast_openclaw_execute",
                "description": "Execute allowed Openclaw/Nemoclaw workflow actions through the governed MCP broker; dry-run by default.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "workflow": {"type": "object"},
                        "context_packet": {"type": "object"},
                        "mode": {"type": "string", "default": "openclaw"},
                        "workspace_root": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                        "approved": {"type": "boolean", "default": False},
                        "use_ollama": {"type": "boolean", "default": True},
                        "candidate_tools": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object"}]}},
                        "required_tools": {"type": "array", "items": {"type": "string"}},
                        "provider_candidates": {"type": "array", "items": {"type": "object"}},
                        "requested_role": {"type": "string", "default": "primary_patch_provider"},
                        "preflight_budget_ms": {"type": "integer", "default": 500},
                        "scout_budget_ms": {"type": "integer", "default": 300},
                    },
                    "required": ["objective"],
                },
            },
            {
                "name": "beast_crystal_compute",
                "description": "Inspect Crystal Compute negative capabilities and Phase 2 shadow friction profiles.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"include_expired": {"type": "boolean", "default": False}},
                },
            },
            {
                "name": "beast_mcp_status",
                "description": "Return MCP server health, tool catalog, broker audit counters, and local inference readiness.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "beast_mcp_tool_catalog",
                "description": "Return BEAST MCP tools with schema, risk, audit, and execution metadata.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        return [
            {
                "uri": "beast://workspace/status",
                "name": "Workspace Status",
                "description": "Current workspace state and BEAST health metrics.",
                "mimeType": "application/json",
            },
            {
                "uri": "beast://chronicles/recent",
                "name": "Recent Chronicles",
                "description": "Recently published diagnostic chronicles.",
                "mimeType": "application/json",
            },
            {
                "uri": "beast://route-cards/active",
                "name": "Active Route Cards",
                "description": "Recently generated provider route cards.",
                "mimeType": "application/json",
            },
        ]

    def read_resource(self, uri: str) -> Dict[str, Any]:
        if uri == "beast://workspace/status":
            payload = {
                "status": "healthy",
                "workspace_root": self._workspace_root(),
                "version": "1.0.0",
                "components": {
                    "gateway": "running",
                    "mcp": "available",
                    "workspace_graph": "loaded",
                },
            }
        elif uri == "beast://chronicles/recent":
            payload = self.task_envelope_builder.list_chronicles(limit=5)
        elif uri == "beast://route-cards/active":
            payload = self.task_envelope_builder.list_route_cards(limit=10)
        else:
            raise ValueError(f"Unknown resource: {uri}")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload, indent=2),
                }
            ]
        }

    def list_prompts(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "diagnose_provider_failure",
                "description": "Guide for diagnosing a provider failure with BEAST.",
                "arguments": [
                    {"name": "provider", "description": "Provider to diagnose", "required": True},
                    {"name": "user_request", "description": "Original request", "required": False},
                ],
            },
            {
                "name": "prepare_handoff_packet",
                "description": "Guide for creating a bounded handoff packet.",
                "arguments": [
                    {"name": "task_description", "description": "Task to continue", "required": True},
                    {"name": "provider", "description": "Target provider", "required": True},
                ],
            },
        ]

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        arguments = arguments or {}
        if name == "diagnose_provider_failure":
            provider = arguments.get("provider", "unknown")
            user_request = arguments.get("user_request", "")
            text = (
                f"Use BEAST to diagnose the {provider} provider.\n\n"
                f"1. Call beast_prepare_task with provider={provider!r} and user_request={user_request!r}.\n"
                "2. Call beast_run_quality_cascade with the resulting envelope.\n"
                "3. Review route-card evidence and recommendations.\n"
                "4. If needed, call beast_prepare_handoff for cloud escalation.\n"
                "5. Call beast_publish_chronicle to persist the result."
            )
        elif name == "prepare_handoff_packet":
            text = (
                f"Prepare a bounded handoff for {arguments.get('provider', 'unknown')}.\n\n"
                f"Task: {arguments.get('task_description', '')}\n\n"
                "1. Call beast_prepare_task.\n"
                "2. Call beast_prepare_handoff.\n"
                "3. Verify packet size and relevance.\n"
                "4. Use the packet for downstream cloud reasoning."
            )
        else:
            raise ValueError(f"Unknown prompt: {name}")
        return {
            "description": name,
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": text},
                }
            ],
        }

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        arguments = arguments or {}
        logger.info("MCP tool call: %s", name)

        if name == "beast_prepare_task":
            result = self.task_envelope_builder.build(arguments, dry_run=arguments.get("dry_run", True))
        elif name == "beast_run_quality_cascade":
            envelope = arguments["envelope"]
            provider = arguments["provider"]
            workspace_root = self._workspace_root(arguments.get("workspace_root"))
            route_card = self.task_envelope_builder.provider_diagnostic_route_card(provider, envelope)
            result = self.task_envelope_builder.quality_cascade.run(envelope, route_card, workspace_root)
        elif name == "beast_run_maintenance_cascade":
            result = self.task_envelope_builder.quality_cascade.run_maintenance(
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
                run_tests=bool(arguments.get("run_tests", False)),
                pytest_args=[str(item) for item in arguments.get("pytest_args", [])],
                include_extension_checks=bool(arguments.get("include_extension_checks", True)),
                include_markdown=bool(arguments.get("include_markdown", True)),
                run_packaging=bool(arguments.get("run_packaging", False)),
                python_versions=[str(item) for item in arguments.get("python_versions", [])],
                timeout_seconds=int(arguments.get("timeout_seconds", 60)),
            )
        elif name == "beast_prepare_handoff":
            envelope = arguments["envelope"]
            envelope = dict(envelope)
            context_budget = dict(envelope.get("context_budget") or {})
            if arguments.get("max_tokens") is not None:
                context_budget["max_tokens"] = int(arguments.get("max_tokens", 8000))
            envelope["context_budget"] = context_budget
            result = self.context_packet_builder.build(
                envelope=envelope,
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
            )
        elif name == "beast_sourceplan_prepare":
            action = self.beast_api.build_source_patch_plan(
                str(arguments.get("objective") or ""),
                [str(item) for item in (arguments.get("files") or [])],
                provider=str(arguments.get("provider") or "litellm"),
                provider_text=str(arguments.get("provider_text") or ""),
            )
            result = self._action_result(action)
        elif name == "beast_sourceplan_preview_hunks":
            action = self.beast_api.render_patch_diff(arguments.get("plan") or {})
            result = self._action_result(action)
        elif name == "beast_sourceplan_apply_selected":
            action = self.beast_api.apply_patch_plan(
                arguments.get("plan") or {},
                approved=bool(arguments.get("approved", False)),
            )
            result = self._action_result(action)
        elif name == "beast_sourceplan_rollback_latest":
            action = self.beast_api.rollback_last_patch()
            result = self._action_result(action)
        elif name == "beast_provider_fitness":
            result = self._provider_fitness(
                provider=str(arguments.get("provider") or ""),
                limit=int(arguments.get("limit", 50)),
            )
        elif name == "beast_provider_economist_select":
            result = self.provider_economist.select(
                arguments.get("candidates") or [],
                EconomistPolicy(
                    requested_role=str(arguments.get("requested_role") or "primary_patch_provider"),
                    max_latency_ms=arguments.get("max_latency_ms"),
                    max_usd_per_fix=arguments.get("max_usd_per_fix"),
                    min_auth_confidence=float(arguments.get("min_auth_confidence", 0.6)),
                    require_cost_observation=bool(arguments.get("require_cost_observation", False)),
                    prefer_hidden_clean=bool(arguments.get("prefer_hidden_clean", True)),
                ),
            )
        elif name == "beast_tool_laziness_record":
            result = self.tool_laziness_learner.record(
                str(arguments["tool_name"]),
                str(arguments["scenario"]),
                called=bool(arguments.get("called", True)),
                useful=bool(arguments["useful"]),
                tokens_spent=int(arguments.get("tokens_spent", 0)),
                cost_usd=float(arguments.get("cost_usd", 0.0)),
                latency_ms=float(arguments.get("latency_ms", 0.0)),
                value_score=float(arguments.get("value_score", 0.0)),
            )
        elif name == "beast_tool_laziness_recommend":
            result = self.tool_laziness_plugin.recommend_tools(
                arguments.get("candidate_tools") or [],
                str(arguments["scenario"]),
                required_tools=arguments.get("required_tools") or [],
                min_samples=max(1, int(arguments.get("min_samples", 3))),
            )
        elif name == "beast_otel_export":
            payload = self.otel_connector.compile(
                chronicles=arguments.get("chronicles") or [],
                route_cards=arguments.get("route_cards") or [],
                packet_evidence=arguments.get("packet_evidence") or [],
                provider_fitness=arguments.get("provider_fitness") or [],
            )
            result = self.otel_connector.export(
                payload,
                endpoint=arguments.get("endpoint"),
                approved=bool(arguments.get("approved", False)),
                dry_run=bool(arguments.get("dry_run", True)),
            )
        elif name == "beast_plugin_manifest_validate":
            manifest = arguments["manifest"]
            if bool(arguments.get("prepare_hashes", False)):
                manifest = self.plugin_marketplace.prepare(manifest)
            result = {"manifest": manifest, "validation": self.plugin_marketplace.validate(manifest)}
        elif name == "beast_plugin_marketplace_install":
            result = self.plugin_marketplace.install(
                arguments["manifest"],
                approved=bool(arguments.get("approved", False)),
                dry_run=bool(arguments.get("dry_run", True)),
            )
        elif name == "beast_capability_exchange":
            action = str(arguments.get("action") or "state")
            if action == "state":
                result = self.capability_exchange.state()
            elif action == "prepare":
                result = self.capability_exchange.prepare(
                    arguments.get("capability") or {}, arguments.get("outcome") or {}
                )
            elif action == "rank":
                evidence = arguments.get("evidence") or []
                result = self.capability_exchange.rank(
                    evidence if isinstance(evidence, list) else [evidence],
                    task_class=arguments.get("task_class"),
                    role=arguments.get("role"),
                )
            elif action == "submit":
                evidence = arguments.get("evidence") or {}
                if not isinstance(evidence, dict):
                    raise ValueError("submit requires one evidence object")
                result = self.capability_exchange.contribute(
                    evidence,
                    approved=bool(arguments.get("approved", False)),
                    dry_run=bool(arguments.get("dry_run", True)),
                    persist_local=bool(arguments.get("persist_local", True)),
                )
            else:
                raise ValueError(f"unsupported capability exchange action: {action}")
        elif name == "beast_meta_tool_commons":
            action = str(arguments.get("action") or "state")
            if action == "state":
                result = self.meta_tool_commons.state()
            elif action == "ingest":
                evidence = arguments.get("evidence") or []
                result = self.meta_tool_commons.ingest(evidence if isinstance(evidence, list) else [evidence])
            elif action == "discovery_ingest":
                result = self.meta_tool_commons.ingest_discovery_sources({
                    "sources": arguments.get("sources") or [],
                    "stage_candidates": bool(arguments.get("stage_candidates", True)),
                })
            elif action == "rank":
                result = self.meta_tool_commons.rank(
                    task_class=arguments.get("task_class"), role=arguments.get("role"),
                    kind=arguments.get("kind"), limit=int(arguments.get("limit", 25)),
                )
            elif action == "propose":
                result = self.meta_tool_commons.propose(
                    arguments.get("candidate") or {}, source=str(arguments.get("source") or "local")
                )
            elif action == "adopt":
                result = self.meta_tool_commons.adopt(
                    str(arguments.get("candidate_id") or ""), approved=bool(arguments.get("approved", False)),
                    dry_run=bool(arguments.get("dry_run", True)), approved_by=str(arguments.get("approved_by") or "user"),
                    reason=str(arguments.get("reason") or ""),
                )
            elif action == "snapshot":
                result = self.meta_tool_commons.snapshot(
                    task_class=arguments.get("task_class"), role=arguments.get("role")
                )
            else:
                raise ValueError(f"unsupported meta tool commons action: {action}")
        elif name == "beast_compute_shadow":
            action = str(arguments.get("action") or "state")
            limit = max(1, min(int(arguments.get("limit", 50)), 2000))
            if action == "state":
                result = compute_ledger.state()
            elif action == "metrics":
                result = compute_ledger.metrics(limit)
            elif action == "savings_summary":
                result = compute_ledger.savings_summary(limit, arguments.get("weekly_call_volume"))
            elif action == "plans":
                result = {"plans": compute_ledger.recent_plans(limit)}
            elif action == "receipts":
                result = {"receipts": compute_ledger.recent_receipts(limit)}
            elif action == "receipt":
                result = compute_ledger.receipt(str(arguments.get("receipt_id") or ""))
            else:
                raise ValueError(f"unsupported compute shadow action: {action}")
        elif name == "beast_check_policy":
            action = arguments["action"]
            context = arguments.get("context", {})
            allowed = action not in {"external_write", "database_write", "production_config_change"}
            result = {
                "allowed": allowed,
                "action": action,
                "context": context,
                "reason": "Action is allowed" if allowed else "Action requires approval",
            }
        elif name == "beast_build_route_card":
            result = self.task_envelope_builder.provider_diagnostic_route_card(
                arguments["provider"],
                arguments.get("envelope", {}),
                persist=arguments.get("persist", True),
            )
        elif name == "beast_publish_chronicle":
            result = self.task_envelope_builder._write_chronicle(arguments["diagnostic_result"])
        elif name == "beast_attach_network_chronicle":
            result = self.network_chronicle_connector.attach_provider_diagnostic(
                arguments["diagnostic"],
                arguments["probe"],
                source=str(arguments.get("source") or "packet_probe"),
                chronicle_builder=self.task_envelope_builder,
                persist=bool(arguments.get("persist", False)),
            )
        elif name == "beast_github_pr_ingest":
            result = self.github_pr_connector.ingest(
                str(arguments["repo"]),
                int(arguments["pr_number"]),
                max_files=max(1, min(int(arguments.get("max_files", 20)), 50)),
                max_comments=max(1, min(int(arguments.get("max_comments", 30)), 100)),
            )
        elif name == "beast_github_pr_publish_chronicle":
            result = self.github_pr_connector.publish_chronicle(
                str(arguments["repo"]),
                int(arguments["pr_number"]),
                arguments["chronicle"],
                approved=bool(arguments.get("approved", False)),
                dry_run=bool(arguments.get("dry_run", True)),
            )
        elif name == "beast_get_workspace_graph":
            depth = int(arguments.get("depth", 2))
            graph = getattr(crystallizer, "workspace_graph", None)
            if graph and hasattr(graph, "summary"):
                result = graph.summary(depth=depth)  # type: ignore[arg-type]
            else:
                result = {
                    "workspace_root": self._workspace_root(),
                    "depth": depth,
                    "nodes": [{"id": "root", "type": "directory", "name": Path(self._workspace_root()).name or "."}],
                    "edges": [],
                }
        elif name == "beast_build_context_packet":
            result = self.context_packet_builder.build(
                arguments["envelope"],
                route_card=arguments.get("route_card"),
                quality_report=arguments.get("quality_report"),
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
                semantic_limit=max(1, min(int(arguments.get("semantic_limit", 5)), 20)),
                include_content=bool(arguments.get("include_content", True)),
                max_files=arguments.get("max_files"),
            )
        elif name == "beast_score_forge":
            result = self.forge_scorecard_builder.build(
                arguments["envelope"],
                context_packet=arguments.get("context_packet"),
                quality_report=arguments.get("quality_report"),
                route_card=arguments.get("route_card"),
            )
        elif name == "beast_plan_workflow":
            result = self.conductor_workflow_builder.build(
                arguments["envelope"],
                context_packet=arguments.get("context_packet"),
                forge_scorecard=arguments.get("forge_scorecard"),
                route_card=arguments.get("route_card"),
                quality_report=arguments.get("quality_report"),
                run_swarm=bool(arguments.get("run_swarm", True)),
                persist=bool(arguments.get("persist", False)),
            )
        elif name == "beast_validate_canon":
            if arguments.get("artifacts"):
                result = self.canon_registry.validate_bundle(arguments.get("artifacts") or {})
            else:
                result = self.canon_registry.validate(arguments.get("object") or arguments)
        elif name == "beast_check_promotion":
            result = self.promotion_loop.check(
                artifacts=arguments.get("artifacts") or {},
                task_class=arguments.get("task_class"),
                provider=arguments.get("provider"),
                category=arguments.get("category"),
                route_id=arguments.get("route_id"),
                min_repetitions=int(arguments.get("min_repetitions", 2)),
                persist=bool(arguments.get("persist", True)),
            )
        elif name == "beast_session_handshake":
            result = self.session_handshake_builder.build(
                str(arguments["objective"]),
                mode=str(arguments.get("mode") or "openclaw"),
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
                tools=arguments.get("candidate_tools") or [],
                preflight_budget_ms=int(arguments.get("preflight_budget_ms", 500)),
                scout_budget_ms=int(arguments.get("scout_budget_ms", 300)),
                session_id=arguments.get("session_id"),
            )
        elif name == "beast_openclaw_plan":
            result = self.beast_cli_executor.plan(
                objective=str(arguments["objective"]),
                workflow=arguments.get("workflow"),
                context_packet=arguments.get("context_packet"),
                mode=arguments.get("mode", "openclaw"),
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
                use_ollama=bool(arguments.get("use_ollama", True)),
                candidate_tools=arguments.get("candidate_tools") or [],
                required_tools=arguments.get("required_tools") or [],
                provider_candidates=arguments.get("provider_candidates") or [],
                requested_role=str(arguments.get("requested_role") or "primary_patch_provider"),
                preflight_budget_ms=int(arguments.get("preflight_budget_ms", 500)),
                scout_budget_ms=int(arguments.get("scout_budget_ms", 300)),
            )
        elif name == "beast_openclaw_execute":
            result = self.beast_cli_executor.execute(
                objective=str(arguments["objective"]),
                workflow=arguments.get("workflow"),
                context_packet=arguments.get("context_packet"),
                mode=arguments.get("mode", "openclaw"),
                workspace_root=self._workspace_root(arguments.get("workspace_root")),
                dry_run=bool(arguments.get("dry_run", True)),
                approved=bool(arguments.get("approved", False)),
                use_ollama=bool(arguments.get("use_ollama", True)),
                candidate_tools=arguments.get("candidate_tools") or [],
                required_tools=arguments.get("required_tools") or [],
                provider_candidates=arguments.get("provider_candidates") or [],
                requested_role=str(arguments.get("requested_role") or "primary_patch_provider"),
                preflight_budget_ms=int(arguments.get("preflight_budget_ms", 500)),
                scout_budget_ms=int(arguments.get("scout_budget_ms", 300)),
            )
        elif name == "beast_crystal_compute":
            result = {
                "beast_object_type": "crystal_compute_state",
                "phase1": "operational",
                "phase2": "shadow",
                "phase3": "advisory",
                "phase4": "escrow_shadow",
                "summary": self.crystal_compute_store.summary(),
                "negative_capabilities": self.crystal_compute_store.list_records(
                    include_expired=bool(arguments.get("include_expired", False))
                ),
                "friction_profiles": self.crystal_compute_store.friction_profiles(),
                "counterfactual_summary": compute_ledger.counterfactual_summary(),
                "escrow_summary": compute_ledger.escrow_summary(),
            }
        elif name == "beast_mcp_status":
            result = self._mcp_status()
        elif name == "beast_mcp_tool_catalog":
            result = {"tools": self._tool_catalog(), "count": len(self.tool_definitions())}
        else:
            raise ValueError(f"Unknown MCP tool: {name}")
        return result

    def _action_result(self, action: Any) -> Dict[str, Any]:
        return {
            "ok": bool(getattr(action, "ok", False)),
            "title": str(getattr(action, "title", "")),
            "summary": str(getattr(action, "summary", "")),
            "data": getattr(action, "data", {}) or {},
            "error": str(getattr(action, "error", "")),
        }

    def _provider_fitness(self, provider: str = "", limit: int = 50) -> Dict[str, Any]:
        chronicles = self.task_envelope_builder.list_chronicles(limit=max(1, min(limit, 200))).get("chronicles", [])
        if provider:
            chronicles = [
                item for item in chronicles
                if str(item.get("provider") or "").lower() == provider.lower()
            ]
        route_cards = self.task_envelope_builder.list_route_cards(limit=max(1, min(limit, 200))).get("route_cards", [])
        providers: Dict[str, Dict[str, Any]] = {}
        for item in chronicles:
            pid = str(item.get("provider") or provider or "local")
            bucket = providers.setdefault(pid, {
                "provider": pid,
                "chronicles": 0,
                "verified": 0,
                "failed": 0,
                "canonicalized": 0,
            })
            bucket["chronicles"] += 1
            status = str(item.get("status") or item.get("category") or "").lower()
            if any(term in status for term in ("passed", "success", "verified", "completed")):
                bucket["verified"] += 1
            if any(term in status for term in ("failed", "error", "denied")):
                bucket["failed"] += 1
            if bool(item.get("canonicalized")):
                bucket["canonicalized"] += 1
        for bucket in providers.values():
            total = max(1, int(bucket["chronicles"]))
            verified_rate = float(bucket["verified"]) / total
            rescue_rate = float(bucket["canonicalized"]) / total
            bucket["provider_fitness_score"] = round((0.7 * verified_rate + 0.3 * (1.0 - rescue_rate)) * 100, 2)
            bucket["beast_rescue_score"] = round(rescue_rate * 100, 2)
            bucket["recommended_role"] = self._recommended_provider_role(bucket)
        ranked = sorted(providers.values(), key=lambda item: item["provider_fitness_score"], reverse=True)
        return {
            "beast_object_type": "provider_fitness_snapshot",
            "provider": provider or "all",
            "providers": ranked,
            "route_card_count": len(route_cards),
            "chronicle_count": len(chronicles),
        }

    def _recommended_provider_role(self, bucket: Dict[str, Any]) -> str:
        provider = str(bucket.get("provider") or "").lower()
        fitness = float(bucket.get("provider_fitness_score") or 0)
        rescue = float(bucket.get("beast_rescue_score") or 0)
        if provider in {"fal", "hyperbolic"} and int(bucket.get("verified") or 0) == 0:
            return "do_not_use_until_auth_fixed"
        if "nim" in provider or "nvidia" in provider:
            return "refs_only_action_ir_generator"
        if fitness >= 75:
            return "primary_patch_provider"
        if fitness >= 45 and rescue >= 30:
            return "rescued_patch_provider"
        if rescue >= 60:
            return "semantic_transform_selector"
        return "scout_only"

    def _mcp_status(self) -> Dict[str, Any]:
        """Metatron-inspired MCP status without importing domain-specific services."""
        tool_catalog = self._tool_catalog()
        return {
            "beast_object_type": "mcp_server_status",
            "version": "1.0",
            "workspace_root": self._workspace_root(),
            "tools_registered": len(tool_catalog),
            "tool_categories": sorted({item["category"] for item in tool_catalog}),
            "broker": self.mcp_broker.stats(),
            "ollama": self.ollama_scout.status(),
            "audit_model": {
                "schema_pinning": True,
                "broker_audit_db": str(self.mcp_broker.db_path),
                "approval_queue": True,
                "dry_run_default_for_execution": True,
            },
        }

    def _tool_catalog(self) -> List[Dict[str, Any]]:
        catalog = []
        for definition in self.tool_definitions():
            name = definition["name"]
            category = self._tool_category(name)
            catalog.append({
                "tool_id": name,
                "name": name,
                "description": definition.get("description", ""),
                "category": category,
                "version": "1.0",
                "required_trust_state": self._trust_state(name),
                "risk": self._risk_level(name),
                "rate_limit_per_hour": self._rate_limit(name),
                "audit_level": "full" if category in {"execution", "governance", "promotion"} else "basic",
                "idempotent": name not in {"beast_publish_chronicle", "beast_check_promotion", "beast_openclaw_execute", "beast_sourceplan_apply_selected", "beast_sourceplan_rollback_latest", "beast_tool_laziness_record", "beast_otel_export", "beast_plugin_marketplace_install", "beast_capability_exchange"},
                "async_capable": False,
                "inputSchema": definition.get("inputSchema", {}),
                "redact_fields": ["*.credentials", "*.api_key", "*.token", "*.secret"],
            })
        return catalog

    def _tool_category(self, name: str) -> str:
        if "openclaw" in name:
            return "execution"
        if "otel" in name:
            return "observability"
        if "plugin" in name:
            return "extension"
        if "capability_exchange" in name:
            return "governance"
        if "sourceplan" in name:
            return "sourceplan"
        if "policy" in name or "canon" in name or "promotion" in name or "economist" in name or "laziness" in name:
            return "governance"
        if "context" in name or "handoff" in name or "workspace" in name:
            return "context"
        if "forge" in name or "workflow" in name or "quality" in name or "maintenance" in name:
            return "planning"
        if "chronicle" in name or "status" in name or "catalog" in name:
            return "audit"
        return "task"

    def _trust_state(self, name: str) -> str:
        if name == "beast_openclaw_execute":
            return "trusted_with_approval_for_non_read_only"
        if name == "beast_sourceplan_apply_selected":
            return "trusted_with_explicit_hunk_approval"
        if name in {"beast_otel_export", "beast_plugin_marketplace_install"}:
            return "trusted_with_explicit_approval"
        if name == "beast_capability_exchange":
            return "trusted_with_opt_in_and_approval"
        if name in {"beast_publish_chronicle", "beast_check_promotion", "beast_provider_economist_select", "beast_tool_laziness_record", "beast_tool_laziness_recommend"}:
            return "trusted"
        return "degraded"

    def _risk_level(self, name: str) -> str:
        if name == "beast_openclaw_execute":
            return "gated_execution"
        if name == "beast_sourceplan_apply_selected":
            return "gated_source_write"
        if name == "beast_sourceplan_rollback_latest":
            return "rollback_write"
        if name == "beast_otel_export":
            return "gated_network_write"
        if name == "beast_plugin_marketplace_install":
            return "gated_plugin_install"
        if name == "beast_capability_exchange":
            return "gated_network_and_learning_write"
        if name in {"beast_publish_chronicle", "beast_check_promotion", "beast_tool_laziness_record"}:
            return "persistent_write"
        return "read_or_plan"

    def _rate_limit(self, name: str) -> int:
        if name == "beast_openclaw_execute":
            return 60
        if name in {"beast_run_quality_cascade", "beast_run_maintenance_cascade", "beast_build_context_packet", "beast_openclaw_plan"}:
            return 240
        return 500


runtime = BeastToolRuntime()
