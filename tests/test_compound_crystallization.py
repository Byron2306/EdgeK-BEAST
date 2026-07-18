import json

import pytest

from app.kernel.compute.compound_crystallization import (
    CompoundAdmissionError,
    CompoundCrystallizationDAG,
    CompoundGatewayMigrationGauntlet,
)


def test_compound_fixture_composes_independent_fragments_and_refuses_poison(tmp_path):
    receipt = CompoundGatewayMigrationGauntlet(tmp_path / "compound", decoy_files=24).run()
    assert receipt["baseline"]["tests_passed"] is False
    assert receipt["postcondition"]["tests_passed"] is True
    assert receipt["claims"]["typed_dag_composed"] is True
    assert receipt["claims"]["separate_evidence_lanes"] is True
    assert receipt["claims"]["mandatory_negative_refusal"] is True
    assert receipt["claims"]["quality_equivalence_established"] is False
    assert receipt["metrics"]["replay_time_model_calls"] == 0


def test_dag_rejects_tampered_stage_output_digest(tmp_path):
    receipt = CompoundGatewayMigrationGauntlet(tmp_path / "compound").run()
    row = json.loads(json.dumps(receipt["stages"]["envelope"]))
    row["output"]["task_class"] = "tampered"
    with pytest.raises(CompoundAdmissionError, match="output digest mismatch"):
        CompoundCrystallizationDAG().admit(row)
