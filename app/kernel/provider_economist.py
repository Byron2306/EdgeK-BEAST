"""Economic provider routing by role, quality, cost, latency, and route trust."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


INVALID_ROLES = {
    "route_invalid",
    "infra_invalid",
    "do_not_use_until_auth_fixed",
    "do_not_use_until_billing_fixed",
    "route_degraded_exclude_cost_rank",
}


@dataclass(frozen=True)
class EconomistPolicy:
    requested_role: str = "primary_patch_provider"
    task_class: str = "general"
    max_latency_ms: Optional[float] = None
    max_usd_per_fix: Optional[float] = None
    min_auth_confidence: float = 0.6
    require_cost_observation: bool = False
    prefer_hidden_clean: bool = True
    friction_mode: str = "shadow"  # off | shadow | enforce


class ProviderEconomist:
    """Rank provider routes for a concrete runtime role and cost envelope."""

    def select(
        self,
        candidates: Iterable[Dict[str, Any]],
        policy: EconomistPolicy,
        negative_capabilities: Iterable[Dict[str, Any]] = (),
        friction_profiles: Iterable[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        ranked: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        normalized = [self._normalize(item) for item in candidates if isinstance(item, dict)]
        latency_values = [item["latency_ms"] for item in normalized if item["latency_ms"] is not None]
        max_observed_latency = max(latency_values, default=1.0)
        economics_key = "hidden_clean_per_usd" if policy.prefer_hidden_clean else "verified_fixes_per_usd"
        economics_values = [item[economics_key] for item in normalized if item[economics_key]]
        max_economics = max(economics_values, default=1.0)

        negatives = [item for item in negative_capabilities if isinstance(item, dict)]
        friction = [item for item in friction_profiles if isinstance(item, dict)]
        for item in normalized:
            reasons = self._exclusion_reasons(item, policy)
            reasons.extend(self._negative_exclusion_reasons(item, policy, negatives))
            if reasons:
                excluded.append({**item, "exclusion_reasons": reasons})
                continue
            role_score = self._role_score(policy.requested_role, item["recommended_role"])
            economics_score = min(1.0, (item[economics_key] or 0.0) / max_economics)
            if not item["cost_observed"]:
                economics_score = 0.35 if not policy.require_cost_observation else 0.0
            if policy.prefer_hidden_clean:
                economics_score = (0.75 * economics_score) + (0.25 * item["hidden_clean_rate"])
            latency_score = 1.0 - min(1.0, (item["latency_ms"] or max_observed_latency) / max_observed_latency)
            rescue_score = self._rescue_fit(policy.requested_role, item["rescue_rate"])
            score = (
                0.30 * role_score
                + 0.30 * economics_score
                + 0.20 * item["auth_confidence"]
                + 0.10 * latency_score
                + 0.10 * rescue_score
            )
            friction_profile = self._matching_friction(item, policy, friction)
            friction_score = float((friction_profile or {}).get("friction_score") or 0.0)
            friction_confidence = float((friction_profile or {}).get("confidence") or 0.0)
            shadow_score = score * (1.0 - (0.35 * friction_score * friction_confidence))
            effective_score = shadow_score if policy.friction_mode == "enforce" else score
            ranked.append({
                **item,
                "economist_score": round(effective_score, 6),
                "base_economist_score": round(score, 6),
                "friction_shadow_score": round(shadow_score, 6),
                "friction_score": round(friction_score, 6),
                "friction_confidence": round(friction_confidence, 6),
                "friction_profile_id": (friction_profile or {}).get("profile_id"),
                "score_components": {
                    "role_fit": round(role_score, 4),
                    "hidden_clean_economics": round(economics_score, 4),
                    "auth_confidence": round(item["auth_confidence"], 4),
                    "latency": round(latency_score, 4),
                    "rescue_fit": round(rescue_score, 4),
                    "friction_penalty_shadow": round(score - shadow_score, 4),
                },
            })
        base_ranked = sorted(
            ranked,
            key=lambda item: (item["base_economist_score"], item[economics_key] or 0.0),
            reverse=True,
        )
        friction_ranked = sorted(
            ranked,
            key=lambda item: (item["friction_shadow_score"], item[economics_key] or 0.0),
            reverse=True,
        )
        ranked.sort(key=lambda item: (item["economist_score"], item[economics_key] or 0.0), reverse=True)
        selected = ranked[0] if ranked else None
        base_selected = base_ranked[0] if base_ranked else None
        friction_selected = friction_ranked[0] if friction_ranked else None
        selection_would_change = bool(
            base_selected and friction_selected
            and base_selected.get("provider") != friction_selected.get("provider")
        )
        return {
            "beast_object_type": "provider_economist_decision",
            "version": "1.0",
            "requested_role": policy.requested_role,
            "policy": {
                "max_latency_ms": policy.max_latency_ms,
                "max_usd_per_fix": policy.max_usd_per_fix,
                "min_auth_confidence": policy.min_auth_confidence,
                "require_cost_observation": policy.require_cost_observation,
                "prefer_hidden_clean": policy.prefer_hidden_clean,
                "task_class": policy.task_class,
                "friction_mode": policy.friction_mode,
            },
            "selected": selected,
            "ranked": ranked,
            "excluded": excluded,
            "decision": "route_selected" if selected else "no_eligible_route",
            "reason": self._selection_reason(selected, policy),
            "phase2_friction": {
                "mode": policy.friction_mode,
                "profiles_considered": len(friction),
                "base_selected_provider": (base_selected or {}).get("provider"),
                "friction_selected_provider": (friction_selected or {}).get("provider"),
                "selection_would_change": selection_would_change,
                "selection_changed": bool(
                    policy.friction_mode == "enforce"
                    and base_selected and selected
                    and base_selected.get("provider") != selected.get("provider")
                ),
            },
            "counterfactual_crystals": self._counterfactual_crystals(
                selected=selected,
                ranked=ranked,
                excluded=excluded,
                policy=policy,
            ),
        }

    def _normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        provider = str(raw.get("provider") or raw.get("route") or raw.get("name") or "unknown")
        role = str(raw.get("recommended_role") or raw.get("role_recommendation") or "unknown")
        tasks = max(0, int(raw.get("sample_size") or raw.get("tasks") or 0))
        rescued = max(0, int(raw.get("rescued_completed") or raw.get("rescued") or 0))
        rescue_rate = self._rate(raw.get("rescue_rate"), rescued, tasks)
        hidden_clean = max(0, int(raw.get("hidden_clean_completed") or raw.get("hidden_clean") or 0))
        hidden_rate = self._rate(
            raw.get("hidden_clean_rate", metrics.get("hidden_test_pass_rate")), hidden_clean, tasks
        )
        usd_per_fix = self._optional_float(raw.get("hidden_clean_usd_per_fix"))
        verified_usd_per_fix = self._optional_float(raw.get("first_party_usd_per_verified_fix"))
        total_usd = self._optional_float(raw.get("first_party_usd_total", raw.get("total_usd")))
        hidden_clean_per_usd = self._optional_float(raw.get("hidden_clean_per_usd"))
        if hidden_clean_per_usd is None and usd_per_fix and usd_per_fix > 0:
            hidden_clean_per_usd = 1.0 / usd_per_fix
        if hidden_clean_per_usd is None and total_usd and total_usd > 0 and hidden_clean > 0:
            hidden_clean_per_usd = hidden_clean / total_usd
        verified_fixes_per_usd = (
            1.0 / verified_usd_per_fix if verified_usd_per_fix and verified_usd_per_fix > 0 else None
        )
        auth_confidence = self._confidence(
            raw.get("auth_confidence", raw.get("route_confidence")), default=0.6
        )
        return {
            "provider": provider,
            "recommended_role": role,
            "sample_size": tasks,
            "hidden_clean_completed": hidden_clean,
            "hidden_clean_rate": hidden_rate,
            "hidden_clean_usd_per_fix": usd_per_fix,
            "hidden_clean_per_usd": hidden_clean_per_usd,
            "verified_usd_per_fix": verified_usd_per_fix,
            "verified_fixes_per_usd": verified_fixes_per_usd,
            "rescue_rate": rescue_rate,
            "latency_ms": self._optional_float(raw.get("avg_latency_ms", raw.get("latency_ms"))),
            "auth_confidence": auth_confidence,
            "cost_coverage": self._confidence(
                raw.get("cost_coverage", raw.get("cost_coverage_percent")), default=0.0
            ),
            "cost_observed": bool(
                usd_per_fix is not None or verified_usd_per_fix is not None
                or total_usd is not None or hidden_clean_per_usd is not None
            ),
            "raw_score": self._optional_float(raw.get("score", raw.get("fitness"))),
            "model": str(raw.get("model") or ""),
        }

    @staticmethod
    def _negative_exclusion_reasons(
        item: Dict[str, Any], policy: EconomistPolicy, records: List[Dict[str, Any]]
    ) -> List[str]:
        reasons: List[str] = []
        for record in records:
            if record.get("state") != "active":
                continue
            capability_id = str(record.get("capability_id") or "")
            if capability_id not in {item["provider"], f"provider:{item['provider']}"}:
                continue
            task_class = str(record.get("task_class") or "general")
            if task_class not in {"general", policy.task_class}:
                continue
            scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
            if scope.get("provider") and str(scope["provider"]) != item["provider"]:
                continue
            if scope.get("model") and str(scope["model"]) != item.get("model"):
                continue
            reasons.append(
                "active negative capability evidence "
                f"{record.get('record_id')} ({record.get('failure_count', 0)} failures)"
            )
        return reasons

    @staticmethod
    def _matching_friction(
        item: Dict[str, Any], policy: EconomistPolicy, profiles: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        matches = []
        for profile in profiles:
            capability_id = str(profile.get("capability_id") or "")
            if capability_id not in {item["provider"], f"provider:{item['provider']}"}:
                continue
            if str(profile.get("task_class") or "general") not in {"general", policy.task_class}:
                continue
            scope = profile.get("scope") if isinstance(profile.get("scope"), dict) else {}
            if scope.get("provider") and str(scope["provider"]) != item["provider"]:
                continue
            if scope.get("model") and str(scope["model"]) != item.get("model"):
                continue
            matches.append(profile)
        return max(matches, key=lambda row: (float(row.get("confidence") or 0), int(row.get("samples") or 0)), default=None)

    def _exclusion_reasons(self, item: Dict[str, Any], policy: EconomistPolicy) -> List[str]:
        reasons = []
        if item["recommended_role"] in INVALID_ROLES:
            reasons.append(f"role {item['recommended_role']} is not routable")
        if item["auth_confidence"] < policy.min_auth_confidence:
            reasons.append("auth confidence below policy minimum")
        if policy.max_latency_ms is not None and item["latency_ms"] is not None and item["latency_ms"] > policy.max_latency_ms:
            reasons.append("latency exceeds envelope")
        effective_usd_per_fix = item["hidden_clean_usd_per_fix"] or item["verified_usd_per_fix"]
        if policy.max_usd_per_fix is not None and effective_usd_per_fix is not None and effective_usd_per_fix > policy.max_usd_per_fix:
            reasons.append("hidden-clean USD/fix exceeds envelope")
        if policy.require_cost_observation and not item["cost_observed"]:
            reasons.append("cost observation required")
        return reasons

    @staticmethod
    def _role_score(requested: str, candidate: str) -> float:
        if requested == candidate:
            return 1.0
        families = {
            "primary_patch_provider": {"candidate_patch_provider", "candidate_patch_provider_high_latency", "clean_patch_candidate", "cheap_clean_candidate_slow", "clean_candidate_cost_incomplete"},
            "rescued_patch_provider": {"rescue_backed_action_ir", "fast_rescue_backed_action_ir", "low_clean_rescue_candidate"},
            "refs_only_action_ir_generator": {"refs_only_transform_selector", "semantic_transform_selector_candidate"},
            "semantic_transform_selector": {"semantic_transform_selector_candidate", "fast_semantic_transform_selector", "refs_only_transform_selector"},
            "scout_only": {"scout_or_microtask_only", "edge_microtask_or_rescue_backed_action_ir", "scout_only_until_hash_contract_fixed"},
        }
        if candidate in families.get(requested, set()):
            return 0.9
        if requested == "primary_patch_provider" and "rescue" in candidate:
            return 0.35
        if requested in {"scout_only", "semantic_transform_selector"} and "candidate" in candidate:
            return 0.65
        return 0.2

    @staticmethod
    def _rescue_fit(requested: str, rescue_rate: float) -> float:
        if requested == "primary_patch_provider":
            return 1.0 - rescue_rate
        if requested == "rescued_patch_provider":
            return min(1.0, rescue_rate + 0.2)
        return 0.7

    @staticmethod
    def _selection_reason(selected: Optional[Dict[str, Any]], policy: EconomistPolicy) -> str:
        if not selected:
            return "No route satisfied role, auth, latency, and cost constraints."
        return (
            f"Selected {selected['provider']} for {policy.requested_role}: best eligible blend of role fit, "
            "hidden-clean economics, rescue fit, latency, and auth confidence."
        )

    @classmethod
    def _counterfactual_crystals(
        cls,
        *,
        selected: Optional[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        excluded: List[Dict[str, Any]],
        policy: EconomistPolicy,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        if not selected:
            return []
        crystals: List[Dict[str, Any]] = []
        alternatives = [item for item in ranked if item.get("provider") != selected.get("provider")]
        alternatives.extend(excluded)
        seen = set()
        for item in alternatives:
            provider = str(item.get("provider") or "")
            if not provider or provider in seen:
                continue
            seen.add(provider)
            failure_class = cls._predicted_failure_class(item)
            predicted_cost = item.get("hidden_clean_usd_per_fix") or item.get("verified_usd_per_fix")
            friction_score = float(item.get("friction_score") or 0.0)
            friction_confidence = float(item.get("friction_confidence") or 0.0)
            predicted_confidence = min(1.0, max(0.0, float(item.get("auth_confidence") or 0.0) * (1.0 - (friction_score * friction_confidence * 0.5))))
            crystals.append({
                "beast_object_type": "counterfactual_crystal_candidate",
                "version": "1.0",
                "task_class": policy.task_class,
                "selected_provider": selected.get("provider"),
                "selected_model": selected.get("model"),
                "alternative_provider": provider,
                "alternative_model": item.get("model"),
                "alternative_rank": len(crystals) + 1,
                "selected_score": selected.get("economist_score"),
                "alternative_score": item.get("economist_score", item.get("base_economist_score", 0.0)),
                "predicted_failure_class": failure_class,
                "predicted_cost_usd": predicted_cost,
                "predicted_latency_ms": item.get("latency_ms"),
                "predicted_confidence": round(predicted_confidence, 6),
                "rejection_reason": cls._counterfactual_reason(item, failure_class),
                "state": "advisory" if predicted_confidence >= 0.7 else "speculative",
            })
            if len(crystals) >= limit:
                break
        return crystals

    @staticmethod
    def _predicted_failure_class(item: Dict[str, Any]) -> str:
        reasons = item.get("exclusion_reasons") if isinstance(item.get("exclusion_reasons"), list) else []
        reason_text = " ".join(str(reason).lower() for reason in reasons)
        if "negative capability" in reason_text:
            return "active_negative_evidence"
        if "auth confidence" in reason_text or float(item.get("auth_confidence") or 0.0) < 0.6:
            return "auth_or_route_confidence"
        if "latency" in reason_text:
            return "latency_envelope"
        if "cost" in reason_text:
            return "cost_envelope"
        if float(item.get("friction_score") or 0.0) >= 0.5:
            return "high_friction"
        if item.get("cost_observed") is False:
            return "cost_unknown"
        if (item.get("latency_ms") or 0) and float(item.get("latency_ms") or 0) >= 30_000:
            return "latency_risk"
        return "lower_expected_value"

    @staticmethod
    def _counterfactual_reason(item: Dict[str, Any], failure_class: str) -> str:
        reasons = item.get("exclusion_reasons") if isinstance(item.get("exclusion_reasons"), list) else []
        if reasons:
            return "; ".join(str(reason)[:160] for reason in reasons[:2])
        return (
            f"Rejected as {failure_class}: score={float(item.get('economist_score') or 0.0):.4f}, "
            f"friction={float(item.get('friction_score') or 0.0):.4f}, "
            f"latency_ms={item.get('latency_ms')}"
        )

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in (None, "", "n/a", "unknown"):
            return None
        try:
            return float(str(value).replace("$", "").replace("%", ""))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _confidence(cls, value: Any, default: float = 0.5) -> float:
        labels = {
            "verified": 1.0, "high": 0.9, "medium_high": 0.8,
            "medium": 0.65, "low": 0.35, "invalid": 0.0, "failed": 0.0,
        }
        if isinstance(value, str) and value.strip().lower() in labels:
            value = labels[value.strip().lower()]
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/", 1)
            try:
                value = float(numerator) / float(denominator)
            except (TypeError, ValueError, ZeroDivisionError):
                value = None
        parsed = cls._optional_float(value)
        if parsed is None:
            return default
        if parsed > 1.0:
            parsed /= 100.0
        return min(1.0, max(0.0, parsed))

    @classmethod
    def _rate(cls, explicit: Any, numerator: int, denominator: int) -> float:
        parsed = cls._optional_float(explicit)
        if parsed is not None:
            if parsed > 1.0:
                parsed /= 100.0
            return min(1.0, max(0.0, parsed))
        return round(numerator / denominator, 6) if denominator else 0.0
