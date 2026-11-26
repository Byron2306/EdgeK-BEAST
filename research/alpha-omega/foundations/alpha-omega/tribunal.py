#!/usr/bin/env python3
"""Offline ALPHA/OMEGA evidence contract prototype. No provider access."""
import argparse, hashlib, json, pathlib, collections

def require(ok,msg):
    if not ok: raise ValueError(msg)
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x): return hashlib.sha256(canonical(x)).hexdigest()
def load(p): return json.loads(pathlib.Path(p).read_text())
def integer(x): return type(x) is int and x>=0
def alpha(plan):
    require(plan['paid_execution_authorized'] is False,'prototype cannot authorize spending')
    require(plan['budget_usd_micros']==0,'prototype requires zero budget')
    return {'status':'DRAFT_COMMITTED_NOT_AUTHORIZED','protocol_sha256':digest(plan)}
def omega(plan,commit,schedule,rows):
    require(commit['protocol_sha256']==digest(plan),'protocol mismatch')
    require(commit.get('schedule_sha256')==digest(schedule),'schedule mismatch')
    expected={r['id']:r for r in schedule}; require(len(expected)==len(schedule) and expected,'invalid schedule')
    seen=set(); totals=collections.defaultdict(lambda:dict(attempts=0,successes=0,cash_micros=0,shadow_micros=0,calls=0))
    for r in rows:
        i=r['id']; require(i in expected and i not in seen,'unexpected or duplicate execution'); seen.add(i)
        for k in ('lane','task','lineage','provider','model'): require(r[k]==expected[i][k],f'{i}: {k} mismatch')
        require(type(r['verified']) is bool,'invalid verification result')
        for k in ('cash_micros','shadow_micros','calls'): require(integer(r[k]),f'invalid {k}')
        require(r['cash_micros']==0,'paid execution outside prototype authorization')
        t=totals[r['lane']]; t['attempts']+=1; t['successes']+=r['verified']
        for k in ('cash_micros','shadow_micros','calls'): t[k]+=r[k]
    require(seen==set(expected),'missing scheduled executions')
    for t in totals.values():
        n=t['successes']; t['cash_per_success_micros']=t['cash_micros']/n if n else None; t['shadow_per_success_micros']=t['shadow_micros']/n if n else None
    return {'status':'STRUCTURAL_CHECK_ONLY','scientific_verdict':'INDETERMINATUM','independent_observer_authentication':False,'billing_reconciled':False,'statistics_validated':False,'totals':dict(totals),'receipt_sha256':digest(rows)}
def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['alpha','omega']); p.add_argument('protocol'); p.add_argument('schedule'); p.add_argument('--commit'); p.add_argument('--receipts'); a=p.parse_args(); plan=load(a.protocol); schedule=load(a.schedule)
    if a.mode=='alpha': out=alpha(plan); out['schedule_sha256']=digest(schedule)
    else: out=omega(plan,load(a.commit),schedule,load(a.receipts))
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
