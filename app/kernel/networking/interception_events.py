"""
Broad interception events for gateway, proxy, runtime, and forensic signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.kernel.storage.evidence_envelope import EvidenceEnvelopeFactory


class InterceptionEventFactory:
    """Normalize non-tool interception signals into scored evidence envelopes."""

    LAYERS = {
        "L1": {
            "name": "gateway_proxy_surface",
            "description": "Provider, gateway, proxy, packet, port, cache, and request/response observations.",
        },
        "L2": {
            "name": "tool_workflow_surface",
            "description": "Tool calls, MCP broker decisions, CLI actions, workflow steps, tests, lint, and database probes.",
        },
        "L3": {
            "name": "runtime_governance_surface",
            "description": "Policy, credentials, circuit breaking, routing, throttling, latency, queue, and approval state.",
        },
        "L4": {
            "name": "forensic_memory_surface",
            "description": "Append-only traces, anomalies, mining signals, sandbox/bypass events, and durable failure signatures.",
        },
    }

    EVENT_LAYERS = {
        "provider_call": "L1",
        "proxy_request": "L1",
        "gateway_request": "L1",
        "status_code": "L1",
        "payload": "L1",
        "packet": "L1",
        "cache": "L1",
        "port": "L1",
        "tool_call": "L2",
        "mcp_evaluate": "L2",
        "mcp_execute": "L2",
        "cli_action": "L2",
        "shell_command": "L2",
        "database_query": "L2",
        "test_run": "L2",
        "lint_run": "L2",
        "workflow_step": "L2",
        "broker": "L2",
        "circuit": "L3",
        "latency": "L3",
        "throttle": "L3",
        "routing": "L3",
        "policy": "L3",
        "credentials": "L3",
        "queue": "L3",
        "rate_limit": "L3",
        "warning": "L3",
        "notification": "L3",
        "error": "L4",
        "trace": "L4",
        "mining": "L4",
        "sandbox": "L4",
        "bypass": "L4",
        "anomaly": "L4",
        "error_signature": "L4",
        "packet_observation": "L4",
        "port_observation": "L4",
        "cache_decision": "L4",
        "forensic_note": "L4",
    }

    EVENT_CAPABILITIES = {
        "provider_call": ("workflow:provider_diagnostic", "diagnostics"),
        "proxy_request": ("tool:semantic_interceptor", "tool_bus"),
        "gateway_request": ("tool:semantic_interceptor", "tool_bus"),
        "status_code": ("workflow:provider_diagnostic", "diagnostics"),
        "payload": ("tool:compression_prune", "compression"),
        "circuit": ("workflow:provider_diagnostic", "diagnostics"),
        "latency": ("workflow:provider_diagnostic", "diagnostics"),
        "packet": ("tool:semantic_interceptor", "tool_bus"),
        "cache": ("tool:semantic_interceptor", "tool_bus"),
        "port": ("workflow:provider_diagnostic", "diagnostics"),
        "tool_call": ("tool:mcp_evaluate", "tool_bus"),
        "mcp_evaluate": ("tool:mcp_evaluate", "tool_bus"),
        "mcp_execute": ("tool:mcp_execute", "tool_bus"),
        "cli_action": ("workflow:beast_cli_harness", "workflow"),
        "shell_command": ("workflow:quality_cascade", "quality"),
        "database_query": ("workflow:quality_cascade", "quality"),
        "test_run": ("workflow:quality_cascade", "quality"),
        "lint_run": ("linter:py_compile", "quality"),
        "workflow_step": ("workflow:quality_cascade", "quality"),
        "error": ("workflow:quality_cascade", "quality"),
        "warning": ("workflow:quality_cascade", "quality"),
        "notification": ("workflow:quality_cascade", "quality"),
        "throttle": ("workflow:provider_diagnostic", "diagnostics"),
        "routing": ("route:route_cards", "routing"),
        "broker": ("tool:mcp_evaluate", "tool_bus"),
        "policy": ("workflow:provider_diagnostic", "diagnostics"),
        "credentials": ("workflow:provider_diagnostic", "diagnostics"),
        "queue": ("workflow:provider_diagnostic", "diagnostics"),
        "rate_limit": ("workflow:provider_diagnostic", "diagnostics"),
        "trace": ("tool:log_signature_matcher", "debugging"),
        "mining": ("skill:learned_registry", "skill"),
        "sandbox": ("workflow:quality_cascade", "quality"),
        "bypass": ("workflow:quality_cascade", "quality"),
        "anomaly": ("tool:log_signature_matcher", "debugging"),
        "error_signature": ("tool:log_signature_matcher", "debugging"),
        "packet_observation": ("tool:semantic_interceptor", "tool_bus"),
        "port_observation": ("workflow:provider_diagnostic", "diagnostics"),
        "cache_decision": ("tool:semantic_interceptor", "tool_bus"),
        "forensic_note": ("tool:log_signature_matcher", "debugging"),
    }

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.evidence_factory = EvidenceEnvelopeFactory(policies or {})

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        kind = str(payload.get("event_kind") or payload.get("kind") or "trace").lower()
        layer = self._layer(kind, payload)
        provider = payload.get("provider")
        status = str(payload.get("status") or "").lower()
        severity = self._severity(kind, status, payload)
        capability_id, family = self.EVENT_CAPABILITIES.get(kind, ("tool:semantic_interceptor", "tool_bus"))
        latency_ms = float(payload.get("latency_ms") or payload.get("duration_ms") or 0.0)
        signals = self._signals(kind, layer, status, payload, latency_ms)
        summary = str(payload.get("summary") or payload.get("message") or f"{kind} interception event")
        evidence = self.evidence_factory.build(
            source_type="interception_event",
            source_uri=str(payload.get("source_uri") or f"intercept://{kind}/{payload.get('event_id') or 'event'}"),
            scope=str(payload.get("scope") or self._default_scope(layer)),
            artifact_type=f"interception_event:{kind}",
            task_id=payload.get("task_id"),
            provider=provider,
            severity=severity,
            confidence=float(payload.get("confidence") or self._confidence(kind, status)),
            relevance=float(payload.get("relevance") or 0.68),
            risk=float(payload.get("risk") or self._risk(kind, status)),
            blast_radius=float(payload.get("blast_radius") or self._blast_radius(kind)),
            repeat_count=int(payload.get("repeat_count") or 1),
            verification_strength=float(payload.get("verification_strength") or 0.55),
            signals=signals,
            relationships=self._relationships(kind, layer, payload),
            recommended_actions=payload.get("recommended_actions") or self._recommendations(kind, status),
            recommended_capability_id=str(payload.get("recommended_capability_id") or capability_id),
            capability_family=str(payload.get("capability_family") or family),
            summary=summary,
            created_at=payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
        evidence["interception_layer"] = layer
        return evidence

    def mesh(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "interception_layer_mesh",
            "version": "1.0",
            "layers": self.LAYERS,
            "event_layers": dict(sorted(self.EVENT_LAYERS.items())),
            "event_capabilities": {
                kind: {"recommended_capability_id": capability, "capability_family": family}
                for kind, (capability, family) in sorted(self.EVENT_CAPABILITIES.items())
            },
        }

    def from_runtime_attempt(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        status = str(attempt.get("status") or "")
        kind = "latency" if status == "succeeded" else "error"
        if status in {"rejected", "abandoned"}:
            kind = "throttle"
        return self.build({
            "event_kind": kind,
            "event_id": attempt.get("attempt_id"),
            "source_uri": f"runtime://attempt/{attempt.get('attempt_id')}",
            "scope": "provider",
            "provider": attempt.get("provider"),
            "status": status,
            "duration_ms": attempt.get("duration_ms") or 0,
            "summary": attempt.get("error_message") or f"Runtime attempt {status}",
            "signals": [f"runtime_{status}"],
            "relationships": [
                {"type": "attempt", "id": attempt.get("attempt_id")},
                {"type": "model", "id": attempt.get("model")},
                {"type": "session", "id": attempt.get("session_id")},
            ],
        })

    def _severity(self, kind: str, status: str, payload: Dict[str, Any]) -> str:
        if payload.get("severity"):
            return str(payload["severity"])
        if kind in {"circuit", "throttle", "bypass", "sandbox"} or status in {"failed", "rejected", "abandoned"}:
            return "high"
        if kind in {"error", "port", "broker"}:
            return "medium"
        if kind in {"warning", "latency"}:
            return "medium"
        return "info"

    def _confidence(self, kind: str, status: str) -> float:
        if status in {"failed", "rejected", "abandoned"}:
            return 0.85
        if kind in {"circuit", "latency", "trace"}:
            return 0.78
        return 0.62

    def _risk(self, kind: str, status: str) -> float:
        if kind in {"bypass", "sandbox"}:
            return 0.75
        if kind in {"circuit", "throttle"} or status in {"failed", "rejected", "abandoned"}:
            return 0.65
        if kind in {"error", "port", "broker"}:
            return 0.5
        return 0.25

    def _blast_radius(self, kind: str) -> float:
        if kind in {"routing", "broker", "circuit", "throttle"}:
            return 0.65
        if kind in {"bypass", "sandbox", "port"}:
            return 0.75
        return 0.35

    def _layer(self, kind: str, payload: Dict[str, Any]) -> str:
        layer = str(payload.get("layer") or self.EVENT_LAYERS.get(kind) or "L4").upper()
        return layer if layer in self.LAYERS else "L4"

    def _default_scope(self, layer: str) -> str:
        return {
            "L1": "gateway",
            "L2": "workflow",
            "L3": "runtime",
            "L4": "forensic",
        }.get(layer, "forensic")

    def _signals(self, kind: str, layer: str, status: str, payload: Dict[str, Any], latency_ms: float) -> List[str]:
        signals = [f"intercept_{kind}", f"intercept_layer_{layer.lower()}"]
        if status:
            signals.append(f"status_{status}")
        if latency_ms >= 1000:
            signals.append("high_latency")
        signals.extend(str(item) for item in payload.get("signals", []))
        return list(dict.fromkeys(signals))

    def _relationships(self, kind: str, layer: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        relationships = [
            {"type": "interception_kind", "id": kind},
            {"type": "interception_layer", "id": layer},
        ]
        for key in ("provider", "route_id", "attempt_id", "trace_id", "port", "broker", "cache_key"):
            if payload.get(key):
                relationships.append({"type": key, "id": payload[key]})
        relationships.extend(payload.get("relationships") or [])
        return relationships

    def _recommendations(self, kind: str, status: str) -> List[str]:
        if kind == "circuit":
            return ["Check circuit state before retrying or routing to fallback."]
        if kind == "latency":
            return ["Compare latency against route/provider baseline before escalation."]
        if kind == "throttle":
            return ["Throttle or queue the request and inspect retry-after policy."]
        if kind == "routing":
            return ["Prefer route cards with lower failure and approval friction."]
        if kind == "broker":
            return ["Evaluate MCP broker policy before execution."]
        if kind in {"sandbox", "bypass"}:
            return ["Keep execution gated and preserve forensic trace before promotion."]
        if status in {"failed", "rejected", "abandoned"}:
            return ["Categorize failure and write Chronicle before retry."]
        return ["Record event as forensic context for future ranking."]
