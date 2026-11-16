import base64,hashlib,json,sqlite3,sys,time
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from msr_tss import TPMS_ATTEST,TPMT_PUBLIC,PCR_ReadResponse,TPM_ALG_ID,TPM_ST,TPMA_OBJECT
ROOT=Path(__file__).resolve().parents[3]
source=Path('/mnt/c/Users/buntb/Documents/BEAST-TPM-Proof/nonce-bound-quote.json')
d=json.loads(source.read_text());raw=base64.b64decode(d['quote_b64'],validate=True);sig=base64.b64decode(d['signature_b64'],validate=True);public_raw=base64.b64decode(d['public_area_b64'],validate=True)
quote=TPMS_ATTEST.fromBytes(raw);public=TPMT_PUBLIC.fromBytes(public_raw);pcr=PCR_ReadResponse.fromBytes(base64.b64decode(d['pcr_read_b64'],validate=True))
key=rsa.RSAPublicNumbers(public.parameters.exponent or 65537,int.from_bytes(public.unique.buffer,'big')).public_key()
key.verify(sig,raw,padding.PKCS1v15(),hashes.SHA256())
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
challenge=d['binding']['challenge'];now=time.time();collected=datetime.fromisoformat(d['collected_at']).timestamp()
ledger=ROOT/'.beast/commons-enterprise/attestation/challenges.sqlite3'
with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row;row=conn.execute('SELECT * FROM tpm_challenges WHERE challenge_id=?',(challenge['challenge_id'],)).fetchone()
assert row is not None,'challenge absent from server ledger'
expected_pcrs=[0,2,4,7,10,14];mask=sum(1<<p for p in expected_pcrs).to_bytes(3,'little')
pcr_bytes=b''.join(bytes(v.buffer) for v in pcr.pcrValues)
bound_digest=hashlib.sha256(canonical(d['binding'])).digest()
attrs=TPMA_OBJECT.fixedTPM|TPMA_OBJECT.fixedParent|TPMA_OBJECT.sensitiveDataOrigin|TPMA_OBJECT.restricted|TPMA_OBJECT.sign
checks={'signature_valid':True,'quote_magic_valid':quote.magic==0xff544347,'quote_type_valid':quote.attested.GetUnionSelector()==TPM_ST.ATTEST_QUOTE,'nonce_and_subject_binding_valid':quote.extraData==bound_digest and d['qualifying_data_hex']==bound_digest.hex(),'challenge_matches_server':all(challenge[k]==row[k] for k in ['challenge_id','node_id','nonce','audience','pcr_bank','issued_at','expires_at']) and challenge['pcrs']==json.loads(row['pcrs_json']),'challenge_active_at_verification':row['state']=='issued' and row['issued_at']<=now<row['expires_at'],'collection_within_challenge':challenge['issued_at']<=collected<challenge['expires_at'],'pcr_selection_valid':[(int(v.hash),bytes(v.pcrSelect)) for v in quote.attested.pcrSelect]==[(int(TPM_ALG_ID.SHA256),mask)] and [(int(v.hash),bytes(v.pcrSelect)) for v in pcr.pcrSelectionOut]==[(int(TPM_ALG_ID.SHA256),mask)],'pcr_values_count_valid':len(pcr.pcrValues)==len(expected_pcrs),'pcr_digest_matches':hashlib.sha256(pcr_bytes).digest()==quote.attested.pcrDigest,'public_name_valid':base64.b64decode(d['public_name_b64'])==b'\x00\x0b'+hashlib.sha256(public_raw).digest(),'qualified_signer_matches':quote.qualifiedSigner==base64.b64decode(d['qualified_name_b64']),'key_attributes_valid':public.objectAttributes&attrs==attrs}
negative={}
for label,changed in [('tampered_quote',raw[:-1]+bytes([raw[-1]^1]))]:
 try:key.verify(sig,changed,padding.PKCS1v15(),hashes.SHA256())
 except InvalidSignature:negative[label+'_refused']=True
 else:negative[label+'_refused']=False
negative['tampered_binding_refused']=hashlib.sha256(canonical({**d['binding'],'challenge':{**challenge,'nonce':'wrong-nonce'}})).digest()!=quote.extraData
negative['tampered_pcr_refused']=hashlib.sha256(pcr_bytes[:-1]+bytes([pcr_bytes[-1]^1])).digest()!=quote.attested.pcrDigest
result={'schema':'beast.windows.quote-verification.v1','verified_at':now,'source_digest':'sha256:'+hashlib.sha256(source.read_bytes()).hexdigest(),'checks':checks,'negative_controls':negative,'nonce_bound_quote_verified':all(checks.values()) and all(negative.values()),'hardware_rooted_identity_proven':False,'eligible_for_commons':False,'remaining':['EK-to-AK credential activation','trusted EK certificate-chain and revocation verification','Windows measured-boot replay and accepted baseline','independent authenticated ARDA appraisal','host-to-container workload identity assurance'],'claim_boundary':'Signature, server challenge, public-key name and PCR digest verified; no hardware-rooted execution admission'}
out=Path(__file__).with_name('quote-verification.json');out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));sys.exit(0 if result['nonce_bound_quote_verified'] else 1)
