"""Materialize only replay-approved Crystal IR into sealed capsules."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.kernel.compute.heldout_replay import ReplayReceipt
from app.kernel.compute.runtime_crystallizer import CrystalIR
from app.kernel.compute.sealed_capsule import CrystalCapsule, SealedCrystal


@dataclass(frozen=True)
class PromotionReceipt:
    crystal_id: str
    crystal_digest: str
    replay_attempts: int
    replay_successes: int
    promoted: bool
    capsule_digest: str = ""


class CrystalMaterializer:
    def __init__(self, capsule: CrystalCapsule | None = None):
        self.capsule = capsule or CrystalCapsule()

    def promote(self, crystal: CrystalIR, replay: ReplayReceipt) -> tuple[PromotionReceipt, SealedCrystal | None]:
        if replay.candidate_id != crystal.identity:
            raise ValueError("replay receipt does not match crystal")
        if replay.variant_ids and (len(replay.variant_ids) != replay.attempts or len(replay.variant_results) != replay.attempts):
            raise ValueError("replay receipt has incomplete variant evidence")
        if replay.variant_results and sum(replay.variant_results) != replay.successes:
            raise ValueError("replay receipt aggregate does not match variant evidence")
        if not replay.promoted:
            return PromotionReceipt(crystal.identity, crystal.digest, replay.attempts, replay.successes, False), None
        sealed = self.capsule.create(json.dumps(crystal.__dict__, sort_keys=True, separators=(",", ":")).encode())
        return PromotionReceipt(crystal.identity, crystal.digest, replay.attempts, replay.successes, True, sealed.digest), sealed
