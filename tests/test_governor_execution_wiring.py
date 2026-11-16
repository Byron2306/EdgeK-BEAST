"""Execution-path wiring: local specialist rung, attested Quality Cascade admit, PSI shrink-only, RTK compression."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_swarm_specialist import mock_ollama  # noqa: E402

from app.kernel.agents.swarm_specialist import SwarmSpecialistDispatch  # noqa: E402
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor  # noqa: E402
from app.kernel.compute.perceive import EdgeKIR  # noqa: E402
from app.kernel.data_processing.cascade_output_compressor import EXACT_HEADER, compress_cascade_output  # noqa: E402
from app.kernel.data_processing.quality_cascade import QualityCascade  # noqa: E402
from app.kernel.governance.compute_governor import ComputeGovernor  # noqa: E402
from app.kernel.governance.governor_spine import (  # noqa: E402
    CASCADE_ATTESTATIONS_ENV,
    ComputeGovernorSpine,
    GovernorReceiptLog,
)
from app.kernel.governance.reason import GovernanceDecision, GovernanceResult  # noqa: E402
from app.kernel.governance.runtime import RuntimeGovernor  # noqa: E402

SPECIALIST = {"execution_mode": "local_specialist_adapter", "model_ref": "ollama://beast-specialist-x",
              "boundary_checks_passed": True, "confidence_score": 0.9}


@pytest.fixture(autouse=True)
def attest_path(tmp_path, monkeypatch):
    monkeypatch.setenv(CASCADE_ATTESTATIONS_ENV, str(tmp_path / "attest.jsonl"))
    monkeypatch.delenv("BEAST_QUALITY_CASCADE_SKIP", raising=False)


def passing_report(tmp_path):
    cascade = QualityCascade(policies={"providers": {"nvidia": {"enabled": True}}})
    report = cascade.run({"task_id": "t1", "inputs": {"provider": "nvidia"}},
                         {"provider": "nvidia", "preferred_order": ["provider_policy"]}, str(tmp_path))
    assert report["attestation"]["digest"].startswith("sha256:")
    return report


def interceptor(tmp_path):
    spine = ComputeGovernorSpine(receipts=GovernorReceiptLog(tmp_path / "r.jsonl"), enforce=True)
    return InferenceComputeInterceptor(governor=ComputeGovernor(mode="shadow", spine=spine))


def ir(**metadata):
    return EdgeKIR(messages=[{"role": "user", "content": "explain this"}], model="m", max_tokens=32,
                   metadata={"provider": "nvidia", **metadata})


# -- Quality Cascade → evaluate()/admit() ----------------------------------------------------------------------
def test_attested_passing_cascade_admits_cloud_with_enforcement(tmp_path):
    report = passing_report(tmp_path)
    assert report["verification_accepted"] is True
    compute = interceptor(tmp_path).begin(ir(quality_cascade=report), "nvidia")
    assert compute.gate.allowed is True
    assert compute.gate.governor["outcome"] == "admit"


def test_no_cascade_still_escalates_with_enforcement(tmp_path):
    compute = interceptor(tmp_path).begin(ir(), "nvidia")
    assert compute.gate.allowed is False


def test_client_forged_cascade_report_never_admits(tmp_path):
    report = passing_report(tmp_path)
    forged = {**report, "task_id": "someone-else"}
    assert interceptor(tmp_path).begin(ir(quality_cascade=forged), "nvidia").gate.allowed is False
    claimed = {"beast_object_type": "quality_cascade_report", "status": "passed", "verification_accepted": True}
    assert interceptor(tmp_path).begin(ir(quality_cascade=claimed), "nvidia").gate.allowed is False


# -- PSI pressure shrinks only ---------------------------------------------------------------------------------
def test_psi_pressure_never_refuses_runtime_admission(tmp_path):
    from app.kernel.governance.psi_governor import PsiGovernor

    for resource in ("cpu", "memory", "io"):
        (tmp_path / resource).write_text("some avg10=95 avg60=0 avg300=0 total=0\nfull avg10=95 avg60=0 avg300=0 total=0\n")
    governor = RuntimeGovernor(db_path=str(tmp_path / "runtime.db"), psi_governor=PsiGovernor(tmp_path))
    admission = governor.begin_execution("local", "model", metadata={"lane": "background"})
    assert admission.allowed is True and 0 < admission.pressure_factor < 1.0


# -- Executor: local specialist rung ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_executor_dispatches_admitted_specialist_instead_of_provider(tmp_path, monkeypatch):
    import app.kernel.execution.execute as execute_module
    from app.kernel.execution.execute import Executor

    runtime = RuntimeGovernor(db_path=str(tmp_path / "runtime.db"))
    monkeypatch.setattr(execute_module, "runtime_governor", runtime)
    monkeypatch.setenv("BEAST_SWARM_SPECIALIST", "1")
    executor = Executor()

    async def nominate(_ir):
        return dict(SPECIALIST)

    monkeypatch.setattr(executor.dispatcher, "route", nominate)
    runner, calls = mock_ollama()
    executor._swarm_specialist = SwarmSpecialistDispatch(
        runner=runner, governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(None), enforce=True),
        quality_gate=lambda text, request: (True, "quality_cascade_passed"))
    request = EdgeKIR(messages=[{"role": "user", "content": "write add"}], model="gpt-3.5-turbo",
                      max_tokens=32, metadata={"provider": "openai"})
    response = await executor.execute(request, GovernanceResult(decision=GovernanceDecision.ALLOW))
    assert response["edgek_provider"] == "beast_local_specialist"
    assert response["model"] == "qwen3:4b"
    assert response["edgek_local_specialist"]["proposal_only"] is True
    assert runtime.state()["attempts"].get("started", 0) == 0 and runtime.state()["attempts"].get("succeeded", 0) == 0
    assert any(path == "/api/generate" for path, _ in calls)


@pytest.mark.asyncio
async def test_executor_specialist_flag_off_never_calls_ollama(tmp_path, monkeypatch):
    from app.kernel.execution.execute import Executor

    monkeypatch.delenv("BEAST_SWARM_SPECIALIST", raising=False)
    executor = Executor()
    runner, calls = mock_ollama()
    executor._swarm_specialist = SwarmSpecialistDispatch(runner=runner, governor=ComputeGovernorSpine(enforce=True))
    from app.kernel.compute.adaptive_router import AdaptiveRouter

    decision = AdaptiveRouter().route(similarity=0.9, specialist=SPECIALIST)
    assert await executor._try_local_specialist(ir(), decision, None) is None
    assert calls == []


# -- RTK compression of cascade output -------------------------------------------------------------------------
PYTEST_OUT = """============ test session starts ============
collected 3 items

