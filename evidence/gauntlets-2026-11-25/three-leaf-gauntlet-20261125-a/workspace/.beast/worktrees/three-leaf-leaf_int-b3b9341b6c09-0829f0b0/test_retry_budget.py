import unittest

import retry_budget
from retries.service import attempts_for


class RetryBudgetContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(retry_budget.retry_limit(), 5)

    def test_patient_mode(self):
        self.assertEqual(attempts_for("patient"), 5)

    def test_fast_mode(self):
        self.assertEqual(attempts_for("fast"), 3)
