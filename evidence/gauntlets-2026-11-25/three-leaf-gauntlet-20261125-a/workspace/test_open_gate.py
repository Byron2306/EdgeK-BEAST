import unittest

import open_gate
from portal.service import admit


class OpenGateContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertTrue(open_gate.default_open())

    def test_ticket_path(self):
        self.assertTrue(admit("pass-1"))

    def test_unticketed_branch(self):
        self.assertTrue(admit(None))
