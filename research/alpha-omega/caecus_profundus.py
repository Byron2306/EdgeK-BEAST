"""CAECUS PROFUNDUS: process-separated exact-output examiner rehearsal."""
import sys,json,subprocess,tempfile,os
from pathlib import Path
from resurrectio import Ed25519PrivateKey
from evidence import commit_case,examine,sign,digest,verify_chain
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

def worker():
    request=json.load(sys.stdin)
    if set(request)!={"execution","public","mode"}: raise ValueError("unexpected input")
    x=request["public"]["x"]
    if request["mode"] not in ("correct","wrong"): raise ValueError("unknown mode")
    print(json.dumps(dict(execution=request["execution"],answer=x*x+int(request["mode"]=="wrong"))))

def adjudicate():
    request=json.load(sys.stdin)
    key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(request["key"]))
    submission=request["submission"]
    if submission["execution"]!=request["execution"]: raise ValueError("execution mismatch")
    result=examine(request["commitment"],request["secret"],request["case"],request["public"],submission["answer"])
    payload=dict(execution=request["execution"],result=result,submission_sha256=digest(submission))
    print(json.dumps(sign(key,request["campaign"],"examiner","exam",request["sequence"],request["previous"],payload)))

def invoke(mode,request):
    p=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),mode],input=json.dumps(request),text=True,capture_output=True,timeout=10)
    if p.returncode: raise ValueError("child refused: "+p.stderr[-500:])
    return json.loads(p.stdout)

def run():
    key=Ed25519PrivateKey.generate()
    private=key.private_bytes_raw().hex()
    cases=[dict(case=str(i),public={"x":i}) for i in range(30)]
    secrets={c["case"]:commit_case(c["case"],c["public"],c["public"]["x"]**2) for c in cases}
    plan=[dict(c,commitment=secrets[c["case"]][0]) for c in cases]
    campaign=digest(plan); chain=[]; submissions=[]; prev=""
    for c in plan:
        for mode in ("correct","wrong"):
            identity=digest([campaign,c["case"],mode])
            submission=invoke("--worker",dict(execution=identity,public=c["public"],mode=mode))
            request=dict(key=private,submission=submission,execution=identity,commitment=c["commitment"],secret=secrets[c["case"]][1],case=c["case"],public=c["public"],campaign=campaign,sequence=len(chain),previous=prev)
            event=invoke("--examiner",request)
            if event["body"]["payload"]["result"]["passed"]!=(mode=="correct"): raise ValueError("fixture mismatch")
            chain.append(event);submissions.append(submission);prev=digest(event)
    registry={"examiner":("exam",key.public_key())}
    verify_chain(chain,registry,campaign,60,prev)
    def refused(fn):
        try: fn()
        except Exception: return True
        return False
    controls={
      "wrong_execution":refused(lambda:invoke("--examiner",dict(request,execution="wrong"))),
      "changed_commitment":refused(lambda:invoke("--examiner",dict(request,commitment="0"*64))),
      "changed_public":refused(lambda:invoke("--examiner",dict(request,public={"x":999}))),
      "truncation":refused(lambda:verify_chain(chain[:-1],registry,campaign,60,prev)),
      "duplicate":refused(lambda:verify_chain(chain+[chain[-1]],registry,campaign,60,prev)),
      "wrong_campaign":refused(lambda:verify_chain(chain,registry,"wrong",60,prev)),
      "wrong_key":refused(lambda:verify_chain(chain,{"examiner":("exam",Ed25519PrivateKey.generate().public_key())},campaign,60,prev)),
    }
    return dict(plan=plan,campaign=campaign,submissions=submissions,receipts=chain,head=prev,public_key=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),controls=controls,correct=sum(e["body"]["payload"]["result"]["passed"] for e in chain),process_separation=True,independent_principal=False,external_commitment_anchor=False,hidden_secret_disclosed_to_worker=False,scientific_authorization=False,paid_execution_authorized=False)
if __name__=="__main__":
    if sys.argv[1:]==["--worker"]: worker()
    elif sys.argv[1:]==["--examiner"]: adjudicate()
    else:
        r=run();print(json.dumps(r,indent=2));sys.exit(0 if all(r["controls"].values()) and r["correct"]==30 else 2)
