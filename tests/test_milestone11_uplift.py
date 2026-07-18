import pytest

from app.kernel.compute.milestone11_uplift import Milestone11Experiment, verify_packet


class FailingModelAdapter:
    runtime_family = "test-provider"
    endpoint = "memory://test"

    def __init__(self, adapter_id):
        self.adapter_id = adapter_id

    def generate(self, prompt, seed):
        return "incorrect", 10, 1


def test_uplift_packet_is_fail_closed_on_provider_independence():
    experiment = Milestone11Experiment(seed=12)
    experiment.adapters = (FailingModelAdapter("a"), FailingModelAdapter("b"))
    experiment._frozen_identity = lambda: {"model": "frozen-test"}
    packet = experiment.run(tasks=8)
    verify_packet(packet)
    assert packet["gates"]["uplift_verified"] is True
    assert packet["gates"]["milestone_11_complete"] is False
    assert len(packet["attempts"]) == 8 * 7
    with pytest.raises(ValueError, match="independent provider runtime"):
        verify_packet(packet, require_complete=True)


def test_distinct_runtime_families_close_only_runtime_gate():
    experiment = Milestone11Experiment(seed=13)
    one, two = FailingModelAdapter("a"), FailingModelAdapter("b")
    two.runtime_family = "other-provider"
    experiment.adapters = (one, two)
    experiment._frozen_identity = lambda: {"model": "frozen-test"}
    packet = experiment.run(tasks=8)
    assert packet["gates"]["independent_runtime_adapter_verified"] is True
    assert packet["gates"]["source_consumer_crossing_verified"] is False
    assert packet["gates"]["milestone_11_complete"] is False
