from typing import Any, Dict, List, Optional
from app.kernel.storage.durable_inference_storage import RuntimeReplayResult

class HybridSemanticMatcher:
    def __init__(self, matchers: List[Any], threshold: float = 0.86):
        self.matchers = matchers
        self.threshold = threshold

    def __call__(self, request: Any) -> Optional[RuntimeReplayResult]:
        for matcher in self.matchers:
            result = matcher(request)
            if result and result.confidence >= self.threshold:
                return result
        return None
