"""Persistent provider quality telemetry for BEAST planner routing."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ProviderQualityLedger:
    """Tiny workspace-local success/failure ledger used to tune route scores."""

    def __init__(self, workspace_root: str | Path, *, path: str | Path | None = None, max_events: int = 1000) -> None:
        root = Path(workspace_root)
        self.path = Path(path) if path is not None else root / ".beast" / "agent_runs" / "provider_quality.json"
        self.max_events = max(20, int(max_events))

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def task_type(run: dict[str, Any]) -> str:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        if failures:
            latest = failures[-1] if isinstance(failures[-1], dict) else {}
            analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
            failure_class = str(analysis.get("failure_class") or "unknown")
            return f"repair:{failure_class}"
        if str(run.get("mode") or "").strip().lower() in {"agent", "edit", "implementer"}:
            context_files = request.get("context_files") if isinstance(request.get("context_files"), list) else []
            objective = str(run.get("objective") or "").casefold()
            if len(context_files) >= 4 or any(term in objective for term in ("monorepo", "architecture", "large", "cross-cutting", "refactor")):
                return "hard_edit"
            return "bounded_edit"
        return "analysis"

    def record(
        self,
        provider: str,
        task_type: str,
        *,
        ok: bool,
        latency_ms: float | int | None = None,
        failure_class: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        provider = str(provider or "unknown").strip() or "unknown"
        task_type = str(task_type or "general").strip() or "general"
        payload = self._read()
        events = payload.get("events") if isinstance(payload.get("events"), list) else []
        event = {
            "provider": provider,
            "task_type": task_type,
            "ok": bool(ok),
            "latency_ms": float(latency_ms) if isinstance(latency_ms, (int, float)) else None,
            "failure_class": str(failure_class or "")[:80],
            "reason": str(reason or "")[:240],
            "recorded_at": time.time(),
        }
        events.append(event)
        payload["events"] = events[-self.max_events :]
        payload["version"] = 1
        self._write(payload)
        return event

    def score(self, provider: str, task_type: str = "general") -> float:
        provider = str(provider or "unknown").strip() or "unknown"
        task_type = str(task_type or "general").strip() or "general"
        events = self._read().get("events")
        if not isinstance(events, list):
            return 0.5
        relevant = [
            item for item in events
            if isinstance(item, dict)
            and str(item.get("provider") or "") == provider
            and str(item.get("task_type") or "") in {task_type, "general"}
        ][-80:]
        if not relevant:
            return 0.5
        successes = sum(1 for item in relevant if item.get("ok") is True)
        failures = len(relevant) - successes
        success_rate = (successes + 1.0) / (successes + failures + 2.0)
        latencies = [
            float(item.get("latency_ms"))
            for item in relevant
            if isinstance(item.get("latency_ms"), (int, float)) and float(item.get("latency_ms")) >= 0
        ]
        if latencies:
            avg_latency = sum(latencies[-20:]) / len(latencies[-20:])
            latency_score = max(0.0, min(1.0, 1.0 - (avg_latency / 60000.0)))
        else:
            latency_score = 0.5
        sample_confidence = min(1.0, len(relevant) / 20.0)
        raw = (success_rate * 0.78) + (latency_score * 0.22)
        return max(0.05, min(0.98, (raw * sample_confidence) + (0.5 * (1.0 - sample_confidence))))

    def summary(self) -> dict[str, Any]:
        events = self._read().get("events")
        rows: dict[str, dict[str, Any]] = {}
        for item in events if isinstance(events, list) else []:
            if not isinstance(item, dict):
                continue
            key = f"{item.get('provider') or 'unknown'}::{item.get('task_type') or 'general'}"
            row = rows.setdefault(key, {"provider": item.get("provider") or "unknown", "task_type": item.get("task_type") or "general", "successes": 0, "failures": 0, "score": 0.5})
            if item.get("ok") is True:
                row["successes"] += 1
            else:
                row["failures"] += 1
        for row in rows.values():
            row["score"] = self.score(str(row["provider"]), str(row["task_type"]))
        return {"ok": True, "providers": sorted(rows.values(), key=lambda item: (str(item["provider"]), str(item["task_type"])))}
