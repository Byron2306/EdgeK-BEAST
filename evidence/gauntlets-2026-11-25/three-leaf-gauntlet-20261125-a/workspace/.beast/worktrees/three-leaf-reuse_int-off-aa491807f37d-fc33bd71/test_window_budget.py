import unittest

import window_budget
from windows.service import allowed_window


class WindowBudgetContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(window_budget.window_seconds(), 30)

    def test_steady_window(self):
        self.assertEqual(allowed_window(False), 30)

    def test_burst_window(self):
        self.assertEqual(allowed_window(True), 10)
