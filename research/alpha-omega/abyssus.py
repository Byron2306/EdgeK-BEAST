"""ABYSSUS: offline adversarial controls and independent correctness adjudication."""
import json, random, math, tempfile, subprocess, sys, sqlite3
from pathlib import Path
from resurrectio import Custody,bill,strict_schedule,Ed25519PrivateKey
from evidence import sign,verify_chain,digest
from vivificatio import judicium

def evaluate(tasks,rows,**kwargs):
    r=judicium.evaluate(tasks,rows,**kwargs)
    p=r["protocol"]
    groups={}
    for row in rows:
        g=groups.setdefault(row["cluster"],[0,0])
        g[0]+=int(row["lane"]=="control")
        g[1]+=int(row["success"])*(1 if row["lane"]=="beast" else -1)
    gs=[groups[k] for k in sorted(groups)]
    r["correctness_verdict"]="INDETERMINATUM"
    r["economic_verdict"]="INDETERMINATUM"
    if len(gs)>=p["min_clusters"]:
        rng=random.Random(p["seed"])
        ds=[]
        for _ in range(p["draws"]):
            sample=rng.choices(gs,k=len(gs))
            ds.append(sum(g[1] for g in sample)/sum(g[0] for g in sample))
        ds.sort()
        lo,hi=ds[math.floor(.025*(len(ds)-1))],ds[math.ceil(.975*(len(ds)-1))]
        r["success_interval"]=[lo,hi]
        if lo>=-p["margin"]: r["correctness_verdict"]="SUPPORTED"
        elif hi<-p["margin"]: r["correctness_verdict"]="CONTRADICTED"
        if "saving_interval" in r:
            lo,hi=r["saving_interval"]
            if lo>=p["saving"]: r["economic_verdict"]="SUPPORTED"
            elif hi<p["saving"]: r["economic_verdict"]="CONTRADICTED"
    v=(r["correctness_verdict"],r["economic_verdict"])
    r["verdict"]="THRESHOLDS_CONTRADICTED" if "CONTRADICTED" in v else "THRESHOLDS_SUPPORTED" if v==("SUPPORTED","SUPPORTED") else "INDETERMINATUM"
    return r

def run():
    results=[]
    def check(name,fn):
        try: results.append(dict(control=name,status="PASS" if fn() is True else "GAP"))
        except Exception as e: results.append(dict(control=name,status="ERROR",error=repr(e)))
    def refused(fn):
        try: fn()
        except Exception: return True
        return False
    tasks=[dict(task=str(i),cluster=str(i)) for i in range(30)]
    def rows(success=True,cost=50):
        return [dict(t,lane=l,success=(l=="control" or success),cost_micros=100 if l=="control" else cost) for t in tasks for l in ("control","beast")]
    check("zero_success_correctness",lambda:evaluate(tasks,rows(False),draws=1000)["verdict"]=="THRESHOLDS_CONTRADICTED")
    check("positive_fixture",lambda:evaluate(tasks,rows(),draws=1000)["verdict"]=="THRESHOLDS_SUPPORTED")
    check("equal_cost",lambda:evaluate(tasks,rows(True,100),draws=1000)["verdict"]=="THRESHOLDS_CONTRADICTED")
    check("missing_pair",lambda:refused(lambda:evaluate(tasks,rows()[:-1],draws=1000)))
    check("duplicate_pair",lambda:refused(lambda:evaluate(tasks,rows()+rows()[:1],draws=1000)))
    check("zero_control_cost",lambda:evaluate(tasks,[dict(r,cost_micros=0) for r in rows()],draws=1000)["verdict"]=="INDETERMINATUM")
    check("invalid_lane",lambda:refused(lambda:strict_schedule([],7,("","beast"))))
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"ledger.db"; k=Ed25519PrivateKey.generate()
        c=Custody(p,100,"campaign",k.public_key())
        # Child exits abruptly after durable dispatch, bypassing normal cleanup.
        child="from resurrectio import Custody,Ed25519PrivateKey;import os,sys;c=Custody(sys.argv[1],100,'campaign',Ed25519PrivateKey.generate().public_key());c.dispatch('a','lost');os._exit(73)"
        rc=subprocess.run([sys.executable,"-B","-c",child,str(p)],cwd=Path(__file__).resolve().parent).returncode
        check("abrupt_exit_liability",lambda:rc==73 and c.snapshot()["held"]==40)
        check("unknown_scenario",lambda:refused(lambda:c.dispatch("b","unknown")))
        check("forged_settlement",lambda:refused(lambda:c.settle("a",bill(Ed25519PrivateKey.generate(),"campaign","a",0))))
        check("cross_campaign",lambda:refused(lambda:c.settle("a",bill(k,"other","a",28))))
        check("wrong_execution",lambda:refused(lambda:c.settle("a",bill(k,"campaign","b",28))))
        c.settle("a",bill(k,"campaign","a",28))
        check("settlement_replay",lambda:refused(lambda:c.settle("a",bill(k,"campaign","a",28))))
        with sqlite3.connect(p) as db: db.execute("UPDATE events SET digest='bad' WHERE seq=2")
        check("ledger_mutation",lambda:refused(c.snapshot))
    k=Ed25519PrivateKey.generate()
    a=sign(k,"c","examiner","exam",0,"",{"passed":True})
    b=sign(k,"c","examiner","exam",1,digest(a),{"passed":False})
    registry={"examiner":("exam",k.public_key())}
    check("signed_truncation",lambda:refused(lambda:verify_chain([a],registry,"c",2,digest(b))))
    check("signed_duplicate",lambda:refused(lambda:verify_chain([a,a],registry,"c",2,digest(b))))
    return dict(schema="abyssus.v1",controls=results,counts={s:sum(r["status"]==s for r in results) for s in ("PASS","GAP","ERROR")},scientific_authorization=False,paid_execution_authorized=False)
if __name__=="__main__":
    r=run();print(json.dumps(r,indent=2));sys.exit(0 if all(x["status"]=="PASS" for x in r["controls"]) else 2)
