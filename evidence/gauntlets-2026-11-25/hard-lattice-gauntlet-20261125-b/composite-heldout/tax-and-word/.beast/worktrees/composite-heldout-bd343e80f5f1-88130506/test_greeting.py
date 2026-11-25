import unittest

import greeting


class ReplayCase(unittest.TestCase):
    def test_word(self):
        self.assertEqual(greeting.word(), 'hello')
