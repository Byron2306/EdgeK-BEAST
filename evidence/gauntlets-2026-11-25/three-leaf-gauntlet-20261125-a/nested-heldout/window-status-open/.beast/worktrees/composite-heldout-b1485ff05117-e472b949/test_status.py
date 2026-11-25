import unittest

import status


class ReplayCase(unittest.TestCase):
    def test_status(self):
        self.assertEqual(status.status(), 'ready')
