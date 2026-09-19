from app.kernel.operations_console.view_model import AgentOperationsConsoleViewModel


def test_phase11_operator_state_is_read_only_and_epoch_bound(tmp_path):
    vm = AgentOperationsConsoleViewModel(tmp_path)
    run = {
        "state": "running",
        "request": {"execution_target": "ssh"},
        "event_head_hash": "sha256:timeline",
    }
    checkpoint = {
        "worktree_mutation_epoch": 3,
        "planner": {"phase": "verification", "turn": 6, "repair_cycles": 1},
        "verification": {
            "ok": True,
            "status": "passed",
            "mutation_epoch": 3,
            "execution_target": "ssh",
            "target_execution": "remote_ssh",
            "transport": "ssh",
            "receipt_digest": "sha256:verify",
        },
    }
    events = [
        {"event_type": "agent.execution.gate", "payload": {"decision": "allow", "tool_id": "worktree.verify"}},
        {"event_type": "agent.crystal.feedback", "payload": {"assistance_mode": "strategy"}},
    ]
    approvals = [{"request_id": "approval-1", "status": "pending"}]
    worktree = {"status": "bound", "path": "/tmp/worktree", "dirty": True}
    verification = {"status": "passed"}
    sourceplan = {"status": "ready", "promotion_ready": True, "promotion_authorized": False}
    route = {"provider": "ollama", "model": "qwen"}

    state = vm._operator_state(run, checkpoint, events, approvals, worktree, verification, sourceplan, route)

    assert state["planner"]["phase"] == "verification"
    assert state["execution"]["target_execution"] == "remote_ssh"
    assert state["execution"]["transport"] == "ssh"
    assert state["worktree"]["mutation_epoch"] == 3
    assert state["verification"]["current"] is True
    assert state["approvals"]["pending"] == ["approval-1"]
    assert state["promotion"]["ready"] is True
    assert state["promotion"]["authorized"] is False
    assert state["authority"] == "read_only_operator_projection"
    assert state["grants_execution_authority"] is False
    assert state["grants_workspace_mutation"] is False
    assert state["grants_promotion_authority"] is False


def test_phase11_stale_verification_blocks_promotion_readiness(tmp_path):
    vm = AgentOperationsConsoleViewModel(tmp_path)
    state = vm._operator_state(
        {"state": "running", "request": {"execution_target": "local"}},
        {
            "worktree_mutation_epoch": 4,
            "planner": {"phase": "repair"},
            "verification": {"ok": True, "status": "passed", "mutation_epoch": 3},
        },
        [],
        [],
        {"status": "bound", "path": "/tmp/worktree", "dirty": True},
        {"status": "passed"},
        {"status": "ready", "promotion_ready": True, "promotion_authorized": False},
        {},
    )
    assert state["verification"]["current"] is False
    assert state["promotion"]["ready"] is False
    assert "current-epoch verification" in state["promotion"]["blocked_reason"]
