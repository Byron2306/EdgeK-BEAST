import sys
from pathlib import Path
from app.kernel.compute.crucible_lane_runner import CrucibleLaneRunner,LaneCommand
from app.kernel.compute.crystal_frontier_crucible import ApplicabilityDecision,SealedTask
def task(): return SealedTask('t','f','C1','r','s','v',True)
def spec(tmp,lane='crystal_only'):
 return LaneCommand(lane,(sys.executable,'-c','import json; print(json.dumps({"verified_completion":True,"hard_gates":{"tests":True},"rollback_verified":True}))'),tmp,'model','image','tools','policy','ir','lattice','attest','episode')
def test_crystal_lane_runs_only_with_verified_applicability(tmp_path):
 r=CrucibleLaneRunner().run(task(),spec(tmp_path),ApplicabilityDecision(True,.9),crystal_verified=True)
 assert r.verified_completion and r.valid()
def test_crystal_only_refuses_ineligible_task_without_execution(tmp_path):
 r=CrucibleLaneRunner().run(task(),spec(tmp_path),ApplicabilityDecision(False,.1),crystal_verified=False)
 assert not r.verified_completion and r.hard_gates['abstention']
