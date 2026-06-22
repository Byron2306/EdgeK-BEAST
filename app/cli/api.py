"""Async HTTP client for the BEAST Power Console.

This client intentionally treats the BEAST backend as the source of truth and
normalizes live endpoint responses into a single snapshot for the Textual TUI.
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

from app.kernel.output_governor import (
    output_gate,
    provider_output_profile,
)
from app.kernel.provider_adapters import ProviderAdapterRegistry
from app.kernel.provider_handoff import build_provider_handoff, render_provider_handoff_prompt

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

ROOT = Path(__file__).resolve().parents[2]


def provider_stream_read_timeout(provider: str) -> float:
    """Return a bounded idle-read timeout for provider SSE streams."""
    configured = os.environ.get("BEAST_STREAM_READ_TIMEOUT_SECONDS")
    if configured:
        try:
            return max(15.0, min(float(configured), 600.0))
        except ValueError:
            pass
    normalized = str(provider or "").strip().lower().replace("-", "_")
    return 210.0 if normalized in {"nvidia", "nvidia_nim", "nim"} else 90.0


def classify_stream_failure(exc: Exception | str) -> Dict[str, Any]:
    """Classify a stream failure without mistaking provider errors for stack death."""
    message = str(exc or "stream failed")
    lowered = message.lower()
    status = 0
    match = re.search(r"(?:status(?:_code)?[=: ]+|http[/ ]?)(\d{3})", lowered)
    if match:
        status = int(match.group(1))
    timeout = "timeout" in lowered or "timed out" in lowered
    transport = any(token in lowered for token in (
        "connection refused", "connection reset", "connecterror", "remoteprotocolerror",
        "server disconnected", "all connection attempts failed", "broken pipe",
    ))
    local_service_failure = transport or status in {502, 503, 504}
    return {
        "kind": "timeout" if timeout else "transport" if transport else "http" if status else "provider",
        "status_code": status or None,
        "recoverable": timeout or transport or status in {408, 429, 500, 502, 503, 504},
        "local_service_failure": local_service_failure,
        "error": message[:1200],
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_list(value: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict):
        return []
    for key in keys:
        item = value.get(key)
        if isinstance(item, list):
            return [x for x in item if isinstance(x, dict)]
    for item in value.values():
        if isinstance(item, list) and all(isinstance(x, dict) for x in item):
            return item
    return []


def _list_at_paths(value: Any, paths: Iterable[str]) -> List[Dict[str, Any]]:
    for path in paths:
        current: Any = value
        ok = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and isinstance(current, list):
            return [x for x in current if isinstance(x, dict)]
    return []


def _nested(value: Dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = value
    for part in path.split('.'):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _latest_files(patterns: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    base = ROOT / "benchmarks" / "results"
    for pattern in patterns:
        files.extend([path for path in base.glob(pattern) if path.is_file()])
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)


def _provider_fitness_from_omni(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fitness = payload.get("governed_provider_fitness")
    if not isinstance(fitness, dict) or not fitness:
        fitness = payload.get("live_provider_fitness")
    if not isinstance(fitness, dict) or not fitness:
        return {}
    models = []
    for provider, row in fitness.items():
        if not isinstance(row, dict):
            continue
        models.append({
            "provider": str(provider),
            "model": _nested(payload, f"live_provider_presets.{provider}.model", provider),
            "fitness_score": row.get("score"),
            "samples": row.get("sample_size") or row.get("tasks"),
            "completed": row.get("beast_completed") or row.get("completed"),
            "completion_rate": row.get("beast_completion_rate") or row.get("completion_rate"),
            "clean_completed": row.get("clean_completed"),
            "clean_completion_rate": row.get("hidden_clean_rate") or row.get("visible_clean_rate"),
            "rescued_completed": row.get("rescued_completed"),
            "rescue_rate": row.get("rescue_rate"),
            "avg_latency_ms": row.get("avg_latency_ms"),
            "recommended_role": row.get("recommended_role"),
            "route_confidence": row.get("route_confidence"),
        })
    if not models:
        return {}
    return {
        "beast_object_type": "provider_model_fitness_snapshot",
        "source": "latest_omni_report",
        "generated_at": payload.get("generated_at"),
        "artifact_path": str(path),
        "models": models,
    }


def load_latest_omni_report(path: Optional[Path] = None) -> Dict[str, Any]:
    candidates = [path] if path else _latest_files(["**/omni_report.json"])
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("beast_object_type") == "beast_xai_omni_gauntlet":
            payload.setdefault("artifact_path", str(candidate))
            return payload
    return {}


def load_local_compute_snapshot() -> Dict[str, Any]:
    try:
        from app.kernel.compute_ledger import ComputeLedger
        ledger = ComputeLedger()
        return {
            "state": ledger.state(),
            "metrics": ledger.metrics(500),
            "savings": ledger.savings_summary(2000),
        }
    except Exception:
        return {}


def load_local_kv_cache_state() -> Dict[str, Any]:
    """Summarize persisted KV/cache blocks when the live transport process is empty."""
    storage_dir = ROOT / "data" / "kv_cache"
    blocks: List[Dict[str, Any]] = []
    for path in sorted(storage_dir.glob("*.json")) if storage_dir.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        block = payload.get("block") if isinstance(payload.get("block"), dict) else payload
        if isinstance(block, dict) and block.get("beast_object_type") == "kv_cache_block":
            blocks.append(block)
    if not blocks:
        return {}
    by_location: Dict[str, int] = {}
    by_engine: Dict[str, int] = {}
    total_bytes = 0
    compressed = 0
    compressed_bytes = 0
    pinned = 0
    for block in blocks:
        location = str(block.get("location") or "storage")
        engine = str(block.get("engine") or "unknown")
        size = int(block.get("size_bytes") or 0)
        ratio = float(block.get("compression_ratio") or 1.0)
        by_location[location] = by_location.get(location, 0) + 1
        by_engine[engine] = by_engine.get(engine, 0) + 1
        total_bytes += size
        if block.get("compressed"):
            compressed += 1
            compressed_bytes += int(size * ratio)
        if block.get("pinned"):
            pinned += 1
    return {
        "beast_object_type": "kv_cache_transport_stats",
        "version": "1.0",
        "source": "local_persisted_kv_cache",
        "total_blocks": len(blocks),
        "pinned_blocks": pinned,
        "compressed_blocks": compressed,
        "total_size_bytes": total_bytes,
        "compressed_size_bytes": compressed_bytes,
        "memory_utilization": 0.0,
        "blocks_by_location": by_location,
        "blocks_by_engine": by_engine,
        "operations_logged": sum(int(block.get("access_count") or 0) for block in blocks),
        "max_memory_bytes": 0,
    }


def load_local_commons_snapshot() -> Dict[str, Any]:
    """Load local Commons/Swarm evidence for TUI fallback when the gateway is stale."""
    out: Dict[str, Any] = {}
    try:
        from app.kernel.meta_tool_commons import MetaToolCommons
        commons = MetaToolCommons()
        out["state"] = commons.state()
        out["evidence_plane"] = commons.evidence_plane()
        candidates = commons.candidates(limit=250)
        out["candidates"] = candidates
        candidate_rows = _first_list(candidates, ["candidates", "records", "items"])
        staged_swarm = [row for row in candidate_rows if str(row.get("source") or "") == "local_swarm_commons"]
        out["swarm_candidates"] = {
            "beast_object_type": "meta_tool_commons_swarm_candidates",
            "source": "local_swarm_commons",
            "proposed_count": len(staged_swarm),
            "skipped_count": 0,
            "proposed": staged_swarm[:50],
            "read_only_fallback": True,
        }
    except Exception:
        pass
    try:
        from app.kernel.swarm import SwarmKernel
        swarm = SwarmKernel()
        out["swarm_state"] = swarm.state()
        out["swarm_governance"] = swarm.governed_roles()
        out["swarm_runs"] = {"runs": swarm.recent_runs(limit=20)}
        out["swarm_value"] = {"value_logs": swarm.value_logs(limit=40)}
    except Exception:
        pass
    latest_plane = load_latest_reuse_plane_artifact()
    if latest_plane:
        out["latest_artifact_plane"] = latest_plane
    local_kv = load_local_kv_cache_state()
    if local_kv:
        out["kv_cache_state"] = local_kv
        blocks = int(local_kv.get("total_blocks") or 0)
        operations = int(local_kv.get("operations_logged") or 0)
        out["kv_cache_ingest"] = {
            "beast_object_type": "meta_tool_commons_kv_cache_ingest",
            "source": "local_persisted_kv_cache_fallback",
            "prepared": blocks if blocks else 0,
            "accepted": blocks if blocks else 0,
            "duplicates": 0,
            "skipped": 0 if blocks or operations else 1,
            "read_only_fallback": True,
        }
    return out


def load_local_spaces_snapshot() -> Dict[str, Any]:
    """Load Spaces and shadow policy state without requiring the gateway."""
    try:
        from app.kernel.commons_policy import CommonsPolicyLearner
        from app.kernel.commons_space_registry import CommonsSpaceRegistry

        registry = CommonsSpaceRegistry()
        learner = CommonsPolicyLearner(registry)
        return {
            "registry": registry.list_spaces(),
            "policy": learner.recommend({
                "task_class": "operator_console",
                "risk": "medium",
                "gpu_available": False,
                "approval_required": False,
            }),
            "evaluation": learner.evaluate(),
        }
    except Exception:
        return {}


def load_local_scale_economics_snapshot() -> Dict[str, Any]:
    """Load the latest Commons scale economics ladder receipt."""
    path = ROOT / "benchmarks" / "results" / "commons_scale_economics_ladder_latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict) and payload.get("beast_object_type") == "commons_scale_economics_report":
        payload.setdefault("artifact_path", str(path))
        return payload
    return {}


def load_latest_reuse_plane_artifact() -> Dict[str, Any]:
    candidates = sorted(
        ROOT.glob("benchmarks/results/**/reuse_evidence_plane.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for candidate in candidates[:20]:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        plane = payload.get("plane") if isinstance(payload.get("plane"), dict) else payload
        if isinstance(plane, dict) and plane.get("beast_object_type") == "meta_tool_commons_evidence_plane":
            plane = dict(plane)
            plane.setdefault("artifact_path", str(candidate))
            return plane
    return {}


def load_local_litellm_config() -> Dict[str, Any]:
    """Load generated LiteLLM config when the gateway endpoint is stale/offline."""
    yaml_path = ROOT / "deploy" / "generated" / "litellm.config.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        payload.setdefault("artifact_path", str(yaml_path))
        return payload
    return {}


def normalize_litellm_models(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _list_at_paths(config, [
        "model_list",
        "models",
        "items",
        "config.model_list",
        "config.models",
        "litellm_config.model_list",
    ])
    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        params = row.get("litellm_params") if isinstance(row.get("litellm_params"), dict) else {}
        info = row.get("model_info") if isinstance(row.get("model_info"), dict) else {}
        name = (
            row.get("model_name")
            or row.get("name")
            or row.get("id")
            or info.get("id")
            or info.get("model_name")
            or params.get("model")
            or f"model_{idx}"
        )
        provider_model = params.get("model") or row.get("model") or info.get("base_model") or ""
        normalized_row = dict(row)
        normalized_row["model_name"] = str(name)
        normalized_row.setdefault("litellm_params", params)
        normalized_row["provider_model"] = str(provider_model)
        normalized.append(normalized_row)
    return normalized


def _plane_by_name(plane: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = plane.get("planes") if isinstance(plane.get("planes"), list) else []
    return {str(row.get("plane") or ""): row for row in rows if isinstance(row, dict)}


def merge_evidence_planes(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not primary:
        return dict(fallback or {})
    if not fallback:
        return primary
    merged = dict(primary)
    rows = _plane_by_name(primary)
    changed = False
    for name, row in _plane_by_name(fallback).items():
        if name and int((rows.get(name) or {}).get("evidence_count") or 0) <= 0 and int(row.get("evidence_count") or 0) > 0:
            rows[name] = dict(row)
            rows[name]["source"] = rows[name].get("source") or fallback.get("artifact_path") or "local_fallback"
            changed = True
    if changed:
        ordered = [rows[name] for name in sorted(rows)]
        merged["planes"] = ordered
        merged["plane_count"] = len(ordered)
        merged["evidence_count"] = sum(int(row.get("evidence_count") or 0) for row in ordered)
        merged["fallback_augmented"] = True
    return merged


def load_provider_model_fitness(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the latest local provider/model fitness snapshot for the TUI."""
    candidates = [path] if path else [
        *_latest_files(["**/omni_report.json"]),
        *_latest_files(["**/*_model_fitness.json", "**/provider_fitness.json"]),
        ROOT / "benchmarks" / "results" / "beast_provider_model_fitness_live_free_model_fitness.json",
    ]
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        if candidate.name == "omni_report.json":
            converted = _provider_fitness_from_omni(candidate)
            if converted:
                return converted
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("models"), list):
            payload.setdefault("artifact_path", str(candidate))
            return payload
    return {}


