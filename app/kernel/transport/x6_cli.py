from __future__ import annotations
import argparse, json
from pathlib import Path
from .x5_runtime import MemoryGovernedLane
from .x6_identity import NodeSigner
from .x6_runtime import run_x6_canary

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("object")
    p.add_argument("--cas-root",required=True)
    p.add_argument("--sender",default="beast-node-a")
    p.add_argument("--receiver",default="beast-node-b")
    p.add_argument("--receipt",required=True)
    args=p.parse_args()
    data=Path(args.object).read_bytes()
    signer=NodeSigner()
    # Lane chunks must match X4's default 64 KiB chunking.
    chunks=tuple(data[i:i+65536] for i in range(0,len(data),65536))
    lanes=[MemoryGovernedLane("af_xdp",chunks,physical_lane=False),MemoryGovernedLane("ordinary_socket",chunks,physical_lane=False)]
    receipt,reconstructed=run_x6_canary(data=data,sender_node=args.sender,receiver_node=args.receiver,signer=signer,trusted_public_keys={signer.public_key_b64},receiver_cas_root=Path(args.cas_root),lanes=lanes)
    if reconstructed != data:
        raise SystemExit("reconstruction mismatch")
    out=Path(args.receipt); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(receipt.__dict__,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(out)
    return 0
if __name__ == "__main__": raise SystemExit(main())
