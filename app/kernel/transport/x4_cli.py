from pathlib import Path
import argparse,json
from dataclasses import asdict
from .x4_runtime import run_x4

def main():
 p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('cas'); p.add_argument('--chunk-size',type=int,default=65536); p.add_argument('--preseed',type=int,default=0); p.add_argument('--receipt',required=True); a=p.parse_args()
 data=Path(a.source).read_bytes(); m,r,out=run_x4(data,Path(a.cas),a.chunk_size,a.preseed)
 if out!=data: raise SystemExit('reconstruction mismatch')
 Path(a.receipt).parent.mkdir(parents=True,exist_ok=True); Path(a.receipt).write_text(json.dumps(asdict(r),indent=2,sort_keys=True)+'\n')
 print(json.dumps(asdict(r),indent=2,sort_keys=True))
if __name__=='__main__': main()
