"""Phase 4: Effect-based plugin registration, hot reload, skills, dependencies."""

from __future__ import annotations

import os
import time

import pytest

from app.kernel.agents.effect_plugin_runtime import (
    EffectPluginRuntime,
    PluginDependencyError,
    PluginPolicy,
    PluginRegistrationError,
)
from app.kernel.agents.effect_ts_bridge import EffectError, EffectTSBridge
from app.kernel.agents.plugin_system import Skill
from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import ToolRegistry


@pytest.fixture(scope="module")
def bridge():
    b = EffectTSBridge()
    with b:
        yield b
    b.close()


def tool_spec(tool_id: str, handler=None) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        version="1.0",
        title=tool_id,
        description="plugin tool",
        category="test",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "required": ["path"]},
        handler=handler,
    )


class FakePlugin:
    def __init__(self, name, log, *, fail_times=0, sleep_s=0.0, tools=None, skills=None):
        self.name = name
        self.log = log
        self.fail_times = fail_times
        self.sleep_s = sleep_s
        self.tools = tools or []
        self.skills = skills or []
        self.attempts = 0

    async def initialize(self, runtime):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError(f"{self.name} transient failure")
        if self.sleep_s:
            time.sleep(self.sleep_s)
        self.log.append(f"init:{self.name}")

    async def shutdown(self):
        self.log.append(f"shutdown:{self.name}")

    def get_tools(self):
        return list(self.tools)

    def get_skills(self):
        return list(self.skills)


def policy(**kwargs) -> PluginPolicy:
    values = {"retry_attempts": 0, "retry_base_ms": 5, "timeout_ms": 3000}
    values.update(kwargs)
    return PluginPolicy(**values)


def test_dependency_order_drives_initialization(bridge):
    log: list[str] = []
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("c", FakePlugin("c", log), dependencies=["b"])
    runtime.register("b", FakePlugin("b", log), dependencies=["a"])
    runtime.register("a", FakePlugin("a", log))

    assert runtime.order() == ["a", "b", "c"]
    assert runtime.load_all() == {"a": True, "b": True, "c": True}
    assert log == ["init:a", "init:b", "init:c"]
    assert runtime.status()["order"] == ["a", "b", "c"]


def test_cycles_and_missing_dependencies_are_rejected(bridge):
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("x", FakePlugin("x", []), dependencies=["y"])
    runtime.register("y", FakePlugin("y", []), dependencies=["x"])
    with pytest.raises(PluginDependencyError, match="cycle"):
        runtime.order()

    other = EffectPluginRuntime(bridge=bridge, policy=policy())
    other.register("orphan", FakePlugin("orphan", []), dependencies=["ghost"])
    with pytest.raises(PluginDependencyError, match="ghost"):
        other.order()


def test_effect_retry_recovers_a_flaky_plugin(bridge):
    log: list[str] = []
    plugin = FakePlugin("flaky", log, fail_times=2)
    runtime = EffectPluginRuntime(
        bridge=bridge, policy=policy(retry_attempts=3, retry_base_ms=5)
    )
    runtime.register("flaky", plugin)

    runtime.load("flaky")

    assert plugin.attempts == 3
    assert log == ["init:flaky"]
    assert runtime.records["flaky"].status == "loaded"


def test_effect_timeout_marks_the_plugin_as_error(bridge):
    log: list[str] = []
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy(timeout_ms=150))
    runtime.register("slow", FakePlugin("slow", log, sleep_s=0.4))

    with pytest.raises(EffectError) as err:
        runtime.load("slow")

    assert err.value.tag == "TimeoutError"
    assert runtime.records["slow"].status == "error"
    assert "timed out" in runtime.records["slow"].error.lower()


def test_plugin_tools_and_skills_execute_through_effect(bridge, tmp_path):
    registry = ToolRegistry(workspace_root=str(tmp_path))

    async def echo(args, ctx):
        return {"echo": args["path"]}

    skill = Skill(
        "review",
        "Review",
        "Review a file",
        "Review {{path}} as {{style}}",
        tools=["demo.echo"],
        parameters={"style": "strict"},
    )
    plugin = FakePlugin(
        "demo",
        [],
        tools=[tool_spec("demo.echo", echo)],
        skills=[skill],
    )
    runtime = EffectPluginRuntime(registry, bridge=bridge, policy=policy())
    runtime.register("demo", plugin)

    runtime.load("demo")

    assert registry.get("demo.echo").tool_id == "demo.echo"
    assert runtime.list_skills() == [
        {
            "skill_id": "review",
            "name": "Review",
            "description": "Review a file",
            "category": "general",
            "tools": ["demo.echo"],
        }
    ]
    result = runtime.execute_skill(
        "review",
        {"path": "src/app.py"},
        arguments={"demo.echo": {"path": "src/app.py"}},
    )
    assert result["prompt"] == "Review src/app.py as strict"
    assert result["results"][0]["value"] == {"echo": "src/app.py"}


def test_hot_reload_restarts_changed_plugins_and_dependents(bridge, tmp_path):
    log: list[str] = []
    source = tmp_path / "demo_plugin.py"
    source.write_text("VERSION = 1\n", encoding="utf-8")

    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("a", FakePlugin("a", log), module_file=source)
    runtime.register("b", FakePlugin("b", log), dependencies=["a"])
    runtime.load_all()
    assert log == ["init:a", "init:b"]
    assert runtime.hot_reload() == []

    mtime = source.stat().st_mtime_ns
    source.write_text("VERSION = 2\n", encoding="utf-8")
    os.utime(source, ns=(mtime + 1_000_000_000, mtime + 1_000_000_000))

    assert runtime.hot_reload() == ["a", "b"]
    assert log == [
        "init:a",
        "init:b",
        "shutdown:b",
        "shutdown:a",
        "init:a",
        "init:b",
    ]
    assert runtime.hot_reload() == []


def test_unload_respects_dependents_and_shuts_down_in_reverse(bridge):
    log: list[str] = []
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("a", FakePlugin("a", log))
    runtime.register("b", FakePlugin("b", log), dependencies=["a"])
    runtime.load_all()

    with pytest.raises(PluginDependencyError, match="loaded dependents"):
        runtime.unload("a")

    assert runtime.unload_all() == ["b", "a"]
    assert log[-2:] == ["shutdown:b", "shutdown:a"]


def test_registration_rejects_duplicates_and_loaded_replacement(bridge):
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("demo", FakePlugin("demo", []))

    with pytest.raises(PluginRegistrationError, match="already registered"):
        runtime.register("demo", FakePlugin("demo", []))

    runtime.load("demo")
    with pytest.raises(PluginRegistrationError, match="unload"):
        runtime.register("demo", FakePlugin("demo", []), replace=True)


async def test_watch_loop_starts_and_stops(bridge):
    runtime = EffectPluginRuntime(bridge=bridge, policy=policy())
    runtime.register("demo", FakePlugin("demo", []))

    await runtime.start_watch(0.05)
    await runtime.stop_watch()

    assert runtime._watch_task is None
