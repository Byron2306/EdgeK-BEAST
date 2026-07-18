"""Fail-closed ARDA appraisal reference and binding contracts."""
from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArdaAppraisal:
    appraisal_ref: str
    policy_generation: str
    authority: str = "arda"
    state: str = "verified"
    expires_at: float = 0.0
    audience: str = "beast-crystal-executor"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ArdaAppraisal:
        item = cls(
            appraisal_ref=str(value.get("appraisal_ref") or value.get("ref") or ""),
            policy_generation=str(value.get("policy_generation") or ""),
            authority=str(value.get("authority") or "arda"),
            state=str(value.get("state") or ""),
            expires_at=float(value.get("expires_at") or 0),
            audience=str(value.get("audience") or "beast-crystal-executor"),
        )
        if (
            not item.appraisal_ref
            or not item.policy_generation
            or item.authority != "arda"
            or item.state not in {"verified", "appraised"}
        ):
            raise ValueError("ARDA appraisal is incomplete or not verified")
        if item.expires_at and item.expires_at <= time.time():
            raise ValueError("ARDA appraisal has expired")
        return item

    def bind(
        self, *, appraisal_ref: str, policy_generation: str, audience: str
    ) -> None:
        if (
            self.appraisal_ref,
            self.policy_generation,
            self.audience,
        ) != (appraisal_ref, policy_generation, audience):
            raise PermissionError("ARDA appraisal binding mismatch")
