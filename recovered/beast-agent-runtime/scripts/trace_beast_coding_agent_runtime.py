#!/usr/bin/env python3
"""Merge evidence-backed coding-agent runtime observations into the BEAST census.

Static reachability is deliberately insufficient. Runtime facts are promoted only
from explicit trace records or from a cryptographically verified durable
AgentRun event chain whose event type has a unique producer mapping.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

TRACE_EVENTS = {
    "constructed",
    "invoked",
    "evidence_written",
    "authority_exercised",
}

RUNTIME_FIELD_BY_EVENT = {
    "constructed": "constructed",
    "invoked": "invoked",
    "evidence_written": "evidence_producing",
}

# Only map event names whose producer is explicit in the current code path.
# Unknown or ambiguous AgentRun events remain durable evidence in RunStore but
# do not promote another component's runtime state.
AGENT_EVENT_PRODUCERS = {
    "agent.planner.started": "app/kernel/agents/planner_runtime.py",
    "agent.planner.turn.started": "app/kernel/agents/planner_runtime.py",
    "agent.planner.decision": "app/kernel/agents/planner_runtime.py",
    "agent.planner.completion_rejected": "app/kernel/agents/planner_runtime.py",
    "agent.planner.completed": "app/kernel/agents/planner_runtime.py",
    "agent.planner.blocked": "app/kernel/agents/planner_runtime.py",
    "agent.planner.observation.accepted": "app/kernel/agents/planner_runtime.py",
    "agent.verification.failed": "app/kernel/agents/planner_runtime.py",
    "agent.verification.passed": "app/kernel/agents/planner_runtime.py",
    "agent.repair.required": "app/kernel/agents/planner_runtime.py",
    "agent.repair.budget_exhausted": "app/kernel/agents/planner_runtime.py",
    "agent.tool.started": "app/kernel/agents/tool_runtime.py",
    "agent.tool.completed": "app/kernel/agents/tool_runtime.py",
    "agent.tool.failed": "app/kernel/agents/tool_runtime.py",
}

RUN_STORE_PATH = "app/kernel/agents/run_store.py"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _normalize_timestamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("trace timestamp must be numeric") from exc


def _validate_trace_record(record: dict[str, Any], known_paths: set[str]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("trace record must be an object")
    component_path = str(record.get("component_path") or "").strip()
    if component_path not in known_paths:
        raise ValueError(f"unknown component: {component_path or '<empty>'}")
    event = str(record.get("event") or "").strip()
    if event not in TRACE_EVENTS:
        raise ValueError(f"invalid trace event: {event or '<empty>'}")
    evidence_ref = str(record.get("evidence_ref") or "").strip()
    if not evidence_ref:
        raise ValueError("trace record requires evidence_ref")
    request_id = str(record.get("request_id") or "").strip()
    run_id = str(record.get("run_id") or "").strip()
    if not request_id:
        raise ValueError("trace record requires request_id")
    if not run_id:
        raise ValueError("trace record requires run_id")
    source = str(record.get("source") or "").strip()
    if not source:
        raise ValueError("trace record requires source")
    return {
        "request_id": request_id,
        "run_id": run_id,
        "component_path": component_path,
        "event": event,
        "evidence_ref": evidence_ref,
        "timestamp": _normalize_timestamp(record.get("timestamp")),
        "source": source,
    }


def merge_trace_records(report: dict[str, Any], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a census copy enriched only by validated runtime evidence."""
    result = deepcopy(report)
    components = result.get("components")
    if not isinstance(components, list):
        raise ValueError("census report requires components list")
    by_path = {
        str(item.get("path") or ""): item
        for item in components
        if isinstance(item, dict) and str(item.get("path") or "")
    }
    known_paths = set(by_path)
    validated = [_validate_trace_record(record, known_paths) for record in records]

    seen: set[tuple[Any, ...]] = set()
    applied: list[dict[str, Any]] = []
    for record in sorted(
        validated,
        key=lambda item: (
            item["timestamp"],
            item["run_id"],
            item["component_path"],
            item["event"],
            item["evidence_ref"],
        ),
    ):
        marker = (
            record["request_id"],
            record["run_id"],
            record["component_path"],
            record["event"],
            record["evidence_ref"],
            record["timestamp"],
            record["source"],
        )
        if marker in seen:
            continue
        seen.add(marker)
        item = by_path[record["component_path"]]
        evidence = list(item.get("runtime_evidence") or [])
        evidence.append(record)
        evidence.sort(
            key=lambda entry: (
                float(entry.get("timestamp") or 0.0),
                str(entry.get("event") or ""),
                str(entry.get("evidence_ref") or ""),
            )
        )
        item["runtime_evidence"] = evidence
        runtime_field = RUNTIME_FIELD_BY_EVENT.get(record["event"])
        if runtime_field:
            runtime = item.setdefault("runtime", {})
            runtime[runtime_field] = "observed"
        elif record["event"] == "authority_exercised":
            item["authority"] = "observed"
        applied.append(record)

    source_counts = Counter(record["source"] for record in applied)
    runtime_overlay = dict((result.get("overlay") or {}).get("runtime_trace") or {})
    runtime_overlay.update(
        {
            "record_count": len(applied),
            "observed_components": sorted({record["component_path"] for record in applied}),
            "sources": dict(sorted(source_counts.items())),
            "truth_rule": "Only explicit evidence-backed trace records may promote runtime or authority fields.",
        }
    )
    overlay = dict(result.get("overlay") or {})
    overlay["runtime_trace"] = runtime_overlay
    result["overlay"] = overlay
    return result


