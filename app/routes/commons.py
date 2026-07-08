"""Commons and Meta Tool Commons route family."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException


def build_commons_router(
    *,
    meta_tool_commons: Any,
    swarm_kernel: Any,
    kv_cache_transport: Any,
    commons_space_registry: Any,
    commons_economy: Any,
    commons_policy_learner: Any,
    federated_commons: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/edgek/meta-tool-commons")
    async def edgek_meta_tool_commons_state():
        return meta_tool_commons.state()

    @router.get("/edgek/meta-tool-commons/evidence-plane")
    async def edgek_meta_tool_commons_evidence_plane():
        return meta_tool_commons.evidence_plane()

    @router.post("/edgek/meta-tool-commons/ingest")
    async def edgek_meta_tool_commons_ingest(payload: Dict[str, Any] = None):
        payload = payload or {}
        evidence = payload.get("evidence") or []
        return meta_tool_commons.ingest(evidence if isinstance(evidence, list) else [evidence])

    @router.get("/edgek/meta-tool-commons/swarm-ingest")
    @router.post("/edgek/meta-tool-commons/swarm-ingest")
    async def edgek_meta_tool_commons_swarm_ingest(payload: Dict[str, Any] = None):
        payload = payload or {}
        runs = swarm_kernel.recent_runs(
            limit=max(1, min(int(payload.get("limit", 25)), 100)),
            status=str(payload.get("status")) if payload.get("status") else None,
        )
        return meta_tool_commons.ingest_swarm_runs(runs)

    @router.get("/edgek/meta-tool-commons/swarm-candidates")
    @router.post("/edgek/meta-tool-commons/swarm-candidates")
    async def edgek_meta_tool_commons_swarm_candidates(payload: Dict[str, Any] = None):
        payload = payload or {}
        return meta_tool_commons.propose_swarm_candidates(
            task_class=payload.get("task_class"),
            role=payload.get("role"),
            min_samples=max(1, min(int(payload.get("min_samples", 2)), 25)),
            limit=max(1, min(int(payload.get("limit", 10)), 100)),
        )

    @router.get("/edgek/meta-tool-commons/kv-cache-ingest")
    @router.post("/edgek/meta-tool-commons/kv-cache-ingest")
    async def edgek_meta_tool_commons_kv_cache_ingest(payload: Dict[str, Any] = None):
        payload = payload or {}
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else kv_cache_transport.get_stats()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return meta_tool_commons.ingest_kv_cache_evidence(stats=stats, result=result)

    @router.post("/edgek/meta-tool-commons/rank")
    async def edgek_meta_tool_commons_rank(payload: Dict[str, Any] = None):
        payload = payload or {}
        return meta_tool_commons.rank(
            task_class=payload.get("task_class"),
            role=payload.get("role"),
            kind=payload.get("kind"),
            limit=int(payload.get("limit", 25)),
        )

    @router.get("/edgek/meta-tool-commons/candidates")
    async def edgek_meta_tool_commons_candidates(status: str = None, source: str = None, limit: int = 25):
        return meta_tool_commons.candidates(status=status, source=source, limit=max(1, min(limit, 100)))

    @router.post("/edgek/meta-tool-commons/adopt")
    async def edgek_meta_tool_commons_adopt(payload: Dict[str, Any] = None):
        payload = payload or {}
        try:
            return meta_tool_commons.adopt(
                str(payload.get("candidate_id") or ""),
                approved=bool(payload.get("approved", False)),
                dry_run=bool(payload.get("dry_run", True)),
                approved_by=str(payload.get("approved_by") or "user"),
                reason=str(payload.get("reason") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/edgek/meta-tool-commons/snapshot")
    async def edgek_meta_tool_commons_snapshot(task_class: str = None, role: str = None):
        return meta_tool_commons.snapshot(task_class=task_class, role=role)

    @router.get("/edgek/commons-spaces")
    def edgek_commons_spaces():
        return commons_space_registry.list_spaces()

    @router.get("/edgek/commons-spaces/{space_id}")
    async def edgek_commons_space_detail(space_id: str):
        try:
            return commons_space_registry.get(space_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/edgek/commons-scale/readiness")
    def edgek_commons_scale_readiness():
        return commons_space_registry.scale_readiness()

    @router.get("/edgek/commons-scale/registration-candidates")
    def edgek_commons_registration_candidates(limit: int = 50):
        return commons_space_registry.registration_candidates(limit=max(1, min(int(limit), 500)))

    @router.get("/edgek/commons-economy")
    async def edgek_commons_economy_state(full: bool = False):
        return commons_economy.state(full=bool(full))

    @router.get("/edgek/commons-economy/proof/{space_id}")
    async def edgek_commons_economy_proof(space_id: str):
        try:
            return commons_economy.proof(space_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.post("/edgek/commons-economy/simulate")
    async def edgek_commons_economy_simulate(payload: Dict[str, Any] = None):
        payload = payload or {}
        try:
            limit = max(1, min(int(payload.get("limit", 10)), 100))
            return commons_economy.simulate(str(payload.get("space_id")), limit=limit) if payload.get("space_id") else commons_economy.simulate(limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/edgek/commons-policy/examples")
    async def edgek_commons_policy_examples(limit: int = 500):
        return commons_policy_learner.extract_examples(max(1, min(limit, 2000)))

    @router.get("/edgek/commons-policy/model")
    async def edgek_commons_policy_model():
        return commons_policy_learner.train()

    @router.get("/edgek/commons-policy/evaluation")
    async def edgek_commons_policy_evaluation():
        return commons_policy_learner.evaluate()

    @router.post("/edgek/commons-policy/recommend")
    async def edgek_commons_policy_recommend(payload: Dict[str, Any] = None):
        return commons_policy_learner.recommend(payload or {})

    @router.get("/edgek/federated-commons")
    async def edgek_federated_commons_state():
        return federated_commons.state()

    return router
