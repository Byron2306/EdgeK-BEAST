import json,sys,subprocess
from pathlib import Path
from app.kernel.compute.crystal_frontier_crucible import CrucibleHypotheses,SealedTask,SealedTaskFoundry
from app.kernel.compute.crystal_proof_conductor import CrystalProofConductor
def test_three_lane_conductor_emits_single_supported_verdict(tmp_path):
 tasks=[SealedTask('eligible','family','C1','r1','s1','v1',True),SealedTask('negative','family','C5','r2','s2','v2',False)]
 manifest=SealedTaskFoundry(CrucibleHypotheses()).manifest(tasks,branch_digest='b',lattice_digest='l',policy_digest='p')
 command=[sys.executable,'-c','import json; print(json.dumps({"verified_completion":True,"hard_gates":{"tests":True},"cloud_calls":0,"rollback_verified":True}))']
 common={'command':command,'worktree':str(tmp_path),'model_identity':'model','runner_image_digest':'image','tool_schema_digest':'tools','policy_generation':'policy','attestation_digest':'attest','sensorium_episode_digest':'episode','crystal_ir_digest':'ir','lattice_checkpoint':'lattice','crystal_verified':True}
 manifest['lane_configs']={task.task_id:{'frontier_native':common,'crystal_only':common,'crystal_hybrid':common} for task in tasks}
 path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
 verdict=CrystalProofConductor().run(path,lanes=('frontier_native','crystal_only','crystal_hybrid'),output=tmp_path/'out')
 assert verdict['verdict']=='SUPPORTED' and verdict['unsafe_false_executions']==0 and (tmp_path/'out'/'final-crystal-proof.json').is_file()

def test_beast_cli_exposes_and_runs_crystal_proof(tmp_path):
 tasks=[SealedTask('eligible','family','C1','r','s','v',True)]
 manifest=SealedTaskFoundry(CrucibleHypotheses()).manifest(tasks,branch_digest='b',lattice_digest='l',policy_digest='p')
 command=[sys.executable,'-c','import json; print(json.dumps({"verified_completion":True,"hard_gates":{"tests":True},"rollback_verified":True}))']
 cfg={'command':command,'worktree':str(tmp_path),'model_identity':'model','runner_image_digest':'image','tool_schema_digest':'tools','policy_generation':'policy','attestation_digest':'attest','sensorium_episode_digest':'episode','crystal_ir_digest':'ir','lattice_checkpoint':'lattice','crystal_verified':True}
 manifest['lane_configs']={'eligible':{lane:cfg for lane in ('frontier_native','crystal_only','crystal_hybrid')}}; path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
 root=Path(__file__).resolve().parents[1]; completed=subprocess.run([str(root/'bin'/'beast'),'crystal-proof','run','--manifest',str(path),'--output',str(tmp_path/'cli-out')],cwd=root,text=True,capture_output=True,check=True)
 assert json.loads(completed.stdout)['verdict']=='SUPPORTED'
