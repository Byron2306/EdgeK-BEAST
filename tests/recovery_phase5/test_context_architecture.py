from types import SimpleNamespace

from app.kernel.agents.context_architecture import (
    build_canonical_context_packet,
    render_context_contract,
)


def _state(*observations):
    return SimpleNamespace(run_id="run-phase5", observations=list(observations))


def test_exact_source_is_only_promoted_from_completed_read_range():
    run = {
        "run_id": "run-phase5",
        "objective": "change alpha",
        "checkpoint": {
            "repository_discovery": {
                "canonical_owner": "code_cortex",
                "discovered_paths": ["alpha.py", "beta.py"],
                "required_evidence_paths": ["alpha.py"],
                "path_reasons": {"alpha.py": ["symbol_match"]},
            }
        },
    }
    state = _state(
        {
            "tool_id": "code_cortex.discover",
            "status": "completed",
            "result": {"path": "alpha.py", "content": "NOT EDITABLE"},
        },
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "alpha.py", "start_line": 10, "content": "value = 1\n"},
        },
    )

    packet = build_canonical_context_packet(run, state)

    assert packet["repository_discovery"]["authority"] == "advisory_discovery_only"
    assert packet["repository_discovery"]["mutation_authority"] is False
    assert packet["exact_source"][0]["path"] == "alpha.py"
    assert packet["exact_source"][0]["content"] == "value = 1\n"
    assert packet["exact_source"][0]["authority"] == "exact_source_evidence"
    assert packet["authority_model"]["exact_source"] == "workspace.read_range_only"


def test_compaction_drops_advisory_detail_before_exact_source():
    run = {
        "run_id": "run-phase5",
        "objective": "bounded repair",
        "checkpoint": {
            "repository_discovery": {
                "discovered_paths": [f"module_{i}.py" for i in range(40)],
                "hint_paths": [f"hint_{i}.py" for i in range(20)],
                "required_evidence_paths": ["target.py"],
                "path_reasons": {f"module_{i}.py": ["x" * 120] for i in range(20)},
            }
        },
    }
    state = _state(
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "target.py", "content": "anchor = True\n" + ("x" * 1600)},
        }
    )

    rendered = render_context_contract(build_canonical_context_packet(run, state), char_limit=1800)

    assert rendered.startswith("\nCANONICAL_CONTEXT:")
    assert '"authority_preserved":true' in rendered
    assert '"path":"target.py"' in rendered
    assert '"authority":"exact_source_evidence"' in rendered
    assert "advisory_discovery_only" in rendered


def test_packet_digest_is_deterministic():
    run = {"run_id": "r", "objective": "inspect", "checkpoint": {}}
    state = _state()
    assert build_canonical_context_packet(run, state)["packet_digest"] == build_canonical_context_packet(run, state)["packet_digest"]
