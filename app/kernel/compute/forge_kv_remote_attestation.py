"""One-use remote attestation challenges for receiving Forge nodes."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass, replace
from threading import RLock
from typing import Any, Callable, Mapping


def _digest(value: Any) -> str:
    body=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,default=str).encode()
    return "sha256:"+hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class AttestationChallenge:
    challenge_id: str
    node_id: str
    audience: str
    nonce: str
    policy_digest: str
    verifier_digest: str
    issued_at: float
    expires_at: float
    digest: str = ""

    def sealed(self) -> "AttestationChallenge":
        value=asdict(self); value.pop("digest",None)
        return replace(self,digest=_digest(value))

    def validate(self, *, now: float | None = None) -> None:
        value=asdict(self); supplied=value.pop("digest")
        if supplied != _digest(value): raise ValueError("attestation challenge tampered")
        if (time.time() if now is None else now) >= self.expires_at: raise PermissionError("attestation challenge expired")


class RemoteAttestationGate:
    def __init__(self):
        self._issued: dict[str, AttestationChallenge] = {}
        self._consumed: set[str] = set()
        self._lock=RLock()

    def issue(self, *, node_id: str, audience: str, policy_digest: str, verifier_digest: str,
              ttl_seconds: float = 300, now: float | None = None) -> AttestationChallenge:
        clock=time.time() if now is None else now
        nonce=secrets.token_hex(32)
        item=AttestationChallenge(
            challenge_id="challenge:"+secrets.token_hex(16), node_id=node_id, audience=audience,
            nonce=nonce, policy_digest=policy_digest, verifier_digest=verifier_digest,
            issued_at=clock, expires_at=clock+max(1.0,float(ttl_seconds)),
        ).sealed()
        with self._lock: self._issued[item.challenge_id]=item
        return item

    def verify_and_consume(self, *, challenge_id: str, evidence: Mapping[str, Any],
                           verifier: Callable[[AttestationChallenge, Mapping[str, Any]], bool],
                           now: float | None = None) -> dict[str, Any]:
        with self._lock:
            challenge=self._issued.get(challenge_id)
            if challenge is None: raise PermissionError("unknown attestation challenge")
            if challenge_id in self._consumed: raise PermissionError("attestation challenge already consumed")
        challenge.validate(now=now)
        if str(evidence.get("nonce") or "") != challenge.nonce: raise PermissionError("attestation nonce mismatch")
        if str(evidence.get("node_id") or "") != challenge.node_id: raise PermissionError("attestation node mismatch")
        if not verifier(challenge,evidence): raise PermissionError("attestation evidence rejected")
        with self._lock: self._consumed.add(challenge_id)
        return {"beast_object_type":"forge_receiver_attestation_receipt","version":"1.0",
                "challenge_digest":challenge.digest,"node_id":challenge.node_id,
                "verified":True,"consumed":True,"authority":"verify_only"}
