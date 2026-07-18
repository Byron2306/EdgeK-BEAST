#!/usr/bin/env python3
"""Exercise all Crucible plumbing with deterministic dummy lanes; never claim science."""
import argparse,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.crystal_frontier_crucible import *
from app.kernel.compute.crucible_lane_runner import CrucibleLaneRunner,LaneCommand
def main():
 p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--output',required=True);a=p.parse_args();m=json.loads(Path(a.manifest).read_text());tasks=[SealedTask(**x) for x in m['tasks']];o=Path(a.output);o.mkdir(parents=True,exist_ok=True);runner=CrucibleLaneRunner(timeout_seconds=30); recorder=SensoriumRunRecorder();runs=[]
 for t in tasks:
  for lane in LANES:
   decision=ApplicabilityDecision(t.expected_eligible,.9 if t.expected_eligible else .1,disqualifiers=() if t.expected_eligible else ('tier outside envelope',))
   body={'verified_completion': lane!='placebo_crystal','hard_gates':{'development_protocol':True},'rollback_verified':True}
   cmd=(sys.executable,'-c',f'import json; print(json.dumps({body!r}))')
   spec=LaneCommand(lane,cmd,o,'development-model','sha256:development-image','sha256:development-tools','development-policy','sha256:development-ir','sha256:development-lattice','sha256:development-attestation','sha256:development-sensorium')
   run=runner.run(t,spec,decision,crystal_verified=t.expected_eligible,placebo=(lane=='placebo_crystal')); recorder.record(o,run); runs.append(run)
 gate=CrucibleDatasetGate().validate(tasks,runs); stats=StatisticalEvidenceEngine(seed=0).evaluate(tasks,runs,CrucibleHypotheses()); packet,key=BlindReviewChamber().packet(runs,seed=0)
 write_json(o/'dataset-gate.json',gate);write_json(o/'blind-review.json',{'rows':packet,'rehearsal':True});write_json(o/'blind-key.private.json',key);write_json(o/'statistics.json',stats);write_json(o/'public-evidence.json',{**PublicEvidenceExporter().export(m,stats,runs),'rehearsal_only':True,'claim_boundary':'deterministic lane plumbing rehearsal; not H1-H4 evidence'})
 print(json.dumps({'dataset_valid':gate['valid'],'runs':len(runs),'output':str(o),'rehearsal_only':True}))
if __name__=='__main__':main()
