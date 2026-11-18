"""Execute BEAST tools through the real Effect TS runtime.

``EffectToolExecutor`` sits on top of ``ToolRegistry``: authorization (schema
validation, target support, approval), handler lookup and output validation
stay in Python, while retry, timeout, cancellation (fiber interrupt) and
acquire/release bracketing are enforced by the Effect runtime in
``desktop-ide/scripts/effect-rpc.mjs``.

Non-local targets (SSH, container) execute through
``ToolRegistry.get_executor(target)``; the Effect policies still wrap the call
so retry/timeout apply to remote work too.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from app.kernel.agents import effect_ts_bridge as E
from app.kernel.agents.effect_ts_bridge import EffectTSBridge, get_bridge
from app.kernel.agents.tool_registry import ExecutionTarget, ToolContext, ToolRegistry


@dataclass
class ToolCallResult:
    tool_id: str
    value: Any
    elapsed_ms: float
    execution_target: str = "local"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "value": self.value,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "execution_target": self.execution_target,
        }


class EffectToolExecutor:
    """Run registered tools as Effect TS programs."""

    def __init__(self, registry: ToolRegistry, bridge: Optional[EffectTSBridge] = None) -> None:
        self.registry = registry
        self.bridge = bridge or get_bridge()
        self._registered_ops: set[str] = set()
        self._resources: Dict[str, tuple[Callable[[], Any], Callable[[], Any]]] = {}
        self._contexts: Dict[str, Any] = {}
        self._contexts_lock = threading.RLock()

    # -- registration ------------------------------------------------------

    def register_resource(
        self,
        tool_id: str,
        acquire: Callable[[], Any],
        release: Callable[[], Any],
    ) -> None:
        """Bracket every execution of ``tool_id`` with acquire/release."""
        self._resources[tool_id] = (acquire, release)

    def _ensure_op(self, tool_id: str) -> None:
        op_name = f"tool:{tool_id}"
        if op_name in self._registered_ops:
            return
        spec = self.registry.get(tool_id)
        handler = spec.handler or self.registry._custom_handlers.get(tool_id)  # noqa: SLF001
        if handler is None:
            raise E.EffectError(f"tool has no handler: {tool_id}", tag="ToolHandlerMissing")

        def op(args: Dict[str, Any]) -> Any:
            token = str(args.get("context_token") or "")
            with self._contexts_lock:
                context = self._contexts.get(token)
            if context is None:
                context = _ExecutionContext.from_payload(args.get("context") or {})
            return self._invoke(handler, args.get("arguments") or {}, context)

        self.bridge.register_op(op_name, op)
        self._registered_ops.add(op_name)

    def invalidate(self, tool_id: str) -> None:
        """Drop the cached op so a reloaded handler is picked up next call."""
        self._registered_ops.discard(f"tool:{tool_id}")

    def _ensure_resource_ops(self, tool_id: str) -> tuple[str, str]:
        acquire_name, release_name = f"tool:{tool_id}:acquire", f"tool:{tool_id}:release"
        acquire, release = self._resources[tool_id]
        if acquire_name not in self._registered_ops:
            self.bridge.register_op(acquire_name, lambda args: _resolve(acquire()))
            self.bridge.register_op(release_name, lambda args: _resolve(release()))
            self._registered_ops.update({acquire_name, release_name})
        return acquire_name, release_name

    @staticmethod
    def _invoke(handler: Callable[..., Any], arguments: Dict[str, Any], context: "_ExecutionContext") -> Any:
        params = [
            p
            for p in inspect.signature(handler).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        result = handler(arguments, context) if len(params) >= 2 else handler(arguments)
        return _resolve(result)

    # -- context -----------------------------------------------------------

    def default_context(self, **overrides: Any) -> ToolContext:
        values: Dict[str, Any] = {
            "run_id": "",
            "session_id": "",
            "workspace_root": str(getattr(self.registry, "workspace_root", "") or ""),
            "execution_target": ExecutionTarget.LOCAL.value,
        }
        values.update(overrides)
        return ToolContext(**values)

    # -- execution ---------------------------------------------------------

    def build_program(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
        retry_attempts: int = 0,
        retry_base_ms: int = 20,
        timeout_ms: Optional[int] = None,
        context_token: str = "",
    ) -> Dict[str, Any]:
        self._ensure_op(tool_id)
        ctx = context or self.default_context()
        payload = {
            "arguments": arguments,
            "context_token": context_token,
            "context": {
                "run_id": str(getattr(ctx, "run_id", "") or ""),
                "session_id": str(getattr(ctx, "session_id", "") or ""),
                "workspace_root": str(getattr(ctx, "workspace_root", "") or ""),
                "execution_target": str(getattr(ctx, "execution_target", "local") or "local"),
                "execution_target_payload": dict(getattr(ctx, "execution_target_payload", {}) or {}),
                "worktree_root": str(getattr(ctx, "worktree_root", "") or ""),
                "approval_id": str(getattr(ctx, "approval_id", "") or ""),
            },
        }
        program: Dict[str, Any] = E.call(f"tool:{tool_id}", payload)
        if retry_attempts > 0:
            program = E.retry_exponential(program, count=retry_attempts, base_ms=retry_base_ms)
        if timeout_ms is not None:
            program = E.timeout(program, ms=timeout_ms)
        if tool_id in self._resources:
            acquire_name, release_name = self._ensure_resource_ops(tool_id)
            program = E.resource(
                E.call(acquire_name), E.call(release_name), program
            )
        return program

    def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
        retry_attempts: int = 0,
        retry_base_ms: int = 20,
        timeout_ms: Optional[int] = None,
    ) -> ToolCallResult:
        ctx = context or self.default_context()
        prepared = _resolve(self.registry.authorize(tool_id, arguments, ctx))
        spec = prepared["spec"]
        validated = dict(prepared["arguments"])
        target: ExecutionTarget = prepared["execution_target"]
        effective_timeout = (
            timeout_ms
            if timeout_ms is not None
            else int(float(getattr(spec, "timeout_seconds", 30.0)) * 1000)
        )

        started = time.monotonic()
        if target is not ExecutionTarget.LOCAL or getattr(spec, "handler", None) is None:
            value = self._execute_direct(target, tool_id, validated, ctx)
        else:
            program = self.build_program(
                tool_id,
                validated,
                context=ctx,
                retry_attempts=retry_attempts,
                retry_base_ms=retry_base_ms,
                timeout_ms=effective_timeout,
            )
            value = self.bridge.run(program)
        elapsed = (time.monotonic() - started) * 1000
        if isinstance(value, dict):
            value = self.registry.validate_output(tool_id, value)
        return ToolCallResult(
            tool_id=tool_id,
            value=value,
            elapsed_ms=elapsed,
            execution_target=target.value,
        )

    def execute_authorized(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        *,
        context: Any,
        retry_attempts: int = 0,
        retry_base_ms: int = 20,
        timeout_ms: Optional[int] = None,
    ) -> ToolCallResult:
        """Run a tool already admitted by BEAST's durable authority boundary.

        This entry point deliberately does not request approval again. The
        caller must have enforced immutable target, capability and worktree
        custody before invoking it. The schema projection still validates the
        exact arguments and output, and Effect still owns timeout/retry/
        resource behavior.
        """
        spec = self.registry.get(tool_id)
        validated = self.registry.validate_input(tool_id, arguments)
        effective_timeout = (
            timeout_ms
            if timeout_ms is not None
            else int(float(getattr(spec, "timeout_seconds", 30.0)) * 1000)
        )
        token = uuid.uuid4().hex
        with self._contexts_lock:
            self._contexts[token] = context
        started = time.monotonic()
        try:
            program = self.build_program(
                tool_id,
                validated,
                context=context,
                retry_attempts=retry_attempts,
                retry_base_ms=retry_base_ms,
                timeout_ms=effective_timeout,
                context_token=token,
            )
            value = self.bridge.run(program)
        finally:
            with self._contexts_lock:
                self._contexts.pop(token, None)
        elapsed = (time.monotonic() - started) * 1000
        if isinstance(value, dict):
            value = self.registry.validate_output(tool_id, value)
        return ToolCallResult(
            tool_id=tool_id,
            value=value,
            elapsed_ms=elapsed,
            execution_target=str(getattr(context, "execution_target", "local") or "local"),
        )

    def _execute_direct(
        self,
        target: ExecutionTarget,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """Run through the target's registry executor (local command or remote)."""
        executor = self.registry.get_executor(target)
        return _resolve(executor.execute(tool_id, arguments, context))

    # -- cancellation ------------------------------------------------------

    def start(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        **policies: Any,
    ) -> str:
        """Start a tool on an Effect fiber; returns the fiber id."""
        context = policies.pop("context", None)
        validated = self.registry.validate_input(tool_id, arguments)
        program = self.build_program(tool_id, validated, context=context, **policies)
        handle = self.bridge.run(E.fork(program))
        return handle["fiberId"]

    def cancel(self, fiber_id: str) -> None:
        """Interrupt a running tool fiber (Effect cancellation)."""
        self.bridge.run(E.interrupt(fiber_id))


@dataclass
class _ExecutionContext:
    """Minimal ToolExecutionContext stand-in for direct handler calls."""

    run_id: str = ""
    session_id: str = ""
    workspace_root: str = ""
    execution_target: str = "local"
    execution_target_payload: Dict[str, Any] = field(default_factory=dict)
    worktree_root: str = ""
    approval_id: str = ""
    engine: Any = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "_ExecutionContext":
        return cls(
            run_id=str(payload.get("run_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            workspace_root=str(payload.get("workspace_root") or ""),
            execution_target=str(payload.get("execution_target") or "local"),
            execution_target_payload=dict(payload.get("execution_target_payload") or {}),
            worktree_root=str(payload.get("worktree_root") or ""),
            approval_id=str(payload.get("approval_id") or ""),
            engine=payload.get("engine"),
        )


def _resolve(value: Any) -> Any:
    """Resolve an awaitable even when a loop is already running."""
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, value).result()
