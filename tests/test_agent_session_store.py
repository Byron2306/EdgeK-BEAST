from app.kernel.workspaces.agent_session_store import AgentSessionStore


def test_agent_session_store_lifecycle_and_sourceplan_draft(tmp_path):
    store = AgentSessionStore(tmp_path)

    created = store.create(
        objective="Improve the BEAST IDE shell",
        mode="architect",
        budget={"tokens": 4000, "seconds": 0},
        tools=["code_cortex", "evidence_bus"],
        files=["app/main.py"],
        agent_id="planner",
        provider="local",
    )

    assert created["ok"] is True
    session_id = created["session"]["session_id"]
    assert created["session"]["status"] == "active"

    paused = store.pause(session_id)
    assert paused["session"]["status"] == "paused"

    resumed = store.resume(session_id)
    assert resumed["session"]["status"] == "active"

    updated = store.update(
        session_id,
        output={"text": "Add a governed SourcePlan panel."},
        evidence=[{"artifact_type": "note", "summary": "operator reviewed"}],
        budget_delta={"tokens": 120},
    )
    assert updated["session"]["budget"]["tokens"] == 4120
    assert updated["session"]["outputs"]
    assert updated["session"]["evidence"]

    draft = store.sourceplan_draft(session_id)
    assert draft["ok"] is True
    assert draft["plan"]["agent_session_id"] == session_id
    assert draft["plan"]["requires_operator_translation"] is True
    assert draft["plan"]["operations"] == []

    cancelled = store.cancel(session_id, reason="done")
    assert cancelled["session"]["status"] == "cancelled"
