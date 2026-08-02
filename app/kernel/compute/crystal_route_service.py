from __future__ import annotations

from dataclasses import dataclass

from .crystal_candidate_adapter import CrystalCandidateAdapter, CrystalRequestContext, PromotedCrystalRecord
from .crystal_execution_plane import CrystalExecutionPlane, CrystalRouteReceipt


@dataclass(slots=True)
class CrystalRouteService:
    adapter: CrystalCandidateAdapter
    execution_plane: CrystalExecutionPlane

    def collect(self, context: CrystalRequestContext):
        return self.adapter.collect(context)

    def execute(self, *, candidate, record: PromotedCrystalRecord, context: CrystalRequestContext) -> CrystalRouteReceipt:
        return self.execution_plane.execute_selected(candidate=candidate, record=record, context=context)
