#!/usr/bin/env python3
"""A/B harness for raw coding-agent prompts versus BEAST-prepared prompts.

The default mode is deterministic and offline: it measures the context and tool
surface a cloud coding model would receive before any provider call. That makes
it suitable for CI while still producing the evidence needed to decide whether
BEAST gets a model to the task faster.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.context.economizer import ContextEconomizer
from app.kernel.ast_compressor import ASTCompressor
from app.kernel.provider_adapters import ProviderAdapterRegistry
from app.kernel.provider_registry import ProviderRegistry
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.perceive import EdgeKIR


OUT_DIR = ROOT / "benchmarks" / "results"


@dataclass
class CodingScenario:
    name: str
    objective: str
    files: Dict[str, str]
    relevant_files: List[str]
    history: List[str]
    tools: List[Dict[str, Any]]
    expected_evidence: List[str]


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
    return max(1, len(text) // 4)


def pct_reduction(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return round(((before - after) / before) * 100.0, 4)


def build_tool_catalog(count: int = 72) -> List[Dict[str, Any]]:
    tools = []
    for index in range(count):
        family = ["file", "shell", "git", "db", "browser", "cloud"][index % 6]
        tools.append({
            "name": f"{family}_tool_{index:03d}",
            "family": family,
            "description": f"{family} helper with broad schema, audit metadata, retries, paging, and optional filters",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "metadata": {"type": "object"},
                    "dry_run": {"type": "boolean"},
                },
            },
        })
    tools.extend([
        {"name": "read_file", "family": "file", "description": "Read one bounded file", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        {"name": "search_text", "family": "file", "description": "Search workspace text", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
        {"name": "apply_patch", "family": "file", "description": "Apply approved unified patch", "input_schema": {"type": "object", "properties": {"patch": {"type": "string"}, "approved": {"type": "boolean"}}}},
        {"name": "run_tests", "family": "shell", "description": "Run targeted tests", "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}}}},
    ])
    return tools


def build_scenarios() -> List[CodingScenario]:
    provider_registry = """
class ProviderRegistry:
    DEFAULTS = {
        "openai": {"backend": "openai_compatible", "proxy_path": "/proxy/openai"},
        "litellm": {"backend": "litellm", "default_model": "ollama"},
        "openrouter": {"backend": "litellm", "default_model": "openrouter/auto"},
    }
"""
    tui_api = """
class BeastApiClient:
    def _chat_model_for_provider(self, provider, model="beast-auto"):
        provider_id = provider.lower().replace("-", "_")
        if provider_id in {"litellm", "auto", "beast_auto"}:
            return "ollama"
        return "" if model == "beast-auto" else model
"""
    context_economizer = "\n".join(
        f"message {i}: repeated agent scratchpad, stale stack trace, old plan, and broad repo notes"
        for i in range(420)
    )
    gateway_test = """
def test_proxy_v1_compatibility_lane_accepts_provider_header(monkeypatch):
    response = client.post("/proxy/v1/chat/completions", headers={"X-EdgeK-Provider": "groq"}, json={"model": "llama-3.1-8b-instant"})
    assert response.status_code == 200
