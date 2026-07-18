#!/usr/bin/env python3
"""Package the crystallized-compute proof work without private verifier/key material."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=(
 'bin/beast','app/kernel/compute/crystal_frontier_crucible.py','app/kernel/compute/crucible_lane_runner.py',
 'app/kernel/compute/crystalbench_authoring.py','app/kernel/compute/crystal_proof_conductor.py',
 'app/kernel/compute/discovery_agnostic_reuse.py','app/kernel/compute/adaptive_dispatcher.py',
 'app/kernel/compute/quality_equivalence_harness.py','app/kernel/compute/hard_coding_crystallization_gauntlet.py',
 'app/kernel/compute/final_boss_crystallization_gauntlet.py','scripts/crystal_proof.py',
 'scripts/build_crystalbench_development_pilot.py','scripts/run_crystalbench_development_rehearsal.py',
 'scripts/build_crystal_proof_evidence_bundle.py',
 'scripts/run_crystal_frontier_crucible.py','scripts/run_quality_equivalence.py','scripts/export_hard_coding_quality_attempts.py',
 'scripts/run_discovery_agnostic_receiver.py','scripts/verify_discovery_agnostic_receipt.py','scripts/setup_beast_windows_discovery_receiver.ps1',
 'scripts/build_windows_discovery_receiver_bundle.py','scripts/windows_receiver_local_verifier.py','scripts/show_scenario_contract_digests.py','scripts/export_discovery_receiver_fixture.py',
 'docs/CRYSTAL_FRONTIER_CRUCIBLE.md','docs/CRYSTALLIZED_COMPUTE_QUALITY_EQUIVALENCE.md',
 'docs/COMPOUND_AGENTIC_CRYSTALLIZATION_EXPERIMENT.md','docs/CRYSTALLIZED_COMPUTE_CLAIM_LEDGER.md',
 'docs/DISCOVERY_AGNOSTIC_REUSE_EXPERIMENT.md','docs/windows-discovery-agnostic-receiver-runbook.md',
 'tests/test_crystal_frontier_crucible.py','tests/test_crucible_lane_runner.py','tests/test_crystalbench_authoring.py',
 'tests/test_crystalbench_development_pilot.py','tests/test_crystalbench_development_rehearsal.py','tests/test_crystal_proof_conductor.py','tests/test_quality_equivalence_harness.py',
 'tests/test_discovery_agnostic_reuse.py','tests/test_discovery_receiver_runner.py',
)
def add(archive,path,target,entries):
 data=path.read_bytes();archive.writestr(target,data);entries.append({'path':target,'sha256':'sha256:'+hashlib.sha256(data).hexdigest(),'bytes':len(data)})
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='dist/beast-crystal-proof-evidence-bundle.zip');p.add_argument('--evidence-root',default='/tmp/crystal-proof-visible');a=p.parse_args();out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);entries=[]
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for rel in FILES:
   path=ROOT/rel
   if not path.is_file(): raise FileNotFoundError(path)
   add(z,path,'beast-crystal-proof-bundle/'+rel,entries)
  evidence=Path(a.evidence_root)
  for path in sorted(evidence.rglob('*')) if evidence.is_dir() else []:
   if path.is_file() and 'hidden-verifiers' not in path.parts and 'blind-key.private' not in path.name:
    add(z,path,'beast-crystal-proof-bundle/evidence/'+path.relative_to(evidence).as_posix(),entries)
  manifest={'beast_object_type':'beast_crystal_proof_evidence_bundle','version':'1.0','claim_boundary':'source/tests/public rehearsal evidence only; excludes private verifiers, keys, credentials, and independent final corpus','entries':entries}
  z.writestr('beast-crystal-proof-bundle/BUNDLE-MANIFEST.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'bundle':str(out),'file_count':len(entries),'sha256':'sha256:'+hashlib.sha256(out.read_bytes()).hexdigest()},sort_keys=True))
if __name__=='__main__':main()
