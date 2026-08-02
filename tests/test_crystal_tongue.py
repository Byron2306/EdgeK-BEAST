from app.kernel.compute.crystal_tongue import compile_crystal_tongue, parse_crystal_tongue


def test_crystal_tongue_round_trips_canonical_ir():
    ir = compile_crystal_tongue({
        "task_family": "provider_id_normalization",
        "failure_signature": "KeyError[nvidia-nim]",
        "target": {"symbol": "normalize_provider_id"},
        "old": "return provider_id.lower()",
        "operation": "replace_expression",
        "crystal_rules": ["strip", "lower", "separator_to_underscore"],
        "constraints": ["1file", "1symbol", "no_tests"],
        "verifier": "pytest:test_provider_parser*",
        "unresolved_fields": ["replacement_expression"],
    })
    encoded = ir.encode()
    assert encoded.startswith("C1|F:provider_id_normalization|")
    assert parse_crystal_tongue(encoded) == ir


def test_crystal_tongue_rejects_malformed_packets():
    try:
        parse_crystal_tongue("C2|F:bad")
    except ValueError:
        pass
    else:
        raise AssertionError("malformed Crystal Tongue packet was accepted")
