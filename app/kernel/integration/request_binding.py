"""Canonical request binding shared by crystal authorization boundaries."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def crystal_request(plan: Any) -> dict[str, Any]:
    """Return the signed body plus its digest; the digest never covers itself."""
    body = {
        "crystal_id": str(plan.crystal_id),
        "action": str(plan.action),
        "plan_evidence_digest": str(plan.evidence_digest),
        "approval_required": bool(plan.approval_required),
    }
    return {**body, "request_digest": canonical_sha256(body)}
