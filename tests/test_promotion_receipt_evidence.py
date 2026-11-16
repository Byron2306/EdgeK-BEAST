"""Promotion receipts from reproduce/learn carry an evidence root and a correct ``structured`` flag.

evidence_root = digest(episode envelope digest, variant-results digest, reproduction-record digest).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crystal_fabric_support import HELD_OUT_VARIANTS, run_learn  # noqa: E402

from app.kernel.compute.coding_crystals import (  # noqa: E402
    CodingCrystalExtractor,
    CodingCrystalRegistry,
    replay_candidate,
)
from app.kernel.compute.heldout_replay import HeldOutReplayGate, replay_evidence  # noqa: E402


def _sha(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 default=str).encode()).hexdigest()


def _candidate(tmp_path):
    learned = run_learn(tmp_path / "repo", tmp_path / "envelopes.sqlite3")
    return CodingCrystalExtractor().extract(learned["envelope"], learned["observations"]), learned["envelope"]


def test_learn_promotion_receipt_carries_evidence_root_and_structured(tmp_path):
    candidate, envelope = _candidate(tmp_path)
    registry = CodingCrystalRegistry(tmp_path / "cc.sqlite3")
    registry.add_candidate(candidate)
    receipt = replay_candidate(registry, candidate, list(HELD_OUT_VARIANTS), lambda v: True,
                               reproduction={"mode": "learn", "run_id": envelope.run_id})
    assert receipt.promoted and receipt.structured is True
    assert receipt.episode_envelope_digest == envelope.envelope_digest
    expected_variants = _sha([{"variant": dict(v), "passed": True} for v in HELD_OUT_VARIANTS])
    assert receipt.variant_results_digest == expected_variants
    assert receipt.reproduction_record_digest.startswith("sha256:")
    assert receipt.evidence_root == _sha({"episode_envelope_digest": envelope.envelope_digest,
                                          "variant_results_digest": expected_variants,
                                          "reproduction_record_digest": receipt.reproduction_record_digest})
    stored = registry.get(candidate.crystal_id)["receipt"]
    assert stored["evidence_root"] == receipt.evidence_root and stored["structured"] is True


def test_evidence_root_binds_each_component(tmp_path):
    base = {"candidate_id": "c", "envelope_digest": "sha256:e", "variants": [{"m": 1}], "results": [True],
            "reproduction": {"mode": "reproduce"}}
    root = replay_evidence(**base)["evidence_root"]
    assert replay_evidence(**{**base, "envelope_digest": "sha256:f"})["evidence_root"] != root
    assert replay_evidence(**{**base, "results": [False]})["evidence_root"] != root
    assert replay_evidence(**{**base, "reproduction": {"mode": "learn"}})["evidence_root"] != root


def test_unstructured_or_unbound_replay_is_not_structured():
    loose = HeldOutReplayGate().evaluate("c", ["a", "b", "c"], lambda _: True, envelope_digest="sha256:e")
    assert loose.structured is False and loose.evidence_root.startswith("sha256:")
    unbound = HeldOutReplayGate().evaluate("c", [{"m": 1}, {"m": 2}, {"m": 3}], lambda _: True)
    assert unbound.structured is False  # no episode envelope bound
    assert asdict(unbound)["evidence_root"]