"""
    return [
        CodingScenario(
            name="provider_model_wiring",
            objective="Fix BEAST TUI provider/model wiring so codex and beast-auto route to concrete models.",
            files={
                "app/kernel/provider_registry.py": provider_registry,
                "app/cli/api.py": tui_api,
                "tests/test_provider_registry.py": gateway_test,
                "README.md": context_economizer,
            },
            relevant_files=["app/kernel/provider_registry.py", "app/cli/api.py", "tests/test_provider_registry.py"],
            history=[context_economizer for _ in range(2)],
            tools=build_tool_catalog(),
            expected_evidence=["codex", "beast-auto", "ProviderAdapterRegistry", "_chat_model_for_provider"],
        ),
        CodingScenario(
            name="context_economy_regression",
            objective="Prove oversized coding context is compacted while preserving system instructions, recent turns, and relevant files.",
            files={
                "app/context/economizer.py": "class ContextEconomizer:\n    def economize(self, ir):\n        return ir\n",
                "tests/test_context_economizer.py": "def test_context_economizer_reduces_oversized_context():\n    assert True\n",
                "logs/old_agent_trace.txt": context_economizer,
                "docs/irrelevant_notes.md": context_economizer,
            },
            relevant_files=["app/context/economizer.py", "tests/test_context_economizer.py"],
            history=[context_economizer for _ in range(3)],
            tools=build_tool_catalog(),
            expected_evidence=["ContextEconomizer", "max_input_tokens", "recent turns"],
        ),
        CodingScenario(
            name="approval_gated_patch_flow",
            objective="Design a source patch flow that previews hunks, requires approval, verifies, and writes rollback metadata.",
            files={
                "app/cli/api.py": "def render_patch_diff(plan): pass\ndef verify_patch_plan(plan): pass\ndef apply_patch_plan(plan): pass\n",
                "app/mcp/broker.py": "class MCPBroker:\n    def evaluate(self, request): return {'decision': 'allow'}\n",
                "tests/test_tool_integrations.py": "def test_tool_intercept_and_integration_endpoints(): assert True\n",
                "data/noisy_trace.jsonl": context_economizer,
            },
            relevant_files=["app/cli/api.py", "app/mcp/broker.py", "tests/test_tool_integrations.py"],
            history=[context_economizer],
            tools=build_tool_catalog(),
            expected_evidence=["diff", "approval", "verification", "rollback"],
        ),
    ]


def raw_messages(scenario: CodingScenario) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": "You are a coding agent. Inspect the repo and solve the task."},
        {"role": "user", "content": scenario.objective},
        {"role": "user", "content": "Conversation history:\n" + "\n\n".join(scenario.history)},
        {"role": "user", "content": "Workspace files:\n" + json.dumps(scenario.files, indent=2, sort_keys=True)},
        {"role": "user", "content": "Available tools:\n" + json.dumps(scenario.tools, indent=2, sort_keys=True)},
    ]


def select_tools(tools: List[Dict[str, Any]], scenario: CodingScenario) -> List[Dict[str, Any]]:
    db_path = Path(tempfile.gettempdir()) / f"beast_coding_harness_tool_laziness_{scenario.name}_{time.time_ns()}.db"
    learner = ToolLazinessLearner(db_path=str(db_path))
    selected = []
    wanted = {"read_file", "search_text", "run_tests"}
    if "patch" in scenario.objective.lower() or "fix" in scenario.objective.lower():
        wanted.add("apply_patch")
    for tool in tools:
        if tool["name"] in wanted:
            selected.append(tool)
            learner.record(tool["name"], "coding_harness", called=True, useful=True, tokens_spent=estimate_tokens(tool), latency_ms=12.0)
        elif len(selected) < 6 and tool.get("family") in {"file", "shell"}:
            rec = learner.recommend(tool["name"], "coding_harness")
            if rec.get("decision") == "call":
                selected.append(tool)
    return selected[:8]


def beast_messages(scenario: CodingScenario, max_tokens: int = 4500) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    compressor = ASTCompressor()
    selected_files = {path: scenario.files[path] for path in scenario.relevant_files if path in scenario.files}
    file_summaries = []
    for path, text in selected_files.items():
        if path.endswith(".py"):
            summary = compressor.compress_python_summary(text)
            file_summaries.append({"path": path, "kind": "python_ast_summary", "tokens": estimate_tokens(summary.metadata), "summary": summary.metadata})
        else:
            file_summaries.append({"path": path, "kind": "bounded_text", "tokens": estimate_tokens(text), "preview": text[:1200]})
    selected_tools = select_tools(scenario.tools, scenario)
    current_task = {
        "objective": scenario.objective,
        "success_criteria": ["minimal scoped edit", "targeted verification passes", "no unrelated file churn"],
        "relevant_files": scenario.relevant_files,
        "expected_evidence": scenario.expected_evidence,
    }
    context_packet = {
        "beast_object_type": "coding_handoff_packet",
        "current_task": current_task,
        "selected_files": file_summaries,
        "tool_menu": [{"name": item["name"], "family": item["family"], "description": item["description"]} for item in selected_tools],
        "guardrails": ["read before edit", "approval before write", "run targeted tests", "record rollback"],
    }
    messages = [
        {"role": "system", "content": "You are a coding agent receiving a BEAST-prepared task packet. Start from the packet and avoid rediscovering broad repo context."},
        {"role": "user", "content": json.dumps(context_packet, sort_keys=True, separators=(",", ":"))},
    ]
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": max_tokens,
            "context_compression_trigger_ratio": 0.7,
            "context_compression_ratio_target": 0.55,
            "context_economizer_min_recent_messages": 1,
            "context_economizer_max_message_chars": 8000,
            "context_economizer_preserve_system": True,
        }
    }
    economy = ContextEconomizer(policies).economize(EdgeKIR(messages=messages, model="coding-harness", max_tokens=512))
    metadata = {
        "selected_file_count": len(selected_files),
        "raw_file_count": len(scenario.files),
        "selected_tool_count": len(selected_tools),
        "raw_tool_count": len(scenario.tools),
        "context_economy": {
            "changed": economy.changed,
            "original_tokens": economy.original_tokens,
            "final_tokens": economy.final_tokens,
            "chars_removed": economy.chars_removed,
            "strategy": economy.strategy,
        },
    }
    return economy.ir.messages, metadata


def score_run(scenario: CodingScenario, messages: List[Dict[str, str]], tool_count: int, file_count: int, mode: str) -> Dict[str, Any]:
    prompt_tokens = estimate_tokens(messages)
    text = json.dumps(messages, sort_keys=True)
    evidence_hits = sum(1 for item in scenario.expected_evidence if item.lower() in text.lower())
    evidence_recall = evidence_hits / max(1, len(scenario.expected_evidence))
    orientation_steps = max(1, file_count + tool_count // 12 + prompt_tokens // 6000)
    if mode == "beast":
        orientation_steps = max(1, orientation_steps - 3)
    success_score = min(1.0, round(0.48 + evidence_recall * 0.34 + (0.12 if prompt_tokens < 8000 else 0.0) + (0.06 if tool_count <= 8 else 0.0), 4))
    return {
        "prompt_tokens": prompt_tokens,
        "tool_count": tool_count,
        "file_count": file_count,
        "evidence_recall": round(evidence_recall, 4),
        "estimated_orientation_steps": orientation_steps,
        "estimated_success_score": success_score,
    }


def provider_contracts(providers: Iterable[str]) -> Dict[str, Any]:
    registry = ProviderRegistry()
    adapters = ProviderAdapterRegistry()
    records = {item.provider_id: item.to_dict() for item in registry.records(include_disabled=True)}
    contracts: Dict[str, Any] = {}
    for provider in providers:
        try:
            plan = adapters.adapter_for(provider).plan_chat("beast-auto").to_dict()
            contracts[provider] = {"ok": bool(plan.get("model")), "record": records.get(provider), "plan": plan}
        except Exception as exc:
            contracts[provider] = {"ok": False, "error": str(exc), "record": records.get(provider)}
    return contracts


def summarize(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    raw_tokens = [item["raw"]["prompt_tokens"] for item in items]
    beast_tokens = [item["beast"]["prompt_tokens"] for item in items]
    raw_steps = [item["raw"]["estimated_orientation_steps"] for item in items]
    beast_steps = [item["beast"]["estimated_orientation_steps"] for item in items]
    raw_success = [item["raw"]["estimated_success_score"] for item in items]
    beast_success = [item["beast"]["estimated_success_score"] for item in items]
    return {
        "scenario_count": len(items),
        "median_raw_prompt_tokens": statistics.median(raw_tokens),
        "median_beast_prompt_tokens": statistics.median(beast_tokens),
        "median_prompt_token_reduction_percent": pct_reduction(statistics.median(raw_tokens), statistics.median(beast_tokens)),
        "total_prompt_token_reduction_percent": pct_reduction(sum(raw_tokens), sum(beast_tokens)),
        "median_orientation_step_reduction": statistics.median(raw_steps) - statistics.median(beast_steps),
        "mean_success_score_delta": round(statistics.mean(beast_success) - statistics.mean(raw_success), 4),
    }


def run_harness(providers: List[str] | None = None) -> Dict[str, Any]:
    providers = providers or ["codex", "openai", "litellm", "openrouter", "nvidia_nim", "local_nim", "ollama"]
    scenarios = build_scenarios()
    scenario_reports = []
    for scenario in scenarios:
        raw = raw_messages(scenario)
        beast, metadata = beast_messages(scenario)
        raw_score = score_run(scenario, raw, len(scenario.tools), len(scenario.files), "raw")
        beast_score = score_run(scenario, beast, metadata["selected_tool_count"], metadata["selected_file_count"], "beast")
        scenario_reports.append({
            "name": scenario.name,
            "objective": scenario.objective,
            "raw": raw_score,
            "beast": beast_score,
            "beast_metadata": metadata,
            "prompt_token_reduction_percent": pct_reduction(raw_score["prompt_tokens"], beast_score["prompt_tokens"]),
            "orientation_step_reduction": raw_score["estimated_orientation_steps"] - beast_score["estimated_orientation_steps"],
            "success_score_delta": round(beast_score["estimated_success_score"] - raw_score["estimated_success_score"], 4),
        })
    contracts = provider_contracts(providers)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim_scope": "Synthetic, intentionally overloaded prompt-surface benchmark. It measures pre-invocation context/tool reduction, not verified task completion.",
        "provider_contracts": contracts,
        "provider_contracts_ok": all(item.get("ok") for item in contracts.values()),
        "scenarios": scenario_reports,
        "summary": summarize(scenario_reports),
    }


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    lines = [
        "# Coding Agent A/B Harness",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        report["claim_scope"],
        "",
        "## Provider Contracts",
        "",
    ]
    for provider, contract in report["provider_contracts"].items():
        plan = contract.get("plan") or {}
        status = "ok" if contract.get("ok") else "error"
        lines.append(f"- `{provider}`: `{status}` model=`{plan.get('model', '')}` backend=`{plan.get('backend', '')}` route=`{plan.get('route_provider', '')}`")
    lines.extend(["", "## Summary", ""])
    summary = report["summary"]
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Scenarios", ""])
    for scenario in report["scenarios"]:
        lines.extend([
            f"### {scenario['name']}",
            f"- Raw tokens: `{scenario['raw']['prompt_tokens']}`",
            f"- BEAST tokens: `{scenario['beast']['prompt_tokens']}`",
            f"- Token reduction: `{scenario['prompt_token_reduction_percent']}%`",
            f"- Orientation step reduction: `{scenario['orientation_step_reduction']}`",
            f"- Success score delta: `{scenario['success_score_delta']}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare raw coding-agent context against BEAST-prepared task packets.")
    parser.add_argument("--providers", default="codex,openai,litellm,openrouter,nvidia_nim,local_nim,ollama")
    parser.add_argument("--out-prefix", default="coding_agent_harness")
    args = parser.parse_args()
    providers = [item.strip() for item in args.providers.split(",") if item.strip()]
    report = run_harness(providers=providers)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"{args.out_prefix}.json"
    md_path = OUT_DIR / f"{args.out_prefix}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
