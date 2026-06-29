"""Attach bounded packet-probe evidence to BEAST diagnostics and benchmarks."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class NetworkChronicleConnector:
    """Normalize network probes into stable, non-payload Chronicle evidence."""

    def normalize_probe(self, probe: Dict[str, Any], source: str = "packet_probe") -> Dict[str, Any]:
        raw = dict(probe or {})
        samples = raw.get("samples") if isinstance(raw.get("samples"), list) else []
        summary = {
            "source": source,
            "mode": raw.get("mode") or source,
            "opened": bool(raw.get("opened")),
            "captured": bool(
                raw.get("captured") or raw.get("marker_seen") or raw.get("marker_found") or raw.get("matched_marker")
            ),
            "interface": raw.get("interface") or (raw.get("config") or {}).get("interface"),
            "packets": int(
                raw.get("packets") or raw.get("packets_seen") or raw.get("captured_packets") or len(samples) or 0
            ),
            "drops": int(raw.get("drops") or 0),
            "latency_ms": raw.get("latency_ms") or raw.get("elapsed_ms"),
            "error_type": raw.get("error_type"),
            "error": str(raw.get("error") or "")[:500],
            "sample_count": len(samples),
        }
        digest = hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return {
            "beast_object_type": "network_probe_evidence",
            "version": "1.0",
            "evidence_id": f"net_{digest[:16]}",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "status": "passed" if summary["opened"] and summary["captured"] else "warning",
            "summary": summary,
            "privacy": {
                "payload_bytes_retained": False,
                "packet_samples_retained": False,
                "policy": "metadata_only",
            },
        }

    def attach_provider_diagnostic(
        self,
        diagnostic: Dict[str, Any],
        probe: Dict[str, Any],
        *,
        source: str = "packet_probe",
        chronicle_builder: Optional[Any] = None,
        persist: bool = False,
    ) -> Dict[str, Any]:
        result = deepcopy(diagnostic)
        evidence = self.normalize_probe(probe, source=source)
        result["network_evidence"] = evidence
        result.setdefault("checks", []).append({
            "name": "network_packet_probe",
            "status": evidence["status"],
            "summary": f"{evidence['summary']['mode']} evidence attached as {evidence['evidence_id']}",
            "evidence_id": evidence["evidence_id"],
        })
        result["chronicle"] = None
        if persist:
            if chronicle_builder is None:
                raise ValueError("chronicle_builder is required when persist=true")
            result["chronicle"] = chronicle_builder._write_chronicle(result)
        return result

    def attach_benchmark_report(
        self,
        report: Dict[str, Any],
        probe: Dict[str, Any],
        *,
        source: str = "packet_probe",
    ) -> Dict[str, Any]:
        result = deepcopy(report)
        evidence = self.normalize_probe(probe, source=source)
        result["network_chronicle"] = evidence
        for row in result.get("live_results") or []:
            output_evidence = row.setdefault("output_evidence", {})
            output_evidence["network_probe_evidence_id"] = evidence["evidence_id"]
            output_evidence["network_probe_status"] = evidence["status"]
        return result
