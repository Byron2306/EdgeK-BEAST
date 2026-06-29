from app.kernel.execution.session_handshake import SessionHandshakeBuilder


def test_session_handshake_makes_agent_beast_aware():
    packet = SessionHandshakeBuilder().build(
        "Fix provider routing",
        tools=["read_file", "pytest", "read_file"],
        preflight_budget_ms=450,
        scout_budget_ms=250,
        session_id="ses_test",
    )

    assert packet["beast_object_type"] == "beast_session_handshake"
    assert packet["session_id"] == "ses_test"
    assert packet["candidate_tools"] == ["pytest", "read_file"]
    assert packet["latency_budget"]["preflight_budget_ms"] == 450
    assert packet["latency_budget"]["scout_budget_ms"] == 250
    assert "You are operating inside BEAST" in packet["agent_instruction"]
    assert "not a standalone model" in packet["agent_instruction"]
    assert any("Do not repeat low-value tool calls" in item for item in packet["agent_contract"]["avoid"])
    assert packet["agent_awareness"]["knows_it_is_inside_beast"] is True
    assert packet["agent_awareness"]["tiny_model_role"] == "intent_router_policy_summarizer"
    assert "commons" in packet["agent_awareness"]
    assert "capability_registry" in packet["agent_awareness"]
    assert packet["operating_protocol"]["llama_loop"][0].startswith("Classify")
    assert packet["operating_protocol"]["tool_request_format"]["needed_capability"] == "capability_id_or_role"
    assert packet["handshake_hash"].startswith("sha256:")


def test_session_handshake_caps_scout_to_preflight_budget():
    packet = SessionHandshakeBuilder().build(
        "Tiny preflight", preflight_budget_ms=100, scout_budget_ms=500
    )

    assert packet["latency_budget"]["preflight_budget_ms"] == 100
    assert packet["latency_budget"]["scout_budget_ms"] == 100
