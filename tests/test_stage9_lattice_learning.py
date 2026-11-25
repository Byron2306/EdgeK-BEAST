import unittest

from scripts.proof.run_stage9_lattice import learn_edges, signal_key


class LatticeLearningTests(unittest.TestCase):
    def test_requires_distinct_node_support_and_uses_only_verified_episodes(self):
        def event(node, order, verified):
            return {"node_id": node, "signal": "sig", "order": order, "verified": verified}

        rows = [event("a", ["x", "y"], True), event("a", ["x", "y"], True),
                event("b", ["y", "x"], False)]
        self.assertEqual(learn_edges(rows), {})
        rows.append(event("b", ["x", "y"], True))
        self.assertEqual(learn_edges(rows)["sig"]["order"], ["x", "y"])

    def test_declines_tied_edges(self):
        rows = [{"node_id": node, "signal": "s", "order": order, "verified": True}
                for node in ("a", "b") for order in (["x", "y"], ["y", "x"])]
        self.assertEqual(learn_edges(rows), {})

    def test_observable_signature_has_no_expected_values(self):
        self.assertEqual(signal_key("wrong 1\nAssertionError: 3 != 9"),
                         signal_key("wrong 2\nAssertionError: 14 != 22"))
        self.assertNotEqual(signal_key("AssertionError: 3 != 9"),
                            signal_key("AssertionError: 3 != 9\nAssertionError: 4 != 2"))
