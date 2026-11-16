from pathlib import Path
import sys,json,urllib.request,urllib.error,hashlib,tempfile,time,shutil
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from app.kernel.commons.tpm_attestation import TpmChallengeLedger
from app.kernel.commons.tpm_appraisal import TpmNodeAppraisalIssuer
from app.kernel.commons.appraisal_verifier import SignedNodeAttestationVerifier
from app.kernel.commons.job_choir import CommonsJobChoir
BASE='http://127.0.0.1:8101'
def request(path,body=None,identity=''):
 headers={'Content-Type':'application/json'}
 if identity:headers['X-BEAST-Workspace-Identity']=identity
 req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=10) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as response:return response.code,json.load(response)
_,wi=request('/edgek/control-plane/workspace-identity');identity=wi['digest']
result={'claim':'hardware-backed independent ARDA admission','hardware_proof_passed':False,'timestamp':time.time(),'environment':{'tpm_device':Path('/dev/tpmrm0').exists() or Path('/dev/tpm0').exists(),'tpm2_quote':shutil.which('tpm2_quote')},'live_nodes':[]}
for node in ['commons-node-a','commons-node-b','commons-node-c']:
 code,issued=request('/edgek/control-plane/commons/attestation/challenges',{'node_id':node},identity)
 assert code==200,(code,issued)
 ch=issued['challenge']
 evidence={'node_id':node,'challenge_id':ch['challenge_id'],'nonce':ch['nonce'],'audience':ch['audience'],'evidence_digest':'sha256:'+hashlib.sha256(b'no-hardware-evidence-available').hexdigest(),'eligible_for_commons':False,'status':'hardware_evidence_unavailable'}
 status,denial=request('/edgek/control-plane/commons/attestation/appraise',{'evidence':evidence},identity)
 result['live_nodes'].append({'node_id':node,'challenge':ch,'submitted_evidence':evidence,'http_status':status,'decision':'REFUSE' if status==403 else 'UNEXPECTED','response':denial})
 assert status==403,(status,denial)
# Isolate the adversarial test: fresh untrusted test key and temporary ledger.
# No production/lab authority keys are used; no live node is given a false appraisal.
with tempfile.TemporaryDirectory(prefix='beast-attestation-boundary-') as td:
 d=Path(td);key=Ed25519PrivateKey.generate();pub=d/'public.pem';pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
 ledger=TpmChallengeLedger(d/'challenges.sqlite3');ch=ledger.issue('isolated-untrusted-test-node')
 evidence={'node_id':ch.node_id,'challenge_id':ch.challenge_id,'nonce':ch.nonce,'audience':ch.audience,'evidence_digest':'sha256:'+hashlib.sha256(b'no-quote-no-ek-no-ak-no-event-log').hexdigest(),'status':'hardware_quote_valid_measurements_reconciled','eligible_for_commons':True,'measurement_reconciliation':{'valid':True},'verifier_facts':{'quote_valid':True,'ek_chain_valid':True,'ak_credential_activated':True,'event_log_replay_valid':True}}
 issuer=TpmNodeAppraisalIssuer(key,policy_generation='isolated-test-policy',key_id='isolated-test-key')
 issued=issuer.issue(evidence,challenge_ledger=ledger)
 verifier=SignedNodeAttestationVerifier(pub,expected_policy_generation='isolated-test-policy');signature_valid=verifier(issued.node)
 selected=CommonsJobChoir(attestation_verifier=verifier,require_attestation_verification=True).select([issued.node],required='cpu',now=time.time())
 try:issuer.issue(evidence,challenge_ledger=ledger)
 except PermissionError:replay_refused=True
 else:replay_refused=False
 result['isolated_adversarial_test']={'scope':'temporary key and ledger, no live authority material','input_had_quote':False,'input_had_ek_certificate':False,'input_had_ak_activation_proof':False,'input_had_event_log':False,'submitted_evidence':evidence,'appraisal':issued.appraisal,'advertisement':asdict(issued.node),'signature_valid':signature_valid,'job_choir_selected':selected.node_id,'replay_refused':replay_refused,'self_reported_evidence_refused':False,'security_boundary_passed':False}
result['conclusion']='REFUSE on honest missing evidence; self-reported verification flags are accepted by the issuer in isolation. Independent cryptographic evidence verification is not proven.'
out=Path(__file__).with_name('attestation-proof.json');out.write_text(json.dumps(result,indent=2));print(json.dumps({'receipt':str(out),'hardware_proof_passed':False,'live_decisions':[n['decision'] for n in result['live_nodes']],'isolated_self_report_accepted':True,'replay_refused':replay_refused},indent=2))
