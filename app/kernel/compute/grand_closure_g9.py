from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


REQUIRED_GATES = tuple(f"G{i}" for i in range(1, 9))
FORBIDDEN_KEYS = {
    "raw_payload", "payload", "canonical_ir", "crystal_ir", "private_key",
    "secret", "token", "capability_secret", "file_descriptor", "fd",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_s = str(key).lower()
            if key_s in FORBIDDEN_KEYS or any(term in key_s for term in ("private_key", "capability_secret")):
                hits.append(f"{path}.{key}")
            hits.extend(_walk_forbidden(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            hits.extend(_walk_forbidden(item, f"{path}[{idx}]"))
    return hits


def _gate_from_name(path: Path, data: Mapping[str, Any]) -> str | None:
    explicit = str(data.get("gate", "")).upper()
    if explicit in REQUIRED_GATES:
        return explicit
    name = path.name.lower()
    for gate in REQUIRED_GATES:
        if gate.lower() in name or f"grand_closure.{gate.lower()}" in json.dumps(data).lower():
            return gate
    return None


def _extract_declared_digest(data: Mapping[str, Any]) -> str | None:
    preferred = (
        "closure_digest", "receipt_digest", "evidence_digest", "reconciliation_digest",
        "decision_digest", "promotion_digest", "bundle_digest",
    )
    for key in preferred:
        value = data.get(key)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    for key, value in data.items():
        if key.endswith("_digest") and isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    gate: str
    relative_path: str
    file_digest: str
    declared_digest: str | None
    size_bytes: int
    status: str | None
    raw_payload_retained: bool | None
    authority: str | None
    item_digest: str


@dataclass(frozen=True, slots=True)
class EvidenceValidation:
    required_gates: tuple[str, ...]
    present_gates: tuple[str, ...]
    missing_gates: tuple[str, ...]
    duplicate_gates: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    failed_status_items: tuple[str, ...]
    contradictory_invariants: tuple[str, ...]
    valid: bool
    validation_digest: str


@dataclass(frozen=True, slots=True)
class MerkleLayer:
    index: int
    nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class G9EvidenceBundle:
    bundle_version: int
    bundle_id: str
    created_at_ns: int
    source_root: str
    items: tuple[EvidenceItem, ...]
    validation: EvidenceValidation
    merkle_layers: tuple[MerkleLayer, ...]
    merkle_root: str
    invariants: Mapping[str, Any]
    authority: str
    raw_payload_retained: bool
    signature_algorithm: str | None
    signer_id: str | None
    public_key_b64: str | None
    signature_b64: str | None
    signed_root_digest: str
    bundle_digest: str


class RootSigner(Protocol):
    signer_id: str
    algorithm: str
    public_key_b64: str

    def sign(self, payload: bytes) -> bytes: ...


class Ed25519RootSigner:
    algorithm = "ed25519"

    def __init__(self, private_key: Any, *, signer_id: str) -> None:
        self._private_key = private_key
        self.signer_id = signer_id
        pub = private_key.public_key().public_bytes_raw()
        self.public_key_b64 = base64.b64encode(pub).decode("ascii")

    @classmethod
    def generate(cls, *, signer_id: str = "beast:g9:ephemeral") -> "Ed25519RootSigner":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return cls(Ed25519PrivateKey.generate(), signer_id=signer_id)

    @classmethod
    def from_private_key_file(cls, path: str | Path, *, signer_id: str) -> "Ed25519RootSigner":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        p = Path(path)
        mode = p.stat().st_mode & 0o777
        if mode & 0o077:
            raise PermissionError("G9 signing key must not be group/world accessible")
        raw = p.read_bytes().strip()
        try:
            key_bytes = base64.b64decode(raw, validate=True)
        except Exception:
            key_bytes = raw
        if len(key_bytes) != 32:
            raise ValueError("Ed25519 private key file must contain 32 raw bytes or base64")
        return cls(Ed25519PrivateKey.from_private_bytes(key_bytes), signer_id=signer_id)

    def sign(self, payload: bytes) -> bytes:
        return self._private_key.sign(payload)


def verify_bundle_signature(bundle: Mapping[str, Any]) -> bool:
    if bundle.get("signature_algorithm") != "ed25519":
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public = base64.b64decode(str(bundle["public_key_b64"]), validate=True)
        signature = base64.b64decode(str(bundle["signature_b64"]), validate=True)
        root = str(bundle["signed_root_digest"]).encode("ascii")
        Ed25519PublicKey.from_public_bytes(public).verify(signature, root)
        return True
    except Exception:
        return False


def _merkle(leaves: Iterable[str]) -> tuple[tuple[MerkleLayer, ...], str]:
    current = sorted(leaves)
    if not current:
        empty = _digest_bytes(b"")
        return (MerkleLayer(0, (empty,)),), empty
    layers: list[MerkleLayer] = [MerkleLayer(0, tuple(current))]
    index = 1
    while len(current) > 1:
        nxt: list[str] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else left
            nxt.append(_digest_bytes((left + "\n" + right).encode("ascii")))
        current = nxt
        layers.append(MerkleLayer(index, tuple(current)))
        index += 1
    return tuple(layers), current[0]


class GrandClosureG9:
    """Build a tamper-evident, payload-safe evidence bundle over G1-G8 receipts."""

    def __init__(self, *, evidence_dir: str | Path, output_dir: str | Path | None = None) -> None:
        self.evidence_dir = Path(evidence_dir).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.evidence_dir

    def _collect(self) -> tuple[list[EvidenceItem], list[str], list[str], list[str]]:
        items: list[EvidenceItem] = []
        forbidden: list[str] = []
        failed: list[str] = []
        contradictions: list[str] = []
        if not self.evidence_dir.exists():
            return items, forbidden, failed, ["evidence_directory_missing"]
        for path in sorted(self.evidence_dir.glob("*.json")):
            if path.name.startswith("g9-") or path.name.startswith("grand-closure-g9"):
                continue
            raw = path.read_bytes()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, Mapping):
                continue
            gate = _gate_from_name(path, data)
            if gate is None:
                continue
            hits = _walk_forbidden(data)
            forbidden.extend(f"{path.name}:{hit}" for hit in hits)
            status = data.get("status")
            if isinstance(status, str) and status.lower() in {"failed", "error", "refused"}:
                failed.append(path.name)
            raw_retained = data.get("raw_payload_retained")
            if raw_retained is True:
                contradictions.append(f"{path.name}:raw_payload_retained_true")
            if data.get("native_context_exported") is True:
                contradictions.append(f"{path.name}:native_context_exported_true")
            if data.get("promotion_granted") is True and gate in {"G1", "G2", "G3", "G4", "G6", "G7"}:
                contradictions.append(f"{path.name}:unexpected_promotion_granted")
            body = {
                "gate": gate,
                "relative_path": path.name,
                "file_digest": _digest_bytes(raw),
                "declared_digest": _extract_declared_digest(data),
                "size_bytes": len(raw),
                "status": status if isinstance(status, str) else None,
                "raw_payload_retained": raw_retained if isinstance(raw_retained, bool) else None,
                "authority": data.get("authority") if isinstance(data.get("authority"), str) else None,
            }
            items.append(EvidenceItem(**body, item_digest=_digest(body)))
        return items, forbidden, failed, contradictions

    def build(self, *, signer: RootSigner | None = None, require_signature: bool = False) -> G9EvidenceBundle:
        items, forbidden, failed, contradictions = self._collect()
        by_gate: dict[str, list[EvidenceItem]] = {gate: [] for gate in REQUIRED_GATES}
        for item in items:
            by_gate[item.gate].append(item)
        present = tuple(g for g in REQUIRED_GATES if by_gate[g])
        missing = tuple(g for g in REQUIRED_GATES if not by_gate[g])
        duplicates = tuple(g for g in REQUIRED_GATES if len(by_gate[g]) > 1)
        valid = not missing and not forbidden and not failed and not contradictions and (signer is not None or not require_signature)
        validation_body = {
            "required_gates": REQUIRED_GATES,
            "present_gates": present,
            "missing_gates": missing,
            "duplicate_gates": duplicates,
            "forbidden_fields": sorted(forbidden),
            "failed_status_items": sorted(failed),
            "contradictory_invariants": sorted(contradictions),
            "valid": valid,
        }
        validation = EvidenceValidation(
            required_gates=REQUIRED_GATES,
            present_gates=present,
            missing_gates=missing,
            duplicate_gates=duplicates,
            forbidden_fields=tuple(sorted(forbidden)),
            failed_status_items=tuple(sorted(failed)),
            contradictory_invariants=tuple(sorted(contradictions)),
            valid=valid,
            validation_digest=_digest(validation_body),
        )
        layers, root = _merkle(item.item_digest for item in items)
        invariants = {
            "all_required_gates_present": not missing,
            "no_forbidden_payload_fields": not forbidden,
            "no_failed_gate_receipts": not failed,
            "no_contradictory_invariants": not contradictions,
            "capsule_required_class": "read_only_repo_inspection",
            "raw_payload_retained": False,
            "ambient_execution_authority": False,
            "bundle_authority": "evidence_only",
        }
        signed_root = _digest({
            "merkle_root": root,
            "validation_digest": validation.validation_digest,
            "invariants": invariants,
            "required_gates": REQUIRED_GATES,
        })
        signature = signer.sign(signed_root.encode("ascii")) if signer else None
        created = time.time_ns()
        bundle_id = "g9_" + hashlib.sha256((signed_root + str(created)).encode()).hexdigest()[:24]
        body = {
            "bundle_version": 1,
            "bundle_id": bundle_id,
            "created_at_ns": created,
            "source_root": str(self.evidence_dir),
            "item_digests": [item.item_digest for item in items],
            "validation_digest": validation.validation_digest,
            "merkle_root": root,
            "invariants": invariants,
            "authority": "evidence_only",
            "raw_payload_retained": False,
            "signature_algorithm": signer.algorithm if signer else None,
            "signer_id": signer.signer_id if signer else None,
            "public_key_b64": signer.public_key_b64 if signer else None,
            "signature_b64": base64.b64encode(signature).decode("ascii") if signature else None,
            "signed_root_digest": signed_root,
        }
        return G9EvidenceBundle(
            bundle_version=1,
            bundle_id=bundle_id,
            created_at_ns=created,
            source_root=str(self.evidence_dir),
            items=tuple(items),
            validation=validation,
            merkle_layers=layers,
            merkle_root=root,
            invariants=invariants,
            authority="evidence_only",
            raw_payload_retained=False,
            signature_algorithm=signer.algorithm if signer else None,
            signer_id=signer.signer_id if signer else None,
            public_key_b64=signer.public_key_b64 if signer else None,
            signature_b64=base64.b64encode(signature).decode("ascii") if signature else None,
            signed_root_digest=signed_root,
            bundle_digest=_digest(body),
        )

    def write(self, bundle: G9EvidenceBundle) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"grand-closure-g9-{bundle.bundle_id}.json"
        temp = path.with_suffix(".json.tmp")
        payload = asdict(bundle)
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
        return path


def verify_bundle_file(path: str | Path) -> Mapping[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("items", [])
    layers, root = _merkle(item["item_digest"] for item in items)
    merkle_valid = root == data.get("merkle_root")
    signature_present = bool(data.get("signature_b64"))
    signature_valid = verify_bundle_signature(data) if signature_present else None
    bundle_valid = bool(data.get("validation", {}).get("valid")) and merkle_valid and signature_valid is not False
    return {
        "bundle_valid": bundle_valid,
        "validation_valid": bool(data.get("validation", {}).get("valid")),
        "merkle_valid": merkle_valid,
        "signature_present": signature_present,
        "signature_valid": signature_valid,
        "computed_merkle_root": root,
        "stored_merkle_root": data.get("merkle_root"),
        "layer_count": len(layers),
    }
