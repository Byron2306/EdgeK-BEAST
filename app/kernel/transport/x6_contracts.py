from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json

class X6Refusal(ValueError):
    pass

def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

def digest_obj(obj: object) -> str:
    return "sha256:" + sha256(canonical(obj)).hexdigest()

@dataclass(frozen=True)
class SignedManifestEnvelope:
    sender_node: str
    receiver_node: str
    manifest_body: dict
    manifest_digest: str
    public_key_b64: str
    signature_b64: str
    nonce: str
    sequence: int
    def __post_init__(self):
        if not self.sender_node or not self.receiver_node:
            raise X6Refusal("node identity required")
        if self.sequence <= 0 or not self.nonce:
            raise X6Refusal("fresh nonce and positive sequence required")
        if not self.manifest_digest.startswith("sha256:"):
            raise X6Refusal("invalid manifest digest")
    def signed_body(self) -> dict:
        return {
            "sender_node": self.sender_node,
            "receiver_node": self.receiver_node,
            "manifest_body": self.manifest_body,
            "manifest_digest": self.manifest_digest,
            "nonce": self.nonce,
            "sequence": self.sequence,
        }

@dataclass
class X6Receipt:
    phase: str
    sender_node: str
    receiver_node: str
    manifest_digest: str
    object_digest: str
    signature_verified: bool
    sender_authorized: bool
    replay_safe: bool
    selected_lane: str
    fallback_used: bool
    chunks_total: int
    chunks_needed: int
    chunks_transmitted: int
    bytes_transmitted: int
    bytes_avoided: int
    reconstruction_verified: bool
    object_root_verified: bool
    receiver_cas_admitted: bool
    promotion_allowed: bool
    execution_allowed: bool
    raw_payload_retained_in_receipt: bool
    authority: str
    receipt_digest: str = ""
    def seal(self) -> "X6Receipt":
        body = asdict(self)
        body.pop("receipt_digest", None)
        self.receipt_digest = digest_obj(body)
        return self
