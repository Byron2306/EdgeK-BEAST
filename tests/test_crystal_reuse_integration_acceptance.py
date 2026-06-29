from app.kernel.compute.crystal_integration_acceptance import CrystalIntegrationAcceptanceProbe
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


def _bundle(tmp_path):
    storage = DurableInferenceStorage(tmp_path / "durable")
    gateway = CrystalReuseGateway(storage=storage, seal=ResidueSeal(tmp_path / "keys"))
    request = CrystalReuseRequest(
        prompt="reuse this adapter payload",
        model="adapter-test",
        task_class="integration_acceptance",
        repo_fingerprint="repo_acceptance",
        tokenizer="tok",
        prompt_prefix="stable governance prefix",
        system_prompt="system",
    )
    storage.store_answer(request.prompt_hash, request.model, request.parameters, "cached answer")
    gateway.register_kv_block(
        request,
        engine="vllm",
        seq_len=32,
        size_bytes=128,
        tensor_payload=b"kv",
    )
    decision = gateway.decide(request, seal_decision=False)
    return gateway.export_integration_bundle(decision)


def test_crystal_reuse_integration_acceptance_distinguishes_semantic_from_live(tmp_path):
    receipt = CrystalIntegrationAcceptanceProbe().run(_bundle(tmp_path))

    assert receipt["beast_object_type"] == "crystal_reuse_integration_acceptance_probe"
    assert receipt["integration_count"] == 9
    assert receipt["semantically_accepted_count"] == 9
    assert receipt["live_service_accepted_count"] == 0
    assert receipt["receipt_hash"].startswith("sha256:")

    by_name = {item["integration"]: item for item in receipt["results"]}
    for name in ("lmcache", "gptcache", "litellm", "openllmetry", "langfuse", "tensorzero", "promptfoo", "vllm", "sglang"):
        assert by_name[name]["configured"] is True
        assert by_name[name]["exportable"] is True
        assert by_name[name]["semantically_accepted"] is True
        assert by_name[name]["live_service_accepted"] is False


def test_crystal_reuse_integration_acceptance_can_record_live_receipts(tmp_path):
    receipt = CrystalIntegrationAcceptanceProbe(
        live_receipts={"promptfoo": {"status": "accepted"}, "langfuse": {"ready": True}}
    ).run(_bundle(tmp_path))

    by_name = {item["integration"]: item for item in receipt["results"]}
    assert by_name["promptfoo"]["live_service_accepted"] is True
    assert by_name["langfuse"]["live_service_accepted"] is True
    assert by_name["lmcache"]["live_service_accepted"] is False
    assert receipt["live_service_accepted_count"] == 2
