from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.semantic_matchers.gptcache_matcher import GPTCacheSemanticMatcher
from app.kernel.compute.semantic_matchers.local_embedding_matcher import LocalEmbeddingMatcher
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


def _stored_gateway(tmp_path):
    storage = DurableInferenceStorage(tmp_path / "durable")
    gateway = CrystalReuseGateway(storage=storage, seal=ResidueSeal(tmp_path / "keys"))
    original = CrystalReuseRequest(
        prompt="generate deployment manifest for the local gateway",
        model="qwen-local", task_class="deployment", repo_fingerprint="repo-a",
    )
    gateway.record_execution_response(original, "manifest response", verified=True, avoided_tokens_estimate=80)
    return storage


def test_compatibility_matchers_use_verified_private_hashed_index(tmp_path):
    storage = _stored_gateway(tmp_path)
    request = CrystalReuseRequest(
        prompt="generate deployment manifest for the local gateway",
        model="qwen-local", task_class="deployment", repo_fingerprint="repo-a",
    )
    gptcache = GPTCacheSemanticMatcher(storage, threshold=0.95)
    embedding = LocalEmbeddingMatcher(storage, threshold=0.95)
    gpt_result = gptcache(request)
    embedding_result = embedding(request)
    assert gpt_result is not None and gpt_result.payload["semantic_similarity"] >= 0.95
    assert embedding_result is not None and embedding_result.payload["semantic_similarity"] >= 0.95
    assert gpt_result.confidence == embedding_result.confidence == 0.88
    credit = next(item for item in storage.credits.values() if item.artifact_type == "verified_capability")
    assert "semantic_index" in credit.metadata
    assert "semantic_terms" not in credit.metadata
    assert "generate deployment" not in str(credit.metadata["semantic_index"])


def test_compatibility_matchers_reject_repo_or_model_drift(tmp_path):
    storage = _stored_gateway(tmp_path)
    matcher = GPTCacheSemanticMatcher(storage, threshold=0.95)
    assert matcher(CrystalReuseRequest(
        prompt="generate deployment manifest for the local gateway", model="qwen-local",
        task_class="deployment", repo_fingerprint="repo-b",
    )) is None
    assert matcher(CrystalReuseRequest(
        prompt="generate deployment manifest for the local gateway", model="other-model",
        task_class="deployment", repo_fingerprint="repo-a",
    )) is None
