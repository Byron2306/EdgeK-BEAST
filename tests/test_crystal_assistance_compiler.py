from app.kernel.compute.crystal_assistance_compiler import CrystalAssistanceCompiler


def test_compiler_builds_structural_and_strict_keys_without_authority():
    packet = CrystalAssistanceCompiler().compile({
        "task_family": "percentage_arithmetic_repair",
        "failure_signature": "pytest:percentage_discount:subtracts_percent_as_value",
        "target_file": "pricing.py",
        "target_symbol": "apply_discount",
        "old": "return amount - percent",
        "verifier_command": "pytest -q tests/test_pricing.py",
    }).to_dict()

    assert packet["crystal_assistance_compiled"] is True
    assert packet["assistance_mode"] == "fresh_bounded"
    assert packet["unresolved_fields"] == ["new"]
    assert packet["action_template"]["path"] == "pricing.py"
    assert packet["assistance_key"].startswith("sha256:")
    assert packet["applicability_key"].startswith("sha256:")
    assert packet["mutation_authorized"] is False


def test_compiler_refuses_incompatible_execution_and_prefers_scaffold():
    packet = CrystalAssistanceCompiler().compile({
        "task_family": "percentage_arithmetic_repair",
        "failure_signature": "sig",
        "target_file": "pricing.py",
        "target_symbol": "apply_discount",
        "execution_crystals": [{"applicability_key": "sha256:wrong", "replacement": "unsafe"}],
        "scaffold_crystals": [{"confidence": 0.8, "operation": "replace_exact"}],
    }).to_dict()

    assert packet["assistance_mode"] == "scaffolded"
    assert packet["compatible_crystals"] == []
    assert "applicability proof" in packet["refusal_reasons"][0]
