"""ANIMA MACHINAE: offline integration pilot, not scientific authorization."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest
from fortuna import schedule,verify,digest
from provider_canon_simulacrum import Gateway,Tariff,Simulacrum

ROOT=Path(__file__).resolve().parent
PACKAGES=("alpha-omega","argus-genesis","argus-ca","judicium","pecunia-umbra")

def preflight(root=ROOT):
    results={}
    for name in PACKAGES:
        p=root/"foundations"/name
        if not (p/"SHA256SUMS").is_file():
            raise RuntimeError("FOUNDATION_MISSING:"+name)
        for line in (p/"SHA256SUMS").read_text().splitlines():
            expected,relative=line.split(maxsplit=1)
            f=(p/relative.lstrip("*")).resolve()
            if not f.is_relative_to(p.resolve()) or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
                raise RuntimeError("FOUNDATION_INTEGRITY:"+name)
        r=subprocess.run([sys.executable,"-B","-m","unittest","discover","-v"],cwd=p,capture_output=True,text=True,timeout=120)
        if r.returncode or "Ran 0 tests" in r.stderr:
            raise RuntimeError("FOUNDATION_TEST_FAILURE:"+name)
        results[name]={"returncode":r.returncode,"test_log":r.stderr+r.stdout}
    return results

def pilot(plan,commitment):
    rows=verify(plan,commitment)
    g=Gateway(len(rows)*40,"mock",Tariff(2,1,4))
    s=Simulacrum(g)
    observations=[]
    scenarios=("normal","lost","interrupted","substitution","malformed")
    for row in rows:
        identity=row["execution"]
        scenario=scenarios[int(digest([row["task"],row["lane"]]),16)%len(scenarios)]
        response=s.run(identity,scenario)
        observations.append({"execution":identity,"scenario":scenario,"response_admitted":response})
    for o in observations:
        o["accounting"]=dict(g.rows[o["execution"]])
    return {"schema":"anima.pilot.v1","schedule_sha256":commitment,
            "observations":observations,"exposure":g.exposure(),
            "unsettled":sum(r["state"]!="settled" for r in g.rows.values()),
            "scientific_verdict":"INDETERMINATUM","paid_execution_authorized":False,
            "independent_examiner_integrated":False,"foundation_runtime_integrated":False}

class Controls(unittest.TestCase):
    def test_pilot(self):
        p=schedule([dict(task=str(i),cluster=str(i),partition="exam",spec_sha256=digest(i)) for i in range(30)],7)
        r=pilot(p,p["sha256"])
        self.assertEqual(len(r["observations"]),60)
        self.assertGreater(r["unsettled"],0)
        self.assertFalse(r["paid_execution_authorized"])
        self.assertEqual(r["scientific_verdict"],"INDETERMINATUM")
        self.assertEqual(len({o["execution"] for o in r["observations"]}),60)
    def test_missing_foundations(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"FOUNDATION_MISSING"):
                preflight(Path(d))
    def test_mutated_schedule(self):
        p=schedule([dict(task="a",cluster="a",partition="exam",spec_sha256=digest("a"))],7)
        with self.assertRaises(ValueError): pilot(p,"0"*64)

def main():
    if sys.argv[1:]==["--preflight"]:
        print(json.dumps(preflight(),indent=2))
    elif sys.argv[1:]==["--pilot"]:
        foundations=preflight()
        p=schedule([dict(task=str(i),cluster=str(i),partition="exam",spec_sha256=digest(i)) for i in range(30)],7)
        print(json.dumps({"preflight":foundations,"plan":p,"pilot":pilot(p,p["sha256"])},indent=2))
    else:
        unittest.main(verbosity=2)

if __name__=="__main__": main()
