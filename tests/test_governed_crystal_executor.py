from app.kernel.compute.governed_crystal_executor import GovernedCrystalExecutor
from app.kernel.compute.port_conflict_crystal import PortConflictRepairCrystal


def plan():
    return PortConflictRepairCrystal().plan(requested_port=8005, listener=None, lease_match=False, process_start_verified=False, health_ok=False)


def test_crystal_execution_requires_authority():
    executor = GovernedCrystalExecutor(authorize=lambda request: False)
    result = executor.execute(plan())
    assert result.authorized is False
    assert result.effect["status"] == "denied"


def test_authorized_crystal_emits_effect_receipt():
    executor = GovernedCrystalExecutor(authorize=lambda request: request["crystal_id"].startswith("crystal:"))
    result = executor.execute(plan(), effect={"status": "bound", "port": 8005})
    assert result.authorized is True
    assert result.evidence_node_id.startswith("sha256:")
    assert len(executor.evidence.query("crystal_execution")) == 1

def test_physical_execution_requires_verification_and_can_rollback():
    rolled = []
    executor = GovernedCrystalExecutor(authorize=lambda request: True)
    result = executor.execute(plan(), actuator=lambda _: {"port": 8005}, verifier=lambda _p, _e: False, rollback=lambda _p, _e: rolled.append(True))
    assert result.physically_executed is True
    assert result.verified is False
    assert result.rolled_back is True
    assert result.authorized is True
    assert result.execution_completed is True
    assert result.rollback_attempted is True
    assert result.rollback_successful is True
    assert result.final_status == "rolled_back_after_verification_failure"
    assert rolled == [True]

def test_arda_appraisal_is_required_when_configured():
    executor=GovernedCrystalExecutor(authorize=lambda _:{"allowed":True}, require_appraisal=True, appraisal_ref="app:1", policy_generation="p1")
    denied=executor.execute(plan())
    assert denied.authorized is False
    executor=GovernedCrystalExecutor(authorize=lambda _:{"allowed":True,"appraisal":{"appraisal_ref":"app:1","policy_generation":"p1","state":"verified"}}, require_appraisal=True, appraisal_ref="app:1", policy_generation="p1")
    assert executor.execute(plan()).authorized is True
