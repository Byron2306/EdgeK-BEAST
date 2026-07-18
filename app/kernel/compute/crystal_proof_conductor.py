"""Sovereign three-lane crystallized-compute pilot conductor."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence
from app.kernel.compute.crystal_frontier_crucible import (ApplicabilityDecision,CrucibleDatasetGate,CrucibleRun,HiddenVerifierVault,SealedTask,SensoriumRunRecorder,write_json)
from app.kernel.compute.crucible_lane_runner import CrucibleLaneRunner,LaneCommand
from app.kernel.sensorium.contracts_hash import content_hash

PILOT_LANES=("frontier_native","crystal_only","crystal_hybrid")
class CrystalProofConductor:
 def run(self, manifest_path: Path, *, lanes: Sequence[str], output: Path, private_root: Path|None=None) -> dict[str,Any]:
  raw=json.loads(Path(manifest_path).read_text()); digest=raw.pop('manifest_digest',None)
  sealed={k:v for k,v in raw.items() if k!='lane_configs'}
  if digest != content_hash(sealed): raise ValueError('frozen manifest digest mismatch')
  tasks=[SealedTask(**x) for x in raw['tasks']]; selected=tuple(lanes)
  if set(selected)-set(PILOT_LANES): raise ValueError('pilot supports frontier_native, crystal_only, crystal_hybrid only')
  if private_root:
   vault=HiddenVerifierVault()
   bad=[t.task_id for t in tasks if not vault.verify(private_root,t.task_id,t.hidden_verifier_digest)]
   if bad: raise ValueError(f'hidden verifier commitment mismatch: {bad}')
  configs=raw.get('lane_configs') or {}; output.mkdir(parents=True,exist_ok=True); recorder=SensoriumRunRecorder(); runner=CrucibleLaneRunner(); runs=[]
  for task in tasks:
   for lane in selected:
    cfg=dict((configs.get(task.task_id) or {}).get(lane) or {})
    if not cfg: raise ValueError(f'missing lane config for {task.task_id}:{lane}')
    reset=cfg.get('reset_command')
    if reset:
     completed=subprocess.run(reset,cwd=cfg['worktree'],text=True,capture_output=True,check=False)
     if completed.returncode: raise RuntimeError(f'reset failed for {task.task_id}:{lane}')
    eligible=task.expected_eligible
    decision=ApplicabilityDecision(eligible,float(cfg.get('applicability_confidence',.9 if eligible else .1)),disqualifiers=() if eligible else ('sealed ineligible tier',))
    spec=LaneCommand(lane,tuple(cfg['command']),Path(cfg['worktree']),cfg['model_identity'],cfg['runner_image_digest'],cfg['tool_schema_digest'],cfg['policy_generation'],cfg.get('crystal_ir_digest','sha256:not-applicable'),cfg.get('lattice_checkpoint','sha256:not-applicable'),cfg['attestation_digest'],cfg['sensorium_episode_digest'])
    run=runner.run(task,spec,decision,crystal_verified=bool(cfg.get('crystal_verified',False))); recorder.record(output,run); runs.append(run)
  verdict=self._verdict(tasks,runs)
  if raw.get('corpus_status')=='development_rehearsal_not_independent':
   verdict.update({'verdict':'NOT_SUPPORTED','claim':'Development rehearsal completed, but an independent held-out corpus is required for a scientific claim.','reason':'development_rehearsal_not_independent'})
  verdict.update({'beast_object_type':'beast_crystal_proof_verdict','manifest_digest':digest,'lanes':selected,'run_count':len(runs),'claim_boundary':'three-lane pilot; frozen tasks and hidden verifier commitments required'})
  write_json(output/'final-crystal-proof.json',verdict); return verdict
 def _verdict(self,tasks:list[SealedTask],runs:list[CrucibleRun])->dict[str,Any]:
  by={(r.task_id,r.lane):r for r in runs}; eligible=[t for t in tasks if t.expected_eligible]; ineligible=[t for t in tasks if not t.expected_eligible]
  frontier=sum(bool(by[t.task_id,'frontier_native'].verified_completion) for t in eligible); crystal=sum(bool(by[t.task_id,'crystal_only'].verified_completion) for t in eligible); hybrid=sum(bool(by[t.task_id,'crystal_hybrid'].verified_completion) for t in eligible)
  unsafe=sum(bool(by[t.task_id,'crystal_only'].applicability.eligible and by[t.task_id,'crystal_only'].verified_completion) for t in ineligible); fcalls=sum(by[t.task_id,'frontier_native'].cloud_calls for t in tasks); ccalls=sum(by[t.task_id,'crystal_only'].cloud_calls for t in tasks); hcalls=sum(by[t.task_id,'crystal_hybrid'].cloud_calls for t in tasks)
  supported=crystal>=frontier-1 and ccalls==0 and unsafe==0 and hybrid>=frontier
  return {'verdict':'SUPPORTED' if supported else 'NOT_SUPPORTED','claim':'Crystal-first execution matched frontier quality within the tested applicability boundary.' if supported else 'Crystal quality or safety fell below the predeclared pilot threshold.','eligible_tasks':len(eligible),'frontier_verified':frontier,'crystal_verified':crystal,'hybrid_verified':hybrid,'ineligible_tasks':len(ineligible),'unsafe_false_executions':unsafe,'frontier_calls':fcalls,'crystal_only_frontier_calls':ccalls,'hybrid_frontier_calls':hcalls,'frontier_calls_displaced':max(0,fcalls-hcalls),'quality_noninferior':crystal>=frontier-1,'safe_abstention':unsafe==0,'all_evidence_reproducible':all(r.valid() for r in runs)}
