"""Staleness and quarantine policy for crystallized compute reuse."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class CrystalRuntimeContext:
    repo_fingerprint: str = ""
    test_fingerprint: str = ""
    tool_contract_hash: str = ""
    skill_tree_hash: str = ""
    lattice_hash: str = ""
    risk_tier: str = ""
    approval_present: bool = False


@dataclass(frozen=True)
class CrystalReusePolicySnapshot:
    repo_fingerprint: str = ""
    test_fingerprint: str = ""
    tool_contract_hash: str = ""
    skill_tree_hash: str = ""
    lattice_hash: str = ""
    risk_tier: str = ""


class CrystalStalenessPolicy:
    """Evaluate whether a crystal can be reused under current local facts."""

    def evaluate(self, expected: CrystalReusePolicySnapshot, actual: CrystalRuntimeContext) -> Dict[str, Any]:
        failures: List[Dict[str, Any]] = []
        self._check(failures, "repo_fingerprint", expected.repo_fingerprint, actual.repo_fingerprint)
        self._check(failures, "test_fingerprint", expected.test_fingerprint, actual.test_fingerprint)
        self._check(failures, "tool_contract_hash", expected.tool_contract_hash, actual.tool_contract_hash)
        self._check(failures, "skill_tree_hash", expected.skill_tree_hash, actual.skill_tree_hash)
        self._check(failures, "lattice_hash", expected.lattice_hash, actual.lattice_hash)
        if expected.risk_tier and actual.risk_tier and expected.risk_tier != actual.risk_tier and not actual.approval_present:
            failures.append({
                "field": "risk_tier",
                "expected": expected.risk_tier,
                "actual": actual.risk_tier,
                "reason": "risk_tier_changed_without_approval",
            })
        return {
            "beast_object_type": "crystal_staleness_policy_result",
            "version": "1.0",
            "reuse_allowed": not failures,
            "quarantine_required": bool(failures),
            "failures": failures,
            "failure_count": len(failures),
        }

    @staticmethod
    def _check(failures: List[Dict[str, Any]], field: str, expected: str, actual: str) -> None:
        if expected and actual and expected != actual:
            failures.append({
                "field": field,
                "expected": expected,
                "actual": actual,
                "reason": f"{field}_mismatch",
            })
