"""
EdgeK BEAST Gateway - Main Application Entry Point
Phase 9: Team and Enterprise Mode
"""

import uvicorn
import os
import json
import hashlib
import subprocess
import time
import tempfile
import threading
from collections import Counter, deque
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, Any, List
import logging
import httpx

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")

from app.kernel.local.local_config import load_local_env

load_local_env()

# Import adapters
from app.adapters.openai_adapter import openai_router
from app.adapters.anthropic_adapter import anthropic_router
from app.adapters.gemini_adapter import gemini_router
from app.adapters.huggingface_adapter import huggingface_router
from app.mcp.server import mcp_router
from app.proxy.server import proxy_router
from app.kernel.compute.container import container
from app.kernel.execution.orchestrator import PRECOrchestrator
from app.kernel.compute.factory import ServiceFactory
from app.kernel.governance.reason import reasoner
from app.kernel.execution.crystallize import crystallizer
from app.kernel.governance.runtime import runtime_governor
from app.kernel.capability.skill_tree import skill_tree
from app.kernel.networking.swarm import swarm_kernel
from app.kernel.compute.enterprise import enterprise_manager
from app.kernel.compute.benchmark import ComparativeBenchmark, MegaGauntlet
from app.kernel.compute.ast_compressor import ASTCompressor
from app.kernel.security.isolation_forest import IsolationForest
from app.kernel.networking.os_bypass import af_packet_capture_probe, capabilities as os_bypass_capabilities, open_ring_probe, dpdk_probe, af_xdp_probe
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.adapters.provider_economist import EconomistPolicy, ProviderEconomist
from app.kernel.networking.otel_connector import OpenTelemetryConnector
from app.kernel.deployment.plugin_marketplace import PluginMarketplace
from app.kernel.registry.beast_builtin_plugins import invoke as invoke_builtin_plugin
from app.kernel.execution.session_handshake import SessionHandshakeBuilder
from app.kernel.capability.capability_exchange import CapabilityExchange
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from app.kernel.compute.inference_interceptor import compute_interceptor, compute_ledger
from app.kernel.deployment.deployment import DeploymentManager
from app.kernel.registry.tool_integrations import RequiredIntegrationRegistry, ToolCallInterceptor
from app.kernel.local.ollama_scout import OllamaScout
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.storage.memory_stack import MemoryStack
from app.kernel.data_processing.context_packet import ContextPacketBuilder
from app.kernel.data_processing.code_cortex import CodeCortexRouter
from app.kernel.agents.mode_router import ModeRouter
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.spec_covenant import SpecCovenantCompiler
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.kernel.data_processing.workspace_graph_service import WorkspaceGraphService
from app.kernel.data_processing.workspace_registry import WorkspaceRegistry, repo_id_for_root
from app.kernel.data_processing.forge_scorecard import ForgeScorecardBuilder
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.data_processing.promotion_loop import PromotionLoop
from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.security.secret_vault import PROVIDER_ENV, SecretVault
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.kernel.capability.capability_registry import CapabilityRegistry
from app.kernel.capability.capability_plane import CapabilityPlane
from app.kernel.storage.evidence_scoring import EvidenceScorer
from app.kernel.compute.compression_pipeline import CompressionPipeline
from app.kernel.networking.interception_events import InterceptionEventFactory
from app.kernel.storage.forensic_memory import ForensicMemory
from app.kernel.data_processing.chronicle_projection import ChronicleProjectionPublisher
from app.kernel.networking.network_chronicle import NetworkChronicleConnector
from app.kernel.networking.github_pr_connector import GitHubPRConnector
from app.kernel.adapters.vector_adapters import VectorAdapterRegistry
from app.kernel.registry.provider_registry import ProviderRegistry
from app.kernel.adapters.provider_adapters import ProviderAdapterRegistry
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseDecision, CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.integration_harness import BeastHarnessRequest, BeastIntegrationHarness
from app.kernel.compute.integration_acceptance import CrystalIntegrationAcceptanceHarness
from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe
from app.kernel.compute.local_execution_gateway import LocalExecutionGateway
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.compute.kv_restore_harness import KVRestoreHarness
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.security.agent_passport import AgentPassport, AgentPassportPolicy
from app.kernel.storage.memory_hull import MemoryHull
from app.kernel.compute.proof_local_compute import (
    ProofRouteRequest,
    build_manifest_stage,
    build_verifier_stage,
    validate_manifest_stage,
    validate_verifier_stage,
)
from app.kernel.storage.prec_lifecycle import prec_lifecycle_store
from app.kernel.storage.outcome_evidence import OutcomeEvidence, default_outcome_store
from app.kernel.compute.crystal_forks import TemporalCrystalForkManager
from app.kernel.data_processing.semantic_raid import ArtifactFossilLayerStore, SemanticRaidStore
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.governance.commons_policy import CommonsPolicyLearner
from app.kernel.networking.federated_commons import FederatedCommons
from app.kernel.networking.commons_economy import ComputeReductionEconomy
from app.kernel.networking.commons_scale_economics import CommonsScaleEconomics, ScaleEconomicsAssumptions
from app.kernel.networking.commons_testnet import CommonsTestnet
from app.kernel.networking.commons_prototype import CommonsCrystalPromoter, FirstPrototypeRunner
from app.routes.cockpit import build_cockpit_router
from app.routes.commons import build_commons_router
from app.routes.compute import build_compute_router
from app.routes.ide import build_ide_router
from app.routes.policy import build_policy_router
from app.routes.sourceplan import build_sourceplan_router
from app.routes.workspace import build_workspace_router
from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller
from app.kernel.data_processing.semantic_compute_pages import SemanticComputePageStore, build_phase3_semantic_pages
from app.kernel.security.crystal_chain_witness import CrystalChainWitnessStore
from app.kernel.security.crystal_lattice_ledger import CrystalLatticeLedger
from app.kernel.data_processing.generative_crystals import GenerativeCrystalStore, run_phase5_generative_crystal_gauntlet
from app.kernel.compute.hardware_adapter_validation import HardwareAdapterValidator
from app.context.economizer import ContextEconomizer
from app.kernel.registry.adapter_comparison import AdapterComparisonGauntlet
from app.mcp.broker import MCPBroker

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
for noisy_logger in ("httpx", "httpcore", "sentence_transformers", "transformers", "huggingface_hub"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
secret_vault = SecretVault()
secret_vault.load()

# Initialize services via factory
ServiceFactory.initialize()

mcp_broker = MCPBroker(reasoner.policies, workspace_graph=crystallizer.workspace_graph)
runtime_governor.policies = reasoner.policies
swarm_kernel.policies = reasoner.policies
swarm_kernel.workspace_graph = crystallizer.workspace_graph
enterprise_manager.policies = reasoner.policies
benchmark_runner = ComparativeBenchmark(reasoner.policies, reasoner=reasoner)
mega_gauntlet = MegaGauntlet(reasoner.policies, reasoner=reasoner)
ast_compressor = ASTCompressor()
tool_laziness_learner = ToolLazinessLearner()
tool_laziness_plugin = ToolLazinessPlugin(tool_laziness_learner)
provider_economist = ProviderEconomist()
crystal_compute_store = default_outcome_store()
crystal_fork_manager = TemporalCrystalForkManager(Path(__file__).resolve().parents[1] / ".beast" / "crystal_forks.json")
semantic_raid_store = SemanticRaidStore(Path(__file__).resolve().parents[1] / ".beast" / "semantic_raid")
artifact_fossil_store = ArtifactFossilLayerStore(Path(__file__).resolve().parents[1] / ".beast" / "fossils")
kv_cache_transport = CrossEngineKVCacheTransport()
inference_engine_fabric = InferenceEngineFabric()
beast_state_root = Path(__file__).resolve().parents[1] / ".beast"
local_semantic_cache = LocalSemanticCache(beast_state_root / "local_semantic_cache.sqlite")
local_trace_ledger = LocalTraceLedger(
    beast_state_root / "local_trace_ledger.sqlite",
    beast_state_root / "local_trace_ledger.jsonl",
)
local_eval_gate = LocalEvalGate()
local_route_optimizer = LocalRouteOptimizer(beast_state_root / "local_route_optimizer.sqlite")
local_execution_gateway = LocalExecutionGateway(
    inference_engine_fabric,
    route_optimizer=local_route_optimizer,
)
memory_hull = MemoryHull(
    beast_state_root / "vault",
    seal=ResidueSeal(beast_state_root / "keys" / "residue"),
)
agent_passport_policy = AgentPassportPolicy(seal=ResidueSeal(beast_state_root / "keys" / "passport"), sign_decisions=True)
crystal_reuse_gateway = CrystalReuseGateway(
    kv_transport=kv_cache_transport,
    memory_hull=memory_hull,
    seal=ResidueSeal(beast_state_root / "keys" / "crystal_reuse"),
    local_semantic_cache=local_semantic_cache,
    trace_ledger=local_trace_ledger,
    eval_gate=local_eval_gate,
    route_optimizer=local_route_optimizer,
)
thin_integration_harness = BeastIntegrationHarness(
    passport_policy=agent_passport_policy,
    crystal_gateway=crystal_reuse_gateway,
    residue_seal=ResidueSeal(beast_state_root / "keys" / "integration_harness"),
    memory_hull=memory_hull,
    enterprise_manager=enterprise_manager,
    local_execution_gateway=local_execution_gateway,
)
commons_space_registry = CommonsSpaceRegistry()
commons_policy_learner = CommonsPolicyLearner(commons_space_registry, compute_ledger)
federated_commons = FederatedCommons(commons_space_registry)
commons_economy = ComputeReductionEconomy(commons_space_registry)
commons_scale_economics = CommonsScaleEconomics(commons_space_registry, commons_economy)
commons_testnet = CommonsTestnet()
commons_crystal_promoter = CommonsCrystalPromoter(commons_space_registry, commons_economy)
commons_prototype_runner = FirstPrototypeRunner(commons_space_registry, commons_economy, commons_crystal_promoter)
crystal_to_adapter_distiller = CrystalToAdapterDistiller()
semantic_compute_page_store = SemanticComputePageStore()
crystal_lattice_ledger = CrystalLatticeLedger()
crystal_chain_witness_store = CrystalChainWitnessStore(node_id=os.environ.get("BEAST_COMMONS_NODE_ID", "local-commons-witness"))
generative_crystal_store = GenerativeCrystalStore()
adapter_comparison_gauntlet = AdapterComparisonGauntlet()
commons_economics_receipt_path = Path(__file__).resolve().parents[1] / "benchmarks/results/commons_scale_economics_ladder_latest.json"
commons_marketplace_cache: Dict[str, Any] = {"receipt_mtime_ns": None, "report": None, "catalog": None}
commons_registry_web_cache: Dict[str, Any] = {"at": 0.0, "local": None, "public": None}
commons_registry_web_cache_lock = threading.Lock()


def cached_commons_registries() -> Dict[str, Any]:
    if time.monotonic() - float(commons_registry_web_cache.get("at") or 0) > 300 or commons_registry_web_cache.get("local") is None:
        with commons_registry_web_cache_lock:
            if time.monotonic() - float(commons_registry_web_cache.get("at") or 0) > 300 or commons_registry_web_cache.get("local") is None:
                commons_registry_web_cache.update({
                    "at": time.monotonic(),
                    "local": commons_space_registry.list_spaces(),
                    "public": commons_space_registry.public_registry(),
                })
    return commons_registry_web_cache


def load_commons_economics_receipt() -> Dict[str, Any]:
    """Load the latest receipt once per file version for cheap web polling."""
    try:
        mtime_ns = commons_economics_receipt_path.stat().st_mtime_ns
    except OSError:
        mtime_ns = None
    if commons_marketplace_cache.get("receipt_mtime_ns") == mtime_ns and commons_marketplace_cache.get("report"):
        return commons_marketplace_cache["report"]
    if commons_economics_receipt_path.is_file():
        try:
            receipt = json.loads(commons_economics_receipt_path.read_text(encoding="utf-8"))
            if receipt.get("beast_object_type") == "commons_scale_economics_report":
                commons_marketplace_cache.update({"receipt_mtime_ns": mtime_ns, "report": receipt, "catalog": None})
                return receipt
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    receipt = commons_scale_economics.report(ScaleEconomicsAssumptions(
        target_spaces=10,
        matches_per_space=3,
        cloud_call_cost_usd=0.02,
        token_cost_per_1m_usd=5.0,
        setup_cost_usd=1.0,
        marketplace_take_rate=0.1,
    ))
    commons_marketplace_cache.update({"receipt_mtime_ns": mtime_ns, "report": receipt, "catalog": None})
    return receipt
otel_connector = OpenTelemetryConnector()
plugin_marketplace = PluginMarketplace()
plugin_marketplace.install_builtins()
session_handshake_builder = SessionHandshakeBuilder()
capability_exchange = CapabilityExchange()
meta_tool_commons = MetaToolCommons(exchange=capability_exchange, skill_registry=skill_tree.skill_registry)
deployment_manager = DeploymentManager(reasoner.policies)
integration_registry = RequiredIntegrationRegistry(reasoner.policies)
tool_call_interceptor = ToolCallInterceptor(crystallizer.workspace_graph, reasoner.policies)
ollama_scout = OllamaScout(crystallizer.workspace_graph, mcp_broker, reasoner.policies)
task_envelope_builder = TaskEnvelopeBuilder(reasoner.policies, runtime_governor=runtime_governor)
code_cortex_router = CodeCortexRouter()
context_packet_builder = ContextPacketBuilder(
    workspace_graph=crystallizer.workspace_graph,
    code_cortex=code_cortex_router,
)
workspace_graph_service = WorkspaceGraphService(
    crystallizer.workspace_graph,
    default_root=Path(__file__).resolve().parents[1],
)
mode_router = ModeRouter()
workspace_registry = WorkspaceRegistry.for_anchor_root(Path(__file__).resolve().parents[1])
forge_scorecard_builder = ForgeScorecardBuilder()
conductor_workflow_builder = ConductorWorkflowBuilder(swarm_kernel=swarm_kernel)
canon_registry = CanonRegistry()
beast_cli_executor = BeastCLIExecutor(
    ollama_scout=ollama_scout,
    mcp_broker=mcp_broker,
    canon_registry=canon_registry,
    runtime_governor=runtime_governor,
    tool_laziness_learner=tool_laziness_learner,
    tool_laziness_plugin=tool_laziness_plugin,
    provider_economist=provider_economist,
    handshake_builder=session_handshake_builder,
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
capability_plane = CapabilityPlane(
    workspace_root=str(Path(__file__).resolve().parents[1]),
    registry=capability_registry,
    skill_tree=skill_tree,
    plugin_marketplace=plugin_marketplace,
    exchange=capability_exchange,
    commons=meta_tool_commons,
)
evidence_scorer = EvidenceScorer(reasoner.policies)
compression_pipeline = CompressionPipeline(reasoner.policies)
interception_event_factory = InterceptionEventFactory(reasoner.policies)
forensic_memory = ForensicMemory()
chronicle_publisher = ChronicleProjectionPublisher()
network_chronicle_connector = NetworkChronicleConnector()
github_pr_connector = GitHubPRConnector(task_envelope_builder=task_envelope_builder)
vector_adapter_registry = VectorAdapterRegistry()
provider_registry = ProviderRegistry(reasoner.policies)
provider_adapter_registry = ProviderAdapterRegistry(reasoner.policies)
hardware_adapter_validator = HardwareAdapterValidator(fabric=inference_engine_fabric)
nim_live_probe = NvidiaNIMLiveProbe(registry=provider_registry, secret_vault=secret_vault)
prec_lifecycle = prec_lifecycle_store


def _main_harness_provider_executor(request: CrystalReuseRequest) -> Dict[str, Any]:
    """Provider executor used by the universal harness path.

    It is intentionally in-process and deterministic so the harness cannot
    deadlock the local gateway by calling its own proxy route.
    """
    try:
        plan = provider_adapter_registry.adapter_for(str(request.provider or "litellm")).plan_chat(request.model).to_dict()
    except Exception:
        plan = {"provider_id": request.provider or "local", "route_provider": request.provider or "local", "model": request.model}
    response = (
        "BEAST integration harness executed the governed provider boundary.\n\n"
        f"Provider: {plan.get('provider_id') or request.provider or 'local'}\n"
        f"Route: {plan.get('route_provider') or plan.get('backend') or 'local'}\n"
        f"Model: {plan.get('model') or request.model}\n"
        f"Prompt: {request.prompt[:600]}"
    )
    return {
        "response": response,
        "provider": plan.get("provider_id") or request.provider or "local",
        "route_provider": plan.get("route_provider") or plan.get("backend") or request.provider or "local",
        "model": plan.get("model") or request.model,
        "cost_usd": 0.0,
        "total_tokens": max(1, len(request.prompt.split()) + len(response.split())),
        "status": "completed",
        "execution_boundary": "beast_integration_harness_in_process_provider_executor",
    }


thin_integration_harness.provider_executor = _main_harness_provider_executor
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
app.include_router(build_sourceplan_router(Path(__file__).resolve().parents[1]))
app.include_router(build_compute_router(
    compute_ledger=compute_ledger,
    crystal_compute_store=crystal_compute_store,
    crystal_fork_manager=crystal_fork_manager,
    semantic_raid_store=semantic_raid_store,
    artifact_fossil_store=artifact_fossil_store,
    commons_crystal_promoter=commons_crystal_promoter,
))
app.include_router(build_workspace_router(
    Path(__file__).resolve().parents[1],
    workspace_graph_service=workspace_graph_service,
    workspace_graph=crystallizer.workspace_graph,
    workspace_registry=workspace_registry,
    code_cortex_router=code_cortex_router,
    trace_path=crystallizer.trace_path,
))
app.include_router(build_commons_router(
    meta_tool_commons=meta_tool_commons,
    swarm_kernel=swarm_kernel,
    kv_cache_transport=kv_cache_transport,
    commons_space_registry=commons_space_registry,
    commons_economy=commons_economy,
    commons_policy_learner=commons_policy_learner,
    federated_commons=federated_commons,
))
app.include_router(build_cockpit_router(Path(__file__).resolve().parents[1]))
app.include_router(build_policy_router(Path(__file__).resolve().parents[1], mode_router))
app.include_router(build_ide_router(Path(__file__).resolve().parents[1], code_cortex_router=code_cortex_router))
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
cli_assets_dir = Path(__file__).parent / "cli" / "assets"
if cli_assets_dir.exists():
    app.mount("/beast-assets", StaticFiles(directory=str(cli_assets_dir)), name="beast-assets")
commons_media_files = {
    "beast-logo.png": Path(__file__).resolve().parents[1] / "BEAST_mascot-removebg-preview.png",
    "inference-economy.mp4": Path(__file__).resolve().parents[1] / "BEAST__Inference_Economy.mp4",
    "inference-inversion.pptx": Path(__file__).resolve().parents[1] / "BEAST_INFERENCE_INVERSION.pptx",
}

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

def _commons_site_file() -> Path:
    site_path = frontend_dir / "commons.html"
    if site_path.exists():
        return site_path
    return frontend_dir / "index.html"


@app.get("/")
async def beast_commons_home():
    """Serve the BEAST Commons web UI on the default port-8000 root."""
    site_path = _commons_site_file()
    if not site_path.exists():
        raise HTTPException(status_code=404, detail="BEAST Commons frontend is not installed")
    return HTMLResponse(site_path.read_text(encoding="utf-8"))


@app.get("/edgek/root-info")
async def root_info():
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
            "edgek_workspace_service": "/edgek/workspace/service",
            "edgek_workspace_graph_stats": "/edgek/workspace/graph/stats",
            "edgek_workspace_index": "/edgek/workspace/index",
            "edgek_workspace_poll": "/edgek/workspace/poll",
            "edgek_workspace_files": "/edgek/workspace/files",
            "edgek_workspace_file": "/edgek/workspace/file",
            "edgek_workspace_symbols": "/edgek/workspace/symbols",
            "edgek_workspace_registry": "/edgek/workspace/registry",
            "edgek_workspace_register": "/edgek/workspace/register",
            "edgek_workspace_context_pack": "/edgek/workspace/context-pack",
            "edgek_workspace_validate_scope": "/edgek/workspace/validate-sourceplan-scope",
            "edgek_workspace_contract_mismatch": "/edgek/workspace/contract-mismatch",
            "edgek_workspace_rebuild": "/edgek/workspace/rebuild",
            "edgek_workspace_export": "/edgek/workspace/export",
            "edgek_workspace_integrity": "/edgek/workspace/integrity",
            "edgek_workspace_search": "/edgek/workspace/search",
            "edgek_workspace_file_status": "/edgek/workspace/file-status",
            "edgek_workspace_changed_since": "/edgek/workspace/changed-since",
            "edgek_workspace_context": "/edgek/workspace/context",
            "edgek_ide_snapshot": "/edgek/ide/snapshot",
            "edgek_ide_events": "/edgek/ide/events",
            "edgek_ide_mission_timeline": "/edgek/ide/mission-timeline",
            "edgek_ide_related_context": "/edgek/ide/related-context",
            "edgek_ide_code_intel": "/edgek/ide/code-intel",
            "edgek_ide_tooling_snapshot": "/edgek/ide/tooling-snapshot",
            "edgek_ide_terminal_stream": "/edgek/ide/terminal/stream",
            "edgek_workspace_context_consumption": "/edgek/workspace/context-consumption",
            "edgek_workspace_stale_context": "/edgek/workspace/stale-context",
            "edgek_workspace_index_benchmark": "/edgek/workspace/index-benchmark",
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
    """Serve the BEAST Commons web UI."""
    index_path = _commons_site_file()
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="BEAST Commons frontend is not installed")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/commons-media/{asset_name}")
@app.head("/commons-media/{asset_name}")
async def beast_commons_media(asset_name: str):
    """Serve approved BEAST Commons media assets without exposing the repo tree."""
    path = commons_media_files.get(asset_name)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="BEAST Commons media asset not found")
    return FileResponse(str(path))


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

