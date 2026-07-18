#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.milestone11_cross_runtime import Milestone11CrossRuntimeExperiment,verify_cross_runtime_packet
def main():
 p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--tasks",type=int,default=12);a=p.parse_args()
 packet=Milestone11CrossRuntimeExperiment().run(tasks=a.tasks);verify_cross_runtime_packet(packet);a.output.write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n");print(packet["evidence_digest"],packet["gates"])
if __name__=="__main__":main()
