"""Phase 6: centralized tool registry - Zod schemas, approval, targets, streaming."""

from __future__ import annotations

import subprocess

import pytest

from app.kernel.agents.effect_tool_executor import EffectToolExecutor
from app.kernel.agents.effect_ts_bridge import EffectTSBridge
from app.kernel.agents.tool_models import ToolEffect as ModelToolEffect
from app.kernel.agents.tool_models import ToolRisk as ModelToolRisk
from app.kernel.agents.tool_models import ToolSpec as ModelToolSpec
from app.kernel.agents.tool_registry import (
    ContainerToolExecutor,
    ExecutionTarget,
    LocalToolExecutor,
    SSHToolExecutor,
    ToolApprovalError,
    ToolContext,
    ToolEffect,
    ToolRegistry,
    ToolRisk,
    ToolSpec,
    ToolValidationError,
)
from app.kernel.agents.zod_schemas_v2 import EnhancedToolSpec
from app.kernel.agents.zod_schemas_v2 import ExecutionTarget as ZodExecutionTarget
from app.kernel.agents.zod_schemas_v2 import ToolEffect as ZodToolEffect
from app.kernel.agents.zod_schemas_v2 import ToolRisk as ZodToolRisk


@pytest.fixture(scope="module")
def bridge():
    b = EffectTSBridge()
    with b:
        yield b
    b.close()


def command_spec(tool_id: str, *, targets=(ExecutionTarget.LOCAL,)) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        version="1.0",
        title=tool_id,
        description="run a command",
        category="test",
        risk=ToolRisk.MEDIUM,
        effect=ToolEffect.EXECUTE,
        input_schema={
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
            "additionalProperties": False,
        },
        targets=list(targets),
        timeout_seconds=30,
    )


def context(target: str = "local", **overrides) -> ToolContext:
    values = {
        "run_id": "run-1",
        "session_id": "sess-1",
        "workspace_root": "/tmp/beast-phase6",
        "execution_target": target,
    }
    values.update(overrides)
    return ToolContext(**values)


# -- schema validation ------------------------------------------------------


def test_input_schema_rejects_missing_wrong_type_and_extra_arguments():
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(command_spec("test.cmd"))

    with pytest.raises(ToolValidationError, match="required property is missing"):
        registry.validate_input("test.cmd", {})
    with pytest.raises(ToolValidationError, match="expected string"):
        registry.validate_input("test.cmd", {"command": 7})
    with pytest.raises(ToolValidationError, match="unexpected properties"):
        registry.validate_input("test.cmd", {"command": "ls", "shell": True})
    assert registry.validate_input("test.cmd", {"command": "ls"}) == {"command": "ls"}


def test_output_schema_is_validated_after_execution():
    async def handler(args, ctx):
        return {"status": 5}

    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(
        ToolSpec(
            tool_id="test.output",
            title="output",
            description="returns the wrong shape",
            category="test",
            risk=ToolRisk.LOW,
            effect=ToolEffect.READ,
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string"}},
            },
            handler=handler,
        )
    )

    import asyncio

    with pytest.raises(ToolValidationError, match="invalid output"):
        asyncio.run(registry.execute("test.output", {}, context()))


# -- Zod registration -------------------------------------------------------


def test_register_zod_converts_spec_and_keeps_schema_contract(bridge):
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")

    async def handler(args, ctx):
        return {"wrote": args["path"]}

    enhanced = EnhancedToolSpec(
        tool_id="zod.write",
        title="Zod Write",
        description="write a file",
        category="files",
        risk=ZodToolRisk.LOW,
        effect=ZodToolEffect.WRITE,
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
        targets=[ZodExecutionTarget.LOCAL],
        requires_approval=False,
        timeout_seconds=15,
    )

    spec = registry.register_zod(enhanced, handler=handler)

    assert isinstance(spec, ToolSpec)
    assert spec.effect is ToolEffect.WRITE
    assert spec.risk is ToolRisk.LOW
    assert spec.targets == [ExecutionTarget.LOCAL]
    assert spec.input_schema["additionalProperties"] is False
    assert spec.input_schema["x-bast-tool"]["tool_id"] == "zod.write"
    with pytest.raises(ToolValidationError):
        registry.validate_input("zod.write", {})

    result = EffectToolExecutor(registry, bridge).execute("zod.write", {"path": "a.txt"})
    assert result.value == {"wrote": "a.txt"}


def test_register_zod_maps_execute_and_promotion_effects():
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    base = dict(
        tool_id="zod.exec",
        title="Zod Exec",
        description="run",
        category="exec",
        input_schema={"type": "object", "properties": {}},
    )
    execution = registry.register_zod(
        EnhancedToolSpec(**base, effect=ZodToolEffect.EXECUTE), handler=lambda args, ctx: {}
    )
    promotion = registry.register_zod(
        EnhancedToolSpec(**{**base, "tool_id": "zod.promote"}, effect=ZodToolEffect.PROMOTION),
        handler=lambda args, ctx: {},
    )

    assert execution.effect is ToolEffect.EXECUTE
    assert promotion.effect is ToolEffect.PROMOTION


# -- approval flow ----------------------------------------------------------


