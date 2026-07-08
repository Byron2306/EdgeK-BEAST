"""Opt-in, privacy-preserving tool and skill capability evidence exchange."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx


class CapabilityExchange:
    """Prepare, rank, persist, and optionally submit anonymous capability evidence."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        endpoint: Optional[str] = None,
        data_dir: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        opt_in = os.environ.get("BEAST_CAPABILITY_EXCHANGE_OPT_IN", "0").lower() in {"1", "true", "yes", "on"}
        self.enabled = opt_in if enabled is None else bool(enabled)
        self.endpoint = str(endpoint or os.environ.get("BEAST_CAPABILITY_EXCHANGE_ENDPOINT") or "").rstrip("/")
        root = Path(__file__).resolve().parents[3]
        self.data_dir = Path(data_dir) if data_dir else root / ".beast" / "capability_exchange"
        self.client = client or httpx.Client(timeout=10.0)
        self.signing_key = os.environ.get("BEAST_CAPABILITY_EXCHANGE_SIGNING_KEY", "")
        node = os.environ.get("BEAST_CAPABILITY_EXCHANGE_NODE_ID", "")
        self.contributor = "node_" + hashlib.sha256(node.encode()).hexdigest()[:12] if node else "anonymous"

    def prepare(self, capability: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
        capability_id = str(capability.get("capability_id") or capability.get("tool_name") or capability.get("skill_name") or "").strip()
        if not capability_id:
            raise ValueError("capability_id, tool_name, or skill_name is required")
        kind = str(capability.get("kind") or ("skill" if capability.get("skill_name") else "tool"))
        schema_hash = str(capability.get("schema_hash") or capability.get("tool_schema_hash") or "")
        if not schema_hash:
            identity_seed = json.dumps({
                "capability_id": capability_id,
                "kind": kind,
                "version": capability.get("version") or "unknown",
            }, sort_keys=True, separators=(",", ":"))
            schema_hash = "sha256:" + hashlib.sha256(identity_seed.encode()).hexdigest()
        envelope = {
            "beast_object_type": "capability_exchange_evidence",
            "version": "1.0",
            "capability": {
                "capability_id": capability_id,
                "kind": kind,
                "version": str(capability.get("version") or "unknown")[:80],
                "schema_hash": schema_hash,
                "risk_class": str(capability.get("risk_class") or "unknown")[:20],
            },
            "context": {
                "task_class": str(outcome.get("task_class") or "general")[:120],
                "role": str(outcome.get("role") or "general")[:120],
                "runtime": "BEAST",
            },
            "outcome": {
                "verified": bool(outcome.get("verified")),
                "useful": bool(outcome.get("useful")),
                "hidden_clean": bool(outcome.get("hidden_clean")),
                "rescued": bool(outcome.get("rescued")),
                "safe": bool(outcome.get("safe", True)),
                "status": str(outcome.get("status") or "unknown")[:40],
            },
            "economics": {
                "tokens": max(0, int(outcome.get("tokens") or 0)),
                "cost_usd": max(0.0, float(outcome.get("cost_usd") or 0.0)),
                "latency_ms": max(0.0, float(outcome.get("latency_ms") or 0.0)),
            },
            "contributor": self.contributor,
            "evidence_scope": "global" if outcome.get("evidence_scope") == "global" else "local",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "privacy": {
                "contains_prompt": False,
                "contains_source_code": False,
                "contains_paths": False,
                "contains_secrets": False,
                "allowlisted_fields_only": True,
            },
        }
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        envelope["evidence_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        envelope["signature"] = (
            "hmac-sha256:" + hmac.new(self.signing_key.encode(), canonical.encode(), hashlib.sha256).hexdigest()
            if self.signing_key else "unsigned"
        )
        return envelope

    def contribute(
        self,
        envelope: Dict[str, Any],
        *,
        approved: bool = False,
        dry_run: bool = True,
        persist_local: bool = True,
    ) -> Dict[str, Any]:
        self._validate_envelope(envelope)
        result = {
            "beast_object_type": "capability_exchange_submission",
            "version": "1.0",
            "enabled": self.enabled,
            "approved": bool(approved),
            "dry_run": bool(dry_run),
            "evidence_hash": envelope.get("evidence_hash"),
            "endpoint": self.endpoint,
            "local_path": None,
        }
        if dry_run:
            return {**result, "submitted": False, "reason": "dry_run"}
        if not self.enabled:
            return {**result, "submitted": False, "reason": "capability exchange opt-in is disabled"}
        if not approved:
            return {**result, "submitted": False, "reason": "explicit approval required"}
        if persist_local:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            path = self.data_dir / "outbox.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(envelope, sort_keys=True) + "\n")
            result["local_path"] = str(path)
        target = self._submission_endpoint()
        if not target:
            return {**result, "submitted": False, "reason": "exchange endpoint is not configured"}
        response = self.client.post(target, json=envelope, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return {**result, "submitted": True, "reason": "evidence accepted", "status_code": response.status_code}

    def rank(
        self,
        evidence: Iterable[Dict[str, Any]],
        *,
        task_class: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        buckets: Dict[tuple[str, str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for item in evidence:
            try:
                self._validate_envelope(item)
            except ValueError:
                continue
            context = item.get("context") or {}
            if task_class and context.get("task_class") != task_class:
                continue
            if role and context.get("role") != role:
                continue
            cap = item.get("capability") or {}
            key = (
                str(cap.get("capability_id")), str(cap.get("version")), str(cap.get("schema_hash")),
                str(context.get("task_class")), str(context.get("role")),
            )
            buckets[key].append(item)
        rankings = []
        for key, rows in buckets.items():
            sample_size = len(rows)
            local_rows = [row for row in rows if row.get("evidence_scope") != "global"]
            global_rows = [row for row in rows if row.get("evidence_scope") == "global"]
            verified = self._rate(rows, "verified")
            useful = self._rate(rows, "useful")
            hidden_clean = self._rate(rows, "hidden_clean")
            safe = self._rate(rows, "safe")
            rescued = self._rate(rows, "rescued")
            avg_latency = sum(float((row.get("economics") or {}).get("latency_ms") or 0) for row in rows) / sample_size
            avg_cost = sum(float((row.get("economics") or {}).get("cost_usd") or 0) for row in rows) / sample_size
            efficiency = 1.0 / (1.0 + (avg_latency / 1000.0) + (avg_cost * 100.0))
            prior_quality = self._quality(global_rows or rows)
            local_quality = self._quality(local_rows) if local_rows else prior_quality
            quality = (0.35 * prior_quality) + (0.65 * local_quality) if local_rows and global_rows else local_quality
            confidence = sample_size / (sample_size + 5.0)
            score = quality * (0.5 + (0.5 * confidence))
            rankings.append({
                "capability_id": key[0], "version": key[1], "schema_hash": key[2],
                "task_class": key[3], "role": key[4], "sample_size": sample_size,
                "local_samples": len(local_rows), "global_samples": len(global_rows),
                "score": round(score, 6), "confidence": round(confidence, 6),
                "verified_rate": verified, "usefulness_rate": useful,
                "hidden_clean_rate": hidden_clean, "rescue_rate": rescued, "safety_rate": safe,
                "avg_latency_ms": round(avg_latency, 3), "avg_cost_usd": round(avg_cost, 8),
            })
        rankings.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
        return {
            "beast_object_type": "capability_exchange_ranking",
            "version": "1.0",
            "scope": {"task_class": task_class or "all", "role": role or "all"},
            "ranking_policy": "contextual_global_prior_local_posterior",
            "rankings": rankings,
            "count": len(rankings),
        }

    def state(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "capability_exchange_state",
            "version": "1.0",
            "enabled": self.enabled,
            "endpoint_configured": bool(self.endpoint),
            "contributor": self.contributor,
            "signed": bool(self.signing_key),
            "privacy_mode": "allowlisted_aggregate_evidence_only",
        }

    def validate(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an evidence envelope without submitting or persisting it."""
        try:
            self._validate_envelope(envelope)
        except ValueError as exc:
            return {"valid": False, "reason": str(exc)}
        return {
            "valid": True,
            "reason": "evidence is privacy-safe and hash-valid",
            "evidence_hash": envelope.get("evidence_hash"),
        }

    def _submission_endpoint(self) -> str:
        if not self.endpoint:
            return ""
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("capability exchange endpoint must be an absolute http(s) URL")
        return self.endpoint + "/v1/evidence"

    def _validate_envelope(self, envelope: Dict[str, Any]) -> None:
        if envelope.get("beast_object_type") != "capability_exchange_evidence":
            raise ValueError("invalid capability exchange evidence type")
        if not (envelope.get("capability") or {}).get("capability_id"):
            raise ValueError("capability identity missing")
        privacy = envelope.get("privacy") or {}
        if not privacy.get("allowlisted_fields_only"):
            raise ValueError("evidence did not declare allowlisted privacy mode")
        forbidden_keys = {"prompt", "source_code", "code", "file_path", "path", "secret", "api_key", "token"}
        stack: List[Any] = [envelope]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, value in current.items():
                    if str(key).lower() in forbidden_keys:
                        raise ValueError(f"forbidden evidence field detected: {key}")
                    stack.append(value)
            elif isinstance(current, list):
                stack.extend(current)
        canonical_source = dict(envelope)
        declared_hash = str(canonical_source.pop("evidence_hash", ""))
        canonical_source.pop("signature", None)
        canonical = json.dumps(canonical_source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        expected_hash = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        if not hmac.compare_digest(declared_hash, expected_hash):
            raise ValueError("capability evidence hash mismatch")

    @staticmethod
    def _rate(rows: List[Dict[str, Any]], key: str) -> float:
        return round(sum(1 for row in rows if bool((row.get("outcome") or {}).get(key))) / len(rows), 6)

    @classmethod
    def _quality(cls, rows: List[Dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        verified = cls._rate(rows, "verified")
        useful = cls._rate(rows, "useful")
        hidden_clean = cls._rate(rows, "hidden_clean")
        safe = cls._rate(rows, "safe")
        avg_latency = sum(float((row.get("economics") or {}).get("latency_ms") or 0) for row in rows) / len(rows)
        avg_cost = sum(float((row.get("economics") or {}).get("cost_usd") or 0) for row in rows) / len(rows)
        efficiency = 1.0 / (1.0 + (avg_latency / 1000.0) + (avg_cost * 100.0))
        return (0.35 * verified) + (0.20 * useful) + (0.20 * hidden_clean) + (0.15 * safe) + (0.10 * efficiency)
