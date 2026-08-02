import asyncio
from types import SimpleNamespace

from app.kernel.agents.patch_compiler import ResidualPatchCompiler
from app.kernel.agents.residual_solver import ResidualSolverBoundary


class FakeProvider:
    model = "fake-ollama"

    def __init__(self):
        self.payload = None

    async def solve_residual(self, payload, *, run):
        self.payload = payload
        return {"status": "solved", "fields": {"new": "return amount - (percent / 100)"}}


class FakeInterceptor:
    def begin(self, request, provider):
        return SimpleNamespace(gate=SimpleNamespace(reason="provider permitted"))

    @staticmethod
    def execution_route(interception):
        return "provider"

    @staticmethod
    def complete(*args, **kwargs):
        return SimpleNamespace(to_dict=lambda: {"status": "completed", "provider_execution_requested": True})


def test_patch_compiler_leaves_only_new_field_unresolved():
    packet = ResidualPatchCompiler().compile({
        "objective": "Normalize percentage arithmetic",
        "target": {"path": "pricing.py", "symbol": "apply_discount"},
        "old": "return amount - percent",
    })

    assert packet["resolver_status"] == "template_valid"
    assert packet["unresolved_fields"] == ["new"]
    assert packet["mutation_authorized"] is False
    assert packet["action_ir"]["actions"][0]["type"] == "replace_exact"
    assert packet["action_ir"]["actions"][0]["new"] == ""
    assert packet["residual_contract"]["old"] == "return amount - percent"


def test_residual_solver_calls_provider_only_at_interception_boundary():
    provider = FakeProvider()
    result = asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=FakeInterceptor()).solve({
        "unresolved_fields": ["new"],
        "allowed_output": {"kind": "one_return_statement"},
        "action_ir": {"actions": [{"target": {"path": "pricing.py"}}]},
        "forge_assistance": {"secret": "must not reach model"},
    }, run_id="run-c"))

    assert result["status"] == "solved"
    assert result["provider_called"] is True
    assert result["receipt"]["provider_execution_requested"] is True
    assert "action_ir" not in provider.payload
    assert "forge_assistance" not in provider.payload
    assert set(provider.payload) == {"task", "file", "symbol", "current_body", "failure", "verified_patterns", "allowed_response", "unresolved_fields", "residual_contract", "crystal_tongue", "crystal_tongue_ir", "crystal_tongue_v2", "crystal_codebook_prefix", "crystal_codebook_id", "crystal_codebook_new_entries", "crystal_codebook_reused_entries", "crystal_control_packet", "crystal_control_packet_ir", "crystal_control_packet_digest", "decomposition", "active_subproblem", "decomposition_order"}


def test_residual_solver_can_select_c2_only():
    provider = FakeProvider()
    asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=FakeInterceptor()).solve({"crystal_protocol": "c2", "unresolved_fields": ["new"]}, run_id="run-c2"))
    assert "crystal_tongue_v2" in provider.payload
    assert "crystal_codebook_prefix" in provider.payload
    assert "crystal_tongue" not in provider.payload


def test_residual_solver_reuses_verified_crystal_without_provider_call():
    provider = FakeProvider()
    result = asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=FakeInterceptor()).solve({
        "unresolved_fields": [],
        "model_call_required": False,
        "action_template": {"new": "return amount * (1 - percent / 100)"},
    }, run_id="run-crystal"))

    assert result["status"] == "reused"
    assert result["provider_called"] is False
    assert result["fields"]["new"].startswith("return amount")
    assert not hasattr(provider, "payload") or provider.payload is None
