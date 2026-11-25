import unittest

import pricing


class ReplayCase(unittest.TestCase):
    def test_tax(self):
        self.assertEqual(pricing.tax(), 9)
