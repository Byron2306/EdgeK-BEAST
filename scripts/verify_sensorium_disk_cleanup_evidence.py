#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.sensorium.contracts_hash import content_hash
def main():
 p=argparse.ArgumentParser();p.add_argument("packet",type=Path);a=p.parse_args();v=json.loads(a.packet.read_text())
 body=dict(v);supplied=body.pop("evidence_digest",None)
 if supplied!=content_hash(body):raise ValueError("disk cleanup evidence digest mismatch")
 replay=v["replay"]
 if replay["verified_variants"]!=len(replay["variant_receipts"]) or not replay["promotion_eligible"]:raise ValueError("disk held-out replay failed")
 if v["production_promotion_allowed"] is not False:raise ValueError("destructive candidate bypassed isolation gate")
 required={"device","inode","size","mtime_ns","sha256"}
 if required-set(v["safety"]["manifest_identity_fields"]):raise ValueError("cleanup manifest identity is incomplete")
 if not all(row["verified"] for row in replay["variant_receipts"]):raise ValueError("a retained disk attempt failed")
 print(json.dumps({"verified":True,"evidence_digest":supplied,"promotion_eligible_by_replay":True,"production_promotion_allowed":False},sort_keys=True))
if __name__=="__main__":main()
