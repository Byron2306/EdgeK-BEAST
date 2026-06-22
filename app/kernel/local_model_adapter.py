"""Dedicated local model adapter used by Phase 4 adaptive inference."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True)
class LocalModelResult:
    adapter: str
    model: str
    task_class: str
    status: str
    response: str
    input_tokens_estimate: int
    output_tokens_estimate: int
    latency_ms: float
    response_hash: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["beast_object_type"] = "local_model_result"
        payload["version"] = "1.0"
        return payload


class LocalModelAdapter:
    """Small fail-closed adapter boundary for local inference routes.

    The default implementation is intentionally deterministic and offline. It
    gives Phase 4 a real adapter execution boundary without pretending that a
    heavyweight local model is installed on every development machine.
    """

    def __init__(self, model: str = "beast-local-adapter-v1") -> None:
        self.model = model

    def execute(self, *, task_class: str, prompt_hint: str = "", max_tokens: int = 128) -> LocalModelResult:
        started = time.perf_counter()
        text = (
            "Local adapter accepted bounded inference route for "
            f"{task_class or 'chat_completion'}."
        )
        if prompt_hint:
            digest = hashlib.sha256(prompt_hint.encode("utf-8")).hexdigest()[:12]
            text += f" prompt_hash={digest}."
        output_tokens = max(1, min(int(max_tokens or 128), len(text.split()) + 4))
        input_tokens = max(1, len(prompt_hint) // 4) if prompt_hint else 0
        encoded = json.dumps(
            {"model": self.model, "task_class": task_class, "response": text},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return LocalModelResult(
            adapter=self.__class__.__name__,
            model=self.model,
            task_class=task_class,
            status="succeeded",
            response=text,
            input_tokens_estimate=input_tokens,
            output_tokens_estimate=output_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            response_hash="sha256:" + hashlib.sha256(encoded).hexdigest(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
