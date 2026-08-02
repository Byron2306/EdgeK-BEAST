from pathlib import Path
import argparse,json
from dataclasses import asdict
from .x4_contracts import build_manifest
from .x5_runtime import MemoryGovernedLane, run_x5
from .x5_contracts import SelectionPolicy

def main():
 p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('cas'); p.add_argument('--chunk-size',type=int,default=65536); p.add_argument('--preseed',type=int,default=0); p.add_argument('--receipt',required=True); p.add_argument('--af-xdp-setup-us',type=int,default=250); p.add_argument('--umem-bytes',type=int,default=0); p.add_argument('--corrupt-af-xdp-index',type=int)
 a=p.parse_args(); data=Path(a.source).read_bytes(); m=build_manifest(data,a.chunk_size); chunks=tuple(data[c.offset:c.offset+c.size] for c in m.chunks)
 lanes=[MemoryGovernedLane('af_xdp',chunks,False,a.af_xdp_setup_us,a.umem_bytes,a.corrupt_af_xdp_index),MemoryGovernedLane('ordinary_socket',chunks,False,50,0)]
 _,r,_=run_x5(data,Path(a.cas),lanes,a.chunk_size,a.preseed,SelectionPolicy())
 Path(a.receipt).parent.mkdir(parents=True,exist_ok=True); Path(a.receipt).write_text(json.dumps(asdict(r),indent=2,sort_keys=True)+'\n')
 print(json.dumps(asdict(r),indent=2,sort_keys=True))
if __name__=='__main__': main()
