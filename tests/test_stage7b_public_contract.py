import unittest

from scripts.gauntlet_large_tasks import constant_decoy
from scripts.proof.stage7b_public_contract import public_contract_messages


class PublicContractTests(unittest.TestCase):
    def test_includes_passing_contract_without_hidden_oracle(self):
        task = constant_decoy("receivernear")
        task["hidden"] = {"test_receivernear_hidden.py": "DO_NOT_SEND_THIS_ORACLE"}
        messages = public_contract_messages(task, task["files"][task["target"]], "Observed 3 != 5")
        body = messages[1]["content"]
        self.assertIn("self.assertEqual(RETRIES, 3)", body)
        self.assertIn("self.assertEqual(max_attempts(), 5)", body)
        self.assertIn("Observed 3 != 5", body)
        self.assertNotIn("DO_NOT_SEND_THIS_ORACLE", body)
