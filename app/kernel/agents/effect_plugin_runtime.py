"""Effect-based plugin runtime for BEAST (Phase 4).

Registration, dependency resolution, lifecycle hooks, hot reload and skills
all run as Effect programs through the real Effect TS runtime in
``desktop-ide/scripts/effect-rpc.mjs``:

* **registration** - plugins are records with declared dependencies; nothing is
  imported or initialized until :meth:`EffectPluginRuntime.load_all` runs them in
  topological order.
* **lifecycle** - ``initialize`` / ``shutdown`` hooks are Effect ``call`` leaves
  wrapped in the runtime's retry and timeout policy, so a flaky plugin is
  retried by ``Effect.retry`` and a hung one is interrupted by ``Effect.timeout``.
* **hot reload** - in development, plugin source files are watched by mtime;
  changed plugins (and their dependents) are shut down and re-initialized, and
  their tools/skills are re-registered.
* **skills** - a skill is a prompt template plus a tool bundle; execution renders
  the prompt and runs the bundled tools through ``EffectToolExecutor``.

The runtime is duck-typed against the existing ``plugin_system.Plugin`` /
``Skill`` classes, so legacy plugins can be registered without modification.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.kernel.agents import effect_ts_bridge as E
from app.kernel.agents.effect_ts_bridge import EffectTSBridge, get_bridge
from app.kernel.agents.effect_tool_executor import EffectToolExecutor
from app.kernel.agents.tool_registry import ToolRegistry


class PluginError(RuntimeError):
    pass


class PluginNotFound(PluginError):
    pass


class PluginDependencyError(PluginError):
    pass


class PluginRegistrationError(PluginError):
    pass


@dataclass
class PluginPolicy:
    """Effect policies applied to plugin lifecycle hooks."""

    retry_attempts: int = 1
    retry_base_ms: int = 20
    timeout_ms: int = 5000

    def wrap(self, program: Dict[str, Any]) -> Dict[str, Any]:
        wrapped = program
        if self.retry_attempts > 0:
            wrapped = E.retry_exponential(wrapped, count=self.retry_attempts, base_ms=self.retry_base_ms)
        if self.timeout_ms > 0:
            wrapped = E.timeout(wrapped, ms=self.timeout_ms)
        return wrapped


@dataclass
class PluginRecord:
    name: str
    plugin: Any
    dependencies: tuple[str, ...] = ()
    version: str = ""
    module_file: Optional[Path] = None
    status: str = "registered"
    error: str = ""
    loaded_at: float = 0.0
    mtime_ns: int = 0
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "status": self.status,
            "error": self.error,
            "loaded_at": self.loaded_at,
            "module_file": str(self.module_file or ""),
            "tools": list(self.tools),
            "skills": list(self.skills),
        }


class EffectPluginRuntime:
    """Load, reload and execute BEAST plugins through the Effect TS runtime."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        *,
        bridge: Optional[EffectTSBridge] = None,
        policy: Optional[PluginPolicy] = None,
    ) -> None:
        self.registry = tool_registry
        self.bridge = bridge or get_bridge()
        self.policy = policy or PluginPolicy()
        self.records: Dict[str, PluginRecord] = {}
        self.skills: Dict[str, Any] = {}
        self._registered_ops: set[str] = set()
        self._watch_task: Optional[asyncio.Task] = None
        self._watching = False
        self.executor = EffectToolExecutor(tool_registry, self.bridge) if tool_registry is not None else None

    # -- registration ------------------------------------------------------

    def register(
        self,
        name: str,
        plugin: Any,
        *,
        dependencies: Sequence[str] = (),
        version: str = "",
        module_file: Optional[str | Path] = None,
        replace: bool = False,
    ) -> PluginRecord:
        clean = str(name or "").strip()
        if not clean:
            raise PluginRegistrationError("plugin name must not be empty")
        if clean in self.records:
            existing = self.records[clean]
            if not replace:
                raise PluginRegistrationError(f"plugin already registered: {clean}")
            if existing.status == "loaded":
                raise PluginRegistrationError(f"unload before replacing a loaded plugin: {clean}")
        record = PluginRecord(
            name=clean,
            plugin=plugin,
            dependencies=tuple(str(dep) for dep in dependencies),
            version=str(version or getattr(plugin, "version", "") or ""),
            module_file=Path(module_file) if module_file else None,
        )
        self.records[clean] = record
        return record

    def unregister(self, name: str) -> PluginRecord:
        record = self._require(name)
        if record.status == "loaded":
            raise PluginRegistrationError(f"unload before unregistering: {name}")
        for skill_id in record.skills:
            self.skills.pop(skill_id, None)
        return self.records.pop(name)

    def _require(self, name: str) -> PluginRecord:
        record = self.records.get(str(name or "").strip())
        if record is None:
            raise PluginNotFound(f"unknown plugin: {name}")
        return record

    # -- dependency management --------------------------------------------

    def order(self) -> List[str]:
        """Topologically sorted plugin names; raises on cycles/missing deps."""
        resolved: List[str] = []
        done: set[str] = set()
        stack: List[str] = []

        def visit(name: str) -> None:
            if name in done:
                return
            if name in stack:
                cycle = " -> ".join(stack[stack.index(name):] + [name])
                raise PluginDependencyError(f"plugin dependency cycle: {cycle}")
            record = self.records.get(name)
            if record is None:
                raise PluginDependencyError(f"unknown plugin dependency: {name}")
            stack.append(name)
            for dependency in record.dependencies:
                visit(dependency)
            stack.pop()
            done.add(name)
            resolved.append(name)

        for name in list(self.records):
            visit(name)
        return resolved

    def dependents(self, name: str) -> List[str]:
        """Transitive dependents of ``name`` in load order."""
        found: set[str] = set()
        frontier = {name}
        while frontier:
            current = frontier.pop()
            for record in self.records.values():
                if current in record.dependencies and record.name not in found:
                    found.add(record.name)
                    frontier.add(record.name)
        return [item for item in self.order() if item in found]

    # -- lifecycle (Effect programs) --------------------------------------

    def _ensure_op(self, record: PluginRecord, action: str) -> str:
        op_name = f"plugin:{record.name}:{action}"
        if op_name in self._registered_ops:
            return op_name

        def op_handler(_args: Dict[str, Any]) -> Any:
            hook = getattr(record.plugin, action, None)
            if hook is None:
                return None
            return _call_hook(hook, self)

        self.bridge.register_op(op_name, op_handler)
        self._registered_ops.add(op_name)
        return op_name

    def _run_hook(self, record: PluginRecord, action: str) -> None:
        program = self.policy.wrap(E.call(self._ensure_op(record, action)))
        self.bridge.run(program)

    def _stamp(self, record: PluginRecord) -> None:
        if record.module_file and record.module_file.exists():
            record.mtime_ns = record.module_file.stat().st_mtime_ns

    def load(self, name: str) -> PluginRecord:
        record = self._require(name)
        if record.status == "loaded":
            return record
        for dependency in record.dependencies:
            self.load(dependency)
        record.status = "loading"
        record.error = ""
        try:
            self._run_hook(record, "initialize")
            self._register_outputs(record)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller and status
            record.status = "error"
            record.error = str(exc)
            raise
        record.status = "loaded"
        record.loaded_at = time.time()
        self._stamp(record)
        return record

    def load_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for name in self.order():
            try:
                self.load(name)
                results[name] = True
            except Exception:  # noqa: BLE001 - one bad plugin must not stop the rest
                results[name] = False
        return results

    def unload(self, name: str) -> PluginRecord:
        record = self._require(name)
        loaded_dependents = [item for item in self.dependents(name) if self.records[item].status == "loaded"]
        if loaded_dependents:
            raise PluginDependencyError(
                f"cannot unload {name}: loaded dependents {', '.join(loaded_dependents)}"
            )
        if record.status != "loaded":
            record.status = "unloaded"
            return record
        record.status = "unloading"
        try:
            self._run_hook(record, "shutdown")
        finally:
            record.status = "unloaded"
            record.tools = []
            record.skills = []
            self._stamp(record)
        return record

    def unload_all(self) -> List[str]:
        unloaded: List[str] = []
        for name in reversed(self.order()):
            if self.records[name].status == "loaded":
                self.unload(name)
                unloaded.append(name)
        return unloaded

    def reload(self, name: str) -> PluginRecord:
        record = self._require(name)
        if record.status == "loaded":
            self.unload(name)
        return self.load(name)

    # -- hot reload --------------------------------------------------------

    def changed(self) -> List[str]:
        changed: List[str] = []
        for name, record in self.records.items():
            if record.status != "loaded" or not record.module_file:
                continue
            if not record.module_file.exists():
                continue
            if record.module_file.stat().st_mtime_ns != record.mtime_ns:
                changed.append(name)
        return [name for name in self.order() if name in changed]

    def hot_reload(self) -> List[str]:
        """Reload changed plugins plus their dependents, in dependency order."""
        changed = self.changed()
        if not changed:
            return []
        targets: set[str] = set(changed)
        for name in changed:
            targets.update(self.dependents(name))
        # Unload in reverse dependency order so no loaded dependent blocks a
        # dependency's shutdown, then re-initialize in dependency order.
        for name in reversed(self.order()):
            if name in targets and self.records[name].status == "loaded":
                self.unload(name)
        reloaded: List[str] = []
        for name in self.order():
            if name in targets:
                self.load(name)
                reloaded.append(name)
        return reloaded

    async def start_watch(self, interval_s: float = 1.0) -> None:
        if self._watch_task is not None:
            return
        self._watching = True

        async def loop() -> None:
            while self._watching:
                await asyncio.sleep(max(0.05, float(interval_s)))
                self.hot_reload()

        self._watch_task = asyncio.create_task(loop())

    async def stop_watch(self) -> None:
        self._watching = False
        task, self._watch_task = self._watch_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # -- tools, skills, integrations --------------------------------------

    def _register_outputs(self, record: PluginRecord) -> None:
        record.tools = []
        record.skills = []
        get_tools = getattr(record.plugin, "get_tools", None)
        for spec in (get_tools() if callable(get_tools) else []) or []:
            tool_id = str(getattr(spec, "tool_id", "") or "")
            if not tool_id:
                continue
            if self.registry is not None:
                self.registry.register(spec, replace=True)
                if self.executor is not None:
                    self.executor.invalidate(tool_id)
            record.tools.append(tool_id)
        get_skills = getattr(record.plugin, "get_skills", None)
        for skill in (get_skills() if callable(get_skills) else []) or []:
            skill_id = str(getattr(skill, "skill_id", "") or "")
            if not skill_id:
                continue
            self.skills[skill_id] = skill
            record.skills.append(skill_id)

    def skill(self, skill_id: str) -> Any:
        skill = self.skills.get(str(skill_id or ""))
        if skill is None:
            raise PluginNotFound(f"unknown skill: {skill_id}")
        return skill

    def list_skills(self, category: str = "") -> List[Dict[str, Any]]:
        items = []
        for skill in self.skills.values():
            if category and str(getattr(skill, "category", "")) != category:
                continue
            items.append(
                {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "description": getattr(skill, "description", ""),
                    "category": getattr(skill, "category", ""),
                    "tools": list(getattr(skill, "tools", []) or []),
                }
            )
        return items

    def render_skill(self, skill_id: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        skill = self.skill(skill_id)
        parameters = dict(parameters or {})
        render = getattr(skill, "render_prompt", None)
        prompt = render(parameters) if callable(render) else str(getattr(skill, "prompt_template", ""))
        return {
            "skill_id": skill.skill_id,
            "name": getattr(skill, "name", skill.skill_id),
            "prompt": prompt,
            "tools": list(getattr(skill, "tools", []) or []),
            "parameters": {**dict(getattr(skill, "parameters", {}) or {}), **parameters},
        }

    def execute_skill(
        self,
        skill_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        arguments: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Render the prompt, then run the bundled tools through Effect."""
        rendered = self.render_skill(skill_id, parameters)
        if self.executor is None:
            raise PluginError("skill execution requires a tool registry")
        arguments = arguments or {}
        results = []
        for tool_id in rendered["tools"]:
            result = self.executor.execute(tool_id, dict(arguments.get(tool_id) or {}))
            results.append(result.as_dict())
        return {"skill_id": skill_id, "prompt": rendered["prompt"], "tools": rendered["tools"], "results": results}

    def status(self) -> Dict[str, Any]:
        return {
            "order": self.order(),
            "plugins": [self.records[name].as_dict() for name in self.order()],
            "skills": [item["skill_id"] for item in self.list_skills()],
        }


def _call_hook(hook: Any, runtime: EffectPluginRuntime) -> Any:
    try:
        accepts_runtime = bool(inspect.signature(hook).parameters)
    except (TypeError, ValueError):
        accepts_runtime = True
    value = hook(runtime) if accepts_runtime else hook()
    return _resolve(value)


def _resolve(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def create_effect_plugin_runtime(
    tool_registry: Optional[ToolRegistry] = None,
    **kwargs: Any,
) -> EffectPluginRuntime:
    return EffectPluginRuntime(tool_registry, **kwargs)
