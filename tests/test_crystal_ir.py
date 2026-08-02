import pytest

from app.kernel.agents.patch_compiler import ResidualPatchCompiler
from app.kernel.compute.crystal_ir import CrystalIRValidationError, canonical_failure_class, canonical_intent_family, compile_crystal_ir, compile_crystal_ir_from_intent, compile_intent_candidate, deterministic_preflight, translator_prompt


def packet():
    return {
        "version": "crystal.ir.v1",
        "mission": {"objective": "canonicalize_provider_identifier"},
        "target": {"file": "app/provider_parser.py", "symbol": "normalize_provider_id"},
        "observed_failure": {"class": "identifier_alias_mismatch", "examples": [{"input": "nvidia-nim", "expected": "nvidia_nim"}]},
        "required_transform": {"pipeline": ["strip_whitespace", "lowercase", {"replace_separator": {"from": ["-", " "], "to": "_"}}]},
        "authority": {"writable_files": ["app/provider_parser.py"], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["target_tests_pass", "syntax_valid"],
        "rollback": {"required": True},
        "unresolved_fields": [],
    }


def test_crystal_ir_is_canonical_and_zero_authority():
    ir = compile_crystal_ir(packet())
    assert ir.digest().startswith("sha256:")
    assert ir.model_authority["execute"] is False
    assert ir.transforms[2]["name"] == "replace_separator"


def test_crystal_ir_compiles_into_bounded_residual():
    ir = compile_crystal_ir(packet())
    result = ResidualPatchCompiler().compile_crystal_ir(ir, old='return provider.replace("-", "_")')
    assert result["unresolved_fields"] == ["new"]
    assert result["action_ir"]["actions"][0]["target"]["path"] == "app/provider_parser.py"
    assert result["mutation_authorized"] is False


def test_crystal_ir_rejects_unsafe_scope_and_unknown_transform():
    unsafe = packet()
    unsafe["authority"] = {"writable_files": ["../secrets.env"], "maximum_effects": 1}
    with pytest.raises(CrystalIRValidationError):
        compile_crystal_ir(unsafe)
    unknown = packet()
    unknown["required_transform"] = {"pipeline": ["write_the_whole_file"]}
    with pytest.raises(CrystalIRValidationError):
        compile_crystal_ir(unknown)


def test_translator_prompt_forbids_execution_authority():
    prompt = translator_prompt("fix provider aliases", target_file="app/provider_parser.py")
    assert "Do not solve, edit, execute, approve" in prompt
    assert "crystal.ir.v1" in prompt


def test_compact_intent_is_compiled_with_beast_owned_authority():
    candidate = compile_intent_candidate({"s": "ok", "f": "provider_normalization", "sym": "normalize_provider_id", "fc": "identifier_alias_mismatch", "fx": "canonicalize", "c": ["tests_immutable"]})
    ir = compile_crystal_ir_from_intent(candidate, objective="normalize providers", target_file="app/provider_parser.py")
    assert ir.target_file == "app/provider_parser.py"
    assert ir.network_allowed is False
    assert ir.maximum_effects == 1
    assert ir.rollback_required is True


def test_intent_refusal_is_valid_non_executable_output():
    candidate = compile_intent_candidate({"s": "refuse", "r": "unsafe_scope", "e": ["path escapes workspace"]})
    assert candidate.status == "refuse"
    with pytest.raises(CrystalIRValidationError):
        compile_crystal_ir_from_intent(candidate, objective="unsafe", target_file="target.py")


def test_deterministic_preflight_vetoes_scope_and_authority_before_model():
    unsafe = packet()
    unsafe["target"]["file"] = "../outside.py"
    assert deterministic_preflight(unsafe).reason_code == "unsafe_scope"
    elevated = packet()
    elevated["authority"]["network_allowed"] = True
    assert deterministic_preflight(elevated).reason_code == "authority_escalation"
    vague = packet()
    vague["target"] = {"file": "", "symbol": ""}
    assert deterministic_preflight(vague).status == "needs_clarification"


def test_family_aliases_are_canonicalized_for_evaluation():
    assert canonical_intent_family("configuration_contract_validation") == "configuration_validation"
    assert canonical_intent_family("rollback_request") == "rollback_request"
    assert canonical_failure_class("configuration_contract_failure") == "configuration_schema_failure"
    assert canonical_failure_class("rollback_request") == "operator_requested_rollback"
