import unittest

import shipping


class ReplayCase(unittest.TestCase):
    def test_charge(self):
        self.assertEqual(shipping.charge(), 19)
