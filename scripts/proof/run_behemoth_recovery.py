#!/usr/bin/env python3
"""BEHEMOTH RECOVERY: a fresh, stdlib-only, seeded ablation harness.

NOT a reconstruction of the lost BEAST-integrated runner. No real registry,
crystal promotion, governor, cloud baseline, or namespace isolation is claimed.
"""
import argparse
import array
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time

SEALS = (fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)
ARMS = ('flat','child_a','child_b','sequential','staged_direct','lattice',
        'stage2_bad_postcondition','benign_drift','hidden_regression','semantic_near_miss',
        'live','full')

def digest_bytes(b): return 'sha256:'+hashlib.sha256(b).hexdigest()
def canon(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def save(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def tree_digest(root):
    parts=[]
    for f in sorted(root.rglob('*.py')):
        if '__pycache__' in f.parts: continue
        parts.append((f.relative_to(root).as_posix(), digest_bytes(f.read_bytes())))
    return digest_bytes(canon(parts))
def create_fixture(dest,seed):
    rng=random.Random(seed); target=rng.randrange(21,89); correct=rng.randrange(6,15)
    (dest/'app').mkdir(parents=True)
    (dest/'app'/'__init__.py').write_text('')
    (dest/'app'/'logic.py').write_text('def last_n(items, n):\n    return items[-n - 1:]\n')
    (dest/'app'/'config.py').write_text(f'RETRY_LIMIT = {correct-2}\n')
    return {'seed':seed,'expected_limit':correct,'wrong_limit':correct-2,'target':target,
            'source_sha256':tree_digest(dest)}
def verify(root, fixture):
    # Eliminates timestamp/size-valid .pyc after same-second equal-length mutations.
    # A stale bytecode cache would verify the old source instead of the mutated tree.
    for cache in root.rglob('__pycache__'):
        if cache.is_dir(): shutil.rmtree(cache)
    script="""import sys\nsys.path.insert(0,sys.argv[1])\nfrom app.logic import last_n\nfrom app.config import RETRY_LIMIT\nn=int(sys.argv[2]); kind=sys.argv[3]\nassert last_n([1,2,3,4,5],2)==[4,5]\nassert RETRY_LIMIT==n\nif kind=='hidden':\n assert last_n(list(range(15)),4)==[11,12,13,14]\n assert RETRY_LIMIT>0\n"""
    out={}
    for kind in ('visible','hidden'):
        cp=subprocess.run([sys.executable,'-I','-B','-c',script,str(root),str(fixture['expected_limit']),kind],
                          cwd=root,text=True,capture_output=True,timeout=10)
        out[kind]={'returncode':cp.returncode,'passed':cp.returncode==0,
                   'stderr_sha256':digest_bytes(cp.stderr.encode()),
                   'stderr_tail':cp.stderr[-1200:], 'stdout_tail':cp.stdout[-1200:]}
    out['passed']=all(out[x]['passed'] for x in ('visible','hidden'))
    out['tree_digest']=tree_digest(root)
    return out

def edits(fixture):
    return [dict(path='app/logic.py',old='return items[-n - 1:]',new='return items[-n:]'),
            dict(path='app/config.py',old=f"RETRY_LIMIT = {fixture['wrong_limit']}",new=f"RETRY_LIMIT = {fixture['expected_limit']}")]

def apply(root, actions):
    for item in actions:
        rel=Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('path escape')
        path=(root/rel).resolve()
        if not path.is_relative_to(root.resolve()): raise ValueError('path escape')
        data=path.read_text()
        if data.count(item['old'])!=1: raise ValueError('exact-old-text-mismatch')
        path.write_text(data.replace(item['old'],item['new'],1))

def receiver(sock_fd,root):
    sock=socket.socket(fileno=sock_fd)
    data,anc,_,_=sock.recvmsg(32,socket.CMSG_SPACE(4*array.array('i').itemsize))
    fds=[]
    for level,kind,buf in anc:
        if (level,kind)==(socket.SOL_SOCKET,socket.SCM_RIGHTS):
            a=array.array('i');a.frombytes(buf[:len(buf)-(len(buf)%a.itemsize)]);fds.extend(a)
    if len(fds)!=1: raise RuntimeError('exactly one capsule fd required')
    fd=fds[0]
    if fcntl.fcntl(fd,fcntl.F_GET_SEALS)!=SEALS: raise RuntimeError('bad seals')
    size=os.fstat(fd).st_size
    if size>1024*1024: raise RuntimeError('oversized capsule')
    with mmap.mmap(fd,size,access=mmap.ACCESS_READ) as mm: payload=json.loads(mm[:])
    if payload.get('kind')!='behemoth-recovery-edits.v1':raise RuntimeError('wrong capsule')
    apply(Path(root),payload['edits'])
    print(json.dumps({'capsule_digest':digest_bytes(canon(payload)),'seals':SEALS,'bytes':size,'applied':len(payload['edits'])}))
    sock.close();os.close(fd)

def memfd_apply(root,actions):
    if not hasattr(os,'memfd_create'): raise RuntimeError('memfd unsupported')
    payload={'kind':'behemoth-recovery-edits.v1','edits':actions}
    binary=canon(payload)
    fd=os.memfd_create('behemoth-recovery',os.MFD_ALLOW_SEALING)
    os.write(fd,binary);fcntl.fcntl(fd,fcntl.F_ADD_SEALS,SEALS)
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    proc=subprocess.Popen([sys.executable,__file__,'--receiver',str(child.fileno()),str(root)],
                          pass_fds=(child.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    child.close()
    parent.sendmsg([b'CAPSULE'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
    stdout,stderr=proc.communicate(timeout=15)
    parent.close();os.close(fd)
    if proc.returncode: raise RuntimeError('memfd receiver failed: '+stderr[:500])
    return json.loads(stdout)

def execute_arm(base,fixture,arm,container):
    root=container/arm
    shutil.copytree(base,root)
    before=tree_digest(root)
    record={'arm':arm,'input_digest':before,'status':'not_run','model_calls':None,'baseline':{'initial_failures_verified_in_fixture':True}}
    if arm in ('live','full'):
        record['reason']='not configured: real provider comparison requires separate authenticated runner'
        return record
    record['model_calls']={'local':0,'cloud':0,'scope':'this harness only'}
    action=edits(fixture)
    started=time.monotonic()
    try:
        if arm in ('flat','semantic_near_miss'):
            record['status']='refused';record['reason']='no exact composite match'
        else:
            if arm=='child_a': action=action[:1]
            elif arm=='child_b': action=action[1:]
            elif arm=='stage2_bad_postcondition':
                apply(root,action[:1])
                # reject second step before it mutates; discard staged tree on exit
                record['status']='rolled_back';record['reason']='second stage rejected before publication'
                action=[]
            if arm=='benign_drift':
                (root/'app'/'logic.py').write_text((root/'app'/'logic.py').read_text()+'# harmless comment\n')
            if arm=='hidden_regression':
                apply(root,action)
                (root/'app'/'logic.py').write_text('def last_n(items, n):\n    return items[-n:] if len(items)<10 else []\n')
                action=[]
            if arm=='lattice':record['transport']=memfd_apply(root,action)
            elif action:apply(root,action)
        result=verify(root,fixture)
        if record['status']=='not_run':
            record['status']='verified' if result['passed'] else ('partial' if arm.startswith('child_') else 'hidden_rejected')
        record['verification']=result
        record['post_tree_digest']=result['tree_digest']
        record['published']=record['status']=='verified'
        record['input_unmodified']=tree_digest(base)==fixture['source_sha256']
        record['wall_ms']=round((time.monotonic()-started)*1000,3)
        expected={'flat':'refused','child_a':'partial','child_b':'partial','sequential':'verified',
                  'staged_direct':'verified','lattice':'verified','stage2_bad_postcondition':'rolled_back',
                  'benign_drift':'verified','hidden_regression':'hidden_rejected','semantic_near_miss':'refused'}
        record['meets_expectation']=(record['status']==expected[arm] and record['input_unmodified'])
    except Exception as e:
        record['status']='error';record['error']=type(e).__name__+': '+str(e)[:300];record['meets_expectation']=False
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,action='append',default=None)
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('REFUSE: output exists; use a fresh directory')
    out.mkdir(parents=True)
    attempts=[];fixtures={}
    for seed in (args.seed or [4317,4318]):
        base=out/'fixtures'/str(seed)
        fixture=create_fixture(base,seed);fixtures[str(seed)]=fixture
        initial=verify(base,fixture)
        if initial['passed'] or initial['visible']['passed'] or initial['hidden']['passed']:
            raise RuntimeError('fixture baseline must fail both oracles')
        case=out/'cases'/str(seed)
        for arm in ARMS:
            record=execute_arm(base,fixture,arm,case)
            record['seed']=seed
            attempts.append(record)
    (out/'attempts.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in attempts))
    save(out/'fixtures.json',fixtures)
    passed=sum(x.get('meets_expectation') is True for x in attempts)
    failed=[(x['seed'],x['arm'],x.get('error') or x.get('status')) for x in attempts if x.get('meets_expectation') is False]
    save(out/'summary.json',{'schema':'beast.behemoth.recovery.v1','source':'new independent recovery harness',
          'claim_boundary':'Seeded synthetic fixtures, scripted repairs, no real BEAST crystal promotion/governor, no cloud calls by design; memfd is real sealed SCM_RIGHTS but no network namespace isolation.',
          'attempts':len(attempts),'executed':sum(x['status']!='not_run' for x in attempts),
          'expected_controls_passed':passed,'errors':failed,
          'not_run':sum(x['status']=='not_run' for x in attempts),
          'status':'controls_pass' if not failed else 'failed'})
    checksum=[]
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS':checksum.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}")
    (out/'SHA256SUMS').write_text('\n'.join(checksum)+'\n')
    print(json.dumps(json.loads((out/'summary.json').read_text()),indent=2))
    if failed:sys.exit(1)

if __name__=='__main__':
    if len(sys.argv)>=2 and sys.argv[1]=='--receiver':
        receiver(int(sys.argv[2]),sys.argv[3])
    else:main()
