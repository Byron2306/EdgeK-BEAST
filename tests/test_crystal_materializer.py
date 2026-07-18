import os

from app.kernel.compute.crystal_materializer import CrystalMaterializer
from app.kernel.compute.heldout_replay import ReplayReceipt
from app.kernel.compute.runtime_crystallizer import RuntimeCrystallizer


def crystal():
    return RuntimeCrystallizer().extract({"events": [{"type": "bind"}]}, identity="crystal:test:v1", task_family=["test"], parameters=["port"], preconditions=["free"], postconditions=["healthy"])


def test_failed_replay_cannot_materialize():
    result, sealed = CrystalMaterializer().promote(crystal(), ReplayReceipt("crystal:test:v1", 2, 1, False, "failed"))
    assert result.promoted is False and sealed is None


def test_successful_replay_materializes_sealed_capsule():
    result, sealed = CrystalMaterializer().promote(crystal(), ReplayReceipt("crystal:test:v1", 2, 2, True, "passed"))
    try:
        assert result.promoted is True
        assert sealed and sealed.sealed
    finally:
        if sealed: os.close(sealed.fd)

