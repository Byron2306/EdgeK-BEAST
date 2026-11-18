"""
Centralized Tool Registry for BEAST.
OpenCode-inspired: schema-validated, permission-gated, execution-target-aware.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
from enum import Enum

from app.kernel.agents.zod_schemas import (
    ToolSpec,
    ExecutionTarget,
    ToolEffect,
    ToolRisk,
    TOOL_SPECS,
    get_tool_spec,
    validate_tool_input,
    validate_tool_output,
)
from app.kernel.agents.effect_runtime import (
    ToolExecution,
    RetryPolicy,
    EffectMetrics,
    get_metrics,
    record_metrics,
    with_retry,
    with_timeout,
    span,
    EffectError,
    TransientError,
    PermanentError,
    CancellationToken,
)
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType


class ToolExecutionError(EffectError):
    """Tool execution failed."""
    pass


class ToolNotFoundError(EffectError):
    """Tool not registered."""
    pass


class ToolValidationError(EffectError):
    """Tool input/output validation failed."""
    pass


class ToolApprovalError(EffectError):
    """Tool requires approval."""
    pass


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


class LocalToolExecutor(ToolExecutor):
    """Execute tools locally."""
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        # Import here to avoid circular imports
        from app.kernel.agents.tools import execute_local_tool
        return await execute_local_tool(tool_id, arguments, context)


class SSHToolExecutor(ToolExecutor):
    """Execute tools over SSH."""
    def __init__(self, host: str, remote_root: str, session_id: str):
        self.host = host
        self.remote_root = remote_root
        self.session_id = session_id

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        from app.kernel.agents.tools import execute_ssh_tool
        return await execute_ssh_tool(
            tool_id, arguments, self.host, self.remote_root, self.session_id, context
        )


class ContainerToolExecutor(ToolExecutor):
    """Execute tools in container."""
    def __init__(self, container_id: str, workspace_folder: str):
        self.container_id = container_id
        self.workspace_folder = workspace_folder

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        from app.kernel.agents.tools import execute_container_tool
        return await execute_container_tool(
            tool_id, arguments, self.container_id, self.workspace_folder, context
        )


class ToolRegistry:
    """
    Centralized tool registry with:
    - Schema validation (input/output)
    - Permission/approval gating
    - Execution target routing
    - Effect-based execution (retry, timeout, metrics)
    - Structured observability
    """

    def __init__(
        self,
        workspace_root: str,
        executors: Optional[Dict[ExecutionTarget, ToolExecutor]] = None,
        approval_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[bool]]] = None,
    ):
        self.workspace_root = workspace_root
        self.specs: Dict[str, ToolSpec] = dict(TOOL_SPECS)
        self.executors: Dict[ExecutionTarget, ToolExecutor] = executors or {}
        self.approval_callback = approval_callback
        self._custom_handlers: Dict[str, Callable] = {}

        # Default executors
        if ExecutionTarget.LOCAL not in self.executors:
            self.executors[ExecutionTarget.LOCAL] = LocalToolExecutor(workspace_root)

        # Metrics
        self.metrics: Dict[str, EffectMetrics] = {}

    def register_spec(self, spec: ToolSpec) -> None:
        """Register a new tool specification."""
        self.specs[spec.tool_id] = spec

    def register_handler(self, tool_id: str, handler: Callable) -> None:
        """Register custom handler for tool."""
        self._custom_handlers[tool_id] = handler

    def register_executor(self, target: ExecutionTarget, executor: ToolExecutor) -> None:
        """Register executor for execution target."""
        self.executors[target] = executor

    def get_spec(self, tool_id: str) -> Optional[ToolSpec]:
        return self.specs.get(tool_id)

    def list_tools(
        self,
        category: Optional[str] = None,
        target: Optional[ExecutionTarget] = None,
    ) -> List[ToolSpec]:
        """List available tools with optional filters."""
        tools = list(self.specs.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if target:
            tools = [t for t in tools if target in t.targets]
        return tools

    def validate_input(self, tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool input against schema."""
        return validate_tool_input(tool_id, arguments)

    def validate_output(self, tool_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool output against schema."""
        return validate_tool_output(tool_id, result)

    def get_executor(self, target: ExecutionTarget) -> ToolExecutor:
        """Get executor for target, with fallback to local."""
        return self.executors.get(target, self.executors[ExecutionTarget.LOCAL])

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

        # Default: deny if no callback
        return False

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute tool with full effect runtime."""
        spec = self.get_spec(tool_id)
        if not spec:
            raise ToolNotFoundError(f"Tool not found: {tool_id}")

        # Validate input
        validated_args = self.validate_input(tool_id, arguments)

        # Check execution target support
        target = ExecutionTarget(context.execution_target)
        if target not in spec.targets:
            raise ToolExecutionError(
                f"Tool {tool_id} does not support target {target}",
                context={"supported_targets": [t.value for t in spec.targets]}
            )

        # Request approval if needed
        if spec.requires_approval:
            approved = await self.request_approval(tool_id, validated_args, context)
            if not approved:
                raise ToolApprovalError(
                    f"Tool {tool_id} execution not approved",
                    context={"tool_id": tool_id, "arguments": validated_args}
                )

        # Get executor
        executor = self.get_executor(target)

        # Check custom handler first
        if tool_id in self._custom_handlers:
            handler = self._custom_handlers[tool_id]
            return await handler(validated_args, context)

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

    async def execute_decision(
        self,
        decision: PlannerDecision,
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute a planner decision."""
        if decision.decision_type != PlannerDecisionType.TOOL:
            raise ToolExecutionError(
                f"Cannot execute non-tool decision: {decision.decision_type}"
            )

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
        """Wait for approval decision."""
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
        """Resolve approval request."""
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


# =============================================================================
# Tool Execution Helpers (for local tools)
# =============================================================================

async def execute_local_tool(
    tool_id: str,
    arguments: Dict[str, Any],
    context: ToolContext,
) -> Dict[str, Any]:
    """Execute a tool locally (placeholder - actual implementations in tools.py)."""
    # This will be implemented in tools.py
    from app.kernel.agents.tools import LOCAL_TOOL_HANDLERS
    handler = LOCAL_TOOL_HANDLERS.get(tool_id)
    if not handler:
        raise ToolExecutionError(f"No local handler for {tool_id}")
    return await handler(arguments, context)


# =============================================================================
# Export
# =============================================================================

__all__ = [
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
    "execute_local_tool",
    "ExecutionTarget",
    "ToolEffect",
    "ToolRisk",
]