@app.get("/edgek/memory-security")
async def edgek_memory_security_state(verify: bool = False):
    """Return Memory Hull, Residue Seal, and Agent Passport production-layer state."""
    scout = AgentPassport.local("scout/repo-reader")
    governor = AgentPassport.local("runtime-governor")
    proxy = AgentPassport.local("proxy/gateway")
    decisions = {
        "scout_memory_append": agent_passport_policy.evaluate(
            caller=scout,
            target="spiffe://beast.local/memory/vault",
            action="append",
        ),
        "governor_cloud_call_approved": agent_passport_policy.evaluate(
            caller=governor,
            target="spiffe://beast.local/provider/cloud",
            action="call",
            facts={"quality_cascade": {"approved": True}},
        ),
        "proxy_cloud_call_unapproved": agent_passport_policy.evaluate(
            caller=proxy,
            target="spiffe://beast.local/provider/cloud",
            action="call",
        ),
    }
    return {
        "beast_object_type": "beast_memory_security_state",
        "version": "1.0",
        "memory_hull": memory_hull.inventory(verify=verify),
        "residue_seal": memory_hull.seal.health(),
        "agent_passport": {
            "policy_lint": agent_passport_policy.lint(),
            "sample_passports": [scout.to_dict(), governor.to_dict(), proxy.to_dict()],
            "sample_decisions": decisions,
        },
        "layers": [
            {"layer": "agent_passport", "status": "active", "purpose": "workload identity and policy decisions"},
            {"layer": "memory_hull", "status": "active", "purpose": "editable sealed operational residue"},
            {"layer": "residue_seal", "status": "active", "purpose": "purpose-specific Ed25519 artifact signing"},
        ],
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

@app.post("/edgek/agent-passport/workload-certificate")
async def edgek_agent_passport_workload_certificate(payload: Dict[str, Any] = None):
    """Issue a passport bound to supplied workload certificate material."""
    payload = payload or {}
    component = str(payload.get("component") or "proxy/gateway")
    cert_pem = str(payload.get("cert_pem") or "")
    if not cert_pem:
        raise HTTPException(status_code=400, detail="cert_pem is required")
    try:
        passport = AgentPassport.from_workload_certificate(
            component,
            cert_pem,
            claims=payload.get("claims") if isinstance(payload.get("claims"), dict) else {},
        )
        return passport.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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

@app.get("/edgek/providers/secrets/route/{provider_id}")
async def edgek_provider_secret_route_status(provider_id: str):
    """Return selected-route secret readiness instead of global cloud readiness."""
    normalized = str(provider_id or "litellm").lower().replace("-", "_")
    records = {record.provider_id: record for record in provider_registry.records(include_disabled=True)}
    record = records.get(normalized)
    if not record:
        raise HTTPException(status_code=404, detail="provider not found")
    local_backend = record.backend in {"ollama"} or record.risk_level == "local" or record.managed_by == "beast_managed_backend_lane"
    present = {env: bool(os.environ.get(env)) for env in record.env}
    required = [] if local_backend else list(record.env)
    missing = [env for env in required if not present.get(env)]
    status = "ready" if not missing else "missing_secrets"
    return {
        "beast_object_type": "provider_selected_route_secret_readiness",
        "version": "1.0",
        "provider_id": record.provider_id,
        "backend": record.backend,
        "managed_by": record.managed_by,
        "local_or_managed_route": local_backend,
        "required_env": required,
        "present_env": present,
        "missing_env": missing,
        "status": status,
        "claim_boundary": "Secret readiness is evaluated for the selected route, not every possible cloud provider.",
    }

@app.post("/edgek/providers/nvidia-nim/live-smoke")
async def edgek_nvidia_nim_live_smoke(payload: Dict[str, Any] = None):
    """Run one explicit, redacted live NVIDIA NIM smoke completion."""
    payload = payload or {}
    if not bool(payload.get("confirm_live")):
        raise HTTPException(status_code=400, detail="confirm_live=true is required for a live NIM call")
    prompt = str(payload.get("prompt") or "Return exactly: BEAST_NIM_LIVE_OK")
    receipt = nim_live_probe.run(
        prompt=prompt,
        requested_model=str(payload.get("model") or ""),
        timeout_seconds=float(payload.get("timeout_seconds") or 30.0),
        max_tokens=int(payload.get("max_tokens") or 32),
        discover_models=bool(payload.get("discover_models", True)),
    )
    if bool(payload.get("crystallize")) and receipt.get("status") == "ok":
        response_preview = str(receipt.get("response_preview") or "")
        if response_preview.strip():
            usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
            evidence = {
                "verification": "live_nim_smoke_passed",
                "live_nim_probe_receipt_hash": receipt.get("receipt_hash"),
                "finish_reason": receipt.get("finish_reason"),
                "latency_ms": receipt.get("latency_ms") or 0,
                "usage": usage,
            }
            receipt["crystal_record"] = crystal_reuse_gateway.record_execution_response(
                CrystalReuseRequest(
                    prompt=prompt,
                    model=str(receipt.get("model") or payload.get("model") or "nvidia_nim"),
                    parameters={"max_tokens": int(payload.get("max_tokens") or 32)},
                    task_class=str(payload.get("task_class") or "nim_live_smoke"),
                    repo_fingerprint=str(payload.get("repo_fingerprint") or "nvidia_nim_live_smoke"),
                    provider="nvidia_nim",
                    metadata={"correlation_id": str(receipt.get("receipt_hash") or "")},
                ),
                response_preview,
                route="nvidia_nim",
                engine=str(receipt.get("model") or payload.get("model") or "nvidia_nim"),
                verified=True,
                avoided_tokens_estimate=int(usage.get("total_tokens") or 0),
                evidence=evidence,
                write_memory=bool(payload.get("write_memory", False)),
            )
        else:
            receipt["crystal_record"] = {
                "status": "skipped",
                "reason": "empty_response_preview_not_crystallized",
            }
    return receipt

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

@app.post("/edgek/session/handshake")
async def edgek_session_handshake(payload: Dict[str, Any] = None):
    """Build the compact BEAST agent-awareness and latency contract."""
    payload = payload or {}
    return session_handshake_builder.build(
        str(payload.get("objective") or payload.get("task") or payload.get("goal") or "Use BEAST efficiently"),
        mode=str(payload.get("mode") or "openclaw"),
        workspace_root=str(payload.get("workspace_root") or Path(__file__).resolve().parents[1]),
        tools=payload.get("candidate_tools") or [],
        preflight_budget_ms=int(payload.get("preflight_budget_ms", 500)),
        scout_budget_ms=int(payload.get("scout_budget_ms", 300)),
        session_id=payload.get("session_id"),
    )

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
        candidate_tools=payload.get("candidate_tools") or [],
        required_tools=payload.get("required_tools") or [],
        provider_candidates=payload.get("provider_candidates") or [],
        requested_role=str(payload.get("requested_role") or "primary_patch_provider"),
        preflight_budget_ms=int(payload.get("preflight_budget_ms", 500)),
        scout_budget_ms=int(payload.get("scout_budget_ms", 300)),
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
        candidate_tools=payload.get("candidate_tools") or [],
        required_tools=payload.get("required_tools") or [],
        provider_candidates=payload.get("provider_candidates") or [],
        requested_role=str(payload.get("requested_role") or "primary_patch_provider"),
        preflight_budget_ms=int(payload.get("preflight_budget_ms", 500)),
        scout_budget_ms=int(payload.get("scout_budget_ms", 300)),
    )
    lifecycle = prec_lifecycle.record_artifact_lifecycle(
        kind="cli_execute",
        payload={**payload, "objective": objective},
        artifacts={**artifacts, "insight_packet": payload.get("insight_packet") or (payload.get("handoff_precheck") or {}).get("insight_packet")},
    )
    commons_ingest = meta_tool_commons.ingest_cli_execution(result)
    return {**result, "artifacts": artifacts, "prec_lifecycle": _prec_summary(lifecycle), "commons_ingest": commons_ingest}

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
    payload = task_envelope_builder.list_chronicles(
        task_class=task_class,
        provider=provider,
        category=category,
        limit=max(1, min(limit, 100)),
    )
    chronicles = payload.get("chronicles") if isinstance(payload.get("chronicles"), list) else []
    if chronicles:
        residue_records = memory_hull.list_residue(limit=500)
        by_task = {
            str(record.get("task") or "").strip().lower(): record
            for record in residue_records
            if str(record.get("task") or "").strip()
        }
        by_residue = {
            str(record.get("residue_id") or ""): record
            for record in residue_records
            if record.get("residue_id")
        }
        enriched = []
        for row in chronicles:
            item = dict(row) if isinstance(row, dict) else {}
            candidate = None
            for key in ("memory_hull_residue_id", "residue_id"):
                if item.get(key):
                    candidate = by_residue.get(str(item.get(key)))
                    if candidate:
                        break
            if candidate is None:
                lookup = str(item.get("task") or item.get("summary") or item.get("task_id") or "").strip().lower()
                candidate = by_task.get(lookup)
            if candidate and (item.get("memory_candidate") or item.get("memory_hull_residue_id") or item.get("residue_id")):
                sidecar_path = candidate.get("sidecar_path") or candidate.get("sidecar")
                verification = memory_hull.verify_sidecar(Path(sidecar_path)) if sidecar_path else {"verified": False, "reason": "missing_sidecar_path"}
                item["memory_hull_residue_id"] = candidate.get("residue_id")
                item["memory_hull_sidecar_path"] = sidecar_path
                item["memory_hull_verified"] = bool(verification.get("verified"))
                item["memory_hull_verification_reason"] = verification.get("reason")
            enriched.append(item)
        payload["chronicles"] = enriched
    return payload

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

