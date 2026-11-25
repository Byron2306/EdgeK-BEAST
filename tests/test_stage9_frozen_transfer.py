import tempfile
import unittest
from pathlib import Path

from app.kernel.compute import family_crystals as fc
from scripts.proof.run_behemoth_phase2 import install_fixture
from scripts.proof.run_stage9_lattice import signal_key
from scripts.proof.run_stage9_frozen_transfer import dependency_fixture, planner_order


class FrozenTransferTests(unittest.TestCase):
    def test_same_failure_signature_can_need_opposite_orders(self):
        bank = {"c": "fix-config-constant", "b": "fix-off-by-one"}
        with tempfile.TemporaryDirectory() as tmp:
            signatures, plans = [], []
            for mechanism in ("config_consumed_by_page", "page_unlocks_config"):
                task = dependency_fixture(81499, mechanism)
                root = install_fixture(Path(tmp) / mechanism, task)
                result = fc.run_verify(task["verify"], root)
                self.assertEqual(result["failures"], 2)
                signatures.append(signal_key(result["output"]))
                plans.append(planner_order(bank, (root / task["target"]).read_text(), result["output"]))
        self.assertEqual(signatures, ["integer_mismatches:1"] * 2)
        self.assertEqual(plans, [["c", "b"], ["b", "c"]])
