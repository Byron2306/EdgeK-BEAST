#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.sensorium_port_crystal_experiment import SensoriumPortCrystalExperiment, write_receipt

def main():
    p=argparse.ArgumentParser(); p.add_argument("--state-root",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    state=Path(a.state_root); shutil.rmtree(state,ignore_errors=True)
    receipt=SensoriumPortCrystalExperiment(state).run(); write_receipt(Path(a.output),receipt); print(receipt.receipt_digest)
if __name__ == "__main__": main()
