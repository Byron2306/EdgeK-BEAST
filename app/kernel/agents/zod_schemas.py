"""
Zod-style schema definitions for BEAST tools.
Single source of truth for tool contracts - input validation, output typing, IDE autocomplete.
Generated from TypeScript Zod schemas or defined natively with Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Literal, Optional, Any, Dict, List
from datetime import datetime
from enum import Enum


# =============================================================================
# Base Types
# =============================================================================

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


class DecisionType(str, Enum):
    TOOL = "tool"
    COMPLETE = "complete"
    BLOCKED = "blocked"


# =============================================================================
# Workspace Tools
# =============================================================================

class WorkspaceReadRangeArgs(BaseModel):
    """Read a line range from a workspace file."""
    path: Annotated[str, Field(min_length=1, description="File path relative to workspace root")]
    start_line: Annotated[int, Field(ge=1, description="Starting line number (1-indexed)")]
    line_count: Annotated[int, Field(ge=1, le=500, description="Number of lines to read")]

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if ".." in v or v.startswith("/"):
            raise ValueError("Path must be relative and not contain '..'")
        return v


class WorkspaceReadRangeResult(BaseModel):
    path: str
    content: str
    start_line: int
    line_count: int
    sha256: str
    truncated: bool = False


class WorkspaceListArgs(BaseModel):
    """List files in workspace."""
    path: Annotated[str, Field(default="", description="Directory path (empty = root)")]
    include_hidden: bool = False
    max_depth: Annotated[int, Field(ge=1, le=10, default=3)] = 3


class WorkspaceListResult(BaseModel):
    files: List[Dict[str, Any]]
    total: int
    truncated: bool = False


class WorkspaceSearchTextArgs(BaseModel):
    """Search for text in workspace files."""
    query: Annotated[str, Field(min_length=1, max_length=200)]
    path: Annotated[str, Field(default=".", description="Search root")]
    include_pattern: Optional[str] = None
    exclude_pattern: Optional[str] = None
    max_results: Annotated[int, Field(ge=1, le=1000, default=50)] = 50


class WorkspaceSearchTextResult(BaseModel):
    matches: List[Dict[str, Any]]
    total: int
    truncated: bool = False


# =============================================================================
# Worktree Tools
# =============================================================================

class WorktreeBindArgs(BaseModel):
    """Create an isolated worktree for mutation."""
    branch: Annotated[str, Field(min_length=1, max_length=100, description="Branch name")]
    base_commit: Optional[str] = None
    execution_target: ExecutionTarget = ExecutionTarget.LOCAL
    execution_target_payload: Optional[Dict[str, Any]] = None


class WorktreeBindResult(BaseModel):
    task_id: str
    worktree_root: str
    branch: str
    base_commit: str
    execution_target: ExecutionTarget


class WorktreeWriteFileArgs(BaseModel):
    """Write a file in the worktree."""
    path: Annotated[str, Field(min_length=1, description="Path relative to worktree root")]
    content: str


class WorktreeWriteFileResult(BaseModel):
    path: str
    sha256: str
    bytes_written: int


class WorktreeReplaceExactArgs(BaseModel):
    """Replace exact text in a file (bounded mutation)."""
    path: Annotated[str, Field(min_length=1)]
    old_text: Annotated[str, Field(min_length=1, description="Exact text to replace")]
    new_text: Annotated[str, Field(min_length=1, description="Replacement text")]


class WorktreeReplaceExactResult(BaseModel):
    path: str
    old_sha256: str
    new_sha256: str
    bytes_changed: int


class WorktreeVerifyArgs(BaseModel):
    """Run verification command in worktree."""
    command: Annotated[List[str], Field(min_length=1, description="Command as argv array")]
    timeout_seconds: Annotated[int, Field(ge=1, le=600, default=60)] = 60


class WorktreeVerifyResult(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    sha256: str


class WorktreeSourcePlanDraftArgs(BaseModel):
    """Draft a SourcePlan for the worktree changes."""
    description: Annotated[str, Field(min_length=10, max_length=500)]
    files: List[Dict[str, str]]  # path -> summary


class WorktreeSourcePlanDraftResult(BaseModel):
    draft_id: str
    preview: str
    requires_approval: bool = True


# =============================================================================
# Agent Tools
# =============================================================================

class AgentRunArgs(BaseModel):
    """Start or continue an agent run."""
    session_id: Annotated[str, Field(min_length=1)]
    objective: Annotated[str, Field(min_length=1, max_length=2000)]
    mode: Literal["agent", "edit", "implementer", "analysis", "chat", "ask"] = "agent"
    provider: Optional[str] = None
    model: Optional[str] = None
    context_files: List[str] = Field(default_factory=list)
    max_tokens: Annotated[int, Field(ge=1, le=32000, default=2048)] = 2048
    simulate: bool = False
    launch_strategy: Optional[str] = None
    approval_timeout_seconds: Annotated[int, Field(ge=1, le=3600, default=3600)] = 3600


class AgentRunResult(BaseModel):
    run_id: str
    session_id: str
    state: Literal["created", "planning", "executing", "completed", "failed", "blocked", "cancelled"]
    turn: int = 0
    max_turns: int = 8


class AgentDecision(BaseModel):
    """Single planner decision."""
    decision_type: DecisionType
    tool_id: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    blocker: Optional[str] = None
    rationale: Optional[str] = None
    approval_id: Optional[str] = None
    execution_target: ExecutionTarget = ExecutionTarget.LOCAL


class AgentObservation(BaseModel):
    """Tool execution observation."""
    observation_id: str
    tool_id: str
    status: Literal["completed", "failed"]
    error: Optional[str] = None
    duration_ms: int
    result: Optional[Dict[str, Any]] = None
    arguments: Optional[Dict[str, Any]] = None


class AgentRunState(BaseModel):
    """Complete agent run state."""
    run_id: str
    session_id: str
    objective: str
    mode: str
    provider: str
    model: str
    state: str
    turn: int
    max_turns: int
    observations: List[AgentObservation]
    last_decision: Optional[AgentDecision] = None
    error: Optional[str] = None
    budget: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Approval Tools
# =============================================================================

class ApprovalRequest(BaseModel):
    """Request approval for a tool execution."""
    request_id: str
    run_id: str
    tool_id: str
    arguments: Dict[str, Any]
    execution_target: ExecutionTarget
    execution_target_payload: Optional[Dict[str, Any]] = None
    risk: ToolRisk = ToolRisk.MEDIUM
    reason: str = ""
    expires_at: Optional[datetime] = None


class ApprovalResponse(BaseModel):
    """Approval decision."""
    request_id: str
    approved: bool
    reason: Optional[str] = None
    modified_arguments: Optional[Dict[str, Any]] = None


# =============================================================================
# Tool Specifications (Registry)
# =============================================================================

class ToolSpec(BaseModel):
    """Complete tool specification for registry."""
    tool_id: str
    version: str = "1.0"
    title: str
    description: str
    category: str
    risk: ToolRisk = ToolRisk.MEDIUM
    effect: ToolEffect = ToolEffect.READ
    input_schema: Dict[str, Any]  # JSON Schema
    output_schema: Optional[Dict[str, Any]] = None
    targets: List[ExecutionTarget] = Field(default_factory=lambda: [ExecutionTarget.LOCAL])
    requires_approval: bool = False
    requires_worktree: bool = False
    timeout_seconds: Annotated[int, Field(ge=1, le=3600, default=30)] = 30
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Pre-defined tool specifications matching OpenCode's patterns
TOOL_SPECS: Dict[str, ToolSpec] = {
    "workspace.read_range": ToolSpec(
        tool_id="workspace.read_range",
        title="Read File Range",
        description="Read a specific line range from a workspace file",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema=WorkspaceReadRangeArgs.model_json_schema(),
        output_schema=WorkspaceReadRangeResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=False,
        timeout_seconds=10,
    ),
    "workspace.list": ToolSpec(
        tool_id="workspace.list",
        title="List Workspace Files",
        description="List files and directories in workspace",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema=WorkspaceListArgs.model_json_schema(),
        output_schema=WorkspaceListResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=False,
        timeout_seconds=10,
    ),
    "workspace.search_text": ToolSpec(
        tool_id="workspace.search_text",
        title="Search Text in Workspace",
        description="Search for text across workspace files",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema=WorkspaceSearchTextArgs.model_json_schema(),
        output_schema=WorkspaceSearchTextResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=False,
        timeout_seconds=15,
    ),
    "worktree.bind": ToolSpec(
        tool_id="worktree.bind",
        title="Bind Worktree",
        description="Create isolated worktree for bounded mutation",
        category="worktree",
        risk=ToolRisk.MEDIUM,
        effect=ToolEffect.WRITE,
        input_schema=WorktreeBindArgs.model_json_schema(),
        output_schema=WorktreeBindResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=True,
        requires_worktree=True,
        timeout_seconds=30,
    ),
    "worktree.write_file": ToolSpec(
        tool_id="worktree.write_file",
        title="Write File in Worktree",
        description="Write a new file in the isolated worktree",
        category="worktree",
        risk=ToolRisk.MEDIUM,
        effect=ToolEffect.WRITE,
        input_schema=WorktreeWriteFileArgs.model_json_schema(),
        output_schema=WorktreeWriteFileResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=True,
        requires_worktree=True,
        timeout_seconds=15,
    ),
    "worktree.replace_exact": ToolSpec(
        tool_id="worktree.replace_exact",
        title="Replace Exact Text",
        description="Bounded mutation: replace exact old_text with new_text",
        category="worktree",
        risk=ToolRisk.HIGH,
        effect=ToolEffect.WRITE,
        input_schema=WorktreeReplaceExactArgs.model_json_schema(),
        output_schema=WorktreeReplaceExactResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=True,
        requires_worktree=True,
        timeout_seconds=15,
    ),
    "worktree.verify": ToolSpec(
        tool_id="worktree.verify",
        title="Verify Worktree",
        description="Run verification command in isolated worktree",
        category="worktree",
        risk=ToolRisk.MEDIUM,
        effect=ToolEffect.EXECUTE,
        input_schema=WorktreeVerifyArgs.model_json_schema(),
        output_schema=WorktreeVerifyResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL, ExecutionTarget.SSH, ExecutionTarget.CONTAINER],
        requires_approval=True,
        requires_worktree=True,
        timeout_seconds=120,
    ),
    "worktree.sourceplan_draft": ToolSpec(
        tool_id="worktree.sourceplan_draft",
        title="Draft SourcePlan",
        description="Create SourcePlan draft for worktree changes",
        category="worktree",
        risk=ToolRisk.MEDIUM,
        effect=ToolEffect.WRITE,
        input_schema=WorktreeSourcePlanDraftArgs.model_json_schema(),
        output_schema=WorktreeSourcePlanDraftResult.model_json_schema(),
        targets=[ExecutionTarget.LOCAL],
        requires_approval=True,
        requires_worktree=True,
        timeout_seconds=30,
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_tool_spec(tool_id: str) -> Optional[ToolSpec]:
    """Get tool specification by ID."""
    return TOOL_SPECS.get(tool_id)


def validate_tool_input(tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool input against schema."""
    spec = get_tool_spec(tool_id)
    if not spec:
        raise ValueError(f"Unknown tool: {tool_id}")

    # Use Pydantic model for validation based on tool_id
    model_map = {
        "workspace.read_range": WorkspaceReadRangeArgs,
        "workspace.list": WorkspaceListArgs,
        "workspace.search_text": WorkspaceSearchTextArgs,
        "worktree.bind": WorktreeBindArgs,
        "worktree.write_file": WorktreeWriteFileArgs,
        "worktree.replace_exact": WorktreeReplaceExactArgs,
        "worktree.verify": WorktreeVerifyArgs,
        "worktree.sourceplan_draft": WorktreeSourcePlanDraftArgs,
    }

    model = model_map.get(tool_id)
    if model:
        return model(**arguments).model_dump()

    # Fallback: basic JSON schema validation
    return arguments


def validate_tool_output(tool_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool output against schema."""
    spec = get_tool_spec(tool_id)
    if not spec or not spec.output_schema:
        return result

    # In production, use jsonschema for validation
    return result