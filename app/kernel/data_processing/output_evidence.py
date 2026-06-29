"""Evidence records for BEAST output governance."""

from __future__ import annotations

from typing import Any, Dict


def base_output_evidence(
    profile: Any,
    contract: str,
    raw_text: str,
    usage: Dict[str, Any] | None = None,
    latency_ms: float | None = None,
) -> Dict[str, Any]:
    return {
        "provider": profile.provider,
        "role": profile.role,
        "contract": contract,
        "raw_chars": len(raw_text or ""),
        "json_parse_ok": False,
        "schema_valid": False,
        "path_valid": False,
        "operation_valid": False,
        "anchor_match_rate": 0.0,
        "diff_compiled": False,
        "repair_attempts": 0,
        "latency_ms": latency_ms,
        "usage": usage or {},
        "recommended_future_role": profile.role,
    }
