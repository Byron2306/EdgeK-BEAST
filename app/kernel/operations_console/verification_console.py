"""Phase 5.10 verification console projection.

Projects durable verification evidence into a canonical, operator-facing,
read-only console without parsing transient terminal output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.kernel.agents.run_store import AgentRunStore

VERSION = "5.10"
OBJECT_TYPE = "beast_verification_console"
STATUSES = {"PASSED", "FAILED", "TIMED_OUT", "SKIPPED", "REUSED_WITH_PROOF", "STALE", "BLOCKED", "RUNNING", "UNKNOWN"}
CATEGORIES = {
    "focused_tests", "package_tests", "lint", "type_check", "security",
    "policy", "sourceplan_validation", "post_apply_verification", "other",
}
FRESHNESS = {"fresh", "reused", "stale", "unknown"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _status(payload: dict[str, Any], event_type: str) -> str:
    raw = str(payload.get("status") or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PASS": "PASSED", "SUCCESS": "PASSED", "OK": "PASSED", "GREEN": "PASSED",
        "FAIL": "FAILED", "ERROR": "FAILED", "RED": "FAILED",
        "TIMEOUT": "TIMED_OUT", "TIMEDOUT": "TIMED_OUT",
        "REUSED": "REUSED_WITH_PROOF", "REUSE": "REUSED_WITH_PROOF",
        "PENDING": "RUNNING", "STARTED": "RUNNING", "ACTIVE": "RUNNING",
    }
    raw = aliases.get(raw, raw)
    if raw in STATUSES:
        return raw
    if payload.get("ok") is True:
        return "PASSED"
    if payload.get("ok") is False:
        return "FAILED"
    lowered = event_type.lower()
    if "timeout" in lowered:
        return "TIMED_OUT"
    if any(token in lowered for token in ("failed", "failure", "error")):
        return "FAILED"
    if any(token in lowered for token in ("passed", "success", "completed")):
        return "PASSED"
    if any(token in lowered for token in ("started", "running")):
        return "RUNNING"
    return "UNKNOWN"


def _category(event_type: str, payload: dict[str, Any]) -> str:
    raw = str(payload.get("category") or payload.get("check_type") or "").strip().lower().replace("-", "_")
    aliases = {
        "test": "focused_tests", "tests": "focused_tests", "focused": "focused_tests",
        "package": "package_tests", "suite": "package_tests", "typecheck": "type_check",
        "typechecking": "type_check", "sourceplan": "sourceplan_validation",
        "post_apply": "post_apply_verification",
    }
    raw = aliases.get(raw, raw)
    if raw in CATEGORIES:
        return raw
    text = event_type.lower()
    if "post_apply" in text or "post-apply" in text:
        return "post_apply_verification"
    if "sourceplan" in text or "source_plan" in text:
        return "sourceplan_validation"
    if "security" in text or "scan" in text:
        return "security"
    if "policy" in text or "governance" in text:
        return "policy"
    if "typecheck" in text or "type_check" in text or "mypy" in text or "pyright" in text:
        return "type_check"
    if "lint" in text or "ruff" in text or "eslint" in text:
        return "lint"
    if "package" in text or "suite" in text or "regression" in text:
        return "package_tests"
    if "test" in text or "verify" in text:
        return "focused_tests"
    return "other"


def _freshness(payload: dict[str, Any], status: str) -> str:
    raw = str(payload.get("freshness") or "").lower().strip()
    if raw in FRESHNESS:
        return raw
    if status == "REUSED_WITH_PROOF" or payload.get("reused") is True:
        return "reused"
    if status == "STALE" or payload.get("stale") is True:
        return "stale"
    if payload.get("fresh") is True:
        return "fresh"
    return "unknown"


class VerificationConsole:
    """Builds a deterministic verification workspace for one durable run."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store = AgentRunStore(self.workspace_root)

    def build(self, run_id: str, *, category: str = "", status: str = "", query: str = "", limit: int = 250) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        category = category.strip().lower()
        status = status.strip().upper().replace("-", "_")
        if category and category not in CATEGORIES:
            raise ValueError(f"unsupported verification category: {category}")
        if status and status not in STATUSES:
            raise ValueError(f"unsupported verification status: {status}")
        limit = max(1, min(int(limit), 1000))

        checks = self._collect(run_id, run)
        total = len(checks)
        needle = query.strip().lower()
        if category:
            checks = [item for item in checks if item["category"] == category]
        if status:
            checks = [item for item in checks if item["status"] == status]
        if needle:
            checks = [item for item in checks if needle in json.dumps(item, sort_keys=True, default=str).lower()]
        checks = checks[-limit:]

        counts = {name: sum(1 for item in self._collect(run_id, run) if item["status"] == name) for name in STATUSES}
        category_counts = {name: sum(1 for item in self._collect(run_id, run) if item["category"] == name) for name in CATEGORIES}
        current_status = self._current_status(self._collect(run_id, run))
        promotion_blockers = [item["check_id"] for item in self._collect(run_id, run) if item["promotion_relevant"] and item["status"] not in {"PASSED", "REUSED_WITH_PROOF", "SKIPPED"}]
        console = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "run_state": str(run.get("state") or ""),
            "status": current_status,
            "summary": {
                "total_checks": total,
                "visible_checks": len(checks),
                "counts": counts,
                "category_counts": category_counts,
                "fresh_count": sum(1 for item in self._collect(run_id, run) if item["freshness"] == "fresh"),
                "reused_with_proof_count": counts["REUSED_WITH_PROOF"],
                "stale_count": counts["STALE"],
            },
            "promotion": {
                "verification_ready": not promotion_blockers and total > 0,
                "promotion_authorized": False,
                "blocking_check_ids": promotion_blockers,
            },
            "filters": {"category": category, "status": status, "query": query, "limit": limit},
            "checks": checks,
            "authority": "verification_console_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        console["console_digest"] = _digest(console)
        return console

    def verify(self, console: dict[str, Any]) -> bool:
        if console.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(console.get("console_digest") or "")
        semantic = dict(console)
        semantic.pop("console_digest", None)
        return claimed == _digest(semantic)

    def _collect(self, run_id: str, run: dict[str, Any]) -> list[dict[str, Any]]:
        events = self.store.events(run_id, after=0, limit=100_000)
        checkpoint = _dict(run.get("checkpoint"))
        candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            payload = _dict(event.get("payload"))
            if any(token in event_type.lower() for token in ("verify", "test", "lint", "typecheck", "type_check", "security", "policy", "sourceplan", "post_apply")) or payload.get("check_type"):
                candidates.append((event_type, payload, event))
        current = _dict(checkpoint.get("verification"))
        for index, item in enumerate(_list(current.get("items"))):
            payload = _dict(item)
            candidates.append((str(payload.get("event_type") or "checkpoint.verification"), payload, {"event_id": f"checkpoint:{index}", "sequence": payload.get("sequence"), "created_at": payload.get("created_at")}))

        seen: set[str] = set()
        checks: list[dict[str, Any]] = []
        for event_type, payload, event in candidates:
            identity = str(payload.get("check_id") or payload.get("receipt_id") or event.get("event_id") or _digest({"event_type": event_type, "payload": payload}))
            if identity in seen:
                continue
            seen.add(identity)
            status = _status(payload, event_type)
            category = _category(event_type, payload)
            stdout = str(payload.get("stdout") or payload.get("output") or "")
            stderr = str(payload.get("stderr") or payload.get("error") or "")
            concise = str(payload.get("summary") or payload.get("message") or stderr or stdout or event_type).strip()[:600]
            full_ref = str(payload.get("evidence_digest") or payload.get("receipt_digest") or payload.get("evidence_ref") or "")
            check = {
                "version": VERSION,
                "beast_object_type": "beast_verification_check_card",
                "check_id": identity,
                "sequence": event.get("sequence"),
                "event_type": event_type,
                "category": category,
                "status": status,
                "command": str(payload.get("command") or payload.get("invocation") or ""),
                "execution_target": str(payload.get("execution_target") or payload.get("target") or ""),
                "started_at": payload.get("started_at") or event.get("created_at"),
                "finished_at": payload.get("finished_at") or event.get("created_at"),
                "duration_ms": payload.get("duration_ms"),
                "exit_code": payload.get("exit_code"),
                "concise_output": concise,
                "full_evidence_reference": full_ref,
                "evidence_digest": full_ref,
                "freshness": _freshness(payload, status),
                "equivalence_proof_digest": str(payload.get("equivalence_proof_digest") or payload.get("equivalence_digest") or ""),
                "repair_cycle": int(payload.get("repair_cycle") or payload.get("repair_round") or 0),
                "step_id": str(payload.get("step_id") or ""),
                "promotion_relevant": bool(payload.get("promotion_relevant", category in {"package_tests", "security", "policy", "sourceplan_validation", "post_apply_verification"})),
                "authority": "verification_check_display_only",
                "grants_execution_authority": False,
                "grants_promotion_authority": False,
            }
            check["check_digest"] = _digest(check)
            checks.append(check)
        checks.sort(key=lambda item: (int(item.get("sequence") or 0), str(item.get("started_at") or ""), item["check_id"]))
        return checks

    @staticmethod
    def _current_status(checks: list[dict[str, Any]]) -> str:
        if not checks:
            return "NOT_STARTED"
        statuses = {item["status"] for item in checks}
        if "RUNNING" in statuses:
            return "RUNNING"
        if statuses & {"FAILED", "TIMED_OUT", "BLOCKED", "STALE"}:
            return "FAILED"
        if statuses <= {"PASSED", "REUSED_WITH_PROOF", "SKIPPED"}:
            return "PASSED"
        return "PARTIAL"
