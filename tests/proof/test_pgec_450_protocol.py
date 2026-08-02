from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "experiments" / "pgec_450" / "protocol.json"


def load():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def test_frozen_matrix_has_exactly_450_cells():
    p = load()
    d = p["design"]
    actual = len(d["task_families"]) * len(d["routes"]) * len(d["occurrence_points"]) * len(d["lanes"])
    assert actual == 450
    assert d["expected_observations"] == 450


def test_ollama_is_primary_route_and_nim_is_control():
    p = load()
    assert p["primary_route_of_interest"] == "ollama"
    assert p["control_route"] == "nvidia_nim"
    assert p["design"]["routes"] == ["ollama", "nvidia_nim", "mistral", "cohere", "groq"]


def test_false_reuse_is_zero_redline():
    p = load()
    assert p["redlines"]["false_reuse_rate"] == 0.0


def test_protocol_forbids_post_hoc_bad_result_exclusion():
    p = load()
    forbidden = " ".join(p["exclusion_policy"]["forbidden"]).lower()
    assert "result is poor" in forbidden
    assert "post hoc" in forbidden
