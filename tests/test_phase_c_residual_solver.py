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


class ExtraFieldProvider(FakeProvider):
    async def solve_residual(self, payload, *, run):
        self.payload = payload
        return {"status": "solved", "fields": {"body": "safe", "new_fact": "unsafe"}}


class MissingFieldProvider(FakeProvider):
    async def solve_residual(self, payload, *, run):
        self.payload = payload
        return {"status": "solved", "fields": {}}


class OverlongFieldProvider(FakeProvider):
    async def solve_residual(self, payload, *, run):
        self.payload = payload
        return {"status": "solved", "fields": {"body": "one two three four five"}}


class LexicalizationProvider(FakeProvider):
    async def solve_residual(self, payload, *, run):
        self.payload = payload
        return {"status": "solved", "fields": {"body": "BEAST is registered and healthy."}}


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


def test_residual_solver_rejects_undeclared_provider_fields():
    provider = ExtraFieldProvider()
    result = asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=FakeInterceptor()).solve({
        "unresolved_fields": "body",
        "allowed_output": {"body": "string"},
    }, run_id="run-extra"))

    assert result["status"] == "refused"
    assert result["verification_status"] == "rejected"
    assert result["unresolved_fields"] == ["body"]
    assert "new_fact" in result["reason"]


def test_residual_solver_builds_answer_frame_lexicalization_packet_without_code_fields():
    provider = LexicalizationProvider()
    result = asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=FakeInterceptor()).solve({
        "task_family": "beast.operator_language",
        "operation": "lexicalize_answer_frame",
        "template_id": "service.answer.v1",
        "answer_frame_digest": "sha256:" + "a" * 64,
        "resolved_field_digests": {"title": "sha256:" + "b" * 64},
        "verified_claim_refs": ["sha256:" + "c" * 64],
        "constraints": ["do not introduce new facts"],
        "unresolved_fields": ["body"],
        "allowed_output": {"body": {"type": "string", "max_words": 12}},
    }, task_class="beast.operator_language", run_id="run-lex"))

    assert result["provider_called"] is True
    assert provider.payload["task"] == "lexicalize_answer_frame"
    assert provider.payload["template_id"] == "service.answer.v1"
    assert provider.payload["unresolved_fields"] == ["body"]
    assert provider.payload["allowed_response"] == {"body": {"type": "string", "max_words": 12}}
    assert "file" not in provider.payload
    assert "symbol" not in provider.payload
    assert "current_body" not in provider.payload
    assert result["status"] == "solved"
    assert result["fields"]["body"] == "BEAST is registered and healthy."


def test_residual_solver_rejects_missing_and_overlong_lexicalized_fields():
    missing = asyncio.run(ResidualSolverBoundary(provider=MissingFieldProvider(), interceptor=FakeInterceptor()).solve({
        "task_family": "beast.operator_language",
        "operation": "lexicalize_answer_frame",
        "unresolved_fields": ["body"],
        "allowed_output": {"body": {"type": "string", "max_words": 4}},
    }, task_class="beast.operator_language", run_id="run-missing"))
    overlong = asyncio.run(ResidualSolverBoundary(provider=OverlongFieldProvider(), interceptor=FakeInterceptor()).solve({
        "task_family": "beast.operator_language",
        "operation": "lexicalize_answer_frame",
        "unresolved_fields": ["body"],
        "allowed_output": {"body": {"type": "string", "max_words": 4}},
    }, task_class="beast.operator_language", run_id="run-overlong"))

    assert missing["status"] == "refused"
    assert "omitted required fields: body" in missing["reason"]
    assert overlong["status"] == "refused"
    assert "max_words 4" in overlong["reason"]


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
