from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.evidence.control_graph import ControlEvidenceGraph


@dataclass(frozen=True, slots=True)
class DisplacementChannel:
    channel: str
    provider_calls_used: int = 0
    provider_calls_avoided: int = 0
    tokens_avoided_observed: int = 0
    events: int = 0
    claim_class: str = "observed"
    notes: tuple[str, ...] = ()

    @property
    def channel_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "provider_calls_used": self.provider_calls_used,
            "provider_calls_avoided": self.provider_calls_avoided,
            "tokens_avoided_observed": self.tokens_avoided_observed,
            "events": self.events,
            "claim_class": self.claim_class,
            "notes": list(self.notes),
            "channel_digest": self.channel_digest,
        }


@dataclass(frozen=True, slots=True)
class DisplacementTrendBucket:
    period: str
    events: int = 0
    provider_calls_used: int = 0
    provider_calls_avoided: int = 0
    tokens_avoided_observed: int = 0
    local_compute_events: int = 0
    provider_fallback_events: int = 0
    visual_promoted_asset_reuses: int = 0
    visual_asset_refusals: int = 0
    semantic_replays: int = 0
    normalized_evidence_events: int = 0
    notes: tuple[str, ...] = ()

    @property
    def bucket_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "events": self.events,
            "provider_calls_used": self.provider_calls_used,
            "provider_calls_avoided": self.provider_calls_avoided,
            "tokens_avoided_observed": self.tokens_avoided_observed,
            "local_compute_events": self.local_compute_events,
            "provider_fallback_events": self.provider_fallback_events,
            "visual_promoted_asset_reuses": self.visual_promoted_asset_reuses,
            "visual_asset_refusals": self.visual_asset_refusals,
            "semantic_replays": self.semantic_replays,
            "normalized_evidence_events": self.normalized_evidence_events,
            "notes": list(self.notes),
            "bucket_digest": self.bucket_digest,
        }


