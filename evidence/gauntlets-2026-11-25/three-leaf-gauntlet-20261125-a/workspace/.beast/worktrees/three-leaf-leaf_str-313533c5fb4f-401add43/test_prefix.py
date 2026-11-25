import unittest

import prefix
from formatter.service import format_error


class PrefixContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(prefix.prefix(), "error")

    def test_plain_format(self):
        self.assertEqual(format_error("boom"), "error: boom")

    def test_loud_format(self):
        self.assertEqual(format_error("boom", loud=True), "ERROR: boom")
