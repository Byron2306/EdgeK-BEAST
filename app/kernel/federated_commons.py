"""Federated Commons envelopes that preserve local trust and authority."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.crystal_seal import canonical_bytes, seal_crystal_payload, verify_crystal_seal


class FederatedCommons:
    MAX_ARTIFACTS = 128
    MAX_ENVELOPE_BYTES = 512_000
    MAX_INGESTS_PER_DAY = 100
    MAX_TTL_DAYS = 90

    def __init__(self, registry: Any, root: Optional[Path] = None):
        self.registry = registry
        self.root = (root or registry.root / "federation").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"

    def prepare(self, space_id: str, *, contributor_id: str, ttl_days: int = 30) -> Dict[str, Any]:
        detail = self.registry.get(space_id)
        if not detail["manifest_validation"].get("valid") or not detail["receipt_validation"].get("valid"):
            raise ValueError("only locally valid Spaces can be federated")
        ttl = max(1, min(int(ttl_days), self.MAX_TTL_DAYS))
        payload = {
            "beast_object_type": "federated_commons_space_envelope",
            "version": "1.0",
            "contributor_id": self._identifier(contributor_id, "contributor_id"),
            "space_id": space_id,
            "manifest": detail["manifest"],
            "reduction_receipt": detail["reduction_receipt"],
            "authority": "remote_hypothesis",
            "issued_at": self._now(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=ttl)).isoformat(),
            "revocation_supported": True,
        }
        payload["envelope_id"] = "fed_" + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:24]
        payload["signature"] = self._sign_ed25519(payload)
        optional_pq = seal_crystal_payload(payload, purpose="federated_commons_manifest_pq")
        if (optional_pq.get("crypto_profile") or {}).get("provider") == "liboqs":
            payload["optional_pq_seal"] = optional_pq
        return payload

    def allow_contributor(
        self,
        contributor_id: str,
        *,
        public_key_hash: str,
        approved: bool,
        reason: str,
    ) -> Dict[str, Any]:
        contributor_id = self._identifier(contributor_id, "contributor_id")
        if not approved or not reason.strip():
            raise ValueError("allowlisting requires explicit approval and a reason")
        if not self._valid_sha256(public_key_hash):
            raise ValueError("allowlisting requires a valid Ed25519 public_key_hash")
        state = self._load()
        state["allowlist"][contributor_id] = {
            "public_key_hash": public_key_hash,
            "approved_at": self._now(),
            "reason": reason,
        }
        self._save(state)
        return {"contributor_id": contributor_id, "allowlisted": True, **state["allowlist"][contributor_id]}

    def ingest(self, envelope: Dict[str, Any], *, require_allowlisted: bool = True) -> Dict[str, Any]:
        encoded = canonical_bytes(envelope)
        if len(encoded) > self.MAX_ENVELOPE_BYTES:
            raise ValueError("federated envelope exceeds size limit")
        contributor_id = self._identifier(str(envelope.get("contributor_id") or ""), "contributor_id")
        envelope_id = self._identifier(str(envelope.get("envelope_id") or ""), "envelope_id")
        state = self._load()
        if require_allowlisted and contributor_id not in state["allowlist"]:
            raise ValueError("contributor is not locally allowlisted")
        allowlist_record = state["allowlist"].get(contributor_id) or {}
        signature_record = envelope.get("signature") if isinstance(envelope.get("signature"), dict) else {}
        if require_allowlisted and signature_record.get("public_key_hash") != allowlist_record.get("public_key_hash"):
            raise ValueError("contributor signing key does not match the local allowlist pin")
        if envelope_id in state["revocations"]:
            raise ValueError("federated envelope is revoked")
        if envelope_id in state["envelopes"]:
            return {"accepted": False, "duplicate": True, "envelope_id": envelope_id, "state": "existing_hypothesis"}
        issued = self._parse_time(str(envelope.get("issued_at") or ""))
        expires = self._parse_time(str(envelope.get("expires_at") or ""))
        now = datetime.now(timezone.utc)
        if expires <= now or expires - issued > timedelta(days=self.MAX_TTL_DAYS):
            raise ValueError("federated envelope is expired or exceeds the TTL limit")
        artifacts = (envelope.get("manifest") or {}).get("artifacts") or []
        if len(artifacts) > self.MAX_ARTIFACTS:
            raise ValueError("federated envelope exceeds artifact limit")
        recent = [
            row for row in state["ingest_events"]
            if row.get("contributor_id") == contributor_id
            and self._parse_time(row["created_at"]) > now - timedelta(days=1)
        ]
        if len(recent) >= self.MAX_INGESTS_PER_DAY:
            raise ValueError("federated contributor ingest rate limit exceeded")
        payload = dict(envelope)
        signature = payload.pop("signature", {})
        optional_pq = payload.pop("optional_pq_seal", None)
        verification = self._verify_ed25519(payload, signature)
        if not verification.get("verified"):
            raise ValueError("federated envelope signature did not verify")
        pq_verification = verify_crystal_seal({**payload, "signature": signature}, optional_pq) if isinstance(optional_pq, dict) else {
            "verified": False, "available": False,
        }
        record = {
            "envelope_id": envelope_id,
            "contributor_id": contributor_id,
            "space_id": envelope.get("space_id"),
            "manifest_hash": (envelope.get("manifest") or {}).get("manifest_hash"),
            "expires_at": envelope.get("expires_at"),
            "state": "quarantined_hypothesis",
            "signature": verification,
            "optional_pq_verification": pq_verification,
            "ingested_at": self._now(),
        }
        state["envelopes"][envelope_id] = record
        state["ingest_events"].append({"envelope_id": envelope_id, "contributor_id": contributor_id, "created_at": self._now()})
        state["ingest_events"] = state["ingest_events"][-2000:]
        self._save(state)
        return {"accepted": True, "duplicate": False, **record, "authority": "local_reproduction_required"}

    def record_reproduction(self, envelope_id: str, receipt: Dict[str, Any]) -> Dict[str, Any]:
        state = self._load()
        if envelope_id not in state["envelopes"]:
            raise ValueError("federated envelope not found")
        record = state["envelopes"][envelope_id]
        reproduction_id = receipt.get("reproduction_id")
        if reproduction_id and any(
            item.get("envelope_id") == envelope_id and item.get("reproduction_id") == reproduction_id
            for item in state["reproductions"]
        ):
            return {
                "envelope_id": envelope_id,
                "reproduction_id": reproduction_id,
                "duplicate": True,
                "reputation": self.reputation(record["contributor_id"], state=state),
            }
        event = {
            "envelope_id": envelope_id,
            "contributor_id": record["contributor_id"],
            "reproduction_id": reproduction_id,
            "reproduced": bool(receipt.get("reproduced")),
            "trust_score": float(receipt.get("trust_score") or 0.0),
            "created_at": self._now(),
        }
        state["reproductions"].append(event)
        record["state"] = "locally_reproduced" if event["reproduced"] else "reproduction_failed"
        self._save(state)
        return {**event, "reputation": self.reputation(record["contributor_id"], state=state)}

    def revoke(self, envelope_id: str, *, approved: bool, reason: str, approved_by: str) -> Dict[str, Any]:
        if not approved or not reason.strip():
            raise ValueError("revocation requires explicit approval and a reason")
        state = self._load()
        if envelope_id not in state["envelopes"]:
            raise ValueError("federated envelope not found")
        receipt = {"reason": reason, "approved_by": approved_by, "revoked_at": self._now()}
        state["revocations"][envelope_id] = receipt
        state["envelopes"][envelope_id]["state"] = "revoked"
        self._save(state)
        return {"envelope_id": envelope_id, "revoked": True, **receipt}

    def reputation(self, contributor_id: str, *, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or self._load()
        rows = [item for item in state["reproductions"] if item.get("contributor_id") == contributor_id]
        successes = sum(1 for item in rows if item.get("reproduced"))
        score = sum(float(item.get("trust_score") or 0) for item in rows) / len(rows) if rows else 0.0
        return {
            "contributor_id": contributor_id,
            "reproductions": len(rows),
            "successful_reproductions": successes,
            "reproduction_rate": round(successes / len(rows), 6) if rows else None,
            "reputation_score": round(score, 6),
            "claim_boundary": "Reputation reflects local reproductions only, not remote claims.",
        }

    def state(self) -> Dict[str, Any]:
        state = self._load()
        now = datetime.now(timezone.utc)
        expired = []
        for envelope_id, row in state["envelopes"].items():
            if row.get("state") != "revoked" and self._parse_time(row["expires_at"]) <= now:
                row["state"] = "expired"
                expired.append(envelope_id)
        if expired:
            self._save(state)
        contributors = sorted({row.get("contributor_id") for row in state["envelopes"].values() if row.get("contributor_id")})
        return {
            "beast_object_type": "federated_commons_state",
            "version": "1.0",
            "authority": "local",
            "allowlist": state["allowlist"],
            "envelopes": list(state["envelopes"].values()),
            "revocations": state["revocations"],
            "reputations": [self.reputation(item, state=state) for item in contributors],
            "abuse_controls": {
                "max_envelope_bytes": self.MAX_ENVELOPE_BYTES,
                "max_artifacts": self.MAX_ARTIFACTS,
                "max_ingests_per_contributor_day": self.MAX_INGESTS_PER_DAY,
                "max_ttl_days": self.MAX_TTL_DAYS,
            },
        }

    def _load(self) -> Dict[str, Any]:
        default = {"allowlist": {}, "envelopes": {}, "revocations": {}, "reproductions": [], "ingest_events": []}
        if not self.state_path.exists():
            return default
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        for key, value in default.items():
            loaded.setdefault(key, value)
        return loaded

    def _save(self, state: Dict[str, Any]) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.state_path)

    def _sign_ed25519(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        key_path = self.root / "node_ed25519.pem"
        if not key_path.exists():
            completed = subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key_path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if completed.returncode != 0:
                raise ValueError("OpenSSL could not generate the federation signing key")
            os.chmod(key_path, 0o600)
        public = subprocess.run(
            ["openssl", "pkey", "-in", str(key_path), "-pubout"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        with tempfile.NamedTemporaryFile(prefix="beast-fed-sign-", suffix=".bin") as message:
            message.write(canonical_bytes(payload))
            message.flush()
            signed = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key_path), "-in", message.name],
                capture_output=True,
                timeout=15,
                check=False,
            )
        if public.returncode != 0 or signed.returncode != 0:
            raise ValueError("OpenSSL could not sign the federation envelope")
        return {
            "algorithm": "Ed25519",
            "provider": "openssl",
            "public_key_pem_b64": base64.b64encode(public.stdout).decode("ascii"),
            "signature_b64": base64.b64encode(signed.stdout).decode("ascii"),
            "public_key_hash": "sha256:" + hashlib.sha256(public.stdout).hexdigest(),
        }

    @staticmethod
    def _verify_ed25519(payload: Dict[str, Any], signature: Dict[str, Any]) -> Dict[str, Any]:
        if signature.get("algorithm") != "Ed25519" or signature.get("provider") != "openssl":
            return {"verified": False, "algorithm": signature.get("algorithm")}
        try:
            public = base64.b64decode(str(signature.get("public_key_pem_b64") or ""), validate=True)
            signed = base64.b64decode(str(signature.get("signature_b64") or ""), validate=True)
        except Exception:
            return {"verified": False, "algorithm": "Ed25519"}
        try:
            with tempfile.TemporaryDirectory(prefix="beast-fed-verify-") as temp:
                public_path = Path(temp) / "public.pem"
                signature_path = Path(temp) / "signature.bin"
                message_path = Path(temp) / "message.bin"
                public_path.write_bytes(public)
                signature_path.write_bytes(signed)
                message_path.write_bytes(canonical_bytes(payload))
                completed = subprocess.run(
                    [
                        "openssl", "pkeyutl", "-verify", "-rawin", "-pubin",
                        "-inkey", str(public_path), "-sigfile", str(signature_path),
                        "-in", str(message_path),
                    ],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            return {
                "verified": completed.returncode == 0,
                "algorithm": "Ed25519",
                "provider": "openssl",
                "public_key_hash": "sha256:" + hashlib.sha256(public).hexdigest(),
            }
        except (OSError, subprocess.SubprocessError):
            return {"verified": False, "algorithm": "Ed25519", "provider": "openssl"}

    @staticmethod
    def _identifier(value: str, field: str) -> str:
        if not value or len(value) > 96 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
            raise ValueError(f"invalid {field}")
        return value

    @staticmethod
    def _valid_sha256(value: str) -> bool:
        if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
            return False
        return all(char in "0123456789abcdef" for char in value[7:])

    @staticmethod
    def _parse_time(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid federation timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("federation timestamps must include a timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
