from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, Sequence


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + sha256(raw).hexdigest()


@dataclass(frozen=True)
class RestoreObservation:
    restored: bool
    prompt_eval_count: int
    prompt_eval_duration_ns: int
    continuation: str
    context_digest_observed: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class RestoreVerificationReceipt:
    restored: bool
    continuation_equivalent: bool
    prefill_displaced: bool
    prompt_tokens_avoided: int
    prompt_eval_ns_avoided: int
    source_context_digest: str
    observed_context_digest: str
    verifier_id: str
    authority: str
    refusal_reason: str | None
    receipt_digest: str


class NativeContextRestoreVerifier:
    def __init__(self, verifier_id: str = "prism-r7-native-restore-v1") -> None:
        self.verifier_id = verifier_id

    def verify(
        self,
        *,
        source_context_digest: str,
        baseline: RestoreObservation,
        restored: RestoreObservation,
        equivalence: Callable[[str, str], bool] | None = None,
    ) -> RestoreVerificationReceipt:
        eq = equivalence or (lambda a, b: a == b)
        digest_ok = restored.context_digest_observed == source_context_digest
        continuation_ok = bool(restored.restored and eq(baseline.continuation, restored.continuation))
        tokens_avoided = max(0, baseline.prompt_eval_count - restored.prompt_eval_count)
        ns_avoided = max(0, baseline.prompt_eval_duration_ns - restored.prompt_eval_duration_ns)
        displaced = digest_ok and continuation_ok and tokens_avoided > 0 and ns_avoided > 0
        refusal = None
        if not restored.restored:
            refusal = "restore_failed"
        elif not digest_ok:
            refusal = "context_digest_mismatch"
        elif not continuation_ok:
            refusal = "continuation_not_equivalent"
        elif not displaced:
            refusal = "no_measurable_prefill_displacement"
        body = {
            "restored": restored.restored and digest_ok,
            "continuation_equivalent": continuation_ok,
            "prefill_displaced": displaced,
            "prompt_tokens_avoided": tokens_avoided,
            "prompt_eval_ns_avoided": ns_avoided,
            "source_context_digest": source_context_digest,
            "observed_context_digest": restored.context_digest_observed,
            "verifier_id": self.verifier_id,
            "authority": "verify_only",
            "refusal_reason": refusal,
        }
        return RestoreVerificationReceipt(**body, receipt_digest=_digest(body))
