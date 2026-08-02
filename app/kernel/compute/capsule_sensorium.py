from __future__ import annotations
import hashlib, json, time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


def _digest(value: Mapping[str, Any]) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class CapsuleLifecycleEventReceipt:
    event_type: str
    capsule_id: str
    event_digest: str
    emitted_at_ns: int
    payload_safe: bool = True

class CapsuleSensoriumProjector:
    """Project capsule lifecycle metadata without raw IR, secrets, or authority material."""
    ALLOWED = {
        'crystal.capsule_created','crystal.capsule_sealed','crystal.capsule_registered',
        'crystal.capsule_offered','crystal.capsule_received','crystal.capsule_verified',
        'crystal.capsule_refused','crystal.capsule_executed','crystal.capsule_closed',
        'crystal.capsule_shadow_compared','crystal.capsule_rollout_transition',
    }
    FORBIDDEN_KEYS = {'canonical_ir','raw_ir','private_key','capability_secret','token','fd','payload'}
    def __init__(self, sink: Callable[[Mapping[str, Any]], Any] | None = None):
        self.sink = sink or (lambda event: None)
    def emit(self, event_type: str, *, capsule_id: str, crystal_id: str, capsule_digest: str, **metadata: Any) -> CapsuleLifecycleEventReceipt:
        if event_type not in self.ALLOWED:
            raise ValueError('unsupported capsule lifecycle event')
        if self.FORBIDDEN_KEYS.intersection(metadata):
            raise ValueError('unsafe capsule event metadata')
        event = {
            'event_type': event_type,
            'capsule_id': capsule_id,
            'crystal_id': crystal_id,
            'capsule_digest': capsule_digest,
            'metadata': dict(metadata),
            'raw_ir_retained': False,
            'authority_secret_retained': False,
            'emitted_at_ns': time.time_ns(),
        }
        digest = _digest(event)
        self.sink({**event, 'event_digest': digest})
        return CapsuleLifecycleEventReceipt(event_type, capsule_id, digest, event['emitted_at_ns'])
