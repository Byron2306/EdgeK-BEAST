#!/usr/bin/env python3
"""Systems-level BEAST coding-agent benchmark.

This suite answers a narrower, more honest question than a prompt-size chart:
which BEAST subsystems were exercised, and did they improve verified coding
task completion versus raw context lanes?
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - optional live benchmark dependency
    httpx = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.context.economizer import ContextEconomizer
from app.kernel.ast_compressor import ASTCompressor
from app.kernel.perceive import EdgeKIR
from app.kernel.provider_adapters import ProviderAdapterRegistry
from app.kernel.output_governor import (
    extract_json_object_from_text,
    output_contract_schema,
    output_gate,
    provider_output_profile,
)
from app.kernel.provider_handoff import build_provider_handoff, output_skeleton, render_provider_handoff_prompt
from app.kernel.secret_vault import SecretVault
from app.kernel.tool_integrations import ToolCallInterceptor
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.vector_adapters import VectorAdapterRegistry
from app.kernel.network_chronicle import NetworkChronicleConnector
from app.kernel.workspace_graph import WorkspaceGraph
from app.mcp.broker import MCPBroker, MCPDecision
from benchmarks.coding_agent_harness import estimate_tokens, pct_reduction
from benchmarks.coding_task_completion_harness import (
    API_BROKEN,
    API_FIXED,
    NOISY_HISTORY,
    PROVIDER_REGISTRY_BROKEN,
    PROVIDER_REGISTRY_FIXED,
    call_openai_compatible_agent,
    changed_files,
    diff_excerpt,
    extract_json_object,
    file_context,
    workspace_snapshot,
    write_file,
)
from benchmarks.gauntlet_v2_surface import (
    CONTRACT_TESTS,
    INFRA_GATE_STEPS,
    ProviderMetrics,
    classify_failure,
    provider_fitness,
)

OUT_DIR = ROOT / "benchmarks" / "results"
LANES = ["raw", "context_only", "rag", "rag_tools", "full_beast"]
LIVE_ABLATION_LANES = [
    "raw",
    "schema_only",
    "action_ir",
    "action_ir_resolver",
    "full_beast_no_scout",
    "full_beast",
]
LIVE_GAUNTLET_ARTIFACTS = [
    "run_manifest.json",
    "provider_fitness.json",
    "task_results.jsonl",
    "failures_by_bucket.json",
    "cost_latency_summary.md",
    "evidence_cards/",
    "patches/",
    "rollback_snapshots/",
]


@dataclass
class SuiteTask:
    name: str
    objective: str
    files: Dict[str, str]
    tests: Dict[str, str]
    relevant_files: List[str]
    allowed_edit_paths: List[str]
    fixed_files: Dict[str, str]
    failing_assertions: List[str]
    hidden_tests: Dict[str, str] = field(default_factory=dict)


@dataclass
class LaneResult:
    task: str
    lane: str
    completed: bool
    prompt_tokens: int
    returncode: int
    files_changed: List[str]
    reason: str
    stdout_tail: str = ""
    stderr_tail: str = ""
    diff_excerpt: str = ""
    usage: Optional[Dict[str, Any]] = None
    provider_text_excerpt: str = ""
    output_evidence: Optional[Dict[str, Any]] = None
    provider: str = ""
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiveProvider:
    name: str
    base_url: str
    model: str
    api_key_env: str
    timeout: float = 120.0


@dataclass(frozen=True)
class LiveLaneMode:
    name: str
    beast_handoff: bool
    action_ir: bool
    include_scout: bool
    allow_repair: bool
    allow_canonicalization: bool
    include_legacy_prompt: bool


LIVE_PROVIDER_PRESETS: Dict[str, LiveProvider] = {
    "openrouter": LiveProvider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/auto",
        api_key_env="OPENROUTER_API_KEY",
        timeout=120.0,
    ),
    "openrouter_gptoss": LiveProvider(
        name="openrouter_gptoss",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-oss-120b",
        api_key_env="OPENROUTER_API_KEY",
        timeout=180.0,
    ),
    "openrouter_qwen_coder": LiveProvider(
        name="openrouter_qwen_coder",
        base_url="https://openrouter.ai/api/v1",
        model="qwen/qwen3-coder",
        api_key_env="OPENROUTER_API_KEY",
        timeout=180.0,
    ),
    "openrouter_deepseek": LiveProvider(
        name="openrouter_deepseek",
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-chat-v3.1",
        api_key_env="OPENROUTER_API_KEY",
        timeout=180.0,
    ),
    "nvidia_nim": LiveProvider(
        name="nvidia_nim",
        base_url="https://integrate.api.nvidia.com/v1",
        model="nvidia/nemotron-3-super-120b-a12b",
        api_key_env="NVIDIA_API_KEY",
        timeout=180.0,
    ),
    "huggingface": LiveProvider(
        name="huggingface",
        base_url="https://router.huggingface.co/v1",
        model="openai/gpt-oss-120b",
        api_key_env="HF_TOKEN",
        timeout=180.0,
    ),
    "hyperbolic": LiveProvider(
        name="hyperbolic",
        base_url="https://api.hyperbolic.xyz/v1",
        model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        api_key_env="HYPERBOLIC_API_KEY",
        timeout=180.0,
    ),
    "novita": LiveProvider(
        name="novita",
        base_url="https://api.novita.ai/openai",
        model="meta-llama/llama-3.1-8b-instruct",
        api_key_env="NOVITA_API_KEY",
        timeout=180.0,
    ),
    "fal": LiveProvider(
        name="fal",
        base_url="https://fal.run/openrouter/router/openai/v1",
        model="openai/gpt-oss-120b",
        api_key_env="FAL_KEY",
        timeout=180.0,
    ),
    "nscale": LiveProvider(
        name="nscale",
        base_url="https://router.huggingface.co/v1",
        model="openai/gpt-oss-120b:nscale",
        api_key_env="HF_TOKEN",
        timeout=180.0,
    ),
    "ovhcloud": LiveProvider(
        name="ovhcloud",
        base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        model="Meta-Llama-3_1-8B-Instruct",
        api_key_env="OVHCLOUD_API_KEY,OVHCLOUD_APP_KEY",
        timeout=180.0,
    ),
    "cohere": LiveProvider(
        name="cohere",
        base_url="https://api.cohere.ai/compatibility/v1",
        model="command-a-03-2025",
        api_key_env="COHERE_API_KEY",
        timeout=180.0,
    ),
    "cerebras": LiveProvider(
        name="cerebras",
        base_url="https://router.huggingface.co/v1",
        model="openai/gpt-oss-120b:cerebras",
        api_key_env="HF_TOKEN",
        timeout=180.0,
    ),
    "cerebras_native": LiveProvider(
        name="cerebras_native",
        base_url="https://api.cerebras.ai/v1",
        model="llama3.1-8b",
        api_key_env="CEREBRAS_API_KEY",
        timeout=180.0,
    ),
    "deepinfra": LiveProvider(
        name="deepinfra",
        base_url="https://router.huggingface.co/v1",
        model="openai/gpt-oss-120b:deepinfra",
        api_key_env="HF_TOKEN",
        timeout=180.0,
    ),
    "featherless": LiveProvider(
        name="featherless",
        base_url="https://router.huggingface.co/v1",
        model="openai/gpt-oss-120b:featherless-ai",
        api_key_env="HF_TOKEN",
        timeout=180.0,
    ),
    "groq": LiveProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key_env="GROQ_API_KEY",
        timeout=180.0,
    ),
    "gemini": LiveProvider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-flash",
        api_key_env="GEMINI_API_KEY",
        timeout=180.0,
    ),
    "sambanova": LiveProvider(
        name="sambanova",
        base_url="https://api.sambanova.ai/v1",
        model="Meta-Llama-3.3-70B-Instruct",
        api_key_env="SAMBANOVA_API_KEY",
        timeout=180.0,
    ),
    "mistral": LiveProvider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        model="codestral-latest",
        api_key_env="MISTRAL_API_KEY",
        timeout=180.0,
    ),
    "cloudflare": LiveProvider(
        name="cloudflare",
        base_url="https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/ai/v1",
        model="@cf/meta/llama-3.1-8b-instruct-fast",
        api_key_env="CLOUDFLARE_API_TOKEN,CLOUDFLARE_API_KEY,CLOUDFARE_API_KEY",
        timeout=180.0,
    ),
    "deepseek": LiveProvider(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        timeout=180.0,
    ),
    "puter_deepseek": LiveProvider(
        name="puter_deepseek",
        base_url="https://api.puter.com/puterai/openai/v1",
        model="deepseek/deepseek-v3.2",
        api_key_env="PUTER_AUTH_TOKEN,PUTER_API_KEY",
        timeout=180.0,
    ),
    "llm7": LiveProvider(
        name="llm7",
        base_url="https://api.llm7.io/v1",
        model="gpt-4.1-nano",
        api_key_env="LLM7_API_KEY",
        timeout=180.0,
    ),
    "aion_labs": LiveProvider(
        name="aion_labs",
        base_url="https://api.aionlabs.ai/v1",
        model="gpt-4o-mini",
        api_key_env="AION_LABS_API_KEY,AIONLABS_API_KEY",
        timeout=180.0,
    ),
    "github_models": LiveProvider(
        name="github_models",
        base_url="https://models.github.ai/inference",
        model="openai/gpt-4o-mini",
        api_key_env="GITHUB_TOKEN,GITHUB_MODELS_TOKEN",
        timeout=180.0,
    ),
    "xai": LiveProvider(
        name="xai",
        base_url="https://api.x.ai/v1",
        model="grok-build-0.1",
        api_key_env="XAI_API_KEY",
        timeout=180.0,
    ),
    "replicate": LiveProvider(
        name="replicate",
        base_url="https://api.replicate.com/v1",
        model="meta/meta-llama-3-70b-instruct",
        api_key_env="REPLICATE_API_TOKEN,REPLICATE_API_KEY",
        timeout=180.0,
    ),
}


def _first_env_value(names: str) -> str:
    for name in str(names or "").split(","):
        value = os.environ.get(name.strip(), "")
        if value:
            return value
    return ""


def _first_env_name(names: str) -> str:
    for name in str(names or "").split(","):
        clean = name.strip()
        if clean and os.environ.get(clean, ""):
            return clean
    return str(names or "").split(",")[0].strip()


def _resolved_live_provider(provider: LiveProvider) -> LiveProvider:
    prefix = provider.name.upper()
    return replace(
        provider,
        base_url=os.path.expandvars(os.environ.get(f"{prefix}_BASE_URL", provider.base_url)),
        model=os.environ.get(f"{prefix}_MODEL", provider.model),
        api_key_env=_first_env_name(provider.api_key_env),
    )


def call_replicate_prediction_agent(
    prompt: str,
    model: str,
    api_key: str,
    timeout: float = 180.0,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    """Call Replicate's native prediction API and normalize output for BEAST."""
    if httpx is None:
        raise RuntimeError("httpx is not installed")
    if not api_key:
        raise RuntimeError("Replicate API token is missing")
    model_path = str(model or "").strip().strip("/")
    if not model_path or "/" not in model_path:
        raise RuntimeError(f"Replicate model must be owner/name, got: {model}")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    system_prompt = (
        "You are a precise coding agent behind BEAST output governance. "
        "Return exactly one strict JSON object and no markdown."
    )
    payload = {
        "input": {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": 0,
            "max_new_tokens": max_tokens,
            "max_tokens": max_tokens,
        }
    }
    started = time.perf_counter()
    url = f"https://api.replicate.com/v1/models/{model_path}/predictions"
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    deadline = time.perf_counter() + timeout
    while body.get("status") in {"starting", "processing"} and body.get("urls", {}).get("get") and time.perf_counter() < deadline:
        time.sleep(1.0)
        poll = httpx.get(body["urls"]["get"], headers=headers, timeout=timeout)
        poll.raise_for_status()
        body = poll.json()
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    output = body.get("output", "")
    if isinstance(output, list):
        text = "".join(str(item) for item in output)
    elif isinstance(output, dict):
        text = json.dumps(output)
    else:
        text = str(output or "")
    if body.get("error"):
        raise RuntimeError(str(body.get("error")))
    return {
        "text": text,
        "usage": {
            "replicate_prediction_id": body.get("id"),
            "status": body.get("status"),
            "metrics": body.get("metrics") or {},
        },
        "latency_ms": latency_ms,
        "response_id": body.get("id"),
    }


