"""Optional FastAPI router for operator publication and SSE progress."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable


def create_forge_publication_router(plane: Any, decode_request: Callable[[dict], dict]):
    try:
        from fastapi import APIRouter, HTTPException, Request
        from fastapi.responses import StreamingResponse
    except ImportError as exc:
        raise RuntimeError("FastAPI is required for the Forge publication router") from exc
    router=APIRouter(prefix="/edgek/forge-kv",tags=["forge-kv"])

    @router.get("/reachability")
    def reachability(): return plane.reachability()

    @router.get("/commons/state")
    def commons_state(): return plane.state.state()

    @router.post("/publish/huggingface")
    def publish(payload: dict):
        try: return plane.publish_hf(**decode_request(payload))
        except (ValueError,PermissionError) as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc

    @router.get("/progress")
    async def progress(request: Request, since: int = 0):
        async def stream():
            cursor=since
            while not await request.is_disconnected():
                items=plane.progress.snapshot(cursor)
                for item in items:
                    cursor=max(cursor,int(item["sequence"]))
                    yield "id: %s\nevent: %s\ndata: %s\n\n"%(item["sequence"],item["event_type"],json.dumps(item,sort_keys=True))
                await asyncio.sleep(.25)
        return StreamingResponse(stream(),media_type="text/event-stream")
    return router
