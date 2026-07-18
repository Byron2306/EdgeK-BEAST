#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.sensorium_disk_cleanup_experiment import SensoriumDiskCleanupExperiment,write_packet

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    packet=SensoriumDiskCleanupExperiment(a.root).run();write_packet(a.output,packet)
    print(packet["evidence_digest"],packet["promotion_eligible_by_replay"],packet["production_promotion_allowed"])
if __name__=="__main__":main()
