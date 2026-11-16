"""Offline fixtures shared by the Episode Envelope and coding-crystal loop tests."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.kernel.agents.run_engine import AgentRunEngine


def make_assertion_repo(root: Path, *, module: str = "calc", constant: str = "RATE", actual: Any = 3,
                        expected: Any = 4, function: str = "rate", second_bug: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "beast@example.test")
    git("config", "user.name", "BEAST Test")
    source = f"{constant} = {actual!r}\n\n\ndef {function}():\n    return {constant}\n"
    test = (
        "import unittest\n\n"
        f"import {module}\n\n\n"
        "class AssertionCase(unittest.TestCase):\n"
        f"    def test_{function}(self):\n"
        f"        self.assertEqual({module}.{function}(), {expected!r})\n"
    )
    if second_bug:  # a second, independent defect the constant fix cannot repair
        source += f"\n\ndef double():\n    return {constant} * 3\n"
        test += f"        self.assertEqual({module}.double(), {expected!r} * 2)\n"
    (root / f"{module}.py").write_text(source, encoding="utf-8")
    (root / f"test_{module}.py").write_text(test, encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "initial")
    return root


def verify_command(module: str = "calc") -> list[str]:
    return ["python3", "-m", "unittest", "discover", "-p", f"test_{module}.py", "-q"]


def create_assertion_run(root: Path, *, module: str = "calc", task_family: str = "fix-failing-assertion",
                         objective: str = "Fix the failing assertion", implementation_target: str | None = None,
                         engine: AgentRunEngine | None = None) -> tuple[AgentRunEngine, str]:
    engine = engine or AgentRunEngine(root)
    target = f"{module}.py" if implementation_target is None else implementation_target
    request: dict[str, Any] = {
        "post_session_closure": "verified_handoff",
        "post_session_test_runner": "unittest",
        "required_test_files": [f"test_{module}.py"],
        "context_files": [target] if target else [],
        "implementation_target": target,
        "task_family": task_family,
    }
    run_id = engine.create_run(session_id="crystal-fabric", objective=objective, mode="agent",
                               provider="simulated", model="scripted", request=request)["run_id"]
    engine.store.create_approval(run_id, {"request_id": "mutate", "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, "mutate", {"approved": True, "scope": "run"})
    engine.store.create_approval(run_id, {
        "request_id": "verify", "tool_id": "worktree.verify",
        "safe_arguments": {"command": verify_command(module)}, "capabilities": [{"id": "worktree.verify"}],
    })
    engine.store.resolve_approval(run_id, "verify", {"approved": True, "scope": "run"})
    return engine, run_id


def learn_script(module: str = "calc", constant: str = "RATE", actual: Any = 3, expected: Any = 4) -> list[dict[str, Any]]:
    """The exploratory model trajectory that a crystal should later compress."""
    command = verify_command(module)
    return [
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "workspace.search_text", "arguments": {"query": constant, "path": "."}},
        {"decision_type": "tool", "tool_id": "workspace.read_range",
         "arguments": {"path": f"{module}.py", "start_line": 1, "line_count": 20}},
        {"decision_type": "tool", "tool_id": "workspace.read_range",
         "arguments": {"path": f"test_{module}.py", "start_line": 1, "line_count": 20}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {"objective": "fix assertion"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "arguments": {"command": command}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact",
         "arguments": {"path": f"{module}.py", "old_text": f"{constant} = {actual!r}", "new_text": f"{constant} = {expected!r}"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "arguments": {"command": command}},
        {"decision_type": "complete", "summary": "fixed"},
        {"decision_type": "complete", "summary": "fixed"},
        {"decision_type": "complete", "summary": "fixed"},
    ]


def run_learn(root: Path, envelope_path: Path, **repo_kwargs: Any) -> dict[str, Any]:
    """Run the exploratory scripted trajectory and return run, envelope and observations."""
    import asyncio

    from app.kernel.agents.planner_provider import ScriptedPlannerProvider
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

    module = repo_kwargs.get("module", "calc")
    make_assertion_repo(root, **repo_kwargs)
    engine, run_id = create_assertion_run(root, module=module)
    script = learn_script(module, repo_kwargs.get("constant", "RATE"), repo_kwargs.get("actual", 3),
                          repo_kwargs.get("expected", 4))
    envelopes = EpisodeEnvelopeStore(envelope_path)
    final = asyncio.run(AgentPlannerRuntime(engine, ScriptedPlannerProvider(script), max_turns=14,
                                            envelope_store=envelopes).run(run_id))
    return {"engine": engine, "run_id": run_id, "final": final, "envelope": envelopes.get(run_id),
            "observations": final["checkpoint"]["planner"]["observations"]}


HELD_OUT_VARIANTS = (
    {"module": "pricing", "constant": "TAX", "actual": 7, "expected": 9, "function": "tax"},
    {"module": "limits", "constant": "MAX_ITEMS", "actual": 10, "expected": 12, "function": "max_items"},
    {"module": "greeting", "constant": "WORD", "actual": "hi", "expected": "hello", "function": "word"},
)
MISFIT_ALREADY_GREEN = {"module": "stable", "constant": "LEVEL", "actual": 5, "expected": 5, "function": "level"}
SECOND_BUG_VARIANT = {"module": "orders", "constant": "UNIT", "actual": 2, "expected": 3, "function": "unit",
                      "second_bug": True}


class CountingProvider:
    """Scripted fallback provider that records whether the model was consulted at all."""

    def __init__(self, decisions: list[dict[str, Any]] | None = None):
        from app.kernel.agents.planner_provider import ScriptedPlannerProvider

        self.inner = ScriptedPlannerProvider(list(decisions or [{"decision_type": "blocked", "blocker": "fallback"}]))
        self.last_route = self.inner.last_route
        self.calls = 0

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
        self.calls += 1
        return await self.inner.next_decision(prompt, run=run, turn=turn)


def crystal_stack(base: Path) -> dict[str, Any]:
    """Registry, signing authority and one-use ledger; the Ed25519 key is generated per test, never persisted."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.kernel.compute.coding_crystals import CodingCrystalAuthority, CodingCrystalRegistry
    from app.kernel.integration.one_use_capability import OneUseCapabilityLedger

    base.mkdir(parents=True, exist_ok=True)
    authority = CodingCrystalAuthority(Ed25519PrivateKey.generate(), key_id="test-coding-crystal-key")
    ledger = OneUseCapabilityLedger({CodingCrystalAuthority.AUTHORITY: authority.verifier()}, base / "capabilities.sqlite3")
    return {"registry": CodingCrystalRegistry(base / "coding_crystals.sqlite3"), "authority": authority, "ledger": ledger}


def run_with_planner(root: Path, planner: Any, *, variant: dict[str, Any], provider: Any = None,
                     envelope_path: Path | None = None, request_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    import asyncio

    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

    module = variant.get("module", "calc")
    make_assertion_repo(root, **variant)
    engine, run_id = create_assertion_run(root, module=module, **(request_overrides or {}))
    provider = provider or CountingProvider()
    envelopes = EpisodeEnvelopeStore(envelope_path or root.parent / f"{root.name}-envelopes.sqlite3")
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=14, envelope_store=envelopes,
                                            crystal_planner=planner).run(run_id))
    events = engine.store.events(run_id, limit=1000)
    return {"engine": engine, "run_id": run_id, "final": final, "provider": provider, "events": events,
            "observations": final["checkpoint"]["planner"]["observations"], "envelope": envelopes.get(run_id)}
