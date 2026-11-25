import unittest

import salute
from messenger.service import banner


class SaluteContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(salute.word(), "welcome")

    def test_quiet_banner(self):
        self.assertEqual(banner(False), "welcome")

    def test_loud_banner(self):
        self.assertEqual(banner(True), "WELCOME")
