"""Tool execution through the real Effect TS runtime (Phase 1 FFI boundary)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.kernel.agents import effect_ts_bridge as E
from app.kernel.agents.effect_tool_executor import EffectToolExecutor
from app.kernel.agents.effect_ts_bridge import EffectTSBridge
from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import ToolRegistry, ToolValidationError


def make_spec(tool_id: str, handler=None, *, required=("path",)) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        version="1.0",
        title=tool_id,
        description="test tool",
        category="test",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "required": list(required)},
        output_schema={},
        handler=handler,
    )


@pytest.fixture(scope="module")
def bridge():
    b = EffectTSBridge()
    with b:
        yield b
    b.close()


@pytest.fixture()
def registry():
    return ToolRegistry(workspace_root="/tmp/beast-effect-tests")


def test_tool_runs_through_effect_runtime(bridge, registry):
    async def handler(args, ctx):
        return {"echo": args["path"], "target": ctx.execution_target}

    registry.register(make_spec("test.echo", handler))
    executor = EffectToolExecutor(registry, bridge)

    result = executor.execute("test.echo", {"path": "src/main.py"})
    assert result.value == {"echo": "src/main.py", "target": "local"}
    assert result.elapsed_ms >= 0


def test_retry_policy_retries_failed_tool(bridge, registry):
    attempts = {"n": 0}

    async def handler(args, ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("flaky backend")
        return {"ok": True, "attempt": attempts["n"]}

    registry.register(make_spec("test.flaky", handler))
    executor = EffectToolExecutor(registry, bridge)

    result = executor.execute("test.flaky", {"path": "x"}, retry_attempts=4, retry_base_ms=10)
    assert result.value == {"ok": True, "attempt": 3}
    assert attempts["n"] == 3


def test_timeout_policy_interrupts_tool(bridge, registry):
    async def handler(args, ctx):
        time.sleep(1.5)
        return {"late": True}

    registry.register(make_spec("test.slow", handler))
    executor = EffectToolExecutor(registry, bridge)

    started = time.monotonic()
    with pytest.raises(E.EffectError) as err:
        executor.execute("test.slow", {"path": "x"}, timeout_ms=150)
    elapsed = time.monotonic() - started

    assert err.value.tag == "TimeoutError"
    assert elapsed < 0.9, f"timeout policy did not interrupt ({elapsed:.2f}s)"


def test_cancel_stops_running_tool_fiber(bridge, registry):
    completed = {"done": False}

    async def handler(args, ctx):
        time.sleep(0.8)
        completed["done"] = True
        return {"done": True}

    registry.register(make_spec("test.cancellable", handler))
    executor = EffectToolExecutor(registry, bridge)

    fiber_id = executor.start("test.cancellable", {"path": "x"})
    executor.cancel(fiber_id)
    time.sleep(0.5)
    assert completed["done"] is False


def test_resource_bracket_releases_after_tool_failure(bridge, registry):
    events = []

    async def handler(args, ctx):
        raise RuntimeError("tool blew up")

    registry.register(make_spec("test.bracketed", handler))
    executor = EffectToolExecutor(registry, bridge)
    executor.register_resource(
        "test.bracketed",
        acquire=lambda: events.append("acquire"),
        release=lambda: events.append("release"),
    )

    with pytest.raises(E.EffectError):
        executor.execute("test.bracketed", {"path": "x"})
    assert events == ["acquire", "release"]


def test_input_validation_happens_before_effect_runtime(bridge, registry):
    registry.register(make_spec("test.needs_path", lambda args, ctx: {"ok": True}))
    executor = EffectToolExecutor(registry, bridge)

    with pytest.raises(ToolValidationError):
        executor.execute("test.needs_path", {})
