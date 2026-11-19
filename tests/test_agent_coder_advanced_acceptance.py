from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.compute.kv_transport import (
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
    bind_default_transport,
)


class CompressionRouter:
    def compress(self, tier, payload, **_kwargs):
        content = str(payload)
        return {
            "content": f"[{tier}] {content[:80]}",
            "fidelity": {"passed": True},
            "metrics": {
                "original_tokens": 20,
                "compressed_tokens": 8,
                "counted_savings_tokens": 12,
            },
            "governor": {"receipt_id": f"compression-{tier}"},
        }


class SpecialistDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, ir, route, *, run_id=""):
        self.calls.append((ir, route, run_id))
        return SimpleNamespace(
            dispatched=True,
            reason="specialist_output_accepted",
            response={"text": "Inspect the caller before changing the callee.", "model": "specialist-test"},
            receipt={"governor_outcome": "admit", "governor_receipt": "gov-1", "model": "specialist-test"},
        )


def test_advanced_preflight_executes_source_compression_and_governed_swarm_dispatch(tmp_path):
    transformed_source = "[longcodezip] def caller(): return callee()"
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    bind_default_transport(transport)
    transport.register_block(
        model="test",
        tokenizer="test",
        prompt_prefix=transformed_source,
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=1,
        num_heads=1,
        head_dim=1,
        seq_len=8,
        size_bytes=4,
        tensor_payload=b"fixture-kv",
        metadata={"payload_provenance": "synthetic_fixture"},
    )
    dispatcher = SpecialistDispatcher()
    coordinator = CoderIntegrationCoordinator(
        tmp_path,
        environ={
            "BEAST_COMPRESSION_TIERS": "1",
            "BEAST_SWARM_SPECIALIST": "1",
            "BEAST_ZERO_COPY_KV": "1",
        },
        compression_router=CompressionRouter(),
        vector_memory=SimpleNamespace(search=lambda *_args, **_kwargs: []),
        swarm_selector=lambda **_kwargs: {
            "selected": True,
            "reason": "specialist_required",
            "route": {"route": "local_specialist_adapter", "specialist_ref": "ollama://specialist-test"},
        },
        swarm_dispatcher=dispatcher,
    )

    packet = coordinator.prepare(
        objective="Refactor both caller and callee",
        source_context="def caller(): return callee()",
        source_files={"service.py": "def caller(): return callee()"},
        task_metadata={"run_id": "advanced-1", "provider": "ollama", "model": "test"},
    )

    payloads = [event["payload"] for event in packet["events"]]
    compression = next(item for item in payloads if item["capability"] == "compression.longcodezip")
    swarm = next(item for item in payloads if item["capability"] == "swarm_specialist")
    kv = next(item for item in payloads if item["capability"] == "kv_transport")
    assert compression["status"] == "fired"
    assert packet["source_files"]["service.py"].startswith("[longcodezip]")
    assert swarm["status"] == "fired"
    assert swarm["stage"] == "execution"
    assert swarm["operation"] == "specialist_dispatch"
    assert swarm["reason"] == "specialist_output_accepted"
    assert kv["status"] == "fired"
    assert kv["artifacts"]["provenance"] == "synthetic_fixture"
    assert dispatcher.calls and dispatcher.calls[0][2] == "advanced-1"
    assert any(item["capability"] == "swarm_specialist" for item in coordinator.advisory_context)


def test_canonical_coding_run_uses_effect_advanced_integrations_and_stream_cancellation(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "test_answer.py").write_text(
        "import answer\n\n\ndef test_value():\n    assert answer.VALUE == 2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "answer.py", "test_answer.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="advanced-canonical",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="local_nim",
        model="test",
        request={
            "context_files": ["answer.py"],
            "implementation_target": "answer.py",
            "required_test_files": ["test_answer.py"],
        },
    )["run_id"]
    approval_id = "advanced-mutation"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})

    transformed_source = "[longcodezip] VALUE = 1"
    transport = CrossEngineKVCacheTransport(storage_dir=root / ".beast" / "kv-test")
    bind_default_transport(transport)
    transport.register_block(
        model="test", tokenizer="test", prompt_prefix=transformed_source,
        system_prompt="beast-agent-coder", engine=CacheEngine.VLLM,
        location=CacheLocation.CPU, precision="fp16", num_layers=1,
        num_heads=1, head_dim=1, seq_len=4, size_bytes=4,
        tensor_payload=b"fixture-kv", metadata={"payload_provenance": "synthetic_fixture"},
    )
    dispatcher = SpecialistDispatcher()
    coordinator = CoderIntegrationCoordinator(
        root,
        environ={
            "BEAST_COMPRESSION_TIERS": "1",
            "BEAST_SWARM_SPECIALIST": "1",
            "BEAST_ZERO_COPY_KV": "1",
        },
        compression_router=CompressionRouter(),
        vector_memory=SimpleNamespace(search=lambda *_args, **_kwargs: []),
        swarm_selector=lambda **_kwargs: {
            "selected": True,
            "reason": "specialist_required",
            "route": {"route": "local_specialist_adapter", "specialist_ref": "ollama://specialist-test"},
        },
        swarm_dispatcher=dispatcher,
    )

    actions = iter([
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {"objective": "Change VALUE to 2"}, "approval_id": approval_id},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}, "approval_id": approval_id},
        {"decision_type": "tool", "tool_id": "worktree.verify", "arguments": {"command": [sys.executable, "-m", "pytest", "-q", "test_answer.py"]}, "approval_id": approval_id},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
    ])
    responses = []

    class Response:
        def __init__(self, action):
            self.action = action
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def close(self):
            self.closed = True

        def __iter__(self):
            for text in (json.dumps(self.action), " trailing output"):
                yield f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n".encode()

    def urlopen(*_args, **_kwargs):
        response = Response(next(actions))
        responses.append(response)
        return response

    monkeypatch.setenv("BEAST_NIM_PLANNER_STREAM", "1")
    monkeypatch.setattr("app.kernel.agents.nim_planner_provider._egress.urlopen", urlopen)
    provider = NIMPlannerProvider(model="test", base_url="http://nim.test/v1", api_key="test", max_retries=0)

    final = asyncio.run(AgentPlannerRuntime(
        engine,
        provider,
        max_turns=5,
        integration_coordinator=coordinator,
    ).run(run_id))

    assert final["state"] == "completed", (final.get("error"), final.get("checkpoint"))
    events = engine.store.events(run_id, after=0, limit=500)
    integration = {
        event["payload"]["capability"]: event["payload"]
        for event in events
        if event["event_type"] == "agent.integration.fired"
    }
    assert integration["compression.longcodezip"]["status"] == "fired"
    assert integration["kv_transport"]["artifacts"]["provenance"] == "synthetic_fixture"
    assert integration["swarm_specialist"]["operation"] == "specialist_dispatch"
    assert responses and all(response.closed for response in responses)
    interceptions = [event for event in events if event["event_type"] == "agent.stream.interception"]
    assert len(interceptions) == 5
    assert all(event["payload"]["upstream_cancel_requested"] for event in interceptions)
    completed_tools = [event for event in events if event["event_type"] == "agent.tool.completed"]
    assert completed_tools and all(event["payload"]["runtime"] == "effect_ts" for event in completed_tools)
