from typing import Any, Optional
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, RuntimeReplayResult

class LocalEmbeddingMatcher:
    def __init__(self, storage: DurableInferenceStorage, threshold: float = 0.90):
        self.storage = storage
        self.threshold = threshold

    def __call__(self, request: Any) -> Optional[RuntimeReplayResult]:
        # Native BEAST implementation using durable storage embedding search
        return self.storage.embedding_search(
            task_class=request.task_class,
            prompt=request.prompt,
            threshold=self.threshold,
        )
