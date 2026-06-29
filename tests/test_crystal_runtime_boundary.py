import pytest

from app.kernel.compute.crystal_runtime_boundary import CrystalRuntimeBoundary
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway
from app.kernel.compute.enterprise import EnterpriseManager
from app.kernel.compute.integration_harness import BeastIntegrationHarness
from app.kernel.compute.crystal_staleness_policy import (
    CrystalReusePolicySnapshot,
    CrystalRuntimeContext,
    CrystalStalenessPolicy,
)
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.execution.execute import Executor
from app.kernel.governance.reason import GovernanceDecision, GovernanceResult
from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet
from app.kernel.security.agent_passport import AgentPassportPolicy
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.storage.memory_hull import MemoryHull


class FastReadiness(ProductionReadinessHardeningGauntlet):
    def production_ops_gate(self):
        return {
            "beast_object_type": "production_ops_hardening_gate",
            "status": "satisfied",
            "lab_status": "satisfied",
            "checks": {"executor_harness_test": True},
            "external_checks": {},
            "claim_boundary": "test gate",
        }


def _integration_harness(tmp_path, provider_executor):
    seal = ResidueSeal(tmp_path / "keys")
    hull = MemoryHull(tmp_path / "vault", seal=seal)
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        memory_hull=hull,
        seal=seal,
    )
    return BeastIntegrationHarness(
        passport_policy=AgentPassportPolicy(seal=seal, sign_decisions=True),
        crystal_gateway=gateway,
        residue_seal=seal,
        memory_hull=hull,
        enterprise_manager=EnterpriseManager(db_path=str(tmp_path / "enterprise.db")),
        readiness=FastReadiness(tmp_path / "readiness"),
        provider_executor=provider_executor,
    )


def test_staleness_policy_blocks_repo_lattice_and_risk_drift():
    result = CrystalStalenessPolicy().evaluate(
        CrystalReusePolicySnapshot(
            repo_fingerprint="repo-a",
            test_fingerprint="tests-a",
            tool_contract_hash="tools-a",
            skill_tree_hash="skills-a",
            lattice_hash="lattice-a",
            risk_tier="medium",
        ),
        CrystalRuntimeContext(
            repo_fingerprint="repo-b",
            test_fingerprint="tests-a",
            tool_contract_hash="tools-b",
            skill_tree_hash="skills-a",
            lattice_hash="lattice-b",
            risk_tier="high",
            approval_present=False,
        ),
    )

    assert result["reuse_allowed"] is False
    assert result["quarantine_required"] is True
    assert {item["field"] for item in result["failures"]} == {
        "repo_fingerprint",
        "tool_contract_hash",
        "lattice_hash",
        "risk_tier",
    }