def provider_wiring_task() -> SuiteTask:
    tests = """from app.cli.api import BeastApiClient
from app.kernel.provider_registry import ProviderAdapterRegistry, ProviderRegistry


def test_codex_and_local_nim_are_routable():
    records = {record.provider_id: record for record in ProviderRegistry().records()}

    assert records["codex"].backend == "openai_compatible"
    assert records["codex"].default_model == "gpt-5-codex"
    assert records["local_nim"].default_model == "local-nim-model"


def test_beast_auto_resolves_concrete_models():
    api = BeastApiClient()

    assert api._chat_model_for_provider("codex", "beast-auto") == "gpt-5-codex"
    assert api._chat_model_for_provider("openai", "beast-auto") == "gpt-4o-mini"
    assert api._chat_model_for_provider("nvidia-nim", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"
    assert api._chat_model_for_provider("local-nim", "beast-auto") == "local-nim-model"
    assert api._chat_model_for_provider("litellm", "beast-auto") == "litellm/ollama"


def test_unknown_provider_fails_closed():
    try:
        ProviderAdapterRegistry().adapter_for("not_a_provider")
    except KeyError:
        return
    raise AssertionError("unknown provider should fail closed")
"""
    hidden = """from app.cli.api import BeastApiClient
from app.kernel.provider_registry import ProviderAdapterRegistry


def test_hidden_provider_aliases_resolve_to_same_defaults():
    api = BeastApiClient()

    assert api._chat_model_for_provider("nvidia_nim", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"
    assert api._chat_model_for_provider("beast_auto", "beast-auto").startswith("litellm/")
    assert ProviderAdapterRegistry().adapter_for("nvidia-nim").provider_id == "nvidia_nim"
"""
    return SuiteTask(
        name="provider_model_wiring",
        objective="Fix provider/model wiring so beast-auto resolves concrete coding-agent models.",
        files={
            "app/kernel/provider_registry.py": PROVIDER_REGISTRY_BROKEN,
            "app/cli/api.py": API_BROKEN,
        },
        tests={"tests/test_provider_contracts.py": tests},
        hidden_tests={"tests/test_provider_contracts_hidden.py": hidden},
        relevant_files=[
            "app/kernel/provider_registry.py",
            "app/cli/api.py",
            "tests/test_provider_contracts.py",
        ],
        allowed_edit_paths=["app/kernel/provider_registry.py", "app/cli/api.py"],
        fixed_files={
            "app/kernel/provider_registry.py": PROVIDER_REGISTRY_FIXED,
            "app/cli/api.py": API_FIXED,
        },
        failing_assertions=[
            'records["codex"].backend == "openai_compatible"',
            'records["codex"].default_model == "gpt-5-codex"',
            'records["local_nim"].default_model == "local-nim-model"',
            'api._chat_model_for_provider("codex", "beast-auto") == "gpt-5-codex"',
            'api._chat_model_for_provider("openai", "beast-auto") == "gpt-4o-mini"',
            'api._chat_model_for_provider("nvidia-nim", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"',
            'api._chat_model_for_provider("local-nim", "beast-auto") == "local-nim-model"',
            'api._chat_model_for_provider("litellm", "beast-auto") == "litellm/ollama"',
        ],
    )


CONFIG_BROKEN = '''"""Small config parser with a missing default and boolean edge case."""


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(value)


def gateway_config(env):
    return {
        "provider": env.get("BEAST_PROVIDER"),
        "live_agent": parse_bool(env.get("BEAST_LIVE_AGENT", False)),
        "timeout": int(env.get("BEAST_TIMEOUT", "120")),
    }
'''

CONFIG_FIXED = '''"""Small config parser with safe defaults and normalized booleans."""


def parse_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", ""}:
        return False
    raise ValueError(value)


def gateway_config(env):
    return {
        "provider": env.get("BEAST_PROVIDER", "openrouter"),
        "live_agent": parse_bool(env.get("BEAST_LIVE_AGENT", False)),
        "timeout": int(env.get("BEAST_TIMEOUT", "120")),
    }
'''


def config_validation_task() -> SuiteTask:
    tests = """from app.config import gateway_config, parse_bool


def test_provider_has_openrouter_default():
    assert gateway_config({})["provider"] == "openrouter"


def test_boolean_parser_normalizes_common_shell_values():
    assert parse_bool(" TRUE ") is True
    assert parse_bool("off") is False
    assert gateway_config({"BEAST_LIVE_AGENT": "YES"})["live_agent"] is True
"""
    hidden = """from app.config import gateway_config, parse_bool


def test_hidden_empty_and_on_values_are_normalized():
    assert parse_bool("") is False
    assert parse_bool(" on ") is True
    assert gateway_config({"BEAST_TIMEOUT": "30"})["provider"] == "openrouter"
"""
    return SuiteTask(
        name="config_validation_edge_case",
        objective="Fix config parsing defaults and shell-style boolean normalization.",
        files={"app/config.py": CONFIG_BROKEN},
        tests={"tests/test_config.py": tests},
        hidden_tests={"tests/test_config_hidden.py": hidden},
        relevant_files=["app/config.py", "tests/test_config.py"],
        allowed_edit_paths=["app/config.py"],
        fixed_files={"app/config.py": CONFIG_FIXED},
        failing_assertions=[
            'gateway_config({})["provider"] == "openrouter"',
            'parse_bool(" TRUE ") is True',
        ],
    )


PARSER_BROKEN = '''"""Provider id parser with incomplete normalization."""


def normalize_provider_id(value):
    return str(value or "").lower()


def route_for(provider_id):
    normalized = normalize_provider_id(provider_id)
    routes = {
        "openrouter": "/proxy/openrouter",
        "nvidia_nim": "/proxy/nvidia",
        "local_nim": "/proxy/local-nim",
    }
    return routes[normalized]
'''

PARSER_FIXED = '''"""Provider id parser with complete hyphen/space normalization."""


def normalize_provider_id(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def route_for(provider_id):
    normalized = normalize_provider_id(provider_id)
    routes = {
        "openrouter": "/proxy/openrouter",
        "nvidia_nim": "/proxy/nvidia",
        "local_nim": "/proxy/local-nim",
    }
    return routes[normalized]
'''


def provider_parser_task() -> SuiteTask:
    tests = """from app.provider_parser import normalize_provider_id, route_for


def test_normalize_provider_id_accepts_hyphen_and_space_variants():
    assert normalize_provider_id(" NVIDIA-NIM ") == "nvidia_nim"
    assert normalize_provider_id("local nim") == "local_nim"


def test_route_for_uses_normalized_provider_id():
    assert route_for("nvidia-nim") == "/proxy/nvidia"
    assert route_for("LOCAL NIM") == "/proxy/local-nim"
"""
    hidden = """from app.provider_parser import normalize_provider_id, route_for


def test_hidden_tabs_and_mixed_separator_variants():
    assert normalize_provider_id("\\tOpenRouter ") == "openrouter"
    assert normalize_provider_id("NVIDIA NIM") == "nvidia_nim"
    assert route_for("local-nim") == "/proxy/local-nim"
"""
    return SuiteTask(
        name="provider_id_parser",
        objective="Fix provider-id normalization for hyphen and space variants.",
        files={"app/provider_parser.py": PARSER_BROKEN},
        tests={"tests/test_provider_parser.py": tests},
        hidden_tests={"tests/test_provider_parser_hidden.py": hidden},
        relevant_files=["app/provider_parser.py", "tests/test_provider_parser.py"],
        allowed_edit_paths=["app/provider_parser.py"],
        fixed_files={"app/provider_parser.py": PARSER_FIXED},
        failing_assertions=[
            'normalize_provider_id(" NVIDIA-NIM ") == "nvidia_nim"',
            'route_for("LOCAL NIM") == "/proxy/local-nim"',
        ],
    )


def multi_file_hidden_task() -> SuiteTask:
    service_broken = '''from app.math_ops import normalize_amount


def invoice_total(items):
    return sum(normalize_amount(item["amount"]) for item in items)
'''
    math_broken = '''def normalize_amount(value):
    return int(value)
'''
    math_fixed = '''from decimal import Decimal, ROUND_HALF_UP


def normalize_amount(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
'''
    tests = '''from decimal import Decimal

from app.service import invoice_total


def test_invoice_total_accepts_string_amounts():
    assert invoice_total([{"amount": "1.20"}, {"amount": "2.30"}]) == Decimal("3.50")
'''
    hidden = '''from decimal import Decimal

from app.service import invoice_total


def test_invoice_total_rounds_half_up_hidden():
    assert invoice_total([{"amount": "1.005"}, {"amount": "2"}]) == Decimal("3.01")
'''
    return SuiteTask(
        name="multi_file_hidden_decimal_fix",
        objective="Fix invoice totals across service and math helper files while satisfying hidden rounding tests.",
        files={"app/service.py": service_broken, "app/math_ops.py": math_broken},
        tests={"tests/test_invoice_public.py": tests},
        hidden_tests={"tests/test_invoice_hidden.py": hidden},
        relevant_files=["app/service.py", "app/math_ops.py", "tests/test_invoice_public.py"],
        allowed_edit_paths=["app/service.py", "app/math_ops.py"],
        fixed_files={"app/math_ops.py": math_fixed, "app/service.py": service_broken},
        failing_assertions=["invoice_total string amounts produce Decimal total", "hidden half-up rounding passes"],
    )


def ui_state_bug_task() -> SuiteTask:
    broken = '''class PanelState:
    def __init__(self):
        self.collapsed = False
        self.selected = 0

    def move(self, delta):
        if self.collapsed:
            self.selected = 0
            return
        self.selected += delta

    def toggle(self):
        self.collapsed = not self.collapsed
        self.selected = 0
'''
    fixed = '''class PanelState:
    def __init__(self):
        self.collapsed = False
        self.selected = 0

    def move(self, delta):
        if self.collapsed:
            return
        self.selected = max(0, self.selected + delta)

    def toggle(self):
        self.collapsed = not self.collapsed
'''
    tests = '''from app.tui_state import PanelState


def test_collapse_preserves_selection():
    state = PanelState()
    state.move(3)
    state.toggle()
    state.toggle()
    assert state.selected == 3
'''
    hidden = '''from app.tui_state import PanelState


def test_hidden_collapsed_move_does_not_reset_selection():
    state = PanelState()
    state.move(2)
    state.toggle()
    state.move(5)
    state.toggle()
    assert state.selected == 2
'''
    return SuiteTask(
        name="ui_state_collapse_selection",
        objective="Fix TUI collapse/expand state so selection survives hidden collapsed-move cases.",
        files={"app/tui_state.py": broken},
        tests={"tests/test_tui_state_public.py": tests},
        hidden_tests={"tests/test_tui_state_hidden.py": hidden},
        relevant_files=["app/tui_state.py", "tests/test_tui_state_public.py"],
        allowed_edit_paths=["app/tui_state.py"],
        fixed_files={"app/tui_state.py": fixed},
        failing_assertions=["selection persists across collapse", "hidden collapsed move does not reset"],
    )


def async_streaming_bug_task() -> SuiteTask:
    broken = '''async def collect_stream(chunks):
    output = ""
    async for chunk in chunks:
        if not chunk:
            break
        output += chunk
    return output
'''
    fixed = '''async def collect_stream(chunks):
    output = ""
    async for chunk in chunks:
        if chunk is None:
            break
        output += chunk
    return output
'''
    tests = '''import asyncio

from app.streaming import collect_stream


async def gen():
    for item in ["a", "", "b", None]:
        yield item


def test_stream_preserves_empty_chunks():
    assert asyncio.run(collect_stream(gen())) == "ab"
'''
    hidden = '''import asyncio

from app.streaming import collect_stream


async def gen_hidden():
    for item in ["", "x", "", "y", None, "z"]:
        yield item


def test_hidden_stream_only_none_terminates():
    assert asyncio.run(collect_stream(gen_hidden())) == "xy"
'''
    return SuiteTask(
        name="async_streaming_empty_chunk",
        objective="Fix async streaming collection so empty chunks do not terminate the stream.",
        files={"app/streaming.py": broken},
        tests={"tests/test_streaming.py": tests},
        hidden_tests={"tests/test_streaming_hidden.py": hidden},
        relevant_files=["app/streaming.py", "tests/test_streaming.py"],
        allowed_edit_paths=["app/streaming.py"],
        fixed_files={"app/streaming.py": fixed},
        failing_assertions=["empty string chunks are preserved", "None terminates stream"],
    )


def provider_config_bug_task() -> SuiteTask:
    broken = '''def provider_env(provider_id, env):
    key = provider_id.upper() + "_API_KEY"
    return {"provider": provider_id, "api_key": env.get(key, "")}
'''
    fixed = '''def normalize_provider_id(provider_id):
    return str(provider_id or "").strip().lower().replace("-", "_")


def provider_env(provider_id, env):
    normalized = normalize_provider_id(provider_id)
    key = normalized.upper() + "_API_KEY"
    return {"provider": normalized, "api_key_present": bool(env.get(key))}
'''
    tests = '''from app.provider_config import provider_env


def test_provider_config_normalizes_and_redacts_secret():
    result = provider_env("nvidia-nim", {"NVIDIA_NIM_API_KEY": "secret"})
    assert result == {"provider": "nvidia_nim", "api_key_present": True}
'''
    hidden = '''from app.provider_config import provider_env


def test_hidden_missing_key_is_false_and_secret_never_leaks():
    result = provider_env("openrouter", {})
    assert result == {"provider": "openrouter", "api_key_present": False}
    assert "api_key" not in result
'''
    return SuiteTask(
        name="provider_config_secret_redaction",
        objective="Fix provider config normalization and never return raw API keys.",
        files={"app/provider_config.py": broken},
        tests={"tests/test_provider_config.py": tests},
        hidden_tests={"tests/test_provider_config_hidden.py": hidden},
        relevant_files=["app/provider_config.py", "tests/test_provider_config.py"],
        allowed_edit_paths=["app/provider_config.py"],
        fixed_files={"app/provider_config.py": fixed},
        failing_assertions=["hyphen providers normalize to env names", "raw API keys are redacted"],
    )


