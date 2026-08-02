from __future__ import annotations
import enum, hashlib, json, time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


def _digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()

class CapsuleRolloutMode(str, enum.Enum):
    SHADOW='shadow'
    DUAL_VERIFY='dual_verify'
    CANARY='canary'
    CAPSULE_PRIMARY='capsule_primary'
    CAPSULE_REQUIRED='capsule_required'

@dataclass(frozen=True, slots=True)
class CapsuleRolloutPolicy:
    mode: CapsuleRolloutMode
    canary_task_classes: tuple[str, ...] = ()
    fallback_allowed: bool = True
    policy_digest: str = ''
    def __post_init__(self):
        if self.mode is CapsuleRolloutMode.CAPSULE_REQUIRED and self.fallback_allowed:
            raise ValueError('capsule-required mode cannot allow fallback')
        if self.mode is CapsuleRolloutMode.CANARY and not self.canary_task_classes:
            raise ValueError('canary mode requires task classes')
        if not self.policy_digest:
            object.__setattr__(self, 'policy_digest', _digest({'mode':self.mode.value,'canary':self.canary_task_classes,'fallback':self.fallback_allowed}))

@dataclass(frozen=True, slots=True)
class CapsuleParityReceipt:
    ir_equal: bool
    bounds_equal: bool
    verifier_equal: bool
    output_equal: bool
    parity_verified: bool
    receipt_digest: str

@dataclass(frozen=True, slots=True)
class CapsuleRolloutReceipt:
    mode: CapsuleRolloutMode
    selected_path: str
    fallback_used: bool
    capsule_attempted: bool
    capsule_verified: bool
    legacy_executed: bool
    parity_receipt: CapsuleParityReceipt | None
    status: str
    receipt_digest: str

class CapsuleRolloutController:
    """Migrate crystal execution without ever weakening verification for availability."""
    def __init__(self, *, policy: CapsuleRolloutPolicy, event_sink: Callable[[Mapping[str, Any]], Any] | None = None):
        self.policy=policy; self.event_sink=event_sink or (lambda e: None)
    def _parity(self, legacy: Mapping[str, Any], capsule: Mapping[str, Any]) -> CapsuleParityReceipt:
        ir = legacy.get('ir_digest') == capsule.get('ir_digest')
        bounds = legacy.get('bounds_digest') == capsule.get('bounds_digest')
        verifier = legacy.get('verifier_digest') == capsule.get('verifier_digest')
        output = legacy.get('output_digest') == capsule.get('output_digest')
        body={'ir_equal':ir,'bounds_equal':bounds,'verifier_equal':verifier,'output_equal':output,'parity_verified':ir and bounds and verifier and output}
        return CapsuleParityReceipt(**body, receipt_digest=_digest(body))
    def run(self, *, task_class: str, legacy_execute: Callable[[], Mapping[str, Any]], capsule_verify: Callable[[], Mapping[str, Any]], capsule_execute: Callable[[], Mapping[str, Any]]) -> tuple[Mapping[str, Any], CapsuleRolloutReceipt]:
        mode=self.policy.mode; cap_attempt=False; cap_verified=False; fallback=False; legacy_ran=False; parity=None
        if mode is CapsuleRolloutMode.SHADOW:
            legacy=legacy_execute(); legacy_ran=True; cap=capsule_verify(); cap_attempt=True; cap_verified=bool(cap.get('verified'))
            parity=self._parity(legacy,cap)
            status='shadow_parity' if parity.parity_verified else 'shadow_mismatch'
            result=legacy; selected='legacy'
        elif mode is CapsuleRolloutMode.DUAL_VERIFY:
            legacy=legacy_execute(); legacy_ran=True; cap=capsule_verify(); cap_attempt=True; cap_verified=bool(cap.get('verified'))
            parity=self._parity(legacy,cap)
            if not parity.parity_verified: raise RuntimeError('capsule dual-path parity failed')
            result=legacy; selected='legacy'
            status='dual_verified'
        elif mode is CapsuleRolloutMode.CANARY and task_class not in self.policy.canary_task_classes:
            result=legacy_execute(); legacy_ran=True; selected='legacy'; status='outside_canary'
        else:
            cap_attempt=True
            try:
                result=capsule_execute(); cap_verified=bool(result.get('verified'))
                if not cap_verified: raise RuntimeError('capsule outcome unverified')
                selected='capsule'; status='capsule_success'
            except Exception:
                if not self.policy.fallback_allowed:
                    raise
                result=legacy_execute(); legacy_ran=True; fallback=True; selected='legacy'; status='capsule_refused_fallback'
        body={'mode':mode.value,'selected_path':selected,'fallback_used':fallback,'capsule_attempted':cap_attempt,'capsule_verified':cap_verified,'legacy_executed':legacy_ran,'parity_receipt_digest':parity.receipt_digest if parity else None,'status':status,'policy_digest':self.policy.policy_digest,'created_ns':time.time_ns()}
        receipt=CapsuleRolloutReceipt(mode,selected,fallback,cap_attempt,cap_verified,legacy_ran,parity,status,_digest(body))
        self.event_sink({'event_type':'crystal.capsule_rollout_transition',**body,'receipt_digest':receipt.receipt_digest})
        return result,receipt
