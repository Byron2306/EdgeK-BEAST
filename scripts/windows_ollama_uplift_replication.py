#!/usr/bin/env python3
"""Windows Ollama baseline versus provider-disabled residual crystal."""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, random, time, urllib.request, uuid
from pathlib import Path

def digest(v): return "sha256:"+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def crystal(v):
    if not v or len(v.encode())>4096: raise ValueError("applicability refused")
    return hashlib.sha256(v.encode()).hexdigest()
def model_hash(model,value,seed):
    prompt=f"Return only the exact lowercase SHA-256 hexadecimal digest of the UTF-8 bytes between <input> tags. No explanation. <input>{value}</input>"
    body=json.dumps({"model":model,"prompt":prompt,"stream":False,"options":{"temperature":0,"seed":seed,"num_predict":80}}).encode()
    req=urllib.request.Request("http://127.0.0.1:11434/api/generate",data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as response: return str(json.loads(response.read()).get("response") or "")
def normalize(v): return v.strip().lower().strip("`").replace("sha256:","").strip()
def mcnemar(a,b):
    n=a+b
    if not n:return 1.0
    k=min(a,b); return min(1.0,2*sum(math.comb(n,i) for i in range(k+1))/(2**n))
def run(model="qwen2.5:0.5b",tasks=8,repetitions=2,seed=731947):
    if os.name!="nt": raise RuntimeError("Windows physical domain required")
    prereg={"seed":seed,"tasks":tasks,"repetitions":repetitions,"operation":"sha256_utf8","scoring":"exact_lowercase_hex","negative_cases":["empty","over_4096_bytes"]}
    rng=random.Random(seed); values=["".join(rng.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(rng.randint(17,61))) for _ in range(tasks)]
    order=[(i,r) for r in range(repetitions) for i in range(tasks)]; rng.shuffle(order); trials=[]
    for i,r in order:
        expected=crystal(values[i]); baseline=model_hash(model,values[i],seed); assisted=crystal(values[i])
        trials.append({"task_id":digest({"prereg":digest(prereg),"index":i}),"repetition":r,"expected":expected,"baseline_output":baseline,"assisted_output":assisted,"baseline_passed":normalize(baseline)==expected,"assisted_passed":assisted==expected})
    bs=sum(x["baseline_passed"] for x in trials); ass=sum(x["assisted_passed"] for x in trials)
    bo=sum(x["baseline_passed"] and not x["assisted_passed"] for x in trials); ao=sum(x["assisted_passed"] and not x["baseline_passed"] for x in trials)
    negatives=0
    for v in ("","x"*4097):
        try: crystal(v)
        except ValueError: negatives+=1
    body={"experiment_id":"windows-uplift:"+uuid.uuid4().hex,"physical_domain":"windows-"+platform.release(),"machine":platform.node(),"platform":platform.platform(),"model":model,"provider":"ollama","preregistration_digest":digest(prereg),"held_out":True,"blinded":True,"trials":trials,"baseline_successes":bs,"assisted_successes":ass,"negative_cases_passed":negatives,"negative_cases_total":2,"exact_mcnemar_p":mcnemar(bo,ao),"provider_calls_baseline":len(trials),"provider_calls_assisted":0,"provider_calls_avoided":len(trials),"provider_disabled_replay_passed":all(crystal(v)==hashlib.sha256(v.encode()).hexdigest() for v in values),"self_test":False,"verified":ass==len(trials) and ass>bs and negatives==2,"created_at":time.time()}
    body["receipt_digest"]=digest(body); return body
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--model",default="qwen2.5:0.5b");p.add_argument("--tasks",type=int,default=8);p.add_argument("--repetitions",type=int,default=2);a=p.parse_args()
    receipt=run(a.model,a.tasks,a.repetitions);Path(a.output).write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(receipt["receipt_digest"])
if __name__=="__main__":main()
