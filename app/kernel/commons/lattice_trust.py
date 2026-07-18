"""Crystal-compute lattice attestations for the transport-agnostic Trust Commons."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, Mapping

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .remote_protocol import canonical_json, sha256_bytes


ATTESTATION_TYPE = "commons_crystal_lattice_attestation"


def lattice_attestation_body(value: Mapping[str, Any]) -> bytes:
    fields = (
        "beast_object_type", "schema_version", "attestation_id", "authority", "key_id",
        "subject_node_id", "subject_digest", "lattice_head_hash", "checkpoint_count",
        "crystal_chain_head_hash", "crystal_chain_height", "policy_generation",
        "assurance_class", "issued_at", "expires_at", "claim_boundary",
    )
    return canonical_json({field: value.get(field) for field in fields})


class CrystalLatticeAttestationIssuer:
    def __init__(self, private_key: Ed25519PrivateKey, *, authority: str, key_id: str, policy_generation: str):
        self.private_key = private_key
        self.authority = str(authority)
        self.key_id = str(key_id)
        self.policy_generation = str(policy_generation)
        if not self.authority or not self.key_id or not self.policy_generation:
            raise ValueError("lattice attestation issuer identity is incomplete")

    def issue(
        self, *, subject: Mapping[str, Any], lattice_verification: Mapping[str, Any],
        chain_verification: Mapping[str, Any] | None = None, ttl_seconds: int = 900,
        now: float | None = None,
    ) -> dict[str, Any]:
        if lattice_verification.get("valid") is not True:
            raise PermissionError("invalid crystal lattice cannot attest a Commons node")
        lattice_head = str(lattice_verification.get("head_hash") or "")
        if not lattice_head.startswith("sha256:"):
            raise ValueError("crystal lattice attestation requires a ledger head")
        chain = dict(chain_verification or {})
        if chain and chain.get("valid") is not True:
            raise PermissionError("invalid crystal chain cannot strengthen a lattice attestation")
        moment = time.time() if now is None else float(now)
        subject_digest = sha256_bytes(canonical_json(subject))
        core = {
            "beast_object_type": ATTESTATION_TYPE,
            "schema_version": "1.0",
            "authority": self.authority,
            "key_id": self.key_id,
            "subject_node_id": str(subject.get("node_id") or ""),
            "subject_digest": subject_digest,
            "lattice_head_hash": lattice_head,
            "checkpoint_count": int(lattice_verification.get("checkpoint_count") or 0),
            "crystal_chain_head_hash": str(chain.get("head_hash") or ""),
            "crystal_chain_height": int(chain.get("block_count") or 0),
            "policy_generation": self.policy_generation,
            "assurance_class": "crystal_lattice_witnessed",
            "issued_at": moment,
            "expires_at": moment + max(30, int(ttl_seconds)),
            "claim_boundary": "lattice_proves_witnessed_compute_history_not_host_hardware_or_global_consensus",
        }
        core["attestation_id"] = "cla_" + sha256_bytes(canonical_json(core))[7:31]
        core["signature"] = base64.b64encode(self.private_key.sign(lattice_attestation_body(core))).decode("ascii")
        return core


@dataclass(frozen=True)
class LatticeAuthority:
    authority: str
    key_id: str
    public_key: Ed25519PublicKey
    policy_generations: frozenset[str]
    accepted_lattice_heads: frozenset[str] = frozenset()
    minimum_checkpoint_count: int = 1


class CrystalLatticeTrustStore:
    def __init__(self, authorities: list[LatticeAuthority]):
        self._authorities = {(item.authority, item.key_id): item for item in authorities}

    @classmethod
    def from_file(cls, path: str | Path) -> "CrystalLatticeTrustStore":
        source = Path(path).expanduser().resolve()
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        records = payload.get("lattice_authorities") or []
        if isinstance(records, Mapping):
            records = [dict(value or {}, authority=authority) for authority, value in records.items()]
        result = []
        seen: set[tuple[str, str]] = set()
        for record in records:
            authority = str(record.get("authority") or "")
            key_id = str(record.get("key_id") or "")
            if record.get("public_key_pem_b64"):
                pem = base64.b64decode(str(record["public_key_pem_b64"]), validate=True)
            else:
                key_path = (source.parent / str(record.get("public_key_path") or "")).resolve()
                if key_path != source.parent and source.parent not in key_path.parents:
                    raise ValueError("lattice authority key path escapes trust-store directory")
                pem = key_path.read_bytes()
            key = serialization.load_pem_public_key(pem)
            if not authority or not key_id or not isinstance(key, Ed25519PublicKey):
                raise ValueError("invalid crystal lattice trust authority")
            identity = (authority, key_id)
            if identity in seen:
                raise ValueError("duplicate crystal lattice trust authority")
            seen.add(identity)
            policy_generations = frozenset(str(item) for item in (record.get("policy_generations") or ()))
            accepted_heads = frozenset(str(item) for item in (record.get("accepted_lattice_heads") or ()))
            if not policy_generations or not accepted_heads:
                raise ValueError("lattice trust authorities require explicit policy generations and accepted heads")
            result.append(LatticeAuthority(
                authority, key_id, key,
                policy_generations,
                accepted_heads,
                max(1, int(record.get("minimum_checkpoint_count") or 1)),
            ))
        return cls(result)

    def verify(
        self, evidence: Mapping[str, Any], *, expected_subject: Mapping[str, Any],
        now: float | None = None,
    ) -> dict[str, Any]:
        if evidence.get("beast_object_type") != ATTESTATION_TYPE:
            raise PermissionError("not a crystal lattice Commons attestation")
        authority = self._authorities.get((str(evidence.get("authority") or ""), str(evidence.get("key_id") or "")))
        if authority is None:
            raise PermissionError("crystal lattice authority is not trusted")
        if authority.policy_generations and str(evidence.get("policy_generation") or "") not in authority.policy_generations:
            raise PermissionError("crystal lattice policy generation is not trusted")
        expected_digest = sha256_bytes(canonical_json(expected_subject))
        instant = time.time() if now is None else float(now)
        lattice_head = str(evidence.get("lattice_head_hash") or "")
        checkpoint_count = int(evidence.get("checkpoint_count") or 0)
        issued_at = float(evidence.get("issued_at") or 0)
        expires_at = float(evidence.get("expires_at") or 0)
        if (
            evidence.get("schema_version") != "1.0"
            or evidence.get("claim_boundary") != "lattice_proves_witnessed_compute_history_not_host_hardware_or_global_consensus"
            or evidence.get("subject_digest") != expected_digest
            or evidence.get("subject_node_id") != expected_subject.get("node_id")
            or evidence.get("assurance_class") != "crystal_lattice_witnessed"
            or len(lattice_head) != 71 or not lattice_head.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in lattice_head[7:])
            or checkpoint_count < authority.minimum_checkpoint_count
            or (authority.accepted_lattice_heads and lattice_head not in authority.accepted_lattice_heads)
            or not (issued_at <= instant < expires_at)
            or expires_at - issued_at > 31 * 24 * 60 * 60
        ):
            raise PermissionError("crystal lattice attestation binding or freshness failed")
        try:
            authority.public_key.verify(
                base64.b64decode(str(evidence.get("signature") or ""), validate=True),
                lattice_attestation_body(evidence),
            )
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise PermissionError("crystal lattice attestation signature failed") from exc
        return {
            "verified": True,
            "attestation_id": evidence.get("attestation_id"),
            "authority": evidence.get("authority"),
            "policy_generation": evidence.get("policy_generation"),
            "lattice_head_hash": evidence.get("lattice_head_hash"),
            "checkpoint_count": checkpoint_count,
            "assurance_class": evidence.get("assurance_class"),
            "issued_at": float(evidence.get("issued_at") or 0),
            "expires_at": float(evidence.get("expires_at") or 0),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "authority_count": len(self._authorities),
            "authorities": [
                {
                    "authority": row.authority,
                    "key_id": row.key_id,
                    "policy_generations": sorted(row.policy_generations),
                    "accepted_lattice_heads": sorted(row.accepted_lattice_heads),
                    "minimum_checkpoint_count": row.minimum_checkpoint_count,
                }
                for row in self._authorities.values()
            ],
        }
