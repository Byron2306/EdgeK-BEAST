from typing import Any, Optional
from app.kernel.storage.durable_inference_storage import RuntimeReplayResult
from app.kernel.compute.local_semantic_cache import LocalSemanticCache

class BeastLocalSemanticMatcher:
    def __init__(self, cache: LocalSemanticCache):
        self.cache = cache

    def __call__(self, request: Any) -> Optional[RuntimeReplayResult]:
        hit = self.cache.match(
            prompt=request.prompt,
            task_class=request.task_class,
            repo_fingerprint=request.repo_fingerprint or "",
            threshold=0.86,
            require_verified=True,
        )
        if hit is None:
            return None

        return RuntimeReplayResult(
            replay_type="semantic_credit",
            credit_id=hit.credit_id,
            reusable=True,
            payload={
                "answer": hit.answer,
                "source": "beast_local_semantic_cache",
                "metadata": hit.metadata,
            },
            avoided_tokens_estimate=max(1, len(request.prompt) // 4),
            confidence=hit.confidence,
            reason=hit.reason,
        )
