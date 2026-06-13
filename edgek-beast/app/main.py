"""
EdgeK BEAST Gateway - Main Application Entry Point
Phase 9: Team and Enterprise Mode
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, Any
import logging

# Import adapters
from app.adapters.openai_adapter import openai_router
from app.adapters.anthropic_adapter import anthropic_router
from app.adapters.gemini_adapter import gemini_router
from app.adapters.huggingface_adapter import huggingface_router
from app.kernel.reason import reasoner
from app.kernel.crystallize import crystallizer
from app.kernel.runtime import runtime_governor
from app.kernel.skill_tree import skill_tree
from app.kernel.swarm import swarm_kernel
from app.kernel.enterprise import enterprise_manager
from app.kernel.benchmark import ComparativeBenchmark, MegaGauntlet
from app.kernel.ast_compressor import ASTCompressor
from app.kernel.isolation_forest import IsolationForest
from app.kernel.os_bypass import capabilities as os_bypass_capabilities, open_ring_probe, dpdk_probe, af_xdp_probe
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.deployment import DeploymentManager
from app.kernel.tool_integrations import RequiredIntegrationRegistry, ToolCallInterceptor
from app.kernel.ollama_scout import OllamaScout
from app.mcp.broker import MCPBroker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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
app.include_router(huggingface_router)
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# In-memory process counters; durable governance state lives in the kernel stores.
active_sessions: Dict[str, Any] = {}
request_count = 0

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
            "edgek_ollama_status": "/edgek/ollama/status",
            "edgek_ollama_packet": "/edgek/ollama/packet",
            "edgek_ollama_scout": "/edgek/ollama/scout",
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
            "edgek_providers_state": "/edgek/providers/state"
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
    providers = reasoner.policies.get("providers", {})
    return {
        "providers": {
            name: {
                "enabled": bool(config.get("enabled", False)),
                "base_url": config.get("base_url"),
                "default_model": config.get("default_model"),
                "backend": config.get("backend"),
            }
            for name, config in providers.items()
        },
        "credentials": {
            "huggingface": bool(os.environ.get("HF_TOKEN")),
            "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "litellm": bool(os.environ.get("LITELLM_API_KEY")),
            "tgi_hf_token": bool(os.environ.get("HF_TOKEN")),
        },
        "runtime_urls": {
            "hf_inference_base_url": os.environ.get("HF_INFERENCE_BASE_URL", "https://router.huggingface.co/v1"),
            "tgi_base_url": os.environ.get("TGI_BASE_URL", "http://127.0.0.1:3000"),
            "litellm_base_url": os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1"),
            "gemini_base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
        },
    }

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

@app.get("/edgek/tools/integrations")
async def edgek_tool_integrations():
    """Return readiness for required BEAST tool-call integrations."""
    return integration_registry.status()

@app.post("/edgek/tools/intercept")
async def edgek_tools_intercept(payload: Dict[str, Any]):
    """Intercept tool calls and return BEAST-compressed semantic payloads."""
    try:
        return tool_call_interceptor.intercept(
            payload,
            workspace_root=str(Path(__file__).resolve().parents[1]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
        context_limit=max(1, min(int(payload.get("context_limit", 6)), 20)),
        tool_limit=max(1, min(int(payload.get("tool_limit", 5)), 10)),
        include_postgres_schema=bool(payload.get("include_postgres_schema", True)),
        include_github_context=bool(payload.get("include_github_context", True)),
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
async def edgek_deploy_litellm_config(beast_base_url: str = "http://127.0.0.1:8005"):
    """Return a LiteLLM config generated from BEAST provider policy."""
    return deployment_manager.generate_litellm_config(beast_base_url=beast_base_url)

@app.get("/edgek/deploy/litellm-config.yaml")
async def edgek_deploy_litellm_config_yaml(beast_base_url: str = "http://127.0.0.1:8005"):
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
    beast_upstream: str = "127.0.0.1:8005",
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

@app.get("/edgek/workspace/semantic-context")
async def edgek_workspace_semantic_context(q: str, limit: int = 8, include_content: bool = True):
    """Return compact semantic context chunks for memory/forensics/RAG use."""
    return crystallizer.workspace_graph.semantic_context(
        query_text=q,
        limit=max(1, min(limit, 50)),
        include_content=include_content,
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

# Middleware to count requests
@app.middleware("http")
async def count_requests(request: Request, call_next):
    global request_count
    request_count += 1
    logger.info(f"Request #{request_count}: {request.method} {request.url}")
    response = await call_next(request)
    return response

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
