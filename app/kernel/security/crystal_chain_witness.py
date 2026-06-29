"""Cross-signed Crystal Chain head witnessing.

This is Phase 4's federation hardening layer.  It does not create consensus or
financial finality; it lets peers remember signed heads so rollback, fork, or
silent history replacement causes quarantine instead of promotion.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.security.crystal_chain import CrystalChainLedger


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrystalChainWitnessStore:
    def __init__(self, root: Optional[Path] = None, *, node_id: str = "local-beast"):
        self.root = Path(root or Path("benchmarks/results/crystal_chain_witness"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.attestations_path = self.root / "attestations.jsonl"
        self.key_path = self.root / f"{node_id}_ed25519.pem"
        self.node_id = node_id

    def attest_chain_head(
        self,
        chain: CrystalChainLedger,
        *,
        lattice_head_hash: str = "",
        previous_attested_head: str = "",
    ) -> Dict[str, Any]:
        verification = chain.verify()
        previous_attested_head = previous_attested_head or self.latest_head_for_node(chain.node_id)
        payload = {
            "beast_object_type": "crystal_chain_head_attestation",
            "version": "1.0",
            "node_id": chain.node_id,
            "witnessed_by": self.node_id,
            "height": verification.block_count,
            "head_hash": verification.head_hash,
            "previous_attested_head": previous_attested_head,
            "source_chain_valid": verification.valid,
            "lattice_head_hash": lattice_head_hash,
            "signed_at": _utc_now(),
            "private_payload_exported": False,
            "authority": "peer_witness_not_consensus",
        }
        payload["attestation_id"] = "cca_" + hashlib.sha256(_canonical(payload)).hexdigest()[:24]
        payload["signature"] = self._sign_ed25519({key: value for key, value in payload.items() if key != "signature"})
        return payload

    def witness(self, attestation: Dict[str, Any], *, peer_id: str = "") -> Dict[str, Any]:
        verification = self.verify_attestation(attestation)
        if not verification.get("verified"):
            raise ValueError("crystal chain attestation signature did not verify")
        row = {
            "beast_object_type": "crystal_chain_witness_record",
            "version": "1.0",
            "witness_recorded_at": _utc_now(),
            "peer_id": peer_id or str(attestation.get("node_id") or "unknown"),
            "attestation": attestation,
            "verification": verification,
        }
        with self.attestations_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def audit_chain(self, chain: CrystalChainLedger) -> Dict[str, Any]:
        verification = chain.verify()
        records = [
            record for record in self.records()
            if (record.get("attestation") or {}).get("node_id") == chain.node_id
        ]
        verdict = "ok"
        reasons: List[str] = []
        promotion_allowed = True
        if not verification.valid:
            verdict = "quarantine"
            promotion_allowed = False
            reasons.append("local_chain_invalid")
        if records:
            max_height = max(int((record.get("attestation") or {}).get("height") or 0) for record in records)
            same_height_heads = {
                str((record.get("attestation") or {}).get("head_hash") or "")
                for record in records
                if int((record.get("attestation") or {}).get("height") or 0) == verification.block_count
            }
            if verification.block_count < max_height:
                verdict = "quarantine"
                promotion_allowed = False
                reasons.append("rollback_detected")
            if same_height_heads and verification.head_hash not in same_height_heads:
                verdict = "quarantine"
                promotion_allowed = False
                reasons.append("fork_or_history_replacement_detected")
        latest = records[-1]["attestation"] if records else {}
        return {
            "beast_object_type": "crystal_chain_witness_audit",
            "version": "1.0",
            "node_id": chain.node_id,
            "verdict": verdict,
            "promotion_allowed": promotion_allowed,
            "reasons": sorted(set(reasons)),
            "current": verification.to_dict(),
            "witness_records": len(records),
            "latest_witnessed_head": latest.get("head_hash"),
            "latest_witnessed_height": latest.get("height"),
            "claim_boundary": "peer_witnessing_detects_disagreement_no_global_consensus",
        }

    def verify_attestation(self, attestation: Dict[str, Any]) -> Dict[str, Any]:
        signature = attestation.get("signature") if isinstance(attestation.get("signature"), dict) else {}
        unsigned = {key: value for key, value in attestation.items() if key != "signature"}
        return self._verify_ed25519(unsigned, signature)

    def records(self) -> List[Dict[str, Any]]:
        if not self.attestations_path.is_file():
            return []
        rows = []
        for line in self.attestations_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def latest_head_for_node(self, node_id: str) -> str:
        for record in reversed(self.records()):
            attestation = record.get("attestation") if isinstance(record.get("attestation"), dict) else {}
            if attestation.get("node_id") == node_id:
                return str(attestation.get("head_hash") or "")
        return ""

    def state(self) -> Dict[str, Any]:
        records = self.records()
        return {
            "beast_object_type": "crystal_chain_witness_state",
            "version": "1.0",
            "root": str(self.root),
            "node_id": self.node_id,
            "record_count": len(records),
            "attested_nodes": sorted({str((record.get("attestation") or {}).get("node_id") or "unknown") for record in records}),
            "financial_asset": False,
            "consensus": "cross_signed_witnessing_no_byzantine_consensus",
        }

    def _sign_ed25519(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_key()
        public = subprocess.run(
            ["openssl", "pkey", "-in", str(self.key_path), "-pubout"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        with tempfile.NamedTemporaryFile(prefix="beast-chain-sign-", suffix=".bin") as message:
            message.write(_canonical(payload))
            message.flush()
            signed = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.key_path), "-in", message.name],
                capture_output=True,
                timeout=15,
                check=False,
            )
        if public.returncode != 0 or signed.returncode != 0:
            raise ValueError("OpenSSL could not sign Crystal Chain head")
        return {
            "algorithm": "Ed25519",
            "provider": "openssl",
            "public_key_pem_b64": base64.b64encode(public.stdout).decode("ascii"),
            "signature_b64": base64.b64encode(signed.stdout).decode("ascii"),
            "public_key_hash": "sha256:" + hashlib.sha256(public.stdout).hexdigest(),
        }

    def _ensure_key(self) -> None:
        if self.key_path.is_file():
            return
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(self.key_path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError("OpenSSL could not generate Crystal Chain witness key")
        os.chmod(self.key_path, 0o600)

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
            with tempfile.TemporaryDirectory(prefix="beast-chain-verify-") as temp:
                public_path = Path(temp) / "public.pem"
                signature_path = Path(temp) / "signature.bin"
                message_path = Path(temp) / "message.bin"
                public_path.write_bytes(public)
                signature_path.write_bytes(signed)
                message_path.write_bytes(_canonical(payload))
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


def hash_attestation_payload(attestation: Dict[str, Any]) -> str:
    return _sha256_payload({key: value for key, value in attestation.items() if key != "signature"})