def test_crystal_runtime_boundary_reuses_before_provider(tmp_path):
    boundary = CrystalRuntimeBoundary(tmp_path)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "classify retry timeout"}],
        model="proof-model",
        max_tokens=32,
        metadata={"task_class": "boundary_test", "repo_fingerprint": "repo-boundary"},
    )
    request = boundary.request_from_ir(ir, "openai")
    boundary.gateway.record_execution_response(
        request,
        "COMPLETE: retry with bounded exponential backoff.",
        route="teacher",
        engine="external_teacher",
        verified=True,
        avoided_tokens_estimate=44,
        evidence={"local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}]},
        write_memory=True,
    )

    decision = boundary.decide_for_ir(ir, "openai")
    assert decision["should_execute_provider"] is False
    assert decision["proof_local"]["beast_object_type"] == "proof_local_crystal_admission_receipt"
    assert decision["proof_local"]["reuse_allowed"] is True
    response = boundary.response_from_decision(ir, decision["decision"])
    assert response["edgek_crystal_runtime"]["provider_execution_requested"] is False
    assert "bounded exponential backoff" in response["choices"][0]["message"]["content"]


def test_crystal_runtime_boundary_blocks_reuse_on_proof_local_mutation(tmp_path):
    boundary = CrystalRuntimeBoundary(tmp_path)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "classify retry timeout"}],
        model="proof-model",
        max_tokens=32,
        metadata={
            "task_class": "boundary_mutation",
            "repo_fingerprint": "repo-good",
            "expected_provider_fingerprint": "provider-a",
            "actual_provider_fingerprint": "provider-b",
            "expected_lattice_hash": "lattice-a",
            "actual_lattice_hash": "lattice-a",
        },
    )
    request = boundary.request_from_ir(ir, "openai")
    boundary.gateway.record_execution_response(
        request,
        "COMPLETE: this cached answer must not be reused after provider drift.",
        route="teacher",
        engine="external_teacher",
        verified=True,
        avoided_tokens_estimate=44,
        evidence={"local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}]},
        write_memory=True,
    )

    decision = boundary.decide_for_ir(ir, "openai")

    assert decision["should_execute_provider"] is True
    assert decision["decision"] is None
    assert decision["reason"] == "proof_local_admission_blocked_reuse"
    assert decision["proof_local"]["reuse_allowed"] is False
    assert decision["proof_local"]["blockers"][0]["reason"] == "provider_fingerprint_mismatch"
    assert decision["quarantine"]["quarantined_count"] >= 1
    replay_after_quarantine = boundary.gateway.decide(request, seal_decision=False)
    assert replay_after_quarantine.action == "execute_local_cpu"


def test_crystal_runtime_boundary_quarantines_stale_policy_credit(tmp_path):
    boundary = CrystalRuntimeBoundary(tmp_path)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "stale repo should quarantine"}],
        model="proof-model",
        max_tokens=32,
        metadata={
            "task_class": "boundary_stale_quarantine",
            "repo_fingerprint": "repo-a",
            "expected_crystal_policy": {
                "repo_fingerprint": "repo-a",
                "test_fingerprint": "tests-a",
                "tool_contract_hash": "tools-a",
                "skill_tree_hash": "skills-a",
                "lattice_hash": "lattice-a",
                "risk_tier": "low",
            },
            "actual_runtime_context": {
                "repo_fingerprint": "repo-b",
                "test_fingerprint": "tests-a",
                "tool_contract_hash": "tools-a",
                "skill_tree_hash": "skills-a",
                "lattice_hash": "lattice-a",
                "risk_tier": "low",
                "approval_present": True,
            },
        },
    )
    request = boundary.request_from_ir(ir, "openai")
    record = boundary.gateway.record_execution_response(
        request,
        "COMPLETE: stale quarantine target.",
        route="teacher",
        engine="external_teacher",
        verified=True,
        avoided_tokens_estimate=44,
        evidence={"local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}]},
        write_memory=True,
    )

    decision = boundary.decide_for_ir(ir, "openai")

    assert decision["reason"] == "staleness_policy_blocked_reuse"
    assert decision["quarantine"]["quarantined_count"] >= 1
    credit = boundary.gateway.storage.credits[record["semantic_credit_id"]]
    assert credit.reuse_state == "stale"
    assert credit.metadata["quarantine"]["reason"] == "staleness_policy_blocked_reuse"


def test_crystal_runtime_boundary_records_provider_result_for_future_reuse(tmp_path):
    boundary = CrystalRuntimeBoundary(tmp_path)
    request = CrystalReuseRequest(
        prompt="summarize local crystal boundary",
        model="proof-model",
        task_class="boundary_record",
        repo_fingerprint="repo-boundary",
        provider="openai",
    )
    provider_response = {
        "choices": [{"message": {"content": "COMPLETE: local crystal boundary recorded."}}],
        "usage": {"total_tokens": 52, "prompt_tokens": 20, "completion_tokens": 32},
    }

    record = boundary.record_provider_result(
        request,
        provider_response,
        route="openai",
        engine="external_teacher",
        verified=True,
        evidence={"local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}]},
    )

    assert record["promotion_allowed"] is True
    replay = boundary.gateway.decide(request, seal_decision=False)
    assert replay.action in {"reuse_answer", "reuse_semantic_credit"}


@pytest.mark.asyncio
async def test_executor_uses_crystal_runtime_boundary_before_provider(tmp_path):
    executor = Executor()
    executor.crystal_runtime_boundary = CrystalRuntimeBoundary(tmp_path)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "executor should reuse this"}],
        model="gpt-test",
        max_tokens=32,
        metadata={"task_class": "executor_boundary", "repo_fingerprint": "repo-executor"},
    )
    request = executor.crystal_runtime_boundary.request_from_ir(ir, "openai")
    executor.crystal_runtime_boundary.gateway.record_execution_response(
        request,
        "COMPLETE: executor reused crystal runtime.",
        route="teacher",
        engine="external_teacher",
        verified=True,
        avoided_tokens_estimate=61,
        evidence={"local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}]},
        write_memory=True,
    )

    response = await executor.execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["edgek_runtime"]["provider"] == "beast_crystal_runtime"
    assert response["edgek_crystal_runtime"]["provider_execution_requested"] is False
    harness_receipt = response["edgek_crystal_runtime"]["harness_receipt"]
    assert harness_receipt["beast_object_type"] == "beast_crystal_runtime_harness_receipt"
    assert harness_receipt["provider_result"]["called"] is False
    assert harness_receipt["residue_seal"]["purpose"] == "beast_crystal_runtime_harness_receipt"
    assert response["edgek_crystal_runtime"]["proof_local"]["reuse_allowed"] is True
    assert response["choices"][0]["message"]["content"] == "COMPLETE: executor reused crystal runtime."


@pytest.mark.asyncio
async def test_executor_records_streaming_provider_result_as_crystal(tmp_path):
    executor = Executor()
    executor.crystal_runtime_boundary = CrystalRuntimeBoundary(tmp_path)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "stream and crystallize this"}],
        model="gpt-test",
        max_tokens=32,
        stream=True,
        metadata={
            "task_class": "executor_stream_boundary",
            "repo_fingerprint": "repo-stream",
            "stream_interception_enabled": True,
            "simulated_stream_text": '{"result":"COMPLETE: streamed crystal recorded"}',
            "stream_baseline_output_tokens": 80,
        },
    )

    response = await executor.execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["edgek_runtime"]["provider"] == "openai"
    assert response["edgek_crystal_record"]["semantic_credit_id"].startswith("scc_")
    assert response["edgek_crystal_record"]["promotion_allowed"] is True
    replay = executor.crystal_runtime_boundary.decide_for_ir(
        EdgeKIR(
            messages=ir.messages,
            model=ir.model,
            max_tokens=32,
            metadata={"task_class": "executor_stream_boundary", "repo_fingerprint": "repo-stream"},
        ),
        "openai",
    )
    assert replay["should_execute_provider"] is False


@pytest.mark.asyncio
async def test_executor_provider_fallback_runs_through_full_integration_harness(tmp_path):
    def provider(request):
        return {
            "response": "COMPLETE: full harness provider fallback executed.",
            "provider": request.provider,
            "model": request.model,
            "cost_usd": 0.0,
            "total_tokens": 37,
        }

    executor = Executor()
    executor.crystal_runtime_boundary = CrystalRuntimeBoundary(tmp_path / "runtime")
    executor.integration_harness = _integration_harness(tmp_path / "harness", provider)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "force provider fallback through harness"}],
        model="gpt-test",
        max_tokens=32,
        metadata={"task_class": "executor_harness_fallback", "repo_fingerprint": "repo-harness"},
    )

    response = await executor.execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    harness = response["edgek_integration_harness_receipt"]
    assert response["edgek_runtime"]["provider"] == "beast_integration_harness"
    assert harness["beast_object_type"] == "beast_thin_integration_harness_receipt"
    assert harness["provider_result"]["called"] is True
    assert harness["verification"]["verified"] is True
    assert harness["crystal_record"]["memory_hull"]["verified"] is True
    assert harness["residue_seal"]["purpose"] == "beast_thin_integration_harness_receipt"
