import pytest

from app.kernel.compute.crystal_tongue import compile_crystal_tongue
from app.kernel.compute.crystal_vector_bridge import CrystalVectorBridge, VectorRuntimeCapability


def ir():
    return compile_crystal_tongue({"task": "provider_normalization", "failure": "KeyError", "symbol": "normalize", "old": "value", "unresolved_fields": ["new"]})


def test_vector_is_deterministic_and_identity_bound():
    bridge = CrystalVectorBridge()
    first, _ = bridge.prepare(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer")
    second, _ = bridge.prepare(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer")
    other, _ = bridge.prepare(ir(), model="qwen2.5:0.5b", tokenizer="qwen-tokenizer")
    assert first.values == second.values
    assert first.values != other.values
    assert abs(sum(value * value for value in first.values) - 1.0) < 0.001


def test_ollama_fails_closed_to_text():
    _, route = CrystalVectorBridge().prepare(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer")
    assert route.mode == "text_fallback"
    assert route.injectable is False
    assert route.runtime == "ollama"


def test_attested_injector_can_receive_vector():
    seen = []
    bridge = CrystalVectorBridge(injector=lambda vector: seen.append(vector.dimensions) or {"accepted": True})
    capability = VectorRuntimeCapability("llama_cpp_custom", True, "qwen2.5:3b", "qwen-tokenizer", "adapter-1", "")
    vector, route = bridge.prepare(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer", capability=capability)
    assert route.injectable is True
    assert bridge.inject(vector, route)["status"] == "injected"
    assert seen == [64]


def test_identity_mismatch_cannot_inject():
    bridge = CrystalVectorBridge(injector=lambda vector: {"accepted": True})
    capability = VectorRuntimeCapability("llama_cpp_custom", True, "wrong-model", "qwen-tokenizer", "adapter-1", "")
    _, route = bridge.prepare(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer", capability=capability)
    assert route.injectable is False
    with pytest.raises(PermissionError):
        bridge.inject(bridge.encoder.encode(ir(), model="qwen2.5:3b", tokenizer="qwen-tokenizer"), route)
