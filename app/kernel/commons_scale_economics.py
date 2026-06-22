"""Scale economics for BEAST Commons proof density.

This module answers the question:

    When do many locally reproduced Spaces become economically meaningful?

It intentionally separates observed local proof from configurable financial
assumptions. No pricing claim is hard-coded as truth.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ARTIFACT_TIERS: Dict[str, Dict[str, Any]] = {
    "tier_1_tiny_replay": {
        "label": "Tier 1: Tiny Replay",
        "base_value_usd": 0.01,
        "proof_depth_cap": 1.0,
        "requirements": ["deterministic_execution", "narrow_boundary", "one_off_reproduction"],
    },
    "tier_2_skill_meta_tool": {
        "label": "Tier 2: Skill / Meta-Tool",
        "base_value_usd": 0.015,
        "proof_depth_cap": 1.5,
        "requirements": ["valid_manifest", "local_reproduction", "verifier_bundle", "privacy_clean"],
    },
    "tier_3_fused_crystal": {
        "label": "Tier 3: Fused Crystal",
        "base_value_usd": 0.02,
        "proof_depth_cap": 2.5,
        "requirements": ["tier_2", "multiple_artifact_types", "cross_component_evidence", "rollback_tested", "live_reproduction"],
    },
    "tier_4_promotion_candidate": {
        "label": "Tier 4: Promotion Candidate",
        "base_value_usd": 0.03,
        "proof_depth_cap": 3.5,
        "requirements": ["tier_3", "durability_or_cross_machine_or_reputation", "durable_storage", "post_quantum_seal"],
    },
}


@dataclass(frozen=True)
class ScaleEconomicsAssumptions:
    target_spaces: int = 10
    matches_per_space: int = 3
    tokens_per_match: int = 3900
    cloud_call_cost_usd: float = 0.0
    token_cost_per_1m_usd: float = 0.0
    local_verifier_cost_usd: float = 0.0
    setup_cost_usd: float = 0.0
    marketplace_take_rate: float = 0.0
    value_tier: str = "base_space"
    tier_value_multiplier: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_spaces": self.target_spaces,
            "matches_per_space": self.matches_per_space,
            "tokens_per_match": self.tokens_per_match,
            "cloud_call_cost_usd": self.cloud_call_cost_usd,
            "token_cost_per_1m_usd": self.token_cost_per_1m_usd,
            "local_verifier_cost_usd": self.local_verifier_cost_usd,
            "setup_cost_usd": self.setup_cost_usd,
            "marketplace_take_rate": self.marketplace_take_rate,
            "value_tier": self.value_tier,
            "tier_value_multiplier": self.tier_value_multiplier,
        }


class CommonsScaleEconomics:
    """Compute proof-density and configurable economics ladders."""

    def __init__(self, registry: Any, economy: Any, result_root: Optional[Path] = None):
        project_root = Path(__file__).resolve().parents[2]
        self.registry = registry
        self.economy = economy
        self.result_root = (result_root or project_root / "benchmarks" / "results").resolve()

    def report(self, assumptions: ScaleEconomicsAssumptions = ScaleEconomicsAssumptions()) -> Dict[str, Any]:
        density = self.proof_density()
        ladder = self.scale_ladder(assumptions)
        marketplace = self.marketplace_readiness(density, ladder)
        tiered = self.tiered_credit_pricing(density)
        return {
            "beast_object_type": "commons_scale_economics_report",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "proof_density": density,
            "scale_ladder": ladder,
            "tiered_credit_pricing": tiered,
            "marketplace_readiness": marketplace,
            "claim_boundary": (
                "Observed proof counts are local evidence. Financial projections are scenario math "
                "from caller-provided assumptions, not promises or market prices."
            ),
        }

    def proof_density(self) -> Dict[str, Any]:
        registry = self.registry.list_spaces()
        spaces = [item for item in registry.get("spaces") or [] if item.get("valid")]
        proofs = []
        for item in spaces:
            space_id = str(item.get("space_id") or "")
            try:
                proof = self.economy.proof(space_id)
            except Exception as exc:  # pragma: no cover - defensive around corrupt local state
                proof = {"space_id": space_id, "eligible": False, "error": str(exc)}
            proofs.append(proof)
        workload = self._workload_receipts()
        matches_by_space: Dict[str, int] = defaultdict(int)
        avoided_by_space: Dict[str, int] = defaultdict(int)
        for receipt in workload:
            space_id = str(receipt.get("space_id") or "")
            observed = receipt.get("observed") if isinstance(receipt.get("observed"), dict) else {}
            matches_by_space[space_id] += int(observed.get("repeated_matches") or 0)
            avoided_by_space[space_id] += int(observed.get("cloud_api_calls_avoided") or 0)
        live_reproduction_spaces = []
        for item in spaces:
            detail = self.registry.get(str(item["space_id"]))
            if any(row.get("mode") == "live_verifier" and row.get("live_verifier_passed") is True for row in detail.get("reproductions") or []):
                live_reproduction_spaces.append(str(item["space_id"]))
        eligible_spaces = [proof["space_id"] for proof in proofs if proof.get("eligible")]
        credited_spaces = {
            str(credit.get("space_id") or "")
            for credit in (self.economy.state().get("credits") or [])
            if credit.get("beast_object_type") == "non_financial_compute_reduction_credit"
        }
        return {
            "beast_object_type": "commons_proof_density",
            "version": "1.0",
            "spaces": {
                "valid": len(spaces),
                "live_reproduced": len(live_reproduction_spaces),
                "eligible_for_credit": len(eligible_spaces),
                "credited": len(credited_spaces),
            },
            "workload": {
                "receipt_count": len(workload),
                "matched_spaces": len([space for space, count in matches_by_space.items() if count > 0]),
                "total_repeated_matches": sum(matches_by_space.values()),
                "total_cloud_calls_avoided": sum(avoided_by_space.values()),
                "matches_by_space": dict(sorted(matches_by_space.items())),
                "cloud_calls_avoided_by_space": dict(sorted(avoided_by_space.items())),
            },
            "tier_inventory": self._tier_inventory(),
            "proof_sets": {
                "live_reproduced_space_ids": sorted(live_reproduction_spaces),
                "eligible_space_ids": sorted(eligible_spaces),
                "credited_space_ids": sorted(credited_spaces),
            },
            "proof_gap_to_10x3": {
                "spaces_needed": max(0, 10 - len([space for space, count in matches_by_space.items() if count >= 3])),
                "matches_needed": max(0, 30 - sum(matches_by_space.values())),
            },
        }

    def tiered_credit_pricing(self, density: Dict[str, Any]) -> Dict[str, Any]:
        """Price observed Spaces using proof-based capped multipliers."""
        matches_by_space = ((density.get("workload") or {}).get("matches_by_space") or {})
        priced = []
        for row in self.registry.list_spaces().get("spaces") or []:
            if not row.get("valid"):
                continue
            space_id = str(row.get("space_id") or "")
            try:
                detail = self.registry.get(space_id)
            except Exception:
                continue
            matches = int(matches_by_space.get(space_id) or 0)
            priced.append(self.price_space(detail, matches=matches))
        portfolio = self.tiered_10_space_portfolio()
        return {
            "beast_object_type": "tiered_credit_pricing_report",
            "version": "1.0",
            "artifact_tiers": ARTIFACT_TIERS,
            "pricing_formula": (
                "base_value * proof_depth_multiplier * fusion_complexity_multiplier * "
                "match_frequency_multiplier * anti_gaming_multiplier, capped to 0.5x..3.0x total premium"
            ),
            "observed_spaces": priced,
            "observed_total_credit_value_usd": round(sum(float(item.get("total_credit_value_usd") or 0.0) for item in priced), 6),
            "tiered_10_space_portfolio_example": portfolio,
            "demotion_and_decay": {
                "false_suppression_event": "drop all multipliers by one tier",
                "repository_drift": "proof depth drops to live-reproduced level until revalidated",
                "match_frequency_decay": "frequency multiplier decreases when recent frequency drops by 50%",
                "reputation_decay": "anti-gaming decreases 0.25x per 30 days without matches, floor 1.0x",
            },
            "anti_inflation_rules": {
                "per_artifact_monthly_cap": "base_value * 3.0 * highest_monthly_frequency",
                "aggregate_marketplace_cap": "total credits capped at 10x marketplace operational cost until self-sustaining",
                "sybil_defense": "node earnings capped by node_reputation_score * historical_match_accuracy * max_per_node",
            },
        }

    def price_space(self, detail: Dict[str, Any], *, matches: int, duration_days: int = 0) -> Dict[str, Any]:
        manifest = detail.get("manifest") or {}
        receipt = detail.get("reduction_receipt") or {}
        reproductions = detail.get("reproductions") or []
        artifact_types = {str(item.get("artifact_type") or "") for item in manifest.get("artifacts") or []}
        live = any(item.get("mode") == "live_verifier" and item.get("live_verifier_passed") is True for item in reproductions)
        deterministic = any(item.get("reproduced") for item in reproductions)
        verifier_bundles = manifest.get("verifier_bundles") or []
        privacy = manifest.get("privacy") or {}
        has_rollback = bool(receipt.get("rollback_available") or "rollback_receipt" in artifact_types)
        has_pq = self._has_post_quantum_seal(detail)
        tier = self._classify_tier(
            artifact_types=artifact_types,
            live=live,
            deterministic=deterministic,
            verifier_present=bool(verifier_bundles),
            privacy_clean=privacy.get("contains_secrets") is False,
            has_rollback=has_rollback,
            has_pq=has_pq,
            matches=matches,
            duration_days=duration_days,
        )
        tier_meta = ARTIFACT_TIERS[tier]
        component_count = self._component_count(artifact_types, verifier_present=bool(verifier_bundles), has_rollback=has_rollback)
        proof = self._proof_depth_multiplier(
            tier,
            matches=matches,
            duration_days=duration_days,
            live=live,
            cross_machine=False,
            reputation_established=False,
        )
        fusion = min(3.0, 1.0 + 0.3 * max(0, component_count))
        frequency = min(2.5, 1.0 + 0.03 * max(0, matches))
        anti = self._anti_gaming_multiplier(
            manifest_signed=bool(manifest.get("manifest_hash")),
            local_approval=bool(detail.get("adoptions")),
            live_reproduction=live,
            deterministic_bundle=deterministic,
            cross_node_reputation=False,
            durable_storage=False,
            post_quantum_approval=has_pq and bool(detail.get("adoptions")),
        )
        raw_multiplier = proof * fusion * frequency * anti
        capped_multiplier = max(0.5, min(3.0, raw_multiplier))
        per_displacement = round(float(tier_meta["base_value_usd"]) * capped_multiplier, 6)
        return {
            "beast_object_type": "tiered_space_credit_pricing",
            "version": "1.0",
            "space_id": manifest.get("space_id"),
            "tier": tier,
            "tier_label": tier_meta["label"],
            "base_value_usd": tier_meta["base_value_usd"],
            "matches": matches,
            "duration_days": duration_days,
            "component_count": component_count,
            "multipliers": {
                "proof_depth": proof,
                "fusion_complexity": round(fusion, 6),
                "match_frequency": round(frequency, 6),
                "anti_gaming_strength": anti,
                "raw_total": round(raw_multiplier, 6),
                "capped_total": round(capped_multiplier, 6),
            },
            "per_displacement_value_usd": per_displacement,
            "total_credit_value_usd": round(per_displacement * max(0, matches), 6),
            "cap_reason": "max_premium_3x_applied" if raw_multiplier > 3.0 else "within_cap",
            "claim_boundary": "Pricing is proof-based scenario accounting, not a redeemable financial instrument.",
        }

    def scale_ladder(self, assumptions: ScaleEconomicsAssumptions) -> Dict[str, Any]:
        scenarios = [
            ("observed_minimum", assumptions.target_spaces, assumptions.matches_per_space),
            ("first_market_signal", 10, 3),
            ("team_level_repeatability", 100, 10),
            ("marketplace_candidate", 1000, 25),
            ("infrastructure_grade", 10000, 100),
        ]
        rows = [self._scenario(label, spaces, matches, assumptions) for label, spaces, matches in scenarios]
        primary = rows[0]
        return {
            "beast_object_type": "commons_scale_ladder",
            "version": "1.0",
            "assumptions": assumptions.to_dict(),
            "primary_question": {
                "spaces": assumptions.target_spaces,
                "matches_per_space": assumptions.matches_per_space,
                "total_displacements": assumptions.target_spaces * assumptions.matches_per_space,
                "answer": self._interpret(primary),
            },
            "scenarios": rows,
            "pricing_boundary": (
                "Use --cloud-call-cost, --token-cost-per-1m, --local-verifier-cost, and --setup-cost "
                "to test pricing assumptions. Use --value-tier and --tier-value-multiplier to model "
                "fused crystals/meta-tools/skill trees separately from base Spaces. Defaults are zero "
                "or 1.0 to avoid fake market claims."
            ),
            "tier_defaults": {
                "base_space": 1.0,
                "forge_crystal": 1.5,
                "meta_tool": 1.8,
                "skill_tree": 2.2,
                "fused_inference_crystal": 3.0,
            },
        }

    def marketplace_readiness(self, density: Dict[str, Any], ladder: Dict[str, Any]) -> Dict[str, Any]:
        workload = density.get("workload") or {}
        spaces = density.get("spaces") or {}
        total_matches = int(workload.get("total_repeated_matches") or 0)
        matched_spaces = int(workload.get("matched_spaces") or 0)
        credited = int(spaces.get("credited") or 0)
        gates = [
            {
                "gate": "public_marketplace",
                "status": "not_ready" if matched_spaces < 10 else "candidate",
                "requires": "at least 10 Spaces with repeated local proof before public listing claims",
            },
            {
                "gate": "large_scale_anti_gaming",
                "status": "minimum_local_controls_present",
                "requires": "duplicate suppression, one credit per evidence fingerprint, mutation/ablation oracles, contributor reputation",
            },
            {
                "gate": "cross_machine_repeated_adoption",
                "status": "not_proven",
                "requires": "same Space adopted and live-reproduced across multiple machines/OS/Ollama versions",
            },
            {
                "gate": "long_term_credit_value",
                "status": "not_ready" if credited < 10 else "candidate",
                "requires": "credits retain predictive value after expiry, demotion, and workload drift",
            },
            {
                "gate": "production_workload_frequency",
                "status": "not_ready" if total_matches < 30 else "first_signal",
                "requires": "real production task-boundary match rate, not synthetic repetition",
            },
            {
                "gate": "financial_pricing",
                "status": "scenario_only",
                "requires": "observed willingness-to-pay, cost baseline, legal review, abuse controls, tax/accounting treatment",
            },
        ]
        counts = Counter(item["status"] for item in gates)
        return {
            "beast_object_type": "commons_marketplace_readiness",
            "version": "1.0",
            "status_counts": dict(sorted(counts.items())),
            "gates": gates,
            "next_required_experiment": "reach_10_spaces_with_3_live_repeated_matches_each",
            "public_claim_allowed_now": False,
            "tiered_marketplace_requirements": {
                "tier_3_credits": [
                    "valid_manifest",
                    "live_reproduction",
                    "multiple_artifact_types",
                    "verifier_bundle",
                    "3_plus_successful_workload_matches",
                    "zero_false_suppressions",
                    "privacy_scan_clean",
                ],
                "tier_4_credits": [
                    "all_tier_3_requirements",
                    "10_plus_matches_or_30_days_clean",
                    "cross_machine_validation_or_reputation_0_85_plus",
                    "durable_storage_validated",
                    "post_quantum_seal_verified",
                    "no_demotion_events_in_60_days",
                ],
                "public_marketplace": [
                    "10_plus_spaces_with_tier_3_eligibility",
                    "3_plus_spaces_with_tier_4_status",
                    "zero_false_suppression_incidents",
                    "cross_node_reputation_validated",
                    "sybil_defense_tested_active",
                    "credit_cap_enforcement_operational",
                ],
            },
        }

    def _workload_receipts(self) -> List[Dict[str, Any]]:
        rows = []
        if not self.result_root.exists():
            return rows
        for path in sorted(self.result_root.glob("*live_commons_displacement*harness*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("beast_object_type") == "live_commons_displacement_harness_receipt":
                rows.append(payload)
        return rows

    def _tier_inventory(self) -> Dict[str, Any]:
        try:
            candidates = self.registry.registration_candidates(limit=500).get("candidates") or []
        except Exception:
            candidates = []
        kinds = Counter(str(item.get("candidate_kind") or "unknown") for item in candidates if isinstance(item, dict))
        forge = [item for item in candidates if isinstance(item, dict) and str(item.get("source") or "") == "compute_forge"]
        return {
            "beast_object_type": "commons_tier_inventory",
            "version": "1.0",
            "candidate_kinds": dict(sorted(kinds.items())),
            "forge_candidates": len(forge),
            "tier_policy": {
                "base_space": "single verified Space boundary",
                "forge_crystal": "model-agnostic reusable contract",
                "meta_tool": "tool-selection or tool-binding capability",
                "skill_tree": "reusable skill/pattern memory",
                "fused_inference_crystal": "compound crystal combining crystals/meta-tools/skills/swarm recipes",
            },
        }

    @staticmethod
    def _classify_tier(
        *,
        artifact_types: set[str],
        live: bool,
        deterministic: bool,
        verifier_present: bool,
        privacy_clean: bool,
        has_rollback: bool,
        has_pq: bool,
        matches: int,
        duration_days: int,
    ) -> str:
        multiple_artifacts = len([item for item in artifact_types if item]) >= 4
        if (
            live
            and multiple_artifacts
            and verifier_present
            and privacy_clean
            and has_rollback
            and has_pq
            and (matches >= 10 or duration_days >= 30)
        ):
            return "tier_4_promotion_candidate"
        if live and multiple_artifacts and verifier_present and privacy_clean and has_rollback:
            return "tier_3_fused_crystal"
        if deterministic and verifier_present and privacy_clean:
            return "tier_2_skill_meta_tool"
        return "tier_1_tiny_replay"

    @staticmethod
    def _component_count(artifact_types: set[str], *, verifier_present: bool, has_rollback: bool) -> int:
        components = 0
        if artifact_types:
            components += 1
        if any("skill" in item or "promotion" in item for item in artifact_types):
            components += 1
        if any("route" in item or "orchestration" in item or "plan" in item for item in artifact_types):
            components += 1
        if verifier_present or any("verifier" in item for item in artifact_types):
            components += 1
        if has_rollback:
            components += 1
        if any("approval" in item or "policy" in item for item in artifact_types):
            components += 1
        return max(1, components)

    @staticmethod
    def _proof_depth_multiplier(
        tier: str,
        *,
        matches: int,
        duration_days: int,
        live: bool,
        cross_machine: bool,
        reputation_established: bool,
    ) -> float:
        if reputation_established and duration_days >= 60:
            value = 3.5
        elif cross_machine and matches >= 5:
            value = 3.0
        elif matches >= 10 and duration_days >= 30:
            value = 2.5
        elif matches >= 3:
            value = 2.0
        elif live:
            value = 1.5
        else:
            value = 1.0
        return round(min(float(ARTIFACT_TIERS[tier]["proof_depth_cap"]), value), 6)

    @staticmethod
    def _anti_gaming_multiplier(
        *,
        manifest_signed: bool,
        local_approval: bool,
        live_reproduction: bool,
        deterministic_bundle: bool,
        cross_node_reputation: bool,
        durable_storage: bool,
        post_quantum_approval: bool,
    ) -> float:
        score = 1.0
        if manifest_signed:
            score += 0.2
        if local_approval:
            score += 0.2
        if live_reproduction:
            score += 0.5
        if deterministic_bundle:
            score += 0.55
        if cross_node_reputation:
            score += 1.0
        if durable_storage:
            score += 1.5
        if post_quantum_approval:
            score += 1.0
        return round(min(3.0, score), 6)

    @staticmethod
    def _has_post_quantum_seal(detail: Dict[str, Any]) -> bool:
        payloads = []
        if detail.get("reduction_receipt"):
            payloads.append(detail["reduction_receipt"])
        payloads.extend(detail.get("adoptions") or [])
        payloads.extend(detail.get("reproductions") or [])
        for payload in payloads:
            seal = payload.get("local_seal") if isinstance(payload, dict) else None
            profile = seal.get("crypto_profile") if isinstance(seal, dict) else None
            if isinstance(profile, dict) and str(profile.get("signature") or "").upper().startswith("ML-DSA"):
                return True
        return False

    @staticmethod
    def tiered_10_space_portfolio() -> Dict[str, Any]:
        """Return the spec's 10-Space tiered scenario."""
        rows = [
            {
                "label": "tier_2_rare_skill",
                "tier": "tier_2_skill_meta_tool",
                "spaces": 3,
                "matches_per_space": 1,
                "proof_depth": 1.5,
                "fusion_complexity": 1.2,
                "match_frequency": 1.0,
                "anti_gaming_strength": 1.5,
            },
            {
                "label": "tier_3_early_fused",
                "tier": "tier_3_fused_crystal",
                "spaces": 4,
                "matches_per_space": 3,
                "proof_depth": 2.0,
                "fusion_complexity": 2.5,
                "match_frequency": 1.3,
                "anti_gaming_strength": 2.5,
            },
            {
                "label": "tier_4_proven_high_frequency",
                "tier": "tier_4_promotion_candidate",
                "spaces": 2,
                "matches_per_space": 10,
                "proof_depth": 3.5,
                "fusion_complexity": 3.0,
                "match_frequency": 2.5,
                "anti_gaming_strength": 3.0,
            },
            {
                "label": "tier_3_launch_space",
                "tier": "tier_3_fused_crystal",
                "spaces": 1,
                "matches_per_space": 3,
                "proof_depth": 2.0,
                "fusion_complexity": 2.5,
                "match_frequency": 1.3,
                "anti_gaming_strength": 2.5,
            },
        ]
        total = 0.0
        total_displacements = 0
        priced = []
        for row in rows:
            tier = ARTIFACT_TIERS[row["tier"]]
            displacements = int(row["spaces"]) * int(row["matches_per_space"])
            raw_multiplier = (
                float(row["proof_depth"])
                * float(row["fusion_complexity"])
                * float(row["match_frequency"])
                * float(row["anti_gaming_strength"])
            )
            capped = max(0.5, min(3.0, raw_multiplier))
            per_displacement = round(float(tier["base_value_usd"]) * capped, 6)
            value = round(per_displacement * displacements, 6)
            total += value
            total_displacements += displacements
            priced.append({
                **row,
                "displacements": displacements,
                "base_value_usd": tier["base_value_usd"],
                "raw_multiplier": round(raw_multiplier, 6),
                "capped_multiplier": round(capped, 6),
                "per_displacement_value_usd": per_displacement,
                "credit_value_usd": value,
            })
        flat = total_displacements * 0.02
        return {
            "beast_object_type": "tiered_10_space_portfolio",
            "version": "1.0",
            "spaces": 10,
            "displacements": total_displacements,
            "rows": priced,
            "tiered_credit_value_usd": round(total, 6),
            "flat_credit_value_usd": round(flat, 6),
            "tiered_vs_flat_multiplier": round(total / flat, 6) if flat else None,
            "marketplace_take_10pct_usd": round(total * 0.10, 6),
            "source_spec_note": (
                "The provided scenario text lists an additional Tier 3 launch Space but its written "
                "subtotal omits that Space. This implementation includes all listed rows."
            ),
        }

    @staticmethod
    def _scenario(label: str, spaces: int, matches_per_space: int, assumptions: ScaleEconomicsAssumptions) -> Dict[str, Any]:
        displacements = max(0, int(spaces)) * max(0, int(matches_per_space))
        multiplier = max(0.0, float(assumptions.tier_value_multiplier or 1.0))
        effective_tokens_per_match = int(round(max(0, int(assumptions.tokens_per_match)) * multiplier))
        effective_cloud_call_cost = max(0.0, float(assumptions.cloud_call_cost_usd)) * multiplier
        tokens = displacements * effective_tokens_per_match
        gross = (
            displacements * effective_cloud_call_cost
            + (tokens / 1_000_000.0) * max(0.0, float(assumptions.token_cost_per_1m_usd))
        )
        local_verifier = displacements * max(0.0, float(assumptions.local_verifier_cost_usd))
        net = gross - local_verifier
        marketplace_revenue = max(0.0, net) * max(0.0, min(float(assumptions.marketplace_take_rate), 1.0))
        denominator = max(0.000001, gross / max(1, displacements))
        break_even_displacements = math.ceil(max(0.0, assumptions.setup_cost_usd) / denominator) if assumptions.setup_cost_usd > 0 and gross > 0 else None
        return {
            "label": label,
            "spaces": spaces,
            "matches_per_space": matches_per_space,
            "value_tier": assumptions.value_tier,
            "tier_value_multiplier": multiplier,
            "displacements": displacements,
            "effective_tokens_per_match": effective_tokens_per_match,
            "effective_cloud_call_cost_usd": round(effective_cloud_call_cost, 6),
            "tokens_avoided_estimate": tokens,
            "gross_avoided_cost_usd": round(gross, 6),
            "local_verifier_cost_usd": round(local_verifier, 6),
            "net_avoided_cost_usd": round(net, 6),
            "marketplace_revenue_at_take_rate_usd": round(marketplace_revenue, 6),
            "break_even_displacements_for_setup_cost": break_even_displacements,
        }

    @staticmethod
    def _interpret(row: Dict[str, Any]) -> str:
        displacements = int(row.get("displacements") or 0)
        net = float(row.get("net_avoided_cost_usd") or 0.0)
        if displacements < 30:
            return "below_first_market_signal"
        if net <= 0:
            return "proof_signal_not_financial_signal_under_current_assumptions"
        if displacements >= 30 and net > 0:
            return "first_economic_signal_under_current_assumptions"
        return "inconclusive"