def test_approval_callback_can_deny_and_allow(bridge):
    calls: list[tuple[str, dict]] = []

    async def deny(tool_id, payload):
        calls.append((tool_id, payload))
        return False

    registry = ToolRegistry(workspace_root="/tmp/beast-phase6", approval_callback=deny)
    registry.register(
        ToolSpec(
            tool_id="test.gated",
            title="gated",
            description="needs approval",
            category="test",
            risk=ToolRisk.HIGH,
            effect=ToolEffect.WRITE,
            input_schema={"type": "object", "properties": {}},
            requires_approval=True,
            handler=lambda args, ctx: {"ok": True},
        )
    )
    executor = EffectToolExecutor(registry, bridge)

    with pytest.raises(ToolApprovalError):
        executor.execute("test.gated", {}, context=context())
    assert calls[0][0] == "test.gated"
    assert calls[0][1]["context"]["execution_target"] == "local"

    async def allow(tool_id, payload):
        return True

    registry.approval_callback = allow
    assert executor.execute("test.gated", {}, context=context()).value == {"ok": True}


def test_authorize_rejects_unsupported_execution_target():
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(command_spec("test.local_only"))
    executor = EffectToolExecutor.__new__(EffectToolExecutor)  # no bridge needed

    import asyncio

    with pytest.raises(Exception) as err:
        asyncio.run(registry.authorize("test.local_only", {"command": "ls"}, context("ssh")))
    assert "does not support target" in str(err.value)


# -- execution targets ------------------------------------------------------


def test_ssh_executor_builds_batchmode_command(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("app.kernel.agents.tool_registry.subprocess.run", fake_run)
    executor = SSHToolExecutor("deploy@example.com", "/srv/app", "sess-1")

    import asyncio

    result = asyncio.run(executor.execute("test.cmd", {"command": "pytest -q"}, context("ssh")))

    assert captured["command"] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "deploy@example.com",
        "cd /srv/app && pytest -q",
    ]
    assert captured["kwargs"]["cwd"] is None
    assert result["status"] == "completed"
    assert result["target"] == "ssh"


def test_container_executor_builds_docker_exec_command(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr("app.kernel.agents.tool_registry.subprocess.run", fake_run)
    executor = ContainerToolExecutor("beast-dev", "/workspace/repo")

    import asyncio

    result = asyncio.run(executor.execute("test.cmd", {"command": "npm test"}, context("container")))

    assert captured["command"] == [
        "docker",
        "exec",
        "-w",
        "/workspace/repo",
        "beast-dev",
        "sh",
        "-lc",
        "npm test",
    ]
    assert result["status"] == "failed"
    assert result["exit_code"] == 1


def test_effect_executor_routes_remote_targets_through_registry_executor(bridge, monkeypatch):
    seen: list[str] = []

    def fake_run(command, **kwargs):
        seen.append(command[0])
        return subprocess.CompletedProcess(command, 0, stdout="remote\n", stderr="")

    monkeypatch.setattr("app.kernel.agents.tool_registry.subprocess.run", fake_run)
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(command_spec("test.cmd", targets=(ExecutionTarget.LOCAL, ExecutionTarget.SSH)))
    registry.register_executor(ExecutionTarget.SSH, SSHToolExecutor("h1", "/srv", "s"))

    result = EffectToolExecutor(registry, bridge).execute(
        "test.cmd", {"command": "ls"}, context=context("ssh")
    )

    assert result.execution_target == "ssh"
    assert seen == ["ssh"]


def test_local_command_execution_still_uses_the_machine(bridge, tmp_path):
    registry = ToolRegistry(workspace_root=str(tmp_path))
    registry.register(command_spec("test.cmd"))

    result = EffectToolExecutor(registry, bridge).execute(
        "test.cmd", {"command": "printf hello"}, context=context(workspace_root=str(tmp_path))
    )

    assert result.value["stdout"] == "hello"
    assert result.value["status"] == "completed"
    assert result.execution_target == "local"


# -- streaming --------------------------------------------------------------


def test_execute_stream_emits_started_chunks_and_result():
    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(command_spec("test.stream"))
    registry.register_executor(ExecutionTarget.LOCAL, LocalToolExecutor("/tmp"))

    import asyncio

    async def collect():
        return [
            event
            async for event in registry.execute_stream(
                "test.stream", {"command": "printf 'one\\ntwo\\n'"}, context()
            )
        ]

    events = asyncio.run(collect())

    assert [event["type"] for event in events] == ["started", "chunk", "chunk", "result"]
    assert events[0]["tool_id"] == "test.stream"
    assert [event["data"] for event in events[1:3]] == ["one", "two"]
    assert events[-1]["result"]["status"] == "completed"
    assert events[-1]["result"]["exit_code"] == 0


def test_execute_stream_reports_authorization_failure_without_running():
    async def deny(tool_id, payload):
        return False

    registry = ToolRegistry(workspace_root="/tmp/beast-phase6", approval_callback=deny)
    registry.register(
        ToolSpec(
            tool_id="test.gated_stream",
            title="gated",
            description="needs approval",
            category="test",
            risk=ToolRisk.HIGH,
            effect=ToolEffect.WRITE,
            input_schema={"type": "object", "properties": {}},
            requires_approval=True,
        )
    )

    import asyncio

    async def collect():
        return [
            event
            async for event in registry.execute_stream("test.gated_stream", {}, context())
        ]

    events = asyncio.run(collect())

    assert len(events) == 1
    assert events[0]["type"] == "failed"
    assert "not approved" in events[0]["error"]


# -- legacy contract stays intact ------------------------------------------


def test_legacy_tool_models_spec_still_registers():
    async def handler(args, ctx):
        return {"path": args["path"]}

    registry = ToolRegistry(workspace_root="/tmp/beast-phase6")
    registry.register(
        ModelToolSpec(
            tool_id="legacy.read",
            version="1.0",
            title="legacy",
            description="legacy spec",
            category="test",
            risk=ModelToolRisk.LOW,
            effect=ModelToolEffect.READ,
            input_schema={"type": "object", "required": ["path"]},
            handler=handler,
        )
    )

    assert registry.get_spec("legacy.read").tool_id == "legacy.read"
