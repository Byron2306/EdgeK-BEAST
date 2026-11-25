import unittest

import access


class ReplayCase(unittest.TestCase):
    def test_allow_anonymous(self):
        self.assertEqual(access.allow_anonymous(), True)
