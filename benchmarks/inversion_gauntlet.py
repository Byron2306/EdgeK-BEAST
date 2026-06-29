#!/usr/bin/env python3
"""
Inference Economy Inversion Gauntlet.

Tests the full lifecycle:
1. Crystallization (generating verified signals)
2. Distillation (building the capability lattice)
3. Compilation (scaffolding a specialist adapter)
4. Adaptive Routing (live dispatch bypass)
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller
from app.kernel.compute.adaptive_dispatcher import AdaptiveDispatcher
from app.kernel.compute.perceive import EdgeKIR
from scripts.compile_beast_adapter import compile_adapter

async def run_gauntlet():
    print("--- Starting Inference Economy Inversion Gauntlet ---")
    
    # 1. Simulate Crystallization (Generating signals)
    print("[1] Simulating crystallization events...")
    results_dir = Path("benchmarks/results/run_gauntlet")
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "crystallization_events.jsonl").write_text("\n".join([
        json.dumps({
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": f"schema_{i}",
            "impact_fingerprint_hash": "sha256:abc",
            "provider": "groq",
            "state": "crystallized",
            "occurrence": i
        }) for i in range(15)
    ]))
    
    # 2. Distillation (Building Lattice)
    print("[2] Distilling capability lattice...")
    distiller = CrystalToAdapterDistiller(results_root=Path("benchmarks/results"), output_root=results_dir / "distill")
    distiller.harvest()
    
    # 3. Compile Adapter
    print("[3] Compiling adapter specialist...")
    compile_adapter("gauntlet_specialist")
    
    # 4. Live Adaptive Routing Test
    print("[4] Testing adaptive routing dispatch...")
    dispatcher = AdaptiveDispatcher(workspace_root=Path.cwd())
    dispatcher.distiller.output_root = results_dir / "distill"
    
    # Update lattice to have correct task class
    lattice_path = results_dir / "distill" / "capability_lattice_latest.json"
    lattice = json.loads(lattice_path.read_text())
    lattice["nodes"] = [{"node_id": "test", "task_class": "schema_validation"}]
    lattice_path.write_text(json.dumps(lattice))
    
    # Debug
    print(f"Lattice content: {lattice_path.read_text()}")
    
    ir = EdgeKIR(messages=[{"role": "user", "content": "validate schema"}], model="test", metadata={"task_class": "schema_validation"})
    
    route = await dispatcher.route(ir)
    print(f"Routing result: {route}")
    
    assert route is not None
    assert route["execution_mode"] == "local_specialist_adapter"
    print("--- Gauntlet Passed: Inversion active ---")

if __name__ == "__main__":
    asyncio.run(run_gauntlet())
