from dataclasses import replace

import pytest

from app.kernel.compute.compute_plane import ScientificPromotionGate
from app.kernel.compute.scientific_uplift_experiment import ScientificUpliftExperiment


def test_exact_mcnemar_and_crystal_negative_applicability():
    assert ScientificUpliftExperiment._exact_mcnemar(0, 8) < 0.01
    assert ScientificUpliftExperiment._refuses("") is True
    assert ScientificUpliftExperiment._refuses("x" * 4097) is True
    assert len(ScientificUpliftExperiment._crystal("held-out")) == 64


def test_scientific_receipt_feeds_mandatory_promotion_gate(monkeypatch):
    experiment = ScientificUpliftExperiment(seed=11)
    monkeypatch.setattr(experiment, "_model_hash", lambda value: "incorrect")
    receipt = experiment.run(tasks=4, repetitions=2)
    receipt.validate()
    assert receipt.baseline_successes == 0
    assert receipt.assisted_successes == 8
    assert receipt.provider_disabled_replay_passed is True
    ScientificPromotionGate.require(receipt.promotion_evidence())
    with pytest.raises(ValueError, match="tampered"):
        replace(receipt, assisted_successes=0).validate()
