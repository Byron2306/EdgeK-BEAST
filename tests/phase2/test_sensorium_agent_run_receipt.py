from __future__ import annotations

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.sensorium.journal import SensoriumJournal


def test_agent_run_events_have_independent_durable_sensorium_receipts(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(session_id="receipt-test", objective="Trace a run")["run_id"]
    engine.emit(run_id, "agent.verification.passed", {"returncode": 0})

    source_events = engine.store.events(run_id)
    journal = SensoriumJournal(tmp_path / ".beast" / "sensorium" / "agent_runs.sqlite3")
    receipts = [entry.event for entry in journal.replay() if entry.event.attribution.get("mission_id") == run_id]
    assert len(receipts) == len(source_events)
    assert [entry.payload["event_hash"] for entry in receipts] == [entry["event_hash"] for entry in source_events]
    assert [entry.payload["source_event_type"] for entry in receipts] == [entry["event_type"] for entry in source_events]
    assert all(entry.event_type == "agent.run.observed" for entry in receipts)
