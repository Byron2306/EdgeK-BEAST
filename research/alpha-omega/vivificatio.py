"""VIVIFICATIO: full offline API rehearsal; synthetic outcomes, no paid authority."""
import json,sys
from pathlib import Path
from resurrectio import Custody,bill,simulate,strict_schedule,ROOT
from fortuna import verify
from evidence import sign,verify_chain,digest,commit_case,examine,Ed25519PrivateKey
for name in ("alpha-omega","pecunia-umbra","judicium"):
    sys.path.insert(0,str(ROOT/"foundations"/name))
import tribunal,pecunia,judicium

def run(out,world):
    if world not in ("equal","failure","lost"): raise ValueError("unknown world")
    out=Path(out); out.mkdir(exist_ok=False)
    tasks=[dict(task=str(i),cluster=str(i),partition="exam",spec_sha256=digest({"x":i})) for i in range(30)]
    plan=strict_schedule(tasks,7)
    rows=verify(plan,plan["sha256"])
    cases={t["task"]:commit_case(t["task"],{"x":int(t["task"])},int(t["task"])*2) for t in tasks}
    protocol=tribunal.load(ROOT/"foundations/alpha-omega/constitution.json")
    schedule=[dict(id=r["execution"],lane=r["lane"],task=r["task"],lineage=r["cluster"],provider="simulator",model="mock") for r in rows]
    commitment=tribunal.alpha(protocol)
    commitment["schedule_sha256"]=tribunal.digest(schedule)
    campaign=digest([plan["sha256"],world,{k:v[0] for k,v in cases.items()}])
    (out/"commitment.json").write_text(json.dumps(dict(campaign=campaign,plan=plan,alpha=commitment,schedule=schedule,cases={k:v[0] for k,v in cases.items()}),indent=2))
    billing=Ed25519PrivateKey.generate(); examiner=Ed25519PrivateKey.generate()
    c=Custody(out/"ledger.db",len(rows)*40,campaign,billing.public_key())
    signed=[]; receipts=[]; outcomes=[]; charges=[]; stats=[]; prev=""
    for r,s in zip(rows,schedule):
        i=r["task"]; identity=r["execution"]; x=int(i)
        scenario="lost" if world=="lost" and x==0 else "normal"
        answer=x*2+int(world=="failure" and r["lane"]=="beast")
        response=simulate(c,billing,identity,scenario,answer)
        if response is None: continue
        h,secret=cases[i]
        exam=examine(h,secret,i,{"x":x},response["answer"])
        payload=dict(execution=identity,exam=exam,billing=response["receipt"])
        event=sign(examiner,campaign,"examiner","exam",len(signed),prev,payload)
        signed.append(event); prev=digest(event)
    snapshot=c.snapshot()
    verify_chain(signed,{"examiner":("exam",examiner.public_key())},campaign,len(signed),prev)
    for r,s in zip(rows,schedule):
        identity=r["execution"]
        state,amount=snapshot["requests"][identity]
        if state!="settled": continue
        event=next(e for e in signed if e["body"]["payload"]["execution"]==identity)
        payload=event["body"]["payload"]
        if payload["billing"]["body"]["payload"]["charge"]!=amount: raise ValueError("billing mismatch")
        ok=payload["exam"]["passed"]
        outcomes.append(dict(task=r["task"],lane=r["lane"],success=ok))
        charges.append(dict(id=identity,task=r["task"],lane=r["lane"],category="execution",actual=0,shadow=amount))
        stats.append(dict(task=r["task"],lane=r["lane"],cluster=r["cluster"],success=ok,cost_micros=amount))
        receipts.append(dict(s,verified=ok,cash_micros=0,shadow_micros=amount,calls=1))
    result=dict(world=world,campaign=campaign,ledger=snapshot,signed=signed,charges=charges,outcomes=outcomes,
                scientific_authorization=False,paid_execution_authorized=False,synthetic=True)
    if snapshot["held"] or len(receipts)!=len(rows):
        result["status"]="INCOMPLETE_LIABILITY"
    else:
        result["pecunia"]=pecunia.account([t["task"] for t in tasks],charges,outcomes)
        result["judicium"]=judicium.evaluate(tasks,stats,draws=1000)
        result["omega"]=tribunal.omega(protocol,commitment,schedule,receipts)
        if sum(e["shadow"] for e in charges)!=snapshot["spent"]: raise ValueError("cost conservation")
        result["status"]="OFFLINE_REHEARSAL_COMPLETE"
    (out/"report.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    return result

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("out");p.add_argument("world",choices=("equal","failure","lost"))
    a=p.parse_args();r=run(a.out,a.world)
    print(json.dumps({k:r[k] for k in ("world","status","scientific_authorization","paid_execution_authorized")},indent=2))
