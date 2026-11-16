import argparse,base64,hashlib,json,os,sys,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from msr_tss import *
from msr_tss.Tpm import Tpm

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def b64(x):return base64.b64encode(bytes(x)).decode()
def template():
 attrs=TPMA_OBJECT.fixedTPM|TPMA_OBJECT.fixedParent|TPMA_OBJECT.sensitiveDataOrigin|TPMA_OBJECT.userWithAuth|TPMA_OBJECT.restricted|TPMA_OBJECT.sign
 return TPMT_PUBLIC(TPM_ALG_ID.SHA256,attrs,b'',TPMS_RSA_PARMS(TPMT_SYM_DEF_OBJECT(),TPMS_SCHEME_RSASSA(TPM_ALG_ID.SHA256),2048,0),TPM2B_PUBLIC_KEY_RSA(b''))
parser=argparse.ArgumentParser();parser.add_argument('--self-check',action='store_true');args=parser.parse_args()
if args.self_check:
 t=template();assert TPMT_PUBLIC.fromBytes(t.toBytes()).toBytes()==t.toBytes();print('Pinned library import and TPM template serialization passed');sys.exit(0)
if sys.platform!='win32':raise SystemExit('This collector must run under Windows Python, not WSL.')
import ctypes
if not ctypes.windll.shell32.IsUserAnAdmin():raise SystemExit('Run Windows PowerShell as Administrator.')
BASE='http://127.0.0.1:8101'
def request(path,body=None,identity=''):
 headers={'Content-Type':'application/json'}
 if identity:headers['X-BEAST-Workspace-Identity']=identity
 req=urllib.request.Request(BASE+path,data=canonical(body) if body is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
identity=request('/edgek/control-plane/workspace-identity')['digest']
challenge=request('/edgek/control-plane/commons/attestation/challenges',{'node_id':'beast-windows-host','ttl_seconds':900},identity)['challenge']
remote=request('/edgek/control-plane/commons/remote')
subjects=[]
for row in remote['nodes']:
 doc=request('/edgek/control-plane/commons/remote/nodes/'+row['node_id']+'/probe',{},identity)
 subjects.append({'node_id':row['node_id'],'workload_digest':row['expected_workload_digest'],'node_public_key':row['node_public_key']})
binding={'challenge':challenge,'commons_subjects':sorted(subjects,key=lambda x:x['node_id'])}
nonce=hashlib.sha256(canonical(binding)).digest()
pcrs=[0,2,4,7,10,14];mask=sum(1<<p for p in pcrs).to_bytes(3,'little');selection=[TPMS_PCR_SELECTION(TPM_ALG_ID.SHA256,mask)]
tpm=Tpm();handle=None
try:
 tpm.connect()
 primary=tpm.CreatePrimary(TPM_HANDLE.NULL,TPMS_SENSITIVE_CREATE(b'',b''),template(),b'',[]);handle=primary.handle
 pub=tpm.ReadPublic(handle)
 before=tpm.PCR_Read(selection)
 quoted=tpm.Quote(handle,nonce,TPMS_SCHEME_RSASSA(TPM_ALG_ID.SHA256),selection)
 after=tpm.PCR_Read(selection)
 if before.toBytes()!=after.toBytes():raise RuntimeError('PCRs changed during quote; rerun for a stable snapshot')
 packet={'schema':'beast.windows.nonce-bound-quote.v1','collected_at':datetime.now(timezone.utc).isoformat(),'claim_boundary':'Windows TBS quote with temporary NULL-hierarchy key; EK-to-AK activation, event-log reconciliation and independent ARDA appraisal remain unproven','binding':binding,'qualifying_data_hex':nonce.hex(),'quote_b64':b64(quoted.quoted.toBytes()),'signature_b64':b64(quoted.signature.sig),'signature_algorithm':'RSASSA-SHA256','public_area_b64':b64(pub.outPublic.toBytes()),'public_name_b64':b64(pub.name),'qualified_name_b64':b64(pub.qualifiedName),'pcr_read_b64':b64(before.toBytes()),'tss_commit':'52cb9f432318e8e95cdfeaf98b824ece89370744','private_key_exported':False,'persistent_key_created':False,'ak_ek_binding_verified':False,'eligible_for_commons':False}
 out=Path(os.environ['USERPROFILE'])/'Documents'/'BEAST-TPM-Proof'/'nonce-bound-quote.json';out.write_text(json.dumps(packet,indent=2),encoding='utf-8');print('Saved nonce-bound quote:',out)
finally:
 if handle is not None:tpm.FlushContext(handle)
 tpm.close()
