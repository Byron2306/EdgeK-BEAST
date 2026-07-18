#!/usr/bin/env python3
"""Build a sealed *development* Crucible corpus from current BEAST task families.

This validates the laboratory pipeline only. Its tasks are not independent
enough to advance H1--H4.
"""
import argparse, hashlib, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.crystal_frontier_crucible import CrucibleHypotheses,HiddenVerifierVault,SealedTask,SealedTaskFoundry,StatisticalEvidenceEngine,preregistered_ablations,write_json
from app.kernel.compute.hard_coding_crystallization_gauntlet import hard_coding_task_specs
from app.kernel.sensorium.contracts_hash import content_hash
def digest(value): return 'sha256:'+hashlib.sha256(value.encode()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='benchmarks/results/crystalbench-development-pilot');p.add_argument('--with-demo-lanes',action='store_true');a=p.parse_args();root=Path(a.output); vault=HiddenVerifierVault();tasks=[]
 tiers=[('C0',True),('C1',True),('C2',True),('C3',True),('C5',False),('C6',False)]
 specs=hard_coding_task_specs()
 for index,(tier,eligible) in enumerate(tiers):
  spec=specs[index%len(specs)]; task_id=f'dev-{tier.lower()}-{spec.family}'
  verifier=(spec.tests_source+f'\n# tier={tier}').encode(); vd=vault.commit(root,task_id,verifier)
  tasks.append(SealedTask(task_id,spec.family,tier,digest(spec.broken_source+tier),digest(spec.family+tier),vd,eligible))
 h=CrucibleHypotheses();m=SealedTaskFoundry(h).manifest(tasks,branch_digest=digest('development-pilot'),lattice_digest=digest('unpromoted-development-lattice'),policy_digest=digest('crucible-v1'));m['power_analysis']={'frontier_rate_assumption':.6,'noninferiority_margin':h.noninferiority_margin,'alpha':.01,'power':.9,'required_binary_pairs':StatisticalEvidenceEngine.required_binary_pairs(frontier_rate=.6,noninferiority_margin=h.noninferiority_margin)};m['ablations']=preregistered_ablations()
 if a.with_demo_lanes:
  command=[sys.executable,'-c','import json; print(json.dumps({"verified_completion":True,"hard_gates":{"development_protocol":True},"rollback_verified":True}))']
  common={'command':command,'worktree':str(root),'model_identity':'development-demo','runner_image_digest':'sha256:development-image','tool_schema_digest':'sha256:development-tools','policy_generation':'development-policy','attestation_digest':'sha256:development-attestation','sensorium_episode_digest':'sha256:development-sensorium','crystal_ir_digest':'sha256:development-ir','lattice_checkpoint':'sha256:development-lattice','crystal_verified':True}
  m['lane_configs']={task.task_id:{lane:common for lane in ('frontier_native','crystal_only','crystal_hybrid')} for task in tasks}
 m['corpus_status']='development_rehearsal_not_independent';m['claim_boundary']='Validates sealing/lane/verifier mechanics only. It cannot advance frontier-quality hypotheses.'
 m['manifest_digest']=content_hash({k:v for k,v in m.items() if k not in {'manifest_digest','lane_configs'}});write_json(root/'sealed-manifest.json',m);print(m['manifest_digest'])
if __name__=='__main__':main()
