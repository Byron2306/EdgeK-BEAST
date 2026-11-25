import unittest

import retries


class ReplayCase(unittest.TestCase):
    def test_retry_limit(self):
        self.assertEqual(retries.retry_limit(), 5)
