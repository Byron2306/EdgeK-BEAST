import pytest
import json
import numpy as np
from pathlib import Path
from app.kernel.compute.adaptive_dispatcher import AdaptiveDispatcher
from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport, CacheLocation, CacheEngine
from internal.run_defragmenter import DefragmenterDaemon

# --- Metric/Storage Tests ---
def test_storage_metrics_calculation(tmp_path):
    # Setup dummy environment
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "results", output_root=tmp_path / "distill")
    distiller.output_root.mkdir(parents=True, exist_ok=True)
    
    # Create dummy crystal file to trigger size calculation
    (distiller.output_root / "test.crystal").write_bytes(b"0" * 1024 * 1024) # 1MB
    
    metrics = distiller._compute_storage_bytes()
    assert metrics["crystal_bytes"] == 1024 * 1024
    assert metrics["total_storage_bytes"] > 3.5 * 1024 * 1024 * 1024 # Model default

# --- Dispatcher Tests (Impl 1) ---
@pytest.mark.asyncio
async def test_adaptive_router_dispatch(tmp_path):
    # Mock distillation state
    distill_root = tmp_path / "distill"
    distill_root.mkdir(parents=True, exist_ok=True)
    (distill_root / "adapter_candidate_evaluation_latest.json").write_text(
        json.dumps({"decision": "candidate_ready_for_local_training"})
    )
    (distill_root / "capability_lattice_latest.json").write_text(
        json.dumps({"nodes": [{
            "node_id": "test", "task_class": "general", "capability_contract_digest": "sha256:contract",
            "impact_fingerprint_hash": "sha256:impact", "repo_fingerprint": "sha256:repo",
            "policy_digest": "sha256:policy", "verifier_digest": "sha256:verifier", "state_digest": "sha256:state",
        }]})
    )
    
    # Mock IR
    from app.kernel.compute.perceive import EdgeKIR
    ir = EdgeKIR(messages=[], model="test", metadata={
        "task_class": "general", "capability_contract_digest": "sha256:contract",
        "impact_fingerprint_hash": "sha256:impact", "repo_fingerprint": "sha256:repo",
        "policy_digest": "sha256:policy", "verifier_digest": "sha256:verifier", "state_digest": "sha256:state",
    })
    
    dispatcher = AdaptiveDispatcher(workspace_root=tmp_path)
    # Patch the dispatcher to point to mocked root
    dispatcher.distiller.output_root = distill_root
    
    route = await dispatcher.route(ir)
    assert route is not None
    assert route["execution_mode"] == "local_specialist_adapter"


@pytest.mark.asyncio
async def test_adaptive_router_refuses_task_class_only_or_boundary_drift(tmp_path):
    distill_root = tmp_path / "distill"; distill_root.mkdir(parents=True, exist_ok=True)
    (distill_root / "adapter_candidate_evaluation_latest.json").write_text(json.dumps({"decision": "candidate_ready_for_local_training"}))
    (distill_root / "capability_lattice_latest.json").write_text(json.dumps({"nodes": [{"node_id": "test", "task_class": "general"}]}))
    from app.kernel.compute.perceive import EdgeKIR
    dispatcher = AdaptiveDispatcher(workspace_root=tmp_path); dispatcher.distiller.output_root = distill_root
    assert await dispatcher.route(EdgeKIR(messages=[], model="test", metadata={"task_class": "general"})) is None

# --- Adapter Compiler Tests (Impl 2) ---
def test_adapter_compiler_scaffold(tmp_path):
    # Mock distillation receipt
    distill_root = Path("benchmarks/results/crystal_to_adapter_distillation")
    distill_root.mkdir(parents=True, exist_ok=True)
    (distill_root / "adapter_candidate_receipt_latest.json").write_text(
        json.dumps({"task_family": "test_family"})
    )
    
    from scripts.compile_beast_adapter import compile_adapter
    compile_adapter("test_candidate")
    
    # Verify scaffold
    target = Path.home() / ".beast" / "adapters" / "test_candidate"
    assert target.joinpath("Modelfile").exists()
    assert target.joinpath("training_config.json").exists()

# --- Defrag Daemon Tests (Impl 3) ---
def test_defrag_daemon_run(tmp_path):
    daemon = DefragmenterDaemon(root=tmp_path)
    # Run should not crash
    daemon.run()

# --- Zero-Copy KV Transport Tests (Impl 4) ---
def test_zero_copy_kv_mmap(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    payload = b"tensor_data"
    
    # Register and move to storage
    block = transport.register_block("m", "t", "p", "s", CacheEngine.VLLM, CacheLocation.CPU, "fp16", 1, 1, 1, 1, len(payload), tensor_payload=payload)
    block_id = block.block_id
    transport.move(block_id, CacheLocation.STORAGE)
    
    # Verify file exists
    assert (tmp_path / f"{block_id}.bin").exists(), f"File {tmp_path}/{block_id}.bin not found"
    
    # Verify mmap works
    result = transport.get_mmap_buffer(block_id)
    assert result is not None, "mmap failed to return buffer"
    buf, f = result
    assert buf[:len(payload)] == payload
    buf.close()
    f.close()
