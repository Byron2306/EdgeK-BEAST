"""IDE shell route family composition root.

The public ``build_ide_router`` contract remains stable while route ownership is
split into focused registrars.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.routes.ide_context import IdeRouteContext
from app.routes.ide_routes.actions import register_actions_routes
from app.routes.ide_routes.agent_sessions import register_agent_sessions_routes
from app.routes.ide_routes.agent_run_stream import register_agent_run_stream_routes
from app.routes.ide_routes.agent_runs import register_agent_runs_routes
from app.routes.ide_routes.editor_sourceplans import register_editor_sourceplans_routes
from app.routes.ide_routes.learning import register_learning_routes
from app.routes.ide_routes.mission import register_mission_routes
from app.routes.ide_routes.overview import register_overview_routes
from app.routes.ide_routes.system import register_system_routes
from app.routes.ide_routes.worktrees import register_worktrees_routes


def build_ide_router(default_root: str | Path, *, code_cortex_router: Any, crystal_gateway: Any = None, context_packet_builder: Any = None, execution_gateway: Any = None, compute_governor: Any = None, pressure_controller: Any = None) -> APIRouter:
    """Compose the complete IDE API without changing its public route contract."""
    router = APIRouter()
    ctx = IdeRouteContext(default_root, code_cortex_router=code_cortex_router, crystal_gateway=crystal_gateway, context_packet_builder=context_packet_builder, execution_gateway=execution_gateway, compute_governor=compute_governor, pressure_controller=pressure_controller)

    register_overview_routes(router, ctx)
    ctx.handlers.update(register_mission_routes(router, ctx) or {})
    register_system_routes(router, ctx)
    register_learning_routes(router, ctx)
    register_actions_routes(router, ctx)
    register_agent_sessions_routes(router, ctx)
    register_agent_runs_routes(router, ctx)
    register_agent_run_stream_routes(router, ctx)
    register_editor_sourceplans_routes(router, ctx)
    register_worktrees_routes(router, ctx)
    return router
