from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.approvals.capability_issuer import RequestBoundCapability
from app.kernel.approvals.capability_runtime import ExactStepResumeRuntime
from app.kernel.approvals.digests import sha256_digest
from app.kernel.approvals.models import ApprovalContractFactory


def _fixture(root, *, step_id="step_47"):
    factory = ApprovalContractFactory()
    request = factory.create_request({
        "approval_id": "approval_47",
        "run_id": "run_47",
        "step_id": step_id,
        "agent_id": "agent:beast",
        "model_id": "model:coder",
        "provider_id": "provider:local",
        "tool_id": "workspace.read_range",
        "tool_version": "1",
        "arguments": {"path": "app/example.py", "start_line": 1, "end_line": 20},
        "workspace_id": "workspace:repo",
        "execution_target": "local",
        "affected_resources": ["app/example.py"],
        "data_egress": [],
        "expected_side_effects": [],
        "risk_class": "LOW",
        "reason": "Read the approved source range",
        "budget_impact": {"tool_calls": 1},
        "evidence_policy": {"level": "summary"},
        "requested_scope": "ONCE",
        "permission_mode": "GUIDED",
        "policy_generation": "policy:47",
        "expiry_seconds": 600,
    })
    now = datetime.now(timezone.utc)
    capability = RequestBoundCapability(
        capability_id="cap_47",
        approval_id=request["approval_id"],
        grant_id="grant_47",
        grant_digest=sha256_digest({"grant": 47}),
        scope_match_digest=sha256_digest({"match": 47}),
        request_digest=request["request_digest"],
        classification_digest=sha256_digest({"classification": 47}),
        decision_digest=sha256_digest({"decision": 47}),
        run_id=request["run_id"],
        step_id=request["step_id"],
        tool_id=request["tool_id"],
        tool_version=request["tool_version"],
        workspace_id=request["workspace_id"],
        execution_target=request["execution_target"],
        policy_generation=request["policy_generation"],
        call_identity_digest=sha256_digest({"call": 47}),
        scope="ONCE",
        audience="beast-tool-runtime",
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        nonce="nonce47",
        single_use=True,
    ).to_dict()
    engine = AgentRunEngine(root)
    engine.create_run(session_id="session_47", objective="test", run_id="run_47")
    engine.store.transition("run_47", "waiting_for_approval")
    engine.merge_checkpoint("run_47", {"suspended_step": {"step_id": step_id, "approval_id": "approval_47"}})
    return request, capability


def test_consumes_capability_and_resumes_exact_step(tmp_path):
    request, capability = _fixture(tmp_path)
    runtime = ExactStepResumeRuntime(tmp_path)
    receipt = runtime.consume_and_resume(capability=capability, request=request)
    assert receipt["capability_consumed"] is True
    assert receipt["run_resumed"] is True
    assert receipt["resume_state"] == "executing_tool"
    assert runtime.verify_receipt(receipt)
    run = runtime.engine.store.get_run("run_47")
    assert run["state"] == "executing_tool"
    assert run["checkpoint"]["approval_resume"]["step_id"] == "step_47"


def test_replay_is_denied_after_durable_consumption(tmp_path):
    request, capability = _fixture(tmp_path)
    runtime = ExactStepResumeRuntime(tmp_path)
    runtime.consume_and_resume(capability=capability, request=request)
    with pytest.raises(ValueError, match="already_consumed"):
        # Put the run back only to prove the durable ledger, not run state, blocks replay.
        runtime.engine.store.transition("run_47", "waiting_for_approval")
        runtime.consume_and_resume(capability=capability, request=request)


def test_wrong_suspended_step_is_denied_without_consumption(tmp_path):
    request, capability = _fixture(tmp_path, step_id="step_expected")
    runtime = ExactStepResumeRuntime(tmp_path)
    runtime.engine.merge_checkpoint("run_47", {"suspended_step": {"step_id": "step_other", "approval_id": "approval_47"}})
    with pytest.raises(ValueError, match="suspended run step"):
        runtime.consume_and_resume(capability=capability, request=request)
    assert runtime.consumptions.get("cap_47") is None


def test_request_binding_substitution_is_denied(tmp_path):
    request, capability = _fixture(tmp_path)
    changed = dict(request)
    changed["tool_id"] = "workspace.search"
    with pytest.raises(ValueError):
        ExactStepResumeRuntime(tmp_path).consume_and_resume(capability=capability, request=changed)


def test_expired_capability_is_denied(tmp_path):
    request, capability = _fixture(tmp_path)
    capability = dict(capability)
    capability["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    capability["capability_digest"] = sha256_digest({k: v for k, v in capability.items() if k != "capability_digest"})
    with pytest.raises(ValueError, match="invalid, tampered, or expired"):
        ExactStepResumeRuntime(tmp_path).consume_and_resume(capability=capability, request=request)


def test_tampered_capability_is_denied(tmp_path):
    request, capability = _fixture(tmp_path)
    capability = dict(capability)
    capability["tool_version"] = "999"
    with pytest.raises(ValueError, match="invalid, tampered, or expired"):
        ExactStepResumeRuntime(tmp_path).consume_and_resume(capability=capability, request=request)


def test_receipt_authority_widening_is_detected(tmp_path):
    request, capability = _fixture(tmp_path)
    runtime = ExactStepResumeRuntime(tmp_path)
    receipt = runtime.consume_and_resume(capability=capability, request=request)
    receipt["workspace_mutation_authorized"] = True
    assert runtime.verify_receipt(receipt) is False


def test_pending_consumption_survives_store_reopen(tmp_path):
    request, capability = _fixture(tmp_path)
    runtime = ExactStepResumeRuntime(tmp_path)
    runtime.consumptions.consume_pending(capability, consumed_at=datetime.now(timezone.utc))
    reopened = ExactStepResumeRuntime(tmp_path)
    pending = reopened.consumptions.pending_recovery(run_id="run_47")
    assert len(pending) == 1
    assert pending[0]["capability_id"] == "cap_47"
