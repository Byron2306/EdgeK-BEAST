"""Crystal evidence boundary for MCP/tool execution results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.kernel.security.residue_seal import ResidueSeal


@dataclass
class CrystalToolBoundary:
    seal: Optional[ResidueSeal] = None

    def __post_init__(self) -> None:
        self.seal = self.seal or ResidueSeal()

    def receipt(self, request: Dict[str, Any], policy_result: Any, response: Dict[str, Any]) -> Dict[str, Any]:
        safe_request = self._redact(request)
        receipt = {
            "beast_object_type": "crystal_tool_boundary_receipt",
            "version": "1.0",
            "request_id": getattr(policy_result, "request_id", response.get("request_id", "")),
            "server_class": getattr(policy_result, "server_class", response.get("server_class", "")),
            "decision": str(response.get("decision") or getattr(getattr(policy_result, "decision", None), "value", "")),
            "executed": bool(response.get("executed")),
            "tool_name": str(request.get("tool_name") or ""),
            "action": str(request.get("action") or ""),
            "target_hash": self._hash(str(request.get("target") or request.get("command") or "")),
            "request_hash": self._hash(json.dumps(safe_request, sort_keys=True, default=str)),
            "response_hash": self._hash(json.dumps(self._redact(response), sort_keys=True, default=str)),
            "promotion_source": {
                "source": "mcp_provider_tool",
                "verified": bool(response.get("executed")),
                "useful": response.get("decision") != "deny",
                "summary": str(response.get("reason") or "mcp tool boundary recorded")[:240],
            },
            "claim_boundary": "Tool execution boundary receipt; promotion still requires separate verifier evidence.",
        }
        receipt["receipt_hash"] = self._hash(json.dumps(receipt, sort_keys=True, default=str))
        receipt["residue_seal"] = self.seal.sign(receipt, purpose="crystal_tool_boundary_receipt")
        return receipt

    @staticmethod
    def _redact(payload: Dict[str, Any]) -> Dict[str, Any]:
        redacted = {}
        for key, value in payload.items():
            if any(marker in str(key).lower() for marker in ("secret", "token", "password", "api_key", "authorization")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
        return redacted

    @staticmethod
    def _hash(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
