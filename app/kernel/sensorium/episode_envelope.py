"""Canonical, privacy-filtered Episode Envelopes and AgentRun budget accounting.

An envelope is the single learning record for one AgentRun or swarm lane. It
keeps ordered tool steps, verification outcome, negative evidence and budget
counters, but only as allow-listed scalars and digests: no raw prompts, file
contents, tool output or secret-pattern matches ever enter an envelope.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from app.kernel.sensorium.privacy import SensorPrivacyGate

ENVELOPE_SCHEMA = "beast.episode_envelope.v1"
COMPOSITE_FIELDS = ("component_ids", "authority", "composite_verification")
SAFE_ARGUMENT_KEYS = ("path", "start_line", "line_count", "end_line")
BUDGET_KEYS = (
    "model_turns", "tokens_prompt", "tokens_completion", "tokens_total", "tokens_estimated_turns",
    "tool_calls", "tool_calls_model", "tool_calls_crystal", "tool_calls_runtime", "tool_failures", "wall_ms",
)
TOOL_SOURCES = frozenset({"model", "crystal", "runtime"})


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SensorPrivacyGate.SECRET_PATTERNS)


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if len(text) > 256 or _contains_secret(text) or any(ch in text for ch in "\r\n\x00"):
        return None
    return text


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4) if text else 0


class RunBudgetTracker:
    """Record real model turns, tool calls and wall time into ``merge_budget``."""

    def __init__(self, store: Any, emit: Callable[[str, str, dict[str, Any]], Any] | None = None,
                 *, clock: Callable[[], float] = time.monotonic):
        self.store = store
        self.emit = emit or (lambda run_id, event_type, payload: store.append_event(run_id, event_type, payload))
        self.clock = clock
        self._marks: dict[str, float] = {}
        self._lock = threading.Lock()

    def start(self, run_id: str) -> None:
        with self._lock:
            self._marks[run_id] = float(self.clock())

    def mark_wall(self, run_id: str) -> float:
        now = float(self.clock())
        with self._lock:
            previous = self._marks.get(run_id, now)
            self._marks[run_id] = now
        elapsed = max(0.0, (now - previous) * 1000.0)
        if elapsed:
            self.store.merge_budget(run_id, {"wall_ms": elapsed})
        return elapsed

    def record_model_turn(self, run_id: str, *, prompt: str, decision: Any,
                          usage: Mapping[str, Any] | None = None) -> dict[str, Any]:
        prompt_tokens = completion_tokens = None
        if isinstance(usage, Mapping):
            try:
                prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0) or None
                completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0) or None
            except (TypeError, ValueError):
                prompt_tokens = completion_tokens = None
        estimated = prompt_tokens is None or completion_tokens is None
        if prompt_tokens is None:
            prompt_tokens = _estimate_tokens(str(prompt or ""))
        if completion_tokens is None:
            payload = decision.as_dict() if hasattr(decision, "as_dict") else decision
            completion_tokens = _estimate_tokens(_canonical(payload).decode("utf-8"))
        delta = {
            "model_turns": 1,
            "tokens_prompt": prompt_tokens,
            "tokens_completion": completion_tokens,
            "tokens_total": prompt_tokens + completion_tokens,
            "tokens_estimated_turns": 1 if estimated else 0,
        }
        self.store.merge_budget(run_id, delta)
        return delta

    def record_tool_call(self, run_id: str, *, tool_id: str, status: str, source: str) -> None:
        source = source if source in TOOL_SOURCES else "model"
        delta = {"tool_calls": 1, f"tool_calls_{source}": 1}
        if str(status) != "completed":
            delta["tool_failures"] = 1
        self.store.merge_budget(run_id, delta)
        self.emit(run_id, "agent.budget.recorded", {"tool_id": str(tool_id), "status": str(status), "source": source})


@dataclass(frozen=True)
class EpisodeEnvelope:
    schema: str
    run_id: str
    origin: str
    workspace_digest: str
    objective_digest: str
    task_family: str
    mode: str
    provider: str
    model: str
    state: str
    implementation_target: str
    steps: tuple[Mapping[str, Any], ...]
    verification: Mapping[str, Any]
    negative_evidence: tuple[Mapping[str, Any], ...]
    budget: Mapping[str, float]
    event_chain_head: str
    envelope_digest: str = ""
    # Lattice spine: composite episodes carry their children, A_L = intersection of A_Ci, and the composite verifier.
    # Empty values are excluded from the digest so pre-existing envelope digests are unchanged.
    component_ids: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()
    composite_verification: Mapping[str, Any] = field(default_factory=dict)

    def _body(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("envelope_digest", None)
        for key in COMPOSITE_FIELDS:
            if not body.get(key):
                body.pop(key, None)
        return body

    def sealed(self) -> EpisodeEnvelope:
        return replace(self, envelope_digest=_digest(self._body()))

    def validate(self) -> None:
        body = self._body()
        if self.schema != ENVELOPE_SCHEMA or not self.run_id:
            raise ValueError("episode envelope schema or run binding is invalid")
        if self.envelope_digest != _digest(body):
            raise ValueError("episode envelope digest mismatch")
        if _contains_secret(_canonical(body).decode("utf-8")):
            raise ValueError("episode envelope contains secret material")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EpisodeEnvelope:
        data = dict(value)
        data["steps"] = tuple(data.get("steps") or ())
        data["negative_evidence"] = tuple(data.get("negative_evidence") or ())
        data["component_ids"] = tuple(data.get("component_ids") or ())
        data["authority"] = tuple(data.get("authority") or ())
        data["composite_verification"] = dict(data.get("composite_verification") or {})
        envelope = cls(**data)
        envelope.validate()
        return envelope


def _verification(steps: list[dict[str, Any]]) -> dict[str, Any]:
    verify = [step for step in steps if step["tool_id"] == "worktree.verify"]
    if not verify:
        return {"present": False, "passed": False, "failures_before_pass": 0, "final_returncode": None, "verify_steps": 0}
    last = verify[-1]
    passed = last["status"] == "completed" and last.get("returncode") == 0
    failures = sum(1 for step in verify[:-1] if step.get("returncode") not in (0, None) or step["status"] != "completed")
    return {"present": True, "passed": bool(passed), "failures_before_pass": failures,
            "final_returncode": last.get("returncode"), "verify_steps": len(verify)}


def _negative(steps: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    rows = []
    for step in steps:
        if step["tool_id"] == "worktree.verify" and step.get("returncode") not in (0, None):
            kind = "verification_failed"
        elif step["status"] != "completed":
            kind = "tool_failed"
        else:
            continue
        rows.append({"index": step["index"], "tool_id": step["tool_id"], "kind": kind,
                     "result_digest": step["result_digest"]})
    return tuple(rows)


def episode_observations(store: Any, run_id: str, *, run=None, events=None) -> list[Mapping[str, Any]]:
    """Read the same full receipts for extraction that were sealed in the envelope."""
    run = run if run is not None else store.get_run(run_id) or {}
    if (run.get("request") or {}).get("launch_strategy") == "direct_coder":
        events = events if events is not None else EpisodeEnvelopeBuilder._events(store, run_id)
        return [observation for event in events
                if event.get("event_type") in {"agent.tool.completed", "agent.tool.failed"}
                and isinstance((observation := (event.get("payload") or {}).get("observation")), Mapping)]
    checkpoint = run.get("checkpoint") or {}
    planner = checkpoint.get("planner") or {}
    return [item for item in planner.get("observations") or [] if isinstance(item, Mapping)]


class EpisodeEnvelopeBuilder:
    def build(self, store: Any, run_id: str) -> EpisodeEnvelope:
        run = store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        events = self._events(store, run_id)
        observations = episode_observations(store, run_id, run=run, events=events)
        sources = [
            str((event.get("payload") or {}).get("source") or "model")
            for event in events
            if event.get("event_type") == "agent.budget.recorded"
        ]
        activation = next((dict(event.get("payload") or {}) for event in events
                           if event.get("event_type") == "agent.crystal.activated"), {})
        component_ids = tuple(str(item) for item in activation.get("component_ids") or ())
        steps = []
        for index, observation in enumerate(observations):
            arguments = observation.get("arguments") if isinstance(observation.get("arguments"), Mapping) else {}
            result = observation.get("result") if isinstance(observation.get("result"), Mapping) else {}
            safe = {key: _safe_scalar(arguments[key]) for key in SAFE_ARGUMENT_KEYS if key in arguments}
            safe = {key: value for key, value in safe.items() if value is not None}
            returncode = result.get("returncode")
            steps.append({
                "index": index,
                "tool_id": str(observation.get("tool_id") or ""),
                "status": str(observation.get("status") or ""),
                "source": sources[index] if index < len(sources) else "model",
                "arguments_digest": _digest(arguments),
                "safe_arguments": safe,
                "result_digest": str(observation.get("evidence_digest") or _digest(result)),
                "returncode": int(returncode) if isinstance(returncode, int) and not isinstance(returncode, bool) else None,
                "duration_ms": float(observation.get("duration_ms") or 0),
            })
        budget = run.get("budget") if isinstance(run.get("budget"), Mapping) else {}
        target = _safe_scalar(request.get("implementation_target") or "")
        task_family = str(_safe_scalar(request.get("task_family") or "") or "")
        if not task_family and request.get("launch_strategy") == "direct_coder":
            from app.kernel.compute.coder_crystal_feedback import observed_trial_family
            task_family = observed_trial_family(request, observations)
        return EpisodeEnvelope(
            schema=ENVELOPE_SCHEMA,
            run_id=str(run_id),
            origin="agent_run",
            workspace_digest=_digest(str(run.get("root_path") or "")),
            objective_digest=_digest(str(run.get("objective") or "")),
            task_family=task_family or "unclassified",
            mode=str(run.get("mode") or ""),
            provider=str(_safe_scalar(run.get("provider") or "") or ""),
            model=str(_safe_scalar(run.get("model") or "") or ""),
            state=str(run.get("state") or ""),
            implementation_target=str(target or ""),
            steps=tuple(steps),
            verification=_verification(steps),
            negative_evidence=_negative(steps),
            budget={key: float(budget.get(key) or 0) for key in BUDGET_KEYS},
            event_chain_head=str(run.get("head_hash") or ""),
            component_ids=component_ids,
            authority=tuple(sorted(str(item) for item in activation.get("authority") or ())) if component_ids else (),
            composite_verification=({"composite_crystal_id": str(activation.get("crystal_id") or ""),
                                     "component_ids": list(component_ids),
                                     "passed": bool(_verification(steps).get("passed"))} if component_ids else {}),
        ).sealed()

    @staticmethod
    def _events(store: Any, run_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        after = 0
        while True:
            batch = store.events(run_id, after=after, limit=250)
            if not batch:
                return events
            events.extend(batch)
            after = int(batch[-1].get("sequence") or after + len(batch))
            if len(batch) < 250:
                return events


def envelope_from_swarm_episode(episode: Mapping[str, Any], *, run_id: str, workspace_digest: str = "") -> EpisodeEnvelope:
    events = [item for item in episode.get("events") or [] if isinstance(item, Mapping)]
    steps = [{
        "index": index,
        "tool_id": "swarm." + str(_safe_scalar(item.get("decision") or item.get("type") or "event") or "event"),
        "status": "completed",
        "source": "swarm",
        "arguments_digest": _digest(item.get("details") or {}),
        "safe_arguments": {},
        "result_digest": _digest(item),
        "returncode": None,
        "duration_ms": 0.0,
    } for index, item in enumerate(events)]
    verified = episode.get("episode_status") == "verified"
    return EpisodeEnvelope(
        schema=ENVELOPE_SCHEMA,
        run_id=str(run_id),
        origin="swarm_lane",
        workspace_digest=str(workspace_digest),
        objective_digest=_digest(str(episode.get("task_class") or "")),
        task_family=str(_safe_scalar(episode.get("task_class") or "") or "unclassified"),
        mode="swarm",
        provider="",
        model="",
        state="verified" if verified else "unverified",
        implementation_target="",
        steps=tuple(steps),
        verification={"present": True, "passed": verified, "failures_before_pass": 0,
                      "final_returncode": None, "verify_steps": 0},
        negative_evidence=() if verified else ({"index": -1, "tool_id": "swarm.episode", "kind": "unverified_episode",
                                                "result_digest": _digest(episode.get("classifications") or [])},),
        budget=dict.fromkeys(BUDGET_KEYS, 0.0) | {"tool_calls": float(len(steps))},
        event_chain_head="",
    ).sealed()


class EpisodeEnvelopeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS episode_envelopes (run_id TEXT PRIMARY KEY, task_family TEXT NOT NULL, "
                "envelope_digest TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def put(self, envelope: EpisodeEnvelope) -> EpisodeEnvelope:
        envelope.validate()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO episode_envelopes(run_id,task_family,envelope_digest,payload,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET task_family=excluded.task_family,"
                "envelope_digest=excluded.envelope_digest,payload=excluded.payload",
                (envelope.run_id, envelope.task_family, envelope.envelope_digest,
                 json.dumps(envelope.to_dict(), sort_keys=True), time.time()),
            )
        return envelope

    def get(self, run_id: str) -> EpisodeEnvelope:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM episode_envelopes WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise LookupError(f"no episode envelope for run {run_id}")
        return EpisodeEnvelope.from_dict(json.loads(row["payload"]))

    def list(self, *, task_family: str = "", limit: int = 100) -> list[EpisodeEnvelope]:
        query = "SELECT payload FROM episode_envelopes"
        params: Iterable[Any] = ()
        if task_family:
            query += " WHERE task_family=?"
            params = (task_family,)
        query += " ORDER BY created_at LIMIT ?"
        with self._connect() as connection:
            rows = connection.execute(query, (*params, max(1, min(int(limit), 1000)))).fetchall()
        return [EpisodeEnvelope.from_dict(json.loads(row["payload"])) for row in rows]
