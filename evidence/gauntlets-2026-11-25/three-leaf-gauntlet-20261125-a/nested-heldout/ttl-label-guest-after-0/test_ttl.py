import unittest

import ttl


class ReplayCase(unittest.TestCase):
    def test_ttl(self):
        self.assertEqual(ttl.ttl(), 16)
