"""CPU-first local execution gateway for BEAST inference requests."""

from __future__ import annotations

from typing import Any, Optional


class LocalExecutionGateway:
    """Route execution to configured local CPU engines before any cloud path."""

    def __init__(self, engine_fabric: Any, route_optimizer: Optional[Any] = None) -> None:
        self.engine_fabric = engine_fabric
        self.route_optimizer = route_optimizer

    def select_engine(self, request: Any) -> str:
        candidates = self.engine_fabric.cpu_candidates()
        candidate_ids = {candidate.engine_id for candidate in candidates}

        if getattr(request, "preferred_engine", None):
            preferred = request.preferred_engine
            if preferred not in candidate_ids:
                raise RuntimeError(f"{preferred} is not a configured local CPU inference engine")
            return preferred

        if self.route_optimizer is not None:
            chosen = self.route_optimizer.choose_route(request)
            if chosen and chosen in candidate_ids:
                return chosen

        if not candidates:
            raise RuntimeError("No configured local CPU inference engine available")

        preferred = ["ollama", "llama_cpp"]
        for engine_id in preferred:
            if any(candidate.engine_id == engine_id for candidate in candidates):
                return engine_id

        return candidates[0].engine_id

    def complete(self, request: Any) -> dict[str, Any]:
        engine_id = self.select_engine(request)
        result = self.engine_fabric.generate(
            engine_id,
            model=request.model,
            prompt=request.prompt,
            system_prompt=getattr(request, "system_prompt", ""),
            max_tokens=int(getattr(request, "parameters", {}).get("max_tokens", 512)),
        )
        result["route"] = "local_cpu"
        result["cloud_used"] = False
        return result