tests/test_x.py ..F

================= FAILURES =================
___________ test_add ___________
    def test_add():
>       assert add(2, 2) == 5
E       assert 4 == 5
E        +  where 4 = add(2, 2)

tests/test_x.py:12: AssertionError
========= short test summary info =========
FAILED tests/test_x.py::test_add - assert 4 == 5
""" + "\n".join(f"noise line {i}" for i in range(50))


def test_native_fallback_keeps_assertions_and_line_numbers_exact(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    out = compress_cascade_output(PYTEST_OUT, kind="test", edit_targets=["assert add(2, 2) == 5"])
    assert out["backend"] in {"beast_native_rtk_stub", "passthrough"} and out["safe"] is True
    for line in ("E       assert 4 == 5", "tests/test_x.py:12: AssertionError",
                 "FAILED tests/test_x.py::test_add - assert 4 == 5", ">       assert add(2, 2) == 5"):
        assert line in out["content"]


def test_rtk_binary_used_when_present_and_exact_lines_restored(tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "rtk"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\ncat >/dev/null\necho '1 failed, 2 passed'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    out = compress_cascade_output(PYTEST_OUT, kind="test", edit_targets=["assert add(2, 2) == 5"])
    assert out["backend"] == "rtk_binary" and out["rtk_command"] == "pipe --filter pytest"
    assert out["content"].startswith("1 failed, 2 passed")
    assert EXACT_HEADER in out["content"] and out["exact_lines_restored"] >= 4
    assert "tests/test_x.py:12: AssertionError" in out["content"] and out["safe"] is True
    assert out["compressed_chars"] < out["original_chars"]


def test_quality_cascade_command_output_is_rtk_compressed(tmp_path):
    result = QualityCascade({})._run_command([sys.executable, "-c", "print('E   assert 1 == 2'); print('x.py:3: E1')"],
                                             tmp_path, 30)
    assert "E   assert 1 == 2" in result["output_compact"]
    assert result["output_compression"]["safe"] is True
    assert result["stdout"].startswith("E   assert 1 == 2")
