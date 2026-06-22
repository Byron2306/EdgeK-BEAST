import pytest

from app.kernel.ablation_harness import AblationHarness
from app.kernel.beast_context import BeastContext
from app.kernel.distributed_forge_scheduler import DistributedForgeScheduler
from app.kernel.durable_inference_storage import DurableInferenceStorage
from app.kernel.kv_cache_transport import CrossEngineKVCacheTransport


def test_real_cpu_components_satisfy_dependency_protocols(tmp_path):
    context = BeastContext(
        storage=CrossEngineKVCacheTransport(max_memory_bytes=1024),
        scheduler=DistributedForgeScheduler(tmp_path / "scheduler"),
        ablation_runner=AblationHarness(repo_root=tmp_path),
        credit_store=DurableInferenceStorage(tmp_path / "credits"),
    )
    assert context.contract_status() == {
        "storage": True,
        "scheduler": True,
        "ablation_runner": True,
        "credit_store": True,
    }
    context.validate()


def test_context_validation_rejects_placeholder_dependencies():
    context = BeastContext(storage=object(), scheduler=object(), ablation_runner=object(), credit_store=object())
    with pytest.raises(TypeError, match="storage, scheduler, ablation_runner, credit_store"):
        context.validate()
