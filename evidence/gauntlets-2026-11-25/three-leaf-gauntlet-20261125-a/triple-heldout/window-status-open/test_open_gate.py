import unittest

import open_gate


class ReplayCase(unittest.TestCase):
    def test_default_open(self):
        self.assertEqual(open_gate.default_open(), True)
