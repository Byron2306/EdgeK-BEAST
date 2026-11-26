"""FORTUNA: deterministic, committed, cluster-isolated paired schedules."""
import hashlib
import json
import unittest

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def schedule(tasks, seed, lanes=("control","beast")):
    if type(seed) is not int or len(lanes)!=2 or len(set(lanes))!=2:
        raise ValueError("invalid design")
    seen=set()
    clusters={}
    for t in tasks:
        if set(t)!={"task","cluster","partition","spec_sha256"}:
            raise ValueError("invalid task")
        if any(not isinstance(v,str) or not v for v in t.values()):
            raise ValueError("invalid identity")
        if len(t["spec_sha256"])!=64 or any(c not in "0123456789abcdef" for c in t["spec_sha256"]):
            raise ValueError("invalid specification commitment")
        if t["task"] in seen or t["partition"] not in ("acquisition","calibration","exam","holdout"):
            raise ValueError("duplicate task or invalid partition")
        seen.add(t["task"])
        if clusters.setdefault(t["cluster"],t["partition"])!=t["partition"]:
            raise ValueError("cluster leakage")
    if not seen:
        raise ValueError("empty design")
    rows=[]
    # Keep acquisition before calibration and examination. Randomize within phase.
    for t in sorted(tasks,key=lambda t:(("acquisition","calibration","exam","holdout").index(t["partition"]),digest([seed,t["task"]]))):
        for lane in sorted(lanes,key=lambda lane:digest([seed,t["task"],lane])):
            rows.append(dict(t,lane=lane,execution=digest([seed,t,lane])))
    body={"schema":"fortuna.v1","seed":seed,"lanes":list(lanes),"rows":rows}
    return {"body":body,"sha256":digest(body)}

def verify(plan, expected_sha256):
    if digest(plan["body"])!=expected_sha256 or plan["sha256"]!=expected_sha256:
        raise ValueError("schedule commitment mismatch")
    b=plan["body"]
    tasks={r["task"]:{k:r[k] for k in ("task","cluster","partition","spec_sha256")} for r in b["rows"]}
    if schedule(list(tasks.values()),b["seed"],tuple(b["lanes"]))!=plan:
        raise ValueError("invalid schedule")
    return b["rows"]

class Controls(unittest.TestCase):
    def setUp(self):
        self.tasks=[dict(task=str(i),cluster=str(i),partition="exam",spec_sha256=digest(i)) for i in range(20)]
    def test_reproducible(self):
        self.assertEqual(schedule(self.tasks,4),schedule(list(reversed(self.tasks)),4))
    def test_pairs(self):
        p=schedule(self.tasks,4)
        self.assertEqual(len(verify(p,p["sha256"])),40)
    def test_leakage(self):
        self.tasks[1].update(cluster="0",partition="holdout")
        with self.assertRaises(ValueError): schedule(self.tasks,4)
    def test_mutation(self):
        p=schedule(self.tasks,4)
        p["body"]["rows"].pop()
        with self.assertRaises(ValueError): verify(p,p["sha256"])
    def test_duplicate(self):
        with self.assertRaises(ValueError): schedule(self.tasks+self.tasks,4)

if __name__=="__main__": unittest.main(verbosity=2)
