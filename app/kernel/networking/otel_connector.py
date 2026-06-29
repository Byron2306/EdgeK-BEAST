"""OpenTelemetry OTLP/HTTP export for governed BEAST evidence."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class OTLPConfig:
    endpoint: str = ""
    service_name: str = "edgek-beast-gateway"
    timeout_seconds: float = 10.0


class OpenTelemetryConnector:
    """Compile and optionally export BEAST artifacts as OTLP trace spans."""

    def __init__(self, config: Optional[OTLPConfig] = None, client: Optional[httpx.Client] = None):
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
        service_name = os.environ.get("OTEL_SERVICE_NAME") or OTLPConfig.service_name
        self.config = config or OTLPConfig(endpoint=endpoint, service_name=service_name)
        self.client = client or httpx.Client(timeout=self.config.timeout_seconds)

    def compile(
        self,
        *,
        chronicles: Iterable[Dict[str, Any]] = (),
        route_cards: Iterable[Dict[str, Any]] = (),
        packet_evidence: Iterable[Dict[str, Any]] = (),
        provider_fitness: Iterable[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        now_ns = time.time_ns()
        spans = []
        for index, item in enumerate(chronicles):
            spans.append(self._span("beast.chronicle", item, now_ns + index, "chronicle"))
        offset = len(spans)
        for index, item in enumerate(route_cards):
            spans.append(self._span("beast.route_card", item, now_ns + offset + index, "route_card"))
        offset = len(spans)
        for index, item in enumerate(packet_evidence):
            spans.append(self._span("beast.packet_probe", item, now_ns + offset + index, "packet_probe"))
        offset = len(spans)
        for index, item in enumerate(provider_fitness):
            spans.append(self._span("beast.provider_fitness", item, now_ns + offset + index, "provider_fitness"))
        return {
            "resourceSpans": [{
                "resource": {"attributes": [
                    self._attribute("service.name", self.config.service_name),
                    self._attribute("service.namespace", "edgek.beast"),
                    self._attribute("telemetry.sdk.language", "python"),
                    self._attribute("beast.governed", True),
                ]},
                "scopeSpans": [{
                    "scope": {"name": "edgek.beast.connectors.otel", "version": "1.0"},
                    "spans": spans,
                }],
            }],
        }

    def export(
        self,
        payload: Dict[str, Any],
        *,
        endpoint: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        approved: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        target = self._traces_endpoint(endpoint or self.config.endpoint)
        span_count = sum(
            len(scope.get("spans") or [])
            for resource in payload.get("resourceSpans") or []
            for scope in resource.get("scopeSpans") or []
        )
        result = {
            "beast_object_type": "otel_export_result",
            "version": "1.0",
            "destination": target,
            "backend_hint": self._backend_hint(target),
            "span_count": span_count,
            "approved": bool(approved),
            "dry_run": bool(dry_run),
            "payload": payload if dry_run else None,
        }
        if not target:
            return {**result, "exported": False, "reason": "OTLP endpoint is not configured"}
        if dry_run or not approved:
            return {
                **result,
                "exported": False,
                "reason": "Dry-run projection; live telemetry export requires approved=true and dry_run=false.",
            }
        response = self.client.post(
            target,
            headers={"Content-Type": "application/json", **self._env_headers(), **(headers or {})},
            json=payload,
        )
        response.raise_for_status()
        return {
            **result,
            "exported": True,
            "status_code": response.status_code,
            "payload": None,
            "reason": "OTLP trace export accepted",
        }

    def state(self) -> Dict[str, Any]:
        endpoint = self._traces_endpoint(self.config.endpoint)
        return {
            "beast_object_type": "otel_connector_state",
            "version": "1.0",
            "configured": bool(endpoint),
            "endpoint": endpoint,
            "backend_hint": self._backend_hint(endpoint),
            "service_name": self.config.service_name,
            "protocol": "otlp_http_json",
            "approval_required_for_export": True,
        }

    def _span(self, name: str, item: Dict[str, Any], start_ns: int, artifact_type: str) -> Dict[str, Any]:
        if isinstance(item.get("record"), dict):
            item = item["record"]
        safe = self._safe_attributes(item, artifact_type)
        seed = json.dumps(safe, sort_keys=True, separators=(",", ":"), default=str)
        trace_id = hashlib.sha256((artifact_type + seed).encode("utf-8")).hexdigest()[:32]
        span_id = hashlib.sha256((name + seed).encode("utf-8")).hexdigest()[:16]
        duration_ms = self._duration_ms(item, artifact_type)
        status = str(item.get("status") or item.get("category") or "").lower()
        failed = any(term in status for term in ("fail", "error", "denied", "invalid"))
        return {
            "traceId": trace_id,
            "spanId": span_id,
            "name": name,
            "kind": 1,
            "startTimeUnixNano": str(max(0, start_ns)),
            "endTimeUnixNano": str(max(0, start_ns + int(duration_ms * 1_000_000))),
            "attributes": [self._attribute(key, value) for key, value in safe.items()],
            "status": {"code": 2 if failed else 1, "message": status[:200]},
        }

    def _safe_attributes(self, item: Dict[str, Any], artifact_type: str) -> Dict[str, Any]:
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        return {
            "beast.artifact_type": artifact_type,
            "beast.task_id": item.get("task_id") or item.get("route_id") or item.get("evidence_id") or "",
            "beast.provider": item.get("provider") or item.get("provider_id") or "",
            "beast.category": item.get("category") or item.get("task_class") or "",
            "beast.status": item.get("status") or "",
            "beast.role": item.get("recommended_role") or item.get("role") or "",
            "beast.score": item.get("provider_fitness_score") or item.get("score") or 0.0,
            "beast.rescue_rate": item.get("rescue_rate") or item.get("beast_rescue_score") or 0.0,
            "beast.hidden_clean_rate": item.get("hidden_clean_rate") or 0.0,
            "beast.auth_confidence": item.get("auth_confidence") or item.get("route_confidence") or "",
            "network.mode": summary.get("mode") or item.get("mode") or "",
            "network.interface.name": summary.get("interface") or item.get("interface") or "",
            "network.packets": summary.get("packets") or item.get("captured_packets") or 0,
            "network.drops": summary.get("drops") or 0,
        }

    @staticmethod
    def _duration_ms(item: Dict[str, Any], artifact_type: str) -> float:
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        value = summary.get("latency_ms") or item.get("latency_ms") or item.get("avg_latency_ms")
        try:
            return max(0.001, float(value))
        except (TypeError, ValueError):
            return 0.001 if artifact_type != "packet_probe" else 1.0

    @staticmethod
    def _attribute(key: str, value: Any) -> Dict[str, Any]:
        if isinstance(value, bool):
            wrapped = {"boolValue": value}
        elif isinstance(value, int):
            wrapped = {"intValue": str(value)}
        elif isinstance(value, float):
            wrapped = {"doubleValue": value}
        else:
            wrapped = {"stringValue": str(value or "")[:1000]}
        return {"key": key, "value": wrapped}

    @staticmethod
    def _traces_endpoint(endpoint: str) -> str:
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OTLP endpoint must be an absolute http(s) URL")
        if value.endswith("/v1/traces"):
            return value
        return value + "/v1/traces"

    @staticmethod
    def _backend_hint(endpoint: str) -> str:
        host = (urlparse(endpoint).hostname or "").lower()
        text = endpoint.lower()
        if "grafana" in host or "tempo" in text:
            return "grafana_tempo"
        if "jaeger" in host or "jaeger" in text:
            return "jaeger"
        return "otlp_compatible" if endpoint else "unconfigured"

    @staticmethod
    def _env_headers() -> Dict[str, str]:
        raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers = {}
        for part in raw.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                headers[key.strip()] = value.strip()
        return headers
