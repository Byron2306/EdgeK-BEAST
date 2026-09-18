from __future__ import annotations

from pathlib import Path

from app.kernel.agents.core_repair_policy import planner_lifecycle_minimum, planner_turn_budget
from app.kernel.agents.ollama_planner_provider import (
    DEFAULT_OLLAMA_PLANNER_NUM_CTX,
    DEFAULT_OLLAMA_PLANNER_NUM_PREDICT,
    OllamaPlannerProvider,
)
from app.kernel.agents.planner_runtime import AgentPlannerRuntime


ROOT = Path(__file__).resolve().parents[2]


def test_local_mutation_default_can_complete_mandatory_lifecycle():
    run = {"mode": "agent", "provider": "ollama", "budget": {}}
    budget = planner_turn_budget(run, {})
    assert planner_lifecycle_minimum(run) == 8
    assert budget["effective"] == 12
    assert budget["effective"] >= budget["lifecycle_minimum"]
    assert budget["source"] == "local_mutation_default"
    assert budget["defaulted"] is True
    assert budget["below_lifecycle_minimum"] is False


def test_explicit_short_turn_cap_is_respected_but_truthfully_flagged():
    run = {"mode": "agent", "provider": "ollama", "budget": {"max_turns": 5}}
    budget = planner_turn_budget(run, {})
    assert budget["effective"] == 5
    assert budget["requested"] == 5
    assert budget["below_lifecycle_minimum"] is True
    assert budget["defaulted"] is False


def test_compact_prompt_preserves_contract_and_late_authority_repair_evidence():
    prompt = (
        "BEAST ACTION PLANNER. Controller only.\n"
        + ("middle-context-" * 800)
        + "\nAPPROVED ONE-USE AUTHORITY: approval-47"
        + "\nREPAIR CONTRACT: latest verifier failure is authoritative"
    )
    compacted = AgentPlannerRuntime._bounded_planner_prompt(prompt, 3600)
    assert len(compacted) <= 3600
    assert compacted.startswith("BEAST ACTION PLANNER")
    assert "<BEAST_MIDDLE_CONTEXT_COMPACTED>" in compacted
    assert "APPROVED ONE-USE AUTHORITY: approval-47" in compacted
    assert "REPAIR CONTRACT: latest verifier failure is authoritative" in compacted


def test_ollama_planner_defaults_are_one_canonical_runtime_profile(monkeypatch):
    monkeypatch.delenv("BEAST_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("BEAST_OLLAMA_NUM_PREDICT", raising=False)
    provider = OllamaPlannerProvider(model="qwen2.5:0.5b")
    assert DEFAULT_OLLAMA_PLANNER_NUM_CTX == 2048
    assert DEFAULT_OLLAMA_PLANNER_NUM_PREDICT == 128
    assert provider._num_ctx() == 2048
    assert provider._num_predict() == 128


def test_native_context_generation_uses_provider_output_budget_not_hardcoded_48(monkeypatch):
    monkeypatch.delenv("BEAST_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("BEAST_OLLAMA_NUM_PREDICT", raising=False)

    class Block:
        native_context_available = True
        context_id = "ctx-test"

    class Manager:
        def __init__(self):
            self.max_tokens = None
            self.context_options = None

        def get_or_create_context(self, *args, **kwargs):
            self.context_options = dict(kwargs.get("options") or {})
            return Block()

        def generate_with_context(self, block, suffix, max_tokens, **kwargs):
            self.max_tokens = max_tokens
            return {
                "response": '{"decision_type":"complete","arguments":{},"summary":"done"}',
                "prompt_eval_count": 20,
                "eval_count": max_tokens,
            }

    manager = Manager()
    provider = OllamaPlannerProvider(model="qwen2.5:0.5b", forge_kv_manager=manager)
    _block, result = provider._native_context_transaction(
        "stable prefix",
        "TURN: 1",
        {"run_id": "run-core-repair"},
        1,
    )
    assert manager.max_tokens == provider._num_predict() == 128
    assert manager.context_options["num_ctx"] == provider._num_ctx() == 2048
    assert result["eval_count"] == 128


def test_detached_renderer_uses_plannerdecision_and_keeps_repository_hints():
    client = (ROOT / "desktop-ide/renderer/js/ai/agent-client.js").read_text(encoding="utf-8")
    controller = (ROOT / "desktop-ide/renderer/js/ai/mode-controller.js").read_text(encoding="utf-8")
    root = (ROOT / "desktop-ide/renderer/js/beast-ai-coding.js").read_text(encoding="utf-8")

    assert "instructionFor(mode, clean, files, selection, localCoder, detachedPlanner)" in client
    assert "if (!detachedPlanner && localCoder && files.length > RELIABLE_LOCAL_PROFILE.maxFiles)" in client
    assert "Forwarding ${files.length} repository file hint(s) to the durable planner" in client
    assert "maxFiles:48" in root
    assert "plannerTurns:12" in root

    assert "plannerProtocol = false" in controller
    assert "canonical PlannerDecision protocol" in controller
    assert "Do not request or emit BEAST Action IR from the model." in controller


def test_endurance_workflow_installs_its_real_import_surface_before_running():
    workflow = (ROOT / ".github/workflows/agentic-loop-endurance.yml").read_text(encoding="utf-8")
    assert '"cryptography>=43,<48"' in workflow
    assert '"numpy>=2,<3"' in workflow
    assert "--collect-only --noconftest tests/test_agent_planner_runtime.py" in workflow
