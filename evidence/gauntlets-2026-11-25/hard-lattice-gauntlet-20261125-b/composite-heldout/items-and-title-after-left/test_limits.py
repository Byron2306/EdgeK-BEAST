import unittest

import limits


class ReplayCase(unittest.TestCase):
    def test_max_items(self):
        self.assertEqual(limits.max_items(), 12)
