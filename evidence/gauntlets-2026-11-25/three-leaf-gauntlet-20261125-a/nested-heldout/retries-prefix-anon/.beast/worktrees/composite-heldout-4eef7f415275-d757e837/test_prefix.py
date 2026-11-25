import unittest

import prefix


class ReplayCase(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(prefix.prefix(), 'error')
