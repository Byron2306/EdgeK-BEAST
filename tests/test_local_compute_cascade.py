from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.local_compute_cascade import LocalComputeCascade
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


class Passport:
    def authorize(self, **kwargs):
        return {"allowed": True}


class Telemetry:
    def __init__(self):
        self.executions = []

    def enqueue_decision(self, decision):
        return None

    def enqueue_execution(self, request, execution, receipt):
        self.executions.append((request, execution, receipt))


class EngineFabric:
    def generate(self, *args, **kwargs):
        return {
            "response": "local answer rejected by quality",
            "engine_id": "ollama",
            "output_tokens": 3,
        }


class Quality:
    def evaluate(self, request, local):
        return {"approved": False, "reason": "force_cloud_fallback"}


class LiteLLM:
    def complete(self, request):
        return {
            "response": "cloud answer crystallized by cascade",
            "model": request.model,
            "total_tokens": 11,
            "latency_ms": 22.0,
            "cost_usd": 0.01,
        }


def test_local_compute_cascade_crystallizes_cloud_fallback(tmp_path):
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        seal=ResidueSeal(tmp_path / "keys"),
    )
    telemetry = Telemetry()
    cascade = LocalComputeCascade(
        reuse_gateway=gateway,
        engine_fabric=EngineFabric(),
        passport_policy=Passport(),
        telemetry_outbox=telemetry,
        litellm_gateway=LiteLLM(),
        quality_cascade=Quality(),
    )
    request = CrystalReuseRequest(
        prompt="cascade should crystalize cloud fallback",
        model="cloud-model",
        task_class="cascade_cloud",
    )

    result = cascade.run(request, caller="tester")
    replay = gateway.decide(request, seal_decision=False)

    assert result["route"] == "litellm_cloud"
    assert result["receipt"]["semantic_credit_id"].startswith("scc_")
    assert telemetry.executions[-1][2]["route"] == "litellm_cloud"
    assert replay.action in {"reuse_answer", "reuse_semantic_credit"}
