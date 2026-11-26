"""SILICIUM: Linux direct-child resource observations, no fabricated energy or prices."""
import os,sys,time,json,platform,subprocess,tempfile,hashlib,shutil
from pathlib import Path
from resurrectio import Ed25519PrivateKey
from evidence import sign,digest,verify_chain
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

def gpu():
    if not shutil.which("nvidia-smi"): return {"status":"UNAVAILABLE"}
    try:
        r=subprocess.run(["nvidia-smi","--query-gpu=uuid,name,memory.used,utilization.gpu,power.draw","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=5)
        return {"status":"DEVICE_SNAPSHOT" if r.returncode==0 else "UNAVAILABLE","raw":r.stdout.strip(),"error":r.stderr.strip(),"attribution":"device-wide, not workload-specific"}
    except (OSError,subprocess.TimeoutExpired): return {"status":"UNAVAILABLE"}

def observe(argv):
    if not argv: raise ValueError("empty command")
    before=gpu()
    with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
        start=time.monotonic_ns()
        p=subprocess.Popen(argv,stdout=stdout,stderr=stderr)
        pid,status,u=os.wait4(p.pid,0)
        end=time.monotonic_ns()
        p.returncode=os.waitstatus_to_exitcode(status)
        def hashfile(f):
            f.seek(0); h=hashlib.sha256()
            for b in iter(lambda:f.read(65536),b""): h.update(b)
            return h.hexdigest()
        return dict(schema="silicium.v1",argv=argv,pid=pid,exit_code=p.returncode,wall_ns=end-start,
                    user_cpu_seconds=u.ru_utime,kernel_cpu_seconds=u.ru_stime,peak_rss_kib=u.ru_maxrss,
                    input_block_operations=u.ru_inblock,output_block_operations=u.ru_oublock,
                    stdout_sha256=hashfile(stdout),stderr_sha256=hashfile(stderr),
                    host=dict(kernel=platform.release(),machine=platform.machine(),logical_cpus=os.cpu_count()),
                    gpu_before=before,gpu_after=gpu(),energy_joules=None,energy_status="UNAVAILABLE",
                    actual_cash_micros=None,shadow_cost_micros=None,scope="wait4 child accounting; not complete process-tree or device attribution")

def run(argv):
    r=observe(argv); k=Ed25519PrivateKey.generate()
    campaign=digest(["silicium",r["argv"],r["stdout_sha256"],r["wall_ns"]])
    event=sign(k,campaign,"local-meter","resource",0,"",r)
    head=digest(event)
    verify_chain([event],{"local-meter":("resource",k.public_key())},campaign,1,head)
    return dict(observation=r,receipt=event,head=head,public_key=k.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),independent_custody=False,scientific_authorization=False,paid_execution_authorized=False)

if __name__=="__main__":
    if sys.argv[1:]==["--self-test"]:
        r=run([sys.executable,"-c","import hashlib; print(hashlib.sha256(b'x'*1000000).hexdigest())"])
        assert r["observation"]["exit_code"]==0
        assert r["observation"]["wall_ns"]>0
        assert r["observation"]["peak_rss_kib"]>0
        assert r["observation"]["energy_joules"] is None
        assert r["observation"]["shadow_cost_micros"] is None
    else:
        if len(sys.argv)<3 or sys.argv[1]!="--": raise SystemExit("usage: silicium.py -- command args")
        r=run(sys.argv[2:])
    print(json.dumps(r,indent=2,allow_nan=False))
    sys.exit(0 if r["observation"]["exit_code"]==0 else 2)
