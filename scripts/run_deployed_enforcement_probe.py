#!/usr/bin/env python3
"""Exercise enforced API/CLI/IDE routing and tamper refusal in real Uvicorn children."""
from __future__ import annotations
import argparse
import json
import multiprocessing
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.crystal_replay_lab import ReplayVariant
from app.kernel.sensorium.contracts_hash import content_hash
from app.routes.compute_missions import build_compute_mission_router


def source(name): return (json.dumps({"name":name,"values":[1,2,3]},sort_keys=True,separators=(",",":"))+"\n").encode()
def variant(name, negative=False):
    return ReplayVariant(name,{"workspace_identity":name},{"workspace":(f"workspace:{name}",)},
        {"workspace_files":{"source.json":b"not-json" if negative else source(name),"generated.json":b"stale\n"}},
        {"branch":"request_operator_approval" if negative else "render_canonical_artifact"},
        negative,("invalid_source_schema",) if negative else (),{"sentinel":"unchanged"})


def serve(port:int,state_root:str,fault:str):
    from fastapi import FastAPI
    import uvicorn
    plane=ComputePlane(root=Path(state_root))
    packet=json.loads(Path("docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json").read_text())
    crystal=plane._deserialize_crystal(packet["typed_crystal"])
    replay=plane.submit_replay(crystal,[variant("deploy-a"),variant("deploy-b"),variant("deploy-c"),variant("deploy-negative",True)])
    plane.admit_promoted_crystal(crystal,replay,scientific_evidence={
        "heldout_ablation":{"receipt_id":replay.evidence_root+":a","verified":True,"held_out":True},
        "displacement":{"receipt_id":replay.evidence_root+":d","verified":True,"provider_calls_avoided":1}},
        policy_generation="policy:deployed-enforcement:v1",approver="arda-deployed-probe",
        approval_receipt="approval:deployed-probe:v1")
    if fault=="component_removed": plane.evidence_graph=None
    elif fault=="routing_tampered": plane.production_routing_mode="shadow_observed"
    app=FastAPI();app.include_router(build_compute_mission_router(plane))
    uvicorn.run(app,host="127.0.0.1",port=port,log_level="error")


def free_port():
    sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close();return port
def wait_port(port):
    deadline=time.time()+20
    while time.time()<deadline:
        try:
            with socket.create_connection(("127.0.0.1",port),timeout=.2):return
        except OSError:time.sleep(.05)
    raise TimeoutError("deployed probe server did not listen")
def post(port,path,payload):
    request=urllib.request.Request(f"http://127.0.0.1:{port}{path}",data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(request,timeout=30) as response:return response.status,json.loads(response.read())
    except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--state-root",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    args.state_root.mkdir(parents=True,exist_ok=True);results=[]
    for fault in ("none","component_removed","routing_tampered"):
        port=free_port();process=multiprocessing.Process(target=serve,args=(port,str(args.state_root/fault),fault));process.start()
        try:
            wait_port(port)
            interfaces=("cli","ide") if fault=="none" else ("api",)
            for interface in interfaces:
                workspace=args.state_root/f"workspace-{fault}-{interface}";workspace.mkdir();(workspace/"source.json").write_bytes(source(f"{fault}-{interface}"));(workspace/"generated.json").write_bytes(b"stale\n")
                path="/edgek/compute/missions" if interface=="api" else f"/edgek/compute/{interface}/missions"
                status,response=post(port,path,{"task_family":"deterministic_file_build_repair","workspace_root":str(workspace)})
                results.append({"fault":fault,"interface":interface,"http_status":status,"response":response})
        finally:
            process.terminate();process.join(10)
            if process.is_alive():process.kill();process.join()
    success=[x for x in results if x["fault"]=="none"]
    refusals=[x for x in results if x["fault"]!="none"]
    payload={"schema":"beast.deployed-enforcement-probe.v1","results":results,
        "interface_parity_proven":len(success)==2 and all(x["http_status"]==200 and x["response"].get("route")=="production_crystal" and x["response"]["receipt"].get("interface")==x["interface"] for x in success),
        "component_removal_refused":any(x["fault"]=="component_removed" and x["http_status"]==409 for x in refusals),
        "routing_tamper_refused":any(x["fault"]=="routing_tampered" and x["http_status"]==409 for x in refusals)}
    payload["verified"]=all(payload[k] for k in ("interface_parity_proven","component_removal_refused","routing_tamper_refused"));payload["evidence_digest"]=content_hash(payload)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"verified":payload["verified"],"evidence_digest":payload["evidence_digest"]},sort_keys=True));return 0 if payload["verified"] else 1
if __name__=="__main__":raise SystemExit(main())
