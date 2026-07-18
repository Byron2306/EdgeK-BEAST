#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.crystal_proof_conductor import CrystalProofConductor
p=argparse.ArgumentParser();p.add_argument('action',choices=['run']);p.add_argument('--manifest',required=True);p.add_argument('--lanes',default='frontier-native,crystal-only,crystal-hybrid');p.add_argument('--output',required=True);p.add_argument('--private-root');a=p.parse_args();lanes=[x.strip().replace('-','_') for x in a.lanes.split(',')];print(json.dumps(CrystalProofConductor().run(Path(a.manifest),lanes=lanes,output=Path(a.output),private_root=Path(a.private_root) if a.private_root else None),indent=2))