@app.post("/edgek/connectors/network-chronicle/attach")
async def edgek_network_chronicle_attach(payload: Dict[str, Any] = None):
    """Attach metadata-only packet evidence to a provider diagnostic Chronicle."""
    payload = payload or {}
    diagnostic = payload.get("diagnostic")
    if diagnostic is None:
        provider = str(payload.get("provider") or "unknown")
        diagnostic = task_envelope_builder.diagnose_provider(
            {"provider": provider, "user_request": payload.get("user_request") or f"Diagnose {provider} route"},
            workspace_root=str(Path(__file__).resolve().parents[1]),
            write_chronicle=False,
        )
    probe = payload.get("probe")
    if probe is None and bool(payload.get("run_probe", False)):
        probe = af_packet_capture_probe(
            interface=str(payload.get("interface") or "lo"),
            timeout_ms=int(payload.get("timeout_ms", 1000)),
            max_packets=int(payload.get("max_packets", 64)),
        )
    if not isinstance(probe, dict):
        raise HTTPException(status_code=400, detail="probe is required unless run_probe=true")
    return network_chronicle_connector.attach_provider_diagnostic(
        diagnostic,
        probe,
        source=str(payload.get("source") or "af_packet_capture_probe"),
        chronicle_builder=task_envelope_builder,
        persist=bool(payload.get("persist", False)),
    )

@app.post("/edgek/connectors/github/pr/ingest")
async def edgek_github_pr_ingest(payload: Dict[str, Any] = None):
    """Convert a GitHub PR diff, failed checks, and comments into a task envelope."""
    payload = payload or {}
    try:
        return github_pr_connector.ingest(
            str(payload.get("repo") or payload.get("repository") or ""),
            int(payload.get("pr_number") or payload.get("number") or 0),
            max_files=max(1, min(int(payload.get("max_files", 20)), 50)),
            max_comments=max(1, min(int(payload.get("max_comments", 30)), 100)),
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/connectors/github/pr/publish-chronicle")
async def edgek_github_pr_publish_chronicle(payload: Dict[str, Any] = None):
    """Publish a bounded Chronicle summary as a governed PR comment."""
    payload = payload or {}
    chronicle = payload.get("chronicle")
    if chronicle is None and payload.get("task_id"):
        try:
            chronicle = task_envelope_builder.get_chronicle(str(payload["task_id"]))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    if not isinstance(chronicle, dict):
        raise HTTPException(status_code=400, detail="chronicle or task_id is required")
    try:
        return github_pr_connector.publish_chronicle(
            str(payload.get("repo") or payload.get("repository") or ""),
            int(payload.get("pr_number") or payload.get("number") or 0),
            chronicle,
            approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)),
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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

@app.get("/edgek/capability-plane/summary")
async def edgek_capability_plane_summary(limit: int = 100):
    """Return the unified read-only capability plane across BEAST capability surfaces."""
    return capability_plane.summary(limit=max(1, min(int(limit), 500)))

@app.post("/edgek/capability-plane/query")
async def edgek_capability_plane_query(payload: Dict[str, Any] = None):
    """Query the unified read-only capability plane."""
    payload = payload or {}
    return capability_plane.query(
        text=str(payload.get("text") or ""),
        kind=str(payload.get("kind") or ""),
        family=str(payload.get("family") or ""),
        source=str(payload.get("source") or ""),
        risk=str(payload.get("risk") or ""),
        local=payload.get("local") if isinstance(payload.get("local"), bool) else None,
        reusable=payload.get("reusable") if isinstance(payload.get("reusable"), bool) else None,
        verified=payload.get("verified") if isinstance(payload.get("verified"), bool) else None,
        limit=max(1, min(int(payload.get("limit") or 50), 500)),
    )

@app.get("/edgek/capabilities/discovery-sources")
async def edgek_capability_discovery_sources(include_inventory: bool = True, include_open_source_mcp: bool = True):
    """Export local and generic MCP capabilities as Commons discovery sources."""
    return capability_registry.discovery_sources(
        include_inventory=include_inventory,
        include_open_source_mcp=include_open_source_mcp,
    )

