"""Crystal-aware inference reuse gateway.

This module turns BEAST's reusable inference substrate into a single runtime
decision point. The live path is BEAST-native and local-first: durable storage,
semantic cache, KV metadata transport, and local CPU execution are the default
capabilities. Compatibility export envelopes remain available for older callers,
but they are generated from local receipts rather than external service state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.kernel.compute.local_capabilities import LocalCapabilityRegistry
from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport, KVCacheBlock
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.compute.semantic_matchers.beast_local_semantic_matcher import BeastLocalSemanticMatcher
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, RuntimeReplayResult
from app.kernel.storage.memory_hull import MemoryHull


CRYSTAL_GATEWAY_VERSION = "1.0"
SEMANTIC_REUSE_THRESHOLD = float(os.environ.get("BEAST_SEMANTIC_REUSE_THRESHOLD", "0.82"))


@dataclass(frozen=True)
class CrystalReuseRequest:
    prompt: str
    model: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    task_class: str = "chat_completion"
    repo_fingerprint: Optional[str] = None
    policy_version: str = "crystal_reuse_v1"
    tokenizer: str = ""
    prompt_prefix: str = ""
    preferred_engine: Optional[str] = None
    provider: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def prompt_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()

    @property
    def effective_prompt_prefix(self) -> str:
        if self.prompt_prefix:
            return self.prompt_prefix
        return self.prompt[: min(len(self.prompt), 2048)]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["prompt_hash"] = self.prompt_hash
        payload["prompt_preview"] = self.prompt[:500]
        payload.pop("prompt", None)
        return {
            "beast_object_type": "crystal_reuse_request",
            "version": CRYSTAL_GATEWAY_VERSION,
            **payload,
        }


@dataclass(frozen=True)
class CrystalReuseDecision:
    decision_id: str
    action: str  # "reuse_answer" | "reuse_semantic_credit" | "reuse_kv_prefill" | "execute_local_cpu" | "execute_litellm_cloud" | "deny_or_require_approval"
    source: str
    confidence: float
    reason: str
    payload: Dict[str, Any] = field(default_factory=dict)
    avoided_tokens_estimate: int = 0
    telemetry: Dict[str, Any] = field(default_factory=dict)
    residue_seal: Dict[str, Any] = field(default_factory=dict)

    @property
    def should_call_provider(self) -> bool:
        return self.action == "execute_litellm_cloud"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_reuse_decision",
            "version": CRYSTAL_GATEWAY_VERSION,
            "decision_id": self.decision_id,
            "action": self.action,
            "source": self.source,
            "confidence": self.confidence,
            "reason": self.reason,
            "payload": self.payload,
            "avoided_tokens_estimate": self.avoided_tokens_estimate,
            "telemetry": self.telemetry,
            "residue_seal": self.residue_seal,
        }


class CrystalReuseGateway:
    """Decide whether BEAST can reuse crystallized inference before live compute."""

    def __init__(
        self,
        storage: Optional[DurableInferenceStorage] = None,
        kv_transport: Optional[CrossEngineKVCacheTransport] = None,
        memory_hull: Optional[MemoryHull] = None,
        seal: Optional[ResidueSeal] = None,
        semantic_matcher: Optional[Callable[[CrystalReuseRequest], Optional[RuntimeReplayResult]]] = None,
        reuse_threshold: float = SEMANTIC_REUSE_THRESHOLD,
        local_capabilities: Optional[LocalCapabilityRegistry] = None,
        local_semantic_cache: Optional[LocalSemanticCache] = None,
        trace_ledger: Optional[LocalTraceLedger] = None,
        eval_gate: Optional[LocalEvalGate] = None,
        route_optimizer: Optional[LocalRouteOptimizer] = None,
    ) -> None:
        self.storage = storage or DurableInferenceStorage()
        self.kv_transport = kv_transport or CrossEngineKVCacheTransport()
        self.seal = seal or ResidueSeal()
        self.memory_hull = memory_hull
        self.local_semantic_cache = local_semantic_cache
        self.semantic_matcher = semantic_matcher or (BeastLocalSemanticMatcher(local_semantic_cache) if local_semantic_cache else None)
        self.reuse_threshold = max(0.0, min(1.0, float(reuse_threshold)))
        self.local_capabilities = local_capabilities or LocalCapabilityRegistry()
        self.trace_ledger = trace_ledger
        self.eval_gate = eval_gate or LocalEvalGate()
        self.route_optimizer = route_optimizer

    def decide(self, request: CrystalReuseRequest, *, seal_decision: bool = True) -> CrystalReuseDecision:
        started = time.perf_counter()
        replay = self.storage.runtime_lookup_replay(
            task_class=request.task_class,
            repo_fingerprint=request.repo_fingerprint,
            prompt_hash=request.prompt_hash,
            model=request.model,
            parameters=request.parameters,
            tokenizer=request.tokenizer or None,
            prompt_prefix=request.effective_prompt_prefix if request.tokenizer else None,
            system_prompt=request.system_prompt if request.tokenizer else None,
        )
        if replay is not None:
            return self._decision_from_replay(request, replay, started, seal_decision=seal_decision)

        semantic = self._semantic_lookup(request)
        if semantic is not None and semantic.confidence >= self.reuse_threshold:
            return self._decision_from_replay(request, semantic, started, source="semantic_cache", seal_decision=seal_decision)

        kv_block = self._lookup_kv_block(request)
        if kv_block is not None:
            replay = RuntimeReplayResult(
                replay_type="kv_prefill",
                credit_id=kv_block.block_id,
                reusable=True,
                payload={"kv_cache_block": kv_block.to_dict()},
                avoided_tokens_estimate=max(0, int(kv_block.seq_len)),
                confidence=0.78,
                reason="kv_cache_block_reused",
            )
            return self._decision_from_replay(request, replay, started, source="kv_transport", seal_decision=seal_decision)

        return self._execute_local_cpu_decision(request, started, seal_decision=seal_decision)

    def record_execution_response(
        self,
        request: CrystalReuseRequest,
        response: str,
        *,
        route: str = "local_cpu",
        engine: str = "ollama",
        cost_usd: Optional[float] = None,
        verified: bool = False,
        avoided_tokens_estimate: int = 0,
        evidence: Optional[Dict[str, Any]] = None,
        write_memory: bool = True,
    ) -> Dict[str, Any]:
        eval_result = self._evaluate_promotion(request, response, evidence=evidence)
        promotion_allowed = bool(eval_result.get("promotion_allowed", True))
        verified_for_promotion = bool(verified and promotion_allowed)

        answer = self.storage.store_answer(
            request.prompt_hash,
            request.model,
            request.parameters,
            response,
            cost_usd=cost_usd,
        )
        semantic_credit = None
        if verified_for_promotion:
            semantic_credit = self.storage.store_semantic_result(
                task_class=request.task_class,
                repo_fingerprint=request.repo_fingerprint or "n/a",
                policy_version=request.policy_version,
                verified_tests=["visible", "hidden"],
                avoided_tokens_estimate=max(0, int(avoided_tokens_estimate)),
                confidence=0.88,
                impact_fingerprint_hash=self._impact_hash(request, response),
                evidence_packet_id=str((evidence or {}).get("evidence_packet_id") or ""),
                metadata={
                    "source": "provider_response_crystallized",
                    "answer_credit_id": answer.credit_id,
                    "model": request.model,
                    "provider": request.provider,
                    "request": request.to_dict(),
                    "evidence": evidence or {},
                    "local_eval_gate": eval_result,
                },
            )
            if self.local_semantic_cache is not None:
                self.local_semantic_cache.put(
                    credit_id=semantic_credit.credit_id,
                    prompt=request.prompt,
                    task_class=request.task_class,
                    repo_fingerprint=request.repo_fingerprint or "n/a",
                    answer=response,
                    confidence=semantic_credit.confidence,
                    verified=True,
                    policy_version=request.policy_version,
                    metadata={
                        "source": "crystal_reuse_record_execution_response",
                        "answer_credit_id": answer.credit_id,
                        "route": route,
                        "engine": engine,
                        "provider": request.provider,
                        "local_eval_gate": eval_result,
                    },
                )

        hull_receipt = None
        if write_memory and self.memory_hull is not None:
            hull_receipt = self.memory_hull.write_residue(
                task=f"Crystallized inference for {request.task_class}",
                provider=request.provider or request.model,
                cost_saved={"avoided_tokens_estimate": avoided_tokens_estimate},
                decision="Stored provider response as reusable BEAST crystal.",
                evidence={
                    "answer_credit_id": answer.credit_id,
                    "semantic_credit_id": getattr(semantic_credit, "credit_id", ""),
                    "verified": verified_for_promotion,
                    "requested_verified": verified,
                    "local_eval_gate": eval_result,
                    **(evidence or {}),
                },
                section="residue",
                policy_tags=["crystal_reuse", "provider_response"],
                correlation_id=str(request.metadata.get("correlation_id") or ""),
            )
        receipt = {
            "beast_object_type": "crystal_reuse_record_receipt",
            "version": CRYSTAL_GATEWAY_VERSION,
            "answer_credit_id": answer.credit_id,
            "semantic_credit_id": getattr(semantic_credit, "credit_id", ""),
            "memory_hull": hull_receipt,
            "storage_metrics": self.storage.get_metrics(),
            "route": route,
            "engine": engine,
            "verified_requested": bool(verified),
            "promotion_allowed": promotion_allowed,
            "local_eval_gate": eval_result,
        }
        route_recorded = self._record_route_feedback(
            request,
            route=route,
            engine=engine,
            success=bool(response.strip()) and promotion_allowed,
            tokens=max(0, int(avoided_tokens_estimate)),
            evidence=evidence or {},
        )
        if route_recorded:
            receipt["local_route_optimizer"] = route_recorded
        self._record_trace(
            str(request.metadata.get("correlation_id") or request.prompt_hash),
            "crystal_reuse_record_execution_response",
            receipt,
        )
        return receipt

    def register_prefill_crystal(
        self,
        request: CrystalReuseRequest,
        *,
        kv_cache_metadata: Dict[str, Any],
        compatibility: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not request.tokenizer:
            raise ValueError("tokenizer is required to register a prefill crystal")
        credit = self.storage.store_prefill(
            model=request.model,
            tokenizer=request.tokenizer,
            prompt_prefix=request.effective_prompt_prefix,
            system_prompt=request.system_prompt,
            kv_cache_metadata=kv_cache_metadata,
            compatibility=compatibility,
        )
        return {
            "beast_object_type": "crystal_prefill_registration",
            "version": CRYSTAL_GATEWAY_VERSION,
            "credit_id": credit.credit_id,
            "artifact_type": credit.artifact_type,
            "metadata": credit.metadata,
        }

    def register_kv_block(
        self,
        request: CrystalReuseRequest,
        *,
        engine: str,
        location: str = "cpu",
        precision: str = "fp16",
        num_layers: int = 0,
        num_heads: int = 0,
        head_dim: int = 0,
        seq_len: int = 0,
        size_bytes: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        tensor_payload: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        if not request.tokenizer:
            raise ValueError("tokenizer is required to register a KV block")
        block = self.kv_transport.register_block(
            model=request.model,
            tokenizer=request.tokenizer,
            prompt_prefix=request.effective_prompt_prefix,
            system_prompt=request.system_prompt,
            engine=CacheEngine(engine),
            location=CacheLocation(location),
            precision=precision,
            num_layers=num_layers,
            num_heads=num_heads,
            head_dim=head_dim,
            seq_len=seq_len,
            size_bytes=size_bytes,
            metadata=metadata,
            tensor_payload=tensor_payload,
        )
        self.kv_transport.pin(block.block_id)
        return {
            "beast_object_type": "crystal_kv_block_registration",
            "version": CRYSTAL_GATEWAY_VERSION,
            "block": self.kv_transport.blocks[block.block_id].to_dict(),
        }

    def export_openllmetry_span(self, decision: CrystalReuseDecision) -> Dict[str, Any]:
        return {
            "name": "beast.local_crystal_reuse",
            "kind": "internal",
            "attributes": {
                "beast.object_type": "crystal_reuse_decision",
                "beast.decision_id": decision.decision_id,
                "beast.crystal.action": decision.action,
                "beast.crystal.source": decision.source,
                "beast.crystal.confidence": decision.confidence,
                "beast.crystal.avoided_tokens": decision.avoided_tokens_estimate,
                "beast.crystal.reason": decision.reason,
                "beast.local_only": True,
            },
        }

    def export_langfuse_observation(self, decision: CrystalReuseDecision) -> Dict[str, Any]:
        return {
            "type": "GENERATION",
            "name": "BEAST local crystal reuse",
            "metadata": {
                "decision_id": decision.decision_id,
                "action": decision.action,
                "source": decision.source,
                "reason": decision.reason,
                "avoided_tokens_estimate": decision.avoided_tokens_estimate,
                "local_only": True,
            },
            "scores": [{"name": "crystal_reuse_confidence", "value": float(decision.confidence)}],
        }

    def export_promptfoo_assertion(self, decision: CrystalReuseDecision, *, min_confidence: float = 0.80) -> Dict[str, Any]:
        return {
            "type": "local_eval_gate",
            "value": f"confidence >= {float(min_confidence):.3f}",
            "metadata": {
                "beast_object_type": "local_eval_gate_assertion",
                "decision_id": decision.decision_id,
                "action": decision.action,
                "source": decision.source,
            },
        }

    def export_integration_bundle(self, decision: CrystalReuseDecision) -> Dict[str, Any]:
        decision_dict = decision.to_dict()
        request = ((decision.payload or {}).get("request") or {})
        reuse = ((decision.payload or {}).get("reuse") or {})
        reuse_payload = reuse.get("payload") if isinstance(reuse, dict) else {}
        kv_block = reuse_payload.get("kv_cache_block") if isinstance(reuse_payload, dict) else {}
        bundle = {
            "beast_object_type": "beast_local_capability_export_bundle",
            "version": CRYSTAL_GATEWAY_VERSION,
            "decision_id": decision.decision_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "local_semantic_cache": {
                "beast_object_type": "local_semantic_cache_record",
                "version": CRYSTAL_GATEWAY_VERSION,
                "decision_id": decision.decision_id,
                "prompt_hash": request.get("prompt_hash"),
                "cache_hit": decision.action in {"reuse_answer", "reuse_semantic_credit"},
                "confidence": decision.confidence,
                "answer": reuse_payload.get("answer") or reuse_payload.get("response") if isinstance(reuse_payload, dict) else None,
            },
            "local_prefix_kv_store": {
                "beast_object_type": "local_prefix_kv_manifest",
                "version": CRYSTAL_GATEWAY_VERSION,
                "decision_id": decision.decision_id,
                "cache_key": kv_block.get("block_id") or decision.decision_id if isinstance(kv_block, dict) else decision.decision_id,
                "reuse_allowed": decision.action == "reuse_kv_prefill",
                "kv_cache_block": kv_block if isinstance(kv_block, dict) else {},
            },
            "local_execution_gateway": {
                "beast_object_type": "local_execution_route_metadata",
                "version": CRYSTAL_GATEWAY_VERSION,
                "route": "local_cpu",
                "cloud_used": False,
                "decision_action": decision.action,
            },
            "local_trace_ledger": self.export_openllmetry_span(decision),
            "local_route_optimizer": {
                "beast_object_type": "local_route_feedback_candidate",
                "version": CRYSTAL_GATEWAY_VERSION,
                "episode_id": decision.decision_id,
                "metric_name": "beast_local_crystal_reuse",
                "value": float(decision.confidence),
                "payload_sha256": "sha256:" + hashlib.sha256(json.dumps(decision_dict, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
            },
            "local_eval_gate": self.export_promptfoo_assertion(decision),
        }
        bundle.update(self._legacy_export_aliases(decision, request, reuse_payload, kv_block))
        return bundle

    def local_capability_health(self) -> Dict[str, Any]:
        return self.local_capabilities.health()

    def integration_health(self, *, probe: bool = False, timeout_seconds: float = 0.45) -> Dict[str, Any]:
        return self.local_capabilities.health(probe=probe, timeout_seconds=timeout_seconds)

    def integration_profiles(self) -> List[Any]:
        # Replaced with local capability profiles
        return self.local_capabilities.profiles()

    def inventory(self, *, probe_integrations: bool = False, probe_timeout_seconds: float = 0.45) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_reuse_gateway_inventory",
            "version": CRYSTAL_GATEWAY_VERSION,
            "reuse_threshold": self.reuse_threshold,
            "storage": self.storage.get_metrics(),
            "kv_transport": self.kv_transport.get_stats(),
            "integration_health": self.integration_health(probe=probe_integrations, timeout_seconds=probe_timeout_seconds),
            "local_capability_health": self.local_capability_health(),
            "integrations": [profile.to_dict() for profile in self.integration_profiles()],
            "runtime_order": [
                "exact_answer",
                "verified_semantic_credit",
                "local_semantic_cache_match",
                "memory_hull_recall",
                "prompt_prefix_prefill",
                "local_cpu_execution",
                "local_quality_gate",
                "governed_cloud_escalation",
            ],
        }

    def _semantic_lookup(self, request: CrystalReuseRequest) -> Optional[RuntimeReplayResult]:
        if self.semantic_matcher is None:
            return None
        replay = self.semantic_matcher(request)
        if replay is None or not replay.reusable:
            return None
        return replay

    def _lookup_kv_block(self, request: CrystalReuseRequest) -> Optional[KVCacheBlock]:
        if not request.tokenizer:
            return None
        preferred_engine = None
        if request.preferred_engine:
            try:
                preferred_engine = CacheEngine(request.preferred_engine)
            except ValueError:
                preferred_engine = None
        return self.kv_transport.lookup(
            request.model,
            request.tokenizer,
            request.effective_prompt_prefix,
            request.system_prompt,
            preferred_engine=preferred_engine,
        )

    def _decision_from_replay(
        self,
        request: CrystalReuseRequest,
        replay: RuntimeReplayResult,
        started: float,
        *,
        source: str = "durable_inference_storage",
        seal_decision: bool,
    ) -> CrystalReuseDecision:
        action = {
            "cached_answer": "reuse_answer",
            "semantic_credit": "reuse_semantic_credit",
            "kv_prefill": "reuse_kv_prefill",
        }.get(replay.replay_type, "reuse_semantic_credit")
        payload = {
            "request": request.to_dict(),
            "reuse": replay.to_dict(),
        }
        decision = CrystalReuseDecision(
            decision_id=self._decision_id(action, request, payload),
            action=action,
            source=source,
            confidence=float(replay.confidence),
            reason=replay.reason,
            payload=payload,
            avoided_tokens_estimate=int(replay.avoided_tokens_estimate),
            telemetry=self._telemetry(action, source, started),
        )
        final = self._seal_decision(decision) if seal_decision else decision
        self._record_trace(final.decision_id, "crystal_reuse_decision", final.to_dict())
        return final

    def _execute_local_cpu_decision(self, request: CrystalReuseRequest, started: float, *, seal_decision: bool) -> CrystalReuseDecision:
        payload = {"request": request.to_dict(), "reuse": None}
        decision = CrystalReuseDecision(
            decision_id=self._decision_id("execute_local_cpu", request, payload),
            action="execute_local_cpu",
            source="local_execution_gateway",
            confidence=0.0,
            reason="no_reusable_crystal_found",
            payload=payload,
            telemetry=self._telemetry("execute_local_cpu", "local_execution_gateway", started),
        )
        final = self._seal_decision(decision) if seal_decision else decision
        self._record_trace(final.decision_id, "crystal_reuse_decision", final.to_dict())
        return final

    def _evaluate_promotion(
        self,
        request: CrystalReuseRequest,
        response: str,
        *,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rules = []
        if isinstance(evidence, dict) and isinstance(evidence.get("local_eval_rules"), list):
            rules.extend(item for item in evidence["local_eval_rules"] if isinstance(item, dict))
        rules.extend([
            {"type": "max_length", "value": int((evidence or {}).get("max_response_chars") or 200000)},
            {"type": "no_secret_patterns"},
        ])
        return self.eval_gate.evaluate(request=request, response=response, rules=rules)

    def _record_trace(self, trace_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if self.trace_ledger is None:
            return
        try:
            self.trace_ledger.record(trace_id, event_type, payload)
        except Exception:
            return

    def _record_route_feedback(
        self,
        request: CrystalReuseRequest,
        *,
        route: str,
        engine: str,
        success: bool,
        tokens: int,
        evidence: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if self.route_optimizer is None:
            return None
        latency_ms = 0.0
        for key in ("latency_ms", "duration_ms", "elapsed_ms"):
            if key in evidence:
                try:
                    latency_ms = float(evidence.get(key) or 0.0)
                except (TypeError, ValueError):
                    latency_ms = 0.0
                break
        usage = evidence.get("usage") if isinstance(evidence.get("usage"), dict) else {}
        if not tokens:
            try:
                tokens = int(usage.get("total_tokens") or usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            except (TypeError, ValueError):
                tokens = 0
        teacher_engine = str(evidence.get("teacher_engine") or request.provider or "")
        runtime_engine = str(evidence.get("runtime_engine") or engine or route or request.preferred_engine or request.provider or "unknown")
        self.route_optimizer.record(
            task_class=request.task_class,
            runtime_engine=runtime_engine,
            model=request.model,
            success=bool(success),
            latency_ms=max(0.0, latency_ms),
            tokens=max(0, int(tokens)),
            teacher_engine=teacher_engine or None,
        )
        return {
            "beast_object_type": "local_route_optimizer_feedback",
            "version": CRYSTAL_GATEWAY_VERSION,
            "task_class": request.task_class,
            "engine_id": runtime_engine,
            "runtime_engine": runtime_engine,
            "teacher_engine": teacher_engine,
            "model": request.model,
            "success": bool(success),
            "latency_ms": round(max(0.0, latency_ms), 3),
            "tokens": max(0, int(tokens)),
        }

    @staticmethod
    def _legacy_export_aliases(
        decision: CrystalReuseDecision,
        request: Dict[str, Any],
        reuse_payload: Dict[str, Any],
        kv_block: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "lmcache": {
                "beast_object_type": "lmcache_reuse_manifest",
                "version": CRYSTAL_GATEWAY_VERSION,
                "decision_id": decision.decision_id,
                "cache_key": kv_block.get("block_id") or decision.decision_id if isinstance(kv_block, dict) else decision.decision_id,
                "reuse_allowed": decision.action == "reuse_kv_prefill",
            },
            "gptcache": {
                "beast_object_type": "gptcache_semantic_record",
                "version": CRYSTAL_GATEWAY_VERSION,
                "decision_id": decision.decision_id,
                "prompt_hash": request.get("prompt_hash"),
                "cache_hit": decision.action in {"reuse_answer", "reuse_semantic_credit"},
                "confidence": decision.confidence,
                "response": reuse_payload.get("answer") or reuse_payload.get("response") if isinstance(reuse_payload, dict) else None,
            },
            "litellm": {
                "beast_object_type": "litellm_crystal_metadata",
                "version": CRYSTAL_GATEWAY_VERSION,
                "metadata": {
                    "beast_crystal_decision_id": decision.decision_id,
                    "beast_crystal_action": decision.action,
                    "beast_crystal_source": decision.source,
                    "beast_crystal_avoided_tokens": decision.avoided_tokens_estimate,
                    "beast_governance_layer": "BEAST",
                    "cloud_used": False,
                },
            },
            "openllmetry": {
                "name": "beast.crystal_reuse",
                "kind": "internal",
                "attributes": {
                    "beast.crystal.action": decision.action,
                    "beast.crystal.source": decision.source,
                    "beast.crystal.confidence": decision.confidence,
                },
            },
            "langfuse": {
                "type": "GENERATION",
                "name": "BEAST crystal reuse",
                "metadata": {"decision_id": decision.decision_id, "local_only": True},
                "scores": [{"name": "crystal_reuse_confidence", "value": float(decision.confidence)}],
            },
            "tensorzero": {
                "beast_object_type": "tensorzero_feedback_candidate",
                "version": CRYSTAL_GATEWAY_VERSION,
                "episode_id": decision.decision_id,
                "metric_name": "beast_crystal_reuse",
                "value": float(decision.confidence),
            },
            "promptfoo": {
                "type": "local_eval_gate",
                "value": "output.reuse.confidence >= 0.800",
                "metadata": {
                    "beast_object_type": "promptfoo_crystal_reuse_assertion",
                    "decision_id": decision.decision_id,
                },
            },
        }

    def _seal_decision(self, decision: CrystalReuseDecision) -> CrystalReuseDecision:
        payload = decision.to_dict()
        payload.pop("residue_seal", None)
        seal = self.seal.sign(payload, purpose="crystal_reuse_decision")
        return CrystalReuseDecision(
            decision_id=decision.decision_id,
            action=decision.action,
            source=decision.source,
            confidence=decision.confidence,
            reason=decision.reason,
            payload=decision.payload,
            avoided_tokens_estimate=decision.avoided_tokens_estimate,
            telemetry=decision.telemetry,
            residue_seal=seal,
        )

    @staticmethod
    def _decision_id(action: str, request: CrystalReuseRequest, payload: Dict[str, Any]) -> str:
        raw = json.dumps({"action": action, "request": request.to_dict(), "payload": payload}, sort_keys=True)
        return "crystal_reuse_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _telemetry(action: str, source: str, started: float) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_reuse_telemetry",
            "version": CRYSTAL_GATEWAY_VERSION,
            "action": action,
            "source": source,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _impact_hash(request: CrystalReuseRequest, response: str) -> str:
        payload = {
            "task_class": request.task_class,
            "repo_fingerprint": request.repo_fingerprint,
            "policy_version": request.policy_version,
            "model": request.model,
            "prompt_hash": request.prompt_hash,
            "response_hash": "sha256:" + hashlib.sha256(response.encode("utf-8")).hexdigest(),
        }
        return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_task_class(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]+", "_", str(value).strip().lower()).strip("_")
    return normalized or "chat_completion"
