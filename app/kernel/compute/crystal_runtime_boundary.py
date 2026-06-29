"""Crystal-first runtime boundary for provider execution paths."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseDecision, CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.crystal_credit_quarantine import CrystalCreditQuarantine
from app.kernel.compute.crystal_staleness_policy import (
    CrystalReusePolicySnapshot,
    CrystalRuntimeContext,
    CrystalStalenessPolicy,
)
from app.kernel.compute.proof_local_admission_bridge import ProofLocalAdmissionBridge
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.storage.memory_hull import MemoryHull


class CrystalRuntimeBoundary:
    """Ask BEAST crystallized runtime before any provider call."""

    def __init__(
        self,
        root: Optional[Path] = None,
        *,
        gateway: Optional[CrystalReuseGateway] = None,
        staleness_policy: Optional[CrystalStalenessPolicy] = None,
        proof_local_admission: Optional[ProofLocalAdmissionBridge] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        default_root = Path(__file__).resolve().parents[2] / "data" / "crystal_runtime"
        self.root = Path(root or os.environ.get("BEAST_CRYSTAL_RUNTIME_ROOT") or default_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.gateway = gateway or self._default_gateway(self.root)
        self.staleness_policy = staleness_policy or CrystalStalenessPolicy()
        self.proof_local_admission = proof_local_admission or ProofLocalAdmissionBridge()
        self.enabled = bool(int(os.environ.get("BEAST_CRYSTAL_RUNTIME_ENABLED", "1"))) if enabled is None else bool(enabled)

    @staticmethod
    def _default_gateway(root: Path) -> CrystalReuseGateway:
        storage = DurableInferenceStorage(root / "durable")
        semantic_cache = LocalSemanticCache(root / "semantic.sqlite")
        return CrystalReuseGateway(
            storage=storage,
            local_semantic_cache=semantic_cache,
            trace_ledger=LocalTraceLedger(root / "trace.sqlite", root / "trace.jsonl"),
            eval_gate=LocalEvalGate(),
            route_optimizer=LocalRouteOptimizer(root / "routes.sqlite"),
            memory_hull=MemoryHull(root / "vault"),
        )

    def request_from_ir(self, ir: Any, provider: str) -> CrystalReuseRequest:
        metadata = dict(getattr(ir, "metadata", None) or {})
        prompt = metadata.get("crystal_prompt")
        if not prompt:
            prompt = self._messages_to_prompt(getattr(ir, "messages", []) or [])
        parameters = {
            "temperature": getattr(ir, "temperature", None),
            "max_tokens": getattr(ir, "max_tokens", None),
        }
        parameters = {key: value for key, value in parameters.items() if value is not None}
        parameters.update(metadata.get("crystal_parameters") if isinstance(metadata.get("crystal_parameters"), dict) else {})
        return CrystalReuseRequest(
            prompt=str(prompt),
            model=str(getattr(ir, "model", "") or metadata.get("model") or ""),
            parameters=parameters,
            system_prompt=str(metadata.get("system_prompt") or ""),
            task_class=str(metadata.get("task_class") or "chat_completion"),
            repo_fingerprint=metadata.get("repo_fingerprint"),
            policy_version=str(metadata.get("policy_version") or "crystal_reuse_v1"),
            tokenizer=str(metadata.get("tokenizer") or ""),
            prompt_prefix=str(metadata.get("prompt_prefix") or ""),
            preferred_engine=metadata.get("preferred_engine"),
            provider=str(provider or metadata.get("provider") or ""),
            metadata=metadata,
        )

    def decide_for_ir(self, ir: Any, provider: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "should_execute_provider": True, "reason": "crystal_runtime_disabled"}
        request = self.request_from_ir(ir, provider)
        metadata = dict(getattr(ir, "metadata", None) or {})
        eligible = bool(
            metadata.get("crystal_runtime_enabled") is True
            or metadata.get("repo_fingerprint")
            or metadata.get("crystal_prompt")
        )
        if not eligible:
            return {
                "enabled": True,
                "eligible": False,
                "should_execute_provider": True,
                "request": None,
                "decision": None,
                "staleness": {},
                "reason": "crystal_runtime_not_eligible_without_repo_fingerprint_or_explicit_opt_in",
            }
        stale = self._staleness_from_metadata(request.metadata)
        if stale and not stale.get("reuse_allowed", False):
            quarantine = CrystalCreditQuarantine(
                self.gateway.storage,
                self.gateway.local_semantic_cache,
            ).quarantine_for_request(
                request,
                reason="staleness_policy_blocked_reuse",
                evidence=stale,
            )
            return {
                "enabled": True,
                "eligible": True,
                "should_execute_provider": True,
                "request": request,
                "staleness": stale,
                "quarantine": quarantine,
                "decision": None,
                "reason": "staleness_policy_blocked_reuse",
            }
        proof_local = self.proof_local_admission.evaluate(
            request,
            advertisements=metadata.get("proof_local_advertisements") if isinstance(metadata.get("proof_local_advertisements"), list) else [],
        )
        if not proof_local.get("reuse_allowed", False):
            quarantine = CrystalCreditQuarantine(
                self.gateway.storage,
                self.gateway.local_semantic_cache,
            ).quarantine_for_request(
                request,
                reason="proof_local_admission_blocked_reuse",
                evidence=proof_local,
            )
            return {
                "enabled": True,
                "eligible": True,
                "should_execute_provider": True,
                "request": request,
                "staleness": stale or {},
                "proof_local": proof_local,
                "quarantine": quarantine,
                "decision": None,
                "reason": "proof_local_admission_blocked_reuse",
            }
        decision = self.gateway.decide(request, seal_decision=False)
        return {
            "enabled": True,
            "eligible": True,
            "should_execute_provider": decision.action not in {"reuse_answer", "reuse_semantic_credit", "reuse_kv_prefill"},
            "request": request,
            "decision": decision,
            "staleness": stale or {},
            "proof_local": proof_local,
            "reason": decision.reason,
        }

    def response_from_decision(self, ir: Any, decision: CrystalReuseDecision, *, provider: str = "crystal_runtime") -> Dict[str, Any]:
        text = self._decision_text(decision)
        response = {
            "id": f"crystal-runtime-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}",
            "object": "chat.completion",
            "created": 1234567890,
            "model": str(getattr(ir, "model", "") or ""),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "edgek_provider": provider,
            "edgek_crystal_runtime": {
                "decision": decision.to_dict(),
                "provider_execution_requested": False,
            },
        }
        return response

    def harness_reuse_receipt(
        self,
        *,
        request: CrystalReuseRequest,
        decision: CrystalReuseDecision,
        proof_local: Optional[Dict[str, Any]] = None,
        staleness: Optional[Dict[str, Any]] = None,
        compute_receipt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        receipt = {
            "beast_object_type": "beast_crystal_runtime_harness_receipt",
            "version": "1.0",
            "request": request.to_dict(),
            "crystal_reuse_decision": decision.to_dict(),
            "proof_local": proof_local or {},
            "staleness": staleness or {},
            "compute_receipt": compute_receipt or {},
            "provider_result": {
                "called": False,
                "status": "skipped_by_crystal_reuse",
                "cloud_used": False,
            },
            "verification": {
                "verified": True,
                "reason": "crystal_runtime_reuse_with_prior_verification",
            },
            "flow": [
                "proof_local_admission_checked",
                "crystal_reuse_decided",
                "execution_skipped_by_crystal_reuse",
                "compute_receipt_recorded",
                "residue_seal_signed",
            ],
        }
        receipt["receipt_id"] = "crystal_runtime_harness_" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        receipt["residue_seal"] = self.gateway.seal.sign(receipt, purpose="beast_crystal_runtime_harness_receipt")
        return receipt

    def record_provider_result(
        self,
        request: CrystalReuseRequest,
        response: Dict[str, Any],
        *,
        route: str,
        engine: str,
        verified: bool,
        cost_usd: Optional[float] = None,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = self._response_text(response)
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        total_tokens = int(usage.get("total_tokens") or response.get("total_tokens") or 0)
        evidence_payload = {
            "runtime_engine": "beast_local_semantic_cache",
            "teacher_engine": engine,
            "usage": usage,
            **(evidence or {}),
        }
        return self.gateway.record_execution_response(
            request,
            text,
            route=route,
            engine=engine,
            cost_usd=cost_usd,
            verified=verified,
            avoided_tokens_estimate=total_tokens,
            evidence=evidence_payload,
            write_memory=True,
        )

    def _staleness_from_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        expected = metadata.get("expected_crystal_policy")
        actual = metadata.get("actual_runtime_context")
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return {}
        return self.staleness_policy.evaluate(
            CrystalReusePolicySnapshot(**{key: str(expected.get(key) or "") for key in CrystalReusePolicySnapshot.__dataclass_fields__}),
            CrystalRuntimeContext(
                **{
                    key: (bool(actual.get(key)) if key == "approval_present" else str(actual.get(key) or ""))
                    for key in CrystalRuntimeContext.__dataclass_fields__
                }
            ),
        )

    @staticmethod
    def _decision_text(decision: CrystalReuseDecision) -> str:
        reuse = ((decision.payload or {}).get("reuse") or {})
        payload = reuse.get("payload") if isinstance(reuse, dict) else {}
        if isinstance(payload, dict):
            return str(payload.get("answer") or payload.get("response") or payload)
        return str(payload or "")

    @staticmethod
    def _response_text(response: Dict[str, Any]) -> str:
        if "text" in response:
            return str(response.get("text") or "")
        choices = response.get("choices") if isinstance(response.get("choices"), list) else []
        if choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first.get("message"), dict) else {}
            if message.get("content") is not None:
                return str(message.get("content") or "")
        if "response" in response:
            return str(response.get("response") or "")
        return json.dumps(response, sort_keys=True, default=str)

    @staticmethod
    def _messages_to_prompt(messages: Any) -> str:
        if not isinstance(messages, list):
            return str(messages or "")
        return "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages if isinstance(item, dict))