def load_master_mega_evidence(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the frozen definitive mega-test release for local TUI reporting."""
    candidates = [path] if path else [
        ROOT / "benchmarks" / "results" / "beast_definitive_mega_test_master_evidence_v0_1",
        ROOT / "benchmarks" / "results" / "beast_definitive_mega_test_master_evidence",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        bundle = candidate if candidate.is_dir() else candidate.parent
        try:
            release = json.loads((bundle / "release_manifest.json").read_text(encoding="utf-8"))
            metrics = json.loads((bundle / "analysis_metrics.json").read_text(encoding="utf-8"))
            coverage = json.loads((bundle / "coverage_matrix.json").read_text(encoding="utf-8"))
            integrity = json.loads((bundle / "integrity_manifest.json").read_text(encoding="utf-8"))
            secret_scan = json.loads((bundle / "secret_scan.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if release.get("release_status") != "frozen" or not isinstance(metrics, dict):
            continue
        latest_omni = load_latest_omni_report()
        return {
            "release_name": release.get("release_name"),
            "release_version": release.get("release_version"),
            "release_status": release.get("release_status"),
            "controlled_design": release.get("controlled_design") or {},
            "credibility_layers": release.get("credibility_layers") or [],
            "metrics": metrics,
            "coverage": coverage,
            "integrity_hash": integrity.get("manifest_hash"),
            "secret_scan_passed": bool(secret_scan.get("passed")),
            "artifact_path": str(bundle),
            "latest_omni": {
                "generated_at": latest_omni.get("generated_at"),
                "artifact_path": latest_omni.get("artifact_path"),
                "covered_layers": _nested(latest_omni, "coverage.covered_layers", 0),
                "total_layers": _nested(latest_omni, "coverage.total_layers", 0),
                "live_summary": latest_omni.get("live_summary") or {},
                "governed_summary": latest_omni.get("governed_summary") or {},
                "live_efficiency_summary": latest_omni.get("live_efficiency_summary") or {},
            } if latest_omni else {},
        }
    return {}


def load_latest_mega_artifact(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the newest local definitive mega-test artifact for operator reporting."""
    candidates = [path] if path else [
        item.parent
        for item in _latest_files(["beast_definitive_mega_test*/run_manifest.json"])
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        bundle = candidate if candidate.is_dir() else candidate.parent
        try:
            run_manifest = json.loads((bundle / "run_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if run_manifest.get("beast_object_type") != "definitive_mega_test_report":
            continue
        try:
            live_execution = json.loads((bundle / "live_execution.json").read_text(encoding="utf-8"))
        except Exception:
            live_execution = {}
        try:
            mutation = json.loads((bundle / "mutation_recovery.json").read_text(encoding="utf-8"))
        except Exception:
            mutation = {}
        try:
            qpc = json.loads((bundle / "qpc_cloud_call_displacement.json").read_text(encoding="utf-8"))
        except Exception:
            qpc = {}
        try:
            phase_package = json.loads((bundle / "crystal_compute_phase_package.json").read_text(encoding="utf-8"))
        except Exception:
            phase_package = {}
        try:
            integrity = json.loads((bundle / "integrity_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            integrity = {}
        provider_receipts_path = bundle / "provider_call_receipts.jsonl"
        provider_call_receipts = 0
        if provider_receipts_path.is_file():
            try:
                provider_call_receipts = sum(1 for line in provider_receipts_path.read_text(encoding="utf-8").splitlines() if line.strip())
            except Exception:
                provider_call_receipts = 0
        controlled_path = bundle / "controlled_observations.jsonl"
        controlled_rows = 0
        completed_rows = 0
        if controlled_path.is_file():
            try:
                for line in controlled_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    controlled_rows += 1
                    try:
                        completed_rows += 1 if json.loads(line).get("completed") else 0
                    except Exception:
                        pass
            except Exception:
                controlled_rows = completed_rows = 0
        return {
            "artifact_path": str(bundle),
            "archive_path": str(bundle) + ".zip" if (Path(str(bundle) + ".zip")).exists() else "",
            "generated_at": run_manifest.get("generated_at"),
            "mode": run_manifest.get("mode"),
            "live": bool(run_manifest.get("live")),
            "providers": run_manifest.get("providers") or [],
            "families": run_manifest.get("families") or [],
            "occurrences": run_manifest.get("occurrences") or [],
            "lanes": run_manifest.get("lanes") or [],
            "acceptance_status": run_manifest.get("acceptance_status") or {},
            "controlled_rows": controlled_rows,
            "completed_rows": completed_rows,
            "raw_live_result_count": int(live_execution.get("raw_live_result_count") or 0),
            "live_result_count": len(live_execution.get("live_results") or []),
            "provider_call_receipts": provider_call_receipts or len(live_execution.get("provider_call_receipts") or []),
            "provider_call_receipt_files": len(list((bundle / "provider_call_receipts").glob("*.json"))) if (bundle / "provider_call_receipts").is_dir() else 0,
            "impact_fingerprint_files": len(list((bundle / "impact_fingerprints").glob("*.json"))) if (bundle / "impact_fingerprints").is_dir() else 0,
            "compute_governor_receipts": len(live_execution.get("compute_governor_receipts") or []),
            "crystallization_events": len(live_execution.get("crystallization_events") or []),
            "mutation": mutation,
            "qpc": qpc,
            "phase_package": phase_package,
            "integrity_hash": integrity.get("manifest_hash"),
            "resume_source": live_execution.get("resume_source"),
        }
    return {}



@dataclass
class ActionResult:
    """Small normalized result object for TUI actions and live sessions."""

    ok: bool
    title: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def brief(self, max_chars: int = 900) -> str:
        if self.error:
            return f"{self.title}: {self.error}"[:max_chars]
        if self.summary:
            return f"{self.title}: {self.summary}"[:max_chars]
        try:
            return json.dumps(self.data, indent=2, default=str)[:max_chars]
        except Exception:
            return str(self.data)[:max_chars]


@dataclass
class LiveTurnResult(ActionResult):
    assistant_text: str = ""
    tool_events: List[str] = field(default_factory=list)
    lifecycle_id: str = ""


@dataclass
class BackendSnapshot:
    base_url: str
    online: bool = False
    gateway: str = 'OFFLINE'
    proxy: str = 'OFFLINE'
    mcp: str = 'OFFLINE'

    health_raw: Dict[str, Any] = field(default_factory=dict)
    proxy_health_raw: Dict[str, Any] = field(default_factory=dict)
    mcp_health_raw: Dict[str, Any] = field(default_factory=dict)

    capability_inventory: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    capability_families_raw: Dict[str, Any] = field(default_factory=dict)

    provider_registry: Dict[str, Any] = field(default_factory=dict)
    provider_adapters_raw: Dict[str, Any] = field(default_factory=dict)
    provider_adapters: List[Dict[str, Any]] = field(default_factory=list)
    provider_state: Dict[str, Any] = field(default_factory=dict)
    provider_secrets: Dict[str, Any] = field(default_factory=dict)

    prec_state: Dict[str, Any] = field(default_factory=dict)
    prec_lifecycle_raw: Dict[str, Any] = field(default_factory=dict)
    prec_lifecycles: List[Dict[str, Any]] = field(default_factory=list)

    litellm_config: Dict[str, Any] = field(default_factory=dict)
    litellm_models: List[Dict[str, Any]] = field(default_factory=list)
    litellm_sidecar: Dict[str, Any] = field(default_factory=dict)
    nginx_config: str = ''

    chronicles_raw: Dict[str, Any] = field(default_factory=dict)
    chronicles: List[Dict[str, Any]] = field(default_factory=list)
    routes_raw: Dict[str, Any] = field(default_factory=dict)
    routes: List[Dict[str, Any]] = field(default_factory=list)
    insight_packet: Dict[str, Any] = field(default_factory=dict)
    handoff_precheck: Dict[str, Any] = field(default_factory=dict)
    http_telemetry: Dict[str, Any] = field(default_factory=dict)
    runtime_metrics: Dict[str, Any] = field(default_factory=dict)
    session_handshake: Dict[str, Any] = field(default_factory=dict)
    commons_state: Dict[str, Any] = field(default_factory=dict)
    commons_ranking: Dict[str, Any] = field(default_factory=dict)
    commons_evidence_plane: Dict[str, Any] = field(default_factory=dict)
    commons_swarm_ingest: Dict[str, Any] = field(default_factory=dict)
    commons_swarm_candidates: Dict[str, Any] = field(default_factory=dict)
    commons_kv_cache_ingest: Dict[str, Any] = field(default_factory=dict)
    commons_candidates: List[Dict[str, Any]] = field(default_factory=list)
    capability_exchange_state: Dict[str, Any] = field(default_factory=dict)
    tool_laziness: Dict[str, Any] = field(default_factory=dict)
    provider_economist: Dict[str, Any] = field(default_factory=dict)
    otel_state: Dict[str, Any] = field(default_factory=dict)
    plugins_state: Dict[str, Any] = field(default_factory=dict)
    swarm_state: Dict[str, Any] = field(default_factory=dict)
    swarm_governance: Dict[str, Any] = field(default_factory=dict)
    swarm_runs_raw: Dict[str, Any] = field(default_factory=dict)
    swarm_runs: List[Dict[str, Any]] = field(default_factory=list)
    swarm_value_raw: Dict[str, Any] = field(default_factory=dict)
    swarm_value_logs: List[Dict[str, Any]] = field(default_factory=list)
    ollama_status: Dict[str, Any] = field(default_factory=dict)
    beast_cli_plan: Dict[str, Any] = field(default_factory=dict)
    kv_cache_state: Dict[str, Any] = field(default_factory=dict)
    compute_state: Dict[str, Any] = field(default_factory=dict)
    compute_metrics: Dict[str, Any] = field(default_factory=dict)
    compute_savings: Dict[str, Any] = field(default_factory=dict)
    crystal_compute: Dict[str, Any] = field(default_factory=dict)
    commons_spaces: Dict[str, Any] = field(default_factory=dict)
    commons_economy: Dict[str, Any] = field(default_factory=dict)
    commons_scale_economics: Dict[str, Any] = field(default_factory=dict)
    commons_policy: Dict[str, Any] = field(default_factory=dict)
    commons_policy_evaluation: Dict[str, Any] = field(default_factory=dict)
    provider_model_fitness: Dict[str, Any] = field(default_factory=dict)
    master_mega_evidence: Dict[str, Any] = field(default_factory=dict)
    latest_mega_artifact: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    def capabilities_by_kind(self, *kinds: str) -> List[Dict[str, Any]]:
        wanted = set(kinds)
        return [c for c in self.capabilities if str(c.get('kind') or '') in wanted]

    def kinds(self) -> Dict[str, int]:
        kinds = self.capability_inventory.get('kinds')
        if isinstance(kinds, dict):
            return {str(k): int(v) for k, v in kinds.items() if isinstance(v, int) or str(v).isdigit()}
        result: Dict[str, int] = {}
        for cap in self.capabilities:
            kind = str(cap.get('kind') or 'unknown')
            result[kind] = result.get(kind, 0) + 1
        return result

    def families(self) -> Dict[str, int]:
        families = self.capability_inventory.get('families')
        if isinstance(families, dict):
            out: Dict[str, int] = {}
            for key, value in families.items():
                if isinstance(value, int):
                    out[str(key)] = value
                elif isinstance(value, dict) and isinstance(value.get('count'), int):
                    out[str(key)] = value['count']
            return out
        return {}

    def providers(self) -> List[Dict[str, Any]]:
        providers = self.provider_registry.get('providers')
        if isinstance(providers, list):
            return [p for p in providers if isinstance(p, dict)]
        providers_dict = self.provider_state.get('providers')
        if isinstance(providers_dict, dict):
            rows = []
            for provider_id, state in providers_dict.items():
                row = dict(state) if isinstance(state, dict) else {}
                row.setdefault('provider_id', provider_id)
                rows.append(row)
            return rows
        return self.capabilities_by_kind('provider')

    def provider_backend_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for adapter in self.provider_adapters:
            backend = str(adapter.get('backend') or adapter.get('adapter_class') or 'unknown')
            counts[backend] = counts.get(backend, 0) + 1
        if counts:
            return counts
        for provider in self.providers():
            backend = str(provider.get('backend') or 'unknown')
            counts[backend] = counts.get(backend, 0) + 1
        return counts

    def provider_secret_count(self) -> int:
        entries = self.provider_secrets.get('entries')
        if isinstance(entries, list):
            return len(entries)
        providers = self.provider_secrets.get('providers')
        if isinstance(providers, dict):
            return len(providers)
        return 0

    def prec_counts(self) -> List[Dict[str, Any]]:
        return _first_list(self.prec_state, ['counts', 'items', 'records'])

    def prec_recent(self) -> List[Dict[str, Any]]:
        return _first_list(self.prec_state, ['recent'])

    def phase_status(self) -> Dict[str, str]:
        phases = ['perceive', 'reason', 'economize', 'crystallize']
        # Prefer handoff and insight signals for the live cockpit ribbon.
        evidence_count = len(self.insight_packet.get('evidence') or self.insight_packet.get('ranked_evidence') or [])
        ready = bool(self.handoff_precheck.get('ready'))
        recent = self.prec_lifecycles[:8]
        observed = {str(item.get('current_phase') or '').lower() for item in recent}
        return {
            'perceive': 'OK' if self.prec_state or evidence_count else 'WAIT',
            'reason': 'OK' if self.insight_packet else ('OK' if 'reason' in observed else 'WAIT'),
            'economize': 'OK' if ready else ('ACTIVE' if self.handoff_precheck else 'WAIT'),
            'crystallize': 'OK' if self.chronicles or 'crystallize' in observed else 'WAIT',
        }

    def deployment_score(self) -> Dict[str, Any]:
        model_count = len(self.litellm_models)
        nginx_ready = bool(self.nginx_config.strip())
        litellm_running = bool(self.litellm_sidecar.get('running'))
        return {
            'nginx_ready': nginx_ready,
            'litellm_running': litellm_running,
            'litellm_models': model_count,
            'litellm_port': self.litellm_sidecar.get('port', 4000),
            'backend_classes': len(self.provider_backend_counts()),
        }

    def swarm_summary(self) -> Dict[str, Any]:
        statuses = self.swarm_state.get('statuses') if isinstance(self.swarm_state.get('statuses'), dict) else {}
        roles = self.swarm_state.get('role_events') if isinstance(self.swarm_state.get('role_events'), dict) else {}
        profiles = self.swarm_governance.get('profiles') if isinstance(self.swarm_governance.get('profiles'), dict) else {}
        ollama_ready = bool(self.ollama_status.get('server_ready'))
        plan_profile = self.beast_cli_plan.get('profile') if isinstance(self.beast_cli_plan.get('profile'), dict) else {}
        planes = _plane_by_name(self.commons_evidence_plane)
        swarm_plane = planes.get('swarm') or {}
        kv_plane = planes.get('kv_cache') or {}
        candidate_summary = self.commons_evidence_plane.get('candidate_summary') if isinstance(self.commons_evidence_plane.get('candidate_summary'), dict) else {}
        candidate_source_totals: Dict[str, int] = {}
        for source, statuses_by_source in candidate_summary.items():
            if isinstance(statuses_by_source, dict):
                candidate_source_totals[str(source)] = sum(int(value or 0) for value in statuses_by_source.values())
        for candidate in self.commons_candidates:
            source = str(candidate.get('source') or 'unknown')
            if source and source not in candidate_source_totals:
                candidate_source_totals[source] = candidate_source_totals.get(source, 0) + 1
        swarm_evidence = int(swarm_plane.get('evidence_count') or 0)
        kv_evidence = int(kv_plane.get('evidence_count') or 0)
        return {
            'enabled': bool(self.swarm_state.get('enabled')),
            'runs': int(self.swarm_state.get('runs') or 0),
            'statuses': statuses,
            'role_events': roles,
            'profiles': profiles,
            'profile_count': len(profiles),
            'recent_count': len(self.swarm_runs),
            'value_count': len(self.swarm_value_logs),
            'commons_prepared': max(int(self.commons_swarm_ingest.get('prepared') or 0), swarm_evidence),
            'commons_accepted': max(int(self.commons_swarm_ingest.get('accepted') or 0), swarm_evidence),
            'commons_duplicates': int(self.commons_swarm_ingest.get('duplicates') or 0),
            'evidence_plane_count': int(self.commons_evidence_plane.get('plane_count') or 0),
            'evidence_plane_total': int(self.commons_evidence_plane.get('evidence_count') or 0),
            'evidence_plane_hash': self.commons_evidence_plane.get('plane_hash') or '',
            'swarm_candidates_proposed': max(int(self.commons_swarm_candidates.get('proposed_count') or 0), len(self.commons_candidates)),
            'swarm_candidates_skipped': int(self.commons_swarm_candidates.get('skipped_count') or 0),
            'commons_candidate_queue': len(self.commons_candidates),
            'commons_candidate_sources': candidate_source_totals,
            'kv_cache_blocks': max(int(self.kv_cache_state.get('total_blocks') or 0), kv_evidence),
            'kv_cache_operations': int(self.kv_cache_state.get('operations_logged') or 0),
            'kv_cache_prepared': max(int(self.commons_kv_cache_ingest.get('prepared') or 0), kv_evidence),
            'kv_cache_accepted': max(int(self.commons_kv_cache_ingest.get('accepted') or 0), kv_evidence),
            'ollama_ready': ollama_ready,
            'ollama_model': self.ollama_status.get('default_model') or '',
            'ollama_models': len(self.ollama_status.get('models') or []),
            'openclaw_ready': bool(self.beast_cli_plan.get('ready')),
            'openclaw_mode': plan_profile.get('mode') or self.beast_cli_plan.get('mode') or 'openclaw',
            'openclaw_actions': len(self.beast_cli_plan.get('actions') or []),
            'openclaw_hash': self.beast_cli_plan.get('plan_hash') or '',
        }


class BeastApiClient:
    def __init__(self, base_url: str = 'http://127.0.0.1:8000', timeout: float = 2.2):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    async def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if httpx is None:
            raise RuntimeError('httpx is not installed')
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f'{self.base_url}{path}', params=params)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {'items': data}

    async def get_text(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        if httpx is None:
            raise RuntimeError('httpx is not installed')
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f'{self.base_url}{path}', params=params)
            response.raise_for_status()
            return response.text

    async def record_outcome_evidence(self, payload: Dict[str, Any]) -> bool:
        """Best-effort evidence emission; telemetry must never break a live turn."""
        try:
            await self.post_json("/edgek/crystal-compute/outcomes", payload)
            return True
        except Exception:
            return False

    async def post_json(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if httpx is None:
            raise RuntimeError('httpx is not installed')
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f'{self.base_url}{path}', json=payload or {})
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {'items': data}

    async def _health_json(self, path: str) -> tuple[str, Dict[str, Any]]:
        try:
            data = await self.get_json(path)
            status = str(data.get('status') or data.get('service_status') or '').lower()
            return ('OK' if status in {'healthy', 'ok', 'ready', 'available'} or data else 'WARN', data)
        except Exception:
            return 'OFFLINE', {}

    async def snapshot(self) -> BackendSnapshot:
        snap = BackendSnapshot(base_url=self.base_url)
        (snap.gateway, snap.health_raw), (snap.proxy, snap.proxy_health_raw), (snap.mcp, snap.mcp_health_raw) = await asyncio.gather(
            self._health_json('/health'),
            self._health_json('/proxy/health'),
            self._health_json('/mcp/health'),
        )
        snap.online = snap.gateway == 'OK'

        async def guarded_json(name: str, coro):
            try:
                return await coro
            except Exception as exc:
                snap.errors[name] = str(exc)
                return {}

        async def guarded_text(name: str, coro):
            try:
                return await coro
            except Exception as exc:
                snap.errors[name] = str(exc)
                return ''

        (
            capabilities,
            families,
            registry,
            adapters,
            provider_state,
            provider_secrets,
            prec_state,
            prec_lifecycle,
            litellm_config,
            nginx_config,
            litellm_sidecar,
            chronicles,
            routes,
            insight,
            handoff,
            http_telemetry,
            runtime_metrics,
            session_handshake,
            commons_state,
            commons_ranking,
            commons_evidence_plane,
            commons_swarm_ingest,
            commons_swarm_candidates,
            commons_kv_cache_ingest,
            commons_candidates,
            capability_exchange_state,
            tool_laziness,
            otel_state,
            plugins_state,
            swarm_state,
            swarm_governance,
            swarm_runs,
            swarm_value,
            ollama_status,
            beast_cli_plan,
            kv_cache_state,
            compute_state,
            compute_metrics,
            compute_savings,
            crystal_compute,
            commons_spaces,
            commons_economy,
            commons_policy,
            commons_policy_evaluation,
        ) = await asyncio.gather(
            guarded_json('capabilities', self.get_json('/edgek/capabilities')),
            guarded_json('capability_families', self.get_json('/edgek/capabilities/families')),
            guarded_json('provider_registry', self.get_json('/edgek/providers/registry')),
            guarded_json('provider_adapters', self.get_json('/edgek/providers/adapters')),
            guarded_json('provider_state', self.get_json('/edgek/providers/state')),
            guarded_json('provider_secrets', self.get_json('/edgek/providers/secrets')),
            guarded_json('prec_state', self.get_json('/edgek/prec/state')),
            guarded_json('prec_lifecycle', self.get_json('/edgek/prec/lifecycle')),
            guarded_json('litellm_config', self.get_json('/edgek/deploy/litellm-config')),
            guarded_text('nginx_config', self.get_text('/edgek/deploy/nginx-config')),
            guarded_json('litellm_sidecar', self.get_json('/edgek/deploy/litellm-sidecar/state')),
            guarded_json('chronicle', self.get_json('/edgek/chronicle', {'limit': 30})),
            guarded_json('routes', self.get_json('/edgek/route/cards', {'limit': 30})),
            guarded_json('insights', self.post_json('/edgek/insights/compile', {
                'objective': 'BEAST Power Console operator summary',
                'task_class': 'operator_console',
                'limit': 10,
            })),
            guarded_json('handoff', self.post_json('/edgek/handoff/prepare', {
                'objective': 'Show BEAST cockpit readiness and routing power',
                'current_task': {
                    'objective': 'Show BEAST cockpit readiness and routing power',
                    'scope': 'operator console integration',
                    'constraints': ['local first', 'no secret capture', 'read only UI refresh'],
                    'success_criteria': [
                        'PREC lifecycle visible',
                        'provider routing fabric visible',
                        'LiteLLM and Nginx wiring visible',
                        'capability inventory visible',
                    ],
                    'source': 'beast_power_console',
                },
                'task_class': 'operator_console',
                'limit': 8,
                'persist_task': False,
            })),
            guarded_json('http_telemetry', self.get_json('/edgek/telemetry/http')),
            guarded_json('runtime_metrics', self.get_json('/edgek/runtime/metrics', {'limit': 500})),
            guarded_json('session_handshake', self.post_json('/edgek/session/handshake', {
                'objective': 'Operate the BEAST Power Console efficiently',
                'mode': 'tui',
                'session_id': 'beast_tui_operator_console',
                'candidate_tools': [
                    'beast_prepare_task', 'beast_prepare_handoff', 'beast_sourceplan_prepare',
                    'beast_provider_economist_select', 'beast_meta_tool_commons',
                ],
                'preflight_budget_ms': 500,
                'scout_budget_ms': 300,
            })),
            guarded_json('commons_state', self.get_json('/edgek/meta-tool-commons')),
            guarded_json('commons_ranking', self.post_json('/edgek/meta-tool-commons/rank', {
                'task_class': 'operator_console', 'role': 'tool_selector', 'limit': 10,
            })),
            guarded_json('commons_evidence_plane', self.get_json('/edgek/meta-tool-commons/evidence-plane')),
            guarded_json('commons_swarm_ingest', self.post_json('/edgek/meta-tool-commons/swarm-ingest', {
                'limit': 25,
            })),
            guarded_json('commons_swarm_candidates', self.post_json('/edgek/meta-tool-commons/swarm-candidates', {
                'min_samples': 2,
                'limit': 10,
            })),
            guarded_json('commons_kv_cache_ingest', self.post_json('/edgek/meta-tool-commons/kv-cache-ingest', {})),
            guarded_json('commons_candidates', self.get_json('/edgek/meta-tool-commons/candidates', {
                'limit': 100,
            })),
            guarded_json('capability_exchange', self.get_json('/edgek/capability-exchange')),
            guarded_json('tool_laziness', self.post_json('/edgek/tool-laziness/recommend-tools', {
                'scenario': 'operator_console',
                'candidate_tools': [
                    'beast_prepare_task', 'beast_prepare_handoff', 'beast_sourceplan_prepare',
                    'beast_provider_economist_select', 'beast_meta_tool_commons',
                ],
                'required_tools': [], 'min_samples': 3,
            })),
            guarded_json('otel', self.get_json('/edgek/connectors/otel')),
            guarded_json('plugins', self.get_json('/edgek/plugins')),
            guarded_json('swarm_state', self.get_json('/edgek/swarm/state')),
            guarded_json('swarm_governance', self.get_json('/edgek/swarm/governance')),
            guarded_json('swarm_runs', self.get_json('/edgek/swarm/runs', {'limit': 20})),
            guarded_json('swarm_value', self.get_json('/edgek/swarm/value', {'limit': 40})),
            guarded_json('ollama_status', self.get_json('/edgek/ollama/status')),
            guarded_json('beast_cli_plan', self.post_json('/edgek/beast-cli/plan', {
                'objective': 'Operator console swarm/OpenClaw/Ollama readiness preview',
                'mode': 'openclaw',
                'use_ollama': False,
                'preflight_budget_ms': 350,
                'scout_budget_ms': 0,
                'candidate_tools': [
                    'beast_workflow_plan', 'beast_openclaw_plan', 'beast_openclaw_execute',
                    'beast_meta_tool_commons', 'beast_check_promotion', 'ollama_scout',
                ],
                'required_tools': ['beast_workflow_plan'],
                'run_swarm': True,
            })),
            guarded_json('kv_cache_state', self.get_json('/edgek/kv-cache/state')),
            guarded_json('compute_state', self.get_json('/edgek/compute')),
            guarded_json('compute_metrics', self.get_json('/edgek/compute/metrics', {'limit': 500})),
            guarded_json('compute_savings', self.get_json('/edgek/compute/savings-summary', {'limit': 2000})),
            guarded_json('crystal_compute', self.get_json('/edgek/crystal-compute')),
            guarded_json('commons_spaces', self.get_json('/edgek/commons-spaces')),
            guarded_json('commons_economy', self.get_json('/edgek/commons-economy')),
            guarded_json('commons_policy', self.post_json('/edgek/commons-policy/recommend', {
                'task_class': 'operator_console', 'risk': 'medium',
                'gpu_available': False, 'approval_required': False,
            })),
            guarded_json('commons_policy_evaluation', self.get_json('/edgek/commons-policy/evaluation')),
        )

        snap.capability_inventory = _as_dict(capabilities)
        snap.capabilities = _first_list(capabilities, ['capabilities', 'records', 'items'])
        snap.capability_families_raw = _as_dict(families)
        snap.provider_registry = _as_dict(registry)
        snap.provider_adapters_raw = _as_dict(adapters)
        snap.provider_adapters = _first_list(adapters, ['adapters', 'records', 'items'])
        snap.provider_state = _as_dict(provider_state)
        snap.provider_secrets = _as_dict(provider_secrets)
        snap.prec_state = _as_dict(prec_state)
        snap.prec_lifecycle_raw = _as_dict(prec_lifecycle)
        snap.prec_lifecycles = _first_list(prec_lifecycle, ['lifecycles', 'records', 'items'])
        snap.litellm_config = _as_dict(litellm_config)
        if not snap.litellm_config or not normalize_litellm_models(snap.litellm_config):
            local_litellm = load_local_litellm_config()
            if local_litellm:
                snap.litellm_config = local_litellm
                snap.errors.pop('litellm_config', None)
        snap.litellm_models = normalize_litellm_models(snap.litellm_config)
        snap.nginx_config = str(nginx_config or '')
        snap.litellm_sidecar = _as_dict(litellm_sidecar)
        snap.chronicles_raw = _as_dict(chronicles)
        snap.chronicles = _first_list(chronicles, ['chronicles', 'records', 'items', 'tasks'])
        snap.routes_raw = _as_dict(routes)
        snap.routes = _first_list(routes, ['route_cards', 'routes', 'cards', 'records', 'items'])
        snap.insight_packet = _as_dict(insight)
        snap.handoff_precheck = _as_dict(handoff)
        snap.http_telemetry = _as_dict(http_telemetry)
        snap.runtime_metrics = _as_dict(runtime_metrics)
        snap.session_handshake = _as_dict(session_handshake)
        snap.commons_state = _as_dict(commons_state)
        snap.commons_ranking = _as_dict(commons_ranking)
        snap.commons_evidence_plane = _as_dict(commons_evidence_plane)
        snap.commons_swarm_ingest = _as_dict(commons_swarm_ingest)
        snap.commons_swarm_candidates = _as_dict(commons_swarm_candidates)
        snap.commons_kv_cache_ingest = _as_dict(commons_kv_cache_ingest)
        snap.commons_candidates = _first_list(commons_candidates, ['candidates', 'records', 'items'])
        snap.capability_exchange_state = _as_dict(capability_exchange_state)
        snap.tool_laziness = _as_dict(tool_laziness)
        snap.otel_state = _as_dict(otel_state)
        snap.plugins_state = _as_dict(plugins_state)
        snap.swarm_state = _as_dict(swarm_state)
        snap.swarm_governance = _as_dict(swarm_governance)
        snap.swarm_runs_raw = _as_dict(swarm_runs)
        snap.swarm_runs = _first_list(swarm_runs, ['runs', 'records', 'items'])
        snap.swarm_value_raw = _as_dict(swarm_value)
        snap.swarm_value_logs = _first_list(swarm_value, ['value_logs', 'records', 'items'])
        snap.ollama_status = _as_dict(ollama_status)
        snap.beast_cli_plan = _as_dict(beast_cli_plan)
        snap.kv_cache_state = _as_dict(kv_cache_state)
        snap.compute_state = _as_dict(compute_state)
        snap.compute_metrics = _as_dict(compute_metrics)
        snap.compute_savings = _as_dict(compute_savings)
        snap.crystal_compute = _as_dict(crystal_compute)
        snap.commons_spaces = _as_dict(commons_spaces)
        snap.commons_economy = _as_dict(commons_economy)
        snap.commons_policy = _as_dict(commons_policy)
        snap.commons_policy_evaluation = _as_dict(commons_policy_evaluation)
        localish_gateway = any(token in self.base_url for token in ("127.0.0.1", "localhost", "0.0.0.0"))
        if localish_gateway:
            local_spaces = load_local_spaces_snapshot()
            local_registry = _as_dict(local_spaces.get("registry"))
            if local_registry and int(local_registry.get("count") or 0) >= int(snap.commons_spaces.get("count") or 0):
                snap.commons_spaces = local_registry
                snap.errors.pop("commons_spaces", None)
            if not snap.commons_policy and isinstance(local_spaces.get("policy"), dict):
                snap.commons_policy = _as_dict(local_spaces.get("policy"))
                snap.errors.pop("commons_policy", None)
            if not snap.commons_policy_evaluation and isinstance(local_spaces.get("evaluation"), dict):
                snap.commons_policy_evaluation = _as_dict(local_spaces.get("evaluation"))
                snap.errors.pop("commons_policy_evaluation", None)
            local_scale_economics = load_local_scale_economics_snapshot()
            if local_scale_economics:
                snap.commons_scale_economics = local_scale_economics
            local_commons = load_local_commons_snapshot()
            local_state = _as_dict(local_commons.get("state"))
            local_plane = _as_dict(local_commons.get("evidence_plane"))
            artifact_plane = _as_dict(local_commons.get("latest_artifact_plane"))
            local_candidates = _first_list(local_commons.get("candidates"), ["candidates", "records", "items"])
            local_swarm_candidates = _as_dict(local_commons.get("swarm_candidates"))
            local_kv_ingest = _as_dict(local_commons.get("kv_cache_ingest"))
            local_kv_state = _as_dict(local_commons.get("kv_cache_state"))
            if local_state and int(local_state.get("evidence_count") or 0) > int(snap.commons_state.get("evidence_count") or 0):
                snap.commons_state = local_state
            if local_plane and int(local_plane.get("evidence_count") or 0) > int(snap.commons_evidence_plane.get("evidence_count") or 0):
                snap.commons_evidence_plane = local_plane
                snap.errors.pop("commons_evidence_plane", None)
            if artifact_plane:
                snap.commons_evidence_plane = merge_evidence_planes(snap.commons_evidence_plane, artifact_plane)
                snap.errors.pop("commons_evidence_plane", None)
            if not snap.commons_swarm_ingest and snap.commons_evidence_plane:
                planes = snap.commons_evidence_plane.get("planes") if isinstance(snap.commons_evidence_plane.get("planes"), list) else []
                swarm_plane = next((row for row in planes if isinstance(row, dict) and row.get("plane") == "swarm"), {})
                prepared = int((swarm_plane or {}).get("evidence_count") or 0)
                if prepared:
                    snap.commons_swarm_ingest = {
                        "prepared": prepared,
                        "accepted": prepared,
                        "duplicates": 0,
                        "source": "local_fallback_evidence_plane",
                    }
                    snap.errors.pop("commons_swarm_ingest", None)
            if local_candidates and len(local_candidates) > len(snap.commons_candidates):
                snap.commons_candidates = local_candidates
                snap.errors.pop("commons_candidates", None)
            if local_swarm_candidates and int(local_swarm_candidates.get("proposed_count") or 0) >= int(snap.commons_swarm_candidates.get("proposed_count") or 0):
                snap.commons_swarm_candidates = local_swarm_candidates
                snap.errors.pop("commons_swarm_candidates", None)
            if local_kv_state and int(local_kv_state.get("total_blocks") or 0) >= int(snap.kv_cache_state.get("total_blocks") or 0):
                snap.kv_cache_state = local_kv_state
                snap.errors.pop("kv_cache_state", None)
            if local_kv_ingest and int(local_kv_ingest.get("prepared") or 0) >= int(snap.commons_kv_cache_ingest.get("prepared") or 0):
                snap.commons_kv_cache_ingest = local_kv_ingest
                snap.errors.pop("commons_kv_cache_ingest", None)
            if not snap.commons_kv_cache_ingest and snap.commons_evidence_plane:
                planes = snap.commons_evidence_plane.get("planes") if isinstance(snap.commons_evidence_plane.get("planes"), list) else []
                kv_plane = next((row for row in planes if isinstance(row, dict) and row.get("plane") == "kv_cache"), {})
                prepared = int((kv_plane or {}).get("evidence_count") or 0)
                if prepared:
                    snap.commons_kv_cache_ingest = {
                        "prepared": prepared,
                        "accepted": prepared,
                        "duplicates": 0,
                        "source": "local_fallback_evidence_plane",
                    }
                    snap.errors.pop("commons_kv_cache_ingest", None)
            if not snap.swarm_state and isinstance(local_commons.get("swarm_state"), dict):
                snap.swarm_state = _as_dict(local_commons.get("swarm_state"))
            if not snap.swarm_governance and isinstance(local_commons.get("swarm_governance"), dict):
                snap.swarm_governance = _as_dict(local_commons.get("swarm_governance"))
            if not snap.swarm_runs:
                snap.swarm_runs_raw = _as_dict(local_commons.get("swarm_runs"))
                snap.swarm_runs = _first_list(local_commons.get("swarm_runs"), ["runs", "records", "items"])
            if not snap.swarm_value_logs:
                snap.swarm_value_raw = _as_dict(local_commons.get("swarm_value"))
                snap.swarm_value_logs = _first_list(local_commons.get("swarm_value"), ["value_logs", "records", "items"])
            local_compute = load_local_compute_snapshot()
            local_metrics = _as_dict(local_compute.get("metrics"))
            local_savings = _as_dict(local_compute.get("savings"))
            local_state = _as_dict(local_compute.get("state"))
            try:
                local_samples = int(local_metrics.get("sample_size") or 0)
                remote_samples = int(snap.compute_metrics.get("sample_size") or 0)
            except Exception:
                local_samples = remote_samples = 0
            if local_metrics and local_samples >= remote_samples:
                snap.compute_metrics = local_metrics
            if local_savings and (local_samples >= remote_samples or not snap.compute_savings):
                snap.compute_savings = local_savings
            if local_state:
                merged_state = dict(snap.compute_state)
                merged_state.update(local_state)
                snap.compute_state = merged_state
        snap.provider_model_fitness = load_provider_model_fitness()
        snap.master_mega_evidence = load_master_mega_evidence()
        snap.latest_mega_artifact = load_latest_mega_artifact()

        economist_candidates = []
        for provider in snap.providers():
            provider_id = str(provider.get('provider_id') or provider.get('id') or provider.get('name') or '')
            matching = [
                item for item in snap.chronicles
                if str(item.get('provider') or '').lower().replace('-', '_') == provider_id.lower().replace('-', '_')
            ][:20]
            if not provider_id or not matching:
                continue
            tasks = len(matching)
            rescued = sum(1 for item in matching if item.get('canonicalized') or (item.get('output_evidence') or {}).get('repair_attempted'))
            latencies = [float(item['latency_ms']) for item in matching if item.get('latency_ms') not in (None, '')]
            latest = matching[0]
            economist_candidates.append({
                'provider': provider_id,
                'recommended_role': latest.get('recommended_role') or latest.get('provider_role') or 'rescue_backed_action_ir',
                'sample_size': tasks,
                'rescued_completed': rescued,
                'rescue_rate': rescued / tasks if tasks else 0.0,
                'hidden_clean_completed': sum(1 for item in matching if item.get('hidden_clean')),
                'hidden_clean_rate': sum(1 for item in matching if item.get('hidden_clean')) / tasks if tasks else 0.0,
                'avg_latency_ms': sum(latencies) / len(latencies) if latencies else None,
                'route_confidence': latest.get('route_confidence') or 'medium',
                'hidden_clean_usd_per_fix': latest.get('hidden_clean_usd_per_fix'),
            })
        if economist_candidates:
            snap.provider_economist = _as_dict(await guarded_json(
                'provider_economist',
                self.post_json('/edgek/provider-economist/select', {
                    'candidates': economist_candidates,
                    'requested_role': 'primary_patch_provider',
                    'min_auth_confidence': 0.6,
                    'prefer_hidden_clean': True,
                }),
            ))

        return snap

    async def action(self, title: str, path: str, payload: Optional[Dict[str, Any]] = None, method: str = "POST") -> ActionResult:
        """Run one BEAST backend action and normalize the result for the TUI."""
        try:
            if method.upper() == "GET":
                data = await self.get_json(path, payload or None)
            else:
                data = await self.post_json(path, payload or {})
            summary = self._summarize(data)
            return ActionResult(ok=True, title=title, summary=summary, data=data)
        except Exception as exc:
            return ActionResult(ok=False, title=title, summary="", data={}, error=str(exc))

    async def action_text(self, title: str, path: str, params: Optional[Dict[str, Any]] = None) -> ActionResult:
        try:
            text = await self.get_text(path, params)
            return ActionResult(ok=True, title=title, summary=f"received {len(text.splitlines())} lines", data={"text": text})
        except Exception as exc:
            return ActionResult(ok=False, title=title, summary="", data={}, error=str(exc))

    async def start_live_session(self, objective: str, provider: str = "litellm", workspace: str = "") -> ActionResult:
        payload = {
            "kind": "ide_live_session",
            "objective": objective,
            "scope": "BEAST CLI/TUI live coding session",
            "provider": provider,
            "metadata": {"workspace": workspace, "surface": "beast_tui"},
        }
        result = await self.action("PREC session start", "/edgek/prec/start", payload)
        if result.ok:
            lifecycle_id = str(result.data.get("lifecycle_id") or result.data.get("id") or "")
            if lifecycle_id:
                await self.update_prec(lifecycle_id, "perceive", "Live session opened from BEAST TUI.", "active")
        return result

    async def update_prec(self, lifecycle_id: str, phase: str, summary: str, status: str = "completed", artifacts: Optional[Dict[str, Any]] = None, signals: Optional[List[str]] = None) -> ActionResult:
        if not lifecycle_id:
            return ActionResult(False, "PREC update", "", error="No lifecycle_id available")
        return await self.action("PREC update", "/edgek/prec/update", {
            "lifecycle_id": lifecycle_id,
            "phase": phase,
            "status": status,
            "summary": summary,
            "artifacts": artifacts or {},
            "signals": signals or [],
        })

    async def build_task_envelope(self, objective: str, provider: str = "litellm", task_class: str = "live_coding") -> ActionResult:
        return await self.action("Task envelope", "/edgek/task/envelope", {
            "user_request": objective,
            "provider": provider,
            "task_class": task_class,
            "dry_run": True,
        })

    async def compile_insight(self, objective: str, provider: str = "litellm", current_task: Optional[Dict[str, Any]] = None, limit: int = 8) -> ActionResult:
        return await self.action("Insight compile", "/edgek/insights/compile", {
            "objective": objective,
            "provider": provider,
            "task_class": "beast_live_session",
            "current_task": current_task or self._current_task(objective),
            "limit": limit,
        })

    async def prepare_handoff(self, objective: str, provider: str = "litellm", limit: int = 8) -> ActionResult:
        return await self.action("Handoff prepare", "/edgek/handoff/prepare", {
            "objective": objective,
            "provider": provider,
            "task_class": "beast_live_session",
            "current_task": self._current_task(objective),
            "limit": limit,
            "persist_task": True,
        })

    async def provider_diagnostic(self, provider: str, objective: str = "Diagnose selected provider route") -> ActionResult:
        return await self.action("Provider diagnostic", "/edgek/task/provider-diagnostic", {
            "provider": provider,
            "user_request": objective,
            "task_class": "provider_debugging",
            "chronicle": True,
        })

    async def provider_route_card(self, provider: str, objective: str = "Build provider diagnostic route card") -> ActionResult:
        return await self.action("Provider route card", f"/edgek/route/provider-diagnostic/{provider}", {
            "user_request": objective,
            "provider": provider,
            "persist": True,
        })

    async def quality_cascade(self, objective: str, provider: str = "litellm") -> ActionResult:
        return await self.action("Quality cascade", "/edgek/task/quality-cascade", {
            "user_request": objective,
            "provider": provider,
            "task_class": "live_coding_quality",
        })

    async def write_deploy_configs(self) -> ActionResult:
        return await self.action("Write generated configs", "/edgek/deploy/write-configs", {"output_dir": "deploy/generated"})

    async def nginx_apply(self, approved: bool = False, dry_run: bool = True) -> ActionResult:
        return await self.action("Nginx apply", "/edgek/deploy/nginx/apply", {"dry_run": dry_run, "approved": approved})

    async def litellm_start(self, approved: bool = False, dry_run: bool = True) -> ActionResult:
        return await self.action("LiteLLM sidecar start", "/edgek/deploy/litellm-sidecar/start", {"dry_run": dry_run, "approved": approved})

    async def litellm_stop(self, approved: bool = False, dry_run: bool = True) -> ActionResult:
        return await self.action("LiteLLM sidecar stop", "/edgek/deploy/litellm-sidecar/stop", {"dry_run": dry_run, "approved": approved})

    async def render_nginx_config(self) -> ActionResult:
        return await self.action_text("Render Nginx config", "/edgek/deploy/nginx-config")

    async def render_litellm_config(self) -> ActionResult:
        return await self.action("Render LiteLLM config", "/edgek/deploy/litellm-config", method="GET")

    async def import_provider_secrets(self, source_path: str, overwrite: bool = True, load: bool = True) -> ActionResult:
        return await self.action("Import provider secrets", "/edgek/providers/secrets/import", {
            "source_path": source_path,
            "overwrite": overwrite,
            "load": load,
        })


    def workspace_root(self) -> Path:
        root = os.environ.get("BEAST_WORKSPACE") or os.getcwd()
        return Path(root).expanduser().resolve()

    def _is_safe_relative(self, path: str) -> bool:
        try:
            root = self.workspace_root()
            resolved = (root / path).resolve()
            return root == resolved or root in resolved.parents
        except Exception:
            return False

    def workspace_file_candidates(self, limit: int = 80) -> List[Dict[str, Any]]:
        """Return small, safe workspace files for the TUI context picker.

        This is intentionally local-only and conservative: no secrets, databases,
        git internals, caches, node_modules, venvs, or large artifacts.
        """
        root = self.workspace_root()
        if not root.exists():
            return []
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
            "dist", "build", ".next", ".cache", ".tox", "data", "logs", "tmp", "temp", ".idea",
        }
        allowed_ext = {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml",
            ".md", ".txt", ".css", ".html", ".sh", ".ini", ".cfg", ".nginx", ".conf",
        }
        secret_markers = ("secret", "token", "key", "credential", ".env", "vault")
        rows: List[Dict[str, Any]] = []
        for path in root.rglob("*"):
            try:
                rel_parts = path.relative_to(root).parts
                if any(part in skip_dirs for part in rel_parts):
                    continue
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root))
                rel_lower = rel.lower()
                if any(marker in rel_lower for marker in secret_markers):
                    continue
                if path.suffix.lower() not in allowed_ext and path.name not in {"Dockerfile", "Makefile", "requirements.txt", "pyproject.toml"}:
                    continue
                size = path.stat().st_size
                if size > 180_000:
                    continue
                priority = 0
                if rel in {"bin/beast", "app/cli/ui.py", "app/cli/api.py", "app/main.py", "README.md", "requirements.txt", "pyproject.toml"}:
                    priority -= 50
                if rel.startswith(("app/", "bin/", "tests/", "vscode-extension/")):
                    priority -= 10
                rows.append({"path": rel, "size": size, "ext": path.suffix.lower() or path.name, "priority": priority})
            except Exception:
                continue
        rows.sort(key=lambda x: (x.get("priority", 0), str(x.get("path", ""))))
        return rows[:limit]

    def read_workspace_file(self, rel_path: str, max_chars: int = 6000) -> Dict[str, Any]:
        if not self._is_safe_relative(rel_path):
            return {"path": rel_path, "ok": False, "error": "Unsafe path outside workspace"}
        root = self.workspace_root()
        path = (root / rel_path).resolve()
        if not path.exists() or not path.is_file():
            return {"path": rel_path, "ok": False, "error": "File not found"}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {
                "path": rel_path,
                "ok": True,
                "size": path.stat().st_size,
                "preview": text[:max_chars],
                "truncated": len(text) > max_chars,
                "line_count": text.count("\n") + 1,
            }
        except Exception as exc:
            return {"path": rel_path, "ok": False, "error": str(exc)}

    def read_context_files(self, paths: List[str], max_files: int = 8, max_chars_each: int = 4200) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        seen = set()
        for path in paths[:max_files]:
            if path in seen:
                continue
            seen.add(path)
            records.append(self.read_workspace_file(path, max_chars=max_chars_each))
        return records

    def build_patch_plan(self, objective: str, context_files: List[str], provider: str = "litellm") -> ActionResult:
        """Create a governed local patch plan without modifying code.

        This is a working Patch 3 command: it inspects selected context files,
        builds a safe edit plan, and queues it for explicit approval/save.
        """
        objective = (objective or "Prepare a governed BEAST workspace edit plan").strip()
        records = self.read_context_files(context_files)
        touched = [r for r in records if r.get("ok")]
        file_notes = []
        for rec in touched:
            preview = str(rec.get("preview") or "")
            symbols = []
            for match in re.finditer(r"^(class|def|async def)\s+([A-Za-z_][\w_]*)", preview, flags=re.MULTILINE):
                symbols.append(match.group(2))
            file_notes.append({
                "path": rec.get("path"),
                "line_count": rec.get("line_count"),
                "symbols": symbols[:12],
                "truncated": rec.get("truncated"),
            })
        plan_id = "plan_" + hex(abs(hash((objective, tuple(context_files), time.time()))))[2:12]
        plan = {
            "plan_id": plan_id,
            "kind": "beast_workspace_edit_plan",
            "status": "draft_requires_approval",
            "objective": objective,
            "provider": provider,
            "workspace": str(self.workspace_root()),
            "context_files": file_notes,
            "risk_level": "medium" if touched else "low",
            "approval_required": True,
            "write_policy": "Patch 4 supports guarded diff preview, verified apply, and rollback. Default generated operations write only under .beast/ unless output governance approves scoped source-file operations.",
            "prec_mapping": {
                "perceive": "Selected context files inspected locally.",
                "reason": "Plan proposes safe edits before provider or file writes.",
                "economize": "Only selected context files are included in the handoff scope.",
                "crystallize": "Approved plan is saved under .beast/patch_plans/ for Chronicle/promotion use.",
            },
            "steps": [
                {"step": 1, "action": "confirm_scope", "detail": "Review selected files and objective."},
                {"step": 2, "action": "compile_insight", "detail": "Run local insight and handoff precheck with the selected context."},
                {"step": 3, "action": "draft_patch", "detail": "Ask provider/local scout to produce a diff scoped only to selected files."},
                {"step": 4, "action": "verify", "detail": "Run syntax/tests/quality cascade before applying any edits."},
                {"step": 5, "action": "crystallize", "detail": "Write Chronicle record and promotion candidate when successful."},
            ],
            "files_allowed": [r.get("path") for r in touched],
            "files_blocked": [r.get("path") for r in records if not r.get("ok")],
            "operations": [
                {
                    "op": "create_or_replace",
                    "path": f".beast/patch_plans/{plan_id}.md",
                    "content_kind": "markdown_summary",
                    "description": "Crystallized human-readable plan artifact. Safe BEAST metadata write.",
                    "beast_managed": True,
                },
                {
                    "op": "create_or_replace",
                    "path": f".beast/patch_plans/{plan_id}.json",
                    "content_kind": "json_plan",
                    "description": "Approved plan JSON artifact. Safe BEAST metadata write.",
                    "beast_managed": True,
                },
            ],
            "apply_policy": {
                "default_mode": "beast_metadata_only",
                "source_edits_require": ["explicit operation", "allowed file scope", "approval", "verification"],
                "rollback_required": True,
            },
            "created_at": int(time.time()),
        }
        summary = f"patch plan {plan_id} prepared for {len(touched)} context file(s)"
        return ActionResult(True, "Patch plan", summary, plan)


    def _file_hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def _file_hash_path(self, path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    def _comment_suffix_for(self, rel_path: str) -> str:
        ext = Path(rel_path).suffix.lower()
        if ext in {".py", ".sh", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}:
            return "#"
        if ext in {".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".rs", ".go"}:
            return "//"
        if ext in {".css"}:
            return "/*"
        if ext in {".html", ".xml"}:
            return "<!--"
        return ""

    def _append_source_note(self, rel_path: str, old_text: str, objective: str, plan_id: str, provider: str) -> str:
        """Create a conservative source-edit draft when no provider JSON diff is available.

        This intentionally produces a visible, reversible source change only for
        files the operator selected. It proves the Patch 5 source-diff/apply
        machinery without pretending the local fallback can safely refactor code
        by itself.
        """
        prefix = self._comment_suffix_for(rel_path)
        timestamp = int(time.time())
        if prefix == "/*":
            note = f"\n\n/* BEAST PATCH 5 DRAFT NOTE\n   plan: {plan_id}\n   provider: {provider}\n   objective: {objective[:280]}\n   created: {timestamp}\n*/\n"
        elif prefix == "<!--":
            note = f"\n\n<!-- BEAST PATCH 5 DRAFT NOTE\nplan: {plan_id}\nprovider: {provider}\nobjective: {objective[:280]}\ncreated: {timestamp}\n-->\n"
        elif prefix:
            note = "\n\n" + "\n".join([
                f"{prefix} BEAST PATCH 5 DRAFT NOTE",
                f"{prefix} plan: {plan_id}",
                f"{prefix} provider: {provider}",
                f"{prefix} objective: {objective[:280]}",
                f"{prefix} created: {timestamp}",
            ]) + "\n"
        else:
            note = "\n\n" + "\n".join([
                "BEAST PATCH 5 DRAFT NOTE",
                f"plan: {plan_id}",
                f"provider: {provider}",
                f"objective: {objective[:280]}",
                f"created: {timestamp}",
            ]) + "\n"
        if old_text.endswith("\n"):
            return old_text + note.lstrip("\n")
        return old_text + note

    def _extract_json_object_from_text(self, text: str) -> Dict[str, Any]:
        """Best-effort strict JSON extraction from a provider response."""
        text = (text or "").strip()
        if not text:
            return {}
        candidates: List[str] = []
        for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE):
            candidates.append(match.group(1))
        candidates.append(text)
        # Also try the largest {...} region.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidates.append(text[start:end+1])
        for candidate in candidates:
            try:
                value = json.loads(candidate)
                return value if isinstance(value, dict) else {}
            except Exception:
                continue
        return {}

    def _provider_plan_from_text(self, text: str, objective: str, context_files: List[str], provider: str, expected_handoff_hash: str = "") -> Dict[str, Any]:
        plan_id = "plan_" + hex(abs(hash((objective, provider, time.time()))))[2:12]
        allowed = [str(x) for x in context_files]
        root = self.workspace_root()
        profile = provider_output_profile(provider)
        gate = output_gate(root, text, allowed, profile, expected_handoff_hash=expected_handoff_hash)
        if not gate.ok:
            return {}
        operations: List[Dict[str, Any]] = []
        for idx, op in enumerate(gate.operations):
            rel = str(op.get("path") or "")
            current_path = (root / rel).resolve()
            old_hash = self._file_hash_path(current_path) if current_path.exists() else ""
            operations.append({
                "op_id": str(op.get("op_id") or f"op_{idx+1:03d}"),
                "op": "create_or_replace",
                "path": rel,
                "content": str(op.get("content") or ""),
                "description": str(op.get("description") or f"Provider-generated replacement for {rel}"),
                "beast_managed": False,
                "source_edit": True,
                "provider_generated": True,
                "selected": bool(op.get("selected", True)),
                "expected_hash": str(op.get("expected_hash") or old_hash),
            })
        if not operations:
            if not gate.non_mutating_requests:
                return {}
        selected = [op["op_id"] for op in operations if op.get("selected", True)]
        return {
            "plan_id": plan_id,
            "kind": "beast_provider_source_patch_plan",
            "status": "draft_requires_approval",
            "objective": objective,
            "provider": provider,
            "workspace": str(self.workspace_root()),
            "risk_level": "high",
            "approval_required": True,
            "provider_generated": True,
            "output_evidence": gate.evidence,
            "non_mutating_requests": gate.non_mutating_requests,
            "write_policy": "Provider-generated source operations are scoped to selected files only. Apply requires diff preview, approval, verification, rollback snapshot, and Chronicle crystallization.",
            "context_files": [{"path": p} for p in allowed],
            "files_allowed": allowed,
            "files_blocked": [],
            "operations": operations,
            "selected_operations": selected,
            "apply_policy": {"source_edits_require": ["selected file", "expected hash", "approval", "verification", "rollback"], "rollback_required": True, "run_py_compile": True, "run_tests": False},
            "prec_mapping": {
                "perceive": "Selected source files and provider draft parsed into explicit operations.",
                "reason": "Provider/local draft constrained by BEAST path, hash, and policy gates.",
                "economize": "Only selected operations/hunks are eligible for apply.",
                "crystallize": "Successful apply writes rollback and Chronicle artifacts.",
            },
            "steps": [
                {"step": 1, "action": "preview_diff", "detail": "Review all provider-generated hunks."},
                {"step": 2, "action": "select_hunks", "detail": "Toggle selected operations before apply."},
                {"step": 3, "action": "verify", "detail": "Run py_compile/JSON validation and optional tests."},
                {"step": 4, "action": "apply", "detail": "Write selected operations with rollback snapshot."},
                {"step": 5, "action": "crystallize", "detail": "Write Chronicle record after successful verification."},
            ],
            "created_at": int(time.time()),
        }

    def build_source_patch_plan(
        self,
        objective: str,
        context_files: List[str],
        provider: str = "litellm",
        provider_text: str = "",
        expected_handoff_hash: str = "",
        provider_handoff: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        """Create a source-edit patch plan scoped to selected files.

        If provider_text contains a valid BEAST JSON operation plan, use it.
        Otherwise create conservative local source-note operations so the operator
        can exercise the diff/apply/rollback loop safely on selected files.
        """
        objective = (objective or "Prepare a governed source patch").strip()
        context_files = [str(p) for p in (context_files or [])][:6]
        provider_handoff = provider_handoff or build_provider_handoff(
            self.workspace_root(),
            objective,
            context_files,
            provider,
            task_name="sourceplan",
            verification="python -m pytest tests -q",
        )
        expected_handoff_hash = expected_handoff_hash or str((provider_handoff.get("trace") or {}).get("provider_handoff_hash") or (provider_handoff.get("trace") or {}).get("input_handoff_hash") or "")
        provider_plan = self._provider_plan_from_text(provider_text, objective, context_files, provider, expected_handoff_hash=expected_handoff_hash) if provider_text else {}
        if provider_plan:
            provider_plan["provider_handoff"] = provider_handoff
            provider_plan["provider_handoff_hash"] = expected_handoff_hash
            provider_plan["bridge_enforced"] = True
            return ActionResult(True, "Source patch plan", f"provider-generated source plan {provider_plan.get('plan_id')} prepared", provider_plan)
        records = self.read_context_files(context_files, max_files=6, max_chars_each=12000)
        touched = [r for r in records if r.get("ok")]
        plan_id = "plan_" + hex(abs(hash((objective, tuple(context_files), provider, time.time()))))[2:12]
        operations: List[Dict[str, Any]] = []
        file_notes: List[Dict[str, Any]] = []
        for rec in touched[:4]:
            rel = str(rec.get("path") or "")
            old_text = str(rec.get("preview") or "")
            root_path = (self.workspace_root() / rel).resolve()
            try:
                old_full = root_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                old_full = old_text
            new_text = self._append_source_note(rel, old_full, objective, plan_id, provider)
            op_id = f"op_{len(operations)+1:03d}"
            operations.append({
                "op_id": op_id,
                "op": "create_or_replace",
                "path": rel,
                "content": new_text,
                "description": f"Local fallback source hunk for {rel}; replace with provider-generated content when available.",
                "beast_managed": False,
                "source_edit": True,
                "provider_generated": False,
                "selected": True,
                "expected_hash": self._file_hash_text(old_full),
            })
            file_notes.append({"path": rel, "line_count": rec.get("line_count"), "truncated": rec.get("truncated"), "expected_hash": self._file_hash_text(old_full)[:12]})
        # Always include BEAST metadata operations too, but not selected for source apply by default.
        operations.append({"op_id": f"op_{len(operations)+1:03d}", "op": "create_or_replace", "path": f".beast/patch_plans/{plan_id}.md", "content_kind": "markdown_summary", "description": "Human-readable patch plan artifact.", "beast_managed": True, "source_edit": False, "selected": True})
        operations.append({"op_id": f"op_{len(operations)+1:03d}", "op": "create_or_replace", "path": f".beast/patch_plans/{plan_id}.json", "content_kind": "json_plan", "description": "JSON patch plan artifact.", "beast_managed": True, "source_edit": False, "selected": True})
        selected = [op["op_id"] for op in operations if op.get("selected", True)]
        plan = {
            "plan_id": plan_id,
            "kind": "beast_source_patch_plan",
            "status": "draft_requires_approval",
            "objective": objective,
            "provider": provider,
            "workspace": str(self.workspace_root()),
            "context_files": file_notes,
            "risk_level": "high" if file_notes else "low",
            "approval_required": True,
            "provider_generated": False,
            "provider_handoff": provider_handoff,
            "provider_handoff_hash": expected_handoff_hash,
            "bridge_enforced": True,
            "write_policy": "Patch 5 source operations apply only to selected files/hunks, require preview/approval, verify before and after write, and write rollback + Chronicle artifacts.",
            "files_allowed": [str(r.get("path")) for r in touched],
            "files_blocked": [str(r.get("path")) for r in records if not r.get("ok")],
            "operations": operations,
            "selected_operations": selected,
            "apply_policy": {"source_edits_require": ["selected file", "expected hash", "approval", "verification", "rollback"], "rollback_required": True, "run_py_compile": True, "run_tests": False},
            "prec_mapping": {
                "perceive": "Selected source files read locally and hashed.",
                "reason": "Source operations generated or provider operations parsed under policy constraints.",
                "economize": "Only selected hunks are eligible for apply.",
                "crystallize": "Successful apply writes rollback and Chronicle artifacts.",
            },
            "steps": [
                {"step": 1, "action": "preview_diff", "detail": "Review unified diff."},
                {"step": 2, "action": "select_hunks", "detail": "Toggle operations/hunks before apply."},
                {"step": 3, "action": "verify", "detail": "Run syntax validation and optional tests."},
                {"step": 4, "action": "apply", "detail": "Apply selected operations only."},
                {"step": 5, "action": "crystallize", "detail": "Write Chronicle record and rollback pointer."},
            ],
            "created_at": int(time.time()),
        }
        summary = f"source patch plan {plan_id} prepared with {len([op for op in operations if op.get('source_edit')])} source hunk(s)"
        return ActionResult(True, "Source patch plan", summary, plan)

    async def draft_source_patch_plan(self, objective: str, context_files: List[str], provider: str = "litellm") -> ActionResult:
        """Ask the selected provider for a strict JSON source patch, with local fallback."""
        objective = (objective or "Prepare a governed source patch").strip()
        context_files = [str(p) for p in (context_files or [])][:6]
        records = self.read_context_files(context_files, max_files=6, max_chars_each=7000)
        usable = [r for r in records if r.get("ok")]
        allowed = [str(r.get("path")) for r in usable]
        handoff = build_provider_handoff(
            self.workspace_root(),
            objective,
            allowed or context_files,
            provider,
            task_name="sourceplan",
            verification="python -m pytest tests -q",
        )
        if not usable:
            return self.build_source_patch_plan(
                objective,
                context_files,
                provider=provider,
                expected_handoff_hash=str((handoff.get("trace") or {}).get("provider_handoff_hash") or (handoff.get("trace") or {}).get("input_handoff_hash") or ""),
                provider_handoff=handoff,
            )
        system = "You are BEAST Output Worker. Return only the governed output object requested by the handoff."
        user = render_provider_handoff_prompt(handoff)
        provider_text = ""
        # Avoid hanging when LiteLLM is selected but the sidecar is off.
        try_provider = True
        if str(provider or "").lower() in {"litellm", "auto", "beast-auto"}:
            try_provider = await self.litellm_sidecar_running()
        if try_provider:
            result = await self.chat_completion(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}], model="beast-auto", context_files=context_files)
            if result.ok:
                provider_text = self._extract_assistant_text(result.data)
        plan_result = self.build_source_patch_plan(
            objective,
            context_files,
            provider=provider,
            provider_text=provider_text,
            expected_handoff_hash=str((handoff.get("trace") or {}).get("provider_handoff_hash") or (handoff.get("trace") or {}).get("input_handoff_hash") or ""),
            provider_handoff=handoff,
        )
        if plan_result.ok:
            plan_result.data["provider_attempted"] = bool(try_provider)
            plan_result.data["provider_text_received"] = bool(provider_text)
            plan_result.data["provider_handoff"] = handoff
            if not plan_result.data.get("provider_generated"):
                plan_result.data["provider_fallback_reason"] = "Provider did not return a valid strict JSON source patch; local fallback hunk generated."
        return plan_result

    def save_patch_plan(self, plan: Dict[str, Any]) -> ActionResult:
        """Save an approved patch plan to the workspace, without editing source files."""
        root = self.workspace_root()
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        out_dir = root / ".beast" / "patch_plans"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{plan_id}.json"
            saved = dict(plan)
            saved["status"] = "approved_saved"
            saved["approved_at"] = int(time.time())
            out_path.write_text(json.dumps(saved, indent=2, default=str), encoding="utf-8")
            return ActionResult(True, "Patch plan approved", f"saved {out_path}", {"path": str(out_path), "plan": saved})
        except Exception as exc:
            return ActionResult(False, "Patch plan approved", "", error=str(exc))

    def _plan_markdown(self, plan: Dict[str, Any]) -> str:
        """Render a patch plan as a human-readable BEAST artifact."""
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        files = plan.get("files_allowed") or []
        steps = plan.get("steps") or []
        lines = [
            f"# BEAST Patch Plan: {plan_id}",
            "",
            f"**Objective:** {plan.get('objective', '')}",
            f"**Provider:** {plan.get('provider', '')}",
            f"**Risk:** {plan.get('risk_level', 'unknown')}",
            f"**Status:** {plan.get('status', 'draft')}",
            "",
            "## PREC Mapping",
            "",
        ]
        prec = plan.get("prec_mapping") or {}
        for stage in ["perceive", "reason", "economize", "crystallize"]:
            lines.append(f"- **{stage.title()}**: {prec.get(stage, 'not recorded')}")
        lines.extend(["", "## Allowed Files", ""])
        if files:
            lines.extend([f"- `{path}`" for path in files])
        else:
            lines.append("- No source files selected. This plan only writes BEAST metadata artifacts.")
        lines.extend(["", "## Planned Steps", ""])
        for step in steps:
            lines.append(f"{step.get('step', '?')}. **{step.get('action', 'action')}**: {step.get('detail', '')}")
        lines.extend([
            "",
            "## Apply Policy",
            "",
            "Patch 4 applies only explicit operations and writes a rollback snapshot before touching files.",
            "Generated default operations are BEAST metadata artifacts under `.beast/patch_plans/`.",
            "",
        ])
        return "\n".join(lines) + "\n"

    def _json_plan_text(self, plan: Dict[str, Any]) -> str:
        return json.dumps(plan, indent=2, default=str) + "\n"

    def _operation_content(self, operation: Dict[str, Any], plan: Dict[str, Any]) -> str:
        kind = str(operation.get("content_kind") or "")
        if kind == "markdown_summary":
            return self._plan_markdown(plan)
        if kind == "json_plan":
            # Avoid infinite recursion by storing a light copy without generated full content.
            light = dict(plan)
            light["operations"] = [
                {k: ("<content omitted>" if k == "content" else v) for k, v in dict(op).items()}
                for op in (plan.get("operations") or [])
            ]
            return json.dumps(light, indent=2, default=str) + "\n"
        return str(operation.get("content") or "")

    def _operation_selection(self, plan: Dict[str, Any], op_id: str, default: bool = True) -> bool:
        selected = plan.get("selected_operations")
        if isinstance(selected, list):
            return op_id in {str(x) for x in selected}
        return default

    def _normalized_operations(self, plan: Dict[str, Any], selected_only: bool = False) -> List[Dict[str, Any]]:
        operations = plan.get("operations")
        if not isinstance(operations, list) or not operations:
            plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
            operations = [
                {"op_id": "op_001", "op": "create_or_replace", "path": f".beast/patch_plans/{plan_id}.md", "content_kind": "markdown_summary", "beast_managed": True, "selected": True},
                {"op_id": "op_002", "op": "create_or_replace", "path": f".beast/patch_plans/{plan_id}.json", "content_kind": "json_plan", "beast_managed": True, "selected": True},
            ]
        normalized: List[Dict[str, Any]] = []
        allowed = set(str(x) for x in (plan.get("files_allowed") or []))
        for index, raw in enumerate(operations):
            if not isinstance(raw, dict):
                continue
            rel = str(raw.get("path") or "").strip()
            op = str(raw.get("op") or "create_or_replace").strip()
            op_id = str(raw.get("op_id") or f"op_{index+1:03d}")
            default_selected = bool(raw.get("selected", True))
            is_selected = self._operation_selection(plan, op_id, default=default_selected)
            if selected_only and not is_selected:
                continue
            if not rel or not self._is_safe_relative(rel):
                normalized.append({"ok": False, "op_id": op_id, "path": rel, "selected": is_selected, "error": "unsafe or empty path"})
                continue
            beast_managed = rel.startswith(".beast/")
            if not beast_managed and rel not in allowed:
                normalized.append({"ok": False, "op_id": op_id, "path": rel, "selected": is_selected, "error": "source path is outside selected/allowed context"})
                continue
            if op not in {"create_or_replace", "append"}:
                normalized.append({"ok": False, "op_id": op_id, "path": rel, "selected": is_selected, "error": f"unsupported operation {op}"})
                continue
            item = dict(raw)
            item["op_id"] = op_id
            item["op"] = op
            item["path"] = rel
            item["beast_managed"] = beast_managed
            item["source_edit"] = bool(item.get("source_edit") or not beast_managed)
            item["selected"] = is_selected
            item["content"] = self._operation_content(item, plan)
            item["ok"] = True
            normalized.append(item)
        return normalized

    def render_patch_diff(self, plan: Dict[str, Any]) -> ActionResult:
        """Render a unified diff preview for all patch operations."""
        root = self.workspace_root()
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        operations = self._normalized_operations(plan, selected_only=False)
        chunks: List[str] = []
        errors: List[str] = []
        op_rows: List[Dict[str, Any]] = []
        for op in operations:
            op_id = str(op.get("op_id") or "")
            rel = str(op.get("path") or "")
            op_rows.append({"op_id": op_id, "path": rel, "selected": bool(op.get("selected")), "source_edit": bool(op.get("source_edit")), "description": op.get("description", "")})
            if not op.get("ok"):
                errors.append(f"{rel}: {op.get('error')}")
                continue
            path = (root / rel).resolve()
            old = ""
            if path.exists() and path.is_file():
                try:
                    old = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    errors.append(f"{rel}: could not read existing file: {exc}")
                    continue
            if op.get("op") == "append":
                new = old + str(op.get("content") or "")
            else:
                new = str(op.get("content") or "")
            marker = "SELECTED" if op.get("selected") else "SKIPPED"
            header = f"\n# --- BEAST HUNK {op_id} [{marker}] {rel} ---\n"
            diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"a/{rel}", tofile=f"b/{rel}"))
            if not diff:
                diff = f"# No textual change for {rel}\n"
            chunks.append(header + diff)
        text = "\n".join(chunks).strip() + "\n"
        data = {"plan_id": plan_id, "diff": text, "operations": op_rows, "errors": errors, "operation_count": len([op for op in operations if op.get("ok")]), "selected_count": len([op for op in operations if op.get("ok") and op.get("selected")])}
        if errors:
            return ActionResult(False, "Patch diff preview", text[:900], data, error="; ".join(errors))
        return ActionResult(True, "Patch diff preview", f"diff ready for {data['operation_count']} operation(s); {data['selected_count']} selected", data)

    def verify_patch_plan(self, plan: Dict[str, Any]) -> ActionResult:
        """Run validation over selected operations before apply."""
        operations = self._normalized_operations(plan, selected_only=True)
        root = self.workspace_root()
        errors: List[str] = []
        verified: List[Dict[str, Any]] = []
        for op in operations:
            if not op.get("ok"):
                errors.append(f"{op.get('path')}: {op.get('error')}")
                continue
            rel = str(op.get("path"))
            content = str(op.get("content") or "")
            expected_hash = str(op.get("expected_hash") or "")
            target = (root / rel).resolve()
            if expected_hash and target.exists() and target.is_file() and not rel.startswith(".beast/"):
                current_hash = self._file_hash_path(target)
                if current_hash and current_hash != expected_hash:
                    errors.append(f"{rel}: current file hash changed since plan was created")
                    continue
            if rel.endswith(".json"):
                try:
                    json.loads(content)
                except Exception as exc:
                    errors.append(f"{rel}: invalid JSON content: {exc}")
                    continue
            if rel.endswith(".py"):
                try:
                    compile(content, rel, "exec")
                except Exception as exc:
                    errors.append(f"{rel}: Python syntax check failed: {exc}")
                    continue
            verified.append({"path": rel, "kind": "python" if rel.endswith(".py") else "json" if rel.endswith(".json") else "text", "ok": True})
        data = {"verified": verified, "errors": errors, "selected_count": len(operations)}
        if errors:
            return ActionResult(False, "Patch verification", "", data, error="; ".join(errors))
        return ActionResult(True, "Patch verification", f"{len(verified)} selected operation(s) verified", data)

    def _post_apply_verification(self, applied_paths: List[str], plan: Dict[str, Any]) -> Dict[str, Any]:
        root = self.workspace_root()
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        py_files = [p for p in applied_paths if p.endswith(".py")]
        for rel in py_files:
            target = root / rel
            cmd = [sys.executable, "-m", "py_compile", str(target)]
            try:
                proc = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, timeout=20)
                ok = proc.returncode == 0
                checks.append({"kind": "py_compile", "path": rel, "ok": ok, "stdout": proc.stdout[-1200:], "stderr": proc.stderr[-1200:]})
                if not ok:
                    errors.append(f"py_compile failed for {rel}: {proc.stderr[-500:]}")
            except Exception as exc:
                checks.append({"kind": "py_compile", "path": rel, "ok": False, "error": str(exc)})
                errors.append(f"py_compile error for {rel}: {exc}")
        apply_policy = plan.get("apply_policy") if isinstance(plan.get("apply_policy"), dict) else {}
        run_tests = bool(apply_policy.get("run_tests")) or os.environ.get("BEAST_PATCH_RUN_TESTS") == "1"
        if run_tests:
            try:
                test_cwd_raw = str(apply_policy.get("test_cwd") or plan.get("verification_cwd") or root)
                test_cwd = Path(test_cwd_raw).expanduser().resolve()
                if not test_cwd.exists() or not test_cwd.is_dir():
                    raise RuntimeError(f"pytest cwd does not exist: {test_cwd}")
                test_args = apply_policy.get("test_args")
                if not isinstance(test_args, list) or not all(isinstance(item, str) for item in test_args):
                    test_args = ["-q"]
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", *test_args],
                    cwd=str(test_cwd),
                    text=True,
                    capture_output=True,
                    timeout=int(os.environ.get("BEAST_PATCH_TEST_TIMEOUT", "60")),
                )
                ok = proc.returncode == 0
                checks.append({"kind": "pytest", "ok": ok, "cwd": str(test_cwd), "args": test_args, "stdout": proc.stdout[-2500:], "stderr": proc.stderr[-2500:]})
                if not ok:
                    errors.append(f"pytest failed in {test_cwd}")
            except Exception as exc:
                checks.append({"kind": "pytest", "ok": False, "error": str(exc)})
                errors.append(f"pytest error: {exc}")
        else:
            checks.append({"kind": "pytest", "ok": True, "skipped": True, "reason": "set BEAST_PATCH_RUN_TESTS=1 or plan.apply_policy.run_tests=true to run tests"})
        return {"ok": not errors, "checks": checks, "errors": errors}

    def _write_patch_chronicle(self, plan: Dict[str, Any], applied: List[str], rollback_path: str, verification: Dict[str, Any]) -> Dict[str, Any]:
        root = self.workspace_root()
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        chron_dir = root / ".beast" / "chronicle"
        chron_dir.mkdir(parents=True, exist_ok=True)
        evidence = plan.get("output_evidence") if isinstance(plan.get("output_evidence"), dict) else {}
        handoff = plan.get("provider_handoff") if isinstance(plan.get("provider_handoff"), dict) else {}
        profile = ((handoff.get("output") or {}).get("profile") or {}) if isinstance(handoff.get("output"), dict) else {}
        usage = evidence.get("usage") if isinstance(evidence.get("usage"), dict) else {}
        token_cost = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": (
                (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0))
                if usage else None
            ),
        }
        pytest_checks = [item for item in (verification.get("checks") or []) if isinstance(item, dict) and item.get("kind") == "pytest"]
        pytest_status = "skipped"
        if pytest_checks:
            pytest_status = "passed" if all(bool(item.get("ok")) for item in pytest_checks) else "failed"
        record = {
            "chronicle_id": f"chr_{plan_id}",
            "artifact_type": "patch_apply_crystallization",
            "task_id": plan_id,
            "objective": plan.get("objective"),
            "provider": plan.get("provider"),
            "provider_role": profile.get("role") or evidence.get("provider_role") or "",
            "provider_handoff_hash": plan.get("provider_handoff_hash") or (handoff.get("trace") or {}).get("provider_handoff_hash") or (handoff.get("trace") or {}).get("input_handoff_hash"),
            "canonicalized": bool(evidence.get("canonicalized")),
            "token_cost": token_cost,
            "latency_ms": evidence.get("latency_ms"),
            "validation_status": evidence.get("final_status") or "not_recorded",
            "pytest_status": pytest_status,
            "prec_stage": "crystallize",
            "status": "applied_verified_crystallized" if verification.get("ok") else "applied_with_verification_errors",
            "applied_files": applied,
            "rollback_path": rollback_path,
            "verification": verification,
            "output_evidence": evidence,
            "created_at": int(time.time()),
        }
        json_path = chron_dir / f"{plan_id}.json"
        md_path = chron_dir / f"{plan_id}.md"
        json_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        md_path.write_text("\n".join([
            f"# BEAST Chronicle: {plan_id}", "", f"Objective: {plan.get('objective')}", f"Provider: {plan.get('provider')}", f"Provider role: {record.get('provider_role')}", f"Canonicalized: {record.get('canonicalized')}", f"Latency ms: {record.get('latency_ms')}", f"Validation: {record.get('validation_status')}", f"Pytest: {record.get('pytest_status')}", "", "## Applied files", *[f"- `{p}`" for p in applied], "", f"Rollback: `{rollback_path}`", "", f"Verification OK: {verification.get('ok')}", "",
        ]), encoding="utf-8")
        return {"json_path": str(json_path), "md_path": str(md_path), "record": record}

    def _restore_rollback_state(self, root: Path, rollback: Dict[str, Any]) -> Dict[str, Any]:
        restored: List[str] = []
        deleted: List[str] = []
        for file_state in reversed(rollback.get("files", [])):
            rel = str(file_state.get("path") or "")
            if not self._is_safe_relative(rel):
                continue
            target = (root / rel).resolve()
            if file_state.get("existed"):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(file_state.get("content") or ""), encoding="utf-8")
                restored.append(rel)
            else:
                if target.exists() and target.is_file():
                    target.unlink()
                    deleted.append(rel)
        return {"restored": restored, "deleted": deleted}

    def apply_patch_plan(self, plan: Dict[str, Any], approved: bool = False) -> ActionResult:
        """Apply selected operations with validation, rollback, and Chronicle crystallization."""
        if not approved:
            return ActionResult(False, "Patch apply", "", error="approval_required")
        root = self.workspace_root()
        plan_id = str(plan.get("plan_id") or f"plan_{int(time.time())}")
        verification_pre = self.verify_patch_plan(plan)
        if not verification_pre.ok:
            return verification_pre
        operations = [op for op in self._normalized_operations(plan, selected_only=True) if op.get("ok")]
        if not operations:
            return ActionResult(False, "Patch apply", "", error="No selected operations to apply")
        rollback_dir = root / ".beast" / "rollback" / plan_id
        rollback_dir.mkdir(parents=True, exist_ok=True)
        rollback: Dict[str, Any] = {"plan_id": plan_id, "created_at": int(time.time()), "workspace": str(root), "files": []}
        applied: List[str] = []
        try:
            for op in operations:
                rel = str(op["path"])
                target = (root / rel).resolve()
                previous_exists = target.exists()
                previous_text = ""
                if previous_exists and target.is_file():
                    previous_text = target.read_text(encoding="utf-8", errors="replace")
                rollback["files"].append({"path": rel, "existed": previous_exists, "content": previous_text})
                target.parent.mkdir(parents=True, exist_ok=True)
                if op.get("op") == "append":
                    with target.open("a", encoding="utf-8") as handle:
                        handle.write(str(op.get("content") or ""))
                else:
                    target.write_text(str(op.get("content") or ""), encoding="utf-8")
                applied.append(rel)
            rollback_path = rollback_dir / "rollback.json"
            rollback_path.write_text(json.dumps(rollback, indent=2, default=str), encoding="utf-8")
            latest = root / ".beast" / "rollback" / "latest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text(json.dumps({"plan_id": plan_id, "rollback_path": str(rollback_path), "applied": applied}, indent=2), encoding="utf-8")
            verification_post = self._post_apply_verification(applied, plan)
            if not verification_post.get("ok"):
                restored = self._restore_rollback_state(root, rollback)
                return ActionResult(False, "Patch apply", "verification failed and rollback was performed", {"applied": applied, "verification": verification_post, "rollback": restored, "rollback_path": str(rollback_path)}, error="post-apply verification failed; rollback performed")
            chronicle = self._write_patch_chronicle(plan, applied, str(rollback_path), verification_post)
            saved = dict(plan)
            saved["status"] = "applied_verified_crystallized"
            saved["applied_at"] = int(time.time())
            saved["applied_files"] = applied
            saved["rollback_path"] = str(rollback_path)
            saved["verification"] = verification_post
            saved["chronicle"] = chronicle
            self.save_patch_plan(saved)
            return ActionResult(True, "Patch apply", f"applied {len(applied)} selected operation(s); verification passed; Chronicle crystallized", {"plan": saved, "applied": applied, "rollback_path": str(rollback_path), "verification": verification_post, "chronicle": chronicle})
        except Exception as exc:
            restored = self._restore_rollback_state(root, rollback)
            return ActionResult(False, "Patch apply", "", {"applied": applied, "rollback": restored}, error=str(exc))

    def rollback_last_patch(self) -> ActionResult:
        root = self.workspace_root()
        latest = root / ".beast" / "rollback" / "latest.json"
        if not latest.exists():
            return ActionResult(False, "Patch rollback", "", error="No rollback snapshot found")
        try:
            pointer = json.loads(latest.read_text(encoding="utf-8"))
            rollback_path = Path(str(pointer.get("rollback_path") or ""))
            if not rollback_path.exists():
                return ActionResult(False, "Patch rollback", "", error=f"Rollback file not found: {rollback_path}")
            rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
            restored = self._restore_rollback_state(root, rollback)
            latest.unlink(missing_ok=True)
            return ActionResult(True, "Patch rollback", f"restored {len(restored.get('restored', []))} file(s), deleted {len(restored.get('deleted', []))} created file(s)", {"rollback": rollback, **restored})
        except Exception as exc:
            return ActionResult(False, "Patch rollback", "", error=str(exc))

    async def litellm_sidecar_running(self) -> bool:
        """Return True only when the LiteLLM sidecar reports running.

        This prevents the TUI from feeling frozen when the default provider is
        litellm but the sidecar is intentionally off.
        """
        try:
            data = await self.get_json("/edgek/deploy/litellm-sidecar/state")
            health = data.get("health") if isinstance(data.get("health"), dict) else {}
            if bool(data.get("running")) or health.get("status_code") == 200:
                return True
        except Exception:
            pass
        if httpx is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get("http://127.0.0.1:4000/v1/models")
                return response.status_code < 500
        except Exception:
            return False

    def _extract_stream_delta(self, data: Dict[str, Any]) -> str:
        """Extract an OpenAI-compatible streaming token/delta from a chunk."""
        try:
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0] or {}
                delta = choice.get("delta") or {}
                if isinstance(delta, dict):
                    if delta.get("content"):
                        return str(delta.get("content"))
                    if delta.get("text"):
                        return str(delta.get("text"))
                msg = choice.get("message") or {}
                if isinstance(msg, dict) and msg.get("content"):
                    return str(msg.get("content"))
                if choice.get("text"):
                    return str(choice.get("text"))
            if data.get("content"):
                content = data.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("text"):
                            parts.append(str(item["text"]))
                    return "".join(parts)
            if data.get("delta"):
                return str(data.get("delta"))
            if data.get("text"):
                return str(data.get("text"))
        except Exception:
            return ""
        return ""

    def _chunk_text(self, text: str, size: int = 42) -> List[str]:
        """Split fallback text into small readable chunks for simulated streaming."""
        if not text:
            return []
        chunks: List[str] = []
        current = ""
        for token in re.split(r"(\s+)", text):
            if len(current) + len(token) > size and current:
                chunks.append(current)
                current = token
            else:
                current += token
        if current:
            chunks.append(current)
        return chunks

    def _chat_model_for_provider(self, provider: str, model: str = "") -> str:
        provider_id = str(provider or "").lower().replace("-", "_")
        if model and model != "beast-auto":
            return model
        if provider_id in {"litellm", "auto", "beast_auto"} and os.environ.get("BEAST_LITELLM_MODEL"):
            return os.environ["BEAST_LITELLM_MODEL"]
        if provider_id in {"litellm", "auto", "beast_auto"}:
            provider_id = "litellm"
        try:
            return ProviderAdapterRegistry().adapter_for(provider_id).plan_chat("beast-auto").model
        except Exception:
            pass
        if provider_id == "ollama":
            return os.environ.get("OLLAMA_SCOUT_MODEL", "llama3.2:3b")
        return model if model and model != "beast-auto" else "gpt-4o-mini"

    async def _scout_fallback_reply(self, user_text: str, insight: ActionResult, handoff: ActionResult, provider_error: str = "") -> str:
        try:
            scout = await self.post_json(
                "/edgek/ollama/scout",
                {
                    "task": user_text,
                    "use_ollama": True,
                    "context_limit": 6,
                    "tool_limit": 6,
                    "include_postgres_schema": False,
                    "include_github_context": False,
                    "include_forensic_context": True,
                },
            )
            contract = scout.get("decision_contract") if isinstance(scout.get("decision_contract"), dict) else {}
            packet = scout.get("packet") if isinstance(scout.get("packet"), dict) else {}
            analysis = packet.get("local_analysis") if isinstance(packet.get("local_analysis"), dict) else {}
            source = str(contract.get("source") or analysis.get("source") or "edgek_fallback")
            label = "Ollama scout" if source == "ollama" else "BEAST local scout"
            selected_tools = contract.get("selected_tools") or []
            relevant_files = contract.get("relevant_files") or []
            lines = [
                f"{label} engaged after the provider route did not complete.",
                "",
                f"Objective: {user_text}",
                f"Scout source: {source}",
                f"Risk: {contract.get('risk', 'unknown')}  Cloud handoff: {contract.get('cloud_handoff', 'unknown')}",
                f"Selected tools: {', '.join(str(x) for x in selected_tools[:5]) or 'none'}",
                f"Relevant files: {', '.join(str(x) for x in relevant_files[:5]) or 'none'}",
            ]
            summary = analysis.get("summary")
            if summary:
                lines.extend(["", str(summary)])
            if provider_error:
                lines.extend(["", f"Provider route note: {provider_error[:220]}"])
            lines.extend([
                "",
                "Safe next move:",
                "1. Use /diagnose litellm to inspect the provider lane.",
                "2. Use /context to attach files before asking for source edits.",
                "3. Use /plan or /patch when you want an approval-gated edit plan.",
            ])
            return "\n".join(lines)
        except Exception:
            return self._local_beast_reply(user_text, insight, handoff, provider_error)

    async def stream_chat_completion(self, provider: str, messages: List[Dict[str, str]], model: str = "beast-auto", context_files: Optional[List[str]] = None) -> AsyncIterator[Dict[str, Any]]:
        """Stream a governed provider turn through BEAST's proxy lane.

        This expects OpenAI-compatible SSE (`data: {...}` / `data: [DONE]`).
        If the backend returns a single JSON object instead of SSE, the method
        still extracts and yields the complete assistant text as one streamed
        chunk.
        """
        if httpx is None:
            yield {"type": "error", "error": "httpx is not installed"}
            return

        payload = {
            "model": self._chat_model_for_provider(provider, model),
            "messages": messages,
            "stream": True,
            "max_tokens": 1200,
            "temperature": 0.2,
            "metadata": {"edgek_surface": "beast_tui_live_session_stream", "context_files": context_files or []},
        }
        token_count = 0
        raw_chunks: List[str] = []
        saw_done = False
        finish_reason = ""
        try:
            timeout = httpx.Timeout(connect=10.0, read=provider_stream_read_timeout(provider), write=20.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/proxy/v1/chat/completions",
                    params={"provider": provider or "litellm"},
                    headers={"X-EdgeK-Provider": provider or "litellm"},
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        yield {"type": "error", "error": body.decode("utf-8", errors="replace")[:1200]}
                        return
                    content_type = response.headers.get("content-type", "")
                    if "text/event-stream" not in content_type:
                        body = await response.aread()
                        text = body.decode("utf-8", errors="replace")
                        try:
                            data = json.loads(text)
                        except Exception:
                            data = {}
                        if isinstance(data, dict) and data.get("error"):
                            yield {"type": "error", "error": json.dumps(data.get("error"), default=str)[:1200]}
                            return
                        delta = self._extract_stream_delta(data) if isinstance(data, dict) else ""
                        if delta:
                            token_count += 1
                            yield {"type": "token", "text": delta}
                            yield {"type": "provider_done", "tokens": token_count, "raw_chunks": 1, "completed": True, "finish_reason": "non_stream_response"}
                            return
                        yield {"type": "error", "error": text[:1200]}
                        return

                    async for line in response.aiter_lines():
                        if line is None:
                            continue
                        line = line.strip()
                        if not line:
                            continue
                        raw_chunks.append(line)
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line in {"[DONE]", "data: [DONE]"}:
                            saw_done = True
                            break
                        try:
                            data = json.loads(line)
                        except Exception:
                            # Some local shims emit plain text lines. Treat them as chunks.
                            if not line.startswith(":"):
                                token_count += 1
                                yield {"type": "token", "text": line}
                            continue
                        delta = self._extract_stream_delta(data)
                        if delta:
                            token_count += 1
                            yield {"type": "token", "text": delta}
                        # Forward tool-like metadata if present without making the UI wait.
                        if data.get("tool_events"):
                            for item in data.get("tool_events") or []:
                                yield {"type": "tool", "text": str(item)}
                        choices = data.get("choices") if isinstance(data, dict) else None
                        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                            reason = choices[0].get("finish_reason")
                            if reason:
                                finish_reason = str(reason)
            completed = bool(saw_done or finish_reason)
            if completed:
                yield {"type": "provider_done", "tokens": token_count, "raw_chunks": len(raw_chunks), "completed": True, "finish_reason": finish_reason or "done"}
            else:
                yield {"type": "error", **classify_stream_failure("provider stream closed before a completion marker"), "tokens": token_count}
        except Exception as exc:
            yield {"type": "error", **classify_stream_failure(exc), "tokens": token_count}

    async def stream_live_turn(self, text: str, history: List[Dict[str, str]], provider: str = "litellm", lifecycle_id: str = "", context_files: Optional[List[str]] = None, model: str = "beast-auto") -> AsyncIterator[Dict[str, Any]]:
        """Streaming version of live_turn.

        It streams BEAST stage/tool events separately from assistant text, then
        streams provider tokens when possible. If provider streaming fails, it
        streams a local scout fallback in small chunks so the TUI remains alive.
        """
        text = text.strip()
        if not text:
            yield {"type": "error", "error": "empty prompt"}
            return

        if text.startswith("/"):
            result = await self._slash_command(text, provider, lifecycle_id)
            body = result.brief(2400)
            for chunk in self._chunk_text(body):
                yield {"type": "token", "text": chunk}
                await asyncio.sleep(0.01)
            yield {"type": "done", "ok": result.ok, "tool_events": []}
            return

        tool_events: List[str] = []
        context_files = context_files or []
        context_records = self.read_context_files(context_files) if context_files else []
        current_task = self._current_task(text)
        if context_records:
            current_task["selected_context"] = [
                {"path": r.get("path"), "ok": r.get("ok"), "line_count": r.get("line_count"), "truncated": r.get("truncated")}
                for r in context_records
            ]

        yield {"type": "stage", "text": "PREC perceive"}
        if lifecycle_id:
            await self.update_prec(lifecycle_id, "perceive", f"User requested: {text[:180]}", "completed", signals=["live_user_turn"])
            tool_events.append("PREC perceive recorded")
            yield {"type": "tool", "text": "PREC perceive recorded"}

        envelope = await self.build_task_envelope(text, provider)
        event = "task envelope: " + ("ok" if envelope.ok else "error")
        tool_events.append(event)
        yield {"type": "tool", "text": event}

        context_event = "context files: " + str(len([r for r in context_records if r.get("ok")]))
        tool_events.append(context_event)
        yield {"type": "tool", "text": context_event}

        yield {"type": "stage", "text": "PREC reason"}
        insight = await self.compile_insight(text, provider, current_task=current_task)
        event = "insight compile: " + ("ok" if insight.ok else "error")
        tool_events.append(event)
        yield {"type": "tool", "text": event}
        if lifecycle_id:
            await self.update_prec(lifecycle_id, "reason", "Compiled ranked local insight for live session turn.", "completed", artifacts={"insight": insight.data if insight.ok else insight.error}, signals=["insight_compiler"])

        yield {"type": "stage", "text": "PREC economize"}
        handoff = await self.prepare_handoff(text, provider)
        ready = bool(handoff.data.get("ready"))
        event = "handoff precheck: " + ("ready" if ready else "not ready")
        tool_events.append(event)
        yield {"type": "tool", "text": event}
        if lifecycle_id:
            await self.update_prec(lifecycle_id, "economize", "Prepared bounded context/handoff packet for provider turn.", "completed" if ready else "active", artifacts={"handoff": handoff.data if handoff.ok else handoff.error}, signals=["handoff_precheck"])

        context_message = ""
        if context_records:
            snippets = []
            for rec in context_records[:6]:
                if rec.get("ok"):
                    snippets.append(f"### {rec.get('path')}\n{str(rec.get('preview') or '')[:2400]}")
            context_message = "\n\n".join(snippets)

        chat_history = history[-12:]
        if context_message:
            chat_history = chat_history + [{"role": "system", "content": "Selected BEAST workspace context follows. Stay within this scope unless the user expands it.\n" + context_message}]
        chat_history = chat_history + [{"role": "user", "content": text}]

        provider_error = ""
        provider_ok = False
        provider_completed = False
        provider_failure: Dict[str, Any] = {}
        stream_started = time.perf_counter()
        assistant_parts: List[str] = []

        skip_provider = False
        if str(provider or "").lower() in {"litellm", "auto", "beast-auto"}:
            if not await self.litellm_sidecar_running():
                skip_provider = True
                provider_error = "LiteLLM sidecar is OFF, so BEAST skipped the provider route and used local scout fallback."
                yield {"type": "tool", "text": provider_error}

        if not skip_provider:
            yield {"type": "stage", "text": f"stream provider: {provider or 'litellm'}"}
            async for event in self.stream_chat_completion(provider, chat_history, model=model, context_files=context_files):
                if event.get("type") == "token":
                    provider_ok = True
                    assistant_parts.append(str(event.get("text") or ""))
                    yield event
                elif event.get("type") == "tool":
                    tool_events.append(str(event.get("text") or ""))
                    yield event
                elif event.get("type") == "error":
                    provider_error = str(event.get("error") or "")
                    provider_failure = dict(event)
                    yield {"type": "tool", "text": "provider stream error: " + provider_error[:240]}
                elif event.get("type") == "provider_done":
                    provider_completed = bool(event.get("completed"))
                    yield event

        if not provider_completed:
            yield {"type": "stage", "text": "local scout fallback" if not provider_ok else "local scout continuation"}
            fallback = await self._scout_fallback_reply(text, insight, handoff, provider_error)
            if provider_ok:
                separator = "\n\n[Provider stream ended early. BEAST preserved the partial response and continued locally.]\n\n"
                assistant_parts.append(separator)
                yield {"type": "token", "text": separator}
            for chunk in self._chunk_text(fallback):
                assistant_parts.append(chunk)
                yield {"type": "token", "text": chunk}
                await asyncio.sleep(0.012)
            tool_events.append("provider route: local fallback" if not provider_ok else "provider route: partial response recovered locally")
        else:
            tool_events.append("provider route: streaming ok")

        evidence_outcome = "success" if provider_completed else "recovered" if assistant_parts else "failure"
        evidence_recorded = await self.record_outcome_evidence({
            "capability_id": f"provider:{provider or 'litellm'}",
            "task_class": "chat_completion",
            "outcome": evidence_outcome,
            "failure_category": str(provider_failure.get("kind") or "provider_stream_incomplete") if not provider_completed else "",
            "failure_code": str(provider_failure.get("status_code") or "") if not provider_completed else "",
            "detail": provider_error[:500],
            "scope": {
                "provider": str(provider or "litellm"),
                "model": self._chat_model_for_provider(provider, model),
                "route": "tui_live_stream",
            },
            "retries": int(bool(provider_failure)),
            "repair_depth": int(not provider_completed),
            "latency_ms": round((time.perf_counter() - stream_started) * 1000.0, 3),
            "selected_capabilities": [f"provider:{provider or 'litellm'}"],
        })
        tool_events.append("crystal outcome evidence: " + ("recorded" if evidence_recorded else "deferred"))

        if lifecycle_id:
            yield {"type": "stage", "text": "PREC crystallize"}
            await self.update_prec(lifecycle_id, "crystallize", "Streaming live session turn completed; outcome returned to operator.", "completed", artifacts={"provider_ok": provider_ok, "provider_completed": provider_completed, "provider_recovered": bool(provider_failure), "tool_events": tool_events}, signals=["live_turn_stream_complete"])

        yield {
            "type": "done",
            "ok": True,
            "assistant_text": "".join(assistant_parts),
            "tool_events": tool_events,
            "lifecycle_id": lifecycle_id,
            "data": {
                "envelope": envelope.data,
                "insight": insight.data,
                "handoff": handoff.data,
                "provider_error": provider_error,
                "provider_streaming": provider_ok,
                "provider_completed": provider_completed,
                "provider_recovered": bool(provider_failure),
                "heal_recommended": bool(provider_failure.get("local_service_failure")),
            },
        }

    async def chat_completion(self, provider: str, messages: List[Dict[str, str]], model: str = "beast-auto", context_files: Optional[List[str]] = None) -> ActionResult:
        """Attempt a governed provider turn through BEAST's proxy lane."""
        if httpx is None:
            return ActionResult(False, "Provider chat", "", error="httpx is not installed")
        payload = {
            "model": self._chat_model_for_provider(provider, model),
            "messages": messages,
            "stream": False,
            "max_tokens": 1200,
            "temperature": 0.2,
            "metadata": {"edgek_surface": "beast_tui_live_session", "context_files": context_files or []},
        }
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout, 5.0)) as client:
                response = await client.post(
                    f"{self.base_url}/proxy/v1/chat/completions",
                    params={"provider": provider or "litellm"},
                    headers={"X-EdgeK-Provider": provider or "litellm"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            return ActionResult(True, "Provider chat", "provider response received", data if isinstance(data, dict) else {"response": data})
        except Exception as exc:
            return ActionResult(False, "Provider chat", "", error=str(exc))

    async def live_turn(self, text: str, history: List[Dict[str, str]], provider: str = "litellm", lifecycle_id: str = "", context_files: Optional[List[str]] = None, model: str = "beast-auto") -> LiveTurnResult:
        """Run one Claude-Code-like BEAST live session turn.

        The turn is useful even without provider credentials: it still compiles local
        insight, prepares handoff, updates PREC, and returns a deterministic local
        BEAST response when the provider route is unavailable.
        """
        text = text.strip()
        if not text:
            return LiveTurnResult(False, "Live turn", "", error="empty prompt")

        if text.startswith("/"):
            return await self._slash_command(text, provider, lifecycle_id)

        tool_events: List[str] = []
        context_files = context_files or []
        context_records = self.read_context_files(context_files) if context_files else []
        current_task = self._current_task(text)
        if context_records:
            current_task["selected_context"] = [{"path": r.get("path"), "ok": r.get("ok"), "line_count": r.get("line_count"), "truncated": r.get("truncated")} for r in context_records]

        if lifecycle_id:
            await self.update_prec(lifecycle_id, "perceive", f"User requested: {text[:180]}", "completed", signals=["live_user_turn"])
            tool_events.append("PREC perceive recorded")

        envelope = await self.build_task_envelope(text, provider)
        tool_events.append("context files: " + str(len([r for r in context_records if r.get("ok")])) )
        tool_events.append("task envelope: " + ("ok" if envelope.ok else "error"))

        insight = await self.compile_insight(text, provider, current_task=current_task)
        tool_events.append("insight compile: " + ("ok" if insight.ok else "error"))
        if lifecycle_id:
            await self.update_prec(lifecycle_id, "reason", "Compiled ranked local insight for live session turn.", "completed", artifacts={"insight": insight.data if insight.ok else insight.error}, signals=["insight_compiler"])

        handoff = await self.prepare_handoff(text, provider)
        tool_events.append("handoff precheck: " + ("ready" if handoff.data.get("ready") else "not ready"))
        if lifecycle_id:
            await self.update_prec(lifecycle_id, "economize", "Prepared bounded context/handoff packet for provider turn.", "completed" if handoff.data.get("ready") else "active", artifacts={"handoff": handoff.data if handoff.ok else handoff.error}, signals=["handoff_precheck"])

        context_message = ""
        if context_records:
            snippets = []
            for rec in context_records[:6]:
                if rec.get("ok"):
                    snippets.append(f"### {rec.get('path')}\n{str(rec.get('preview') or "")[:2400]}")
            context_message = "\n\n".join(snippets)
        chat_history = history[-12:]
        if context_message:
            chat_history = chat_history + [{"role": "system", "content": "Selected BEAST workspace context follows. Stay within this scope unless the user expands it.\n" + context_message}]
        chat_history = chat_history + [{"role": "user", "content": text}]
        skip_provider = False
        provider_result = ActionResult(False, "Provider chat", "", error="")
        if str(provider or "").lower() in {"litellm", "auto", "beast-auto"}:
            if not await self.litellm_sidecar_running():
                skip_provider = True
                provider_result = ActionResult(False, "Provider chat", "", error="LiteLLM sidecar is OFF, so BEAST skipped the provider route and used local scout fallback.")
        if not skip_provider:
            provider_result = await self.chat_completion(provider, chat_history, model=model, context_files=context_files)
        if provider_result.ok:
            assistant_text = self._extract_assistant_text(provider_result.data)
            if not assistant_text:
                assistant_text = self._local_beast_reply(text, insight, handoff, provider_result.error)
            tool_events.append("provider route: ok")
        else:
            assistant_text = await self._scout_fallback_reply(text, insight, handoff, provider_result.error)
            tool_events.append("provider route: local fallback")

        if lifecycle_id:
            await self.update_prec(lifecycle_id, "crystallize", "Live session turn completed; outcome returned to operator.", "completed", artifacts={"provider_ok": provider_result.ok, "tool_events": tool_events}, signals=["live_turn_complete"])

        return LiveTurnResult(
            ok=True,
            title="Live turn",
            summary="BEAST live turn complete",
            data={"envelope": envelope.data, "insight": insight.data, "handoff": handoff.data, "provider": provider_result.data, "provider_error": provider_result.error},
            assistant_text=assistant_text,
            tool_events=tool_events,
            lifecycle_id=lifecycle_id,
        )

    async def _slash_command(self, text: str, provider: str, lifecycle_id: str = "") -> LiveTurnResult:
        parts = text.split()
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else provider
        tool_events: List[str] = []
        result: ActionResult
        if command in {"/help", "/?"}:
            assistant = "BEAST live commands: /provider <id>, /diagnose <provider>, /handoff <objective>, /quality <objective>, /prec, /deploy, /nginx, /litellm, /capabilities, /context, /plan, /clear. Normal messages run the full PREC → insight → handoff → provider turn loop."
            return LiveTurnResult(True, "Live help", "help", assistant_text=assistant, tool_events=["local command help"], lifecycle_id=lifecycle_id)
        if command == "/provider":
            assistant = f"Provider route set request noted: {arg}. Use the provider selector in the next patch; this turn will report the target."
            return LiveTurnResult(True, "Provider select", arg, assistant_text=assistant, tool_events=[f"provider target: {arg}"], lifecycle_id=lifecycle_id)
        if command == "/diagnose":
            result = await self.provider_diagnostic(arg)
            tool_events.append(f"provider diagnostic {arg}: {'ok' if result.ok else 'error'}")
        elif command == "/route":
            result = await self.provider_route_card(arg)
            tool_events.append(f"route card {arg}: {'ok' if result.ok else 'error'}")
        elif command == "/handoff":
            objective = text.partition(" ")[2] or "Prepare governed live session handoff"
            result = await self.prepare_handoff(objective, provider)
            tool_events.append("handoff: " + ("ready" if result.data.get("ready") else "not ready"))
        elif command == "/quality":
            objective = text.partition(" ")[2] or "Run BEAST quality cascade"
            result = await self.quality_cascade(objective, provider)
            tool_events.append("quality cascade: " + ("ok" if result.ok else "error"))
        elif command == "/prec":
            result = await self.action("PREC state", "/edgek/prec/state", method="GET")
            tool_events.append("PREC state fetched")
        elif command == "/deploy":
            result = await self.write_deploy_configs()
            tool_events.append("deployment configs written")
        elif command == "/nginx":
            result = await self.nginx_apply(approved=False, dry_run=True)
            tool_events.append("nginx dry-run executed")
        elif command == "/litellm":
            result = await self.litellm_start(approved=False, dry_run=True)
            tool_events.append("litellm start dry-run executed")
        elif command == "/capabilities":
            result = await self.action("Capabilities", "/edgek/capabilities", method="GET")
            tool_events.append("capabilities fetched")
        elif command == "/context":
            files = self.workspace_file_candidates(limit=20)
            return LiveTurnResult(True, "Context files", f"{len(files)} candidates", {"files": files}, assistant_text="Top BEAST context candidates:\n" + "\n".join(f"- {f.get('path')} ({f.get('size')} bytes)" for f in files[:15]), tool_events=["workspace context candidates listed"], lifecycle_id=lifecycle_id)
        elif command == "/plan":
            objective = text.partition(" ")[2] or "Prepare a governed workspace edit plan"
            result = self.build_patch_plan(objective, [], provider=provider)
            tool_events.append("local patch plan prepared")
        else:
            assistant = f"Unknown BEAST slash command: {command}. Try /help."
            return LiveTurnResult(False, "Slash command", "", error=assistant, assistant_text=assistant, tool_events=["unknown slash command"], lifecycle_id=lifecycle_id)
        assistant = self._command_reply(result)
        return LiveTurnResult(result.ok, result.title, result.summary, result.data, result.error, assistant, tool_events, lifecycle_id)

    def _current_task(self, objective: str) -> Dict[str, Any]:
        return {
            "objective": objective,
            "scope": "BEAST live coding session",
            "constraints": ["local first", "governed tool use", "no secret capture", "approval before writes"],
            "success_criteria": ["ranked local insight exists", "safe next action identified", "tool outcomes visible", "PREC state updated"],
            "source": "beast_tui_live_session",
        }

    def _summarize(self, data: Dict[str, Any]) -> str:
        for key in ("summary", "message", "status", "mode", "decision", "reason"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)[:500]
        if "ready" in data:
            return "ready" if data.get("ready") else str(data.get("reason") or "not ready")
        if "capabilities" in data and isinstance(data["capabilities"], list):
            return f"{len(data['capabilities'])} capabilities"
        if "providers" in data:
            providers = data.get("providers")
            return f"{len(providers) if isinstance(providers, list) else 'provider'} records"
        return "action complete"

    def _extract_assistant_text(self, data: Dict[str, Any]) -> str:
        try:
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                if isinstance(msg, dict) and msg.get("content"):
                    return str(msg.get("content"))
                if choices[0].get("text"):
                    return str(choices[0].get("text"))
            if data.get("content"):
                content = data.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("text"):
                            parts.append(str(item["text"]))
                    return "\n".join(parts)
        except Exception:
            return ""
        return ""

    def _local_beast_reply(self, user_text: str, insight: ActionResult, handoff: ActionResult, provider_error: str = "") -> str:
        evidence = []
        if isinstance(insight.data, dict):
            evidence = insight.data.get("evidence") or insight.data.get("ranked_evidence") or []
        ready = bool(handoff.data.get("ready")) if isinstance(handoff.data, dict) else False
        lines = [
            "BEAST local scout engaged. The provider route did not complete, so I stayed local-first and still ran the governance loop.",
            "",
            f"Objective: {user_text}",
            f"Insight evidence records: {len(evidence) if isinstance(evidence, list) else 0}",
            f"Handoff precheck: {'ready' if ready else 'not ready'}",
        ]
        if provider_error:
            lines.append(f"Provider route note: {provider_error[:220]}")
        lines.extend([
            "",
            "Safe next move:",
            "1. Inspect the relevant capability/provider route.",
            "2. Run the diagnostic or quality cascade before making edits.",
            "3. Approve any write/apply action explicitly.",
            "",
            "Try /diagnose <provider>, /handoff <objective>, /quality <objective>, /prec, /nginx, or /litellm.",
        ])
        return "\n".join(lines)

    def _command_reply(self, result: ActionResult) -> str:
        status = "OK" if result.ok else "ERROR"
        lines = [f"{result.title} [{status}]", result.brief(1200)]
        if result.data:
            keys = ", ".join(list(result.data.keys())[:8])
            lines.append(f"Returned fields: {keys}")
        return "\n".join(line for line in lines if line)
