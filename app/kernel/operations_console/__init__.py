"""BEAST Agent Operations Console kernels."""
from .event_projection import DurableConsoleEventProjection
from .mode_contract import WorkbenchMode, WorkbenchModeEngine
from .objective_plan import ObjectivePlanWorkspace
from .context_manifest import ContextManifestStore
from .view_model import AgentOperationsConsoleViewModel

__all__ = [
    "AgentOperationsConsoleViewModel", "DurableConsoleEventProjection",
    "WorkbenchMode", "WorkbenchModeEngine", "ObjectivePlanWorkspace", "ContextManifestStore",
]

from app.kernel.operations_console.context_console import ContextManifestConsole
from .timeline_console import LiveRunTimelineConsole
__all__.append("LiveRunTimelineConsole")

from .tool_approval_console import ToolApprovalCardsConsole
from .worktree_console import WorktreeChangesDiffConsole
__all__.append("WorktreeChangesDiffConsole")

from .verification_console import VerificationConsole
__all__.append("VerificationConsole")
