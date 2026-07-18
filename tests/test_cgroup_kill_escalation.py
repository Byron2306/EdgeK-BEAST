import base64
import time

import pytest

from app.kernel.execution.cgroup_capsule import CgroupMissionCapsule
from app.kernel.execution.cgroup_kill_escalation import (
    CGROUP_KILL_AUDIENCE,
    CGROUP_KILL_AUTHORITY,
    CgroupKillEscalationCoordinator,
    CgroupKillEscalationRequest,
)
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.runtime import SensoriumRuntime


class SyntheticKernelKillCapsule(CgroupMissionCapsule):
    def kill(self, authorization):
        receipt = super().kill(authorization)
        (self.path / "cgroup.procs").write_text("", encoding="utf-8")
        (self.path / "cgroup.events").write_text("populated 0\n", encoding="utf-8")
        return receipt


def _capsule(tmp_path):
    capsule = SyntheticKernelKillCapsule(tmp_path, "mission-kill", synthetic=True)
    capsule.path.mkdir(parents=True)
    (capsule.path / "cgroup.procs").write_text("101\n102\n", encoding="utf-8")
    (capsule.path / "cgroup.events").write_text("populated 1\n", encoding="utf-8")
    (capsule.path / "cgroup.kill").write_text("", encoding="utf-8")
    return capsule


def _request(capsule):
    return CgroupKillEscalationRequest(
        mission_id="mission-kill",
        retirement_request_digest="sha256:retirement",
        cgroup_path=str(capsule.path),
        expected_member_pids=(101, 102),
        policy_generation="policy:kill:1",
        appraisal_ref="appraisal:kill:1",
        reason="descendants retained the governed listener",
    )


def _authority(request, now):
    operator = {
        "approval_receipt_id": "operator:cgroup-kill:1",
        "approved_by": "test-operator",
        "request_digest": request.request_digest,
        "action": CGROUP_KILL_AUTHORITY,
        "destructive": True,
    }
    appraisal = {
        "appraisal_ref": request.appraisal_ref,
        "request_digest": request.request_digest,
        "policy_generation": request.policy_generation,
        "audience": CGROUP_KILL_AUDIENCE,
        "state": "verified",
        "expires_at": now + 60,
    }
    capability = {
        "capability_id": "capability:cgroup-kill:1",
        "request_digest": request.request_digest,
        "authority": CGROUP_KILL_AUTHORITY,
        "expires_at": now + 60,
        "nonce": "kill-once",
        "signature": base64.b64encode(b"isolated-test-signature").decode(),
        "audience": CGROUP_KILL_AUDIENCE,
        "policy_generation": request.policy_generation,
        "appraisal_ref": request.appraisal_ref,
    }
    return operator, appraisal, capability


def test_cgroup_kill_requires_separate_exact_one_use_authority(tmp_path):
    capsule = _capsule(tmp_path)
    ledger = OneUseCapabilityLedger(path=tmp_path / "capabilities.sqlite", require_verifier=False)
    request = _request(capsule)
    now = time.time()
    operator, appraisal, capability = _authority(request, now)

    sensorium = SensoriumRuntime(capacity=32, export_root=tmp_path / "sensorium", boot_id="boot-kill")
    receipt = CgroupKillEscalationCoordinator(capsule, ledger, sensorium=sensorium).execute(
        request,
        operator_approval=operator,
        arda_appraisal=appraisal,
        one_use_capability=capability,
        now=now,
    )

    assert receipt.final_status == "verified_cgroup_kill"
    assert receipt.populated_zero_observed is True
    assert (capsule.path / "cgroup.kill").read_text(encoding="utf-8") == "1\n"
    assert ledger.consumed("capability:cgroup-kill:1") is True
    receipt.validate()
    assert sensorium.sequencer.latest(1)[0].event.event_type == "cgroup.kill_verified"


def test_membership_drift_refuses_before_consuming_kill_capability(tmp_path):
    capsule = _capsule(tmp_path)
    ledger = OneUseCapabilityLedger(path=tmp_path / "capabilities.sqlite", require_verifier=False)
    request = _request(capsule)
    now = time.time()
    operator, appraisal, capability = _authority(request, now)
    (capsule.path / "cgroup.procs").write_text("101\n999\n", encoding="utf-8")
    sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-refusal")

    with pytest.raises(PermissionError, match="membership drifted"):
        CgroupKillEscalationCoordinator(capsule, ledger, sensorium=sensorium).execute(
            request,
            operator_approval=operator,
            arda_appraisal=appraisal,
            one_use_capability=capability,
            now=now,
        )
    assert ledger.consumed("capability:cgroup-kill:1") is False
    assert (capsule.path / "cgroup.kill").read_text(encoding="utf-8") == ""
    assert sensorium.sequencer.latest(1)[0].event.event_type == "cgroup.kill_refused"
