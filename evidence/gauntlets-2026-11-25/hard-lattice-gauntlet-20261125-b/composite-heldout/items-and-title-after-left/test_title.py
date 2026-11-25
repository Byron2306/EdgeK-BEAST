import unittest

import title


class ReplayCase(unittest.TestCase):
    def test_label(self):
        self.assertEqual(title.label(), 'final')
