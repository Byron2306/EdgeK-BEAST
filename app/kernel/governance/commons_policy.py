"""Tiny local policy ranker trained over privacy-safe BEAST receipts."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.security.crystal_seal import canonical_bytes


class CommonsPolicyLearner:
    """Extract receipt examples and make non-enforcing route recommendations."""

    def __init__(self, registry: CommonsSpaceRegistry, compute_ledger: Any = None):
        self.registry = registry
        self.compute_ledger = compute_ledger

    def extract_examples(self, limit: int = 500) -> Dict[str, Any]:
        examples: List[Dict[str, Any]] = []
        registry = self.registry.list_spaces()
        for row in registry.get("spaces") or []:
            if not row.get("valid"):
                continue
            detail = self.registry.get(str(row["space_id"]))
            examples.append(self._space_example(detail))
        if self.compute_ledger is not None:
            plans = self.compute_ledger.recent_receipts(limit)
            plan_by_id = {str(item.get("plan_id") or ""): item for item in plans}
            for receipt in self.compute_ledger.recent_receipts(limit):
                examples.append(self._compute_example(receipt, plan_by_id.get(str(receipt.get("plan_id") or ""), {})))
        examples = [item for item in examples if item.get("labels", {}).get("route")]
        return {
            "beast_object_type": "commons_policy_examples",
            "version": "1.0",
            "privacy": "fingerprints_and_route_metadata_only",
            "count": len(examples),
            "examples": examples,
            "dataset_hash": "sha256:" + hashlib.sha256(canonical_bytes({"examples": examples})).hexdigest(),
        }

    def build_labels(self, plan: Dict[str, Any], route_id: str) -> Dict[str, Any]:
        route = [str(item) for item in (plan.get("route") or plan.get("required_route") or [])]
        subagents = [str(item) for item in (plan.get("subagents") or plan.get("required_subagents") or [])]
        orchestration = {"zeroclaw", "openclaw", "nemoclaw", "swarm", "approval_gate", "promotion_candidate"}
        tools = [item for item in route if item not in orchestration and item not in subagents]
        return {
            "route": route_id,
            "tools": sorted(set(tools)),
            "subagents": sorted(set(subagents)),
            "reuse": [item for item in route if "crystal" in item or "commons" in item],
        }

    def train(self, examples: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        examples = examples if examples is not None else self.extract_examples()["examples"]
        routes = sorted({str(item["labels"]["route"]) for item in examples})
        weights: Dict[str, Dict[str, float]] = {route: defaultdict(float) for route in routes}  # type: ignore[assignment]
        support: Dict[str, Dict[str, Any]] = {}
        for item in examples:
            target = str(item["labels"]["route"])
            utility = self._utility(item)
            for feature in self._features(item.get("features") or {}):
                weights[target][feature] += utility
            profile = support.setdefault(target, {"samples": 0, "verified": 0, "utility_sum": 0.0})
            profile["samples"] += 1
            profile["verified"] += int(bool((item.get("outcome") or {}).get("verified")))
            profile["utility_sum"] += utility
        normalized = {}
        for route, route_weights in weights.items():
            count = max(1, int(support[route]["samples"]))
            normalized[route] = {key: round(value / count, 6) for key, value in route_weights.items()}
            support[route]["verified_rate"] = round(support[route]["verified"] / count, 6)
            support[route]["mean_utility"] = round(support[route].pop("utility_sum") / count, 6)
        model = {
            "beast_object_type": "commons_tiny_policy_ranker",
            "version": "1.0",
            "model_type": "tiny_hashed_linear_ranker",
            "mode": "shadow",
            "enforcing": False,
            "sample_size": len(examples),
            "routes": routes,
            "weights": normalized,
            "support": support,
        }
        model["model_hash"] = "sha256:" + hashlib.sha256(canonical_bytes(model)).hexdigest()
        return model

    def recommend(
        self,
        request: Dict[str, Any],
        model: Optional[Dict[str, Any]] = None,
        examples: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        examples = examples if examples is not None else self.extract_examples()["examples"]
        model = model or self.train(examples)
        features = {
            "task_class": str(request.get("task_class") or "general"),
            "risk": str(request.get("risk") or "medium"),
            "gpu_available": bool(request.get("gpu_available", False)),
            "approval_required": bool(request.get("approval_required", False)),
        }
        active = self._features(features)
        ranked = []
        for route in model.get("routes") or []:
            route_weights = (model.get("weights") or {}).get(route) or {}
            score = sum(float(route_weights.get(feature) or 0.0) for feature in active)
            support = (model.get("support") or {}).get(route) or {}
            score += 0.1 * math.log1p(int(support.get("samples") or 0))
            ranked.append({"route": route, "score": round(score, 6), **support})
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["route"])))
        heuristic = self.heuristic(request)
        selected = ranked[0] if ranked else {"route": heuristic["route"], "score": 0.0, "samples": 0, "verified_rate": 0.0}
        matched = [item for item in examples if item["labels"]["route"] == selected["route"]]
        labels = self._consensus_labels(matched)
        return {
            "beast_object_type": "commons_policy_shadow_recommendation",
            "version": "1.0",
            "mode": "shadow",
            "enforcing": False,
            "task_class": features["task_class"],
            "recommendation": {
                "route": selected["route"],
                **labels,
                "score": selected.get("score"),
                "expected_compute_reduction": round(sum(self._utility(item) for item in matched) / len(matched), 6) if matched else 0.0,
                "risk": features["risk"],
            },
            "verification_projection": {
                "historical_support": len(matched),
                "verified_support": sum(1 for item in matched if item.get("outcome", {}).get("verified")),
                "would_preserve_verification": bool(matched and all(item.get("outcome", {}).get("verified") for item in matched)),
                "claim_boundary": "Historical shadow projection; no provider call or route is suppressed.",
            },
            "ranked_routes": ranked,
            "static_baseline": heuristic,
            "model_hash": model.get("model_hash"),
        }

    def heuristic(self, request: Dict[str, Any]) -> Dict[str, Any]:
        risk = str(request.get("risk") or "medium").lower()
        if risk == "low":
            route = "deterministic_then_local"
        elif risk == "high":
            route = "local_model_beast_then_approved_escalation"
        else:
            route = "local_model_then_provider"
        return {
            "beast_object_type": "commons_static_policy_baseline",
            "route": route,
            "risk": risk,
            "approval_required": risk == "high" or bool(request.get("approval_required")),
        }

    def evaluate(self, examples: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        examples = examples if examples is not None else self.extract_examples()["examples"]
        predictions = []
        holdout = len(examples) >= 2
        for index, item in enumerate(examples):
            training = [row for i, row in enumerate(examples) if i != index] if holdout else examples
            model = self.train(training)
            prediction = self.recommend(item.get("features") or {}, model, examples=training)
            actual = item["labels"]["route"]
            predicted = prediction["recommendation"]["route"]
            predictions.append({
                "example_id": item["example_id"],
                "actual_route": actual,
                "predicted_route": predicted,
                "route_match": predicted == actual,
                "actual_verified": bool(item.get("outcome", {}).get("verified")),
                "projected_preserved": prediction["verification_projection"]["would_preserve_verification"],
            })
        count = len(predictions)
        verified = [item for item in predictions if item["actual_verified"]]
        return {
            "beast_object_type": "commons_policy_offline_evaluation",
            "version": "1.0",
            "protocol": "leave_one_out" if holdout else "in_sample_insufficient_for_holdout",
            "sample_size": count,
            "top1_route_accuracy": round(sum(1 for item in predictions if item["route_match"]) / count, 6) if count else None,
            "verification_preservation_projection_rate": round(sum(1 for item in verified if item["projected_preserved"]) / len(verified), 6) if verified else None,
            "predictions": predictions,
        }

    def _space_example(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        manifest = detail["manifest"]
        receipt = detail["reduction_receipt"]
        plan = {}
        root = self.registry.root / str(manifest["space_id"])
        for artifact in manifest.get("artifacts") or []:
            if artifact.get("artifact_type") == "orchestration_plan":
                plan = json.loads((root / artifact["path"]).read_text(encoding="utf-8"))
                break
        route_id = str((receipt.get("optimized_route") or {}).get("route_id") or "")
        labels = self.build_labels(plan, route_id)
        features = {
            "task_class": manifest.get("task_class") or "general",
            "risk": (manifest.get("safety") or {}).get("risk") or "medium",
            "gpu_available": bool((manifest.get("hardware_profile") or {}).get("gpu_required")),
            "approval_required": bool((manifest.get("safety") or {}).get("approval_required")),
        }
        outcome = {
            "verified": bool((receipt.get("verifier") or {}).get("passed")),
            "provider_calls_avoided": (receipt.get("displacement") or {}).get("provider_calls_avoided"),
            "tokens_avoided": (receipt.get("displacement") or {}).get("tokens_avoided"),
            "gpu_avoided": (receipt.get("resource_deltas") or {}).get("gpu_avoided"),
        }
        return self._example("space:" + str(manifest["space_id"]), features, labels, outcome)

    def _compute_example(self, receipt: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        route = str(receipt.get("selected_rung") or receipt.get("provider") or "")
        shadow_tools = [
            str(item.get("candidate_name") or item.get("transform") or "")
            for item in receipt.get("deterministic_shadow_results") or []
            if isinstance(item, dict)
        ]
        labels = {"route": route, "tools": sorted(set(filter(None, shadow_tools))), "subagents": [], "reuse": list(plan.get("reuse_candidates") or [])}
        features = {
            "task_class": plan.get("task_class") or "general",
            "risk": "low" if route == "deterministic" else "medium",
            "gpu_available": False,
            "approval_required": False,
        }
        status = str(receipt.get("status") or "")
        outcome = {
            "verified": receipt.get("behavior_preserved") is not False and (
                status in {"succeeded", "completed", "passed", "deterministic_succeeded"}
                or "success" in status
            ),
            "provider_calls_avoided": 0 if receipt.get("provider_execution_requested", True) else 1,
            "tokens_avoided": receipt.get("observed_avoidable_tokens"),
            "gpu_avoided": False,
        }
        return self._example("compute:" + str(receipt.get("receipt_id") or "unknown"), features, labels, outcome)

    @staticmethod
    def _example(source: str, features: Dict[str, Any], labels: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"source": source, "features": features, "labels": labels, "outcome": outcome}
        payload["example_id"] = "policy_ex_" + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:20]
        return payload

    @staticmethod
    def _features(features: Dict[str, Any]) -> List[str]:
        return [
            "bias",
            "task_class=" + str(features.get("task_class") or "general"),
            "risk=" + str(features.get("risk") or "medium"),
            "gpu_available=" + str(bool(features.get("gpu_available"))).lower(),
            "approval_required=" + str(bool(features.get("approval_required"))).lower(),
        ]

    @staticmethod
    def _utility(example: Dict[str, Any]) -> float:
        outcome = example.get("outcome") or {}
        score = 0.55 if outcome.get("verified") else 0.0
        score += min(0.2, max(0, int(outcome.get("tokens_avoided") or 0)) / 50_000)
        score += min(0.15, 0.15 * max(0, int(outcome.get("provider_calls_avoided") or 0)))
        score += 0.1 if outcome.get("gpu_avoided") else 0.0
        return round(min(1.0, score), 6)

    @staticmethod
    def _consensus_labels(examples: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
        examples = list(examples)
        output = {}
        for field in ("tools", "subagents", "reuse"):
            counts: Dict[str, int] = defaultdict(int)
            for item in examples:
                for value in item.get("labels", {}).get(field) or []:
                    counts[str(value)] += 1
            output[field] = [key for key, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:8]]
        return output
