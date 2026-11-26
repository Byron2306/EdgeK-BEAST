"""APOCALYPSIS I: offline adversarial census; never authorizes spending."""
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fortuna import schedule,verify,digest
from anima_machinae import pilot,preflight
from provider_canon_simulacrum import Gateway,Tariff,Usage,Simulacrum

def gateway(budget=100):
    return Gateway(budget,"mock",Tariff(2,1,4))

def plan():
    return schedule([dict(task=str(i),cluster=str(i),partition="exam",spec_sha256=digest(i)) for i in range(30)],7)

def refuses(fn):
    try: fn()
    except (ValueError,RuntimeError): return True
    return False

def run():
    results=[]
    def check(name,fn):
        try:
            ok=fn()
            results.append(dict(control=name,status="PASS" if ok is True else "GAP"))
        except Exception as e:
            results.append(dict(control=name,status="ERROR",error=repr(e)))
    def mutation():
        p=plan(); h=p["sha256"]; p["body"]["rows"].pop()
        return refuses(lambda:verify(p,h))
    check("schedule_truncation",mutation)
    def recommit():
        p=plan(); h=p["sha256"]; p["body"]["seed"]=8; p["sha256"]=digest(p["body"])
        return refuses(lambda:verify(p,h))
    check("attacker_recommit_against_pinned_head",recommit)
    def leakage():
        tasks=[dict(task=str(i),cluster="shared",partition=v,spec_sha256=digest(i)) for i,v in enumerate(("acquisition","holdout"))]
        return refuses(lambda:schedule(tasks,7))
    check("cluster_partition_leakage",leakage)
    def missing():
        with tempfile.TemporaryDirectory() as d:
            return refuses(lambda:preflight(Path(d)))
    check("missing_foundations",missing)
    for scenario in ("lost","interrupted","substitution","malformed"):
        def failure(scenario=scenario):
            g=gateway(); ok=Simulacrum(g).run("a",scenario)
            return not ok and g.exposure()==(40 if scenario=="lost" else 28)
        check("liability_"+scenario,failure)
    def duplicate():
        g=gateway(); Simulacrum(g).run("a","normal")
        return refuses(lambda:g.settle("a",28)) and refuses(lambda:g.dispatch("a",10,5))
    check("duplicate_dispatch_and_settlement",duplicate)
    def concurrent():
        g=gateway()
        def attempt(i): return not refuses(lambda:g.dispatch(str(i),10,5))
        with ThreadPoolExecutor(max_workers=8) as pool:
            n=sum(pool.map(attempt,range(100)))
        return n==2 and g.exposure()==80
    check("concurrent_budget",concurrent)
    def overrun():
        g=gateway(); Simulacrum(g).run("a","overrun")
        return g.exposure()==128 and g.rows["a"]["overrun"] and refuses(lambda:g.dispatch("b",10,5))
    check("overrun_retained",overrun)
    def restart():
        g=gateway(); Simulacrum(g).run("a","lost")
        restarted=gateway()
        return restarted.exposure()==g.exposure()
    check("restart_liability_persistence",restart)
    def forged():
        g=gateway(); g.dispatch("a",10,5)
        return refuses(lambda:g.settle("a",0))
    check("unauthenticated_zero_settlement",forged)
    def invalid_scenario():
        g=gateway()
        return refuses(lambda:Simulacrum(g).run("a","unknown"))
    check("unknown_scenario_refusal",invalid_scenario)
    def invalid_lanes():
        p=plan()
        tasks=[{k:r[k] for k in ("task","cluster","partition","spec_sha256")} for r in p["body"]["rows"][::2]]
        return refuses(lambda:schedule(tasks,7,("","beast")))
    check("empty_lane_refusal",invalid_lanes)
    def interlock():
        p=plan(); r=pilot(p,p["sha256"])
        return r["scientific_verdict"]=="INDETERMINATUM" and r["paid_execution_authorized"] is False and len(r["observations"])==60
    check("scientific_interlock",interlock)
    counts={s:sum(r["status"]==s for r in results) for s in ("PASS","GAP","ERROR")}
    return {"schema":"apocalypse.v1","counts":counts,"controls":results,
            "unexamined":["signed observer chain","independent hidden examiner","durable ARGUS","PECUNIA attribution","JUDICIUM false victory","real egress"],
            "paid_execution_authorized":False,"scientific_authorization":False,
            "status":"GAPS_PRESENT" if counts["GAP"] or counts["ERROR"] else "CONTROLS_PASS"}

if __name__=="__main__":
    import sys
    report=run()
    print(json.dumps(report,indent=2))
    sys.exit(2 if report["status"]=="GAPS_PRESENT" else 0)
