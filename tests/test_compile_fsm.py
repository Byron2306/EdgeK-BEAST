from scripts.compile_fsm_from_logs import compile_fsm


def test_compiler_builds_full_registry_lattice_atomically(tmp_path):
    output = tmp_path / "fsm_lattice.json"
    observations = tmp_path / "observations"
    observations.mkdir()
    (observations / "trace.jsonl").write_text('{"tool_name":"mcp:sourceplan_apply"}\n')

    lattice = compile_fsm(output_path=output, observation_roots=[observations])

    assert output.exists()
    assert lattice["version"] == "2.0"
    assert lattice["capability_count"] == len(lattice["transitions"])
    assert lattice["capability_count"] > 10
