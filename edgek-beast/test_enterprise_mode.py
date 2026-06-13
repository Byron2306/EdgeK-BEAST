from app.kernel.enterprise import EnterpriseManager


def test_enterprise_manager_creates_team_user_and_virtual_key(tmp_path):
    manager = EnterpriseManager(db_path=str(tmp_path / "enterprise.db"))
    team = manager.create_team("Platform", daily_request_limit=2, daily_cost_limit_usd=1.0)
    user = manager.create_user(team["team_id"], "dev@example.com", role="admin")
    issued = manager.issue_virtual_key(team["team_id"], user["user_id"], scopes=["gateway:use", "admin"])

    context = manager.authenticate_virtual_key(issued["virtual_key"], required_scope="gateway:use")

    assert context.team_id == team["team_id"]
    assert context.user_id == user["user_id"]
    assert context.key_id == issued["key_id"]
    assert "virtual_key" in issued
    assert manager.state()["active_virtual_keys"] == 1


def test_enterprise_manager_enforces_per_team_budget(tmp_path):
    manager = EnterpriseManager(db_path=str(tmp_path / "enterprise.db"))
    team = manager.create_team("Ops", daily_request_limit=1, daily_cost_limit_usd=0.25)
    user = manager.create_user(team["team_id"], "ops@example.com")

    before = manager.check_team_budget(team["team_id"], projected_requests=1, projected_cost_usd=0.1)
    summary = manager.record_team_usage(
        team_id=team["team_id"],
        user_id=user["user_id"],
        request_count=1,
        estimated_cost_usd=0.2,
        total_tokens=100,
    )
    after = manager.check_team_budget(team["team_id"], projected_requests=1, projected_cost_usd=0.1)

    assert before["allowed"] is True
    assert summary["within_budget"] is True
    assert after["allowed"] is False
    assert "exceeded" in after["reason"]


def test_enterprise_observability_and_otel_export(tmp_path):
    manager = EnterpriseManager(db_path=str(tmp_path / "enterprise.db"))
    team = manager.create_team("Telemetry")

    event = manager.record_observability_event(
        team_id=team["team_id"],
        event_type="gateway.request",
        severity="info",
        payload={"route": "/v1/chat/completions"},
        trace_id="trace-1",
    )
    otel = manager.otel_export(team_id=team["team_id"])

    assert manager.observability_events(team_id=team["team_id"])[0]["event_id"] == event["event_id"]
    assert otel["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "gateway.request"


def test_enterprise_policy_pack_merges_into_effective_policy(tmp_path):
    manager = EnterpriseManager(
        policies={"meta_rules": {"daily_max_requests": 1000}},
        db_path=str(tmp_path / "enterprise.db"),
    )
    team = manager.create_team("Security")
    pack = manager.register_policy_pack(
        "Strict Budget",
        {"meta_rules": {"daily_max_requests": 10}, "providers": {"openai": {"enabled": False}}},
    )

    manager.assign_policy_pack(team["team_id"], pack["pack_id"])
    effective = manager.effective_policy(team["team_id"])

    assert effective["meta_rules"]["daily_max_requests"] == 10
    assert effective["providers"]["openai"]["enabled"] is False


def test_enterprise_encrypted_trace_round_trip_and_integrity(tmp_path):
    manager = EnterpriseManager(
        policies={"enterprise": {"trace_encryption_secret": "test-secret"}},
        db_path=str(tmp_path / "enterprise.db"),
    )
    team = manager.create_team("Archive")
    trace = {"trace_id": "trace-a", "message": "secret-ish local trace"}

    stored = manager.store_encrypted_trace(team["team_id"], trace, user_id="user-a")
    retrieved = manager.retrieve_encrypted_trace(team["team_id"], stored["trace_id"])

    assert stored["encrypted"] is True
    assert retrieved["trace"] == trace
    assert retrieved["digest"] == stored["digest"]
