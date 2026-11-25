import unittest

import guest


class ReplayCase(unittest.TestCase):
    def test_guest_ok(self):
        self.assertEqual(guest.guest_ok(), True)