def verify_agent_run_event_chain(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Verify a full AgentRunStore event chain before using it as evidence."""
    chain = list(events)
    if not chain:
        return {"valid": True, "event_count": 0, "run_id": "", "head_hash": ""}

    run_id = str(chain[0].get("run_id") or "").strip()
    if not run_id:
        raise ValueError("agent run event chain requires run_id")
    previous_hash = ""
    expected_sequence = 1

    for event in chain:
        if not isinstance(event, dict):
            raise ValueError("agent run event must be an object")
        if str(event.get("run_id") or "").strip() != run_id:
            raise ValueError("agent run event chain contains multiple run_ids")
        try:
            sequence = int(event.get("sequence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("agent run event sequence is invalid") from exc
        if sequence != expected_sequence:
            raise ValueError(f"agent run event sequence mismatch at {sequence}; expected {expected_sequence}")
        observed_previous = str(event.get("previous_hash") or "")
        if observed_previous != previous_hash:
            raise ValueError(f"previous hash mismatch at event {sequence}")
        body = {
            "run_id": run_id,
            "sequence": sequence,
            "event_type": str(event.get("event_type") or ""),
            "legacy_type": str(event.get("legacy_type") or ""),
            "created_at": event.get("created_at"),
            "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
        }
        calculated = "sha256:" + hashlib.sha256(
            previous_hash.encode("utf-8") + _canonical(body)
        ).hexdigest()
        observed_hash = str(event.get("event_hash") or "")
        if calculated != observed_hash:
            raise ValueError(f"event hash mismatch at event {sequence}")
        previous_hash = observed_hash
        expected_sequence += 1

    return {
        "valid": True,
        "event_count": len(chain),
        "run_id": run_id,
        "head_hash": previous_hash,
    }


def _event_evidence_ref(event: dict[str, Any]) -> str:
    return (
        f"agent_run:{str(event.get('run_id') or '')}:"
        f"event:{int(event.get('sequence') or 0)}:{str(event.get('event_hash') or '')}"
    )


def trace_records_from_agent_run_events(
    events: Iterable[dict[str, Any]],
    *,
    request_id: str,
) -> list[dict[str, Any]]:
    """Translate a verified full AgentRun chain into conservative runtime facts.

    Every durable event proves AgentRunStore wrote evidence. Only event names
    with an explicit unique producer mapping promote another component. In
    particular, these records do not prove Sensorium mirroring because that
    path is best-effort and failures are intentionally swallowed by RunEngine.
    """
    chain = list(events)
    verification = verify_agent_run_event_chain(chain)
    if not chain:
        return []
    run_id = verification["run_id"]
    request_id = str(request_id or "").strip()
    if not request_id:
        raise ValueError("request_id is required for AgentRun trace import")

    records: list[dict[str, Any]] = []
    for event in chain:
        evidence_ref = _event_evidence_ref(event)
        timestamp = _normalize_timestamp(event.get("created_at"))
        common = {
            "request_id": request_id,
            "run_id": run_id,
            "evidence_ref": evidence_ref,
            "timestamp": timestamp,
            "source": "agent_run_event_chain",
        }
        records.append(
            {
                **common,
                "component_path": RUN_STORE_PATH,
                "event": "evidence_written",
            }
        )
        records.append(
            {
                **common,
                "component_path": RUN_STORE_PATH,
                "event": "invoked",
            }
        )
        producer = AGENT_EVENT_PRODUCERS.get(str(event.get("event_type") or ""))
        if producer:
            records.append(
                {
                    **common,
                    "component_path": producer,
                    "event": "invoked",
                }
            )
    return records


def _load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--trace-records", type=Path)
    parser.add_argument("--agent-run-events", type=Path)
    parser.add_argument("--request-id", default="")
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    report = _load_json(args.census)
    records: list[dict[str, Any]] = []
    if args.trace_records:
        payload = _load_json(args.trace_records)
        if isinstance(payload, dict):
            payload = payload.get("records")
        if not isinstance(payload, list):
            raise ValueError("trace records input must be a list or {'records': [...]} object")
        records.extend(payload)
    if args.agent_run_events:
        payload = _load_json(args.agent_run_events)
        if isinstance(payload, dict):
            payload = payload.get("events")
        if not isinstance(payload, list):
            raise ValueError("agent run events input must be a list or {'events': [...]} object")
        records.extend(trace_records_from_agent_run_events(payload, request_id=args.request_id))

    merged = merge_trace_records(report, records)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
