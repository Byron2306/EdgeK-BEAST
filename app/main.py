"""
EdgeK BEAST Gateway - Main Application Entry Point
Phase 9: Team and Enterprise Mode
"""

import uvicorn
import os
import time
from collections import Counter, deque
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, Any
import logging

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")

# Import adapters
from app.adapters.openai_adapter import openai_router
from app.adapters.anthropic_adapter import anthropic_router
from app.adapters.gemini_adapter import gemini_router
from app.adapters.huggingface_adapter import huggingface_router
from app.mcp.server import mcp_router
from app.proxy.server import proxy_router
from app.kernel.reason import reasoner
from app.kernel.crystallize import crystallizer
from app.kernel.runtime import runtime_governor
from app.kernel.skill_tree import skill_tree
from app.kernel.swarm import swarm_kernel
from app.kernel.enterprise import enterprise_manager
from app.kernel.benchmark import ComparativeBenchmark, MegaGauntlet
from app.kernel.ast_compressor import ASTCompressor
from app.kernel.isolation_forest import IsolationForest
from app.kernel.os_bypass import af_packet_capture_probe, capabilities as os_bypass_capabilities, open_ring_probe, dpdk_probe, af_xdp_probe
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.deployment import DeploymentManager
from app.kernel.tool_integrations import RequiredIntegrationRegistry, ToolCallInterceptor
from app.kernel.ollama_scout import OllamaScout
from app.kernel.task_envelope import TaskEnvelopeBuilder
from app.kernel.memory_stack import MemoryStack
from app.kernel.context_packet import ContextPacketBuilder
from app.kernel.forge_scorecard import ForgeScorecardBuilder
from app.kernel.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.canon_registry import CanonRegistry
from app.kernel.promotion_loop import PromotionLoop
from app.kernel.beast_cli_executor import BeastCLIExecutor
from app.kernel.secret_vault import PROVIDER_ENV, SecretVault
from app.kernel.insight_compiler import InsightCompiler
from app.kernel.capability_registry import CapabilityRegistry
from app.kernel.evidence_scoring import EvidenceScorer
from app.kernel.compression_pipeline import CompressionPipeline
from app.kernel.interception_events import InterceptionEventFactory
from app.kernel.forensic_memory import ForensicMemory
from app.kernel.chronicle_projection import ChronicleProjectionPublisher
from app.kernel.vector_adapters import VectorAdapterRegistry
from app.kernel.provider_registry import ProviderRegistry
from app.kernel.provider_adapters import ProviderAdapterRegistry
from app.kernel.prec_lifecycle import prec_lifecycle_store
from app.mcp.broker import MCPBroker

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
for noisy_logger in ("httpx", "httpcore", "sentence_transformers", "transformers", "huggingface_hub"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
secret_vault = SecretVault()
secret_vault.load()
mcp_broker = MCPBroker(reasoner.policies, workspace_graph=crystallizer.workspace_graph)
runtime_governor.policies = reasoner.policies
swarm_kernel.policies = reasoner.policies
swarm_kernel.workspace_graph = crystallizer.workspace_graph
enterprise_manager.policies = reasoner.policies
benchmark_runner = ComparativeBenchmark(reasoner.policies, reasoner=reasoner)
mega_gauntlet = MegaGauntlet(reasoner.policies, reasoner=reasoner)
ast_compressor = ASTCompressor()
tool_laziness_learner = ToolLazinessLearner()
deployment_manager = DeploymentManager(reasoner.policies)
integration_registry = RequiredIntegrationRegistry(reasoner.policies)
tool_call_interceptor = ToolCallInterceptor(crystallizer.workspace_graph, reasoner.policies)
ollama_scout = OllamaScout(crystallizer.workspace_graph, mcp_broker, reasoner.policies)
task_envelope_builder = TaskEnvelopeBuilder(reasoner.policies, runtime_governor=runtime_governor)
context_packet_builder = ContextPacketBuilder(workspace_graph=crystallizer.workspace_graph)
forge_scorecard_builder = ForgeScorecardBuilder()
conductor_workflow_builder = ConductorWorkflowBuilder(swarm_kernel=swarm_kernel)
canon_registry = CanonRegistry()
beast_cli_executor = BeastCLIExecutor(
    ollama_scout=ollama_scout,
    mcp_broker=mcp_broker,
    canon_registry=canon_registry,
    runtime_governor=runtime_governor,
    tool_laziness_learner=tool_laziness_learner,
)
promotion_loop = PromotionLoop(
    task_envelope_builder=task_envelope_builder,
    conductor_workflow_builder=conductor_workflow_builder,
    canon_registry=canon_registry,
    tool_laziness_learner=tool_laziness_learner,
    skill_registry=skill_tree.skill_registry,
)
insight_compiler = InsightCompiler(policies=reasoner.policies)
capability_registry = CapabilityRegistry(reasoner.policies, skill_tree=skill_tree)
evidence_scorer = EvidenceScorer(reasoner.policies)
compression_pipeline = CompressionPipeline(reasoner.policies)
interception_event_factory = InterceptionEventFactory(reasoner.policies)
forensic_memory = ForensicMemory()
chronicle_publisher = ChronicleProjectionPublisher()
vector_adapter_registry = VectorAdapterRegistry()
provider_registry = ProviderRegistry(reasoner.policies)
provider_adapter_registry = ProviderAdapterRegistry(reasoner.policies)
prec_lifecycle = prec_lifecycle_store
runtime_governor.forensic_memory = forensic_memory
ollama_scout.forensic_memory = forensic_memory
insight_compiler.forensic_memory = forensic_memory
memory_stack = MemoryStack(
    reasoner.policies,
    reasoner=reasoner,
    runtime_governor=runtime_governor,
    workspace_graph=crystallizer.workspace_graph,
    skill_tree=skill_tree,
    crystallizer=crystallizer,
    mcp_broker=mcp_broker,
    task_envelope_builder=task_envelope_builder,
    enterprise_manager=enterprise_manager,
)
frontend_dir = Path(__file__).resolve().parent / "frontend"

# Initialize FastAPI app
app = FastAPI(
    title="EdgeK BEAST Gateway",
    description="Governed local AI execution broker for agentic coding",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(openai_router)
app.include_router(anthropic_router)
app.include_router(gemini_router)
app.include_router(mcp_router)
app.include_router(proxy_router, prefix="/proxy")
app.include_router(huggingface_router)
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# In-memory process counters; durable governance state lives in the kernel stores.
active_sessions: Dict[str, Any] = {}
request_count = 0
http_telemetry = {
    "started_at": time.time(),
    "request_count": 0,
    "rx_bytes": 0,
    "tx_bytes": 0,
    "status_counts": Counter(),
    "method_counts": Counter(),
    "route_counts": Counter(),
    "recent": deque(maxlen=240),
}


def _telemetry_stats() -> Dict[str, Any]:
    recent = list(http_telemetry["recent"])
    durations = sorted(int(item.get("duration_ms") or 0) for item in recent)
    elapsed = max(0.001, time.time() - float(http_telemetry["started_at"]))
    window_seconds = 0.001
    if recent:
        window_seconds = max(0.001, float(recent[-1]["completed_at_epoch"]) - float(recent[0]["completed_at_epoch"]))
    recent_rx = sum(int(item.get("rx_bytes") or 0) for item in recent)
    recent_tx = sum(int(item.get("tx_bytes") or 0) for item in recent)
    p95_index = min(len(durations) - 1, int(round((len(durations) - 1) * 0.95))) if durations else 0
    latency = {
        "count": len(durations),
        "avg": int(sum(durations) / len(durations)) if durations else 0,
        "min": durations[0] if durations else 0,
        "max": durations[-1] if durations else 0,
        "p95": durations[p95_index] if durations else 0,
    }
    return {
        "started_at_epoch": http_telemetry["started_at"],
        "uptime_seconds": int(elapsed),
        "request_count": int(http_telemetry["request_count"]),
        "packets": {
            "http_requests": int(http_telemetry["request_count"]),
            "recent_window_requests": len(recent),
        },
        "io": {
            "rx_bytes": int(http_telemetry["rx_bytes"]),
            "tx_bytes": int(http_telemetry["tx_bytes"]),
            "recent_rx_bytes": recent_rx,
            "recent_tx_bytes": recent_tx,
        },
        "bandwidth": {
            "rx_bytes_per_second": round(recent_rx / window_seconds, 2),
            "tx_bytes_per_second": round(recent_tx / window_seconds, 2),
            "lifetime_rx_bytes_per_second": round(int(http_telemetry["rx_bytes"]) / elapsed, 2),
            "lifetime_tx_bytes_per_second": round(int(http_telemetry["tx_bytes"]) / elapsed, 2),
        },
        "latency_ms": latency,
        "status_counts": dict(http_telemetry["status_counts"]),
        "method_counts": dict(http_telemetry["method_counts"]),
        "route_counts": dict(http_telemetry["route_counts"].most_common(20)),
        "recent": recent[-40:],
    }

@app.get("/")
async def root():
    """Root endpoint providing basic gateway information"""
    return {
        "service": "EdgeK BEAST Gateway",
        "version": "0.1.0",
        "status": "operational",
            "phase": "9 - Team and Enterprise Mode",
        "endpoints": {
            "health": "/health",
            "edgek_state": "/edgek/state",
            "edgek_workspace": "/edgek/workspace",
            "edgek_workspace_index": "/edgek/workspace/index",
            "edgek_workspace_rebuild": "/edgek/workspace/rebuild",
            "edgek_workspace_export": "/edgek/workspace/export",
            "edgek_workspace_integrity": "/edgek/workspace/integrity",
            "edgek_workspace_search": "/edgek/workspace/search",
            "edgek_workspace_semantic_index": "/edgek/workspace/semantic-index",
            "edgek_workspace_semantic_context": "/edgek/workspace/semantic-context",
            "edgek_workspace_node": "/edgek/workspace/nodes/{node_id}",
            "edgek_mcp_evaluate": "/edgek/mcp/evaluate",
            "edgek_mcp_execute": "/edgek/mcp/execute",
            "edgek_mcp_state": "/edgek/mcp/state",
            "edgek_mcp_servers": "/edgek/mcp/servers",
            "edgek_mcp_audit": "/edgek/mcp/audit",
            "edgek_mcp_executions": "/edgek/mcp/executions",
            "edgek_mcp_approvals": "/edgek/mcp/approvals",
            "edgek_tool_intercept": "/edgek/tools/intercept",
            "edgek_tool_integrations": "/edgek/tools/integrations",
            "edgek_interception_event": "/edgek/interception/event",
            "edgek_interception_mesh": "/edgek/interception/mesh",
            "edgek_forensics_l4_state": "/edgek/forensics/l4/state",
            "edgek_forensics_l4_query": "/edgek/forensics/l4/query",
            "edgek_ollama_status": "/edgek/ollama/status",
            "edgek_ollama_packet": "/edgek/ollama/packet",
            "edgek_ollama_scout": "/edgek/ollama/scout",
            "edgek_task_envelope": "/edgek/task/envelope",
            "edgek_task_provider_diagnostic": "/edgek/task/provider-diagnostic",
            "edgek_task_quality_cascade": "/edgek/task/quality-cascade",
            "edgek_quality_run": "/edgek/quality/run",
            "edgek_maintenance_run": "/edgek/maintenance/run",
            "edgek_context_packet": "/edgek/context/packet",
            "edgek_forge_scorecard": "/edgek/forge/scorecard",
            "edgek_forge_decision": "/edgek/forge/decision",
            "edgek_workflow_plan": "/edgek/workflow/plan",
            "edgek_conductor_workflow_card": "/edgek/conductor/workflow-card",
            "edgek_workflow_cards": "/edgek/workflow/cards",
            "edgek_canon_schemas": "/edgek/canon/schemas",
            "edgek_canon_validate": "/edgek/canon/validate",
            "edgek_canon_metrics": "/edgek/canon/metrics",
            "edgek_skills_promotion_check": "/edgek/skills/promotion-check",
            "edgek_skills_promote": "/edgek/skills/promote",
            "edgek_beast_cli_plan": "/edgek/beast-cli/plan",
            "edgek_beast_cli_execute": "/edgek/beast-cli/execute",
            "edgek_chronicle": "/edgek/chronicle",
            "edgek_chronicle_detail": "/edgek/chronicle/{task_id}",
            "edgek_chronicle_publish": "/edgek/chronicle/publish",
            "edgek_route_cards": "/edgek/route/cards",
            "edgek_provider_route_card": "/edgek/route/provider-diagnostic/{provider}",
            "edgek_pathfinder_route_card": "/edgek/pathfinder/route-card",
            "edgek_vector_adapters": "/edgek/vector/adapters",
            "edgek_memory_stack": "/edgek/memory/stack",
            "edgek_runtime_state": "/edgek/runtime/state",
            "edgek_runtime_attempts": "/edgek/runtime/attempts",
            "edgek_runtime_integrity": "/edgek/runtime/integrity",
            "edgek_runtime_sweep": "/edgek/runtime/sweep",
            "edgek_runtime_reset_circuit": "/edgek/runtime/circuit-breakers/{provider}/reset",
            "edgek_skills_state": "/edgek/skills/state",
            "edgek_skills": "/edgek/skills",
            "edgek_skills_mine": "/edgek/skills/mine",
            "edgek_skills_patterns": "/edgek/skills/patterns",
            "edgek_skills_candidates": "/edgek/skills/candidates",
            "edgek_skills_promotion_candidates": "/edgek/skills/promotion-candidates",
            "edgek_swarm_state": "/edgek/swarm/state",
            "edgek_swarm_run": "/edgek/swarm/run",
            "edgek_swarm_runs": "/edgek/swarm/runs",
            "edgek_swarm_value": "/edgek/swarm/value",
            "edgek_enterprise_state": "/edgek/enterprise/state",
            "edgek_enterprise_teams": "/edgek/enterprise/teams",
            "edgek_enterprise_auth": "/edgek/enterprise/auth/verify",
            "edgek_enterprise_observability": "/edgek/enterprise/observability",
            "edgek_enterprise_otel": "/edgek/enterprise/otel",
            "edgek_enterprise_policy_packs": "/edgek/enterprise/policy-packs",
            "edgek_deploy_litellm": "/edgek/deploy/litellm-config",
            "edgek_deploy_nginx": "/edgek/deploy/nginx-config",
            "edgek_deploy_tgi_llamacpp": "/edgek/deploy/tgi-llamacpp",
            "edgek_prompt_cache_keepalive": "/edgek/prompt-cache/keepalives",
            "edgek_semantic_dedupe": "/edgek/semantic/dedupe",
            "v1/models": "/v1/models",
            "v1/chat/completions": "/v1/chat/completions (POST)",
            "v1/completions": "/v1/completions (POST)",
            "v1/messages": "/v1/messages (POST)",
            "v1beta/gemini_generate": "/v1beta/models/{model}:generateContent (POST)",
            "hf_chat_completions": "/hf/v1/chat/completions (POST)",
            "tgi_chat_completions": "/tgi/v1/chat/completions (POST)",
            "edgek_providers_state": "/edgek/providers/state",
            "edgek_providers_registry": "/edgek/providers/registry",
            "edgek_prec_state": "/edgek/prec/state",
            "edgek_prec_lifecycle": "/edgek/prec/lifecycle",
        }
    }

@app.get("/ui")
async def beast_cockpit():
    """Serve the BEAST live operations cockpit."""
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="BEAST cockpit frontend is not installed")
    return FileResponse(str(index_path))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "edgek-beast-gateway",
        "version": "0.1.0",
        "active_sessions": len(active_sessions),
        "total_requests": request_count
    }

