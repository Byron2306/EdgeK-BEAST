from typing import Any, Optional
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, RuntimeReplayResult

class GPTCacheSemanticMatcher:
    def __init__(self, storage: DurableInferenceStorage, threshold: float = 0.86, require_repo_fingerprint: bool = True, require_verified: bool = True):
        self.storage = storage
        self.threshold = threshold
        self.require_repo_fingerprint = require_repo_fingerprint
        self.require_verified = require_verified

    def __call__(self, request: Any) -> Optional[RuntimeReplayResult]:
        # Native BEAST implementation using durable storage semantic search
        return self.storage.semantic_search(
            task_class=request.task_class,
            prompt=request.prompt,
            threshold=self.threshold,
            repo_fingerprint=request.repo_fingerprint,
            model=request.model,
            require_repo_fingerprint=self.require_repo_fingerprint,
            require_verified=self.require_verified,
        )
