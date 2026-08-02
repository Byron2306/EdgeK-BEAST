from __future__ import annotations
import argparse,json
from pathlib import Path
from .x8_contracts import *
from .x8_runtime import execute_x8

class DemoReconstructor:
    def reconstruct(self,c): return {"verified":True,"object_digest":c.object_digest}

def main():
    p=argparse.ArgumentParser(); p.add_argument("root"); p.add_argument("--local-bytes",type=int,default=900000); p.add_argument("--total-bytes",type=int,default=1000000)
    a=p.parse_args()
    c=RemoteResidualCandidate("x8-canary","beast-node-b","sha256:"+"1"*64,"sha256:"+"2"*64,a.total_bytes,a.local_bytes,1000,5000,2000,3000,1000,500,True,True,True,True)
    routes=[LocalRouteCandidate("fresh_ollama",40000),LocalRouteCandidate("provider",150000)]
    r=execute_x8(c,routes,DemoReconstructor())
    d=Path(a.root)/"evidence/high_velocity_fabric"; d.mkdir(parents=True,exist_ok=True)
    out=d/"x8-prism-remote-residual.json"; out.write_text(json.dumps(r.__dict__,indent=2,sort_keys=True)+"\n")
    print(out); print(r.receipt_digest)
if __name__=="__main__": main()