@app.get("/edgek/state")
async def edgek_state(session_id: str = "default"):
    """Expose gateway governance state for local inspection."""
    return {
        "phase": "9 - Team and Enterprise Mode",
        "budget": reasoner.budget_ledger.usage_summary(session_id),
        "skills": crystallizer.skill_registry.get_statistics(),
        "workspace_graph": crystallizer.workspace_graph.stats(),
        "mcp_broker": mcp_broker.stats(),
        "runtime": runtime_governor.state(),
        "skill_tree": skill_tree.state(),
        "swarm": swarm_kernel.state(),
        "enterprise": enterprise_manager.state(),
        "recent_process_state": {
            "traces": len(crystallizer.trace_storage),
            "skill_updates": len(crystallizer.skill_updates),
            "telemetry_events": len(crystallizer.telemetry_data),
            "workspace_updates": len(crystallizer.workspace_graph_updates)
        },
        "storage": {
            "trace_jsonl": str(crystallizer.trace_path),
            "trace_index": str(crystallizer.index_path),
            "budget_db": str(reasoner.budget_ledger.db_path),
            "workspace_graph_db": str(crystallizer.workspace_graph.db_path),
            "mcp_broker_db": str(mcp_broker.db_path),
            "runtime_db": str(runtime_governor.db_path),
            "swarm_db": str(swarm_kernel.db_path),
            "enterprise_db": str(enterprise_manager.db_path)
        }
    }

@app.get("/edgek/providers/state")
async def edgek_providers_state():
    """Return provider integration readiness without exposing secrets."""
    import os
    registry = provider_registry.records(include_disabled=True)
    return {
        "providers": {
            record.provider_id: {
                "enabled": record.enabled,
                "base_url": record.base_url,
                "default_model": record.default_model,
                "backend": record.backend,
                "proxy_path": record.proxy_path,
                "managed_by": record.managed_by,
            }
            for record in registry
        },
        "credentials": {
            provider: bool(os.environ.get(env_name))
            for provider, env_name in PROVIDER_ENV.items()
        },
        "runtime_urls": {
            "hf_inference_base_url": os.environ.get("HF_INFERENCE_BASE_URL", "https://router.huggingface.co/v1"),
            "tgi_base_url": os.environ.get("TGI_BASE_URL", "http://127.0.0.1:3000"),
            "litellm_base_url": os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1"),
            "gemini_base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
        },
    }

@app.get("/edgek/providers/registry")
async def edgek_providers_registry():
    """Return provider registry source of truth for gateway, deployment, and capabilities."""
    return provider_registry.inventory()

@app.get("/edgek/providers/adapters")
async def edgek_providers_adapters():
    """Return concrete provider adapter classes and routing plans."""
    return provider_adapter_registry.inventory()

@app.get("/edgek/providers/secrets")
async def edgek_provider_secrets_status():
    """Return redacted local provider secret readiness."""
    return secret_vault.status()

@app.get("/edgek/prec/state")
async def edgek_prec_state():
    """Return PREC lifecycle counts and recent records."""
    return prec_lifecycle.state()

@app.get("/edgek/prec/lifecycle")
async def edgek_prec_lifecycle_list(kind: str = None, status: str = None, limit: int = 50):
    """List append-only PREC lifecycle records."""
    return prec_lifecycle.list(kind=kind, status=status, limit=limit)

@app.get("/edgek/prec/lifecycle/{lifecycle_id}")
async def edgek_prec_lifecycle_detail(lifecycle_id: str):
    """Return one PREC lifecycle with phase events."""
    detail = prec_lifecycle.get(lifecycle_id)
    if not detail:
        raise HTTPException(status_code=404, detail="PREC lifecycle not found")
    return detail

@app.get("/edgek/prec/lifecycle/{lifecycle_id}/snapshot")
async def edgek_prec_lifecycle_snapshot(lifecycle_id: str, max_chars: int = 6000, persist: bool = True):
    """Return a compact PREC lifecycle snapshot suitable for handoff/operator review."""
    try:
        return prec_lifecycle.compact_snapshot(lifecycle_id, max_chars=max_chars, persist=persist)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/edgek/prec/lifecycle/{lifecycle_id}/snapshots")
async def edgek_prec_lifecycle_snapshots(lifecycle_id: str, limit: int = 20):
    """List persisted compact PREC snapshots for one lifecycle."""
    return prec_lifecycle.list_snapshots(lifecycle_id, limit=limit)

@app.post("/edgek/prec/start")
async def edgek_prec_start(payload: Dict[str, Any]):
    """Start a manually marked PREC lifecycle for IDE/operator sessions."""
    objective = str(payload.get("objective") or payload.get("task") or payload.get("goal") or "").strip()
    if not objective:
        raise HTTPException(status_code=400, detail="objective/task/goal is required")
    return prec_lifecycle.start(
        kind=str(payload.get("kind") or "operator_session"),
        objective=objective,
        scope=str(payload.get("scope") or ""),
        task_id=payload.get("task_id"),
        provider=payload.get("provider"),
        metadata=payload.get("metadata") or {},
    )

@app.post("/edgek/prec/update")
async def edgek_prec_update(payload: Dict[str, Any]):
    """Append one phase event to a PREC lifecycle."""
    lifecycle_id = str(payload.get("lifecycle_id") or "").strip()
    phase = str(payload.get("phase") or "").strip()
    if not lifecycle_id or not phase:
        raise HTTPException(status_code=400, detail="lifecycle_id and phase are required")
    try:
        return prec_lifecycle.record_phase(
            lifecycle_id,
            phase,
            status=str(payload.get("status") or "completed"),
            summary=str(payload.get("summary") or ""),
            artifacts=payload.get("artifacts") or {},
            signals=payload.get("signals") or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

def _prec_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lifecycle_id": record.get("lifecycle_id"),
        "kind": record.get("kind"),
        "status": record.get("status"),
        "current_phase": record.get("current_phase"),
    }

