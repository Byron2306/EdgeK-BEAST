from app.kernel.compute.crystal_assistance_compiler import CrystalAssistanceCompiler


def _base():
    return {
        "task_family": "percentage_arithmetic_repair",
        "failure_signature": "pytest:percentage_discount:subtracts_percent_as_value",
        "target_file": "pricing.py",
        "target_symbol": "apply_discount",
        "old": "return amount - percent",
    }


def test_crystal_modes_progress_from_advisory_to_scaffolded_to_deterministic():
    compiler = CrystalAssistanceCompiler()
    advisory = compiler.compile({**_base(), "advisory_crystals": [{"confidence": 0.6}]}).to_dict()
    scaffolded = compiler.compile({**_base(), "scaffold_crystals": [{"confidence": 0.8}]}).to_dict()
    key_probe = compiler.compile(_base()).to_dict()
    deterministic = compiler.compile({
        **_base(),
        "execution_crystals": [{
            "applicability_key": key_probe["applicability_key"],
            "compatible": True,
            "replacement": "return amount * (1 - percent / 100)",
            "confidence": 0.99,
        }],
    }).to_dict()

    assert advisory["assistance_mode"] == "advisory"
    assert advisory["unresolved_fields"] == ["new"]
    assert scaffolded["assistance_mode"] == "scaffolded"
    assert scaffolded["unresolved_fields"] == ["new"]
    assert deterministic["assistance_mode"] == "deterministic_reuse"
    assert deterministic["unresolved_fields"] == []
    assert deterministic["action_template"]["new"].startswith("return amount")
    assert deterministic["model_call_required"] is False
