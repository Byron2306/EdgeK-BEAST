"""Optional S3-compatible content-addressed bucket adapter."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from app.kernel.compute.forge_kv_bucket import sha256_bytes
@dataclass(frozen=True)
class S3ObjectReceipt: bucket:str; key:str; digest:str; size:int; created:bool
class S3ContentAddressedBucket:
    def __init__(self,client:Any,bucket:str,prefix:str="forge-kv/objects"): self.client=client; self.bucket=bucket; self.prefix=prefix.rstrip('/')
    def key(self,digest:str)->str:
        if not digest.startswith('sha256:'): raise ValueError('invalid digest')
        return f"{self.prefix}/{digest[7:9]}/{digest[9:]}"
    def head(self,digest:str):
        try: return self.client.head_object(Bucket=self.bucket,Key=self.key(digest))
        except Exception as exc:
            code=str(getattr(exc,'response',{}).get('Error',{}).get('Code',''))
            if code in {'404','NoSuchKey','NotFound'}: return None
            raise
    def put(self,payload:bytes,expected_digest:str=''):
        digest=sha256_bytes(payload)
        if expected_digest and expected_digest!=digest: raise ValueError('digest mismatch')
        existing=self.head(digest) is not None
        if not existing: self.client.put_object(Bucket=self.bucket,Key=self.key(digest),Body=payload,Metadata={'sha256':digest[7:]})
        return S3ObjectReceipt(self.bucket,self.key(digest),digest,len(payload),not existing)
    def get(self,digest:str)->bytes:
        body=self.client.get_object(Bucket=self.bucket,Key=self.key(digest))['Body'].read()
        if sha256_bytes(body)!=digest: raise ValueError('remote object digest mismatch')
        return body
