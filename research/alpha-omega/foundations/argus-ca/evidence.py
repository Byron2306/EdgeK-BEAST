"""Offline signed evidence and blind exact-output examination primitives."""
import hashlib, json, secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(x): return hashlib.sha256(canonical(x)).hexdigest()
def sign(key, campaign, observer, role, sequence, previous, payload):
    body=dict(schema='argus.v1',campaign=campaign,observer=observer,role=role,sequence=sequence,previous=previous,payload=payload)
    return dict(body=body,signature=key.sign(canonical(body)).hex())
def verify_chain(rows, registry, campaign, expected_count, expected_head):
    prev=''; seen=set()
    for i,row in enumerate(rows):
        b=row['body']; identity=b['observer']; role,key=registry[identity]
        if b['schema']!='argus.v1' or b['campaign']!=campaign or b['role']!=role or type(b['sequence']) is not int or b['sequence']!=i or b['previous']!=prev: raise ValueError('binding mismatch')
        key.verify(bytes.fromhex(row['signature']),canonical(b))
        prev=digest(row)
        if prev in seen: raise ValueError('duplicate')
        seen.add(prev)
    if len(rows)!=expected_count or prev!=expected_head: raise ValueError('checkpoint mismatch')
    return prev

def commit_case(case_id, public, expected):
    secret=dict(case_id=case_id,public_digest=digest(public),expected=expected,salt=secrets.token_hex(32))
    return digest(secret),secret

def examine(commitment, secret, case_id, public, submitted):
    if digest(secret)!=commitment or secret['case_id']!=case_id or secret['public_digest']!=digest(public): raise ValueError('case binding mismatch')
    return dict(case_id=case_id,commitment=commitment,submission_digest=digest(submitted),passed=canonical(submitted)==canonical(secret['expected']))
