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
from typing import Any, Dict, List, Optional

from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload, verify_crystal_seal
from app.kernel.compute.proof_local_compute import (
    ProofRoutePlanner,
    ProofRouteRequest,
    build_capability_advertisement,
    build_receipt_packet,
    staged_transfer_receipt,
    validate_capability_advertisement,
    validate_receipt_packet,
)


class FederatedCommons:
    MAX_ARTIFACTS = 128
    MAX_ENVELOPE_BYTES = 512_000
    MAX_INGESTS_PER_DAY = 100
    MAX_TTL_DAYS = 90
    MAX_RECEIPT_PACKET_BYTES = 512_000
    MAX_ADVERTISEMENT_BYTES = 512_000
    MAX_ADVERTISED_CAPABILITIES = 128

    def __init__(self, registry: Any, root: Optional[Path] = None):
        self.registry = registry
        self.root = (root or registry.root / "federation").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.proof_route_planner = ProofRoutePlanner()

    def prepare_receipt_packet(self, space_id: str, *, contributor_id: str, ttl_minutes: int = 30) -> Dict[str, Any]:
        """Build a small public-safe packet before any artifact transfer."""
        detail = self.registry.get(space_id)
        if not detail["manifest_validation"].get("valid") or not detail["receipt_validation"].get("valid"):
            raise ValueError("only locally valid Spaces can publish receipt packets")
        now = datetime.now(timezone.utc)
        exported = self.registry.export_bundle(space_id)
        bundle_path = Path(str(exported.get("path") or ""))
        packet = build_receipt_packet(
            detail,
            contributor_id=self._identifier(contributor_id, "contributor_id"),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=max(1, min(int(ttl_minutes), 1440)))).isoformat(),
            chain_head=self.registry.crystal_chain.verify().head_hash,
            declared_bundle_bytes=bundle_path.stat().st_size,
            bundle_sha256=str(exported.get("sha256") or ""),
        )
        packet["signature"] = self._sign_ed25519(packet)
        return packet

    def ingest_receipt_packet(self, packet: Dict[str, Any], *, require_allowlisted: bool = True) -> Dict[str, Any]:
        if len(canonical_bytes(packet)) > self.MAX_RECEIPT_PACKET_BYTES:
            raise ValueError("receipt packet exceeds size limit")
        validation = validate_receipt_packet(packet)
        if not validation["valid"]:
            self.record_staged_transfer(
                transfer_id="xfer_rejected_" + hashlib.sha256(canonical_bytes(packet)).hexdigest()[:12],
                stage="receipt_packet", accepted=False,
                reason="; ".join(validation["errors"]), bytes_received=len(canonical_bytes(packet)),
                declared_artifact_bytes=int(packet.get("declared_artifact_bytes") or 0),
                declared_bundle_bytes=int(packet.get("declared_bundle_bytes") or 0),
                packet_id=str(packet.get("packet_id") or ""),
            )
            raise ValueError("receipt packet validation failed: " + "; ".join(validation["errors"]))
        contributor_id = self._identifier(str(packet.get("contributor_id") or ""), "contributor_id")
        verification = self._verify_signed_remote(packet, contributor_id, require_allowlisted=require_allowlisted)
        state = self._load()
        packet_id = self._identifier(str(packet.get("packet_id") or ""), "packet_id")
        if packet_id in state["receipt_packets"]:
            return {"accepted": False, "duplicate": True, **state["receipt_packets"][packet_id]}
        record = {
            "packet_id": packet_id,
            "contributor_id": contributor_id,
            "space_id": packet.get("space_id"),
            "task_class": packet.get("task_class"),
            "manifest_hash": packet.get("manifest_hash"),
            "proof_depth": packet.get("proof_depth"),
            "privacy_class": packet.get("privacy_class"),
            "declared_artifact_bytes": int(packet.get("declared_artifact_bytes") or 0),
            "declared_bundle_bytes": int(packet.get("declared_bundle_bytes") or 0),
            "verifier_descriptions": packet.get("verifier_descriptions") or [],
            "expires_at": packet.get("expires_at"),
            "signature": verification,
            "state": "receipt_only_hypothesis",
            "ingested_at": self._now(),
        }
        state["receipt_packets"][packet_id] = record
        self._save(state)
        self.record_staged_transfer(
            transfer_id="xfer_" + packet_id, stage="receipt_packet", accepted=True,
            reason="signed_public_receipt_accepted", bytes_received=len(canonical_bytes(packet)),
            declared_artifact_bytes=record["declared_artifact_bytes"], packet_id=packet_id,
            declared_bundle_bytes=record["declared_bundle_bytes"],
            manifest_hash=str(packet.get("manifest_hash") or ""),
        )
        return {"accepted": True, "duplicate": False, **record, "next_stage": "request_manifest"}

    def prepare_capability_advertisement(
        self,
        *,
        node_id: str,
        contributor_id: str,
        task_classes: List[str],
        verifier_classes: List[str],
        engine_profiles: Optional[List[str]] = None,
        privacy_classes_accepted: Optional[List[str]] = None,
        load_bucket: str = "low",
        rtt_bucket_ms: int = 10,
        max_transfer_bytes: int = 5_000_000,
        ttl_seconds: int = 60,
    ) -> Dict[str, Any]:
        packets = []
        capability_hashes = []
        for summary in self.registry.list_spaces().get("spaces") or []:
            if not summary.get("valid") or summary.get("task_class") not in task_classes:
                continue
            detail = self.registry.get(str(summary.get("space_id") or ""))
            manifest = detail.get("manifest") or {}
            capability_hashes.append(str(manifest.get("manifest_hash") or ""))
            packets.append({
                "space_id": manifest.get("space_id"),
                "manifest_hash": manifest.get("manifest_hash"),
                "proof_depth": "promoted" if summary.get("adoption_state") == "promoted" else
                    "adopted" if summary.get("adoption_state") == "adopted" else
                    "locally_reproduced" if int(summary.get("reproduction_count") or 0) else "manifest_valid",
            })
        packets = packets[: self.MAX_ADVERTISED_CAPABILITIES]
        capability_hashes = capability_hashes[: self.MAX_ADVERTISED_CAPABILITIES]
        now = datetime.now(timezone.utc)
        advertisement = build_capability_advertisement(
            node_id=self._identifier(node_id, "node_id"),
            contributor_id=self._identifier(contributor_id, "contributor_id"),
            capability_hashes=capability_hashes,
            task_classes=task_classes,
            verifier_classes=verifier_classes,
            engine_profiles=engine_profiles or ["ollama_cpu"],
            privacy_classes_accepted=privacy_classes_accepted or ["public_metadata_only"],
            load_bucket=load_bucket,
            rtt_bucket_ms=rtt_bucket_ms,
            max_transfer_bytes=max_transfer_bytes,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=max(5, min(int(ttl_seconds), 3600)))).isoformat(),
            receipt_packets=packets,
        )
        advertisement["signature"] = self._sign_ed25519(advertisement)
        return advertisement

    def ingest_capability_advertisement(
        self, advertisement: Dict[str, Any], *, require_allowlisted: bool = True,
    ) -> Dict[str, Any]:
        if len(canonical_bytes(advertisement)) > self.MAX_ADVERTISEMENT_BYTES:
            raise ValueError("capability advertisement exceeds size limit")
        validation = validate_capability_advertisement(advertisement)
        if not validation["valid"]:
            raise ValueError("capability advertisement validation failed: " + "; ".join(validation["errors"]))
        contributor_id = self._identifier(str(advertisement.get("contributor_id") or ""), "contributor_id")
        verification = self._verify_signed_remote(advertisement, contributor_id, require_allowlisted=require_allowlisted)
        state = self._load()
        advertisement_id = self._identifier(str(advertisement.get("advertisement_id") or ""), "advertisement_id")
        duplicate = advertisement_id in state["advertisements"]
        if not duplicate:
            state["advertisements"][advertisement_id] = {
                **{key: value for key, value in advertisement.items() if key not in {"signature", "optional_pq_seal"}},
                "signature": verification,
                "state": "fresh_advisory_metadata",
                "ingested_at": self._now(),
            }
            self._save(state)
        return {"accepted": not duplicate, "duplicate": duplicate, **state["advertisements"][advertisement_id]}

    def fresh_advertisements(self) -> List[Dict[str, Any]]:
        state = self._load()
        now = datetime.now(timezone.utc)
        changed = False
        fresh = []
        for item in state["advertisements"].values():
            if self._parse_time(str(item.get("expires_at") or "")) <= now:
                if item.get("state") != "expired":
                    item["state"] = "expired"
                    changed = True
                continue
            fresh.append(item)
        if changed:
            self._save(state)
        return fresh

    def plan_proof_route(self, request: ProofRouteRequest) -> Dict[str, Any]:
        state = self._load()
        contributors = {str(item.get("contributor_id") or "") for item in state["advertisements"].values()}
        reputations = {item: self.reputation(item, state=state) for item in contributors if item}
        return self.proof_route_planner.plan(request, self.fresh_advertisements(), reputations=reputations)

    def record_staged_transfer(self, **values: Any) -> Dict[str, Any]:
        receipt = staged_transfer_receipt(**values)
        state = self._load()
        state["transfer_events"].append(receipt)
        state["transfer_events"] = state["transfer_events"][-2000:]
        self._save(state)
        return receipt

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
            "receipt_packets": list(state["receipt_packets"].values()),
            "fresh_advertisements": self.fresh_advertisements(),
            "transfer_metrics": self._transfer_metrics(state["transfer_events"]),
            "abuse_controls": {
                "max_envelope_bytes": self.MAX_ENVELOPE_BYTES,
                "max_artifacts": self.MAX_ARTIFACTS,
                "max_ingests_per_contributor_day": self.MAX_INGESTS_PER_DAY,
                "max_ttl_days": self.MAX_TTL_DAYS,
                "max_receipt_packet_bytes": self.MAX_RECEIPT_PACKET_BYTES,
                "max_advertisement_bytes": self.MAX_ADVERTISEMENT_BYTES,
                "max_advertised_capabilities": self.MAX_ADVERTISED_CAPABILITIES,
            },
        }

    def _load(self) -> Dict[str, Any]:
        default = {
            "allowlist": {}, "envelopes": {}, "revocations": {}, "reproductions": [], "ingest_events": [],
            "receipt_packets": {}, "advertisements": {}, "transfer_events": [],
        }
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

    def _verify_signed_remote(
        self, payload: Dict[str, Any], contributor_id: str, *, require_allowlisted: bool,
    ) -> Dict[str, Any]:
        state = self._load()
        if require_allowlisted and contributor_id not in state["allowlist"]:
            raise ValueError("contributor is not locally allowlisted")
        signature = payload.get("signature") if isinstance(payload.get("signature"), dict) else {}
        allowed = state["allowlist"].get(contributor_id) or {}
        if require_allowlisted and signature.get("public_key_hash") != allowed.get("public_key_hash"):
            raise ValueError("contributor signing key does not match the local allowlist pin")
        unsigned = {key: value for key, value in payload.items() if key not in {"signature", "optional_pq_seal"}}
        verification = self._verify_ed25519(unsigned, signature)
        if not verification.get("verified"):
            raise ValueError("signed proof-local payload did not verify")
        return verification

    @staticmethod
    def _transfer_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "events": len(events),
            "bytes_received": sum(int(item.get("bytes_received") or 0) for item in events),
            "bytes_avoided": sum(int(item.get("bytes_avoided") or 0) for item in events),
            "full_bundles_avoided": sum(1 for item in events if item.get("full_bundle_avoided")),
            "early_rejections": sum(1 for item in events if not item.get("accepted")),
            "claim_boundary": "measured received bytes versus signed compressed bundle bytes when present; legacy events may use artifact bytes; no compute credit issued",
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
