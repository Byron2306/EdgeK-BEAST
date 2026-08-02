from pathlib import Path

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.operations_console.context_console import ContextManifestConsole
from app.kernel.operations_console.context_manifest import ContextManifestStore


def seed(tmp_path: Path):
    AgentRunEngine(tmp_path).create_run(session_id="s", objective="Inspect parser", mode="agent", run_id="run-56")
    store = ContextManifestStore(tmp_path)
    suggested = store.add_item(
        "run-56", source="semantic_search", path="app/parser.py", start_line=10, end_line=30,
        content="parser", retrieval_reasons=["Matches failing symbol"], token_estimate=12,
    )
    accepted = store.add_item(
        "run-56", source="operator", path="tests/test_parser.py", start_line=1, end_line=20,
        content="test", selection_origin="manual", token_estimate=8, privacy_level="PUBLIC",
        provider_visibility="ANY_PROVIDER",
    )
    sensitive = store.add_item(
        "run-56", source="file", path=".env", content="SECRET", selection_origin="manual",
        token_estimate=3, privacy_level="SENSITIVE", provider_visibility="REDACTED_ONLY",
    )
    return store, suggested, accepted, sensitive


def test_console_projects_operator_cards(tmp_path):
    seed(tmp_path)
    view = ContextManifestConsole(tmp_path).build("run-56")
    assert view["summary"]["item_count"] == 3
    assert len(view["cards"]) == 3
    assert view["authority"] == "context_manifest_console_read_only"


def test_suggestion_is_visibly_unselected(tmp_path):
    _, suggested, _, _ = seed(tmp_path)
    view = ContextManifestConsole(tmp_path).build("run-56")
    card = next(c for c in view["cards"] if c["item_id"] == suggested["item_id"])
    assert card["selected"] is False
    assert card["valid_actions"] == ["ACCEPTED", "REJECTED", "EXCLUDED"]
    assert "not selected" in card["warnings"][0]


def test_acceptance_and_admission_remain_distinct(tmp_path):
    _, _, accepted, _ = seed(tmp_path)
    card = next(c for c in ContextManifestConsole(tmp_path).build("run-56")["cards"] if c["item_id"] == accepted["item_id"])
    assert card["selected"] is True and card["admitted"] is False
    assert "ADMITTED" in card["valid_actions"]


def test_sensitive_card_exposes_redaction_warning(tmp_path):
    _, _, _, sensitive = seed(tmp_path)
    card = next(c for c in ContextManifestConsole(tmp_path).build("run-56")["cards"] if c["item_id"] == sensitive["item_id"])
    assert card["privacy_level"] == "SENSITIVE"
    assert any("redaction receipt" in warning for warning in card["warnings"])


def test_source_reference_includes_line_range(tmp_path):
    seed(tmp_path)
    card = next(c for c in ContextManifestConsole(tmp_path).build("run-56")["cards"] if c["path"] == "app/parser.py")
    assert card["source_reference"] == "app/parser.py:10-30"


def test_console_filters_by_status_privacy_visibility_and_query(tmp_path):
    seed(tmp_path)
    console = ContextManifestConsole(tmp_path)
    assert console.build("run-56", status="accepted")["summary"]["visible_count"] == 2
    assert console.build("run-56", privacy="sensitive")["summary"]["visible_count"] == 1
    assert console.build("run-56", visibility="any_provider")["summary"]["visible_count"] == 1
    assert console.build("run-56", query="failing symbol")["summary"]["visible_count"] == 1


def test_token_summary_distinguishes_selected_from_total(tmp_path):
    seed(tmp_path)
    summary = ContextManifestConsole(tmp_path).build("run-56")["summary"]
    assert summary["selected_token_estimate"] == 11
    assert summary["total_token_estimate"] == 23


def test_projection_is_restart_stable_and_verifiable(tmp_path):
    seed(tmp_path)
    first = ContextManifestConsole(tmp_path).build("run-56")
    second_console = ContextManifestConsole(tmp_path)
    second = second_console.build("run-56")
    assert first["projection_digest"] == second["projection_digest"]
    assert second_console.verify(second)


def test_projection_tampering_is_detected(tmp_path):
    seed(tmp_path)
    console = ContextManifestConsole(tmp_path)
    view = console.build("run-56")
    view["cards"][0]["status"] = "ADMITTED"
    assert not console.verify(view)


def test_console_never_grants_admission_or_execution(tmp_path):
    seed(tmp_path)
    view = ContextManifestConsole(tmp_path).build("run-56")
    assert view["grants_model_admission"] is False
    assert view["grants_execution_authority"] is False
    assert all(card["grants_model_admission"] is False for card in view["cards"])


def test_frontend_contains_context_manifest_workspace():
    html = Path("app/frontend/index.html").read_text(encoding="utf-8")
    assert 'id="contextManifestCards"' in html
    assert 'id="loadContextManifest"' in html
    assert "/console/context" in html
    assert "Suggestions stay unselected" in html
