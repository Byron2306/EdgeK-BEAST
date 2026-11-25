#!/usr/bin/env python3
"""
Generate TypeScript type definitions from Pydantic models in zod_schemas.py.
Run this to generate .d.ts files for IDE autocomplete.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.kernel.agents.zod_schemas_v2 import TypeScriptGenerator
from app.kernel.agents import zod_schemas

# Collect all Pydantic models from zod_schemas
models = [
    zod_schemas.WorkspaceReadRangeArgs,
    zod_schemas.WorkspaceReadRangeResult,
    zod_schemas.WorkspaceListArgs,
    zod_schemas.WorkspaceListResult,
    zod_schemas.WorkspaceSearchTextArgs,
    zod_schemas.WorkspaceSearchTextResult,
    zod_schemas.WorktreeBindArgs,
    zod_schemas.WorktreeBindResult,
    zod_schemas.WorktreeWriteFileArgs,
    zod_schemas.WorktreeWriteFileResult,
    zod_schemas.WorktreeReplaceExactArgs,
    zod_schemas.WorktreeReplaceExactResult,
    zod_schemas.WorktreeVerifyArgs,
    zod_schemas.WorktreeVerifyResult,
    zod_schemas.WorktreeSourcePlanDraftArgs,
    zod_schemas.WorktreeSourcePlanDraftResult,
    zod_schemas.AgentRunArgs,
    zod_schemas.AgentRunResult,
    zod_schemas.AgentDecision,
    zod_schemas.AgentObservation,
    zod_schemas.AgentRunState,
    zod_schemas.ApprovalRequest,
    zod_schemas.ApprovalResponse,
]

# Generate TypeScript
ts_gen = TypeScriptGenerator()
output_path = Path(__file__).parent.parent / "desktop-ide" / "src" / "types" / "generated.ts"
output_path.parent.mkdir(parents=True, exist_ok=True)

ts_gen.write_to_file(models, output_path)
print(f"Generated TypeScript types at {output_path}")