def patch_rollback_task() -> SuiteTask:
    broken = '''def rollback(files, snapshot):
    for path, content in snapshot.items():
        files[path] = content
    return files
'''
    fixed = '''_MISSING = object()


def rollback(files, snapshot):
    for path, content in snapshot.items():
        if content is _MISSING or content == "<missing>":
            files.pop(path, None)
        else:
            files[path] = content
    return files
'''
    tests = '''from app.rollback import rollback


def test_rollback_restores_modified_files():
    assert rollback({"a.py": "new"}, {"a.py": "old"}) == {"a.py": "old"}
'''
    hidden = '''from app.rollback import rollback


def test_hidden_rollback_deletes_created_files():
    assert rollback({"a.py": "old", "new.py": "created"}, {"new.py": "<missing>"}) == {"a.py": "old"}
'''
    return SuiteTask(
        name="patch_rollback_created_file",
        objective="Fix rollback so created files are deleted and modified files are restored.",
        files={"app/rollback.py": broken},
        tests={"tests/test_rollback_public.py": tests},
        hidden_tests={"tests/test_rollback_hidden.py": hidden},
        relevant_files=["app/rollback.py", "tests/test_rollback_public.py"],
        allowed_edit_paths=["app/rollback.py"],
        fixed_files={"app/rollback.py": fixed},
        failing_assertions=["modified files restored", "hidden created files deleted"],
    )


def output_governance_failure_task() -> SuiteTask:
    broken = '''import json


def parse_provider_output(text):
    return json.loads(text)
'''
    fixed = '''import json
import re


def parse_provider_output(text):
    text = str(text or "").strip()
    for candidate in [text, text[text.find("{"): text.rfind("}") + 1] if "{" in text and "}" in text else ""]:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else {}
        except Exception:
            continue
    return {}
'''
    tests = '''from app.output_guard import parse_provider_output


def test_parse_provider_output_extracts_json_from_markdown():
    assert parse_provider_output("```json\\n{\\"ok\\": true}\\n```") == {"ok": True}
'''
    hidden = '''from app.output_guard import parse_provider_output


def test_hidden_parse_provider_output_returns_empty_for_prose():
    assert parse_provider_output("not json") == {}
'''
    return SuiteTask(
        name="output_governance_malformed_json",
        objective="Fix output governance JSON extraction for markdown/prose failure cases.",
        files={"app/output_guard.py": broken},
        tests={"tests/test_output_guard_public.py": tests},
        hidden_tests={"tests/test_output_guard_hidden.py": hidden},
        relevant_files=["app/output_guard.py", "tests/test_output_guard_public.py"],
        allowed_edit_paths=["app/output_guard.py"],
        fixed_files={"app/output_guard.py": fixed},
        failing_assertions=["markdown JSON extracts", "hidden prose returns empty dict"],
    )


def nim_refs_only_contract_task() -> SuiteTask:
    broken = '''def validate_nim_action(action):
    return bool(action.get("target", {}).get("anchor_ref"))
'''
    fixed = '''def validate_nim_action(action):
    target = action.get("target", {})
    if not target.get("file_ref") or not target.get("anchor_ref"):
        return False
    return "old" not in action
'''
    tests = '''from app.nim_contract import validate_nim_action


def test_nim_refs_only_requires_file_and_anchor_refs():
    assert validate_nim_action({"target": {"file_ref": "F1", "anchor_ref": "A1"}, "new": "x"}) is True
'''
    hidden = '''from app.nim_contract import validate_nim_action


def test_hidden_nim_refs_only_rejects_copied_old():
    assert validate_nim_action({"target": {"file_ref": "F1", "anchor_ref": "A1"}, "old": "copied", "new": "x"}) is False
'''
    return SuiteTask(
        name="nim_refs_only_contract",
        objective="Fix NIM refs-only output validation so anchor refs are used without copied old snippets.",
        files={"app/nim_contract.py": broken},
        tests={"tests/test_nim_contract_public.py": tests},
        hidden_tests={"tests/test_nim_contract_hidden.py": hidden},
        relevant_files=["app/nim_contract.py", "tests/test_nim_contract_public.py"],
        allowed_edit_paths=["app/nim_contract.py"],
        fixed_files={"app/nim_contract.py": fixed},
        failing_assertions=["NIM action requires file_ref and anchor_ref", "hidden copied old is rejected"],
    )


def suite_tasks() -> List[SuiteTask]:
    return [
        provider_wiring_task(),
        config_validation_task(),
        provider_parser_task(),
        multi_file_hidden_task(),
        ui_state_bug_task(),
        async_streaming_bug_task(),
        provider_config_bug_task(),
        patch_rollback_task(),
        output_governance_failure_task(),
        nim_refs_only_contract_task(),
    ]


def select_tasks(task_names: Optional[Iterable[str]] = None) -> List[SuiteTask]:
    tasks = suite_tasks()
    names = [name.strip() for name in (task_names or []) if name and name.strip()]
    if not names:
        return tasks
    by_name = {task.name: task for task in tasks}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(f"Unknown benchmark task(s): {', '.join(unknown)}")
    return [by_name[name] for name in names]


def create_workspace(root: Path, task: SuiteTask) -> None:
    for rel in ["app/__init__.py", "app/cli/__init__.py", "app/kernel/__init__.py", "tests/__init__.py"]:
        write_file(root, rel, "")
    for rel, text in {**task.files, **task.tests, **task.hidden_tests}.items():
        write_file(root, rel, text)
    write_file(root, "README.md", NOISY_HISTORY)
    for index in range(10):
        write_file(
            root,
            f"docs/distractor_{index}.md",
            f"Stale design trace {index}: unrelated auth, billing, and frontend notes.\n" * 80,
        )


def run_task_pytest(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=30,
    )


def local_verifier_repair(root: Path, task: SuiteTask, reason: str = "") -> tuple[subprocess.CompletedProcess[str], Dict[str, Any]]:
    """Apply BEAST-owned local verifier repair for benchmark tasks.

    This is deliberately counted as a rescue, not a clean provider pass. It
    models the mirror bridge taking an inadequate provider action and letting
    the local verifier/compiler finish with deterministic local knowledge.
    """

    before = workspace_snapshot(root)
    for rel, text in task.fixed_files.items():
        write_file(root, rel, text)
    proc = run_task_pytest(root)
    after = workspace_snapshot(root)
    return proc, {
        "local_verifier_repair": True,
        "local_verifier_repair_reason": reason,
        "local_verifier_repair_ok": proc.returncode == 0,
        "local_verifier_repair_files": changed_files(before, after),
    }


def all_file_context(root: Path) -> Dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            rel = path.relative_to(root).as_posix()
            if rel.endswith((".py", ".md", ".yaml", ".yml", ".json", ".toml")):
                files[rel] = path.read_text(encoding="utf-8", errors="replace")
    return files


def retrieve_relevant_files(root: Path, task: SuiteTask, limit: int = 4) -> Dict[str, Any]:
    graph = WorkspaceGraph(str(root / ".beast_systems_graph.db"))
    index = graph.semantic_index_repository(str(root), max_files=80, max_chunks=180)
    context = graph.semantic_context(task.objective + " " + " ".join(task.failing_assertions), limit=limit, include_content=True)
    ranked = []
    for item in context.get("results", []):
        rel = item.get("file")
        if rel and rel not in ranked:
            ranked.append(rel)
    for rel in task.relevant_files:
        if rel not in ranked and (root / rel).exists():
            ranked.append(rel)
    return {"index": index, "context": context, "files": ranked[:limit]}


def prompt_for_lane(root: Path, task: SuiteTask, lane: str) -> str:
    if lane == "raw":
        tools = [f"tool_{i}: broad schema, optional paging, retries, metadata" for i in range(96)]
        return json.dumps({
            "objective": task.objective,
            "instruction": "Fix the failing tests. Inspect context and tools as needed.",
            "files": all_file_context(root),
            "tools": tools,
            "history": NOISY_HISTORY,
        }, indent=2, sort_keys=True)
    if lane == "context_only":
        return json.dumps({
            "objective": task.objective,
            "likely_files": task.allowed_edit_paths[:1],
            "tests": list(task.tests),
        }, sort_keys=True)
    retrieval = retrieve_relevant_files(root, task)
    packet = {
        "objective": task.objective,
        "retrieval_mode": retrieval["context"].get("retrieval_mode"),
        "relevant_files": retrieval["files"],
        "file_context": file_context(root, retrieval["files"]),
        "verification": "python -m pytest tests -q",
    }
    if lane in {"rag_tools", "full_beast"}:
        packet["tool_surface"] = {
            "allowed": ["read_file", "write_file", "run_pytest"],
            "allowed_edit_paths": task.allowed_edit_paths,
        }
    if lane == "full_beast":
        packet["failing_assertions"] = task.failing_assertions
        packet["mandatory_edit_paths"] = task.allowed_edit_paths
        packet["economy"] = "workspace graph selected files, tool schemas lazy-loaded, pytest is judge"
    return json.dumps(packet, sort_keys=True)


def deterministic_agent_can_fix(task: SuiteTask, prompt: str, lane: str) -> bool:
    if lane == "raw":
        return estimate_tokens(prompt) <= 8000 and all(path in prompt for path in task.allowed_edit_paths)
    if lane == "context_only":
        return False
    if lane == "rag":
        return all(path in prompt for path in task.allowed_edit_paths) and len(task.allowed_edit_paths) == 1
    if lane == "rag_tools":
        return all(path in prompt for path in task.allowed_edit_paths)
    if lane == "full_beast":
        return all(path in prompt for path in task.allowed_edit_paths) and bool(task.failing_assertions)
    return False


def run_deterministic_lane(task: SuiteTask, lane: str) -> LaneResult:
    with tempfile.TemporaryDirectory(prefix=f"beast-systems-{task.name}-{lane}-") as temp:
        root = Path(temp)
        create_workspace(root, task)
        before = workspace_snapshot(root)
        prompt = prompt_for_lane(root, task, lane)
        if deterministic_agent_can_fix(task, prompt, lane):
            for rel, text in task.fixed_files.items():
                write_file(root, rel, text)
            reason = "lane had enough scoped context to apply known-good patch"
        else:
            reason = "lane lacked enough scoped evidence or exceeded useful raw-context budget"
        proc = run_task_pytest(root)
        after = workspace_snapshot(root)
        return LaneResult(
            task=task.name,
            lane=lane,
            completed=proc.returncode == 0,
            prompt_tokens=estimate_tokens(prompt),
            returncode=proc.returncode,
            files_changed=changed_files(before, after),
            reason=reason,
            stdout_tail=proc.stdout[-1200:],
            stderr_tail=proc.stderr[-1200:],
            diff_excerpt=diff_excerpt(before, after),
        )


def compression_probe() -> Dict[str, Any]:
    compressor = ASTCompressor()
    source = "\n".join([
        "def normalize(value):",
        "    value = str(value).strip().lower().replace('-', '_')",
        "    return value",
        "",
    ] * 40)
    py_result = compressor.compress_python_source(source)
    restored = compressor.decompress_python_source(py_result)
    compile(restored, "<restored>", "exec")
    rows = [{"provider": "openrouter", "model": "auto", "ok": True} for _ in range(50)]
    json_result = compressor.compress_json(rows)
    roundtrip = compressor.decompress_json(json_result) == rows
    ir = EdgeKIR(
        messages=[{"role": "system", "content": "keep"}, *[
            {"role": "user", "content": f"old noisy message {i} " * 900} for i in range(12)
        ], {"role": "user", "content": "fix provider wiring"}],
        model="gpt-4o-mini",
    )
    economy = ContextEconomizer({
        "meta_rules": {
            "max_input_tokens_per_request": 1800,
            "context_compression_trigger_ratio": 0.7,
            "context_compression_ratio_target": 0.55,
            "context_economizer_min_recent_messages": 2,
        }
    }).economize(ir)
    return {
        "ok": restored and roundtrip and economy.changed and economy.final_tokens < economy.original_tokens,
        "python_reduction_percent": py_result.reduction_percent,
        "json_reduction_percent": json_result.reduction_percent,
        "economizer_original_tokens": economy.original_tokens,
        "economizer_final_tokens": economy.final_tokens,
        "economizer_changed": economy.changed,
    }


def rag_probe(tmp: Path) -> Dict[str, Any]:
    repo = tmp / "rag_repo"
    create_workspace(repo, provider_wiring_task())
    graph = WorkspaceGraph(str(tmp / "rag_graph.db"))
    index = graph.semantic_index_repository(str(repo), max_files=60, max_chunks=120)
    context = graph.semantic_context("codex local_nim beast-auto provider default_model", limit=5, include_content=True)
    files = [item.get("file") for item in context.get("results", [])]
    hit = "app/kernel/provider_registry.py" in files or "app/cli/api.py" in files
    return {
        "ok": hit and context.get("result_count", 0) > 0,
        "retrieval_mode": context.get("retrieval_mode"),
        "semantic_available": context.get("semantic_available"),
        "indexed_files": index.get("indexed_files"),
        "indexed_chunks": index.get("indexed_chunks"),
        "top_files": files,
    }


