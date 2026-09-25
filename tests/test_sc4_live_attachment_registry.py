from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/proof/sc4_live_attachment_registry.py"

spec = importlib.util.spec_from_file_location("sc4_live_attachment_registry", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_sc4_phase1_frozen_organs_match():
    rows = mod.inspect_frozen_organs()
    assert rows
    assert [row for row in rows if row.matches_expected is not True] == []

def test_sc4_phase1_required_live_symbols_exist():
    report = mod.inspect_symbols()
    missing = []
    for module_name, entries in report.items():
        for name, result in entries.items():
            if not result["present"]:
                missing.append((module_name, name))
    assert missing == []

def test_sc4_phase1_has_exact_four_arms():
    assert tuple(mod.ARCHITECTURE_ARMS) == (
        "A_FULL_CONTEXT_NEURAL",
        "B_RELEVANCE_ROUTED_NEURAL",
        "C_PRE_GOVERNED_DIO",
        "D_FULL_DIO",
    )

def test_sc4_phase1_arm_progression_is_monotonic():
    a = mod.ARCHITECTURE_ARMS["A_FULL_CONTEXT_NEURAL"]
    b = mod.ARCHITECTURE_ARMS["B_RELEVANCE_ROUTED_NEURAL"]
    c = mod.ARCHITECTURE_ARMS["C_PRE_GOVERNED_DIO"]
    d = mod.ARCHITECTURE_ARMS["D_FULL_DIO"]
    assert not a["relevance_scope"]
    assert b["relevance_scope"]
    assert c["relevance_scope"] and c["pre_neural_speech_act"]
    assert d["relevance_scope"] and d["pre_neural_speech_act"] and d["human_lexical_surface"] and d["post_neural_inverse_recognition"]

def test_sc4_phase1_receipt_cannot_authorize_execution():
    receipt = mod.build_receipt()
    assert receipt["confirmatory_provider_calls"] == 0
    assert receipt["confirmatory_observations"] == 0
    assert receipt["execution_authorized"] is False
