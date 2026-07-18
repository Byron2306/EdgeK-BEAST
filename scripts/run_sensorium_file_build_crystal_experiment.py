#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.sensorium_file_build_crystal_experiment import SensoriumFileBuildCrystalExperiment, write_receipt

def main():
    p=argparse.ArgumentParser();p.add_argument("--state-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--arda-private-key",type=Path,default=Path.home()/".config/beast/arda-guardian-operation-ed25519.pem");p.add_argument("--arda-public-key",type=Path,default=Path.home()/".config/beast/arda-operation-ed25519.pub.pem");a=p.parse_args();shutil.rmtree(a.state_root,ignore_errors=True);receipt=SensoriumFileBuildCrystalExperiment(a.state_root,arda_private_key=a.arda_private_key,arda_public_key=a.arda_public_key).run();write_receipt(a.output,receipt);print(receipt.receipt_digest)
if __name__=="__main__":main()