@app.post("/edgek/capabilities/ingest-commons")
async def edgek_capability_ingest_commons(payload: Dict[str, Any] = None):
    """Stage registry and generic MCP capability hypotheses into Meta Tool Commons."""
    payload = payload or {}
    sources = capability_registry.discovery_sources(
        include_inventory=bool(payload.get("include_inventory", True)),
        include_open_source_mcp=bool(payload.get("include_open_source_mcp", True)),
    )
    result = meta_tool_commons.ingest_discovery_sources({
        "sources": sources["sources"],
        "stage_candidates": bool(payload.get("stage_candidates", True)),
    })
    return {
        **result,
        "source": "capability_registry_discovery_bridge",
        "capability_sources": {
            "source_count": sources["source_count"],
            "item_count": sum(len(source.get("items") or []) for source in sources["sources"]),
        },
    }

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

@app.post("/edgek/tool-laziness/recommend-tools")
async def edgek_tool_laziness_recommend_tools(payload: Dict[str, Any] = None):
    """Recommend which candidate tools should not be called for this scenario."""
    payload = payload or {}
    return tool_laziness_plugin.recommend_tools(
        payload.get("candidate_tools") or [],
        str(payload.get("scenario") or "general"),
        required_tools=payload.get("required_tools") or [],
        min_samples=max(1, int(payload.get("min_samples", 3))),
    )

@app.post("/edgek/provider-economist/select")
async def edgek_provider_economist_select(payload: Dict[str, Any] = None):
    """Choose the best eligible route for a role, quality, cost, latency, and auth envelope."""
    payload = payload or {}
    return provider_economist.select(
        payload.get("candidates") or [],
        EconomistPolicy(
            requested_role=str(payload.get("requested_role") or "primary_patch_provider"),
            task_class=str(payload.get("task_class") or "general"),
            max_latency_ms=payload.get("max_latency_ms"),
            max_usd_per_fix=payload.get("max_usd_per_fix"),
            min_auth_confidence=float(payload.get("min_auth_confidence", 0.6)),
            require_cost_observation=bool(payload.get("require_cost_observation", False)),
            prefer_hidden_clean=bool(payload.get("prefer_hidden_clean", True)),
            friction_mode=str(payload.get("friction_mode") or "shadow"),
        ),
        negative_capabilities=crystal_compute_store.list_records(),
        friction_profiles=crystal_compute_store.friction_profiles(),
    )

@app.get("/edgek/connectors/otel")
async def edgek_otel_connector_state():
    """Return OTLP/HTTP connector configuration and approval state."""
    return otel_connector.state()

@app.post("/edgek/connectors/otel/export")
async def edgek_otel_export(payload: Dict[str, Any] = None):
    """Compile and optionally export governed BEAST evidence as OTLP trace spans."""
    payload = payload or {}
    otlp_payload = payload.get("otlp_payload")
    if not isinstance(otlp_payload, dict):
        otlp_payload = otel_connector.compile(
            chronicles=payload.get("chronicles") or [],
            route_cards=payload.get("route_cards") or [],
            packet_evidence=payload.get("packet_evidence") or [],
            provider_fitness=payload.get("provider_fitness") or [],
        )
    try:
        return otel_connector.export(
            otlp_payload,
            endpoint=payload.get("endpoint"),
            headers=payload.get("headers") if isinstance(payload.get("headers"), dict) else None,
            approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)),
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

@app.post("/edgek/plugins/manifest/prepare")
async def edgek_plugin_manifest_prepare(payload: Dict[str, Any] = None):
    """Canonicalize a BEAST plugin manifest and pin each tool schema hash."""
    payload = payload or {}
    raw_manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
    manifest = plugin_marketplace.prepare(raw_manifest)
    return {"manifest": manifest, "validation": plugin_marketplace.validate(manifest)}

@app.post("/edgek/plugins/manifest/validate")
async def edgek_plugin_manifest_validate(payload: Dict[str, Any] = None):
    """Validate risk, permissions, budgets, approvals, and tool schema pins."""
    payload = payload or {}
    raw_manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
    return plugin_marketplace.validate(raw_manifest)

@app.post("/edgek/plugins/install")
async def edgek_plugin_install(payload: Dict[str, Any] = None):
    """Dry-run or install an approved, schema-pinned plugin manifest."""
    payload = payload or {}
    return plugin_marketplace.install(
        payload.get("manifest") or {},
        approved=bool(payload.get("approved", False)),
        dry_run=bool(payload.get("dry_run", True)),
    )

@app.get("/edgek/plugins")
async def edgek_plugins_installed():
    """List locally installed BEAST plugin manifests."""
    return plugin_marketplace.list_installed()


@app.post("/edgek/plugins/{plugin_id}/invoke/{tool_name}")
async def edgek_plugin_invoke(plugin_id: str, tool_name: str, payload: Dict[str, Any] = None):
    payload = payload or {}
    installed={item.get("id") for item in plugin_marketplace.list_installed().get("plugins") or []}
    if plugin_id not in installed: raise HTTPException(status_code=404,detail="plugin is not installed")
    if payload.get("approved") is not True: raise HTTPException(status_code=403,detail="explicit first-run approval required")
    try:
        return invoke_builtin_plugin(plugin_id,tool_name,payload,{"registry":commons_space_registry,"economy":commons_economy,"scale":commons_scale_economics,"testnet":commons_testnet})
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/edgek/capability-exchange")
async def edgek_capability_exchange_state():
    """Return opt-in and privacy state for the BEAST Capability Exchange."""
    return capability_exchange.state()

@app.post("/edgek/capability-exchange/prepare")
async def edgek_capability_exchange_prepare(payload: Dict[str, Any] = None):
    """Prepare an allowlisted tool/skill outcome envelope without publishing it."""
    payload = payload or {}
    try:
        return capability_exchange.prepare(payload.get("capability") or {}, payload.get("outcome") or {})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/capability-exchange/rank")
async def edgek_capability_exchange_rank(payload: Dict[str, Any] = None):
    """Build contextual rankings by task class and role from exchange evidence."""
    payload = payload or {}
    return capability_exchange.rank(
        payload.get("evidence") or [],
        task_class=payload.get("task_class"),
        role=payload.get("role"),
    )

@app.post("/edgek/capability-exchange/submit")
async def edgek_capability_exchange_submit(payload: Dict[str, Any] = None):
    """Submit evidence only when exchange opt-in and explicit approval are active."""
    payload = payload or {}
    try:
        return capability_exchange.contribute(
            payload.get("evidence") or {},
            approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)),
            persist_local=bool(payload.get("persist_local", True)),
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/meta-tool-commons")
async def edgek_meta_tool_commons_state():
    """Return local Commons evidence, candidate, and adoption state."""
    return meta_tool_commons.state()

@app.get("/edgek/meta-tool-commons/evidence-plane")
async def edgek_meta_tool_commons_evidence_plane():
    """Return aggregate local reuse evidence across Swarm, CLI, Ollama, and KV."""
    return meta_tool_commons.evidence_plane()

@app.post("/edgek/meta-tool-commons/ingest")
async def edgek_meta_tool_commons_ingest(payload: Dict[str, Any] = None):
    """Ingest privacy-safe, hash-valid capability evidence into local priors."""
    payload = payload or {}
    evidence = payload.get("evidence") or []
    return meta_tool_commons.ingest(evidence if isinstance(evidence, list) else [evidence])

@app.get("/edgek/meta-tool-commons/swarm-ingest")
@app.post("/edgek/meta-tool-commons/swarm-ingest")
async def edgek_meta_tool_commons_swarm_ingest(payload: Dict[str, Any] = None):
    """Crystallize recent local swarm role traces into Commons evidence."""
    payload = payload or {}
    limit = max(1, min(int(payload.get("limit", 25)), 100))
    status = payload.get("status")
    runs = swarm_kernel.recent_runs(limit=limit, status=str(status) if status else None)
    return meta_tool_commons.ingest_swarm_runs(runs)

@app.get("/edgek/meta-tool-commons/swarm-candidates")
@app.post("/edgek/meta-tool-commons/swarm-candidates")
async def edgek_meta_tool_commons_swarm_candidates(payload: Dict[str, Any] = None):
    """Stage approval-gated skill recipes from repeated Commons Swarm priors."""
    payload = payload or {}
    return meta_tool_commons.propose_swarm_candidates(
        task_class=payload.get("task_class"),
        role=payload.get("role"),
        min_samples=max(1, min(int(payload.get("min_samples", 2)), 25)),
        limit=max(1, min(int(payload.get("limit", 10)), 100)),
    )

@app.post("/edgek/meta-tool-commons/ollama-calibration")
async def edgek_meta_tool_commons_ollama_calibration(payload: Dict[str, Any] = None):
    """Record Ollama scout confidence against a verifier outcome."""
    payload = payload or {}
    return meta_tool_commons.ingest_ollama_calibration(
        scout=payload.get("scout") or {},
        verifier=payload.get("verifier") or {},
    )

