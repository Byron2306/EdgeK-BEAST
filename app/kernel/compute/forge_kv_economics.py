"""Measured economics for Forge-managed Ollama context reuse."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.kernel.compute.forge_kv_proof_status import claim_status

@dataclass(frozen=True)
class ForgeKVEconomics:
    reuse_mode: str
    lookup_ms: float
    execution_ms: float
    prompt_eval_count: int
    prompt_eval_duration_ns: int
    native_context_supplied: bool
    native_context_returned: bool
    estimated_context_bytes: int
    measured: bool = True
    performance_claim_allowed: bool = False

    @property
    def prompt_eval_ms(self) -> float:
        return max(0, self.prompt_eval_duration_ns) / 1_000_000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "forge_kv_economics",
            "version": "1.0",
            **asdict(self),
            "prompt_eval_ms": round(self.prompt_eval_ms, 3),
            "claim_boundary": (
                "A reuse classification is not itself a compute-saving claim. "
                "Ollama legacy context has failed the live paired savings proof."
            ),
            "proof_status": claim_status(
                engine="ollama_api_generate_context",
                native_context_supplied=self.native_context_supplied,
            ),
        }


def economics_from_result(result: Mapping[str, Any], *, lookup_ms: float, context_bytes: int) -> ForgeKVEconomics:
    return ForgeKVEconomics(
        reuse_mode=str(result.get("reuse_mode") or "miss"),
        lookup_ms=max(0.0, float(lookup_ms)),
        execution_ms=max(0.0, float(result.get("latency_ms") or 0.0)),
        prompt_eval_count=max(0, int(result.get("prompt_eval_count") or 0)),
        prompt_eval_duration_ns=max(0, int(result.get("prompt_eval_duration") or 0)),
        native_context_supplied=bool(result.get("native_context_supplied")),
        native_context_returned=bool(result.get("native_context_returned")),
        estimated_context_bytes=max(0, int(context_bytes)),
    )
