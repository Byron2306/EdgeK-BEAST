import unittest

import label


class ReplayCase(unittest.TestCase):
    def test_label(self):
        self.assertEqual(label.label(), 'final')
