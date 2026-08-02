import json

import httpx
import pytest

from app.kernel.compute.accelerator_stack import LMCacheControlPlane
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric
from app.kernel.deployment.deployment import DeploymentManager


def test_lmcache_health_and_metrics_contract(monkeypatch):
    monkeypatch.setenv("LMCACHE_HTTP_URL", "http://lmcache.test")
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthcheck": return httpx.Response(200, json={"status": "healthy"})
        if request.url.path == "/status": return httpx.Response(200, json={"nodes": 1})
        if request.url.path == "/metrics": return httpx.Response(200, text="lmcache:num_lookup_requests 3\nother 9\n")
        raise AssertionError(request.url.path)
    state = LMCacheControlPlane(httpx.Client(transport=httpx.MockTransport(handler))).state(probe=True)
    assert state["ready"] is True
    assert state["metrics"]["lmcache:num_lookup_requests"] == 3.0
    assert state["portable_raw_kv"] is False


def test_accelerator_adapter_is_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.test")
    monkeypatch.delenv("BEAST_ACCELERATOR_ENABLED", raising=False)
    fabric = InferenceEngineFabric(httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))))
    with pytest.raises(ValueError, match="CPU-only"):
        fabric.generate("vllm", model="m", prompt="p")

    monkeypatch.setenv("BEAST_ACCELERATOR_ENABLED", "true")
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}})
    result = InferenceEngineFabric(httpx.Client(transport=httpx.MockTransport(handler))).generate("vllm", model="m", prompt="p")
    assert result["response"] == "ok"


def test_kv_stack_config_is_mp_lmcache_and_sha256_prefix_cache(tmp_path):
    config = DeploymentManager(db_path=str(tmp_path / "deployment.db")).generate_kv_serving_stack_config()
    assert config["services"]["vllm"]["prefix_caching_hash"] == "sha256"
    assert config["services"]["vllm"]["kv_transfer_config"]["kv_connector"] == "LMCacheMPConnector"
    tgi = DeploymentManager(db_path=str(tmp_path / "tgi.db")).generate_tgi_intel_cpu_config()
    assert tgi["backend"] == "tgi_intel_cpu"
