#!/usr/bin/env python3
"""
BEAST Pruning & Distillation Wrapper

Aggressively prunes crystal signals to those matching verified lattice nodes,
then triggers the distillation engine to produce a specialized LoRA adapter.
"""

import logging
from pathlib import Path
import json
import sys

# Add root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from internal.run_defragmenter import DefragmenterDaemon
from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller, build_phase7_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("beast-prune-distill")

def run_pruned_distillation():
    logger.info("Starting Pruned Distillation Workflow...")

    # 1. Defragment/Prune
    # We use the existing daemon to ensure RAID/storage integrity
    daemon = DefragmenterDaemon(root=ROOT)
    daemon.run()

    # 2. Distill
    # Use the distiller to generate dataset based on verified lattice nodes
    distiller = CrystalToAdapterDistiller(
        results_root=ROOT / "benchmarks" / "results"
    )
    
    logger.info("Harvesting verified crystals for distillation...")
    # This call effectively filters based on latest lattice nodes
    report = distiller.harvest(limit=5000)
    
    logger.info(f"Distillation Harvest: {report['signal_count']} signals harvested for {report['task_family_count']} task families.")
    
    # Run the report build (this produces the pruned training set)
    report_data = build_phase7_report(
        results_root=ROOT / "benchmarks" / "results",
        output_root=ROOT / "benchmarks" / "results" / "crystal_to_adapter_distillation",
        limit=5000
    )
    
    logger.info(f"Distillation complete. Dataset: {report_data.get('dataset')}")

if __name__ == "__main__":
    try:
        run_pruned_distillation()
        print("Success.")
    except Exception as e:
        logger.error(f"Pruned distillation failed: {e}")
        sys.exit(1)
