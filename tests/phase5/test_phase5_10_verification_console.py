from pathlib import Path
import pytest
from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.verification_console import VerificationConsole


def seed(tmp_path: Path):
    store=AgentRunStore(tmp_path)
    store.create_run(session_id="s", objective="verify", run_id="run-510", mode="agent")
    store.append_event("run-510", "agent.verify.focused.completed", {"check_id":"focus", "status":"passed", "command":"pytest -q tests/test_parser.py", "category":"focused_tests", "fresh":True, "evidence_digest":"sha256:focus", "step_id":"verify"})
    store.append_event("run-510", "agent.verify.package.completed", {"check_id":"package", "status":"reused", "command":"pytest -q tests", "category":"package_tests", "reused":True, "equivalence_proof_digest":"sha256:eq", "evidence_digest":"sha256:package", "promotion_relevant":True})
    store.append_event("run-510", "agent.verify.security.completed", {"check_id":"security", "status":"failed", "command":"bandit -r app", "category":"security", "ok":False, "stderr":"one finding", "exit_code":1, "evidence_digest":"sha256:security", "promotion_relevant":True})
    return "run-510"


def test_canonical_verification_projection(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid)
    assert c["status"]=="FAILED"
    assert c["summary"]["total_checks"]==3
    assert c["summary"]["counts"]["PASSED"]==1
    assert c["summary"]["counts"]["REUSED_WITH_PROOF"]==1
    assert c["summary"]["counts"]["FAILED"]==1


def test_verification_fields_are_operator_reviewable(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid)
    item=next(x for x in c["checks"] if x["check_id"]=="security")
    assert item["command"]=="bandit -r app"
    assert item["exit_code"]==1
    assert item["concise_output"]=="one finding"
    assert item["evidence_digest"]=="sha256:security"


def test_reuse_requires_visible_equivalence_proof(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid)
    item=next(x for x in c["checks"] if x["status"]=="REUSED_WITH_PROOF")
    assert item["freshness"]=="reused"
    assert item["equivalence_proof_digest"]=="sha256:eq"


def test_failed_promotion_relevant_check_blocks_readiness(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid)
    assert not c["promotion"]["verification_ready"]
    assert "security" in c["promotion"]["blocking_check_ids"]
    assert not c["promotion"]["promotion_authorized"]


def test_category_filter(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid, category="security")
    assert [x["check_id"] for x in c["checks"]]==["security"]


def test_status_filter(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid, status="PASSED")
    assert [x["check_id"] for x in c["checks"]]==["focus"]


def test_query_filter(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid, query="bandit")
    assert [x["check_id"] for x in c["checks"]]==["security"]


def test_invalid_filters_fail_closed(tmp_path):
    rid=seed(tmp_path)
    with pytest.raises(ValueError): VerificationConsole(tmp_path).build(rid, category="banana")
    with pytest.raises(ValueError): VerificationConsole(tmp_path).build(rid, status="sparkly")


def test_unknown_run_denied(tmp_path):
    with pytest.raises(KeyError): VerificationConsole(tmp_path).build("missing")


def test_tamper_detection_and_read_only_authority(tmp_path):
    rid=seed(tmp_path); c=VerificationConsole(tmp_path).build(rid)
    assert c["authority"]=="verification_console_read_only"
    assert not c["grants_promotion_authority"]
    c["grants_promotion_authority"]=True
    assert not VerificationConsole(tmp_path).verify(c)
