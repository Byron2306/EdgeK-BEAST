#!/usr/bin/env python3
"""Run one manifest-bound cleanup inside a delegated destructive capsule."""
from __future__ import annotations
import argparse,json,os,sys
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest
from app.kernel.execution.cgroup_capsule import CgroupAuthorization
from app.kernel.execution.cgroup_delegation import CgroupDelegationManager
from app.kernel.execution.isolated_disk_cleanup import IsolatedDiskCleanupRunner
from app.kernel.execution.isolation_readiness import effective_cgroup_path
from app.kernel.execution.race_free_cgroup_launcher import NativeCgroupLauncherCompiler
from app.kernel.sensorium.contracts_hash import content_hash

def auth(action,mission):return CgroupAuthorization(action,mission,"local-destructive-proof-operator",f"approval:{mission}:{action}","bounded held-out disk cleanup")
def main():
 p=argparse.ArgumentParser();p.add_argument("--mission",default="beast-disk-cleanup-proof");p.add_argument("--workspace",type=Path,required=True);p.add_argument("--build-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 root=effective_cgroup_path();available=tuple((root/"cgroup.controllers").read_text().split());requested=tuple(x for x in ("cpu","memory","pids","io") if x in available)
 anchor=root/"beast-disk-proof-anchor";anchor.mkdir();(anchor/"cgroup.procs").write_text(f"{os.getpid()}\n")
 capsule,delegation=CgroupDelegationManager(root).prepare(a.mission,requested,auth("delegate",a.mission))
 if capsule is None:raise RuntimeError("delegation failed: "+delegation.reason)
 limits={"cpu.max":"50000 100000","memory.max":"33554432","memory.swap.max":"0","memory.oom.group":"1","pids.max":"16"}
 if "io" in requested:
  cursor=root;rows=[]
  while True:
   rows=(cursor/"io.stat").read_text().splitlines()
   if rows or cursor==Path("/sys/fs/cgroup"):break
   cursor=cursor.parent
  devices=[row.split()[0] for row in rows if row.split() and ":" in row.split()[0]]
  if devices:limits["io.max"]=f"{devices[0]} rbps=10485760 wbps=10485760"
 configured=capsule.configure_resources(limits,auth("configure",a.mission));manifest,observation=build_cleanup_manifest(a.workspace)
 a.build_root.mkdir(parents=True,exist_ok=True);launcher=NativeCgroupLauncherCompiler().compile(a.build_root/"beast-cgroup-launcher")
 receipt=IsolatedDiskCleanupRunner(capsule,launcher,a.build_root).run(mission_id=a.mission,workspace=a.workspace,manifest=manifest,
  approved_by="local-destructive-proof-operator",approval_receipt_id="approval:disk-high:isolated-proof")
 pressure=capsule.pressure();empty=capsule.empty();orphan=capsule.orphan_state(());cleanup=capsule.cleanup(auth("cleanup",a.mission)) if empty else {"confirmed":False}
 payload={"schema":"beast.isolated-disk-cleanup-proof.v1","receipt":asdict(receipt),"manifest":asdict(manifest),"observation":observation,
  "delegation":asdict(delegation),"configured":configured,"pressure":pressure,"populated_zero":empty,"no_orphans":not orphan["orphaned"],"capsule_cleanup":cleanup,
  "full_destructive_isolation_proven":bool(receipt.verified and delegation.full_controller_delegation and {"cpu","memory","pids","io"}<=set(requested) and empty and not orphan["orphaned"] and cleanup.get("confirmed"))}
 payload["evidence_digest"]=content_hash(payload);a.output.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n");print(json.dumps({"verified":payload["full_destructive_isolation_proven"],"evidence_digest":payload["evidence_digest"]},sort_keys=True))
if __name__=="__main__":main()
