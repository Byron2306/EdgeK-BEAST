"""Phase 7 coding-agent reuse authority plane.

Crystals may reduce inference and propose strategy. They do not inherit source,
mutation, verification, or promotion authority from a previous successful run.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice


PROHIBITED_AUTHORITY = {
    "exact_source": "workspace.read_range_only",
    "mutation": "worktree_tools_only",
    "verification": "fresh_verifier_receipt_required",
    "promotion": "fresh_governed_promotion_required",
}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AgentReuseRuntime:
    def __init__(self, workspace_root: Any):
        self.lattice = MissionCrystalLattice(workspace_root)

    @staticmethod
    def _plan_from_run(run: dict[str, Any], state: Any) -> dict[str, Any]:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        return {
            "plan_id": str(run.get("run_id") or getattr(state, "run_id", "") or ""),
            "objective": str(run.get("objective") or request.get("prompt") or ""),
            "provider": str(run.get("provider") or ""),
            "risk_level": str(request.get("risk_level") or "unknown"),
            "operations": [],
            "selected_operations": [],
        }

    def propose(self, run: dict[str, Any], state: Any, *, limit: int = 3) -> dict[str, Any]:
        plan = self._plan_from_run(run, state)
        lookup = self.lattice.lookup(plan, scorecard={}, limit=limit)
        best = lookup.get("best_match") if isinstance(lookup.get("best_match"), dict) else {}
        blockers = list(lookup.get("blockers") or [])
        score = float(lookup.get("match_strength") or 0.0)

        if score >= 0.88 and not blockers and best.get("verification_ok"):
            allowed_use = "strategy_and_replay_candidate"
        elif score >= 0.55:
            allowed_use = "strategy_scaffold"
        elif score > 0:
            allowed_use = "context_hint_only"
        else:
            allowed_use = "none"

        packet = {
            "beast_object_type": "beast_agent_reuse_proposal",
            "version": "1.0",
            "run_id": plan["plan_id"],
            "allowed_use": allowed_use,
            "match_strength": round(score, 4),
            "lattice": lookup,
            "compute_savings": {
                "may_reduce_planner_inference": allowed_use != "none",
                "may_reuse_verified_strategy": allowed_use in {"strategy_scaffold", "strategy_and_replay_candidate"},
                "may_skip_fresh_source_read": False,
                "may_skip_fresh_verification": False,
            },
            "authority": {
                "advisory_only": True,
                "grants_exact_source_authority": False,
                "grants_mutation_authority": False,
                "grants_verification_authority": False,
                "grants_promotion_authority": False,
                "required_fresh_authority": PROHIBITED_AUTHORITY,
            },
            "staleness_or_compatibility_blockers": blockers,
        }
        packet["proposal_digest"] = _digest(packet)
        return packet

    def record_verified_outcome(self, run: dict[str, Any], state: Any, observation: dict[str, Any]) -> dict[str, Any]:
        """Promote only a freshly verified coding mission into the lattice."""
        evidence_hash = str(observation.get("evidence_digest") or "")
        packet = {
            "plan_id": str(run.get("run_id") or getattr(state, "run_id", "") or ""),
            "objective": str(run.get("objective") or ""),
            "provider": str(run.get("provider") or ""),
            "operations": [],
            "applied_files": [],
            "evidence_hash": evidence_hash,
            "verification": {"ok": True, "fresh": True, "evidence_digest": evidence_hash},
            "promotion_candidate": bool(evidence_hash),
        }
        return self.lattice.record_from_packet(packet)

    def feedback(self, run: dict[str, Any], state: Any, observation: dict[str, Any]) -> dict[str, Any]:
        """Close the reuse loop without allowing failure history to become authority."""
        status = str(observation.get("status") or "")
        result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
        returncode = result.get("returncode")
        passed = status == "completed" and returncode in (None, 0)
        if passed:
            recorded = self.record_verified_outcome(run, state, observation)
            return {
                "beast_object_type": "beast_agent_reuse_feedback",
                "version": "1.0",
                "outcome": "fresh_verification_strengthened_lattice",
                "recorded": recorded,
                "authority_escalated": False,
            }
        proposal = self.propose(run, state, limit=3)
        return {
            "beast_object_type": "beast_agent_reuse_feedback",
            "version": "1.0",
            "outcome": "verification_failure_blocks_promotion",
            "proposal_digest": proposal.get("proposal_digest"),
            "blockers": ["fresh_verification_failed"],
            "authority_escalated": False,
            "promotion_written": False,
        }


def render_reuse_proposal(packet: dict[str, Any], *, char_limit: int = 1400) -> str:
    compact = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
    limit = max(650, int(char_limit))
    if len(compact) <= limit:
        return "\nCRYSTAL_REUSE:" + compact
    minimal = {
        "beast_object_type": packet.get("beast_object_type"),
        "version": packet.get("version"),
        "run_id": packet.get("run_id"),
        "allowed_use": packet.get("allowed_use"),
        "match_strength": packet.get("match_strength"),
        "compute_savings": packet.get("compute_savings"),
        "authority": packet.get("authority"),
        "staleness_or_compatibility_blockers": packet.get("staleness_or_compatibility_blockers"),
        "proposal_digest": packet.get("proposal_digest"),
        "compacted": True,
        "authority_preserved": True,
    }
    return "\nCRYSTAL_REUSE:" + json.dumps(minimal, sort_keys=True, default=str, separators=(",", ":"))[:limit]
