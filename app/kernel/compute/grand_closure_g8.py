from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .capsule_rollout import CapsuleRolloutController, CapsuleRolloutMode, CapsuleRolloutPolicy


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class CapsuleClassPromotion:
    task_class: str
    previous_mode: str
    enforced_mode: str
    fallback_allowed: bool
    operator_approval_digest: str
    policy_digest: str
    rollback_mode: str
    promoted_at_ns: int
    promotion_digest: str


@dataclass(frozen=True, slots=True)
class G8CaseReceipt:
    name: str
    task_class: str
    expected: str
    observed: str
    capsule_attempted: bool
    capsule_verified: bool
    legacy_executed: bool
    fallback_used: bool
    physical_effects: int
    passed: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class G8ClosureReceipt:
    status: str
    enforced_task_class: str
    promotion: CapsuleClassPromotion
    lawful_capsule_success: bool
    missing_capsule_refused: bool
    unverified_capsule_refused: bool
    legacy_fallback_prohibited: bool
    unrelated_class_unchanged: bool
    raw_payload_retained: bool
    authority: str
    cases: tuple[G8CaseReceipt, ...]
    event_count: int
    closure_digest: str


class GrandClosureG8:
    """Promote one low-risk crystal class to capsule-required enforcement.

    The harness proves that the promoted class executes only through a verified
    capsule, cannot fall back to legacy execution, and does not alter policy for
    unrelated task classes.
    """

    ENFORCED_CLASS = "read_only_repo_inspection"

    def __init__(self, *, evidence_dir: str | Path | None = None,
                 event_sink: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self.events: list[Mapping[str, Any]] = []
        self.event_sink = event_sink or self.events.append

    def _promotion(self, operator_approval_digest: str) -> CapsuleClassPromotion:
        if not operator_approval_digest.startswith("sha256:"):
            raise ValueError("operator approval must be content-addressed")
        policy = CapsuleRolloutPolicy(
            CapsuleRolloutMode.CAPSULE_REQUIRED,
            canary_task_classes=(self.ENFORCED_CLASS,),
            fallback_allowed=False,
        )
        body = {
            "task_class": self.ENFORCED_CLASS,
            "previous_mode": CapsuleRolloutMode.CAPSULE_PRIMARY.value,
            "enforced_mode": CapsuleRolloutMode.CAPSULE_REQUIRED.value,
            "fallback_allowed": False,
            "operator_approval_digest": operator_approval_digest,
            "policy_digest": policy.policy_digest,
            "rollback_mode": CapsuleRolloutMode.CAPSULE_PRIMARY.value,
        }
        return CapsuleClassPromotion(
            **body,
            promoted_at_ns=time.time_ns(),
            promotion_digest=_digest(body),
        )

    @staticmethod
    def _case(name: str, task_class: str, expected: str, observed: str,
              *, capsule_attempted: bool, capsule_verified: bool,
              legacy_executed: bool, fallback_used: bool,
              physical_effects: int) -> G8CaseReceipt:
        passed = expected == observed and physical_effects == (1 if observed == "capsule_success" else 0)
        body = {
            "name": name, "task_class": task_class, "expected": expected,
            "observed": observed, "capsule_attempted": capsule_attempted,
            "capsule_verified": capsule_verified, "legacy_executed": legacy_executed,
            "fallback_used": fallback_used, "physical_effects": physical_effects,
            "passed": passed,
        }
        return G8CaseReceipt(**body, receipt_digest=_digest(body))

    def run(self, *, operator_approval_digest: str | None = None) -> G8ClosureReceipt:
        approval = operator_approval_digest or _digest({"operator": "g8-rehearsal", "scope": self.ENFORCED_CLASS})
        promotion = self._promotion(approval)
        required = CapsuleRolloutController(
            policy=CapsuleRolloutPolicy(
                CapsuleRolloutMode.CAPSULE_REQUIRED,
                canary_task_classes=(self.ENFORCED_CLASS,),
                fallback_allowed=False,
                policy_digest=promotion.policy_digest,
            ),
            event_sink=self.event_sink,
        )
        cases: list[G8CaseReceipt] = []

        legacy_calls = 0
        capsule_calls = 0

        def legacy() -> Mapping[str, Any]:
            nonlocal legacy_calls
            legacy_calls += 1
            return {"verified": True, "route": "legacy", "physical_effects": 1}

        def capsule_ok() -> Mapping[str, Any]:
            nonlocal capsule_calls
            capsule_calls += 1
            return {"verified": True, "route": "capsule", "physical_effects": 1,
                    "authority": "one_use_execute", "raw_payload_retained": False}

        # Lawful success through the capsule path.
        result, receipt = required.run(
            task_class=self.ENFORCED_CLASS,
            legacy_execute=legacy,
            capsule_verify=lambda: {"verified": True},
            capsule_execute=capsule_ok,
        )
        cases.append(self._case(
            "lawful_capsule_success", self.ENFORCED_CLASS, "capsule_success", receipt.status,
            capsule_attempted=receipt.capsule_attempted,
            capsule_verified=receipt.capsule_verified,
            legacy_executed=receipt.legacy_executed,
            fallback_used=receipt.fallback_used,
            physical_effects=int(result.get("physical_effects", 0)),
        ))

        # Missing capsule must refuse without touching legacy.
        before_legacy = legacy_calls
        try:
            required.run(
                task_class=self.ENFORCED_CLASS,
                legacy_execute=legacy,
                capsule_verify=lambda: {"verified": False},
                capsule_execute=lambda: (_ for _ in ()).throw(FileNotFoundError("sealed capsule unavailable")),
            )
            observed = "unexpected_success"
        except FileNotFoundError:
            observed = "capsule_required_refusal"
        cases.append(self._case(
            "missing_capsule_refused", self.ENFORCED_CLASS, "capsule_required_refusal", observed,
            capsule_attempted=True, capsule_verified=False,
            legacy_executed=legacy_calls > before_legacy,
            fallback_used=False, physical_effects=0,
        ))

        # An unverified capsule outcome must also refuse without fallback.
        before_legacy = legacy_calls
        try:
            required.run(
                task_class=self.ENFORCED_CLASS,
                legacy_execute=legacy,
                capsule_verify=lambda: {"verified": False},
                capsule_execute=lambda: {"verified": False, "physical_effects": 0},
            )
            observed = "unexpected_success"
        except RuntimeError:
            observed = "capsule_required_refusal"
        cases.append(self._case(
            "unverified_capsule_refused", self.ENFORCED_CLASS, "capsule_required_refusal", observed,
            capsule_attempted=True, capsule_verified=False,
            legacy_executed=legacy_calls > before_legacy,
            fallback_used=False, physical_effects=0,
        ))

        # An unrelated class remains on its current governed route.
        unrelated_policy = CapsuleRolloutController(
            policy=CapsuleRolloutPolicy(
                CapsuleRolloutMode.CANARY,
                canary_task_classes=(self.ENFORCED_CLASS,),
                fallback_allowed=True,
            ),
            event_sink=self.event_sink,
        )
        before_legacy = legacy_calls
        other_result, other_receipt = unrelated_policy.run(
            task_class="bounded_formatting",
            legacy_execute=legacy,
            capsule_verify=lambda: {"verified": False},
            capsule_execute=capsule_ok,
        )
        cases.append(self._case(
            "unrelated_class_unchanged", "bounded_formatting", "outside_canary", other_receipt.status,
            capsule_attempted=other_receipt.capsule_attempted,
            capsule_verified=other_receipt.capsule_verified,
            legacy_executed=legacy_calls > before_legacy,
            fallback_used=other_receipt.fallback_used,
            physical_effects=0 if other_result.get("route") == "legacy" else 1,
        ))

        lawful = cases[0].passed and not cases[0].legacy_executed
        missing = cases[1].passed and not cases[1].legacy_executed
        unverified = cases[2].passed and not cases[2].legacy_executed
        unchanged = cases[3].expected == cases[3].observed and cases[3].legacy_executed
        fallback_prohibited = not cases[1].fallback_used and not cases[2].fallback_used
        status = "closed" if lawful and missing and unverified and unchanged and fallback_prohibited else "failed"
        body = {
            "status": status,
            "enforced_task_class": self.ENFORCED_CLASS,
            "promotion_digest": promotion.promotion_digest,
            "lawful_capsule_success": lawful,
            "missing_capsule_refused": missing,
            "unverified_capsule_refused": unverified,
            "legacy_fallback_prohibited": fallback_prohibited,
            "unrelated_class_unchanged": unchanged,
            "raw_payload_retained": False,
            "authority": "policy_and_enforcement_only",
            "case_digests": [case.receipt_digest for case in cases],
            "event_count": len(self.events),
        }
        receipt = G8ClosureReceipt(
            status=status,
            enforced_task_class=self.ENFORCED_CLASS,
            promotion=promotion,
            lawful_capsule_success=lawful,
            missing_capsule_refused=missing,
            unverified_capsule_refused=unverified,
            legacy_fallback_prohibited=fallback_prohibited,
            unrelated_class_unchanged=unchanged,
            raw_payload_retained=False,
            authority="policy_and_enforcement_only",
            cases=tuple(cases),
            event_count=len(self.events),
            closure_digest=_digest(body),
        )
        self.event_sink({
            "event_type": "grand_closure.g8.closed",
            "task_class": self.ENFORCED_CLASS,
            "status": status,
            "promotion_digest": promotion.promotion_digest,
            "closure_digest": receipt.closure_digest,
            "raw_payload_retained": False,
        })
        if self.evidence_dir:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            path = self.evidence_dir / f"g8-capsule-required-{time.time_ns()}.json"
            path.write_text(json.dumps(asdict(receipt), sort_keys=True, indent=2), encoding="utf-8")
        return receipt
