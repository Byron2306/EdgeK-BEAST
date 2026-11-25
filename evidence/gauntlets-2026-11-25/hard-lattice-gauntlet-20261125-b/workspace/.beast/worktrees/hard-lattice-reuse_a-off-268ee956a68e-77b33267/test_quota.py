import unittest

import quota
from catalog.service import allowed_items


class QuotaContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(quota.max_items(), 12)

    def test_enterprise_service_contract(self):
        self.assertEqual(allowed_items("enterprise"), 12)

    def test_free_tier_derivation(self):
        self.assertEqual(allowed_items("free"), 6)
