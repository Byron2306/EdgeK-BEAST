"""Read-only Level 8 ceremony status and SSE projection helpers."""
from __future__ import annotations
import json
from typing import Any, Iterator


def ceremony_status(ceremony: Any, ceremony_id: str) -> dict:
    state=ceremony.store.load(ceremony_id)
    if state is None: return {"ceremony_id":ceremony_id,"status":"not_found","authority":"read_only"}
    return {"ceremony_id":state.ceremony_id,"dataset_id":state.dataset_id,"commit_digest":state.commit_digest,
            "phase":state.phase,"updated_at":state.updated_at,"closed":state.phase=="closed",
            "native_context_exported":False,"promotion_granted":False,"authority":"read_only"}


def sse_snapshot(progress: Any, *, after_sequence: int=0) -> Iterator[str]:
    for item in progress.snapshot(after_sequence=after_sequence):
        payload=item if isinstance(item,dict) else getattr(item,"__dict__",{"value":str(item)})
        yield "event: forge-kv\n"+"data: "+json.dumps(payload,sort_keys=True,default=str)+"\n\n"
