#!/usr/bin/env python3
"""Export the same signed fixture used by test_discovery_receiver_runner."""
import argparse,base64,hashlib,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.kernel.commons.signature_verifier import canonical_bytes
from app.kernel.compute.discovery_agnostic_reuse import SemanticCapabilityContract
from app.kernel.integration.signed_decision import SignedDecision
def d(x): return 'sha256:'+x*64
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='windows-receiver-fixture');a=p.parse_args();o=Path(a.output);o.mkdir(parents=True,exist_ok=True); k=Ed25519PrivateKey.generate(); exp=time.time()+86400
 pub=o/'arda-public.pem';pub.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
 body={'node_id':'receiver-host','attestation':'verified','capabilities':['cpu','tpm'],'pressure_budget':.8,'reliability':.9,'route_penalty':0.,'expires_at':exp,'appraisal_ref':'arda:node:receiver'};rd='sha256:'+hashlib.sha256(canonical_bytes(body)).hexdigest(); sd=SignedDecision('arda',True,rd,'policy-1','nonce-1','','arda-key')
 ev={'appraisal_ref':'arda:node:receiver','policy_generation':'policy-1','authority':'arda','state':'verified','expires_at':exp,'audience':'commons-job-choir','decision':{'authority':'arda','allowed':True,'request_digest':rd,'policy_generation':'policy-1','nonce':'nonce-1','signature':base64.b64encode(k.sign(sd.unsigned())).decode(),'verification_material':{'key_id':'arda-key'}}}
 c=SemanticCapabilityContract('normalize_provider_identifier',{'provider':'string'},{'provider':'canonical'},('case_fold',),d('c'),'low'); pol=d('a');run=d('e')
 task={'task_id':'distant-words','contract':{'operation':c.operation,'input_schema':c.input_schema,'output_schema':c.output_schema,'invariants':list(c.invariants),'tool_schema_digest':c.tool_schema_digest,'risk_tier':c.risk_tier},'policy_digest':pol,'verifier_digest':d('b'),'state_digest':d('d'),'runtime_digest':run}
 sc={'preregistration':{'corpus':'integration-v1','seed':11},'origin_host_id':'origin-host','receiver':{'host_id':'receiver-host','physical_host':True,'attestation_expires_at':exp,'policy_digest':pol,'verifier_digest':d('b'),'state_digest':d('d'),'runtime_digest':run,'attestation_evidence':{'node_advertisement':{**body,'attestation_evidence':ev}}},'cases':[{'case_id':'positive','expected_admission':True,'task':task,'candidates':[{'candidate_id':'origin-candidate','semantic_contract_digest':c.digest,'policy_digest':pol,'verifier_digest':d('b'),'state_digest':d('d'),'runtime_compatible_digests':[run],'expires_at':exp,'source':'peer_exchange'}],'economics':{'baseline_provider_ms':100.,'discovery_ms':1.,'transfer_ms':1.,'reproduction_ms':2.,'execution_ms':1.,'verifier_ms':1.}}]}
 (o/'scenario.json').write_text(json.dumps(sc,indent=2)+'\n');(o/'verifier-plan.json').write_text(json.dumps({'timeout_seconds':180,'contracts':{c.digest:['py','-3','-c','import sys; raise SystemExit(0)']}},indent=2)+'\n');print(json.dumps({'output':str(o),'contract_digest':c.digest,'public_key':str(pub)}))
if __name__=='__main__':main()
