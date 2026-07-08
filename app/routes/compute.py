"""Compute and Crystal Compute route family."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.kernel.storage.outcome_evidence import OutcomeEvidence


def build_compute_router(
    *,
    compute_ledger: Any,
    crystal_compute_store: Any,
    crystal_fork_manager: Any,
    semantic_raid_store: Any,
    artifact_fossil_store: Any,
    commons_crystal_promoter: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/edgek/compute")
    async def edgek_compute_state():
        return compute_ledger.state()

    @router.get("/edgek/crystal-compute")
    async def edgek_crystal_compute_state(include_expired: bool = False):
        return {
            "beast_object_type": "crystal_compute_state",
            "version": "1.0",
            "phase1": "operational",
            "phase2": "shadow",
            "phase3": "advisory",
            "phase4": "escrow_shadow",
            "phase5": "temporal_forks_shadow",
            "phase6": "durable_intelligence_local",
            "phase7": "non_financial_simulation",
            "summary": crystal_compute_store.summary(),
            "negative_capabilities": crystal_compute_store.list_records(include_expired=include_expired),
            "friction_profiles": crystal_compute_store.friction_profiles(),
            "counterfactual_summary": compute_ledger.counterfactual_summary(),
            "escrow_summary": compute_ledger.escrow_summary(),
            "temporal_forks": crystal_fork_manager.state(),
            "semantic_raid": semantic_raid_store.integrity_report(),
            "artifact_fossils": artifact_fossil_store.replay(),
            "commons_space_crystals": commons_crystal_promoter.state(),
        }

    @router.get("/edgek/crystal-compute/forks")
    async def edgek_crystal_compute_forks():
        return crystal_fork_manager.state()

    @router.post("/edgek/crystal-compute/forks")
    async def edgek_crystal_compute_create_fork(payload: Dict[str, Any] = None):
        payload = payload or {}
        try:
            return crystal_fork_manager.create_fork(
                capability_id=str(payload.get("capability_id") or ""),
                task_class=str(payload.get("task_class") or "general"),
                channel=str(payload.get("channel") or "candidate"),
                parent_fork_id=str(payload.get("parent_fork_id") or ""),
                traffic_share=float(payload.get("traffic_share") or 0.0),
                confidence=float(payload.get("confidence") or 0.0),
            ).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/edgek/crystal-compute/forks/anneal")
    async def edgek_crystal_compute_anneal():
        return crystal_fork_manager.anneal()

    @router.get("/edgek/crystal-compute/semantic-raid")
    async def edgek_crystal_compute_semantic_raid():
        return semantic_raid_store.integrity_report()

    @router.post("/edgek/crystal-compute/semantic-raid/reconstruct")
    async def edgek_crystal_compute_semantic_raid_reconstruct():
        return semantic_raid_store.reconstruct()

    @router.post("/edgek/crystal-compute/semantic-raid/shards")
    async def edgek_crystal_compute_semantic_raid_store(payload: Dict[str, Any] = None):
        payload = payload or {}
        artifact = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        return semantic_raid_store.store_shard(
            str(payload.get("artifact_type") or artifact.get("beast_object_type") or "compute_artifact"),
            artifact,
            value_score=float(payload.get("value_score") or 0.5),
        ).to_dict()

    @router.get("/edgek/crystal-compute/fossils/replay")
    async def edgek_crystal_compute_fossil_replay():
        return artifact_fossil_store.replay()

    @router.post("/edgek/crystal-compute/outcomes")
    async def edgek_crystal_compute_record(payload: Dict[str, Any] = None):
        try:
            evidence = OutcomeEvidence.create(**(payload or {}))
            record = crystal_compute_store.record(evidence)
            return {"recorded": True, "evidence": evidence.to_dict(), "negative_capability": record.to_dict() if record else None}
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/edgek/crystal-compute/maintenance")
    async def edgek_crystal_compute_maintenance(payload: Dict[str, Any] = None):
        return crystal_compute_store.maintain(prune_expired=bool((payload or {}).get("prune_expired", False)))

    @router.post("/edgek/crystal-compute/negative/{record_id}/override")
    async def edgek_crystal_compute_override(record_id: str, payload: Dict[str, Any] = None):
        payload = payload or {}
        if payload.get("approved") is not True:
            raise HTTPException(status_code=403, detail="explicit approved=true is required")
        try:
            return crystal_compute_store.override(
                record_id,
                state=str(payload.get("state") or ""),
                reason=str(payload.get("reason") or ""),
                approved_by=str(payload.get("approved_by") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/edgek/compute/metrics")
    async def edgek_compute_metrics(limit: int = 500):
        return compute_ledger.metrics(limit=max(1, min(int(limit), 2000)))

    @router.get("/edgek/compute/savings-summary")
    async def edgek_compute_savings_summary(limit: int = 2000, weekly_call_volume: int = None):
        return compute_ledger.savings_summary(
            limit=max(1, min(int(limit), 5000)),
            weekly_call_volume=max(0, int(weekly_call_volume)) if weekly_call_volume is not None else None,
        )

    @router.get("/edgek/compute/plans")
    async def edgek_compute_plans(limit: int = 50):
        return {"plans": compute_ledger.recent_plans(max(1, min(int(limit), 500)))}

    @router.get("/edgek/compute/receipts")
    async def edgek_compute_receipts(limit: int = 50):
        return {"receipts": compute_ledger.recent_receipts(max(1, min(int(limit), 500)))}

    @router.get("/edgek/compute/receipts/{receipt_id}")
    async def edgek_compute_receipt(receipt_id: str):
        try:
            return compute_ledger.receipt(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/edgek/compute/counterfactuals")
    async def edgek_compute_counterfactuals(limit: int = 50):
        return {
            "summary": compute_ledger.counterfactual_summary(limit=max(1, min(int(limit), 2000))),
            "counterfactual_crystals": compute_ledger.recent_counterfactuals(max(1, min(int(limit), 500))),
        }

    @router.get("/edgek/compute/escrows")
    async def edgek_compute_escrows(limit: int = 50):
        return {
            "summary": compute_ledger.escrow_summary(limit=max(1, min(int(limit), 2000))),
            "escrows": compute_ledger.recent_escrows(max(1, min(int(limit), 500))),
        }

    return router
