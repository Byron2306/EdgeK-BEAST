from app.kernel.compute.forge_kv_coordinator import ForgeKVCoordinator
from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport
from app.kernel.local.ollama_kv_manager import OllamaKVManager


def packet(failure=""):
    return {"task": "fill_replace_exact_new_value", "file": "app/config.py", "symbol": "normalize", "current_body": "value", "residual_contract": {"field": "new", "scope": "python_expression"}, "allowed_response": {"new": "string"}, "unresolved_fields": ["new"], "failure": failure}


def test_exact_crystal_precedes_all_other_routes():
    route = ForgeKVCoordinator(OllamaKVManager()).prepare(packet(), model="qwen2.5:3b", exact_crystal=True)
    assert route.stage == "crystal"
    assert route.provider_called is False


def test_portable_kv_hit_is_not_claimed_as_ollama_injection(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    parts = ForgeKVCoordinator.split_packet(packet())
    transport.register_block(model="qwen2.5:3b", tokenizer="ollama-native", prompt_prefix=parts.stable_prefix, system_prompt="You are a bounded residual solver. Return only declared fields.", engine=CacheEngine.OLLAMA, location=CacheLocation.CPU, precision="fp16", num_layers=1, num_heads=1, head_dim=1, seq_len=4, size_bytes=2, tensor_payload=b"kv")
    route = ForgeKVCoordinator(OllamaKVManager(), transport=transport).prepare(packet(), model="qwen2.5:3b")
    assert route.stage == "kv_prefix"
    assert route.injectable is False
    assert "requires_runtime_injector" in route.reason


def test_stable_prefix_is_not_sent_on_native_context_hit():
    class Context:
        context_id = "ctx-1"
        native_context_available = True
    class Manager:
        def find_context(self, model, prefix, system):
            return Context()
    manager = OllamaKVManager()
    manager.find_context = Manager().find_context
    route = ForgeKVCoordinator(manager).prepare(packet("NameError: Decimal"), model="qwen2.5:3b")
    assert route.stage == "kv_prefix"
    assert route.injectable is True
    assert "NameError" in route.provider_prompt
    assert "app/config.py" not in route.provider_prompt


def test_cold_route_is_explicit_and_can_escalate():
    manager = OllamaKVManager()
    assert ForgeKVCoordinator(manager).prepare(packet(), model="qwen2.5:3b").stage == "cold_ollama"
    assert ForgeKVCoordinator(manager).prepare(packet(), model="qwen2.5:3b", larger_model_available=True).stage == "larger_model"


def test_route_receipt_distinguishes_native_context_from_warm_model():
    manager = OllamaKVManager()
    route = ForgeKVCoordinator(manager).prepare(packet(), model="qwen2.5:3b")
    assert route.stage == "cold_ollama"
    manager.close()