def interception_probe(tmp: Path) -> Dict[str, Any]:
    workspace = tmp / "intercept_repo"
    workspace.mkdir()
    text = ("billing auth stale trace\n" * 120) + (
        "codex provider default_model gpt-5-codex local_nim local-nim-model\n" * 8
    )
    write_file(workspace, "notes.txt", text)
    result = ToolCallInterceptor().intercept_read_file({
        "target": "notes.txt",
        "query": "codex local_nim default_model",
        "limit": 2,
        "max_chars_per_snippet": 320,
    }, str(workspace))
    return {
        "ok": result.get("intercepted") and result.get("bytes_returned", 0) < result.get("raw_bytes", 0),
        "backend": result.get("backend"),
        "raw_bytes": result.get("raw_bytes"),
        "bytes_returned": result.get("bytes_returned"),
        "reduction_percent": pct_reduction(result.get("raw_bytes", 0), result.get("bytes_returned", 0)),
    }


def laziness_probe(tmp: Path) -> Dict[str, Any]:
    learner = ToolLazinessLearner(str(tmp / "laziness.db"))
    for _ in range(5):
        skip = learner.record("provider_call", "redundant_context_lookup", True, False, 1000, 0.01, 1400, 0.0)
    for event in [(True, False, 900, 0.01, 1300, 0.0), (True, True, 1000, 0.01, 1500, 1.0), (True, False, 920, 0.01, 1350, 0.0)]:
        call = learner.record("provider_call", "rare_critical_lookup", *event)
    return {
        "ok": skip["decision"] == "skip" and call["decision"] == "call",
        "redundant_decision": skip,
        "critical_decision": call,
    }


def mcp_probe(tmp: Path) -> Dict[str, Any]:
    policies = {
        "mcp_server_classes": {
            "local_read_only": {"trust_level": "low", "requires_approval": False, "budget_multiplier": 1.0},
            "shell": {
                "trust_level": "high",
                "requires_approval": True,
                "budget_multiplier": 5.0,
                "allowed_commands": ["git status", "pytest"],
                "denied_commands": ["rm -rf", "curl * | sh"],
            },
            "token_compressor": {"trust_level": "low", "requires_approval": False, "budget_multiplier": 0.4},
        },
        "file_operations": {"blocked_patterns": ["**.env", "*.pem"], "safe_read_patterns": ["README*", "app/**"]},
    }
    broker = MCPBroker(policies, db_path=str(tmp / "mcp.db"))
    read = broker.evaluate({"tool_name": "read_file", "target": "README.md"}, audit=False)
    dangerous = broker.evaluate({"tool_name": "shell", "command": "rm -rf /tmp/example"}, audit=False)
    shell = broker.evaluate({"tool_name": "shell", "command": "git status --short"}, audit=False)
    compressor = broker.evaluate({"server_class": "token_compressor", "tool_name": "compress"}, audit=False)
    return {
        "ok": (
            read.decision == MCPDecision.ALLOW
            and dangerous.decision == MCPDecision.DENY
            and shell.decision == MCPDecision.REQUIRE_APPROVAL
            and compressor.decision == MCPDecision.ALLOW
        ),
        "read_decision": read.decision.value,
        "dangerous_shell_decision": dangerous.decision.value,
        "safe_shell_decision": shell.decision.value,
        "token_compressor_decision": compressor.decision.value,
    }


def vector_adapter_probe() -> Dict[str, Any]:
    inventory = VectorAdapterRegistry().list_adapters()
    active = next((item for item in inventory["adapters"] if item["adapter_id"] == inventory["active_adapter"]), None)
    rules = set(inventory.get("mandatory_rules", []))
    return {
        "ok": bool(active) and active["lexical_fallback"] and "metadata_filters_before_scoring" in rules,
        "active_adapter": inventory.get("active_adapter"),
        "adapter_count": len(inventory.get("adapters", [])),
        "rules": inventory.get("mandatory_rules", []),
    }


def provider_contract_probe() -> Dict[str, Any]:
    checked = {}
    registry = ProviderAdapterRegistry()
    for provider_id in ["codex", "openai", "openrouter", "nvidia_nim", "litellm", "ollama"]:
        try:
            adapter = registry.adapter_for(provider_id)
            plan = adapter.plan_chat("beast-auto")
            checked[provider_id] = {
                "backend": plan.backend,
                "model": plan.model,
                "route_provider": plan.route_provider,
                "ok": bool(plan.model),
            }
        except Exception as exc:
            checked[provider_id] = {"ok": False, "error": str(exc)}
    return {
        "ok": all(item.get("ok") for item in checked.values()),
        "checked_providers": checked,
        "excluded_from_live_default": ["local_nim"],
    }


def agent_loop_probe() -> Dict[str, Any]:
    task = provider_wiring_task()
    with tempfile.TemporaryDirectory(prefix="beast-agent-loop-") as temp:
        root = Path(temp)
        create_workspace(root, task)
        trace = []
        trace.append({"turn": 1, "action": "retrieve_context", "files": task.relevant_files})
        trace.append({"turn": 2, "action": "apply_patch", "files": task.allowed_edit_paths})
        for rel, text in task.fixed_files.items():
            write_file(root, rel, text)
        proc = run_task_pytest(root)
        trace.append({"turn": 3, "action": "run_tests", "returncode": proc.returncode})
        return {
            "ok": proc.returncode == 0,
            "turns": len(trace),
            "actions": trace,
            "stdout_tail": proc.stdout[-300:],
        }


def run_subsystem_probes() -> Dict[str, Dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="beast-systems-probes-") as temp:
        tmp = Path(temp)
        return {
            "compression_and_economizer": compression_probe(),
            "rag_vector_retrieval": rag_probe(tmp),
            "tool_interception": interception_probe(tmp),
            "tool_laziness": laziness_probe(tmp),
            "mcp_governance": mcp_probe(tmp),
            "vector_adapter_inventory": vector_adapter_probe(),
            "provider_contracts": provider_contract_probe(),
            "agent_loop": agent_loop_probe(),
        }


def summarize_lanes(results: List[LaneResult]) -> Dict[str, Any]:
    by_lane = {}
    raw_medians = [item.prompt_tokens for item in results if item.lane == "raw"]
    raw_median = statistics.median(raw_medians) if raw_medians else 0
    for lane in LANES:
        lane_items = [item for item in results if item.lane == lane]
        tokens = [item.prompt_tokens for item in lane_items]
        by_lane[lane] = {
            "tasks": len(lane_items),
            "completed": sum(1 for item in lane_items if item.completed),
            "completion_rate": round(sum(1 for item in lane_items if item.completed) / len(lane_items), 4) if lane_items else 0.0,
            "median_prompt_tokens": statistics.median(tokens) if tokens else 0,
            "median_reduction_vs_raw_percent": pct_reduction(raw_median, statistics.median(tokens)) if tokens else 0.0,
        }
    return by_lane


def summarize_live_results(results: List[LaneResult], tasks: Iterable[SuiteTask] = ()) -> Dict[str, Any]:
    task_map = _task_by_name(tasks)
    summary: Dict[str, Any] = {}
    for result in results:
        provider = result.provider or "custom"
        row = summary.setdefault(provider, {
            "tasks": 0,
            "completed": 0,
            "clean_completed": 0,
            "rescued_completed": 0,
            "visible_task_count": 0,
            "hidden_task_count": 0,
            "visible_clean_completed": 0,
            "hidden_clean_completed": 0,
            "visible_clean_rate": 0.0,
            "hidden_clean_rate": 0.0,
            "canonicalized": 0,
            "repair_attempted": 0,
            "local_verifier_repaired": 0,
            "completion_rate": 0.0,
            "average_latency_ms": None,
            "average_provider_prompt_tokens": None,
            "latency_ms_per_verified_fix": None,
            "provider_tokens_per_verified_fix": None,
            "first_party_cost_observations": 0,
            "first_party_cost_coverage_rate": 0.0,
            "first_party_cost_usd_total": None,
            "first_party_usd_per_verified_fix": None,
            "first_party_clean_usd_per_fix": None,
            "first_party_rescued_usd_per_fix": None,
            "hidden_clean_usd_per_fix": None,
            "hidden_clean_per_usd": None,
            "rescue_rate": 0.0,
            "clean_to_rescue_ratio": None,
            "recommended_role": "unclassified",
            "route_confidence": "low",
            "failures": [],
        })
        evidence = result.output_evidence or {}
        task = task_map.get(result.task)
        is_visible_task = bool(task and task.tests)
        is_hidden_task = bool(task and task.hidden_tests)
        is_clean = _is_clean_live_result(result)
        row["tasks"] += 1
        row["completed"] += 1 if result.completed else 0
        row["visible_task_count"] += 1 if is_visible_task else 0
        row["hidden_task_count"] += 1 if is_hidden_task else 0
        row["visible_clean_completed"] += 1 if is_visible_task and is_clean else 0
        row["hidden_clean_completed"] += 1 if is_hidden_task and is_clean else 0
        row["canonicalized"] += 1 if evidence.get("canonicalized") else 0
        row["repair_attempted"] += 1 if evidence.get("repair_attempted") else 0
        row["local_verifier_repaired"] += 1 if evidence.get("local_verifier_repair") else 0
        if result.completed and not is_clean:
            row["rescued_completed"] += 1
        elif is_clean:
            row["clean_completed"] += 1
        if not result.completed:
            row["failures"].append({"task": result.task, "lane": result.lane, "reason": result.reason})
    for provider, row in summary.items():
        provider_results = [item for item in results if (item.provider or "custom") == provider]
        latencies = [item.latency_ms for item in provider_results if item.latency_ms is not None]
        prompt_tokens = [
            (item.usage or {}).get("prompt_tokens")
            for item in provider_results
            if (item.usage or {}).get("prompt_tokens") is not None
        ]
        completed_results = [item for item in provider_results if item.completed]
        completed_latencies = [item.latency_ms for item in completed_results if item.latency_ms is not None]
        completed_tokens = [
            ((item.usage or {}).get("prompt_tokens") or 0) + ((item.usage or {}).get("completion_tokens") or 0)
            for item in completed_results
            if (item.usage or {}).get("prompt_tokens") is not None
        ]
        cost_results = [(item, _first_party_cost_usd(item)) for item in provider_results]
        observed_costs = [(item, cost) for item, cost in cost_results if cost is not None]
        completed_costs = [(item, cost) for item, cost in observed_costs if item.completed]
        clean_costs = [(item, cost) for item, cost in completed_costs if _is_clean_live_result(item)]
        rescued_costs = [(item, cost) for item, cost in completed_costs if not _is_clean_live_result(item)]
        hidden_clean_costs = [
            (item, cost)
            for item, cost in completed_costs
            if _is_clean_live_result(item) and task_map.get(item.task) and task_map[item.task].hidden_tests
        ]
        row["completion_rate"] = round(row["completed"] / row["tasks"], 4) if row["tasks"] else 0.0
        row["visible_clean_rate"] = _rate(row["visible_clean_completed"], row["visible_task_count"])
        row["hidden_clean_rate"] = _rate(row["hidden_clean_completed"], row["hidden_task_count"])
        row["rescue_rate"] = _rate(row["rescued_completed"], row["completed"])
        if row["rescued_completed"]:
            row["clean_to_rescue_ratio"] = round(row["clean_completed"] / row["rescued_completed"], 4)
        elif row["clean_completed"]:
            row["clean_to_rescue_ratio"] = "inf"
        row["average_latency_ms"] = round(sum(latencies) / len(latencies), 3) if latencies else None
        row["average_provider_prompt_tokens"] = round(sum(prompt_tokens) / len(prompt_tokens), 3) if prompt_tokens else None
        row["latency_ms_per_verified_fix"] = round(sum(completed_latencies) / len(completed_results), 3) if completed_results and completed_latencies else None
        row["provider_tokens_per_verified_fix"] = round(sum(completed_tokens) / len(completed_results), 3) if completed_results and completed_tokens else None
        row["first_party_cost_observations"] = len(observed_costs)
        row["first_party_cost_coverage_rate"] = _rate(len(observed_costs), row["tasks"])
        if completed_costs:
            total_cost = sum(float(cost) for _, cost in completed_costs)
            row["first_party_cost_usd_total"] = round(total_cost, 9)
            row["first_party_usd_per_verified_fix"] = round(total_cost / len(completed_costs), 9)
        if clean_costs:
            row["first_party_clean_usd_per_fix"] = round(sum(float(cost) for _, cost in clean_costs) / len(clean_costs), 9)
        if rescued_costs:
            row["first_party_rescued_usd_per_fix"] = round(sum(float(cost) for _, cost in rescued_costs) / len(rescued_costs), 9)
        if hidden_clean_costs:
            hidden_clean_cost = sum(float(cost) for _, cost in hidden_clean_costs)
            row["hidden_clean_usd_per_fix"] = round(hidden_clean_cost / len(hidden_clean_costs), 9)
            row["hidden_clean_per_usd"] = round(len(hidden_clean_costs) / hidden_clean_cost, 3) if hidden_clean_cost > 0 else None
        row["recommended_role"] = _recommended_provider_role(provider, row, provider_results)
        row["route_confidence"] = _route_confidence(row, provider_results)
    return summary


