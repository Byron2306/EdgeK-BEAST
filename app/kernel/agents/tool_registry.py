"""Canonical typed tool registry for BEAST agent runs.
Extended with Effect runtime support, plugin system integration, and MCP/IDE adapters.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from app.kernel.agents.tool_models import ToolSpec
from app.kernel.agents.tool_schema import SchemaValidationError, validate_schema
from app.kernel.agents.effect_runtime import (
    EffectError,
    TransientError,
    PermanentError,
    CancellationError,
    TimeoutError,
    ResourceError,
    RetryPolicy,
    DEFAULT_RETRY_POLICY,
    with_retry,
    with_timeout,
    span,
    CancellationToken,
    EffectMetrics,
    get_metrics,
    record_metrics,
)
from app.kernel.agents.zod_schemas import (
    ToolSpec as ZodToolSpec,
    ToolRisk,
    ToolEffect,
    ExecutionTarget,
)


# =============================================================================
# Original AgentToolRegistry (Preserved for Compatibility)
# =============================================================================

class ToolRegistryError(ValueError):
    pass


class AgentToolRegistry:
    """Original BEAST tool registry - preserved for backward compatibility."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._lock = threading.RLock()

    def register(self, spec: ToolSpec, *, replace: bool = False) -> ToolSpec:
        tool_id = str(spec.tool_id or "").strip()
        if not tool_id:
            raise ToolRegistryError("tool_id must not be empty")
        if spec.handler is None:
            raise ToolRegistryError(f"tool {tool_id} has no handler")
        with self._lock:
            if tool_id in self._tools and not replace:
                raise ToolRegistryError(f"tool already registered: {tool_id}")
            self._tools[tool_id] = spec
        return spec

    def get(self, tool_id: str) -> ToolSpec:
        with self._lock:
            spec = self._tools.get(str(tool_id or "").strip())
        if spec is None:
            raise KeyError(f"unknown agent tool: {tool_id}")
        return spec

    def list(self, *, category: str = "", effect: str = "") -> list[dict[str, Any]]:
        with self._lock:
            tools = list(self._tools.values())
        if category:
            tools = [tool for tool in tools if tool.category == category]
        if effect:
            tools = [tool for tool in tools if tool.effect.value == effect]
        return [tool.public_dict() for tool in sorted(tools, key=lambda item: item.tool_id)]

    def validate_arguments(self, spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ToolRegistryError("tool arguments must be an object")
        schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        missing = [str(name) for name in required if name not in arguments]
        if missing:
            raise ToolRegistryError(f"missing required tool arguments: {', '.join(missing)}")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        types = {
            "string": lambda value: isinstance(value, str),
            "array": lambda value: isinstance(value, list),
            "object": lambda value: isinstance(value, dict),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": lambda value: isinstance(value, bool),
            "null": lambda value: value is None,
        }
        for name, value in arguments.items():
            field = properties.get(name) or {}
            expected = field.get("type")
            if isinstance(expected, str) and expected in types and not types[expected](value):
                raise ToolRegistryError(f"tool argument {name} must have type {expected}")
            if expected == "array":
                item_type = (field.get("items") or {}).get("type")
                if item_type in types and any(not types[item_type](item) for item in value):
                    raise ToolRegistryError(f"tool argument {name} items must have type {item_type}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                raise ToolRegistryError(f"unknown tool arguments: {', '.join(unknown)}")
        return dict(arguments)


# =============================================================================
# New Extended Tool Registry (Effect Runtime + Plugin System)
# =============================================================================

class ToolExecutionError(EffectError):
    pass


class ToolNotFoundError(EffectError):
    pass


class ToolValidationError(EffectError):
    pass


class ToolApprovalError(EffectError):
    pass


class ExecutionTarget(str, Enum):
    LOCAL = "local"
    SSH = "ssh"
    CONTAINER = "container"


class ToolEffect(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    PROMOTION = "promotion"


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolSpec:
    """Extended tool specification with Effect runtime support."""
    tool_id: str
    version: str = "1.0"
    title: str = ""
    description: str = ""
    category: str = "general"
    risk: ToolRisk = ToolRisk.MEDIUM
    effect: ToolEffect = ToolEffect.READ
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    targets: List[ExecutionTarget] = field(default_factory=lambda: [ExecutionTarget.LOCAL])
    requires_approval: bool = False
    requires_worktree: bool = False
    timeout_seconds: int = 30
    handler: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "risk": self.risk.value,
            "effect": self.effect.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "targets": [t.value for t in self.targets],
            "requires_approval": self.requires_approval,
            "requires_worktree": self.requires_worktree,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }


@dataclass
class ToolContext:
    """Context passed to tool executors."""
    run_id: str
    session_id: str
    workspace_root: str
    execution_target: str = "local"
    execution_target_payload: Optional[Dict[str, Any]] = None
    approval_id: Optional[str] = None
    cancellation_token: Optional[CancellationToken] = None


class ToolExecutor:
    """Base tool executor interface."""
    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def stream(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ):
        """Default streaming: one result event after execute()."""
        yield {"type": "result", "result": await self.execute(tool_id, arguments, context)}


MAX_EXEC_OUTPUT = 65536


def _command_arguments(arguments: Dict[str, Any]) -> str:
    command = arguments.get("command") or arguments.get("cmd") or arguments.get("script")
    if not command:
        raise ToolExecutionError("execution target requires a 'command' argument")
    return str(command)


def _run_command(
    command: List[str],
    *,
    timeout_seconds: float,
    cwd: Optional[str] = None,
    target: str = "local",
) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=float(timeout_seconds),
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise ToolExecutionError(f"{target} command not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(f"{target} command timed out after {timeout_seconds}s") from exc
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    truncated = len(stdout) > MAX_EXEC_OUTPUT or len(stderr) > MAX_EXEC_OUTPUT
    return {
        "status": "completed" if completed.returncode == 0 else "failed",
        "exit_code": int(completed.returncode),
        "stdout": stdout[:MAX_EXEC_OUTPUT],
        "stderr": stderr[:MAX_EXEC_OUTPUT],
        "truncated": truncated,
        "target": target,
    }


class _CommandExecutor(ToolExecutor):
    """Executor for command-style tools on a specific target."""

    target = "local"
    runtime_arguments = ("command", "cmd", "script")

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = float(timeout_seconds)

    def build_command(self, arguments: Dict[str, Any]) -> List[str]:
        raise NotImplementedError

    def cwd(self) -> Optional[str]:
        return None

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        command = self.build_command(arguments)
        return await asyncio.to_thread(
            _run_command,
            command,
            timeout_seconds=self.timeout_seconds,
            cwd=self.cwd(),
            target=self.target,
        )

    async def stream(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ):
        command = self.build_command(arguments)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd(),
        )
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield {
                "type": "chunk",
                "stream": "stdout",
                "data": line.decode("utf-8", errors="replace").rstrip("\n"),
            }
        stderr = ""
        if process.stderr is not None:
            stderr = (await process.stderr.read()).decode("utf-8", errors="replace")[:MAX_EXEC_OUTPUT]
        returncode = await process.wait()
        yield {
            "type": "result",
            "result": {
                "status": "completed" if returncode == 0 else "failed",
                "exit_code": int(returncode),
                "stderr": stderr,
                "target": self.target,
            },
        }


class LocalToolExecutor(_CommandExecutor):
    """Execute command tools locally; fall back to the tool module if present."""

    target = "local"

    def __init__(self, workspace_root: str, *, timeout_seconds: float = 60.0) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.workspace_root = workspace_root

    def cwd(self) -> Optional[str]:
        return self.workspace_root

    def build_command(self, arguments: Dict[str, Any]) -> List[str]:
        return ["sh", "-lc", _command_arguments(arguments)]

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        if any(key in arguments for key in self.runtime_arguments):
            return await super().execute(tool_id, arguments, context)
        try:
            from app.kernel.agents.tools import execute_local_tool
            return await execute_local_tool(tool_id, arguments, context)
        except ImportError:
            return {"error": f"No handler for {tool_id}", "status": "not_implemented"}


class SSHToolExecutor(_CommandExecutor):
    """Execute command tools over SSH (BatchMode; no interactive prompts)."""

    target = "ssh"

    def __init__(
        self,
        host: str,
        remote_root: str,
        session_id: str,
        *,
        ssh_binary: str = "ssh",
        timeout_seconds: float = 60.0,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.host = host
        self.remote_root = remote_root
        self.session_id = session_id
        self.ssh_binary = ssh_binary

    def build_command(self, arguments: Dict[str, Any]) -> List[str]:
        command = _command_arguments(arguments)
        remote = command
        if self.remote_root:
            remote = f"cd {shlex.quote(self.remote_root)} && {command}"
        return [self.ssh_binary, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.host, remote]


class ContainerToolExecutor(_CommandExecutor):
    """Execute command tools inside a container via ``docker exec``."""

    target = "container"

    def __init__(
        self,
        container_id: str,
        workspace_folder: str = "",
        *,
        runtime: str = "docker",
        timeout_seconds: float = 60.0,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.container_id = container_id
        self.workspace_folder = workspace_folder or "/workspace"
        self.runtime = runtime

    def build_command(self, arguments: Dict[str, Any]) -> List[str]:
        command = _command_arguments(arguments)
        return [
            self.runtime,
            "exec",
            "-w",
            self.workspace_folder,
            self.container_id,
            "sh",
            "-lc",
            command,
        ]


class ToolRegistry:
    """
    Extended tool registry with:
    - Schema validation (input/output)
    - Permission/approval gating
    - Execution target routing
    - Effect-based execution (retry, timeout, metrics)
    - Plugin system integration
    - Structured observability
    """

    def __init__(
        self,
        workspace_root: str,
        executors: Optional[Dict[ExecutionTarget, ToolExecutor]] = None,
        approval_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[bool]]] = None,
    ):
        self.workspace_root = workspace_root
        self.specs: Dict[str, ToolSpec] = {}
        self.executors: Dict[ExecutionTarget, ToolExecutor] = executors or {}
        self.approval_callback = approval_callback
        self._custom_handlers: Dict[str, Callable] = {}
        self._lock = threading.RLock()

        # Default local executor
        if ExecutionTarget.LOCAL not in self.executors:
            self.executors[ExecutionTarget.LOCAL] = LocalToolExecutor(workspace_root)

        # Metrics
        self.metrics: Dict[str, EffectMetrics] = {}

    def register(self, spec: ToolSpec, *, replace: bool = False) -> ToolSpec:
        """Register a tool specification."""
        tool_id = str(spec.tool_id or "").strip()
        if not tool_id:
            raise ToolRegistryError("tool_id must not be empty")
        with self._lock:
            if tool_id in self.specs and not replace:
                raise ToolRegistryError(f"tool already registered: {tool_id}")
            self.specs[tool_id] = spec
        return spec

    def get(self, tool_id: str) -> ToolSpec:
        with self._lock:
            spec = self.specs.get(str(tool_id or "").strip())
        if spec is None:
            raise KeyError(f"unknown agent tool: {tool_id}")
        return spec

    def register_spec(self, spec: ToolSpec) -> None:
        """Register a tool specification (alias for register)."""
        self.register(spec)

    def register_zod(
        self,
        spec: Any,
        *,
        handler: Optional[Callable[..., Any]] = None,
        replace: bool = False,
    ) -> ToolSpec:
        """Register an ``EnhancedToolSpec`` from the Zod schema layer.

        The Zod spec exports JSON Schema via ``to_zod_schema()``, so the same
        validator protects planner/tool output regardless of which schema
        authoring style the tool used.
        """
        effect_map = {
            "write": ToolEffect.WRITE,
            "execute": ToolEffect.EXECUTE,
            "promotion": ToolEffect.PROMOTION,
        }
        converted = ToolSpec(
            tool_id=str(spec.tool_id),
            version=str(spec.version),
            title=str(spec.title),
            description=str(spec.description),
            category=str(spec.category),
            risk=ToolRisk(str(getattr(spec.risk, "value", spec.risk))),
            effect=effect_map.get(str(getattr(spec.effect, "value", spec.effect)), ToolEffect.READ),
            input_schema=spec.to_zod_schema(),
            output_schema=dict(spec.output_schema or {}),
            targets=[ExecutionTarget(str(getattr(target, "value", target))) for target in spec.targets],
            requires_approval=bool(spec.requires_approval),
            requires_worktree=bool(spec.requires_worktree),
            timeout_seconds=float(spec.timeout_seconds),
            handler=handler,
        )
        return self.register(converted, replace=replace)

    def get_spec(self, tool_id: str) -> Optional[ToolSpec]:
        with self._lock:
            return self.specs.get(tool_id)

    def list_tools(
        self,
        category: Optional[str] = None,
        target: Optional[ExecutionTarget] = None,
    ) -> List[ToolSpec]:
        """List available tools with optional filters."""
        with self._lock:
            tools = list(self.specs.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if target:
            tools = [t for t in tools if target in t.targets]
        return tools

    def validate_input(self, tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool input against its (Zod-generated) JSON Schema."""
        spec = self.get_spec(tool_id)
        if not spec:
            raise ToolNotFoundError(f"Tool not found: {tool_id}")

        if not isinstance(arguments, dict):
            raise ToolValidationError(f"arguments for {tool_id} must be an object")
        schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
        try:
            validate_schema(arguments, schema)
        except SchemaValidationError as exc:
            raise ToolValidationError(f"invalid arguments for {tool_id}: {exc}") from exc
        return arguments

    def validate_output(self, tool_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool output against its (Zod-generated) JSON Schema."""
        spec = self.get_spec(tool_id)
        if not spec or not spec.output_schema:
            return result
        try:
            validate_schema(result, spec.output_schema)
        except SchemaValidationError as exc:
            raise ToolValidationError(f"invalid output for {tool_id}: {exc}") from exc
        return result

    def get_executor(self, target: ExecutionTarget) -> ToolExecutor:
        """Get executor for target, with fallback to local."""
        with self._lock:
            return self.executors.get(target, self.executors[ExecutionTarget.LOCAL])

    def register_executor(self, target: ExecutionTarget, executor: ToolExecutor) -> None:
        """Register executor for execution target."""
        with self._lock:
            self.executors[target] = executor

    def register_handler(self, tool_id: str, handler: Callable) -> None:
        """Register custom handler for tool."""
        with self._lock:
            self._custom_handlers[tool_id] = handler

    async def request_approval(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> bool:
        """Request approval for tool execution."""
        spec = self.get_spec(tool_id)
        if not spec or not spec.requires_approval:
            return True

        if self.approval_callback:
            return await self.approval_callback(tool_id, {
                "arguments": arguments,
                "context": {
                    "run_id": context.run_id,
                    "session_id": context.session_id,
                    "execution_target": context.execution_target,
                },
            })

        return False

    async def authorize(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Validate input, check target support, and enforce approval once.

        Both ``execute`` and streaming callers use this so a tool cannot skip
        the permission gate by choosing a different execution path.
        """
        spec = self.get_spec(tool_id)
        if not spec:
            raise ToolNotFoundError(f"Tool not found: {tool_id}")
        validated_args = self.validate_input(tool_id, arguments)
        target = ExecutionTarget(context.execution_target)
        if target not in spec.targets:
            raise ToolExecutionError(
                f"Tool {tool_id} does not support target {target}",
                context={"supported_targets": [t.value for t in spec.targets]},
            )
        if spec.requires_approval:
            approved = await self.request_approval(tool_id, validated_args, context)
            if not approved:
                raise ToolApprovalError(
                    f"Tool {tool_id} execution not approved",
                    context={"tool_id": tool_id, "arguments": validated_args},
                )
        return {
            "tool_id": tool_id,
            "spec": spec,
            "arguments": validated_args,
            "execution_target": target,
            "approval_id": context.approval_id or "",
        }

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute tool with full effect runtime."""
        prepared = await self.authorize(tool_id, arguments, context)
        spec: ToolSpec = prepared["spec"]
        validated_args: Dict[str, Any] = prepared["arguments"]
        target: ExecutionTarget = prepared["execution_target"]

        # Get executor
        executor = self.get_executor(target)

        # Check custom handlers and the spec's own handler first. Local
        # handlers are in-process, so no target executor is involved.
        handler = self._custom_handlers.get(tool_id) or (
            getattr(spec, "handler", None) if target is ExecutionTarget.LOCAL else None
        )
        if handler is not None:
            started = time.time()
            try:
                result = handler(validated_args, context)
                if inspect.isawaitable(result):
                    result = await result
                validated_result = self.validate_output(tool_id, result)
            except Exception as exc:
                record_metrics(f"tool.{tool_id}", False, (time.time() - started) * 1000, exc)
                raise
            record_metrics(f"tool.{tool_id}", True, (time.time() - started) * 1000, None)
            return validated_result

        # Execute with effect runtime
        execution = ToolExecution(
            tool_id=tool_id,
            arguments=validated_args,
            execution_target=target.value,
            approval_id=context.approval_id,
            timeout_seconds=float(spec.timeout_seconds),
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay=1.0,
                max_delay=10.0,
            ),
        )

        start_time = time.time()
        success = False
        error: Optional[Exception] = None

        try:
            # Execute with timeout
            result = await with_timeout(
                lambda: executor.execute(tool_id, validated_args, context),
                timeout_seconds=float(spec.timeout_seconds),
            )

            # Validate output
            validated_result = self.validate_output(tool_id, result)

            success = True
            return validated_result

        except Exception as e:
            error = e
            raise

        finally:
            duration_ms = (time.time() - start_time) * 1000
            record_metrics(f"tool.{tool_id}", success, duration_ms, error)

    async def execute_stream(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ):
        """Yield streaming events while executing a tool.

        Events: ``started``, ``chunk`` (when the executor streams), ``result``
        or ``failed``. Authorization happens before the first event so an
        unapproved tool never emits executor output.
        """
        try:
            prepared = await self.authorize(tool_id, arguments, context)
        except Exception as exc:  # noqa: BLE001 - streamed to the caller
            yield {"type": "failed", "tool_id": tool_id, "error": str(exc)}
            return
        yield {
            "type": "started",
            "tool_id": tool_id,
            "execution_target": prepared["execution_target"].value,
            "approval_id": prepared["approval_id"],
        }
        executor = self.get_executor(prepared["execution_target"])
        started = time.time()
        try:
            async for event in executor.stream(tool_id, prepared["arguments"], context):
                yield event
        except Exception as exc:  # noqa: BLE001 - failure becomes an event
            record_metrics(f"tool.{tool_id}", False, (time.time() - started) * 1000, exc)
            yield {"type": "failed", "tool_id": tool_id, "error": str(exc)}
            return
        record_metrics(f"tool.{tool_id}", True, (time.time() - started) * 1000, None)

    async def execute_decision(
        self,
        decision: Any,  # PlannerDecision
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute a planner decision."""
        if not hasattr(decision, 'decision_type') or decision.decision_type != "tool":
            raise ToolExecutionError(f"Cannot execute non-tool decision: {decision.decision_type}")

        if not decision.tool_id:
            raise ToolExecutionError("Decision has no tool_id")

        return await self.execute(
            decision.tool_id,
            decision.arguments or {},
            context,
        )


# =============================================================================
# Approval Manager
# =============================================================================

@dataclass
class ApprovalRequest:
    request_id: str
    tool_id: str
    arguments: Dict[str, Any]
    context: ToolContext
    risk: str = "medium"
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    resolved: bool = False
    approved: Optional[bool] = None


class ApprovalManager:
    """Manages approval requests for tool execution."""

    def __init__(self, default_timeout_seconds: float = 3600.0):
        self.requests: Dict[str, ApprovalRequest] = {}
        self.default_timeout = default_timeout_seconds
        self._callbacks: Dict[str, asyncio.Future] = {}

    def create_request(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
        risk: str = "medium",
        reason: str = "",
    ) -> ApprovalRequest:
        request_id = f"approval_{hashlib.sha256(f'{tool_id}{time.time()}'.encode()).hexdigest()[:16]}"
        request = ApprovalRequest(
            request_id=request_id,
            tool_id=tool_id,
            arguments=arguments,
            context=context,
            risk=risk,
            reason=reason,
            expires_at=time.time() + self.default_timeout,
        )
        self.requests[request_id] = request
        self._callbacks[request_id] = asyncio.Future()
        return request

    async def wait_for_approval(self, request_id: str) -> bool:
        if request_id not in self.requests:
            raise ValueError(f"Unknown approval request: {request_id}")

        request = self.requests[request_id]
        future = self._callbacks[request_id]

        try:
            result = await asyncio.wait_for(future, timeout=3600)
            return result
        except asyncio.TimeoutError:
            request.resolved = True
            request.approved = False
            return False

    def approve(self, request_id: str, approved: bool) -> bool:
        if request_id not in self.requests:
            return False

        request = self.requests[request_id]
        if request.resolved:
            return False

        request.resolved = True
        request.approved = approved

        if request_id in self._callbacks:
            self._callbacks[request_id].set_result(approved)

        return True

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self.requests.get(request_id)

    def list_pending(self) -> List[ApprovalRequest]:
        return [r for r in self.requests.values() if not r.resolved]


# =============================================================================
# Tool Execution (Effect Runtime)
# =============================================================================

@dataclass
class ToolExecution:
    """Tool execution with full effect runtime support."""
    tool_id: str
    arguments: Dict[str, Any]
    execution_target: str = "local"
    approval_id: Optional[str] = None
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=lambda: DEFAULT_RETRY_POLICY)

    async def execute(
        self,
        executor: Callable[[str, Dict[str, Any], str, Optional[str]], Awaitable[Dict[str, Any]]],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Execute tool with full effect runtime."""
        async with span(f"tool.{self.tool_id}", {
            "tool_id": self.tool_id,
            "execution_target": self.execution_target,
            "timeout_seconds": self.timeout_seconds,
        }) as s:
            start_time = time.time()

            try:
                # Execute with timeout and retry
                result = await with_timeout(
                    lambda: with_retry(
                        lambda: executor(
                            self.tool_id,
                            self.arguments,
                            self.execution_target,
                            self.approval_id,
                        ),
                        policy=self.retry_policy,
                    ),
                    timeout_seconds=self.timeout_seconds,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "success")

                return result

            except TimeoutError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "timeout")
                raise

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "error")
                s.add_attribute("error", str(e))
                raise


# =============================================================================
# Factory Functions
# =============================================================================

def create_tool_registry(
    workspace_root: str,
    ssh_configs: Optional[List[Dict[str, Any]]] = None,
    container_configs: Optional[List[Dict[str, Any]]] = None,
    approval_callback: Optional[Callable] = None,
) -> ToolRegistry:
    """Create tool registry with configured executors."""
    executors = {}

    # Local executor always available
    executors[ExecutionTarget.LOCAL] = LocalToolExecutor(workspace_root)

    # SSH executors
    if ssh_configs:
        for config in ssh_configs:
            session_id = config.get("session_id", f"ssh_{config['host']}")
            executors[ExecutionTarget.SSH] = SSHToolExecutor(
                host=config["host"],
                remote_root=config.get("remote_root", "/home"),
                session_id=session_id,
            )

    # Container executors
    if container_configs:
        for config in container_configs:
            executors[ExecutionTarget.CONTAINER] = ContainerToolExecutor(
                container_id=config["container_id"],
                workspace_folder=config.get("workspace_folder", "/workspace"),
            )

    return ToolRegistry(
        workspace_root=workspace_root,
        executors=executors,
        approval_callback=approval_callback,
    )


def build_default_tool_registry() -> AgentToolRegistry:
    """Build the default agent tool registry (for backward compatibility)."""
    return AgentToolRegistry()


# =============================================================================
# Export
# =============================================================================

__all__ = [
    # Original
    "AgentToolRegistry",
    "ToolRegistryError",
    # New Extended
    "ToolRegistry",
    "ToolSpec",
    "ToolExecutor",
    "LocalToolExecutor",
    "SSHToolExecutor",
    "ContainerToolExecutor",
    "ToolContext",
    "ApprovalManager",
    "ApprovalRequest",
    "ToolExecution",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolApprovalError",
    "create_tool_registry",
    "build_default_tool_registry",
    "AgentToolRegistry",
    # Enums
    "ExecutionTarget",
    "ToolEffect",
    "ToolRisk",
    # Effect Runtime
    "ToolExecution",
    "RetryPolicy",
    "DEFAULT_RETRY_POLICY",
]