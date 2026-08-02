"""FastAPI route for BEAST Phase 3.6 governed evidence reuse."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.kernel.evidence.reuse_engine import (
    GovernedEvidenceReuseEngine,
    ReusePolicyError,
)

router = APIRouter(prefix="/edgek/evidence/reuse", tags=["evidence-reuse"])
_engine = GovernedEvidenceReuseEngine()


class WorktreeBinding(BaseModel):
    worktree_id: str
    phase: str = "2"
    isolated: bool = True
    operator_workspace: bool = False
    root_digest: str


class ReuseArtifactModel(BaseModel):
    artifact_id: str
    kind: str
    digest: str
    size_bytes: int = Field(ge=0)
    relative_path: Optional[str] = None
    media_type: Optional[str] = None


class GovernedReuseRequest(BaseModel):
    compatibility_receipt: Dict[str, Any]
    worktree: WorktreeBinding
    artifacts: List[ReuseArtifactModel] = Field(default_factory=list)
    requested_mode: Optional[str] = None
    current_fingerprint_digest: Optional[str] = None
    candidate_fingerprint_digest: Optional[str] = None
    policy_controls: Optional[Dict[str, Any]] = None


@router.post("/prepare")
def prepare_governed_reuse(request: GovernedReuseRequest) -> Dict[str, Any]:
    try:
        return _engine.evaluate(
            compatibility_receipt=request.compatibility_receipt,
            worktree=request.worktree.model_dump(),
            artifacts=[item.model_dump() for item in request.artifacts],
            requested_mode=request.requested_mode,
            current_fingerprint_digest=request.current_fingerprint_digest,
            candidate_fingerprint_digest=request.candidate_fingerprint_digest,
            policy_controls=request.policy_controls,
        )
    except ReusePolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
