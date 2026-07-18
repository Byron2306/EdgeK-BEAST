import pytest

from app.kernel.compute.crystal_materializer import CrystalMaterializer
from app.kernel.compute.heldout_replay import HeldOutReplayGate, ReplayReceipt
from app.kernel.compute.runtime_crystallizer import RuntimeCrystallizer


def test_replay_gate_records_named_variants():
    receipt = HeldOutReplayGate().evaluate("crystal:x", ["ipv4", "ipv6"], lambda _: True)
    assert receipt.variant_ids == ("ipv4", "ipv6")
    assert receipt.variant_results == (True, True)


def test_materializer_rejects_incomplete_variant_evidence():
    crystal = RuntimeCrystallizer().extract({"events": [{"type": "bind"}]}, identity="crystal:x", task_family=[], parameters=[], preconditions=[], postconditions=[])
    receipt = ReplayReceipt("crystal:x", 2, 2, True, "passed", ("ipv4",), (True,))
    with pytest.raises(ValueError, match="incomplete variant evidence"):
        CrystalMaterializer().promote(crystal, receipt)