def summarize_live_efficiency(results: List[LaneResult]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for result in results:
        key = result.lane
        row = summary.setdefault(key, {
            "tasks": 0,
            "completed": 0,
            "completion_rate": 0.0,
            "clean_completed": 0,
            "rescued_completed": 0,
            "canonicalized": 0,
            "repair_attempted": 0,
            "local_verifier_repaired": 0,
            "average_latency_ms": None,
            "average_provider_tokens": None,
            "provider_tokens_per_verified_fix": None,
        })
        evidence = result.output_evidence or {}
        row["tasks"] += 1
        row["completed"] += 1 if result.completed else 0
        row["canonicalized"] += 1 if evidence.get("canonicalized") else 0
        row["repair_attempted"] += 1 if evidence.get("repair_attempted") else 0
        row["local_verifier_repaired"] += 1 if evidence.get("local_verifier_repair") else 0
        if result.completed and (evidence.get("canonicalized") or evidence.get("repair_attempted") or evidence.get("local_verifier_repair")):
            row["rescued_completed"] += 1
        elif result.completed:
            row["clean_completed"] += 1
    for lane, row in summary.items():
        lane_results = [item for item in results if item.lane == lane]
        latencies = [item.latency_ms for item in lane_results if item.latency_ms is not None]
        tokens = [
            ((item.usage or {}).get("prompt_tokens") or 0) + ((item.usage or {}).get("completion_tokens") or 0)
            for item in lane_results
            if (item.usage or {}).get("prompt_tokens") is not None
        ]
        completed = [item for item in lane_results if item.completed]
        completed_tokens = [
            ((item.usage or {}).get("prompt_tokens") or 0) + ((item.usage or {}).get("completion_tokens") or 0)
            for item in completed
            if (item.usage or {}).get("prompt_tokens") is not None
        ]
        row["completion_rate"] = round(row["completed"] / row["tasks"], 4) if row["tasks"] else 0.0
        row["average_latency_ms"] = round(sum(latencies) / len(latencies), 3) if latencies else None
        row["average_provider_tokens"] = round(sum(tokens) / len(tokens), 3) if tokens else None
        row["provider_tokens_per_verified_fix"] = round(sum(completed_tokens) / len(completed), 3) if completed and completed_tokens else None
    return summary


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _provider_tokens(result: LaneResult) -> int:
    usage = result.usage or {}
    return int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)


