from pathlib import Path
import os,json
from msr_tss import TPM_HANDLE
from msr_tss.Tpm import Tpm
out=Path(os.environ['USERPROFILE'])/'Documents'/'BEAST-TPM-Proof';results=[];tpm=Tpm()
try:
 tpm.connect()
 for index in [0x01c00002,0x01c0000a,0x01c00100]:
  h=TPM_HANDLE(index);pub=tpm.NV_ReadPublic(h).nvPublic;data=bytearray()
  for offset in range(0,pub.dataSize,512):
   response=tpm.NV_Read(h,h,min(512,pub.dataSize-offset),offset);data.extend(response)
  target=out/('nv-certificate-'+hex(index)+'.bin');target.write_bytes(data);results.append({'index':hex(index),'bytes':len(data),'file':str(target)})
 print(json.dumps(results,indent=2))
finally:tpm.close()
