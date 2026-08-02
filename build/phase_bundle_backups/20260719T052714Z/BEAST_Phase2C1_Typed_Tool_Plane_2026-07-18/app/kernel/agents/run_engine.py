"""Canonical durable runtime facade for BEAST agent runs.

Phase 2A wraps the existing Pair Programmer stream so it gains durable identity,
replay, cancellation, checkpoints, approval records, and Sensorium metadata
without changing the provider or SourcePlan semantics underneath it.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from app.kernel.agents.run_cancel import AGENT_RUN_CANCELLATIONS
from app.kernel.agents.run_events import canonical_event_type, parse_sse_chunk, state_for_event
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, can_transition, normalize_state
from app.kernel.agents.run_store import AgentRunStore


class AgentRunCancelled(asyncio.CancelledError):
    def __init__(self, run_id: str, reason: str = "operator_cancelled"):
        super().__init__(reason)
        self.run_id = run_id
        self.reason = reason


class AgentRunEngine:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store = AgentRunStore(self.workspace_root)
        self._sensorium = None

    def create_run(
        self,
        *,
        session_id: str,
        objective: str,
        mode: str = "agent",
        provider: str = "",
        model: str = "",
        request: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> dict[str, Any]:
        run = self.store.create_run(
            session_id=session_id,
            objective=objective,
            mode=mode,
            provider=provider,
            model=model,
            request=request,
            budget=budget,
            run_id=run_id,
        )
        AGENT_RUN_CANCELLATIONS.register(str(run.get("run_id") or ""))
        self._mirror_latest(str(run.get("run_id") or ""))
        return run

    def ensure_run(
        self,
        *,
        run_id: str,
        session_id: str,
        objective: str,
        mode: str,
        provider: str,
        model: str,
        request: dict[str, Any],
        budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if run_id:
            existing = self.store.get_run(run_id)
            if existing:
                if str(existing.get("session_id") or "") != str(session_id or ""):
                    raise ValueError("agent run does not belong to this session")
                AGENT_RUN_CANCELLATIONS.register(run_id)
                return existing
        return self.create_run(
            session_id=session_id,
            objective=objective,
            mode=mode,
            provider=provider,
            model=model,
            request=request,
            budget=budget,
            run_id=run_id,
        )

    def record_legacy_chunk(self, run_id: str, chunk: str) -> dict[str, Any] | None:
        parsed = parse_sse_chunk(chunk)
        if parsed is None:
            return None
        legacy_type, payload = parsed
        canonical = canonical_event_type(legacy_type, payload)
        payload.setdefault("run_id", run_id)
        event = self.store.append_event(run_id, canonical, payload, legacy_type=legacy_type)
        state = state_for_event(canonical, payload)
        current = self.store.get_run(run_id)
        if current and state and can_transition(str(current.get("state") or "created"), state):
            error = str(payload.get("error") or "") if state == AgentRunState.FAILED else ""
            self.store.transition(run_id, state, error=error)
        if canonical == "agent.approval.requested":
            self.store.create_approval(run_id, payload)
        self.store.checkpoint(run_id, {
            "sequence": event["sequence"],
            "event_type": event["event_type"],
            "legacy_type": legacy_type,
            "payload_keys": sorted(payload.keys()),
        })
        self._mirror_event(event)
        return event

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None, *, legacy_type: str = "") -> dict[str, Any]:
        event = self.store.append_event(run_id, event_type, payload or {}, legacy_type=legacy_type)
        self._mirror_event(event)
        return event

    def checkpoint(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.checkpoint(run_id, payload)

    def attach_current_task(self, run_id: str) -> None:
        task = asyncio.current_task()
        if task is not None:
            AGENT_RUN_CANCELLATIONS.attach_task(run_id, task)

    def cancellation_requested(self, run_id: str) -> bool:
        return self.store.is_cancel_requested(run_id) or AGENT_RUN_CANCELLATIONS.is_cancelled(run_id)

    def raise_if_cancelled(self, run_id: str) -> None:
        if not self.cancellation_requested(run_id):
            return
        run = self.store.get_run(run_id) or {}
        raise AgentRunCancelled(run_id, str(run.get("cancel_reason") or "operator_cancelled"))

    async def cancel(self, run_id: str, reason: str = "") -> dict[str, Any]:
        run = self.store.request_cancel(run_id, reason)
        event = self.store.append_event(run_id, "agent.run.cancellation_requested", {
            "reason": str(reason or "operator_cancelled"),
            "state": run.get("state"),
        })
        self._mirror_event(event)
        handles = await AGENT_RUN_CANCELLATIONS.cancel(run_id, reason)
        return {"ok": True, "run": self.store.get_run(run_id), "execution": handles}

    def finalize_cancel(self, run_id: str, reason: str = "") -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        if normalize_state(str(run["state"])) not in TERMINAL_STATES:
            event = self.store.append_event(run_id, "agent.run.cancelled", {
                "reason": str(reason or run.get("cancel_reason") or "operator_cancelled"),
            })
            self._mirror_event(event)
            self.store.transition(run_id, AgentRunState.CANCELLED)
        AGENT_RUN_CANCELLATIONS.unregister(run_id)
        return self.store.get_run(run_id) or {}

    def fail(self, run_id: str, error: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        if normalize_state(str(run["state"])) not in TERMINAL_STATES:
            event = self.store.append_event(run_id, "agent.run.failed", {"error": str(error)})
            self._mirror_event(event)
            self.store.transition(run_id, AgentRunState.FAILED, error=error)
        AGENT_RUN_CANCELLATIONS.unregister(run_id)
        return self.store.get_run(run_id) or {}

    def resume(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        state = normalize_state(str(run["state"]))
        if state not in {AgentRunState.PAUSED, AgentRunState.CREATED}:
            raise ValueError(f"run cannot resume from {state.value}")
        self.store.clear_cancel(run_id)
        self.store.transition(run_id, AgentRunState.SCOPING)
        event = self.store.append_event(run_id, "agent.run.resumed", {"from_state": state.value})
        self._mirror_event(event)
        AGENT_RUN_CANCELLATIONS.register(run_id)
        return self.store.get_run(run_id) or {}

    def sse_event(self, event: dict[str, Any], *, projection: str = "canonical") -> str:
        import json
        selected = str(projection or "canonical").strip().lower()
        if selected == "legacy":
            event_name = str(event.get("legacy_type") or event.get("event_type") or "message")
            payload = {
                "beast_object_type": "beast_ide_event",
                "version": "2.0",
                "event_type": event_name,
                "created_at": int(float(event.get("created_at") or 0)),
                "run_sequence": int(event.get("sequence") or 0),
                "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
            }
        else:
            event_name = str(event.get("event_type") or "message")
            payload = {
                "beast_object_type": "beast_agent_run_event",
                "version": "2.0",
                **event,
            }
        return (
            f"id: {event['sequence']}\n"
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, sort_keys=True, default=str)}\n\n"
        )

    def _sensorium_runtime(self):
        if self._sensorium is not None:
            return self._sensorium
        try:
            from app.kernel.sensorium.runtime import SensoriumRuntime
            path = self.workspace_root / ".beast" / "sensorium" / "agent_runs.sqlite3"
            self._sensorium = SensoriumRuntime(capacity=2048, journal_path=path)
        except Exception:
            self._sensorium = False
        return self._sensorium

    def _mirror_latest(self, run_id: str) -> None:
        events = self.store.events(run_id, after=0, limit=1)
        if events:
            self._mirror_event(events[0])

    def _mirror_event(self, event: dict[str, Any]) -> None:
        runtime = self._sensorium_runtime()
        if not runtime:
            return
        try:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            runtime.observe_owned(
                event_type=str(event.get("event_type") or "agent.run.event"),
                source="beast_agent_run_engine",
                payload_schema="beast.sensor.agent_run_event.v1",
                mission_id=str(event.get("run_id") or ""),
                workspace_id="workspace:sha256:" + hashlib.sha256(str(self.workspace_root).encode()).hexdigest(),
                payload={
                    "run_id": str(event.get("run_id") or ""),
                    "sequence": int(event.get("sequence") or 0),
                    "legacy_type": str(event.get("legacy_type") or ""),
                    "event_hash": str(event.get("event_hash") or ""),
                    "payload_keys": sorted(payload.keys()),
                    "payload_included": False,
                },
            )
        except Exception:
            # The durable run ledger is authoritative for AgentRun replay.
            # Sensorium mirroring is deliberately best-effort in Phase 2A.
            return