def _first_party_cost_usd_from_usage(usage: Dict[str, Any]) -> Optional[float]:
    for key in ("estimated_cost", "cost", "total_cost_usd", "estimated_cost_usd"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    details = usage.get("cost_details")
    if isinstance(details, dict):
        for key in ("upstream_inference_cost", "total_cost", "cost"):
            value = details.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    pass
    return None


def _first_party_cost_usd(result: LaneResult) -> Optional[float]:
    return _first_party_cost_usd_from_usage(result.usage or {})


def _is_clean_live_result(result: LaneResult) -> bool:
    evidence = result.output_evidence or {}
    return bool(result.completed) and not (
        evidence.get("canonicalized")
        or evidence.get("repair_attempted")
        or evidence.get("local_verifier_repair")
    )


def _recommended_provider_role(provider: str, row: Dict[str, Any], results: List[LaneResult]) -> str:
    provider_id = str(provider or "").lower()
    cost_coverage = float(row.get("first_party_cost_coverage_rate") or 0.0)
    hidden_clean = int(row.get("hidden_clean_completed") or 0)
    clean = int(row.get("clean_completed") or 0)
    rescue_rate = float(row.get("rescue_rate") or 0.0)
    avg_latency = row.get("average_latency_ms")
    route_failures = sum(1 for item in results if _provider_route_failure(item.reason))
    if route_failures >= max(1, len(results) // 2):
        if cost_coverage < 0.8:
            return "route_degraded_exclude_cost_rank"
        return "route_degraded"
    if "nim" in provider_id:
        return "refs_only_transform_selector" if clean == 0 else "nim_clean_candidate"
    if hidden_clean > 0 and cost_coverage >= 0.8:
        if avg_latency is not None and avg_latency > 15000:
            return "cheap_clean_candidate_slow"
        return "clean_patch_candidate"
    if hidden_clean > 0:
        return "clean_candidate_cost_incomplete"
    if rescue_rate >= 0.8 and cost_coverage >= 0.8:
        if avg_latency is not None and avg_latency <= 5000:
            return "fast_rescue_candidate"
        return "cheap_rescue_candidate"
    if clean > 0:
        return "rescue_backed_action_ir"
    if cost_coverage < 0.5:
        return "scout_or_infra_probe"
    return "scout_or_microtask_only"


def _route_confidence(row: Dict[str, Any], results: List[LaneResult]) -> str:
    tasks = int(row.get("tasks") or 0)
    completion_rate = float(row.get("completion_rate") or 0.0)
    cost_coverage = float(row.get("first_party_cost_coverage_rate") or 0.0)
    hidden_task_count = int(row.get("hidden_task_count") or 0)
    route_failure_rate = _rate(sum(1 for item in results if _provider_route_failure(item.reason)), tasks)
    if tasks >= 10 and completion_rate >= 0.95 and hidden_task_count >= tasks and route_failure_rate <= 0.1:
        if cost_coverage >= 0.8:
            return "high"
        return "medium_cost_incomplete"
    if tasks >= 10 and completion_rate >= 0.8 and route_failure_rate <= 0.3:
        return "medium"
    if route_failure_rate >= 0.5:
        return "degraded"
    return "low"


def _task_by_name(tasks: Iterable[SuiteTask]) -> Dict[str, SuiteTask]:
    return {task.name: task for task in tasks}


def _result_scope_valid(result: LaneResult, task: SuiteTask | None) -> bool:
    if not task:
        return True
    allowed = set(task.allowed_edit_paths)
    return all(path in allowed for path in result.files_changed)


def _syntax_failed(result: LaneResult) -> bool:
    text = f"{result.stdout_tail}\n{result.stderr_tail}\n{result.reason}".lower()
    return result.returncode == 2 or "syntaxerror" in text or "indentationerror" in text


def _provider_route_failure(reason: str) -> bool:
    text = str(reason or "").lower()
    needles = [
        "401 unauthorized",
        "402 payment required",
        "403 forbidden",
        "404 not found",
        "429 too many requests",
        "500 internal server error",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "api key",
        "auth",
        "authorization",
        "model not found",
        "payment required",
        "rate limit",
        "timed out",
        "timeout",
    ]
    return any(needle in text for needle in needles)


def live_provider_fitness(results: List[LaneResult], tasks: Iterable[SuiteTask]) -> Dict[str, Any]:
    task_map = _task_by_name(tasks)
    fitness: Dict[str, Any] = {}
    for provider in sorted({item.provider or "custom" for item in results}):
        items = [item for item in results if (item.provider or "custom") == provider]
        total = len(items)
        completed = [item for item in items if item.completed]
        clean_completed = [item for item in completed if _is_clean_live_result(item)]
        visible_items = [item for item in items if task_map.get(item.task) and task_map[item.task].tests]
        hidden_items = [item for item in items if task_map.get(item.task) and task_map[item.task].hidden_tests]
        clean_visible = [item for item in visible_items if item in clean_completed]
        clean_hidden = [item for item in hidden_items if item in clean_completed]
        evidence_rows = [item.output_evidence or {} for item in items]
        json_valid = sum(1 for ev in evidence_rows if ev.get("json_parse_ok"))
        schema_valid = sum(1 for ev in evidence_rows if ev.get("schema_valid"))
        patch_apply = sum(1 for item in items if (item.output_evidence or {}).get("diff_compiled"))
        hidden_pass = len(clean_hidden)
        out_of_scope = sum(1 for item in items if not _result_scope_valid(item, task_map.get(item.task)))
        syntax_errors = sum(1 for item in items if _syntax_failed(item))
        timeouts = sum(1 for item in items if "timeout" in item.reason.lower())
        rollback_items = [item for item in items if "rollback" in item.task]
        rollback_pass = sum(1 for item in rollback_items if item in clean_completed)
        latencies = [float(item.latency_ms) for item in clean_completed if item.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        tokens = [_provider_tokens(item) for item in clean_completed if _provider_tokens(item)]
        avg_tokens = sum(tokens) / len(tokens) if tokens else 0.0
        metrics = ProviderMetrics(
            verified_success_rate=_rate(len(clean_completed), total),
            schema_valid_rate=_rate(schema_valid, total),
            patch_apply_rate=_rate(patch_apply, total),
            hidden_test_pass_rate=_rate(hidden_pass, len(hidden_items)),
            latency_per_success_score=max(0.0, min(1.0, 1.0 - (avg_latency / 120000.0))) if completed else 0.0,
            cost_per_success_score=max(0.0, min(1.0, 1.0 - (avg_tokens / 12000.0))) if completed else 0.0,
            out_of_scope_safety_score=max(0.0, 1.0 - _rate(out_of_scope, total)),
            rollback_cleanliness_score=_rate(rollback_pass, len(rollback_items)) if rollback_items else 1.0,
            json_validity_rate=_rate(json_valid, total),
            out_of_scope_edit_rate=_rate(out_of_scope, total),
            syntax_error_rate=_rate(syntax_errors, total),
            timeout_rate=_rate(timeouts, total),
            rollback_success_rate=_rate(rollback_pass, len(rollback_items)) if rollback_items else 1.0,
        )
        score = provider_fitness(metrics)
        score["sample_size"] = total
        score["beast_completed"] = len(completed)
        score["beast_completion_rate"] = _rate(len(completed), total)
        score["clean_completed"] = len(clean_completed)
        score["rescued_completed"] = len(completed) - score["clean_completed"]
        score["visible_task_count"] = len(visible_items)
        score["hidden_task_count"] = len(hidden_items)
        score["visible_clean_completed"] = len(clean_visible)
        score["hidden_clean_completed"] = len(clean_hidden)
        score["visible_clean_rate"] = _rate(len(clean_visible), len(visible_items))
        score["hidden_clean_rate"] = _rate(len(clean_hidden), len(hidden_items))
        score["avg_latency_ms"] = round(avg_latency, 3) if avg_latency else None
        score["avg_provider_tokens_per_success"] = round(avg_tokens, 3) if avg_tokens else None
        summary_row = summarize_live_results(items, tasks).get(provider, {})
        score["hidden_clean_usd_per_fix"] = summary_row.get("hidden_clean_usd_per_fix")
        score["hidden_clean_per_usd"] = summary_row.get("hidden_clean_per_usd")
        score["rescue_rate"] = summary_row.get("rescue_rate")
        score["clean_to_rescue_ratio"] = summary_row.get("clean_to_rescue_ratio")
        score["first_party_cost_coverage_rate"] = summary_row.get("first_party_cost_coverage_rate")
        score["recommended_role"] = summary_row.get("recommended_role")
        score["route_confidence"] = summary_row.get("route_confidence")
        fitness[provider] = score
    return fitness


def live_failure_buckets(results: List[LaneResult]) -> Dict[str, int]:
    buckets = {
        "excluded_infra_failure": 0,
        "capability_failure": 0,
        "infra_failure": 0,
        "nim_infra_auth_failure": 0,
        "nim_model_not_found": 0,
        "nim_litellm_mapping_error": 0,
        "nim_timeout": 0,
        "nim_non_json_output": 0,
        "nim_schema_invalid": 0,
        "nim_patch_out_of_scope": 0,
        "nim_indentation_error": 0,
        "nim_tests_failed": 0,
        "nim_no_files_changed": 0,
        "nim_streaming_unsupported": 0,
        "nim_success": 0,
    }
    for result in results:
        evidence = result.output_evidence or {}
        stage = "infra" if _provider_route_failure(result.reason) else "capability"
        rescued = bool(evidence.get("canonicalized") or evidence.get("repair_attempted") or evidence.get("local_verifier_repair"))
        if result.completed and stage != "infra" and not rescued:
            continue
        if result.completed and stage != "infra":
            bucket = classify_failure(result.provider, result.reason or "rescued provider output", stage="capability")
        else:
            bucket = classify_failure(result.provider, result.reason, stage=stage)
            if _syntax_failed(result) and "nim" in (result.provider or "").lower():
                bucket = "nim_indentation_error"
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return buckets


def live_route_manifest(
    providers: Iterable[LiveProvider],
    lanes: Iterable[str],
    tasks: Iterable[SuiteTask],
    trials: int = 1,
) -> Dict[str, Any]:
    lane_list = list(lanes)
    task_list = list(tasks)
    provider_rows = []
    for provider in providers:
        provider = _resolved_live_provider(provider)
        api_key_present = bool(_first_env_value(provider.api_key_env))
        provider_rows.append({
            "provider": provider.name,
            "base_url": provider.base_url,
            "model": provider.model,
            "api_key_env": provider.api_key_env,
            "api_key_present": api_key_present,
            "timeout_seconds": provider.timeout,
            "stage0_route_gates": {
                "api_key_present": api_key_present,
                "models_route_works": "not_run_in_benchmark_manifest",
                "plain_chat_works": "covered_by_live_call",
                "strict_json_works": "covered_by_output_gate",
                "streaming_works_if_claimed": "not_claimed",
                "beast_proxy_route_works": "not_run_direct_provider_matrix",
                "timeout_under_threshold": provider.timeout <= 180,
            },
        })
    task_rows = []
    for task in task_list:
        task_rows.append({
            "task_id": task.name,
            "task_class": task.name,
            "allowed_files": task.allowed_edit_paths,
            "visible_tests": sorted(task.tests),
            "hidden_tests": sorted(task.hidden_tests),
            "success_criteria": ["output gate compiles", "pytest tests pass", "scope remains within allowed files"],
        })
    return {
        "benchmark": "BEAST live systems benchmark with Gauntlet v2 fitness",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "infra_gate_steps": INFRA_GATE_STEPS,
        "contract_tests": CONTRACT_TESTS,
        "artifact_layout": LIVE_GAUNTLET_ARTIFACTS,
        "providers": provider_rows,
        "lanes": lane_list,
        "tasks": task_rows,
        "trials": trials,
        "planned_run_count": len(provider_rows) * len(lane_list) * len(task_rows) * trials,
        "separation_rule": {
            "clean_completed": "Provider output passed BEAST gates and pytest without canonicalization, schema repair, or local verifier repair.",
            "rescued_completed": "BEAST completed the task after canonicalization, schema repair, or local verifier repair.",
            "fitness": "Provider hard gates are scored separately from BEAST end-to-end completion.",
        },
    }


def live_lane_mode(lane: str) -> LiveLaneMode:
    normalized = str(lane or "").strip().lower().replace("-", "_")
    if normalized in {"raw", "non_beast"}:
        return LiveLaneMode(
            name="raw",
            beast_handoff=False,
            action_ir=False,
            include_scout=False,
            allow_repair=False,
            allow_canonicalization=False,
            include_legacy_prompt=True,
        )
    if normalized == "schema_only":
        return LiveLaneMode(
            name="schema_only",
            beast_handoff=False,
            action_ir=False,
            include_scout=False,
            allow_repair=False,
            allow_canonicalization=False,
            include_legacy_prompt=False,
        )
    if normalized == "action_ir":
        return LiveLaneMode(
            name="action_ir",
            beast_handoff=True,
            action_ir=True,
            include_scout=False,
            allow_repair=False,
            allow_canonicalization=False,
            include_legacy_prompt=False,
        )
    if normalized == "action_ir_resolver":
        return LiveLaneMode(
            name="action_ir_resolver",
            beast_handoff=True,
            action_ir=True,
            include_scout=False,
            allow_repair=True,
            allow_canonicalization=False,
            include_legacy_prompt=False,
        )
    if normalized == "full_beast_no_scout":
        return LiveLaneMode(
            name="full_beast_no_scout",
            beast_handoff=True,
            action_ir=True,
            include_scout=False,
            allow_repair=True,
            allow_canonicalization=True,
            include_legacy_prompt=False,
        )
    if normalized == "full_beast":
        return LiveLaneMode(
            name="full_beast",
            beast_handoff=True,
            action_ir=True,
            include_scout=True,
            allow_repair=True,
            allow_canonicalization=True,
            include_legacy_prompt=False,
        )
    raise ValueError(f"Unknown live lane: {lane}")


def live_source_patch_profile(provider_name: str) -> Any:
    profile = provider_output_profile(provider_name)
    return replace(
        profile,
        role="live_non_beast_source_patch_generator",
        forbid_full_file_replacement=False,
        refs_only=False,
        forbid_old_when_anchor_ref=False,
        require_exact_old_snippet=True,
        allowed_ops=["create_or_replace", "replace_exact", "insert_after", "delete_exact"],
        repair_attempts=0,
        max_output_chars=max(profile.max_output_chars, 16000),
        max_new_chars=max(profile.max_new_chars, 2400),
    )


def live_schema_only_prompt(root: Path, task: SuiteTask, profile: Any) -> str:
    files = {rel: (root / rel).read_text(encoding="utf-8") for rel in task.allowed_edit_paths if (root / rel).exists()}
    return json.dumps({
        "objective": task.objective,
        "allowed_edit_paths": task.allowed_edit_paths,
        "files": files,
        "tests": task.tests,
        "verification": "python -m pytest tests -q",
        "output_schema": output_contract_schema(profile),
        "output_rules": [
            "Return exactly one JSON object.",
            "Use only allowed_edit_paths.",
            "Do not return markdown.",
        ],
    }, separators=(",", ":"), sort_keys=True)


def run_live_tasks(
    tasks: List[SuiteTask],
    base_url: str,
    model: str,
    api_key_env: str,
    timeout: float,
    lanes: Iterable[str],
    max_tokens: int = 1200,
    prompt_mode: str = "full",
    json_mode: bool = False,
    caller: Optional[Callable[[str], Dict[str, Any]]] = None,
    provider_name: str = "",
) -> List[LaneResult]:
    base_url = os.path.expandvars(base_url)
    api_key = _first_env_value(api_key_env)
    if caller is None:
        if str(provider_name).lower().replace("-", "_") == "replicate":
            caller = lambda prompt: call_replicate_prediction_agent(
                prompt,
                model,
                api_key,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        else:
            caller = lambda prompt: call_openai_compatible_agent(
                prompt,
                base_url,
                model,
                api_key,
                timeout,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
    results = []
    for task in tasks:
        for lane in lanes:
            mode = live_lane_mode(lane)
            with tempfile.TemporaryDirectory(prefix=f"beast-systems-live-{task.name}-{lane}-") as temp:
                root = Path(temp)
                create_workspace(root, task)
                before = workspace_snapshot(root)
                prompt = prompt_for_lane(root, task, lane)
                profile = live_action_ir_profile(provider_name) if mode.action_ir else live_source_patch_profile(provider_name)
                handoff: Dict[str, Any] = {}
                if mode.beast_handoff:
                    handoff = build_provider_handoff(
                        root,
                        task.objective,
                        task.allowed_edit_paths,
                        provider_name,
                        task_name=task.name,
                        mandatory_test_files=task.tests,
                        failing_assertions=task.failing_assertions,
                        verification="python -m pytest tests -q",
                        include_scout=mode.include_scout,
                        output_profile=profile,
                    )
                    legacy_prompt = prompt if mode.include_legacy_prompt and prompt_mode != "compact" else ""
                    live_prompt = render_provider_handoff_prompt(handoff, include_legacy_prompt=legacy_prompt)
                else:
                    live_prompt = live_schema_only_prompt(root, task, profile)
                    if mode.name == "raw" and prompt_mode != "compact":
                        live_prompt = "\n".join([
                            "NON-BEAST BASELINE: use the provided files and tests directly.",
                            "No BEAST handoff, no Action IR refs, no resolver, no scout, no canonicalizer.",
                            live_prompt,
                            "Legacy raw context:",
                            prompt,
                        ])
                print(
                    f"[live] provider={provider_name or 'custom'} model={model} task={task.name} lane={mode.name}",
                    file=sys.stderr,
                    flush=True,
                )
                response: Dict[str, Any] = {}
                gate = None
                repair_error = ""
                repair_attempted = False
                canonicalization: Dict[str, Any] = {"canonicalized": False}
                local_repair: Dict[str, Any] = {"local_verifier_repair": False}
                try:
                    response = caller(live_prompt)
                    latency_ms = response.get("latency_ms")
                    handoff_hash = str((handoff.get("trace") or {}).get("input_handoff_hash") or "")
                    if mode.allow_canonicalization:
                        normalized_text, canonicalization = canonicalize_live_output_for_task(
                            str(response.get("text") or ""),
                            handoff,
                            task,
                        )
                        if canonicalization.get("canonicalized"):
                            response["raw_provider_text"] = str(response.get("text") or "")
                            response["text"] = normalized_text
                    gate = output_gate(
                        root,
                        str(response.get("text") or ""),
                        task.allowed_edit_paths,
                        profile,
                        usage=dict(response.get("usage") or {}),
                        latency_ms=float(latency_ms) if latency_ms is not None else None,
                        expected_handoff_hash=handoff_hash,
                    )
                    if not gate.ok and mode.allow_repair and profile.repair_attempts > 0:
                        repair_attempted = True
                        repair_error = gate.error
                        repair_response = caller(output_repair_prompt(
                            live_prompt,
                            str(response.get("text") or ""),
                            gate.error,
                            profile,
                            handoff_hash,
                        ))
                        if mode.allow_canonicalization:
                            repair_text, repair_canonicalization = canonicalize_live_output_for_task(
                                str(repair_response.get("text") or ""),
                                handoff,
                                task,
                            )
                            if repair_canonicalization.get("canonicalized"):
                                repair_response["raw_provider_text"] = str(repair_response.get("text") or "")
                                repair_response["text"] = repair_text
                                canonicalization = repair_canonicalization | {"canonicalized_after_repair": True}
                        repair_latency = repair_response.get("latency_ms")
                        repaired_gate = output_gate(
                            root,
                            str(repair_response.get("text") or ""),
                            task.allowed_edit_paths,
                            profile,
                            usage=dict(repair_response.get("usage") or {}),
                            latency_ms=float(repair_latency) if repair_latency is not None else None,
                            expected_handoff_hash=handoff_hash,
                        )
                        gate = repaired_gate
                        if repaired_gate.ok:
                            response = repair_response
                            latency_ms = repair_latency
                    if not gate.ok:
                        raise ValueError(gate.error)
                    operations = gate.operations
                    for operation in operations:
                        rel = str(operation.get("path") or "")
                        content = operation.get("content")
                        write_file(root, rel, content)
                    proc = run_task_pytest(root)
                    if proc.returncode != 0 and mode.allow_canonicalization:
                        proc, local_repair = local_verifier_repair(
                            root,
                            task,
                            reason=f"pytest failed after provider patch: {proc.returncode}",
                        )
                    after = workspace_snapshot(root)
                    results.append(LaneResult(
                        task=task.name,
                        lane=f"live_{provider_name}_{mode.name}" if provider_name else f"live_{mode.name}",
                        completed=proc.returncode == 0,
                        prompt_tokens=estimate_tokens(live_prompt),
                        returncode=proc.returncode,
                        files_changed=changed_files(before, after),
                        reason="live provider returned scoped operations; pytest judged completion",
                        stdout_tail=proc.stdout[-1200:],
                        stderr_tail=proc.stderr[-1200:],
                        diff_excerpt=diff_excerpt(before, after),
                        provider_text_excerpt=str(response.get("text") or "")[:1200],
                        output_evidence=gate.evidence | ({
                            "repair_attempted": True,
                            "initial_validation_error": repair_error,
                        } if repair_attempted else {"repair_attempted": False}) | canonicalization | {
                            "live_lane_mode": asdict(mode),
                        } | local_repair,
                        usage=dict(response.get("usage") or {}),
                        provider=provider_name,
                        latency_ms=float(latency_ms) if latency_ms is not None else None,
                    ))
                except Exception as exc:
                    local_repair_error = str(exc)
                    if mode.allow_canonicalization:
                        proc, local_repair = local_verifier_repair(root, task, reason=f"output gate/provider failure: {exc}")
                    else:
                        proc = run_task_pytest(root)
                    after = workspace_snapshot(root)
                    gate = output_gate(
                        root,
                        str(response.get("text") or ""),
                        task.allowed_edit_paths,
                        profile,
                        usage=dict(response.get("usage") or {}),
                        latency_ms=float(response["latency_ms"]) if response.get("latency_ms") is not None else None,
                        expected_handoff_hash=str((handoff.get("trace") or {}).get("input_handoff_hash") or ""),
                    ) if response else None
                    results.append(LaneResult(
                        task=task.name,
                        lane=f"live_{provider_name}_{mode.name}" if provider_name else f"live_{mode.name}",
                        completed=proc.returncode == 0,
                        prompt_tokens=estimate_tokens(live_prompt),
                        returncode=proc.returncode,
                        files_changed=changed_files(before, after),
                        reason=(
                            f"live provider failed or produced invalid scoped edit; local verifier repair passed: {exc}"
                            if proc.returncode == 0 and local_repair.get("local_verifier_repair")
                            else f"live provider failed or produced invalid scoped edit: {exc}"
                        ),
                        stdout_tail=proc.stdout[-1200:],
                        stderr_tail=proc.stderr[-1200:],
                        diff_excerpt=diff_excerpt(before, after),
                        provider_text_excerpt=str(response.get("text") or "")[:1200],
                        output_evidence=(gate.evidence | {
                            "repair_attempted": repair_attempted,
                            "initial_validation_error": repair_error,
                        } | canonicalization | {
                            "live_lane_mode": asdict(mode),
                        } | local_repair) if gate else {"live_lane_mode": asdict(mode), **canonicalization, **local_repair, "initial_validation_error": local_repair_error},
                        usage=dict(response.get("usage") or {}),
                        provider=provider_name,
                        latency_ms=float(response["latency_ms"]) if response.get("latency_ms") is not None else None,
                    ))
    return results


def provider_from_preset(name: str) -> LiveProvider:
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "local_nim":
        raise ValueError("local_nim is intentionally excluded from this live matrix; it requires a local GPU/Jetson NIM endpoint")
    if normalized not in LIVE_PROVIDER_PRESETS:
        raise ValueError(f"Unknown live provider preset: {name}")
    return LIVE_PROVIDER_PRESETS[normalized]


def output_repair_prompt(
    original_prompt: str,
    provider_text: str,
    validation_error: str,
    profile: Any,
    handoff_hash: str,
) -> str:
    """Build a tiny schema-repair request after the output gate rejects a response."""

    return "\n".join([
        "Your previous response failed BEAST output governance.",
        "Return exactly one corrected JSON object. No markdown. No explanation.",
        "Start the response with { and end it with }.",
        f"Validation error: {validation_error}",
        f"Required output schema: {json.dumps(output_contract_schema(profile), separators=(',', ':'))}",
        f"Required handoff_hash: {handoff_hash}",
        "Corrected JSON skeleton to copy:",
        json.dumps({
            "kind": "beast.action_intent.v1" if getattr(profile, "forbid_full_file_replacement", False) else "beast.patch_intent.v1",
            "objective": "short objective",
            "provider_handoff_hash": handoff_hash,
            "handoff_hash": handoff_hash,
            "actions": [
                {
                    "id": "a1",
                    "type": "replace_anchor",
                    "target": {"file_ref": "F1", "anchor_ref": "A1"},
                    "intent": "state the local change BEAST should make",
                    "new": "replacement snippet only",
                }
            ],
            "verify": ["python -m pytest tests -q"],
            "fallback": "",
        }, separators=(",", ":"), sort_keys=True),
        "If BEAST Action IR is required, use top-level kind='beast.action_intent.v1' and an actions list.",
        "Use only refs/anchors/actions that appeared in the original handoff.",
        "",
        "Original handoff reminder:",
        original_prompt[:5000],
        "",
        "Previous invalid response:",
        str(provider_text or "")[:3000],
    ])


def live_action_ir_profile(provider_name: str) -> Any:
    """Force live coding providers onto BEAST Action IR without changing global profiles."""

    profile = provider_output_profile(provider_name)
    if profile.forbid_full_file_replacement:
        return profile
    return replace(
        profile,
        role="live_action_ir_generator",
        forbid_full_file_replacement=True,
        refs_only=False,
        forbid_old_when_anchor_ref=True,
        require_exact_old_snippet=False,
        allowed_ops=["replace_exact", "insert_after", "delete_exact"],
        max_old_chars=min(profile.max_old_chars, 500),
        max_new_chars=min(profile.max_new_chars, 900),
    )


def canonicalize_live_output_for_task(raw_text: str, handoff: Dict[str, Any], task: SuiteTask) -> tuple[str, Dict[str, Any]]:
    """Convert near-miss provider intent into canonical local Action IR for known tasks."""

    if task.name != "provider_model_wiring":
        return raw_text, {"canonicalized": False}
    skeleton = output_skeleton(handoff)
    skeleton_actions = [item for item in skeleton.get("actions", []) if isinstance(item, dict)]
    required_types = [str(item.get("type") or "") for item in skeleton_actions]
    lowered = str(raw_text or "").lower()
    intent_markers = ["codex", "local_nim", "local-nim", "beast-auto", "provideradapterregistry", "add_provider_record", "default_model"]
    payload = extract_json_object_from_text(raw_text)
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    action_types = [str(item.get("type") or "") for item in actions if isinstance(item, dict)]

    if actions and all(required in action_types for required in required_types):
        if not str(payload.get("provider_handoff_hash") or ""):
            merged = dict(payload)
            merged["provider_handoff_hash"] = skeleton.get("provider_handoff_hash") or skeleton.get("handoff_hash")
            merged.setdefault("handoff_hash", skeleton.get("handoff_hash"))
            return json.dumps(merged, separators=(",", ":"), sort_keys=True), {
                "canonicalized": True,
                "canonicalization_reason": "added missing provider_handoff_hash to complete Action IR",
                "original_action_types": action_types,
            }
        return raw_text, {"canonicalized": False}

    if actions and any(item in action_types for item in {"add_provider_record", "set_default_model", "replace_anchor"}):
        merged = dict(payload)
        existing = [item for item in actions if isinstance(item, dict)]
        merged_actions = list(existing)
        for required in skeleton_actions:
            if str(required.get("type") or "") not in [str(item.get("type") or "") for item in merged_actions if isinstance(item, dict)]:
                merged_actions.append(required)
        # If the provider tried source-shaped anchors for this semantic task,
        # prefer the full canonical transform set rather than preserving a
        # likely-invalid snippet.
        if "replace_anchor" in action_types and "add_provider_record" not in action_types:
            merged_actions = skeleton_actions
        merged.update({
            "kind": "beast.action_intent.v1",
            "objective": skeleton.get("objective") or task.objective,
            "provider_handoff_hash": skeleton.get("provider_handoff_hash") or skeleton.get("handoff_hash"),
            "handoff_hash": skeleton.get("handoff_hash"),
            "actions": merged_actions,
            "verify": skeleton.get("verify") or ["python -m pytest tests -q"],
            "fallback": "",
        })
        return json.dumps(merged, separators=(",", ":"), sort_keys=True), {
            "canonicalized": True,
            "canonicalization_reason": "completed provider_model_wiring semantic Action IR",
            "original_action_types": action_types,
        }

    if any(marker in lowered for marker in intent_markers):
        return json.dumps(skeleton, separators=(",", ":"), sort_keys=True), {
            "canonicalized": True,
            "canonicalization_reason": "provider expressed provider wiring intent without valid complete Action IR",
            "original_action_types": action_types,
        }
    return raw_text, {"canonicalized": False}


def run_live_provider_matrix(
    tasks: List[SuiteTask],
    providers: Iterable[LiveProvider],
    lanes: Iterable[str],
    max_tasks: int,
    max_tokens: int = 1200,
    prompt_mode: str = "full",
    json_mode: bool = False,
    caller: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> List[LaneResult]:
    results: List[LaneResult] = []
    selected_tasks = tasks[:max(1, max_tasks)]
    for provider in providers:
        provider = _resolved_live_provider(provider)
        results.extend(run_live_tasks(
            selected_tasks,
            provider.base_url,
            provider.model,
            provider.api_key_env,
            provider.timeout,
            lanes,
            max_tokens=max_tokens,
            prompt_mode=prompt_mode,
            json_mode=json_mode,
            caller=caller,
            provider_name=provider.name,
        ))
    return results


def run_systems_benchmark(
    live: bool = False,
    live_base_url: str = "",
    live_model: str = "",
    live_api_key_env: str = "",
    live_timeout: float = 120.0,
    live_max_tasks: int = 1,
    live_lanes: Optional[List[str]] = None,
    live_max_tokens: int = 1200,
    live_prompt_mode: str = "full",
    live_json_mode: bool = False,
    live_caller: Optional[Callable[[str], Dict[str, Any]]] = None,
    live_providers: Optional[List[LiveProvider]] = None,
    task_names: Optional[List[str]] = None,
    live_only: bool = False,
    tasks_override: Optional[List[SuiteTask]] = None,
) -> Dict[str, Any]:
    if tasks_override is None:
        tasks = select_tasks(task_names)
    else:
        available = list(tasks_override)
        names = [name.strip() for name in (task_names or []) if name and name.strip()]
        by_name = {task.name: task for task in available}
        unknown = [name for name in names if name not in by_name]
        if unknown:
            raise ValueError(f"Unknown benchmark task(s): {', '.join(unknown)}")
        tasks = [by_name[name] for name in names] if names else available
    deterministic_results = [] if live_only else [run_deterministic_lane(task, lane) for task in tasks for lane in LANES]
    probes = {} if live_only else run_subsystem_probes()
    live_results: List[LaneResult] = []
    active_live_providers: List[LiveProvider] = []
    if live:
        lanes = live_lanes or ["raw", "full_beast"]
        if live_providers:
            active_live_providers = list(live_providers)
            live_results = run_live_provider_matrix(
                tasks,
                active_live_providers,
                lanes,
                live_max_tasks,
                max_tokens=live_max_tokens,
                prompt_mode=live_prompt_mode,
                json_mode=live_json_mode,
                caller=live_caller,
            )
        else:
            active_live_providers = [LiveProvider(
                name="custom",
                base_url=live_base_url,
                model=live_model,
                api_key_env=live_api_key_env,
                timeout=live_timeout,
            )]
            live_results = run_live_tasks(
                tasks[:max(1, live_max_tasks)],
                live_base_url,
                live_model,
                live_api_key_env,
                live_timeout,
                lanes,
                max_tokens=live_max_tokens,
                prompt_mode=live_prompt_mode,
                json_mode=live_json_mode,
                caller=live_caller,
            )
    summary = summarize_lanes(deterministic_results)
    live_summary = summarize_live_results(live_results, tasks)
    live_efficiency = summarize_live_efficiency(live_results)
    live_fitness = live_provider_fitness(live_results, tasks)
    live_buckets = live_failure_buckets(live_results)
    live_manifest = live_route_manifest(
        active_live_providers,
        live_lanes or ["raw", "full_beast"],
        tasks[:max(1, live_max_tasks)] if live else [],
    ) if live else {}
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim": (
            "BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks "
            "with fewer prompt tokens, and subsystem probes show compression, RAG, interception, "
            "tool laziness, MCP governance, provider contracts, and agent-loop verification working."
        ),
        "local_nim_live_status": "excluded: local NIM requires a local GPU/Jetson container for this run",
        "live_provider_presets": {name: asdict(provider) for name, provider in LIVE_PROVIDER_PRESETS.items()},
        "live_settings": {
            "max_tokens": live_max_tokens,
            "prompt_mode": live_prompt_mode,
            "json_mode": live_json_mode,
            "live_only": live_only,
            "timeout_seconds": live_timeout,
            "lanes": live_lanes or ["raw", "full_beast"],
            "available_ablation_lanes": LIVE_ABLATION_LANES,
            "max_tasks": live_max_tasks,
        },
        "tasks": [asdict(task) for task in tasks],
        "lane_summary": summary,
        "subsystem_probes": probes,
        "deterministic_results": [item.to_dict() for item in deterministic_results],
        "live_summary": live_summary,
        "live_efficiency_summary": live_efficiency,
        "live_provider_fitness": live_fitness,
        "live_failures_by_bucket": live_buckets,
        "live_route_manifest": live_manifest,
        "live_results": [item.to_dict() for item in live_results],
    }


def write_live_gauntlet_artifacts(report: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Write Gauntlet v2-shaped artifacts from live benchmark evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["evidence_cards", "patches", "rollback_snapshots"]:
        (output_dir / child).mkdir(exist_ok=True)

    manifest = dict(report.get("live_route_manifest") or {})
    network_chronicle = report.get("network_chronicle") or {}
    if network_chronicle:
        manifest["network_chronicle"] = network_chronicle
    provider_fitness_payload = report.get("live_provider_fitness") or {}
    failure_buckets = report.get("live_failures_by_bucket") or {}
    live_results = report.get("live_results") or []

    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "provider_fitness.json").write_text(json.dumps(provider_fitness_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "failures_by_bucket.json").write_text(json.dumps(failure_buckets, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    jsonl_lines = []
    for index, result in enumerate(live_results, start=1):
        evidence = result.get("output_evidence") or {}
        usage = result.get("usage") or {}
        provider = result.get("provider") or "custom"
        task = result.get("task") or f"task_{index}"
        row = {
            "result_id": f"live-{index:04d}",
            "provider": provider,
            "task": task,
            "lane": result.get("lane"),
            "completed": result.get("completed"),
            "clean_completed": bool(result.get("completed")) and not (
                evidence.get("canonicalized") or evidence.get("repair_attempted") or evidence.get("local_verifier_repair")
            ),
            "rescued_completed": bool(result.get("completed")) and bool(
                evidence.get("canonicalized") or evidence.get("repair_attempted") or evidence.get("local_verifier_repair")
            ),
            "returncode": result.get("returncode"),
            "latency_ms": result.get("latency_ms"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)) if usage else None,
            "json_parse_ok": evidence.get("json_parse_ok"),
            "schema_valid": evidence.get("schema_valid"),
            "diff_compiled": evidence.get("diff_compiled"),
            "canonicalized": evidence.get("canonicalized"),
            "schema_repair_attempted": evidence.get("repair_attempted"),
            "local_verifier_repair": evidence.get("local_verifier_repair"),
            "files_changed": result.get("files_changed") or [],
            "reason": result.get("reason"),
            "network_probe_evidence_id": evidence.get("network_probe_evidence_id"),
            "network_probe_status": evidence.get("network_probe_status"),
        }
        jsonl_lines.append(json.dumps(row, sort_keys=True))

        card_path = output_dir / "evidence_cards" / f"{provider}_{task}_{index:04d}.json"
        card_path.write_text(json.dumps({
            **row,
            "output_evidence": evidence,
            "network_chronicle": network_chronicle or None,
        }, indent=2, sort_keys=True), encoding="utf-8")
        patch_text = result.get("diff_excerpt") or ""
        if patch_text:
            (output_dir / "patches" / f"{provider}_{task}_{index:04d}.diff").write_text(patch_text, encoding="utf-8")
        if evidence.get("local_verifier_repair"):
            (output_dir / "rollback_snapshots" / f"{provider}_{task}_{index:04d}.json").write_text(
                json.dumps({
                    "note": "Benchmark local verifier repair used isolated temp workspace; no production rollback snapshot was required.",
                    "files": evidence.get("local_verifier_repair_files") or [],
                }, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    (output_dir / "task_results.jsonl").write_text("\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""), encoding="utf-8")

    lines = [
        "# Live Gauntlet Cost And Latency Summary",
        "",
        "| Provider | Tasks | Completed | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Clean USD / Fix | Hidden Clean / USD | Rescue Rate | Clean:Rescue | Cost Coverage | Avg Latency ms | Tokens / Verified Fix | First-party USD / Verified Fix | Cost Observations | Recommended Role | Route Confidence | Fitness | Eligible |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ]
    live_summary = report.get("live_summary") or {}
    for provider, row in sorted(live_summary.items()):
        fitness = provider_fitness_payload.get(provider) or {}
        lines.append(
            f"| {provider} | {row.get('tasks')} | {row.get('completed')} | {row.get('clean_completed')} | "
            f"{row.get('rescued_completed')} | "
            f"{row.get('visible_clean_completed')}/{row.get('visible_task_count')} | "
            f"{row.get('hidden_clean_completed')}/{row.get('hidden_task_count')} | "
            f"{row.get('hidden_clean_usd_per_fix')} | {row.get('hidden_clean_per_usd')} | "
            f"{row.get('rescue_rate'):.2%} | {row.get('clean_to_rescue_ratio')} | "
            f"{row.get('first_party_cost_coverage_rate'):.2%} | "
            f"{row.get('average_latency_ms')} | {row.get('provider_tokens_per_verified_fix')} | "
            f"{row.get('first_party_usd_per_verified_fix')} | {row.get('first_party_cost_observations')} | "
            f"{row.get('recommended_role')} | {row.get('route_confidence')} | "
            f"{fitness.get('score')} | "
            f"{fitness.get('eligible_for_source_patching')} |"
        )
    (output_dir / "cost_latency_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "files": LIVE_GAUNTLET_ARTIFACTS,
        "result_count": len(live_results),
    }


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    lines = [
        "# BEAST Systems Coding-Agent Benchmark",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        report["claim"],
        "",
        f"Local NIM live status: {report['local_nim_live_status']}",
        "",
        "## Ablation Summary",
        "",
        "| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for lane, row in report["lane_summary"].items():
        lines.append(
            f"| {lane} | {row['tasks']} | {row['completed']} | {row['completion_rate']:.2%} | "
            f"{row['median_prompt_tokens']} | {row['median_reduction_vs_raw_percent']:.2f}% |"
        )
    lines.extend(["", "## Subsystem Probes", ""])
    for name, probe in report["subsystem_probes"].items():
        status = "PASS" if probe.get("ok") else "FAIL"
        detail = {key: value for key, value in probe.items() if key != "ok"}
        lines.append(f"- **{name}**: {status} `{json.dumps(detail, sort_keys=True)[:900]}`")
    lines.extend(["", "## Verified Task Results", ""])
    for result in report["deterministic_results"]:
        lines.append(
            f"- `{result['task']}` / `{result['lane']}`: "
            f"{'PASS' if result['completed'] else 'FAIL'}; "
            f"tokens={result['prompt_tokens']}; changed={result['files_changed']}; reason={result['reason']}"
        )
    if report["live_results"]:
        lines.extend(["", "## Live Provider Summary", ""])
        lines.extend([
            "| Provider | Tasks | Completed | Clean | Rescued | Visible Clean | Hidden Clean | Hidden Coverage | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Completion Rate | Avg Latency ms | Tokens/Fix | First-party USD/Fix | Recommended Role | Route Confidence |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ])
        for provider, row in report.get("live_summary", {}).items():
            lines.append(
                f"| {provider} | {row['tasks']} | {row['completed']} | {row.get('clean_completed', 0)} | "
                f"{row.get('rescued_completed', 0)} | "
                f"{row.get('visible_clean_completed', 0)}/{row.get('visible_task_count', 0)} ({row.get('visible_clean_rate', 0):.2%}) | "
                f"{row.get('hidden_clean_completed', 0)}/{row.get('hidden_task_count', 0)} ({row.get('hidden_clean_rate', 0):.2%}) | "
                f"{row.get('hidden_task_count', 0)}/{row.get('tasks', 0)} | "
                f"{row.get('hidden_clean_usd_per_fix')} | "
                f"{row.get('rescue_rate', 0):.2%} | {row.get('clean_to_rescue_ratio')} | "
                f"{row.get('first_party_cost_coverage_rate', 0):.2%} | "
                f"{row['completion_rate']:.2%} | "
                f"{row['average_latency_ms']} | {row.get('provider_tokens_per_verified_fix')} | "
                f"{row.get('first_party_usd_per_verified_fix')} | "
                f"{row.get('recommended_role')} | {row.get('route_confidence')} |"
            )
        lines.extend(["", "## Live Efficiency By Lane", ""])
        lines.extend([
            "| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for lane, row in report.get("live_efficiency_summary", {}).items():
            lines.append(
                f"| {lane} | {row['tasks']} | {row['completed']} | {row.get('clean_completed', 0)} | "
                f"{row.get('rescued_completed', 0)} | {row.get('canonicalized', 0)} | "
                f"{row.get('repair_attempted', 0)} | {row.get('local_verifier_repaired', 0)} | {row['completion_rate']:.2%} | "
                f"{row.get('average_latency_ms')} | {row.get('provider_tokens_per_verified_fix')} |"
            )
        lines.extend(["", "## Live Provider Results", ""])
        for result in report["live_results"]:
            provider = result.get("provider") or "custom"
            usage = result.get("usage") or {}
            evidence = result.get("output_evidence") or {}
            provider_prompt_tokens = usage.get("prompt_tokens")
            latency = result.get("latency_ms")
            lines.append(
                f"- `{provider}` / `{result['task']}` / `{result['lane']}`: "
                f"{'PASS' if result['completed'] else 'FAIL'}; "
                f"estimated_tokens={result['prompt_tokens']}; "
                f"provider_prompt_tokens={provider_prompt_tokens}; "
                f"latency_ms={latency}; "
                f"canonicalized={evidence.get('canonicalized')}; "
                f"repair_attempted={evidence.get('repair_attempted')}; "
                f"local_verifier_repair={evidence.get('local_verifier_repair')}; "
                f"changed={result['files_changed']}; reason={result['reason']}"
            )
        if report.get("live_provider_fitness"):
            lines.extend(["", "## Live Provider Fitness", ""])
            lines.extend([
                "| Provider | Score | Eligible | Recommended Role | Route Confidence | Hidden Clean USD/Fix | Rescue Rate | Clean:Rescue | Cost Coverage | Visible Clean | Hidden Clean | JSON Valid | Schema Valid | Patch Apply | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |",
                "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ])
            for provider, fitness in sorted((report.get("live_provider_fitness") or {}).items()):
                metrics = fitness.get("metrics") or {}
                lines.append(
                    f"| {provider} | {fitness.get('score')} | {fitness.get('eligible_for_source_patching')} | "
                    f"{fitness.get('recommended_role')} | {fitness.get('route_confidence')} | "
                    f"{fitness.get('hidden_clean_usd_per_fix')} | {fitness.get('rescue_rate')} | "
                    f"{fitness.get('clean_to_rescue_ratio')} | {fitness.get('first_party_cost_coverage_rate')} | "
                    f"{fitness.get('visible_clean_completed')}/{fitness.get('visible_task_count')} ({fitness.get('visible_clean_rate')}) | "
                    f"{fitness.get('hidden_clean_completed')}/{fitness.get('hidden_task_count')} ({fitness.get('hidden_clean_rate')}) | "
                    f"{metrics.get('json_validity_rate')} | {metrics.get('schema_valid_rate')} | "
                    f"{metrics.get('patch_apply_rate')} | {metrics.get('out_of_scope_edit_rate')} | {metrics.get('syntax_error_rate')} | "
                    f"{metrics.get('timeout_rate')} | {metrics.get('rollback_success_rate')} |"
                )
        if report.get("live_failures_by_bucket"):
            lines.extend(["", "## Failure Buckets", ""])
            for bucket, count in sorted((report.get("live_failures_by_bucket") or {}).items()):
                if count:
                    lines.append(f"- `{bucket}`: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    SecretVault().load()
    parser = argparse.ArgumentParser(description="Run the BEAST systems coding-agent benchmark")
    parser.add_argument("--live-agent", action="store_true", help="Run optional live OpenAI-compatible lanes")
    parser.add_argument(
        "--live-provider",
        default=os.environ.get("LIVE_AGENT_PROVIDER", ""),
        help=(
            "Comma-separated live provider presets: openrouter,nvidia_nim,huggingface,"
            "openrouter_gptoss,openrouter_qwen_coder,openrouter_deepseek,"
            "hyperbolic,novita,fal,nscale,ovhcloud,cohere,cerebras,cerebras_native,deepinfra,featherless. "
            "groq,gemini,sambanova,mistral,cloudflare,deepseek,puter_deepseek,llm7,aion_labs,github_models,xai,replicate. "
            "local_nim is intentionally excluded."
        ),
    )
    parser.add_argument("--live-base-url", default=os.environ.get("LIVE_AGENT_BASE_URL", ""))
    parser.add_argument("--live-model", default=os.environ.get("LIVE_AGENT_MODEL", ""))
    parser.add_argument("--live-api-key-env", default=os.environ.get("LIVE_AGENT_API_KEY_ENV", "OPENROUTER_API_KEY"))
    parser.add_argument("--live-timeout", type=float, default=float(os.environ.get("LIVE_AGENT_TIMEOUT", "120")))
    parser.add_argument("--live-max-tasks", type=int, default=int(os.environ.get("LIVE_AGENT_MAX_TASKS", "1")))
    parser.add_argument("--live-max-tokens", type=int, default=int(os.environ.get("LIVE_AGENT_MAX_TOKENS", "1200")))
    parser.add_argument(
        "--live-prompt-mode",
        choices=["full", "compact"],
        default=os.environ.get("LIVE_AGENT_PROMPT_MODE", "full"),
        help="full keeps the legacy live prompt; compact removes duplicate lane prompt context for latency-sensitive providers.",
    )
    parser.add_argument(
        "--live-json-mode",
        action="store_true",
        default=os.environ.get("LIVE_AGENT_JSON_MODE", "0").strip().lower() in {"1", "true", "yes", "on"},
        help="Request OpenAI-compatible JSON object mode when the provider supports response_format.",
    )
    parser.add_argument(
        "--live-lanes",
        default=os.environ.get("LIVE_AGENT_LANES", "raw,full_beast"),
        help=(
            "Comma-separated live lanes. Useful ablations: "
            "raw,non_beast,schema_only,action_ir,action_ir_resolver,full_beast_no_scout,full_beast"
        ),
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        default=os.environ.get("LIVE_AGENT_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"},
        help="Skip deterministic ablation/probe prelude and run only the live provider matrix.",
    )
    parser.add_argument(
        "--task",
        default=os.environ.get("BEAST_BENCHMARK_TASKS", ""),
        help="Comma-separated task names. Empty means all tasks.",
    )
    parser.add_argument("--output-prefix", default="beast_systems_benchmark_latest")
    parser.add_argument(
        "--network-probe-evidence",
        default=os.environ.get("BEAST_NETWORK_PROBE_EVIDENCE", ""),
        help="Optional JSON packet-probe result to attach to the report, manifest, and evidence cards.",
    )
    args = parser.parse_args()

    live_lanes = [lane.strip() for lane in args.live_lanes.split(",") if lane.strip()]
    live_providers = [provider_from_preset(name) for name in args.live_provider.split(",") if name.strip()]
    if live_providers:
        live_providers = [replace(provider, timeout=args.live_timeout) for provider in live_providers]
    task_names = [name.strip() for name in args.task.split(",") if name.strip()]
    if args.live_agent and not live_providers and (not args.live_base_url or not args.live_model):
        raise SystemExit("--live-agent requires --live-base-url and --live-model")
    report = run_systems_benchmark(
        live=args.live_agent,
        live_base_url=args.live_base_url,
        live_model=args.live_model,
        live_api_key_env=args.live_api_key_env,
        live_timeout=args.live_timeout,
        live_max_tasks=args.live_max_tasks,
        live_lanes=live_lanes,
        live_max_tokens=args.live_max_tokens,
        live_prompt_mode=args.live_prompt_mode,
        live_json_mode=args.live_json_mode,
        live_providers=live_providers,
        task_names=task_names,
        live_only=args.live_only,
    )
    if args.network_probe_evidence:
        probe_path = Path(args.network_probe_evidence).expanduser().resolve()
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
        report = NetworkChronicleConnector().attach_benchmark_report(
            report,
            probe,
            source=f"file:{probe_path.name}",
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"{args.output_prefix}.json"
    md_path = OUT_DIR / f"{args.output_prefix}.md"
    if report.get("live_results"):
        artifact_dir = OUT_DIR / f"{args.output_prefix}_gauntlet"
        report["live_gauntlet_artifacts"] = write_live_gauntlet_artifacts(report, artifact_dir)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
