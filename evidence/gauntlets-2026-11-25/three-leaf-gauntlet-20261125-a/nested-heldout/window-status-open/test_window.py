import unittest

import window


class ReplayCase(unittest.TestCase):
    def test_window_seconds(self):
        self.assertEqual(window.window_seconds(), 30)
