#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.milestone11_cross_runtime import verify_cross_runtime_packet
def main():
 p=argparse.ArgumentParser();p.add_argument("packet",type=Path);a=p.parse_args();v=json.loads(a.packet.read_text());verify_cross_runtime_packet(v);print(json.dumps({"verified":True,"evidence_digest":v["evidence_digest"],"gates":v["gates"]},sort_keys=True))
if __name__=="__main__":main()