@app.post("/edgek/providers/secrets/import")
async def edgek_provider_secrets_import(payload: Dict[str, Any]):
    """Import a local secrets file into the chmod 600 BEAST provider vault."""
    source_path = payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    try:
        return secret_vault.import_file(
            source_path=source_path,
            overwrite=bool(payload.get("overwrite", False)),
            load=bool(payload.get("load", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/benchmarks/comparative")
async def edgek_benchmarks_comparative(session_id: str = None):
    """Run built-in comparative scenarios for non-gated versus governed calls."""
    return benchmark_runner.run(session_id=session_id)

@app.post("/edgek/benchmarks/comparative")
async def edgek_benchmarks_comparative_custom(payload: Dict[str, Any] = None):
    """Run custom comparative scenarios for non-gated versus governed calls."""
    payload = payload or {}
    return benchmark_runner.run(
        scenarios=payload.get("scenarios"),
        session_id=payload.get("session_id"),
    )

@app.get("/edgek/benchmarks/gauntlet")
async def edgek_benchmarks_gauntlet(session_id: str = None):
    """Run the broad provider-profile gauntlet without live API spend."""
    return mega_gauntlet.run(session_id=session_id)

@app.post("/edgek/benchmarks/gauntlet")
async def edgek_benchmarks_gauntlet_custom(payload: Dict[str, Any] = None):
    """Run a filtered provider-profile gauntlet without live API spend."""
    payload = payload or {}
    return mega_gauntlet.run(
        providers=payload.get("providers"),
        scenario_names=payload.get("scenario_names"),
        session_id=payload.get("session_id"),
    )

@app.get("/edgek/os-bypass/capabilities")
async def edgek_os_bypass_capabilities():
    """Return host support for low-latency packet ingress modes."""
    return os_bypass_capabilities()

@app.post("/edgek/os-bypass/af-packet/probe")
async def edgek_os_bypass_af_packet_probe(payload: Dict[str, Any] = None):
    """Try to open an AF_PACKET mmap ring and report host capability."""
    payload = payload or {}
    try:
        return open_ring_probe(interface=payload.get("interface", "lo"))
    except Exception as exc:
        return {
            "opened": False,
            "mode": "af_packet_tpacket_v3_mmap",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

@app.post("/edgek/os-bypass/af-packet/capture-probe")
async def edgek_os_bypass_af_packet_capture_probe(payload: Dict[str, Any] = None):
    """Emit a marked loopback UDP datagram and verify AF_PACKET observes it."""
    payload = payload or {}
    try:
        return af_packet_capture_probe(
            interface=payload.get("interface", "lo"),
            marker=payload.get("marker", "BEAST_OS_BYPASS_PROBE"),
            port=int(payload.get("port", 45555)),
            timeout_ms=int(payload.get("timeout_ms", 1000)),
            max_packets=int(payload.get("max_packets", 64)),
        )
    except Exception as exc:
        return {
            "opened": False,
            "mode": "af_packet_raw_capture",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

@app.post("/edgek/os-bypass/dpdk/probe")
async def edgek_os_bypass_dpdk_probe(payload: Dict[str, Any] = None):
    """Try to initialize DPDK EAL and report available ethdev ports."""
    payload = payload or {}
    try:
        return dpdk_probe(argv=payload.get("argv"))
    except Exception as exc:
        return {
            "opened": False,
            "mode": "dpdk_eal",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

@app.post("/edgek/os-bypass/af-xdp/probe")
async def edgek_os_bypass_af_xdp_probe(payload: Dict[str, Any] = None):
    """Try to load AF_XDP/libxdp support and report socket-create readiness."""
    payload = payload or {}
    try:
        return af_xdp_probe(
            interface=payload.get("interface", "lo"),
            queue_id=int(payload.get("queue_id", 0)),
        )
    except Exception as exc:
        return {
            "opened": False,
            "mode": "af_xdp_libxdp",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

@app.post("/edgek/compression/json")
async def edgek_compress_json(payload: Dict[str, Any]):
    """Compress JSON telemetry or structured payloads."""
    if "value" not in payload:
        raise HTTPException(status_code=400, detail="Missing value")
    return ast_compressor.compress_json(payload["value"]).to_dict()

@app.post("/edgek/compression/python")
async def edgek_compress_python(payload: Dict[str, Any]):
    """Compress Python source into a canonical semantic AST payload."""
    if "source" not in payload:
        raise HTTPException(status_code=400, detail="Missing source")
    try:
        if payload.get("mode") == "summary":
            return ast_compressor.compress_python_summary(payload["source"]).to_dict()
        return ast_compressor.compress_python_source(payload["source"]).to_dict()
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/compression/prune")
async def edgek_compress_prune(payload: Dict[str, Any]):
    """Run required token-pruning/compression integration surface."""
    text = payload.get("text") or payload.get("content") or payload.get("source")
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="Missing text/content/source")
    return tool_call_interceptor.compress_text(
        text,
        algorithm=str(payload.get("algorithm") or "edgek_prune"),
    )

@app.post("/edgek/compression/pipeline")
async def edgek_compression_pipeline(payload: Dict[str, Any]):
    """Run layered compression with chunks, scored evidence, and Chronicle write."""
    try:
        payload = payload or {}
        result = compression_pipeline.compress(payload)
        lifecycle = prec_lifecycle.record_artifact_lifecycle(
            kind="tool_call",
            payload={**payload, "objective": payload.get("objective") or "Run compression pipeline"},
            artifacts={
                "evidence_records": result.get("evidence") or result.get("evidence_records") or [],
                "chronicle": result.get("chronicle"),
                "capability_signals": [{"capability_id": "tool:compression_prune"}],
            },
        )
        result["prec_lifecycle"] = _prec_summary(lifecycle)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/tools/integrations")
async def edgek_tool_integrations():
    """Return readiness for required BEAST tool-call integrations."""
    return integration_registry.status()

@app.post("/edgek/tools/intercept")
async def edgek_tools_intercept(payload: Dict[str, Any]):
    """Intercept tool calls and return BEAST-compressed semantic payloads."""
    try:
        result = tool_call_interceptor.intercept(
            payload,
            workspace_root=str(Path(__file__).resolve().parents[1]),
        )
        lifecycle = prec_lifecycle.record_artifact_lifecycle(
            kind="tool_call",
            payload={**(payload or {}), "objective": f"Intercept tool call {(payload or {}).get('tool_name') or (payload or {}).get('name') or 'unknown'}"},
            artifacts={
                "interception": result.get("interception"),
                "evidence_records": [result.get("evidence_record")] if result.get("evidence_record") else [],
                "capability_signals": [{"capability_id": (result.get("evidence_record") or {}).get("recommended_capability_id")}],
            },
        )
        result["prec_lifecycle"] = _prec_summary(lifecycle)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/interception/event")
async def edgek_interception_event(payload: Dict[str, Any]):
    """Normalize a broad gateway/proxy/runtime interception event into scored evidence."""
    evidence = interception_event_factory.build(payload or {})
    chronicle = forensic_memory.append(payload or {}, evidence=evidence) if bool((payload or {}).get("persist", False)) else {"written": False, "reason": "persist_false"}
    result = {**evidence, "forensic_memory": chronicle}
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="interception_event",
        payload={**(payload or {}), "objective": evidence.get("summary") or "Record interception event"},
        artifacts={
            "interception": {"layer": evidence.get("interception_layer"), "event_kind": (payload or {}).get("event_kind")},
            "evidence_records": [evidence],
            "chronicle": chronicle,
            "capability_signals": [{"capability_id": evidence.get("recommended_capability_id")}],
        },
        provider=evidence.get("provider"),
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.get("/edgek/interception/mesh")
async def edgek_interception_mesh():
    """Return the L1-L4 interception layer mesh and event capability map."""
    return interception_event_factory.mesh()

@app.get("/edgek/interception/transparent/state")
async def edgek_transparent_interception_state():
    """Return transparent interception readiness for routed clients and local edge proxying."""
    return {
        "beast_object_type": "transparent_interception_state",
        "version": "1.0",
        "status": "route_bound",
        "ready": True,
        "routes": {
            "tool_calls": "/tool-calls/* -> /edgek/tools/intercept",
            "direct_tool_intercept": "/edgek/tools/intercept",
            "provider_compatibility": "/v1/* and /proxy/v1/* enter BEAST governance",
            "provider_explicit": "/proxy/<provider>/* enters BEAST governance",
            "mcp_http": "/mcp/* -> BEAST MCP HTTP facade",
        },
        "nginx_config_endpoint": "/edgek/deploy/nginx-config",
        "nginx_apply_endpoint": "/edgek/deploy/nginx/apply",
        "limits": [
            "Arbitrary process traffic cannot be captured unless the client uses BEAST base URLs, MCP stdio, HTTP MCP, or the generated Nginx edge.",
            "OS-level transparent proxying remains an operator/network configuration task.",
        ],
    }

@app.get("/edgek/forensics/l4/state")
async def edgek_forensics_l4_state():
    """Return append-only L4 forensic memory state."""
    return forensic_memory.state()

@app.post("/edgek/forensics/l4/query")
async def edgek_forensics_l4_query(payload: Dict[str, Any] = None):
    """Query L4 forensic memory with metadata filters before lexical scoring."""
    payload = payload or {}
    return forensic_memory.query(
        query=str(payload.get("query") or ""),
        event_kind=payload.get("event_kind"),
        layer=payload.get("layer"),
        provider=payload.get("provider"),
        status=payload.get("status"),
        limit=max(1, min(int(payload.get("limit", 10)), 100)),
    )

@app.get("/edgek/ollama/status")
async def edgek_ollama_status():
    """Return Ollama scout readiness."""
    return ollama_scout.status()

@app.post("/edgek/ollama/packet")
async def edgek_ollama_packet(payload: Dict[str, Any]):
    """Build a compact BEAST handoff packet for Ollama/cloud reasoning."""
    task = str(payload.get("task") or payload.get("goal") or payload.get("query") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="task/goal/query is required")
    return ollama_scout.build_packet(
        task=task,
        workspace_root=str(Path(__file__).resolve().parents[1]),
        model=payload.get("model"),
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
    )

@app.post("/edgek/ollama/scout")
async def edgek_ollama_scout(payload: Dict[str, Any]):
    """Use BEAST context tools plus local Ollama to classify/rank/pack a task."""
    try:
        return ollama_scout.scout(
            payload,
            workspace_root=str(Path(__file__).resolve().parents[1]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/task/envelope")
async def edgek_task_envelope(payload: Dict[str, Any]):
    """Build a canonical BEAST task envelope without executing the task."""
    if not any(payload.get(key) for key in ("user_request", "task", "goal")):
        raise HTTPException(status_code=400, detail="user_request/task/goal is required")
    envelope = task_envelope_builder.build(payload, dry_run=True)
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="task",
        payload=payload,
        artifacts={"envelope": envelope},
    )
    return {
        "mode": "dry_run",
        "envelope": envelope,
        "prec_lifecycle": _prec_summary(lifecycle),
    }

@app.post("/edgek/task/provider-diagnostic")
async def edgek_task_provider_diagnostic(payload: Dict[str, Any]):
    """Run a local-only provider diagnostic from a canonical task envelope."""
    if not any(payload.get(key) for key in ("user_request", "task", "goal", "provider")):
        raise HTTPException(status_code=400, detail="provider or user_request/task/goal is required")
    result = task_envelope_builder.diagnose_provider(
        payload,
        workspace_root=str(Path(__file__).resolve().parents[1]),
        write_chronicle=bool(payload.get("chronicle", True)),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="provider_diagnostic",
        payload=payload,
        artifacts={
            "envelope": result.get("envelope"),
            "route_card": result.get("route_card"),
            "quality_report": result.get("quality_report"),
            "chronicle": result.get("chronicle"),
            "diagnostic": result,
        },
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.post("/edgek/task/quality-cascade")
async def edgek_task_quality_cascade(payload: Dict[str, Any]):
    """Run route-card-driven local checks for a task before escalation."""
    if not any(payload.get(key) for key in ("user_request", "task", "goal", "provider")):
        raise HTTPException(status_code=400, detail="provider or user_request/task/goal is required")
    result = task_envelope_builder.run_quality_cascade(
        payload,
        workspace_root=str(Path(__file__).resolve().parents[1]),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="quality_cascade",
        payload=payload,
        artifacts={
            "envelope": result.get("envelope") or payload.get("envelope"),
            "route_card": result.get("route_card") or payload.get("route_card"),
            "quality_report": result,
        },
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.post("/edgek/quality/run")
async def edgek_quality_run(payload: Dict[str, Any]):
    """Compatibility alias for the Quality Cascade route."""
    return await edgek_task_quality_cascade(payload)

@app.post("/edgek/maintenance/run")
async def edgek_maintenance_run(payload: Dict[str, Any]):
    """Run repo hygiene checks after BEAST or agent-driven edits."""
    payload = payload or {}
    workspace_root = payload.get("workspace_root") or str(Path(__file__).resolve().parents[1])
    report = task_envelope_builder.quality_cascade.run_maintenance(
        workspace_root=str(workspace_root),
        run_tests=bool(payload.get("run_tests", False)),
        pytest_args=[str(item) for item in payload.get("pytest_args", [])],
        include_extension_checks=bool(payload.get("include_extension_checks", True)),
        include_markdown=bool(payload.get("include_markdown", True)),
        run_packaging=bool(payload.get("run_packaging", False)),
        python_versions=[str(item) for item in payload.get("python_versions", [])],
        timeout_seconds=int(payload.get("timeout_seconds", 60)),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="maintenance_cascade",
        payload=payload,
        artifacts={"maintenance_report": report},
    )
    report["prec_lifecycle"] = _prec_summary(lifecycle)
    return report

@app.post("/edgek/context/packet")
async def edgek_context_packet(payload: Dict[str, Any]):
    """Build a bounded, evidence-backed context packet for model handoff."""
    if not any(payload.get(key) for key in ("envelope", "user_request", "task", "goal", "provider")):
        raise HTTPException(status_code=400, detail="envelope or user_request/task/goal/provider is required")

    workspace_root = str(Path(__file__).resolve().parents[1])
    envelope = payload.get("envelope")
    if envelope is None:
        envelope = task_envelope_builder.build(payload, dry_run=bool(payload.get("dry_run", True)))

    provider = (
        envelope.get("inputs", {}).get("provider")
        or payload.get("provider")
        or "unknown"
    )
    task_class = envelope.get("task_class") or payload.get("task_class") or "general_software_task"
    route_card = payload.get("route_card")
    if route_card is None:
        persist_route = bool(payload.get("persist_route", False))
        if task_class == "provider_debugging":
            route_card = task_envelope_builder.provider_diagnostic_route_card(
                str(provider),
                envelope=envelope,
                persist=persist_route,
            )
        else:
            route_card = task_envelope_builder.generic_quality_route_card(
                str(task_class),
                envelope=envelope,
                persist=persist_route,
            )

    quality_report = payload.get("quality_report")
    if quality_report is None and bool(payload.get("run_quality", True)):
        quality_report = task_envelope_builder.quality_cascade.run(
            envelope,
            route_card,
            workspace_root=workspace_root,
        )

    context_packet = context_packet_builder.build(
        envelope,
        route_card=route_card,
        quality_report=quality_report,
        workspace_root=workspace_root,
        semantic_limit=max(1, min(int(payload.get("semantic_limit", 5)), 20)),
        include_content=bool(payload.get("include_content", True)),
        max_files=payload.get("max_files"),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="context_packet",
        payload=payload,
        artifacts={
            "envelope": envelope,
            "route_card": route_card,
            "quality_report": quality_report,
            "context_packet": context_packet,
        },
    )
    context_packet["prec_lifecycle"] = _prec_summary(lifecycle)
    return context_packet

@app.post("/edgek/forge/scorecard")
async def edgek_forge_scorecard(payload: Dict[str, Any]):
    """Score implementation/refactor shape before edits are made."""
    if not any(payload.get(key) for key in ("envelope", "user_request", "task", "goal", "context_packet")):
        raise HTTPException(status_code=400, detail="envelope/context_packet or user_request/task/goal is required")

    workspace_root = str(Path(__file__).resolve().parents[1])
    envelope = payload.get("envelope")
    if envelope is None:
        envelope = task_envelope_builder.build(payload, dry_run=True)

    route_card = payload.get("route_card")
    if route_card is None:
        task_class = envelope.get("task_class") or "general_software_task"
        provider = envelope.get("inputs", {}).get("provider") or payload.get("provider") or "unknown"
        if task_class == "provider_debugging":
            route_card = task_envelope_builder.provider_diagnostic_route_card(
                str(provider),
                envelope=envelope,
                persist=False,
            )
        else:
            route_card = task_envelope_builder.generic_quality_route_card(
                str(task_class),
                envelope=envelope,
                persist=False,
            )

    quality_report = payload.get("quality_report")
    if quality_report is None and bool(payload.get("run_quality", False)):
        quality_report = task_envelope_builder.quality_cascade.run(
            envelope,
            route_card,
            workspace_root=workspace_root,
        )

    context_packet = payload.get("context_packet")
    if context_packet is None and bool(payload.get("build_context", True)):
        context_packet = context_packet_builder.build(
            envelope,
            route_card=route_card,
            quality_report=quality_report,
            workspace_root=workspace_root,
            semantic_limit=max(1, min(int(payload.get("semantic_limit", 5)), 20)),
            include_content=bool(payload.get("include_content", True)),
            max_files=payload.get("max_files"),
        )

    scorecard = forge_scorecard_builder.build(
        envelope,
        context_packet=context_packet,
        quality_report=quality_report,
        route_card=route_card,
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="forge_scorecard",
        payload=payload,
        artifacts={
            "envelope": envelope,
            "route_card": route_card,
            "quality_report": quality_report,
            "context_packet": context_packet,
            "forge_scorecard": scorecard,
        },
    )
    scorecard["prec_lifecycle"] = _prec_summary(lifecycle)
    return scorecard

@app.post("/edgek/forge/decision")
async def edgek_forge_decision(payload: Dict[str, Any]):
    """Compatibility alias for Forge decision/scorecard generation."""
    return await edgek_forge_scorecard(payload)

@app.post("/edgek/workflow/plan")
async def edgek_workflow_plan(payload: Dict[str, Any]):
    """Build a Conductor workflow card using prepared artifacts and swarm advice."""
    if not any(payload.get(key) for key in ("envelope", "user_request", "task", "goal", "context_packet", "forge_scorecard")):
        raise HTTPException(status_code=400, detail="envelope/context/scorecard or user_request/task/goal is required")

    workspace_root = str(Path(__file__).resolve().parents[1])
    envelope = payload.get("envelope")
    if envelope is None:
        envelope = task_envelope_builder.build(payload, dry_run=True)

    route_card = payload.get("route_card")
    if route_card is None:
        task_class = envelope.get("task_class") or "general_software_task"
        provider = envelope.get("inputs", {}).get("provider") or payload.get("provider") or "unknown"
        if task_class == "provider_debugging":
            route_card = task_envelope_builder.provider_diagnostic_route_card(str(provider), envelope=envelope, persist=False)
        else:
            route_card = task_envelope_builder.generic_quality_route_card(str(task_class), envelope=envelope, persist=False)

    quality_report = payload.get("quality_report")
    if quality_report is None and bool(payload.get("run_quality", False)):
        quality_report = task_envelope_builder.quality_cascade.run(
            envelope,
            route_card,
            workspace_root=workspace_root,
        )

    context_packet = payload.get("context_packet")
    if context_packet is None and bool(payload.get("build_context", True)):
        context_packet = context_packet_builder.build(
            envelope,
            route_card=route_card,
            quality_report=quality_report,
            workspace_root=workspace_root,
            semantic_limit=max(1, min(int(payload.get("semantic_limit", 5)), 20)),
            include_content=bool(payload.get("include_content", True)),
            max_files=payload.get("max_files"),
        )

    forge_scorecard = payload.get("forge_scorecard")
    if forge_scorecard is None and bool(payload.get("build_scorecard", True)):
        forge_scorecard = forge_scorecard_builder.build(
            envelope,
            context_packet=context_packet,
            quality_report=quality_report,
            route_card=route_card,
        )

    workflow = conductor_workflow_builder.build(
        envelope,
        context_packet=context_packet,
        forge_scorecard=forge_scorecard,
        route_card=route_card,
        quality_report=quality_report,
        run_swarm=bool(payload.get("run_swarm", True)),
        persist=bool(payload.get("persist", False)),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="workflow",
        payload=payload,
        artifacts={
            "envelope": envelope,
            "route_card": route_card,
            "quality_report": quality_report,
            "context_packet": context_packet,
            "forge_scorecard": forge_scorecard,
            "workflow": workflow,
        },
    )
    workflow["prec_lifecycle"] = _prec_summary(lifecycle)
    return workflow

@app.post("/edgek/conductor/workflow-card")
async def edgek_conductor_workflow_card(payload: Dict[str, Any]):
    """Compatibility alias for Conductor workflow-card generation."""
    return await edgek_workflow_plan(payload)

@app.get("/edgek/workflow/cards")
async def edgek_workflow_cards(task_class: str = None, limit: int = 20):
    """List persisted Conductor workflow cards."""
    return conductor_workflow_builder.list_workflows(
        task_class=task_class,
        limit=max(1, min(limit, 100)),
    )

@app.get("/edgek/workflow/cards/{workflow_id}")
async def edgek_workflow_card_detail(workflow_id: str):
    """Return one persisted Conductor workflow card."""
    try:
        return conductor_workflow_builder.get_workflow(workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

def _prepare_workflow_artifacts(payload: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    envelope = payload.get("envelope")
    if envelope is None:
        envelope = task_envelope_builder.build(payload, dry_run=True)
    task_class = envelope.get("task_class") or payload.get("task_class") or "general_software_task"
    provider = envelope.get("inputs", {}).get("provider") or payload.get("provider") or "unknown"
    route_card = payload.get("route_card")
    if route_card is None:
        if task_class == "provider_debugging":
            route_card = task_envelope_builder.provider_diagnostic_route_card(str(provider), envelope=envelope, persist=False)
        else:
            route_card = task_envelope_builder.generic_quality_route_card(str(task_class), envelope=envelope, persist=False)
    quality_report = payload.get("quality_report")
    if quality_report is None and bool(payload.get("run_quality", False)):
        quality_report = task_envelope_builder.quality_cascade.run(envelope, route_card, workspace_root=workspace_root)
    context_packet = payload.get("context_packet")
    if context_packet is None and bool(payload.get("build_context", True)):
        context_packet = context_packet_builder.build(
            envelope,
            route_card=route_card,
            quality_report=quality_report,
            workspace_root=workspace_root,
            semantic_limit=max(1, min(int(payload.get("semantic_limit", 5)), 20)),
            include_content=bool(payload.get("include_content", True)),
            max_files=payload.get("max_files"),
        )
    forge_scorecard = payload.get("forge_scorecard")
    if forge_scorecard is None and bool(payload.get("build_scorecard", True)):
        forge_scorecard = forge_scorecard_builder.build(
            envelope,
            context_packet=context_packet,
            quality_report=quality_report,
            route_card=route_card,
        )
    workflow = payload.get("workflow") or payload.get("workflow_card")
    if workflow is None and bool(payload.get("build_workflow", True)):
        workflow = conductor_workflow_builder.build(
            envelope,
            context_packet=context_packet,
            forge_scorecard=forge_scorecard,
            route_card=route_card,
            quality_report=quality_report,
            run_swarm=bool(payload.get("run_swarm", True)),
            persist=bool(payload.get("persist_workflow", False)),
        )
    return {
        "envelope": envelope,
        "route_card": route_card,
        "quality_report": quality_report,
        "context_packet": context_packet,
        "forge_scorecard": forge_scorecard,
        "workflow": workflow,
    }

@app.post("/edgek/beast-cli/plan")
async def edgek_beast_cli_plan(payload: Dict[str, Any]):
    """Build an Openclaw/Nemoclaw local-first execution plan."""
    if not any(payload.get(key) for key in ("objective", "user_request", "task", "goal", "workflow", "workflow_card")):
        raise HTTPException(status_code=400, detail="objective/user_request/task/goal or workflow is required")
    workspace_root = str(Path(__file__).resolve().parents[1])
    artifacts = _prepare_workflow_artifacts(payload, workspace_root)
    objective = (
        payload.get("objective")
        or payload.get("user_request")
        or payload.get("task")
        or payload.get("goal")
        or artifacts["workflow"].get("task_id")
        or "Run BEAST CLI plan"
    )
    plan = beast_cli_executor.plan(
        objective=str(objective),
        workflow=artifacts.get("workflow"),
        context_packet=artifacts.get("context_packet"),
        insight_packet=payload.get("insight_packet") or (payload.get("handoff_precheck") or {}).get("insight_packet"),
        mode=payload.get("mode", "openclaw"),
        workspace_root=workspace_root,
        use_ollama=bool(payload.get("use_ollama", True)),
        scout_options=payload.get("scout_options") or {},
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="cli_plan",
        payload={**payload, "objective": objective},
        artifacts={**artifacts, "insight_packet": payload.get("insight_packet") or (payload.get("handoff_precheck") or {}).get("insight_packet")},
    )
    return {**plan, "artifacts": artifacts, "prec_lifecycle": _prec_summary(lifecycle)}

@app.post("/edgek/beast-cli/execute")
async def edgek_beast_cli_execute(payload: Dict[str, Any]):
    """Execute Openclaw/Nemoclaw actions through local inference and MCP gates."""
    if not any(payload.get(key) for key in ("objective", "user_request", "task", "goal", "workflow", "workflow_card")):
        raise HTTPException(status_code=400, detail="objective/user_request/task/goal or workflow is required")
    workspace_root = str(Path(__file__).resolve().parents[1])
    artifacts = _prepare_workflow_artifacts(payload, workspace_root)
    objective = (
        payload.get("objective")
        or payload.get("user_request")
        or payload.get("task")
        or payload.get("goal")
        or artifacts["workflow"].get("task_id")
        or "Run BEAST CLI execution"
    )
    result = beast_cli_executor.execute(
        objective=str(objective),
        workflow=artifacts.get("workflow"),
        context_packet=artifacts.get("context_packet"),
        insight_packet=payload.get("insight_packet") or (payload.get("handoff_precheck") or {}).get("insight_packet"),
        mode=payload.get("mode", "openclaw"),
        workspace_root=workspace_root,
        dry_run=bool(payload.get("dry_run", True)),
        approved=bool(payload.get("approved", False)),
        use_ollama=bool(payload.get("use_ollama", True)),
        scout_options=payload.get("scout_options") or {},
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="cli_execute",
        payload={**payload, "objective": objective},
        artifacts={**artifacts, "insight_packet": payload.get("insight_packet") or (payload.get("handoff_precheck") or {}).get("insight_packet")},
    )
    return {**result, "artifacts": artifacts, "prec_lifecycle": _prec_summary(lifecycle)}

@app.get("/edgek/canon/schemas")
async def edgek_canon_schemas():
    """Return the canonical BEAST V2 schema catalog."""
    return canon_registry.schema_catalog()

@app.post("/edgek/canon/validate")
async def edgek_canon_validate(payload: Dict[str, Any]):
    """Validate one BEAST object or an artifact bundle."""
    if not payload:
        raise HTTPException(status_code=400, detail="object or artifacts payload is required")
    return canon_registry.validate(payload)

@app.get("/edgek/canon/metrics")
async def edgek_canon_metrics():
    """Return Canon registry coverage and cross-reference rules."""
    return canon_registry.metrics()

@app.get("/edgek/chronicle")
async def edgek_chronicle(
    task_class: str = None,
    provider: str = None,
    category: str = None,
    limit: int = 20,
):
    """List local Chronicle records."""
    return task_envelope_builder.list_chronicles(
        task_class=task_class,
        provider=provider,
        category=category,
        limit=max(1, min(limit, 100)),
    )

@app.get("/edgek/chronicle/{task_id}")
async def edgek_chronicle_detail(task_id: str):
    """Return one local Chronicle record and its Markdown projection."""
    try:
        return task_envelope_builder.get_chronicle(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/chronicle/publish")
async def edgek_chronicle_publish(payload: Dict[str, Any] = None):
    """Draft or dry-run publish Chronicle projections to governed targets."""
    payload = payload or {}
    chronicle = payload.get("chronicle")
    task_id = payload.get("task_id")
    if chronicle is None and task_id:
        try:
            chronicle = task_envelope_builder.get_chronicle(str(task_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    if chronicle is None:
        raise HTTPException(status_code=400, detail="chronicle or task_id is required")
    targets = payload.get("targets")
    if isinstance(targets, str):
        targets = [item.strip() for item in targets.split(",") if item.strip()]
    result = chronicle_publisher.publish(
        chronicle,
        targets=targets,
        approved=bool(payload.get("approved", False)),
        dry_run=bool(payload.get("dry_run", True)),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="chronicle_publish",
        payload=payload,
        artifacts={"chronicle": chronicle, "capability_signals": result.get("projections") or []},
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.post("/edgek/insights/compile")
async def edgek_insights_compile(payload: Dict[str, Any] = None):
    """Compile ranked local evidence from Chronicle/provider diagnostic memory."""
    payload = payload or {}
    result = insight_compiler.compile(
        objective=str(payload.get("objective") or payload.get("task") or payload.get("goal") or ""),
        provider=payload.get("provider"),
        task_class=payload.get("task_class"),
        limit=max(1, min(int(payload.get("limit", 10)), 100)),
        current_task=payload.get("current_task"),
        evidence_records=payload.get("evidence_records") or payload.get("live_evidence") or [],
        include_forensic_context=bool(payload.get("include_forensic_context", True)),
        forensic_limit=max(1, min(int(payload.get("forensic_limit", 8)), 50)),
        forensic_layer=payload.get("forensic_layer"),
        forensic_event_kind=payload.get("forensic_event_kind"),
        forensic_provider=payload.get("forensic_provider"),
        forensic_status=payload.get("forensic_status"),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="insight_compile",
        payload=payload,
        artifacts={"insight_packet": result, "evidence_records": result.get("evidence") or []},
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.post("/edgek/handoff/prepare")
async def edgek_handoff_prepare(payload: Dict[str, Any] = None):
    """Require current task markup before preparing a cloud handoff packet."""
    payload = payload or {}
    result = insight_compiler.prepare_handoff(
        current_task=payload.get("current_task") or {},
        objective=str(payload.get("objective") or payload.get("task") or payload.get("goal") or ""),
        provider=payload.get("provider"),
        task_class=payload.get("task_class"),
        limit=max(1, min(int(payload.get("limit", 8)), 50)),
        persist_task=bool(payload.get("persist_task", True)),
        evidence_records=payload.get("evidence_records") or payload.get("live_evidence") or [],
        include_forensic_context=bool(payload.get("include_forensic_context", True)),
        forensic_limit=max(1, min(int(payload.get("forensic_limit", 8)), 50)),
        forensic_layer=payload.get("forensic_layer"),
        forensic_event_kind=payload.get("forensic_event_kind"),
        forensic_provider=payload.get("forensic_provider"),
        forensic_status=payload.get("forensic_status"),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="handoff",
        payload=payload,
        artifacts={
            "insight_packet": result.get("insight_packet"),
            "evidence_records": (result.get("insight_packet") or {}).get("evidence") or [],
            "context_packet": result.get("context_packet"),
        },
    )
    result["prec_lifecycle"] = _prec_summary(lifecycle)
    return result

@app.post("/edgek/evidence/score")
async def edgek_evidence_score(payload: Dict[str, Any] = None):
    """Score one normalized evidence envelope for ranking and promotion."""
    payload = payload or {}
    return evidence_scorer.score(
        relevance=float(payload.get("relevance") or 0.4),
        confidence=float(payload.get("confidence") or 0.5),
        severity=str(payload.get("severity") or "info"),
        freshness=float(payload.get("freshness") or 1.0),
        repeat_count=int(payload.get("repeat_count") or 1),
        verification_strength=float(payload.get("verification_strength") or 0.35),
        blast_radius=float(payload.get("blast_radius") or 0.4),
    ).to_dict()

@app.get("/edgek/capabilities")
async def edgek_capabilities(kind: str = None):
    """Return governed capability inventory across tools, skills, routes, parsers, and workflows."""
    return capability_registry.list_capabilities(kind=kind)

@app.get("/edgek/capabilities/families")
async def edgek_capability_families():
    """Return capability families for routing and prioritization."""
    return capability_registry.list_families()

@app.get("/edgek/vector/adapters")
async def edgek_vector_adapters():
    """Return active and future vector/RAG adapter status."""
    return vector_adapter_registry.list_adapters()

@app.get("/edgek/route/cards")
async def edgek_route_cards(task_class: str = None, provider: str = None, limit: int = 20):
    """List persisted Pathfinder route cards."""
    return task_envelope_builder.list_route_cards(
        task_class=task_class,
        provider=provider,
        limit=max(1, min(limit, 100)),
    )

@app.get("/edgek/route/cards/{route_id}")
async def edgek_route_card_detail(route_id: str):
    """Return one persisted Pathfinder route card."""
    try:
        return task_envelope_builder.get_route_card(route_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/route/provider-diagnostic/{provider}")
async def edgek_provider_diagnostic_route_card(provider: str, payload: Dict[str, Any] = None):
    """Create or refresh the provider diagnostic route card for a provider."""
    payload = payload or {}
    envelope = payload.get("envelope")
    if envelope is None and any(payload.get(key) for key in ("user_request", "task", "goal")):
        envelope = task_envelope_builder.build(
            {**payload, "provider": provider, "task_class": "provider_debugging"},
            dry_run=True,
        )
    return task_envelope_builder.provider_diagnostic_route_card(
        provider,
        envelope=envelope,
        persist=bool(payload.get("persist", True)),
    )

@app.post("/edgek/pathfinder/route-card")
async def edgek_pathfinder_route_card(payload: Dict[str, Any] = None):
    """Compatibility alias for Pathfinder route-card generation."""
    payload = payload or {}
    envelope = payload.get("envelope")
    if envelope is None and any(payload.get(key) for key in ("user_request", "task", "goal", "provider")):
        envelope = task_envelope_builder.build(payload, dry_run=True)
    provider = payload.get("provider") or (envelope or {}).get("inputs", {}).get("provider") or "unknown"
    return task_envelope_builder.provider_diagnostic_route_card(
        str(provider),
        envelope=envelope,
        persist=bool(payload.get("persist", True)),
    )

@app.get("/edgek/memory/stack")
async def edgek_memory_stack(session_id: str = "default"):
    """Return the canonical L0-L4 BEAST memory and governance stack."""
    return memory_stack.state(session_id=session_id)

@app.post("/edgek/isolation-forest/predict")
async def edgek_isolation_forest_predict(payload: Dict[str, Any]):
    """Fit a deterministic Isolation Forest and score supplied records."""
    rows = payload.get("rows")
    if not rows:
        raise HTTPException(status_code=400, detail="Missing rows")
    model = IsolationForest(
        n_trees=int(payload.get("n_trees", 100)),
        sample_size=int(payload.get("sample_size", min(256, len(rows)))),
        contamination=float(payload.get("contamination", 0.01)),
        random_state=int(payload.get("random_state", 1337)),
    )
    model.fit(rows, features=payload.get("features"))
    return {
        "model": model.state(),
        "predictions": model.predict(payload.get("score_rows", rows)),
    }

@app.post("/edgek/tool-laziness/record")
async def edgek_tool_laziness_record(payload: Dict[str, Any]):
    """Record a tool/provider outcome and return learned recommendation."""
    try:
        return tool_laziness_learner.record(
            tool_name=payload["tool_name"],
            scenario=payload["scenario"],
            called=bool(payload.get("called", True)),
            useful=bool(payload.get("useful", False)),
            tokens_spent=int(payload.get("tokens_spent", 0)),
            cost_usd=float(payload.get("cost_usd", 0.0)),
            latency_ms=float(payload.get("latency_ms", 0.0)),
            value_score=float(payload.get("value_score", 0.0)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing {exc}")

@app.get("/edgek/tool-laziness/recommend")
async def edgek_tool_laziness_recommend(tool_name: str, scenario: str):
    """Return learned call/skip recommendation for a tool/scenario pair."""
    return tool_laziness_learner.recommend(tool_name, scenario)

@app.get("/edgek/tool-laziness/semantic-recommend")
async def edgek_tool_laziness_semantic_recommend(
    tool_name: str,
    scenario: str,
    objective: str,
    min_similarity: float = 0.55,
):
    """Return learned call/skip recommendation blended with semantic workspace evidence."""
    return tool_laziness_learner.semantic_recommend(
        tool_name=tool_name,
        scenario=scenario,
        objective=objective,
        workspace_graph=crystallizer.workspace_graph,
        min_similarity=max(0.0, min(float(min_similarity), 1.0)),
    )

@app.post("/edgek/tool-laziness/benchmark")
async def edgek_tool_laziness_benchmark():
    """Run a deterministic learning benchmark for redundant provider calls."""
    return tool_laziness_learner.benchmark_learning()

@app.post("/edgek/tool-laziness/schema-benchmark")
async def edgek_tool_laziness_schema_benchmark(payload: Dict[str, Any] = None):
    """Run a high-token MCP schema laziness benchmark."""
    payload = payload or {}
    return tool_laziness_learner.benchmark_schema_laziness(
        tool_count=int(payload.get("tool_count", 72)),
        turns=int(payload.get("turns", 36)),
        relevant_tools_per_turn=int(payload.get("relevant_tools_per_turn", 5)),
    )

@app.get("/edgek/deploy/litellm-config")
async def edgek_deploy_litellm_config(beast_base_url: str = "http://127.0.0.1:8000"):
    """Return a LiteLLM config generated from BEAST provider policy."""
    return deployment_manager.generate_litellm_config(beast_base_url=beast_base_url)

@app.get("/edgek/deploy/litellm-config.yaml")
async def edgek_deploy_litellm_config_yaml(beast_base_url: str = "http://127.0.0.1:8000"):
    """Return generated LiteLLM YAML."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        deployment_manager.generate_litellm_yaml(beast_base_url=beast_base_url),
        media_type="application/yaml",
    )

@app.get("/edgek/deploy/nginx-config")
async def edgek_deploy_nginx_config(
    server_name: str = "localhost",
    listen_port: int = 8080,
    beast_upstream: str = "127.0.0.1:8000",
    litellm_upstream: str = "127.0.0.1:4000",
):
    """Return generated Nginx reverse-proxy config."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        deployment_manager.generate_nginx_config(
            server_name=server_name,
            listen_port=listen_port,
            beast_upstream=beast_upstream,
            litellm_upstream=litellm_upstream,
        ),
        media_type="text/plain",
    )

@app.get("/edgek/deploy/tgi-llamacpp")
async def edgek_deploy_tgi_llamacpp(
    model_id: str = "Qwen/Qwen2.5-3B-Instruct",
    listen_port: int = 3000,
    models_dir: str = "$HOME/models",
    gpu: bool = False,
    n_gpu_layers: int = 99,
    model_gguf: str = "",
):
    """Return TGI llama.cpp deployment commands for a governed local sidecar."""
    return deployment_manager.generate_tgi_llamacpp_config(
        model_id=model_id,
        listen_port=listen_port,
        models_dir=models_dir,
        gpu=gpu,
        n_gpu_layers=n_gpu_layers,
        model_gguf=model_gguf,
    )

@app.post("/edgek/deploy/write-configs")
async def edgek_deploy_write_configs(payload: Dict[str, Any] = None):
    """Write generated LiteLLM/Nginx configs into deploy/generated by default."""
    payload = payload or {}
    return deployment_manager.write_generated_files(payload.get("output_dir", "deploy/generated"))

@app.post("/edgek/deploy/nginx/apply")
async def edgek_deploy_nginx_apply(payload: Dict[str, Any] = None):
    """Write/test/reload Nginx config; dry-run and approval-gated by default."""
    payload = payload or {}
    return deployment_manager.apply_nginx_config(
        output_dir=payload.get("output_dir", "deploy/generated"),
        nginx_conf_path=str(payload.get("nginx_conf_path") or ""),
        reload_command=str(payload.get("reload_command") or "nginx -s reload"),
        test_command=str(payload.get("test_command") or "nginx -t"),
        dry_run=bool(payload.get("dry_run", True)),
        approved=bool(payload.get("approved", False)),
    )

@app.get("/edgek/deploy/litellm-sidecar/state")
async def edgek_litellm_sidecar_state(pid_file: str = "deploy/run/litellm.pid", port: int = 4000):
    """Return managed LiteLLM sidecar process state."""
    return deployment_manager.litellm_sidecar_status(pid_file=pid_file, port=port)

@app.post("/edgek/deploy/litellm-sidecar/start")
async def edgek_litellm_sidecar_start(payload: Dict[str, Any] = None):
    """Start LiteLLM sidecar; dry-run and approval-gated by default."""
    payload = payload or {}
    return deployment_manager.start_litellm_sidecar(
        config_path=payload.get("config_path", "deploy/generated/litellm.config.yaml"),
        pid_file=payload.get("pid_file", "deploy/run/litellm.pid"),
        port=int(payload.get("port", 4000)),
        dry_run=bool(payload.get("dry_run", True)),
        approved=bool(payload.get("approved", False)),
    )

@app.post("/edgek/deploy/litellm-sidecar/stop")
async def edgek_litellm_sidecar_stop(payload: Dict[str, Any] = None):
    """Stop LiteLLM sidecar; dry-run and approval-gated by default."""
    payload = payload or {}
    return deployment_manager.stop_litellm_sidecar(
        pid_file=payload.get("pid_file", "deploy/run/litellm.pid"),
        dry_run=bool(payload.get("dry_run", True)),
        approved=bool(payload.get("approved", False)),
    )

@app.get("/edgek/prompt-cache/state")
async def edgek_prompt_cache_state():
    """Return prompt-cache keepalive manager state."""
    return deployment_manager.keepalive_state()

@app.get("/edgek/prompt-cache/keepalives")
async def edgek_prompt_cache_keepalives():
    """List registered prompt-cache keepalives."""
    return {"keepalives": deployment_manager.list_keepalives()}

@app.post("/edgek/prompt-cache/keepalives")
async def edgek_prompt_cache_register(payload: Dict[str, Any]):
    """Register an explicit, auditable prompt-cache keepalive."""
    try:
        return deployment_manager.register_keepalive(
            provider=payload["provider"],
            model=payload["model"],
            cache_key=payload["cache_key"],
            interval_seconds=int(payload.get("interval_seconds", 240)),
            ttl_seconds=int(payload.get("ttl_seconds", 1800)),
            ping_url=payload.get("ping_url", ""),
            enabled=bool(payload.get("enabled", True)),
            authorized=bool(payload.get("authorized", False)),
            dry_run=bool(payload.get("dry_run", True)),
            metadata=payload.get("metadata"),
            cache_id=payload.get("cache_id"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/prompt-cache/tick")
async def edgek_prompt_cache_tick(payload: Dict[str, Any] = None):
    """Process due prompt-cache keepalives; network pings are opt-in."""
    payload = payload or {}
    return deployment_manager.tick_keepalives(
        allow_network=bool(payload.get("allow_network", False)),
        limit=int(payload.get("limit", 20)),
    )

@app.get("/edgek/prompt-cache/events")
async def edgek_prompt_cache_events(limit: int = 50):
    """Return recent prompt-cache keepalive audit events."""
    return {"events": deployment_manager.recent_keepalive_events(limit=limit)}

@app.get("/edgek/enterprise/state")
async def edgek_enterprise_state():
    """Return Phase 9 enterprise control-plane state."""
    return enterprise_manager.state()

@app.post("/edgek/enterprise/teams")
async def edgek_enterprise_create_team(payload: Dict[str, Any]):
    """Create a team with per-team budget limits."""
    try:
        return enterprise_manager.create_team(
            name=payload["name"],
            team_id=payload.get("team_id"),
            daily_request_limit=payload.get("daily_request_limit"),
            daily_cost_limit_usd=payload.get("daily_cost_limit_usd"),
            metadata=payload.get("metadata"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/enterprise/teams")
async def edgek_enterprise_teams():
    """List teams."""
    return {"teams": enterprise_manager.list_teams()}

@app.get("/edgek/enterprise/teams/{team_id}")
async def edgek_enterprise_team(team_id: str):
    """Return one team."""
    try:
        return enterprise_manager.get_team(team_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/enterprise/users")
async def edgek_enterprise_create_user(payload: Dict[str, Any]):
    """Create a user under a team."""
    try:
        return enterprise_manager.create_user(
            team_id=payload["team_id"],
            email=payload["email"],
            role=payload.get("role", "member"),
            user_id=payload.get("user_id"),
            metadata=payload.get("metadata"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/enterprise/virtual-keys")
async def edgek_enterprise_issue_virtual_key(payload: Dict[str, Any]):
    """Issue a virtual key. The secret is returned once."""
    try:
        return enterprise_manager.issue_virtual_key(
            team_id=payload["team_id"],
            user_id=payload["user_id"],
            scopes=payload.get("scopes"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/enterprise/auth/verify")
async def edgek_enterprise_verify_key(payload: Dict[str, Any]):
    """Verify a virtual key and optional required scope."""
    try:
        context = enterprise_manager.authenticate_virtual_key(
            payload["virtual_key"],
            required_scope=payload.get("required_scope"),
        )
        return {
            "authenticated": True,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "key_id": context.key_id,
            "scopes": context.scopes,
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc))

@app.get("/edgek/enterprise/teams/{team_id}/budget")
async def edgek_enterprise_team_budget(team_id: str):
    """Return per-team budget state."""
    try:
        return enterprise_manager.team_budget_summary(team_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/enterprise/teams/{team_id}/budget/check")
async def edgek_enterprise_team_budget_check(team_id: str, payload: Dict[str, Any] = None):
    """Check projected usage against team budget."""
    payload = payload or {}
    try:
        return enterprise_manager.check_team_budget(
            team_id,
            projected_requests=int(payload.get("projected_requests", 1)),
            projected_cost_usd=float(payload.get("projected_cost_usd", 0.0)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/enterprise/usage")
async def edgek_enterprise_record_usage(payload: Dict[str, Any]):
    """Record per-team usage for budget accounting."""
    try:
        return enterprise_manager.record_team_usage(
            team_id=payload["team_id"],
            user_id=payload["user_id"],
            key_id=payload.get("key_id", ""),
            provider=payload.get("provider", ""),
            model=payload.get("model", ""),
            request_count=int(payload.get("request_count", 1)),
            estimated_cost_usd=float(payload.get("estimated_cost_usd", 0.0)),
            total_tokens=int(payload.get("total_tokens", 0)),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/enterprise/observability")
async def edgek_enterprise_record_observability(payload: Dict[str, Any]):
    """Record a centralized observability event."""
    try:
        return enterprise_manager.record_observability_event(
            team_id=payload["team_id"],
            user_id=payload.get("user_id", ""),
            event_type=payload["event_type"],
            severity=payload.get("severity", "info"),
            payload=payload.get("payload"),
            trace_id=payload.get("trace_id", ""),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/enterprise/observability")
async def edgek_enterprise_observability(team_id: str = None, limit: int = 50):
    """List centralized observability events."""
    return {
        "events": enterprise_manager.observability_events(
            team_id=team_id,
            limit=max(1, min(limit, 200)),
        )
    }

@app.get("/edgek/enterprise/otel")
async def edgek_enterprise_otel(team_id: str = None, limit: int = 50):
    """Export observability events in an OTLP-like JSON shape."""
    return enterprise_manager.otel_export(
        team_id=team_id,
        limit=max(1, min(limit, 200)),
    )

@app.post("/edgek/enterprise/policy-packs")
async def edgek_enterprise_register_policy_pack(payload: Dict[str, Any]):
    """Register or update a policy pack."""
    try:
        return enterprise_manager.register_policy_pack(
            name=payload["name"],
            policy_overlay=payload["policy_overlay"],
            version=payload.get("version", "1.0.0"),
            pack_id=payload.get("pack_id"),
            active=bool(payload.get("active", True)),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/enterprise/policy-packs")
async def edgek_enterprise_policy_packs():
    """List policy packs."""
    return {"policy_packs": enterprise_manager.list_policy_packs()}

@app.post("/edgek/enterprise/teams/{team_id}/policy-packs/{pack_id}")
async def edgek_enterprise_assign_policy_pack(team_id: str, pack_id: str):
    """Assign a policy pack to a team."""
    try:
        return enterprise_manager.assign_policy_pack(team_id, pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/enterprise/teams/{team_id}/policy")
async def edgek_enterprise_effective_policy(team_id: str):
    """Return a team's effective policy after active policy packs are merged."""
    try:
        return enterprise_manager.effective_policy(team_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/enterprise/traces/encrypted")
async def edgek_enterprise_store_encrypted_trace(payload: Dict[str, Any]):
    """Store a sealed trace record for a team."""
    try:
        return enterprise_manager.store_encrypted_trace(
            team_id=payload["team_id"],
            user_id=payload.get("user_id", ""),
            trace=payload["trace"],
            trace_id=payload.get("trace_id"),
            metadata=payload.get("metadata"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/enterprise/teams/{team_id}/traces/{trace_id}")
async def edgek_enterprise_get_encrypted_trace(team_id: str, trace_id: str):
    """Retrieve and verify a sealed trace record."""
    try:
        return enterprise_manager.retrieve_encrypted_trace(team_id, trace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/edgek/swarm/state")
async def edgek_swarm_state():
    """Return Phase 8 swarm kernel state."""
    return swarm_kernel.state()

@app.get("/edgek/swarm/governance")
async def edgek_swarm_governance(profile: str = None):
    """Return governed swarm profiles and role lanes."""
    return swarm_kernel.governed_roles(profile=profile)

@app.post("/edgek/swarm/run")
async def edgek_swarm_run(payload: Dict[str, Any]):
    """Run a deterministic swarm planning/supervision cycle."""
    try:
        return swarm_kernel.run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/swarm/runs")
async def edgek_swarm_runs(status: str = None, limit: int = 20):
    """List recent swarm runs."""
    return {
        "runs": swarm_kernel.recent_runs(
            status=status,
            limit=max(1, min(limit, 100)),
        )
    }

@app.get("/edgek/swarm/runs/{run_id}")
async def edgek_swarm_run_detail(run_id: str):
    """Return one swarm run with role events and value logs."""
    try:
        return swarm_kernel.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/edgek/swarm/value")
async def edgek_swarm_value(limit: int = 50):
    """Return recent measurable value logs from swarm runs."""
    return {
        "value_logs": swarm_kernel.value_logs(limit=max(1, min(limit, 200)))
    }

@app.get("/edgek/skills/state")
async def edgek_skills_state():
    """Return Phase 7 skill-tree state."""
    return skill_tree.state()

@app.get("/edgek/skills")
async def edgek_skills(category: str = None, limit: int = 50):
    """List learned skills, optionally filtered by category."""
    return {
        "skills": skill_tree.list_skills(
            category=category,
            limit=max(1, min(limit, 200)),
        )
    }

@app.post("/edgek/skills/mine")
async def edgek_skills_mine(payload: Dict[str, Any] = None):
    """Mine successful traces or supplied tool sequences for repeated patterns."""
    payload = payload or {}
    return skill_tree.mine(
        sequences=payload.get("sequences"),
        min_length=max(2, int(payload.get("min_length", 2))),
        min_frequency=max(1, int(payload.get("min_frequency", 3))),
        use_approximate=bool(payload.get("use_approximate", True)),
        store=bool(payload.get("store", True)),
    )

@app.get("/edgek/skills/patterns")
async def edgek_skills_patterns(status: str = None, min_confidence: float = 0.0):
    """List detected repeated sequence patterns."""
    return {
        "patterns": skill_tree.list_patterns(
            status=status,
            min_confidence=max(0.0, min(float(min_confidence), 1.0)),
        )
    }

@app.post("/edgek/skills/candidates/generate")
async def edgek_skills_generate_candidates(payload: Dict[str, Any] = None):
    """Generate meta-tool candidates from stored sequence patterns."""
    payload = payload or {}
    return skill_tree.generate_candidates(
        min_frequency=max(1, int(payload.get("min_frequency", 3))),
        min_confidence=max(0.0, min(float(payload.get("min_confidence", 0.6)), 1.0)),
        status=payload.get("status"),
    )

@app.get("/edgek/skills/candidates")
async def edgek_skills_candidates(limit: int = 20):
    """List generated meta-tool candidates."""
    return {
        "candidates": skill_tree.list_candidates(limit=max(1, min(limit, 100)))
    }

@app.post("/edgek/skills/promotion-check")
async def edgek_skills_promotion_check(payload: Dict[str, Any] = None):
    """Create an approval-gated V2 promotion candidate from artifact evidence."""
    payload = payload or {}
    return promotion_loop.check(
        artifacts=payload.get("artifacts") or {},
        task_class=payload.get("task_class"),
        provider=payload.get("provider"),
        category=payload.get("category"),
        route_id=payload.get("route_id"),
        min_repetitions=max(1, int(payload.get("min_repetitions", 2))),
        persist=bool(payload.get("persist", True)),
    )

@app.get("/edgek/skills/promotion-candidates")
async def edgek_skills_promotion_candidates(limit: int = 20):
    """List persisted V2 promotion candidates."""
    return promotion_loop.list_candidates(limit=max(1, min(limit, 100)))

@app.get("/edgek/skills/promotion-candidates/{candidate_id}")
async def edgek_skills_promotion_candidate(candidate_id: str):
    """Return one persisted V2 promotion candidate."""
    try:
        return promotion_loop.get_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/skills/promote")
async def edgek_skills_promote(payload: Dict[str, Any]):
    """Promote an eligible V2 promotion candidate into the SkillRegistry."""
    try:
        return promotion_loop.promote(
            candidate=payload.get("candidate"),
            candidate_id=payload.get("candidate_id"),
            approved_by=payload.get("approved_by", "user"),
            require_eligible=bool(payload.get("require_eligible", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/skills/candidates/{candidate_id}")
async def edgek_skills_candidate(candidate_id: str):
    """Return one generated meta-tool candidate."""
    candidate = skill_tree.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Meta-tool candidate not found: {candidate_id}")
    return candidate

@app.post("/edgek/skills/candidates/{candidate_id}/validate")
async def edgek_skills_validate_candidate(candidate_id: str, payload: Dict[str, Any] = None):
    """Validate a meta-tool candidate in the sandbox validator."""
    payload = payload or {}
    result = skill_tree.validate_candidate(
        candidate_id,
        test_scenarios=payload.get("test_scenarios"),
    )
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["errors"][0] if result["errors"] else "Validation failed")
    return result

@app.get("/edgek/skills/candidates/{candidate_id}/validations")
async def edgek_skills_candidate_validations(candidate_id: str):
    """Return sandbox validation history for a meta-tool candidate."""
    return {
        "validations": skill_tree.validation_history(candidate_id)
    }

@app.post("/edgek/skills/candidates/{candidate_id}/promote")
async def edgek_skills_promote_candidate(candidate_id: str, payload: Dict[str, Any] = None):
    """Promote a validated, user-approved meta-tool candidate into the skill registry."""
    payload = payload or {}
    try:
        return skill_tree.promote_candidate(
            candidate_id,
            approved_by=payload.get("approved_by", "user"),
            require_validation=bool(payload.get("require_validation", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/workspace")
async def edgek_workspace(limit: int = 20):
    """Expose recent workspace graph nodes for local inspection."""
    return {
        "stats": crystallizer.workspace_graph.stats(),
        "recent_nodes": crystallizer.workspace_graph.recent_nodes(limit=max(1, min(limit, 100)))
    }

@app.post("/edgek/workspace/index")
async def edgek_workspace_index(payload: Dict[str, Any] = None):
    """Index a repository path into the workspace graph."""
    payload = payload or {}
    root_path = payload.get("root_path") or str(Path(__file__).resolve().parents[1])
    max_files = int(payload.get("max_files", 1000))
    return crystallizer.workspace_graph.index_repository(
        root_path=root_path,
        max_files=max(1, min(max_files, 5000)),
        include_patterns=payload.get("include_patterns"),
        exclude_dirs=payload.get("exclude_dirs"),
    )

@app.post("/edgek/workspace/rebuild")
async def edgek_workspace_rebuild(payload: Dict[str, Any] = None):
    """Backfill or rebuild the workspace graph from archived traces."""
    payload = payload or {}
    trace_path = payload.get("trace_path") or str(crystallizer.trace_path)
    clear_existing = bool(payload.get("clear_existing", False))
    return crystallizer.workspace_graph.rebuild_from_traces(
        trace_path=trace_path,
        clear_existing=clear_existing,
    )

@app.get("/edgek/workspace/export")
async def edgek_workspace_export(node_limit: int = 1000, edge_limit: int = 2000):
    """Export a bounded workspace graph snapshot."""
    return crystallizer.workspace_graph.export_graph(
        node_limit=max(1, min(node_limit, 5000)),
        edge_limit=max(1, min(edge_limit, 10000)),
    )

@app.get("/edgek/workspace/integrity")
async def edgek_workspace_integrity(sample_limit: int = 20):
    """Return workspace graph integrity checks."""
    return crystallizer.workspace_graph.integrity_report(
        sample_limit=max(1, min(sample_limit, 100))
    )

@app.get("/edgek/workspace/search")
async def edgek_workspace_search(q: str, node_type: str = None, limit: int = 20):
    """Search workspace graph nodes by id or label."""
    return {
        "query": q,
        "node_type": node_type,
        "results": crystallizer.workspace_graph.search_nodes(
            query=q,
            node_type=node_type,
            limit=max(1, min(limit, 100))
        )
    }

@app.get("/edgek/workspace/vector_search")
async def edgek_workspace_vector_search(q: str, limit: int = 10):
    """Perform vector similarity search on workspace graph nodes."""
    return {
        "query": q,
        "limit": limit,
        "results": crystallizer.workspace_graph.vector_search(
            query_text=q,
            limit=max(1, min(limit, 50))
        )
    }

@app.post("/edgek/workspace/semantic-index")
async def edgek_workspace_semantic_index(payload: Dict[str, Any] = None):
    """Build semantic chunk embeddings for repository RAG/context selection."""
    payload = payload or {}
    root_path = payload.get("root_path") or str(Path(__file__).resolve().parents[1])
    return crystallizer.workspace_graph.semantic_index_repository(
        root_path=root_path,
        max_files=max(1, min(int(payload.get("max_files", 200)), 2000)),
        max_chunks=max(1, min(int(payload.get("max_chunks", 1000)), 10000)),
        include_patterns=payload.get("include_patterns"),
        exclude_dirs=payload.get("exclude_dirs"),
    )

@app.post("/edgek/memory/artifacts/index")
async def edgek_memory_artifacts_index(payload: Dict[str, Any] = None):
    """Index BEAST Chronicle/route/envelope/outcome artifacts for RAG memory."""
    payload = payload or {}
    data_dir = payload.get("data_dir") or str(Path(__file__).resolve().parents[1] / "data")
    return crystallizer.workspace_graph.index_beast_artifacts(
        data_dir=data_dir,
        max_records=max(1, min(int(payload.get("max_records", 500)), 5000)),
        include_embeddings=bool(payload.get("include_embeddings", True)),
    )

@app.get("/edgek/memory/artifacts/context")
async def edgek_memory_artifacts_context(q: str, limit: int = 8):
    """Retrieve Chronicle/route/envelope artifact memory for a query."""
    return crystallizer.workspace_graph.artifact_context(
        query_text=q,
        limit=max(1, min(limit, 50)),
    )

@app.get("/edgek/workspace/semantic-context")
async def edgek_workspace_semantic_context(
    q: str,
    limit: int = 8,
    include_content: bool = True,
    file_glob: str = None,
    node_type: str = None,
):
    """Return compact semantic context chunks for memory/forensics/RAG use."""
    return crystallizer.workspace_graph.semantic_context(
        query_text=q,
        limit=max(1, min(limit, 50)),
        include_content=include_content,
        file_glob=file_glob,
        node_types=[node_type] if node_type else None,
    )

@app.post("/edgek/semantic/dedupe")
async def edgek_semantic_dedupe(payload: Dict[str, Any]):
    """Deduplicate repeated payloads by exact and semantic similarity."""
    payloads = payload.get("payloads")
    if not isinstance(payloads, list):
        raise HTTPException(status_code=400, detail="payloads must be a list")
    return crystallizer.workspace_graph.semantic_dedupe_payloads(
        payloads,
        similarity_threshold=max(0.0, min(float(payload.get("similarity_threshold", 0.92)), 1.0)),
    )

@app.get("/edgek/workspace/nodes/{node_id:path}")
async def edgek_workspace_node(node_id: str):
    """Return a workspace graph node and one-hop neighborhood."""
    node = crystallizer.workspace_graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Workspace graph node not found: {node_id}")
    return crystallizer.workspace_graph.neighborhood(node_id)

@app.post("/edgek/mcp/evaluate")
async def edgek_mcp_evaluate(payload: Dict[str, Any]):
    """Evaluate an MCP/tool request against policy without executing it."""
    return mcp_broker.evaluate(payload).to_dict()

@app.post("/edgek/mcp/execute")
async def edgek_mcp_execute(payload: Dict[str, Any]):
    """Execute a supported MCP request after policy and approval checks."""
    try:
        return mcp_broker.execute(
            payload,
            workspace_root=str(Path(__file__).resolve().parents[1])
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/mcp/state")
async def edgek_mcp_state():
    """Return MCP broker state and recent audit events."""
    return {
        "stats": mcp_broker.stats(),
        "servers": mcp_broker.list_servers(),
        "pending_approvals": mcp_broker.list_approvals(status="pending", limit=20),
        "recent_audit_events": mcp_broker.recent_audit_events(limit=20),
        "recent_execution_events": mcp_broker.recent_execution_events(limit=20),
        "schema_pins": mcp_broker.list_schema_pins(limit=50),
    }

@app.get("/edgek/mcp/schema-pins")
async def edgek_mcp_schema_pins(limit: int = 100):
    """Return pinned MCP tool schema hashes."""
    return {"schema_pins": mcp_broker.list_schema_pins(limit=max(1, min(limit, 500)))}

@app.post("/edgek/mcp/servers")
async def edgek_mcp_register_server(payload: Dict[str, Any]):
    """Register or update a known MCP server."""
    try:
        return mcp_broker.register_server(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/mcp/servers")
async def edgek_mcp_servers():
    """List registered MCP servers."""
    return {"servers": mcp_broker.list_servers()}

@app.get("/edgek/mcp/audit")
async def edgek_mcp_audit(limit: int = 20):
    """Return recent MCP broker audit events."""
    return {
        "events": mcp_broker.recent_audit_events(limit=max(1, min(limit, 100)))
    }

@app.get("/edgek/mcp/executions")
async def edgek_mcp_executions(limit: int = 20):
    """Return recent MCP broker execution events."""
    return {
        "events": mcp_broker.recent_execution_events(limit=max(1, min(limit, 100)))
    }

@app.get("/edgek/mcp/approvals")
async def edgek_mcp_approvals(status: str = None, limit: int = 20):
    """Return MCP approval requests."""
    return {
        "approvals": mcp_broker.list_approvals(
            status=status,
            limit=max(1, min(limit, 100))
        )
    }

@app.get("/edgek/mcp/approvals/{request_id}")
async def edgek_mcp_approval(request_id: str):
    """Return one MCP approval request."""
    try:
        return mcp_broker.get_approval(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/edgek/mcp/approvals/{request_id}/approve")
async def edgek_mcp_approve(request_id: str, payload: Dict[str, Any] = None):
    """Approve a pending MCP request."""
    payload = payload or {}
    try:
        return mcp_broker.resolve_approval(
            request_id=request_id,
            approved=True,
            resolved_by=payload.get("resolved_by", "user"),
            reason=payload.get("reason", "")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/mcp/approvals/{request_id}/deny")
async def edgek_mcp_deny(request_id: str, payload: Dict[str, Any] = None):
    """Deny a pending MCP request."""
    payload = payload or {}
    try:
        return mcp_broker.resolve_approval(
            request_id=request_id,
            approved=False,
            resolved_by=payload.get("resolved_by", "user"),
            reason=payload.get("reason", "")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/runtime/state")
async def edgek_runtime_state():
    """Return runtime governance state."""
    return runtime_governor.state()

@app.get("/edgek/runtime/metrics")
async def edgek_runtime_metrics(limit: int = 500):
    """Return aggregate provider attempt metrics."""
    return runtime_governor.metrics(limit=max(1, min(limit, 2000)))

@app.get("/edgek/runtime/attempts")
async def edgek_runtime_attempts(provider: str = None, status: str = None, limit: int = 20):
    """Return runtime attempts, optionally filtered by provider or status."""
    return {
        "attempts": runtime_governor.recent_attempts(
            provider=provider,
            status=status,
            limit=max(1, min(limit, 100)),
        )
    }

@app.get("/edgek/runtime/attempts/{attempt_id}")
async def edgek_runtime_attempt(attempt_id: str):
    """Return one runtime attempt."""
    try:
        return runtime_governor.get_attempt(attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/edgek/runtime/integrity")
async def edgek_runtime_integrity():
    """Return runtime ledger integrity checks."""
    return runtime_governor.integrity_report()

@app.post("/edgek/runtime/sweep")
async def edgek_runtime_sweep(payload: Dict[str, Any] = None):
    """Mark stale started runtime attempts abandoned."""
    payload = payload or {}
    max_age_seconds = payload.get("max_age_seconds")
    return runtime_governor.sweep_stale_attempts(
        max_age_seconds=int(max_age_seconds) if max_age_seconds is not None else None
    )

@app.post("/edgek/runtime/circuit-breakers/{provider}/reset")
async def edgek_runtime_reset_circuit(provider: str):
    """Reset a provider circuit breaker."""
    return runtime_governor.reset_circuit(provider)

@app.get("/edgek/telemetry/http")
async def edgek_http_telemetry():
    """Return gateway request, I/O, bandwidth, and latency telemetry."""
    return _telemetry_stats()

# Middleware to count requests
@app.middleware("http")
async def count_requests(request: Request, call_next):
    global request_count
    started = time.perf_counter()
    request_count += 1
    request_bytes = int(request.headers.get("content-length") or 0)
    path = request.url.path
    logger.info(f"Request #{request_count}: {request.method} {request.url}")
    status_code = 500
    response_bytes = 0
    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        response_bytes = int(response.headers.get("content-length") or 0)
        return response
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        status_class = f"{status_code // 100}xx"
        http_telemetry["request_count"] += 1
        http_telemetry["rx_bytes"] += request_bytes
        http_telemetry["tx_bytes"] += response_bytes
        http_telemetry["status_counts"][str(status_code)] += 1
        http_telemetry["status_counts"][status_class] += 1
        http_telemetry["method_counts"][request.method] += 1
        http_telemetry["route_counts"][path] += 1
        http_telemetry["recent"].append({
            "method": request.method,
            "path": path,
            "status": status_code,
            "duration_ms": duration_ms,
            "rx_bytes": request_bytes,
            "tx_bytes": response_bytes,
            "completed_at_epoch": time.time(),
        })

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
