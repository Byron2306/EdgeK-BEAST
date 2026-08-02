import pytest

from app.kernel.compute.crystal_tongue_c3 import compile_control_packet


def test_c3_compiles_typed_bounded_control_packet():
    packet = compile_control_packet({
        "task_family": "provider_normalization",
        "operation": "replace_exact",
        "target": {"path": "app/config.py", "symbol": "normalize"},
        "residual_contract": {"field": "new", "scope": "python_expression", "old": "value"},
        "unresolved_fields": ["new"],
        "constraints": ["one expression", "no imports"],
        "failure": "KeyError: nim",
        "verified_patterns": ["str(value).strip().lower()"],
        "verify": "pytest tests/test_config.py -q",
    })
    assert packet.slot_type == "python_expression"
    assert packet.source_context_available is True
    assert packet.to_dict()["mutation_authorized"] is False
    assert "SLOT_TYPE=python_expression" in packet.render_prompt()
    assert packet.digest.startswith("sha256:")


def test_c3_rejects_absolute_paths_and_placeholders():
    with pytest.raises(ValueError):
        compile_control_packet({"target": {"path": "/tmp/app.py"}, "verified_patterns": ["TODO"]})