@dataclass(frozen=True, slots=True)
class ProviderReductionScorecard:
    provider_calls_used: int
    provider_calls_avoided: int
    tokens_avoided_observed: int
    semantic_replays: int
    scene_capsules_composed: int
    visual_regions_local: int
    visual_provider_fallbacks: int
    visual_asset_promotions: int
    visual_asset_reuses: int
    visual_asset_refusals: int
    normalized_evidence_events: int
    physical_crystal_replays: int
    provider_fallbacks: int
    g9_bundle_health: tuple[Mapping[str, Any], ...]
    trend_buckets: tuple[DisplacementTrendBucket, ...]
    observed_channels: tuple[DisplacementChannel, ...]
    unsupported_or_estimated_channels: tuple[DisplacementChannel, ...] = ()

    @property
    def provider_reduction_ratio(self) -> float:
        denominator = self.provider_calls_used + self.provider_calls_avoided
        return self.provider_calls_avoided / denominator if denominator else 0.0

    @property
    def scorecard_digest(self) -> str:
        return sha256_digest(
            {
                "provider_calls_used": self.provider_calls_used,
                "provider_calls_avoided": self.provider_calls_avoided,
                "tokens_avoided_observed": self.tokens_avoided_observed,
                "semantic_replays": self.semantic_replays,
                "scene_capsules_composed": self.scene_capsules_composed,
                "visual_regions_local": self.visual_regions_local,
                "visual_provider_fallbacks": self.visual_provider_fallbacks,
                "visual_asset_promotions": self.visual_asset_promotions,
                "visual_asset_reuses": self.visual_asset_reuses,
                "visual_asset_refusals": self.visual_asset_refusals,
                "normalized_evidence_events": self.normalized_evidence_events,
                "physical_crystal_replays": self.physical_crystal_replays,
                "provider_fallbacks": self.provider_fallbacks,
                "g9_bundle_health": self.g9_bundle_health,
                "trend_buckets": tuple(item.bucket_digest for item in self.trend_buckets),
                "observed_channels": tuple(item.channel_digest for item in self.observed_channels),
                "unsupported_or_estimated_channels": tuple(item.channel_digest for item in self.unsupported_or_estimated_channels),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "provider_reduction_scorecard",
            "version": "1.0",
            "provider_calls_used": self.provider_calls_used,
            "provider_calls_avoided": self.provider_calls_avoided,
            "provider_reduction_ratio": self.provider_reduction_ratio,
            "tokens_avoided_observed": self.tokens_avoided_observed,
            "semantic_replays": self.semantic_replays,
            "scene_capsules_composed": self.scene_capsules_composed,
            "visual_regions_local": self.visual_regions_local,
            "visual_provider_fallbacks": self.visual_provider_fallbacks,
            "visual_asset_promotions": self.visual_asset_promotions,
            "visual_asset_reuses": self.visual_asset_reuses,
            "visual_asset_refusals": self.visual_asset_refusals,
            "normalized_evidence_events": self.normalized_evidence_events,
            "physical_crystal_replays": self.physical_crystal_replays,
            "provider_fallbacks": self.provider_fallbacks,
            "g9_bundle_health": [dict(item) for item in self.g9_bundle_health],
            "trend_buckets": [item.to_dict() for item in self.trend_buckets],
            "observed_channels": [item.to_dict() for item in self.observed_channels],
            "unsupported_or_estimated_channels": [item.to_dict() for item in self.unsupported_or_estimated_channels],
            "scorecard_digest": self.scorecard_digest,
        }


class DisplacementObservatory:
    """Project runtime displacement evidence into one conservative scorecard."""

    def build(
        self,
        *,
        counters: Mapping[str, int],
        evidence_graph: ControlEvidenceGraph,
    ) -> ProviderReductionScorecard:
        provider_fallback_nodes = evidence_graph.query("production_provider_fallback")
        physical_nodes = evidence_graph.query("production_displacement_observation")
        economics_nodes = evidence_graph.query("verified_displacement_economics")
        scene_nodes = evidence_graph.query("scene_capsule_composed")
        visual_local_nodes = evidence_graph.query("visual_residual_local_region")
        visual_provider_nodes = evidence_graph.query("visual_residual_provider_fallback")
        visual_asset_nodes = evidence_graph.query("visual_asset_promoted")
        visual_asset_reuse_nodes = evidence_graph.query("visual_residual_promoted_asset_reuse")
        visual_asset_refusal_nodes = evidence_graph.query("visual_asset_candidate_refused")
        normalized_nodes = evidence_graph.query("normalized_reduction_evidence")
        semantic_replay_nodes = evidence_graph.query("semantic_crystal_replayed")
        scene_events = int(counters.get("scene_capsule.composed") or len(scene_nodes))
        visual_local_events = int(counters.get("visual_residual.local_region") or len(visual_local_nodes))
        visual_provider_events = int(counters.get("visual_residual.provider_fallback") or len(visual_provider_nodes))
        visual_asset_promotions = int(counters.get("visual_asset.promoted") or len(visual_asset_nodes))
        visual_asset_reuses = int(counters.get("visual_residual.promoted_asset_reuse") or len(visual_asset_reuse_nodes))
        visual_asset_refusals = int(counters.get("visual_asset.refused") or len(visual_asset_refusal_nodes))

        provider_used = int(counters.get("provider.execute") or 0)
        provider_used = max(
            provider_used,
            sum(self._witness_used(node.receipt) for node in provider_fallback_nodes)
            + sum(self._witness_used(node.receipt) for node in visual_provider_nodes),
        )

        physical_avoided = sum(int(node.receipt.get("provider_calls_avoided") or 0) for node in physical_nodes)
        economics_avoided = sum(int(node.receipt.get("provider_calls_avoided") or 0) for node in economics_nodes)
        semantic_avoided = int(counters.get("operator_language.semantic_reused") or 0)
        normalized_provider_avoided = sum(
            int(node.receipt.get("provider_calls_avoided") or 0)
            for node in normalized_nodes
            if node.receipt.get("claim_class") == "observed"
        )
        provider_avoided = physical_avoided + economics_avoided + semantic_avoided + normalized_provider_avoided
        normalized_observed_tokens = sum(
            int(node.receipt.get("tokens_avoided_observed") or 0)
            for node in normalized_nodes
            if node.receipt.get("claim_class") == "observed"
        )
        normalized_channels = self._normalized_channels(normalized_nodes)
        g9_health = tuple(
            {
                "source_system": str(node.receipt.get("source_system") or ""),
                **dict(node.receipt.get("g9_bundle_health") or {}),
                "evidence_node_id": node.node_id,
            }
            for node in normalized_nodes
            if isinstance(node.receipt.get("g9_bundle_health"), Mapping)
        )
        trend_buckets = self._trend_buckets(
            provider_fallback_nodes=provider_fallback_nodes,
            physical_nodes=physical_nodes,
            economics_nodes=economics_nodes,
            scene_nodes=scene_nodes,
            visual_local_nodes=visual_local_nodes,
            visual_provider_nodes=visual_provider_nodes,
            visual_asset_nodes=visual_asset_nodes,
            visual_asset_reuse_nodes=visual_asset_reuse_nodes,
            visual_asset_refusal_nodes=visual_asset_refusal_nodes,
            normalized_nodes=normalized_nodes,
            semantic_replay_nodes=semantic_replay_nodes,
        )

        channels = (
            DisplacementChannel(
                "semantic_crystals",
                provider_calls_avoided=semantic_avoided,
                events=semantic_avoided,
                notes=("one avoided fresh operator-language interpretation counted as one provider-risk displacement witness",),
            ),
            DisplacementChannel(
                "physical_crystals",
                provider_calls_avoided=physical_avoided,
                events=len(physical_nodes),
                notes=("counts production_displacement_observation receipts only",),
            ),
            DisplacementChannel(
                "verified_displacement_economics",
                provider_calls_avoided=economics_avoided,
                tokens_avoided_observed=sum(int(node.receipt.get("provider_tokens_avoided") or 0) for node in economics_nodes),
                events=len(economics_nodes),
                notes=("paired net-positive economics receipts",),
            ),
            DisplacementChannel(
                "scene_capsules",
                provider_calls_avoided=0,
                events=scene_events,
                notes=("deterministic visual composition is local, but does not count as provider-call avoidance until paired against provider image fallback",),
            ),
            DisplacementChannel(
                "visual_residuals",
                provider_calls_used=sum(self._witness_used(node.receipt) for node in visual_provider_nodes),
                provider_calls_avoided=0,
                events=visual_local_events + visual_asset_reuses,
                notes=("local region-only image fills are wired; promoted asset reuse avoids repeated local residual execution but does not claim provider avoidance without paired provider fallback evidence",),
            ),
            DisplacementChannel(
                "promoted_visual_assets",
                provider_calls_avoided=0,
                events=visual_asset_promotions + visual_asset_reuses,
                notes=("repeated verified region outputs can promote into render-only visual assets; provider avoidance remains conservative until paired with provider-fallback evidence",),
            ),
            DisplacementChannel(
                "visual_asset_refusals",
                provider_calls_avoided=0,
                events=visual_asset_refusals,
                notes=("counts refused visual promotion candidates such as low-quality, unstable, stale, or false reuse candidates",),
            ),
        ) + tuple(item for item in normalized_channels if item.claim_class == "observed")
        normalized_unobserved = tuple(item for item in normalized_channels if item.claim_class != "observed")
        unsupported = (
            DisplacementChannel(
                "visual_image_generation",
                provider_calls_used=sum(self._witness_used(node.receipt) for node in visual_provider_nodes),
                events=visual_local_events + visual_provider_events + visual_asset_promotions + visual_asset_reuses + visual_asset_refusals,
                claim_class="route_selection_only",
                notes=("local fills, explicit provider fallback, and promoted visual asset reuse are wired; net provider-avoidance claims still need paired fallback comparisons",),
            ),
        ) + normalized_unobserved + self._pending_normalized_channels(normalized_channels)
        return ProviderReductionScorecard(
            provider_calls_used=provider_used,
            provider_calls_avoided=provider_avoided,
            tokens_avoided_observed=sum(item.tokens_avoided_observed for item in channels),
            semantic_replays=semantic_avoided,
            scene_capsules_composed=scene_events,
            visual_regions_local=visual_local_events,
            visual_provider_fallbacks=visual_provider_events,
            visual_asset_promotions=visual_asset_promotions,
            visual_asset_reuses=visual_asset_reuses,
            visual_asset_refusals=visual_asset_refusals,
            normalized_evidence_events=len(normalized_nodes),
            physical_crystal_replays=len(physical_nodes),
            provider_fallbacks=len(provider_fallback_nodes),
            g9_bundle_health=g9_health,
            trend_buckets=trend_buckets,
            observed_channels=channels,
            unsupported_or_estimated_channels=unsupported,
        )

    @staticmethod
    def _witness_used(receipt: Mapping[str, Any]) -> int:
        witness = receipt.get("provider_call_witness")
        if not isinstance(witness, Mapping):
            return 0
        return max(0, int(witness.get("during_execution") or 0))

    @staticmethod
    def _normalized_channels(nodes: tuple[Any, ...]) -> tuple[DisplacementChannel, ...]:
        grouped: dict[str, dict[str, Any]] = {}
        priority = {"observed": 3, "estimated": 2, "route_selection_only": 1, "hypothesis": 0}
        for node in nodes:
            receipt = node.receipt
            source = str(receipt.get("source_system") or "unknown")
            claim = str(receipt.get("claim_class") or "hypothesis")
            bucket = grouped.setdefault(source, {
                "provider_calls_avoided": 0,
                "tokens_avoided_observed": 0,
                "events": 0,
                "claim_class": claim,
                "notes": set(),
            })
            bucket["events"] += 1
            if priority.get(claim, 0) > priority.get(str(bucket["claim_class"]), 0):
                bucket["claim_class"] = claim
            if claim == "observed":
                bucket["provider_calls_avoided"] += int(receipt.get("provider_calls_avoided") or 0)
                bucket["tokens_avoided_observed"] += int(receipt.get("tokens_avoided_observed") or 0)
            for note in receipt.get("notes") or ():
                bucket["notes"].add(str(note))
        return tuple(
            DisplacementChannel(
                source,
                provider_calls_avoided=int(values["provider_calls_avoided"]),
                tokens_avoided_observed=int(values["tokens_avoided_observed"]),
                events=int(values["events"]),
                claim_class=str(values["claim_class"]),
                notes=tuple(sorted(values["notes"])),
            )
            for source, values in sorted(grouped.items())
        )

    @staticmethod
    def _pending_normalized_channels(channels: tuple[DisplacementChannel, ...]) -> tuple[DisplacementChannel, ...]:
        present = {item.channel for item in channels}
        pending: list[DisplacementChannel] = []
        if "forge_kv_prompt_cache" not in present:
            pending.append(DisplacementChannel(
                "forge_kv_prompt_cache",
                events=0,
                claim_class="hypothesis",
                notes=("no normalized Forge KV native-restore evidence has been ingested yet",),
            ))
        if "grand_closure" not in present:
            pending.append(DisplacementChannel(
                "grand_closure",
                events=0,
                claim_class="route_selection_only",
                notes=("no normalized Grand Closure/G9 bundle-health evidence has been ingested yet",),
            ))
        if "commons_spaces" not in present:
            pending.append(DisplacementChannel(
                "commons_spaces",
                events=0,
                claim_class="hypothesis",
                notes=("no locally reproduced/promoted Commons Space reduction receipt has been ingested yet",),
            ))
        return tuple(pending)

    @classmethod
    def _trend_buckets(
        cls,
        *,
        provider_fallback_nodes: tuple[Any, ...],
        physical_nodes: tuple[Any, ...],
        economics_nodes: tuple[Any, ...],
        scene_nodes: tuple[Any, ...],
        visual_local_nodes: tuple[Any, ...],
        visual_provider_nodes: tuple[Any, ...],
        visual_asset_nodes: tuple[Any, ...],
        visual_asset_reuse_nodes: tuple[Any, ...],
        visual_asset_refusal_nodes: tuple[Any, ...],
        normalized_nodes: tuple[Any, ...],
        semantic_replay_nodes: tuple[Any, ...],
    ) -> tuple[DisplacementTrendBucket, ...]:
        buckets: dict[str, dict[str, Any]] = {}

        def bucket_for(node: Any) -> dict[str, Any]:
            period = cls._period_for(node.receipt)
            return buckets.setdefault(period, {
                "events": 0,
                "provider_calls_used": 0,
                "provider_calls_avoided": 0,
                "tokens_avoided_observed": 0,
                "local_compute_events": 0,
                "provider_fallback_events": 0,
                "visual_promoted_asset_reuses": 0,
                "visual_asset_refusals": 0,
                "semantic_replays": 0,
                "normalized_evidence_events": 0,
                "notes": set(),
            })

        for node in provider_fallback_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["provider_calls_used"] += cls._witness_used(node.receipt)
            bucket["provider_fallback_events"] += 1
        for node in visual_provider_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["provider_calls_used"] += cls._witness_used(node.receipt)
            bucket["provider_fallback_events"] += 1
        for node in physical_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["provider_calls_avoided"] += int(node.receipt.get("provider_calls_avoided") or 0)
            bucket["local_compute_events"] += 1
        for node in economics_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["provider_calls_avoided"] += int(node.receipt.get("provider_calls_avoided") or 0)
            bucket["tokens_avoided_observed"] += int(node.receipt.get("provider_tokens_avoided") or 0)
        for node in scene_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["local_compute_events"] += 1
        for node in visual_local_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["local_compute_events"] += 1
        for node in visual_asset_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["local_compute_events"] += 1
            bucket["notes"].add("visual asset promotion")
        for node in visual_asset_reuse_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["local_compute_events"] += 1
            bucket["visual_promoted_asset_reuses"] += 1
        for node in visual_asset_refusal_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["visual_asset_refusals"] += 1
            reason = str(node.receipt.get("reason") or "visual_candidate_refused")
            bucket["notes"].add(reason)
        for node in normalized_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["normalized_evidence_events"] += 1
            if node.receipt.get("claim_class") == "observed":
                bucket["provider_calls_avoided"] += int(node.receipt.get("provider_calls_avoided") or 0)
                bucket["tokens_avoided_observed"] += int(node.receipt.get("tokens_avoided_observed") or 0)
        for node in semantic_replay_nodes:
            bucket = bucket_for(node)
            bucket["events"] += 1
            bucket["provider_calls_avoided"] += int(node.receipt.get("provider_calls_avoided") or 0)
            bucket["semantic_replays"] += 1

        return tuple(
            DisplacementTrendBucket(
                period=period,
                events=int(values["events"]),
                provider_calls_used=int(values["provider_calls_used"]),
                provider_calls_avoided=int(values["provider_calls_avoided"]),
                tokens_avoided_observed=int(values["tokens_avoided_observed"]),
                local_compute_events=int(values["local_compute_events"]),
                provider_fallback_events=int(values["provider_fallback_events"]),
                visual_promoted_asset_reuses=int(values["visual_promoted_asset_reuses"]),
                visual_asset_refusals=int(values["visual_asset_refusals"]),
                semantic_replays=int(values["semantic_replays"]),
                normalized_evidence_events=int(values["normalized_evidence_events"]),
                notes=tuple(sorted(values["notes"])),
            )
            for period, values in sorted(buckets.items())
        )

    @staticmethod
    def _period_for(receipt: Mapping[str, Any]) -> str:
        for key in ("observed_at", "ingested_at", "created_at"):
            value = receipt.get(key)
            if isinstance(value, str) and len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
                return value[:10]
        return "undated"
