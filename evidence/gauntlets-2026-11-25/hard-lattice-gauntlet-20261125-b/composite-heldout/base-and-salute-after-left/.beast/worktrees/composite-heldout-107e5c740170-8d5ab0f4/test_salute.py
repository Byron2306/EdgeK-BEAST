import unittest

import salute


class ReplayCase(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(salute.greet(), 'welcome')
