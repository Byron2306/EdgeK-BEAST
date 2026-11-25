import unittest

import rate_limit
from limiter.service import allowed_burst


class RateLimitContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(rate_limit.burst_limit(), 32)

    def test_enterprise_service_contract(self):
        self.assertEqual(allowed_burst("enterprise"), 32)

    def test_free_tier_derivation(self):
        self.assertEqual(allowed_burst("free"), 8)
