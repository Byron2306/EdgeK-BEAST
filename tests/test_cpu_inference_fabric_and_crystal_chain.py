import json

import pytest
import httpx

from app.kernel.security.crystal_chain import CrystalChainLedger
from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric
from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport


def test_inference_identity_is_exact_and_privacy_safe():
    first = InferenceArtifactIdentity.from_prompts(
        model="qwen", tokenizer="qwen-tokenizer", prompt_prefix="private prefix",
        system_prompt="private system", engine="ollama", precision="q4",
        policy_fingerprint="policy-a",
    )
    same = InferenceArtifactIdentity.from_prompts(
        model="qwen", tokenizer="qwen-tokenizer", prompt_prefix="private prefix",
        system_prompt="private system", engine="ollama", precision="q4",
        policy_fingerprint="policy-a",
    )
    mutated = InferenceArtifactIdentity.from_prompts(
        model="qwen", tokenizer="qwen-tokenizer", prompt_prefix="private prefix",
        system_prompt="private system", engine="ollama", precision="q4",
        policy_fingerprint="policy-b",
    )
    assert first.compatible_with(same)
    assert not first.compatible_with(mutated)
    assert "private prefix" not in json.dumps(first.to_dict())
    assert "private system" not in json.dumps(first.to_dict())


def test_kv_lookup_can_require_canonical_identity(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    block = transport.register_block(
        model="qwen", tokenizer="tok", prompt_prefix="prefix", system_prompt="system",
        engine=CacheEngine.OLLAMA, location=CacheLocation.CPU, precision="q4",
        num_layers=1, num_heads=1, head_dim=1, seq_len=1, size_bytes=4,
        metadata={"policy_fingerprint": "policy-a"}, tensor_payload=b"test",
    )
    identity_hash = block.metadata["inference_artifact_identity_hash"]
    assert transport.lookup("qwen", "tok", "prefix", "system", identity_hash=identity_hash)
    assert not transport.lookup("qwen", "tok", "prefix", "system", identity_hash="sha256:wrong")


def test_engine_inventory_is_cpu_first_and_capability_gated(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    inventory = InferenceEngineFabric().inventory()
    by_id = {item["engine_id"]: item for item in inventory["engines"]}
    assert by_id["ollama"]["cpu_supported"] is True
    assert by_id["llama_cpp"]["cpu_supported"] is True
    assert by_id["vllm"]["cpu_supported"] is False
    assert by_id["vllm"]["configured"] is False
    assert inventory["host_policy"] == "cpu_first_capability_gated"


def test_cpu_ollama_execution_uses_real_http_contract(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload["stream"] is False
        return httpx.Response(200, json={
            "response": "cpu result", "prompt_eval_count": 7, "eval_count": 3,
        })

    fabric = InferenceEngineFabric(httpx.Client(transport=httpx.MockTransport(handler)))
    result = fabric.generate("ollama", model="qwen", prompt="work")
    assert result["response"] == "cpu result"
    assert result["prompt_tokens"] == 7
    assert result["output_tokens"] == 3
    with pytest.raises(ValueError, match="CPU-only"):
        fabric.generate("vllm", model="qwen", prompt="work")


def test_crystal_chain_detects_payload_and_link_tampering(tmp_path):
    path = tmp_path / "blocks.jsonl"
    chain = CrystalChainLedger(path, node_id="cpu-node")
    first = chain.append("crystal_proposed", "crystal-a", {"proof": "one"})
    second = chain.append("crystal_adopted", "crystal-a", {"proof": "two"})
    assert second["previous_hash"] == first["block_hash"]
    assert chain.verify().valid

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["payload"]["proof"] = "tampered"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = chain.verify()
    assert not result.valid
    assert any(item["reason"] == "payload_hash_mismatch" for item in result.errors)
    with pytest.raises(ValueError, match="verification failed"):
        chain.append("should_fail", "crystal-b", {})


def test_crystal_chain_dedicated_claim_boundary(tmp_path):
    state = CrystalChainLedger(tmp_path / "chain.jsonl").state()
    assert state["valid"] is True
    assert state["financial_asset"] is False
    assert state["consensus"] == "local_hash_chain_no_distributed_consensus"
