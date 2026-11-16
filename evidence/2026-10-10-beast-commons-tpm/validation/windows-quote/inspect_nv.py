import json,os
from pathlib import Path
from msr_tss import TPM_CAP
from msr_tss.Tpm import Tpm

tpm=Tpm();records=[]
try:
 tpm.connect()
 response=tpm.GetCapability(TPM_CAP.HANDLES,0x01000000,256)
 for handle in response.capabilityData.handle:
  if handle.handle>>24!=1:continue
  value=tpm.NV_ReadPublic(handle).nvPublic
  records.append({'index':hex(handle.handle),'attributes':hex(int(value.attributes)),'data_size':value.dataSize,'name_algorithm':int(value.nameAlg),'authorization_policy_hex':bytes(value.authPolicy).hex()})
 out=Path(os.environ['USERPROFILE'])/'Documents'/'BEAST-TPM-Proof'/'nv-public-metadata.json'
 out.write_text(json.dumps({'scope':'Public NV metadata only; no NV contents read or authorization attempted','more_data':bool(response.moreData),'indices':records},indent=2),encoding='utf-8')
 print('Saved:',out);print(json.dumps(records,indent=2))
finally:tpm.close()
