from pathlib import Path
import pytest
from app.kernel.operations_console.tool_approval_console import ToolApprovalCardsConsole
from app.kernel.agents.run_store import AgentRunStore


def seed(root: Path, run_id='run-58'):
    store=AgentRunStore(root)
    store.create_run(session_id="s", objective="x", run_id=run_id)
    return run_id


def test_empty_console_is_valid(tmp_path):
    rid=seed(tmp_path)
    c=ToolApprovalCardsConsole(tmp_path).build(rid)
    assert c['summary']['total_cards']==0
    assert ToolApprovalCardsConsole(tmp_path).verify(c)


def test_unknown_run_denied(tmp_path):
    with pytest.raises(KeyError): ToolApprovalCardsConsole(tmp_path).build('missing')


def test_invalid_status_denied(tmp_path):
    rid=seed(tmp_path)
    with pytest.raises(ValueError): ToolApprovalCardsConsole(tmp_path).build(rid,status='banana')


def test_read_only_authority(tmp_path):
    rid=seed(tmp_path); c=ToolApprovalCardsConsole(tmp_path).build(rid)
    assert c['authority']=='tool_approval_cards_console_read_only'
    assert not c['grants_execution_authority']


def test_tamper_detection(tmp_path):
    rid=seed(tmp_path); engine=ToolApprovalCardsConsole(tmp_path); c=engine.build(rid)
    c['grants_execution_authority']=True
    assert not engine.verify(c)


def test_status_filter_empty(tmp_path):
    rid=seed(tmp_path); c=ToolApprovalCardsConsole(tmp_path).build(rid,status='FAILED')
    assert c['cards']==[]


def test_query_filter_empty(tmp_path):
    rid=seed(tmp_path); c=ToolApprovalCardsConsole(tmp_path).build(rid,query='not-present')
    assert c['cards']==[]


def test_valid_actions_are_bounded():
    assert ToolApprovalCardsConsole._valid_actions({'status':'WAITING_FOR_APPROVAL'}) == ['APPROVE_ONCE','EDIT_AND_APPROVE_ONCE','REJECT','REQUEST_REPLAN']


def test_terminal_card_has_no_actions():
    assert ToolApprovalCardsConsole._valid_actions({'status':'CONSUMED'}) == []


def test_frontend_panel_present():
    html=Path('app/frontend/index.html').read_text()
    assert 'PHASE5_8_TOOL_APPROVAL_CARDS' in html
    assert 'toolApprovalCardsPanel' in html