@app.get("/edgek/meta-tool-commons/kv-cache-ingest")
@app.post("/edgek/meta-tool-commons/kv-cache-ingest")
async def edgek_meta_tool_commons_kv_cache_ingest(payload: Dict[str, Any] = None):
    """Record KV/cache transport reuse in Commons without prompt/source payloads."""
    payload = payload or {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else kv_cache_transport.get_stats()
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return meta_tool_commons.ingest_kv_cache_evidence(stats=stats, result=result)

@app.post("/edgek/meta-tool-commons/discovery-ingest")
async def edgek_meta_tool_commons_discovery_ingest(payload: Dict[str, Any] = None):
    """Stage discovered MCP/plugin/retrieval/skill metadata as guarded hypotheses."""
    try:
        return meta_tool_commons.ingest_discovery_sources(payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/edgek/meta-tool-commons/rank")
async def edgek_meta_tool_commons_rank(payload: Dict[str, Any] = None):
    """Rank tools or skills in context without creating a universal leaderboard."""
    payload = payload or {}
    return meta_tool_commons.rank(
        task_class=payload.get("task_class"), role=payload.get("role"),
        kind=payload.get("kind"), limit=int(payload.get("limit", 25)),
    )

@app.post("/edgek/meta-tool-commons/candidates")
async def edgek_meta_tool_commons_propose(payload: Dict[str, Any] = None):
    """Stage a schema-pinned local or shared promotion candidate."""
    payload = payload or {}
    try:
        return meta_tool_commons.propose(payload.get("candidate") or {}, source=str(payload.get("source") or "local"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/meta-tool-commons/candidates")
async def edgek_meta_tool_commons_candidates(status: str = None, source: str = None, limit: int = 25):
    """List local Commons candidates staged for explicit approval."""
    return meta_tool_commons.candidates(
        status=status,
        source=source,
        limit=max(1, min(limit, 100)),
    )

@app.post("/edgek/meta-tool-commons/adopt")
async def edgek_meta_tool_commons_adopt(payload: Dict[str, Any] = None):
    """Adopt a candidate only after explicit local approval."""
    payload = payload or {}
    try:
        return meta_tool_commons.adopt(
            str(payload.get("candidate_id") or ""), approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)), approved_by=str(payload.get("approved_by") or "user"),
            reason=str(payload.get("reason") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/meta-tool-commons/snapshot")
async def edgek_meta_tool_commons_snapshot(task_class: str = None, role: str = None):
    """Export an integrity-hashed advisory ranking snapshot."""
    return meta_tool_commons.snapshot(task_class=task_class, role=role)

@app.get("/edgek/commons-spaces")
def edgek_commons_spaces():
    """List validated local Compute Spaces and aggregate reduction evidence."""
    return cached_commons_registries()["local"]


@app.get("/edgek/commons-spaces/{space_id}")
async def edgek_commons_space_detail(space_id: str):
    """Inspect one local Space, its receipt, and local adoption history."""
    try:
        return commons_space_registry.get(space_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/edgek/commons-spaces/{space_id}/bundle")
async def edgek_commons_space_bundle(space_id: str):
    """Export one Space as a content-addressed bundle for remote import."""
    try:
        exported = commons_space_registry.export_bundle(space_id)
        return FileResponse(
            exported["path"],
            media_type="application/zip",
            filename=f"{space_id}.beast-space.zip",
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/public-commons-registry")
def edgek_public_commons_registry():
    """Return the cloud-safe public Commons Registry projection."""
    return cached_commons_registries()["public"]


@app.get("/edgek/public-commons-registry/{space_id}")
async def edgek_public_commons_space_card(space_id: str):
    """Return one public-safe Space card; no artifact payloads are exposed."""
    try:
        return commons_space_registry.public_space_card(space_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/edgek/commons-scale/readiness")
def edgek_commons_scale_readiness():
    """Report whether Commons evidence is ready to scale beyond one-off demos."""
    return commons_space_registry.scale_readiness()


@app.get("/edgek/commons-scale/economics")
async def edgek_commons_scale_economics():
    """Return live proof density, tiered pricing scenarios, and market gates."""
    return load_commons_economics_receipt()


@app.get("/edgek/commons-scale/economics/summary")
async def edgek_commons_scale_economics_summary():
    """Return the compact proof summary used by the polling web surface."""
    report = load_commons_economics_receipt()
    return {
        "beast_object_type": "commons_scale_economics_summary",
        "version": "1.0",
        "generated_at": report.get("generated_at"),
        "proof_density": report.get("proof_density") or {},
        "marketplace_readiness": report.get("marketplace_readiness") or {},
        "primary_question": (report.get("scale_ladder") or {}).get("primary_question") or {},
        "claim_boundary": report.get("claim_boundary"),
    }


@app.get("/edgek/commons-marketplace")
def edgek_commons_marketplace():
    """Return governed, public-safe listing candidates without transactions."""
    report = load_commons_economics_receipt()
    if commons_marketplace_cache.get("catalog") is None:
        commons_marketplace_cache["catalog"] = commons_scale_economics.marketplace_catalog(report=report)
    return commons_marketplace_cache["catalog"]


def commons_session_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return request.cookies.get("beast_commons_session", "")


def commons_account(request: Request) -> Dict[str, Any]:
    try:
        return commons_testnet.authenticate(commons_session_token(request))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/edgek/commons-auth/signup")
async def edgek_commons_signup(request: Request, payload: Dict[str, Any] = None):
    payload = payload or {}
    try:
        source = request.client.host if request.client else "unknown"
        account = commons_testnet.signup(str(payload.get("email") or ""), str(payload.get("display_name") or ""), str(payload.get("password") or ""), source=source)
        session = commons_testnet.login(str(payload.get("email") or ""), str(payload.get("password") or ""))
        response = JSONResponse({"account": account, "wallet": commons_testnet.wallet(account["user_id"]), "expires_at": session["expires_at"]})
        response.set_cookie("beast_commons_session", session["token"], max_age=43200, httponly=True, samesite="strict", secure=False)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-auth/login")
async def edgek_commons_login(payload: Dict[str, Any] = None):
    payload = payload or {}
    try:
        session = commons_testnet.login(str(payload.get("email") or ""), str(payload.get("password") or ""))
        response = JSONResponse({"account": session["account"], "wallet": commons_testnet.wallet(session["account"]["user_id"]), "expires_at": session["expires_at"]})
        response.set_cookie("beast_commons_session", session["token"], max_age=43200, httponly=True, samesite="strict", secure=False)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/edgek/commons-auth/logout")
async def edgek_commons_logout(request: Request):
    token = commons_session_token(request)
    if token: commons_testnet.logout(token)
    response = JSONResponse({"logged_out": True}); response.delete_cookie("beast_commons_session"); return response


@app.get("/edgek/commons-account")
async def edgek_commons_account(request: Request):
    account = commons_account(request)
    return {"account": account, "wallet": commons_testnet.wallet(account["user_id"])}


@app.post("/edgek/commons-wallet/swap")
async def edgek_commons_wallet_swap(request: Request, payload: Dict[str, Any] = None):
    account = commons_account(request); payload = payload or {}
    try: return {"swap": commons_testnet.swap(account["user_id"], str(payload.get("from_asset") or ""), int(payload.get("amount") or 0)), "wallet": commons_testnet.wallet(account["user_id"])}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-wallet/claim/{credit_id}")
async def edgek_commons_wallet_claim(credit_id: str, request: Request):
    account = commons_account(request)
    credit = next((item for item in commons_economy.state().get("credits") or [] if item.get("credit_id") == credit_id), None)
    if not credit: raise HTTPException(status_code=404, detail="verified credit not found")
    owner = str(credit.get("approved_by") or "")
    if owner not in {account["user_id"], account["email"], account["display_name"]}:
        raise HTTPException(status_code=403, detail="credit is not bound to this account")
    try: return {"claim": commons_testnet.claim_credit(account["user_id"], credit), "wallet": commons_testnet.wallet(account["user_id"])}
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc))


@app.get("/edgek/commons-wallet/pricing")
async def edgek_commons_wallet_pricing(request: Request):
    commons_account(request)
    return commons_testnet.pricing(commons_economy.state().get("credits") or [])


@app.get("/edgek/commons-testnet/audit")
async def edgek_commons_testnet_audit():
    return commons_testnet.audit()


@app.get("/edgek/commons-scale/registration-candidates")
def edgek_commons_registration_candidates(limit: int = 50):
    """Discover benchmark result folders that are candidates for new Spaces."""
    return commons_space_registry.registration_candidates(limit=max(1, min(int(limit), 500)))


@app.post("/edgek/commons-spaces/import")
async def edgek_commons_space_import(payload: Dict[str, Any] = None):
    """Preview or import a bundle from inside the local workspace."""
    payload = payload or {}
    try:
        return commons_space_registry.import_bundle(
            Path(str(payload.get("bundle_path") or "")),
            approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)),
            workspace_root=Path(__file__).resolve().parents[1],
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-spaces/import-remote")
async def edgek_commons_space_import_remote(payload: Dict[str, Any] = None):
    """Fetch a remote bundle and import it only through local verification gates."""
    payload = payload or {}
    bundle_url = str(payload.get("bundle_url") or "")
    if not bundle_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="bundle_url must be http(s)")
    try:
        with httpx.Client(timeout=max(5, min(int(payload.get("timeout_seconds", 30)), 120))) as client:
            response = client.get(bundle_url)
            response.raise_for_status()
            if len(response.content) > 25_000_000:
                raise ValueError("remote bundle exceeds size limit")
            with tempfile.NamedTemporaryFile(prefix="beast-remote-space-", suffix=".zip") as bundle:
                bundle.write(response.content)
                bundle.flush()
                imported = commons_space_registry.import_untrusted_bundle(
                    Path(bundle.name),
                    approved=bool(payload.get("approved", False)),
                    dry_run=bool(payload.get("dry_run", True)),
                )
        return {
            **imported,
            "remote": {
                "bundle_url": bundle_url,
                "authority": "quarantined_hypothesis_until_local_replay",
                "bytes": len(response.content),
            },
        }
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-spaces/{space_id}/adopt")
async def edgek_commons_space_adopt(space_id: str, payload: Dict[str, Any] = None):
    """Adopt selected artifact references after explicit local approval."""
    payload = payload or {}
    try:
        return commons_space_registry.adopt(
            space_id,
            artifact_paths=payload.get("artifact_paths"),
            approved=bool(payload.get("approved", False)),
            dry_run=bool(payload.get("dry_run", True)),
            approved_by=str(payload.get("approved_by") or "operator"),
            reason=str(payload.get("reason") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-spaces/{space_id}/replay")
async def edgek_commons_space_replay(space_id: str, payload: Dict[str, Any] = None):
    """Replay integrity only, or run approved allowlisted verifiers on a local target."""
    payload = payload or {}
    deterministic_only = bool(payload.get("deterministic_only", True))
    target_value = str(payload.get("target") or "")
    try:
        return commons_space_registry.replay(
            space_id,
            target=Path(target_value) if target_value else None,
            deterministic_only=deterministic_only,
            approved=bool(payload.get("approved", False)),
            timeout_seconds=int(payload.get("timeout_seconds", 120)),
            contributor_id=str(payload.get("contributor_id") or "local"),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/commons-spaces/{space_id}/reproductions")
async def edgek_commons_space_reproductions(space_id: str):
    """List local reproduction receipts used to derive Space trust."""
    try:
        commons_space_registry.get(space_id)
        rows = commons_space_registry.replay_engine.list_reproductions(space_id)
        return {"space_id": space_id, "count": len(rows), "reproductions": rows}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/edgek/commons-economy")
async def edgek_commons_economy_state(full: bool = False):
    """Return non-financial credits, duplicate checks, and verified adoptions."""
    return commons_economy.state(full=bool(full))


@app.get("/edgek/commons-economy/proof/{space_id}")
async def edgek_commons_economy_proof(space_id: str):
    """Build a reproduction-backed proof of useful compute reduction."""
    try:
        return commons_economy.proof(space_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/edgek/commons-economy/simulate")
async def edgek_commons_economy_simulate(payload: Dict[str, Any] = None):
    """Simulate capped Commons credits with no financial or transfer value."""
    payload = payload or {}
    try:
        limit = max(1, min(int(payload.get("limit", 10)), 100))
        return commons_economy.simulate(str(payload.get("space_id")), limit=limit) if payload.get("space_id") else commons_economy.simulate(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-economy/credits/{space_id}")
async def edgek_commons_economy_issue(space_id: str, payload: Dict[str, Any] = None):
    """Issue one sealed non-financial credit after explicit approval."""
    payload = payload or {}
    try:
        return commons_economy.issue_credit(
            space_id,
            approved=bool(payload.get("approved", False)),
            approved_by=str(payload.get("approved_by") or "operator"),
            reason=str(payload.get("reason") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-spaces/{space_id}/promote-crystal")
async def edgek_commons_space_promote_crystal(space_id: str, payload: Dict[str, Any] = None):
    """Promote a thrice-reproduced Space into advisory Crystal Compute."""
    payload = payload or {}
    try:
        return commons_crystal_promoter.promote(
            space_id,
            approved=bool(payload.get("approved", False)),
            approved_by=str(payload.get("approved_by") or "operator"),
            reason=str(payload.get("reason") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/commons-prototype/complete")
async def edgek_commons_prototype_complete(payload: Dict[str, Any] = None):
    """Complete the explicitly approved Tiny Llama first-prototype workflow."""
    payload = payload or {}
    try:
        return commons_prototype_runner.complete(
            space_id=str(payload.get("space_id") or "tiny_llama_opus_gateway_repair"),
            target=Path(str(payload.get("target") or Path(__file__).resolve().parents[1])),
            approved=bool(payload.get("approved", False)),
            approved_by=str(payload.get("approved_by") or "operator"),
            reason=str(payload.get("reason") or ""),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/commons-policy/examples")
async def edgek_commons_policy_examples(limit: int = 500):
    """Extract privacy-safe route policy examples from local receipts."""
    return commons_policy_learner.extract_examples(max(1, min(limit, 2000)))


@app.get("/edgek/commons-policy/model")
async def edgek_commons_policy_model():
    """Train and return the current tiny local shadow ranker."""
    return commons_policy_learner.train()


@app.get("/edgek/commons-policy/evaluation")
async def edgek_commons_policy_evaluation():
    """Evaluate route matching and verification preservation offline."""
    return commons_policy_learner.evaluate()


@app.post("/edgek/commons-policy/recommend")
async def edgek_commons_policy_recommend(payload: Dict[str, Any] = None):
    """Recommend a lower-compute route in non-enforcing shadow mode."""
    return commons_policy_learner.recommend(payload or {})


@app.get("/edgek/federated-commons")
async def edgek_federated_commons_state():
    """Return local allowlists, quarantined hypotheses, revocations, and reputation."""
    return federated_commons.state()


@app.get("/edgek/proof-local/spaces/{space_id}/receipt")
async def edgek_proof_local_receipt(space_id: str, contributor_id: str = "local_node", ttl_minutes: int = 30):
    """Publish a signed metadata-only receipt before any artifact transfer."""
    try:
        return federated_commons.prepare_receipt_packet(
            space_id, contributor_id=contributor_id, ttl_minutes=ttl_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/spaces/{space_id}/manifest")
async def edgek_proof_local_manifest(space_id: str):
    """Publish the public-safe manifest stage without artifact payload bytes."""
    try:
        stage = build_manifest_stage(commons_space_registry.public_space_card(space_id))
        validation = validate_manifest_stage(stage)
        if not validation["valid"]:
            raise ValueError("manifest stage privacy validation failed")
        return stage
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/spaces/{space_id}/verifiers")
async def edgek_proof_local_verifiers(space_id: str):
    """Publish inert verifier descriptors; remote commands never execute."""
    try:
        stage = build_verifier_stage(commons_space_registry.public_space_card(space_id))
        validation = validate_verifier_stage(stage)
        if not validation["valid"]:
            raise ValueError("verifier stage privacy validation failed")
        return stage
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/receipt-packets/ingest")
async def edgek_proof_local_receipt_ingest(payload: Dict[str, Any] = None):
    payload = payload or {}
    try:
        return federated_commons.ingest_receipt_packet(
            payload.get("packet") or {},
            require_allowlisted=bool(payload.get("require_allowlisted", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/advertisements/prepare")
async def edgek_proof_local_advertisement_prepare(payload: Dict[str, Any] = None):
    payload = payload or {}
    try:
        return federated_commons.prepare_capability_advertisement(
            node_id=str(payload.get("node_id") or "local_node"),
            contributor_id=str(payload.get("contributor_id") or "local_node"),
            task_classes=list(payload.get("task_classes") or []),
            verifier_classes=list(payload.get("verifier_classes") or []),
            engine_profiles=list(payload.get("engine_profiles") or ["ollama_cpu"]),
            privacy_classes_accepted=list(payload.get("privacy_classes_accepted") or ["public_metadata_only"]),
            load_bucket=str(payload.get("load_bucket") or "low"),
            rtt_bucket_ms=int(payload.get("rtt_bucket_ms") or 10),
            max_transfer_bytes=int(payload.get("max_transfer_bytes") or 5_000_000),
            ttl_seconds=int(payload.get("ttl_seconds") or 60),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/advertisements/ingest")
async def edgek_proof_local_advertisement_ingest(payload: Dict[str, Any] = None):
    payload = payload or {}
    try:
        return federated_commons.ingest_capability_advertisement(
            payload.get("advertisement") or {},
            require_allowlisted=bool(payload.get("require_allowlisted", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/route")
async def edgek_proof_local_route(payload: Dict[str, Any] = None):
    """Rank fresh LAN proof metadata, then apply Compute Governor authority gates."""
    payload = payload or {}
    request = ProofRouteRequest(
        task_class=str(payload.get("task_class") or "unknown"),
        space_id=str(payload.get("space_id") or ""),
        manifest_hash=str(payload.get("manifest_hash") or ""),
        privacy_class=str(payload.get("privacy_class") or "public_metadata_only"),
        required_verifiers=list(payload.get("required_verifiers") or []),
        max_lan_rtt_ms=max(1, int(payload.get("max_lan_rtt_ms") or 200)),
        max_transfer_bytes=max(0, int(payload.get("max_transfer_bytes") or 5_000_000)),
        risk_class=str(payload.get("risk_class") or "low"),
        allow_trusted_lan=bool(payload.get("allow_trusted_lan", True)),
        fallback=str(payload.get("fallback") or "local_ollama"),
    )
    plan = federated_commons.plan_proof_route(request)
    selected = plan.get("selected") if isinstance(plan.get("selected"), dict) else {}
    reproduction_id = str(payload.get("reproduction_id") or "")
    local_replay_verified = False
    if reproduction_id and selected.get("space_id"):
        local_replay_verified = any(
            item.get("reproduction_id") == reproduction_id
            and item.get("reproduced") is True
            and item.get("manifest_hash") == selected.get("manifest_hash")
            for item in commons_space_registry.replay_engine.list_reproductions(str(selected.get("space_id")))
        )
    gate = compute_interceptor.governor.gate_proof_local_route(
        plan,
        risk_class=request.risk_class,
        approval_granted=bool(payload.get("approval_granted", False)),
        local_replay_verified=local_replay_verified,
    )
    return {
        "request": request.__dict__, "plan": plan, "gate": gate,
        "reproduction_evidence": {
            "reproduction_id": reproduction_id or None,
            "verified_locally": local_replay_verified,
            "caller_boolean_ignored": "local_replay_verified" in payload,
        },
    }


@app.get("/edgek/proof-local/distillation")
async def edgek_proof_local_distillation():
    """Return the latest Phase 7 crystal-to-adapter lattice/candidate report."""
    latest = crystal_to_adapter_distiller.output_root / "phase7_crystal_to_adapter_latest.json"
    if latest.is_file():
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return crystal_to_adapter_distiller.harvest(limit=5000)


@app.post("/edgek/proof-local/distillation/build")
async def edgek_proof_local_distillation_build(payload: Dict[str, Any] = None):
    """Build Phase 7 lattice, local-only dataset, adapter receipt, and mutation report."""
    payload = payload or {}
    limit = max(1, min(int(payload.get("limit") or 5000), 50_000))
    try:
        results_root = Path(str(payload.get("results_root"))) if payload.get("results_root") else crystal_to_adapter_distiller.results_root
        output_root = Path(str(payload.get("output_root"))) if payload.get("output_root") else crystal_to_adapter_distiller.output_root
        distiller = CrystalToAdapterDistiller(results_root=results_root, output_root=output_root)
        return distiller.harvest(limit=limit)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/distillation/dataset")
async def edgek_proof_local_distillation_dataset(limit: int = 50):
    """Preview privacy-scrubbed local-only Phase 7 training rows."""
    dataset_path = crystal_to_adapter_distiller.output_root / "distillation_dataset_latest.jsonl"
    if not dataset_path.is_file():
        crystal_to_adapter_distiller.harvest(limit=5000)
    rows: List[Dict[str, Any]] = []
    try:
        with dataset_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if len(rows) >= max(1, min(int(limit), 500)):
                    break
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "beast_object_type": "distillation_dataset_preview",
        "version": "1.0",
        "dataset_path": str(dataset_path),
        "preview_count": len(rows),
        "public_export_allowed": False,
        "rows": rows,
    }


@app.post("/edgek/proof-local/distillation/ollama-model")
async def edgek_proof_local_distillation_ollama_model(payload: Dict[str, Any] = None):
    """Create or preview a real Ollama Modelfile-derived BEAST adapter model."""
    payload = payload or {}
    try:
        return crystal_to_adapter_distiller.create_ollama_crystal_adapter(
            base_model=str(payload.get("base_model") or "qwen2.5:0.5b"),
            model_name=str(payload.get("model_name") or "beast-crystal-qwen25-05b:latest"),
            execute=bool(payload.get("execute", True)),
            timeout_seconds=max(30, min(int(payload.get("timeout_seconds") or 600), 1800)),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/distillation/lora-lattice")
async def edgek_proof_local_distillation_lora_lattice(payload: Dict[str, Any] = None):
    """Train actual low-rank crystal-lattice matrices from local Phase 7 rows."""
    payload = payload or {}
    try:
        receipt = crystal_to_adapter_distiller.train_crystal_lora_lattice(
            dimension=max(64, min(int(payload.get("dimension") or 512), 8192)),
            rank=max(1, min(int(payload.get("rank") or 16), 256)),
            epochs=max(1, min(int(payload.get("epochs") or 250), 5000)),
            learning_rate=max(0.001, min(float(payload.get("learning_rate") or 0.35), 5.0)),
            seed=int(payload.get("seed") or 1337),
        )
        sft = crystal_to_adapter_distiller.export_sft_training_package(limit=max(1, min(int(payload.get("sft_limit") or 1000), 50_000)))
        return {"training": receipt, "sft_package": sft}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/distillation/lora-lattice")
async def edgek_proof_local_distillation_lora_lattice_latest():
    """Return latest crystal-lattice matrix training receipt."""
    latest = crystal_to_adapter_distiller.output_root / "crystal_lora_lattice_training_latest.json"
    if not latest.is_file():
        raise HTTPException(status_code=404, detail="run POST /edgek/proof-local/distillation/lora-lattice first")
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/distillation/true-lora-package")
async def edgek_proof_local_distillation_true_lora_package(payload: Dict[str, Any] = None):
    """Export a PEFT/LoRA-ready package from local crystal SFT rows."""
    payload = payload or {}
    try:
        return crystal_to_adapter_distiller.export_true_lora_package(
            base_model_name=str(payload.get("base_model_name") or "Qwen/Qwen2.5-0.5B-Instruct"),
            adapter_name=str(payload.get("adapter_name") or "beast-crystal-lora"),
            rank=max(1, min(int(payload.get("rank") or 16), 256)),
            lora_alpha=max(1, min(int(payload.get("lora_alpha") or 32), 512)),
            lora_dropout=max(0.0, min(float(payload.get("lora_dropout") or 0.05), 0.95)),
            max_rows=max(1, min(int(payload.get("max_rows") or 1000), 50_000)),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/semantic-pages")
async def edgek_proof_local_semantic_pages(include_pages: bool = False):
    """Return Phase 3 semantic compute page state and reuse evidence."""
    return semantic_compute_page_store.state(include_pages=include_pages)


@app.post("/edgek/proof-local/semantic-pages/build")
async def edgek_proof_local_semantic_pages_build(payload: Dict[str, Any] = None):
    """Build content-addressed Phase 3 pages from local crystal evidence."""
    payload = payload or {}
    try:
        return build_phase3_semantic_pages(
            store=semantic_compute_page_store,
            ttl_seconds=max(1, min(int(payload.get("ttl_seconds") or 86_400), 31_536_000)),
            reuse_repetitions=max(1, min(int(payload.get("reuse_repetitions") or 3), 1000)),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/generative-crystals")
async def edgek_proof_local_generative_crystals(include_templates: bool = False):
    """Return Phase 5 context-aware generative crystal template state."""
    return generative_crystal_store.state(include_templates=include_templates)


@app.post("/edgek/proof-local/generative-crystals/gauntlet")
async def edgek_proof_local_generative_crystals_gauntlet():
    """Run the Phase 5 bounded-template/demotion gauntlet."""
    try:
        return run_phase5_generative_crystal_gauntlet(store=generative_crystal_store)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/proof-local/import-staged")
async def edgek_proof_local_import_staged(payload: Dict[str, Any] = None):
    """Fetch receipt -> manifest -> verifier -> optional bundle, aborting at each gate."""
    payload = payload or {}
    base_url = str(payload.get("base_url") or "").rstrip("/")
    space_id = str(payload.get("space_id") or "")
    contributor_id = str(payload.get("contributor_id") or "remote_node")
    stop_after = str(payload.get("stop_after") or "manifest")
    if not base_url.startswith(("http://", "https://")) or not space_id:
        raise HTTPException(status_code=400, detail="base_url and space_id are required")
    if stop_after not in {"receipt", "manifest", "verifier", "bundle"}:
        raise HTTPException(status_code=400, detail="invalid stop_after stage")
    received = 0
    packet = {}
    transfer_id = "xfer_staged_" + str(time.time_ns())
    timeout = max(5, min(int(payload.get("timeout_seconds") or 30), 120))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                f"{base_url}/edgek/proof-local/spaces/{space_id}/receipt",
                params={"contributor_id": contributor_id},
            )
            response.raise_for_status()
            received += len(response.content)
            if len(response.content) > 512_000:
                raise ValueError("receipt packet exceeds size limit")
            packet = response.json()
            ingested = federated_commons.ingest_receipt_packet(packet)
            if stop_after == "receipt":
                return {"stage": "receipt", "packet": ingested, "bytes_received": received}

            response = client.get(f"{base_url}/edgek/proof-local/spaces/{space_id}/manifest")
            response.raise_for_status()
            received += len(response.content)
            if len(response.content) > 1_000_000:
                raise ValueError("manifest stage exceeds size limit")
            manifest_stage = response.json()
            manifest_validation = validate_manifest_stage(
                manifest_stage, expected_manifest_hash=str(packet.get("manifest_hash") or ""),
            )
            if not manifest_validation["valid"]:
                raise ValueError("manifest stage validation failed: " + "; ".join(manifest_validation["errors"]))
            if stop_after == "manifest":
                receipt = federated_commons.record_staged_transfer(
                    transfer_id=transfer_id, stage="manifest", accepted=True,
                    reason="operator_stopped_after_manifest", bytes_received=received,
                    declared_artifact_bytes=int(packet.get("declared_artifact_bytes") or 0),
                    declared_bundle_bytes=int(packet.get("declared_bundle_bytes") or 0),
                    packet_id=str(packet.get("packet_id") or ""),
                    manifest_hash=str(packet.get("manifest_hash") or ""),
                )
                return {"stage": "manifest", "packet": ingested, "manifest": manifest_stage, "transfer": receipt}

            response = client.get(f"{base_url}/edgek/proof-local/spaces/{space_id}/verifiers")
            response.raise_for_status()
            received += len(response.content)
            verifier_stage = response.json()
            verifier_validation = validate_verifier_stage(
                verifier_stage, expected_manifest_hash=str(packet.get("manifest_hash") or ""),
            )
            if not verifier_validation["valid"]:
                raise ValueError("verifier stage validation failed: " + "; ".join(verifier_validation["errors"]))
            if stop_after == "verifier":
                receipt = federated_commons.record_staged_transfer(
                    transfer_id=transfer_id, stage="verifier", accepted=True,
                    reason="operator_stopped_after_verifier", bytes_received=received,
                    declared_artifact_bytes=int(packet.get("declared_artifact_bytes") or 0),
                    declared_bundle_bytes=int(packet.get("declared_bundle_bytes") or 0),
                    packet_id=str(packet.get("packet_id") or ""),
                    manifest_hash=str(packet.get("manifest_hash") or ""),
                )
                return {"stage": "verifier", "manifest": manifest_stage, "verifiers": verifier_stage, "transfer": receipt}

            response = client.get(f"{base_url}/edgek/commons-spaces/{space_id}/bundle")
            response.raise_for_status()
            received += len(response.content)
            if len(response.content) > 25_000_000:
                raise ValueError("remote bundle exceeds size limit")
            bundle_sha256 = "sha256:" + hashlib.sha256(response.content).hexdigest()
            if bundle_sha256 != packet.get("bundle_sha256"):
                raise ValueError("remote bundle hash does not match signed receipt packet")
            with tempfile.NamedTemporaryFile(prefix="beast-staged-space-", suffix=".zip") as bundle:
                bundle.write(response.content)
                bundle.flush()
                imported = commons_space_registry.import_untrusted_bundle(
                    Path(bundle.name), approved=bool(payload.get("approved", False)),
                    dry_run=bool(payload.get("dry_run", True)),
                )
            receipt = federated_commons.record_staged_transfer(
                transfer_id=transfer_id, stage="bundle", accepted=True,
                reason="full_bundle_locally_verified", bytes_received=received,
                declared_artifact_bytes=int(packet.get("declared_artifact_bytes") or 0),
                declared_bundle_bytes=int(packet.get("declared_bundle_bytes") or 0),
                packet_id=str(packet.get("packet_id") or ""),
                manifest_hash=str(packet.get("manifest_hash") or ""),
                full_bundle_transferred=True,
            )
            return {"stage": "bundle", "import": imported, "transfer": receipt}
    except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError) as exc:
        if packet:
            federated_commons.record_staged_transfer(
                transfer_id=transfer_id, stage="aborted", accepted=False,
                reason=str(exc), bytes_received=received,
                declared_artifact_bytes=int(packet.get("declared_artifact_bytes") or 0),
                declared_bundle_bytes=int(packet.get("declared_bundle_bytes") or 0),
                packet_id=str(packet.get("packet_id") or ""),
                manifest_hash=str(packet.get("manifest_hash") or ""),
            )
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/federated-commons/prepare/{space_id}")
async def edgek_federated_commons_prepare(space_id: str, payload: Dict[str, Any] = None):
    """Create a signed, expiring federation envelope for one valid local Space."""
    payload = payload or {}
    try:
        return federated_commons.prepare(
            space_id,
            contributor_id=str(payload.get("contributor_id") or "local_node"),
            ttl_days=int(payload.get("ttl_days", 30)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/federated-commons/allowlist")
async def edgek_federated_commons_allowlist(payload: Dict[str, Any] = None):
    """Allow one contributor after explicit local operator approval."""
    payload = payload or {}
    try:
        return federated_commons.allow_contributor(
            str(payload.get("contributor_id") or ""),
            public_key_hash=str(payload.get("public_key_hash") or ""),
            approved=bool(payload.get("approved", False)),
            reason=str(payload.get("reason") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/federated-commons/ingest")
async def edgek_federated_commons_ingest(payload: Dict[str, Any] = None):
    """Ingest a signed envelope as a quarantined hypothesis, never an authority."""
    payload = payload or {}
    try:
        return federated_commons.ingest(
            payload.get("envelope") or {},
            require_allowlisted=bool(payload.get("require_allowlisted", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/federated-commons/{envelope_id}/reproduce")
async def edgek_federated_commons_reproduce(envelope_id: str, payload: Dict[str, Any] = None):
    """Reproduce an ingested hypothesis and update contributor reputation."""
    payload = payload or {}
    state = federated_commons.state()
    record = next((item for item in state["envelopes"] if item.get("envelope_id") == envelope_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="federated envelope not found")
    try:
        replay = commons_space_registry.replay(
            str(record.get("space_id") or ""),
            target=Path(str(payload.get("target"))) if payload.get("target") else None,
            deterministic_only=bool(payload.get("deterministic_only", True)),
            approved=bool(payload.get("approved", False)),
            timeout_seconds=int(payload.get("timeout_seconds", 120)),
            contributor_id=str(record.get("contributor_id") or "unknown"),
        )
        reputation = federated_commons.record_reproduction(envelope_id, replay)
        return {"replay": replay, "federation": reputation}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/federated-commons/{envelope_id}/revoke")
async def edgek_federated_commons_revoke(envelope_id: str, payload: Dict[str, Any] = None):
    """Revoke a federated hypothesis under explicit local authority."""
    payload = payload or {}
    try:
        return federated_commons.revoke(
            envelope_id,
            approved=bool(payload.get("approved", False)),
            reason=str(payload.get("reason") or ""),
            approved_by=str(payload.get("approved_by") or "operator"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/kv-cache/state")
@app.post("/edgek/kv-cache/state")
async def edgek_kv_cache_state():
    """Return local KV/cache transport state."""
    return kv_cache_transport.get_stats()

@app.get("/edgek/inference-engines")
async def edgek_inference_engines(probe: bool = False):
    """Return CPU-first engine capabilities; live probes are explicit and bounded."""
    return inference_engine_fabric.inventory(probe=probe)

def _crystal_reuse_request(payload: Dict[str, Any]) -> CrystalReuseRequest:
    return CrystalReuseRequest(
        prompt=str(payload.get("prompt") or ""),
        model=str(payload.get("model") or ""),
        parameters=payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {},
        system_prompt=str(payload.get("system_prompt") or ""),
        task_class=str(payload.get("task_class") or "chat_completion"),
        repo_fingerprint=payload.get("repo_fingerprint"),
        policy_version=str(payload.get("policy_version") or "crystal_reuse_v1"),
        tokenizer=str(payload.get("tokenizer") or ""),
        prompt_prefix=str(payload.get("prompt_prefix") or ""),
        preferred_engine=payload.get("preferred_engine"),
        provider=str(payload.get("provider") or ""),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )

def _agent_passport_from_payload(payload: Dict[str, Any]) -> AgentPassport:
    caller = payload.get("caller")
    if isinstance(caller, dict):
        return AgentPassport.from_dict(caller)
    if isinstance(caller, str) and caller.strip():
        component = caller.strip()
        if component.startswith("spiffe://beast.local/"):
            component = component[len("spiffe://beast.local/"):]
        return AgentPassport.local(component)
    return AgentPassport.local("proxy/gateway")

def _harness_request(payload: Dict[str, Any]) -> BeastHarnessRequest:
    provider = str(payload.get("provider") or "local")
    target = str(payload.get("target") or f"spiffe://beast.local/provider/{provider}")
    return BeastHarnessRequest(
        prompt=str(payload.get("prompt") or ""),
        model=str(payload.get("model") or ""),
        caller=_agent_passport_from_payload(payload),
        parameters=payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {},
        provider=provider,
        task_class=str(payload.get("task_class") or "chat_completion"),
        repo_fingerprint=payload.get("repo_fingerprint"),
        policy_version=str(payload.get("policy_version") or "crystal_reuse_v1"),
        system_prompt=str(payload.get("system_prompt") or ""),
        tokenizer=str(payload.get("tokenizer") or ""),
        prompt_prefix=str(payload.get("prompt_prefix") or ""),
        preferred_engine=payload.get("preferred_engine"),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        enterprise=payload.get("enterprise") if isinstance(payload.get("enterprise"), dict) else {},
        projected_cost_usd=float(payload.get("projected_cost_usd") or 0.0),
        projected_tokens=int(payload.get("projected_tokens") or 0),
        target=target,
        action=str(payload.get("action") or "call"),
    )

@app.get("/edgek/crystal-reuse")
async def edgek_crystal_reuse_inventory(probe_integrations: bool = False, probe_timeout_seconds: float = 0.45):
    """Report the crystal reuse gateway and BEAST-local capability state."""
    return crystal_reuse_gateway.inventory(
        probe_integrations=probe_integrations,
        probe_timeout_seconds=probe_timeout_seconds,
    )

@app.get("/edgek/crystal-reuse/integrations")
async def edgek_crystal_reuse_integrations(probe: bool = False, timeout_seconds: float = 0.45):
    """Compatibility route returning BEAST-native local capabilities."""
    return crystal_reuse_gateway.integration_health(probe=probe, timeout_seconds=timeout_seconds)

@app.get("/edgek/crystal-reuse/local-capabilities")
async def edgek_crystal_reuse_local_capabilities(probe: bool = False, timeout_seconds: float = 0.45):
    """Return BEAST-native local crystal reuse capabilities."""
    return crystal_reuse_gateway.integration_health(probe=probe, timeout_seconds=timeout_seconds)

@app.get("/edgek/crystal-reuse/acceptance")
async def edgek_crystal_reuse_acceptance(probe: bool = False, timeout_seconds: float = 0.45):
    """Run local capability acceptance checks."""
    return CrystalIntegrationAcceptanceHarness().run(probe=probe, timeout_seconds=timeout_seconds)

@app.post("/edgek/crystal-reuse/decide")
async def edgek_crystal_reuse_decide(payload: Dict[str, Any] = None):
    """Ask BEAST whether a request can reuse a crystallized inference artifact before provider execution."""
    payload = payload or {}
    if not payload.get("prompt") or not payload.get("model"):
        raise HTTPException(status_code=400, detail="prompt and model are required")
    return crystal_reuse_gateway.decide(_crystal_reuse_request(payload)).to_dict()

@app.post("/edgek/integration-harness/run")
async def edgek_integration_harness_run(payload: Dict[str, Any] = None):
    """Run the thin AgentPassport -> CrystalReuse -> Provider -> Seal -> Hull -> Enterprise -> Readiness harness."""
    payload = payload or {}
    if not payload.get("prompt") or not payload.get("model"):
        raise HTTPException(status_code=400, detail="prompt and model are required")
    try:
        return thin_integration_harness.run(_harness_request(payload))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edgek/kv-cache/restore-harness")
async def edgek_kv_cache_restore_harness(model: str = "beast-kv-smoke", tokenizer: str = "beast-tokenizer"):
    """Run a bounded KV tensor restore harness across BEAST's transport layer."""
    return KVRestoreHarness(kv_cache_transport).run(model=model, tokenizer=tokenizer)

@app.get("/edgek/readiness/federation-soak")
async def edgek_readiness_federation_soak(nodes: int = 3, cycles: int = 3):
    """Run bounded multi-node federation churn/replay soak."""
    return thin_integration_harness.readiness.federation_soak_gate(nodes=nodes, cycles=cycles)

@app.get("/edgek/readiness/workload-frequency")
async def edgek_readiness_workload_frequency(window_days: int = 7):
    """Emit a 7/30-day normalized workload-frequency receipt."""
    return thin_integration_harness.readiness.workload_frequency_receipt(window_days=window_days)

@app.get("/edgek/api/groups")
async def edgek_api_groups():
    """Publish stable API groups and experimental/deprecated boundaries."""
    return {
        "beast_object_type": "beast_api_surface_groups",
        "version": "1.0",
        "stable": {
            "health": ["/health", "/proxy/health", "/mcp/health"],
            "providers": ["/edgek/providers/registry", "/edgek/providers/adapters", "/edgek/providers/secrets/route/{provider_id}"],
            "integration_harness": ["/edgek/integration-harness/run"],
            "crystal_reuse": ["/edgek/crystal-reuse", "/edgek/crystal-reuse/decide", "/edgek/crystal-reuse/record", "/edgek/crystal-reuse/prefill"],
            "memory_security": ["/edgek/memory-security"],
            "readiness": ["/edgek/readiness/federation-soak", "/edgek/readiness/workload-frequency"],
        },
        "experimental": {
            "commons_marketplace": ["/edgek/commons-*", "/edgek/proof-local/*"],
            "crystal_lattice": ["/edgek/crystal-chain", "/edgek/crystal-lattice"],
            "operator_tui_support": ["/edgek/session/*", "/edgek/insights/*", "/edgek/handoff/*"],
        },
        "deprecated": [],
        "policy": "Stable groups preserve request/response object types; experimental routes may add fields without notice.",
    }

@app.post("/edgek/crystal-reuse/export")
async def edgek_crystal_reuse_export(payload: Dict[str, Any] = None):
    """Export a local capability bundle for a crystal reuse decision."""
    payload = payload or {}
    if payload.get("decision") and isinstance(payload.get("decision"), dict):
        decision_payload = payload["decision"]
        decision = CrystalReuseDecision(
            decision_id=str(decision_payload.get("decision_id") or "external_decision"),
            action=str(decision_payload.get("action") or "execute_local_cpu"),
            source=str(decision_payload.get("source") or "local_execution_gateway"),
            confidence=float(decision_payload.get("confidence") or 0.0),
            reason=str(decision_payload.get("reason") or "provided_decision"),
            payload=decision_payload.get("payload") if isinstance(decision_payload.get("payload"), dict) else {},
            avoided_tokens_estimate=int(decision_payload.get("avoided_tokens_estimate") or 0),
            telemetry=decision_payload.get("telemetry") if isinstance(decision_payload.get("telemetry"), dict) else {},
            residue_seal=decision_payload.get("residue_seal") if isinstance(decision_payload.get("residue_seal"), dict) else {},
        )
    else:
        if not payload.get("prompt") or not payload.get("model"):
            raise HTTPException(status_code=400, detail="prompt and model are required")
        decision = crystal_reuse_gateway.decide(_crystal_reuse_request(payload), seal_decision=False)
    return crystal_reuse_gateway.export_integration_bundle(decision)

@app.post("/edgek/crystal-reuse/record")
async def edgek_crystal_reuse_record(payload: Dict[str, Any] = None):
    """Record a provider response as an exact answer crystal and optionally a verified semantic crystal."""
    payload = payload or {}
    if not payload.get("prompt") or not payload.get("model") or "response" not in payload:
        raise HTTPException(status_code=400, detail="prompt, model, and response are required")
    return crystal_reuse_gateway.record_execution_response(
        _crystal_reuse_request(payload),
        str(payload.get("response") or ""),
        route=str(payload.get("route") or "local_cpu"),
        engine=str(payload.get("engine") or "ollama"),
        cost_usd=payload.get("cost_usd"),
        verified=bool(payload.get("verified", False)),
        avoided_tokens_estimate=int(payload.get("avoided_tokens_estimate") or 0),
        evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
        write_memory=bool(payload.get("write_memory", False)),
    )

@app.post("/edgek/crystal-reuse/prefill")
async def edgek_crystal_reuse_prefill(payload: Dict[str, Any] = None):
    """Register a durable prefill identity for exact model/tokenizer/prompt-prefix reuse."""
    payload = payload or {}
    if not payload.get("prompt") or not payload.get("model") or not payload.get("tokenizer"):
        raise HTTPException(status_code=400, detail="prompt, model, and tokenizer are required")
    return crystal_reuse_gateway.register_prefill_crystal(
        _crystal_reuse_request(payload),
        kv_cache_metadata=payload.get("kv_cache_metadata") if isinstance(payload.get("kv_cache_metadata"), dict) else {},
        compatibility=payload.get("compatibility") if isinstance(payload.get("compatibility"), dict) else {},
    )

@app.post("/edgek/crystal-reuse/kv-block")
async def edgek_crystal_reuse_kv_block(payload: Dict[str, Any] = None):
    """Register a KV block with the BEAST LMCache-style transport adapter."""
    payload = payload or {}
    if not payload.get("prompt") or not payload.get("model") or not payload.get("tokenizer"):
        raise HTTPException(status_code=400, detail="prompt, model, and tokenizer are required")
    try:
        return crystal_reuse_gateway.register_kv_block(
            _crystal_reuse_request(payload),
            engine=str(payload.get("engine") or payload.get("preferred_engine") or "ollama"),
            location=str(payload.get("location") or "cpu"),
            precision=str(payload.get("precision") or "fp16"),
            num_layers=int(payload.get("num_layers") or 0),
            num_heads=int(payload.get("num_heads") or 0),
            head_dim=int(payload.get("head_dim") or 0),
            seq_len=int(payload.get("seq_len") or 0),
            size_bytes=int(payload.get("size_bytes") or 0),
            metadata=payload.get("kv_metadata") if isinstance(payload.get("kv_metadata"), dict) else {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/proof-local/hardware-adapters")
async def edgek_proof_local_hardware_adapters(probe: bool = False):
    """Return Phase 6 optional hardware adapter validation cards."""
    return hardware_adapter_validator.validate(probe=probe)


@app.post("/edgek/proof-local/adapter-comparison")
async def edgek_proof_local_adapter_comparison(payload: Dict[str, Any] = None):
    """Run held-out baseline/wrapper/loaded-LoRA/crystal/cloud proposal comparison."""
    payload = payload or {}
    try:
        return adapter_comparison_gauntlet.run(
            live_ollama=bool(payload.get("live_ollama", False)),
            ollama_host=str(payload.get("ollama_host") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"),
            run_loaded_lora=bool(payload.get("run_loaded_lora", True)),
            live_cloud=bool(payload.get("live_cloud", False)),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/inference-engines/{engine_id}/generate")
async def edgek_inference_engine_generate(engine_id: str, payload: Dict[str, Any] = None):
    """Execute a bounded request only on an explicitly CPU-capable local engine."""
    payload = payload or {}
    prompt = str(payload.get("prompt") or "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    try:
        return inference_engine_fabric.generate(
            engine_id,
            model=str(payload.get("model") or os.environ.get("OLLAMA_MODEL") or "llama3.2:3b"),
            prompt=prompt,
            system_prompt=str(payload.get("system_prompt") or ""),
            max_tokens=max(1, min(int(payload.get("max_tokens") or 128), 4096)),
            timeout_seconds=max(1.0, min(float(payload.get("timeout_seconds") or 60.0), 300.0)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"local inference engine error: {type(exc).__name__}")

@app.get("/edgek/crystal-chain")
async def edgek_crystal_chain_state(include_blocks: bool = False, limit: int = 25):
    """Verify the local tamper-evident crystallized-compute lifecycle chain."""
    state = commons_space_registry.crystal_chain.state()
    if include_blocks:
        state["blocks"] = commons_space_registry.crystal_chain.blocks()[-max(1, min(limit, 100)):]
    return state


@app.get("/edgek/crystal-chain/witness")
async def edgek_crystal_chain_witness_state():
    """Return Phase 4 cross-signed chain-head witness state and audit."""
    return {
        "beast_object_type": "crystal_chain_witness_dashboard",
        "version": "1.0",
        "state": crystal_chain_witness_store.state(),
        "audit": crystal_chain_witness_store.audit_chain(commons_space_registry.crystal_chain),
        "lattice": crystal_lattice_ledger.state(),
        "financial_asset": False,
    }


@app.post("/edgek/crystal-chain/witness/attest")
async def edgek_crystal_chain_witness_attest(payload: Dict[str, Any] = None):
    """Sign and locally witness the current Commons Crystal Chain head."""
    payload = payload or {}
    try:
        lattice_verification = crystal_lattice_ledger.verify()
        attestation = crystal_chain_witness_store.attest_chain_head(
            commons_space_registry.crystal_chain,
            lattice_head_hash=str(payload.get("lattice_head_hash") or lattice_verification.head_hash),
        )
        record = crystal_chain_witness_store.witness(
            attestation,
            peer_id=str(payload.get("peer_id") or commons_space_registry.crystal_chain.node_id),
        )
        return {
            "beast_object_type": "crystal_chain_witness_attest_result",
            "version": "1.0",
            "attestation": attestation,
            "record": record,
            "audit": crystal_chain_witness_store.audit_chain(commons_space_registry.crystal_chain),
        }
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/edgek/crystal-lattice")
async def edgek_crystal_lattice_state():
    """Return append-only crystal lattice checkpoint/defrag state."""
    return crystal_lattice_ledger.state()


@app.post("/edgek/crystal-lattice/checkpoint")
async def edgek_crystal_lattice_checkpoint(payload: Dict[str, Any] = None):
    """Append the latest vector/matrix lattice heads to the append-only ledger."""
    payload = payload or {}
    try:
        checkpoint = crystal_lattice_ledger.append_latest(
            distillation_root=Path(str(payload.get("distillation_root"))) if payload.get("distillation_root") else crystal_to_adapter_distiller.output_root,
            event_type=str(payload.get("event_type") or "lattice_checkpoint"),
        )
        chain_block = commons_space_registry.crystal_chain.append("lattice_checkpoint_appended", str(checkpoint["checkpoint_hash"]), {
            "checkpoint_hash": checkpoint["checkpoint_hash"],
            "lattice_head_hash": crystal_lattice_ledger.verify().head_hash,
            "private_payload_exported": False,
        })
        return {"checkpoint": checkpoint, "crystal_chain_block": chain_block, "state": crystal_lattice_ledger.state()}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/edgek/crystal-lattice/defrag")
async def edgek_crystal_lattice_defrag():
    """Create a compact latest-head lattice index without rewriting history."""
    try:
        snapshot = crystal_lattice_ledger.defrag()
        chain_block = commons_space_registry.crystal_chain.append("lattice_defrag_snapshot", str(snapshot["snapshot_hash"]), {
            "snapshot_hash": snapshot["snapshot_hash"],
            "ledger_head_hash": snapshot["ledger_head_hash"],
            "private_payload_exported": False,
        })
        return {"snapshot": snapshot, "crystal_chain_block": chain_block, "state": crystal_lattice_ledger.state()}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Compute and Crystal Compute routes are owned by app.routes.compute.

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

# Workspace, Code Cortex, and worktree routes are owned by app.routes.workspace.

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

def _dedupe_routes_keep_first() -> None:
    """Keep module-mounted routes active while legacy inline handlers retire.

    The extracted route families are mounted before the historical inline
    handlers. Keeping the first matching path/method preserves API stability
    and prevents old bodies from quietly shadowing the new ownership modules.
    """
    seen = set()
    deduped = []
    for route in app.router.routes:
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        key = (getattr(route, "path", ""), methods)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(route)
    app.router.routes = deduped


_dedupe_routes_keep_first()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
