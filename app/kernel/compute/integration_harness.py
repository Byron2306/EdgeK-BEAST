"""Thin BEAST integration harness for request-to-receipt flow."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.enterprise import EnterpriseManager
from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet
from app.kernel.security.agent_passport import AgentPassport, AgentPassportPolicy
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.memory_hull import MemoryHull


ProviderExecutor = Callable[[CrystalReuseRequest], Dict[str, Any] | str]
ProviderVerifier = Callable[[CrystalReuseRequest, Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class BeastHarnessRequest:
    prompt: str
    model: str
    caller: AgentPassport | Dict[str, Any] | str = field(default_factory=lambda: AgentPassport.local("proxy/gateway"))
    parameters: Dict[str, Any] = field(default_factory=dict)
    provider: str = "local"
    task_class: str = "chat_completion"
    repo_fingerprint: Optional[str] = None
    policy_version: str = "crystal_reuse_v1"
    system_prompt: str = ""
    tokenizer: str = ""
    prompt_prefix: str = ""
    preferred_engine: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    enterprise: Dict[str, Any] = field(default_factory=dict)
    projected_cost_usd: float = 0.0
    projected_tokens: int = 0
    target: str = "spiffe://beast.local/provider/local"
    action: str = "call"

    def crystal_request(self) -> CrystalReuseRequest:
        return CrystalReuseRequest(
            prompt=self.prompt,
            model=self.model,
            parameters=self.parameters,
            system_prompt=self.system_prompt,
            task_class=self.task_class,
            repo_fingerprint=self.repo_fingerprint,
            policy_version=self.policy_version,
            tokenizer=self.tokenizer,
            prompt_prefix=self.prompt_prefix,
            preferred_engine=self.preferred_engine,
            provider=self.provider,
            metadata=self.metadata,
        )


class BeastIntegrationHarness:
    """Orchestrate BEAST's production path without hiding any layer boundary."""

    def __init__(
        self,
        *,
        passport_policy: AgentPassportPolicy,
        crystal_gateway: CrystalReuseGateway,
        residue_seal: ResidueSeal,
        memory_hull: MemoryHull,
        enterprise_manager: EnterpriseManager,
        readiness: Optional[ProductionReadinessHardeningGauntlet] = None,
        provider_executor: Optional[ProviderExecutor] = None,
        provider_verifier: Optional[ProviderVerifier] = None,
        local_execution_gateway: Optional[Any] = None,
    ) -> None:
        self.passport_policy = passport_policy
        self.crystal_gateway = crystal_gateway
        self.residue_seal = residue_seal
        self.memory_hull = memory_hull
        self.enterprise_manager = enterprise_manager
        self.readiness = readiness or ProductionReadinessHardeningGauntlet()
        self.provider_executor = provider_executor or self._default_provider_executor
        self._provider_executor_overridden = provider_executor is not None
        self.provider_verifier = provider_verifier or self._default_provider_verifier
        self.local_execution_gateway = local_execution_gateway

    def run(self, request: BeastHarnessRequest) -> Dict[str, Any]:
        started = time.perf_counter()
        trace_id = str(request.metadata.get("trace_id") or self._trace_id(request))
        facts = {
            "quality_cascade": {"approved": bool(request.metadata.get("quality_cascade_approved", True))},
            "enterprise": request.enterprise,
        }
        passport = self.passport_policy.evaluate(caller=request.caller, target=request.target, action=request.action, facts=facts)
        if not passport.get("allowed"):
            raise PermissionError(f"BEAST integration harness denied: {passport.get('reason')}")

        enterprise_context = self._enterprise_context(request)
        budget = self._check_budget(enterprise_context, request)
        if budget and not budget.get("allowed", True):
            raise PermissionError(f"BEAST enterprise budget denied: {budget.get('reason')}")

        crystal_request = request.crystal_request()
        crystal_decision = self.crystal_gateway.decide(crystal_request)
        execution_result: Dict[str, Any] = {
            "called": False,
            "response": self._reused_response(crystal_decision.to_dict()),
            "status": "skipped_by_crystal_reuse",
        }
        verification: Dict[str, Any] = {
            "verified": True,
            "reason": "crystal_reuse_decision_reused_existing_artifact",
        }
        crystal_record: Optional[Dict[str, Any]] = None

        should_execute = crystal_decision.action in {"execute_local_cpu", "execute_litellm_cloud", "execute_provider"}
        if should_execute:
            execution_result = self._execute_provider(crystal_request)
            execution_result.setdefault("route", "local_cpu" if crystal_decision.action == "execute_local_cpu" else "litellm_cloud")
            execution_result.setdefault("cloud_used", crystal_decision.action == "execute_litellm_cloud")
            verification = self.provider_verifier(crystal_request, execution_result)
            crystal_record = self.crystal_gateway.record_execution_response(
                crystal_request,
                str(execution_result.get("response") or ""),
                route=str(execution_result.get("route") or "local_cpu"),
                engine=str(execution_result.get("engine_id") or execution_result.get("engine") or request.preferred_engine or "ollama"),
                cost_usd=execution_result.get("cost_usd"),
                verified=bool(verification.get("verified")),
                avoided_tokens_estimate=int(execution_result.get("total_tokens") or request.projected_tokens or 0),
                evidence={
                    "verification": verification,
                    "trace_id": trace_id,
                    "provider_result_id": execution_result.get("provider_result_id") or "",
                    "latency_ms": execution_result.get("latency_ms") or 0,
                    "usage": {
                        "total_tokens": execution_result.get("total_tokens") or (
                            int(execution_result.get("prompt_tokens") or 0) + int(execution_result.get("output_tokens") or 0)
                        ),
                        "prompt_tokens": execution_result.get("prompt_tokens") or 0,
                        "output_tokens": execution_result.get("output_tokens") or 0,
                    },
                },
                write_memory=True,
            )

        enterprise_receipts = self._record_enterprise(
            enterprise_context,
            request,
            trace_id=trace_id,
            crystal_decision=crystal_decision.to_dict(),
            provider_result=execution_result,
            verification=verification,
        )
        gate_receipt = self._readiness_gate_receipt(trace_id)

        unsigned = {
            "beast_object_type": "beast_thin_integration_harness_receipt",
            "version": "1.0",
            "trace_id": trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "passport": passport,
            "budget": budget,
            "crystal_reuse_decision": crystal_decision.to_dict(),
            "provider_result": self._redact_provider_result(execution_result),
            "execution_result": self._redact_provider_result(execution_result),
            "verification": verification,
            "crystal_record": crystal_record,
            "enterprise": enterprise_receipts,
            "readiness_gate": gate_receipt,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "flow": [
                "agent_passport_authorized",
                "crystal_reuse_decided",
                "local_execution_verified" if should_execute and crystal_decision.action == "execute_local_cpu" else "provider_result_verified" if should_execute else "execution_skipped_by_crystal_reuse",
                "residue_seal_signed",
                "memory_hull_written" if crystal_record else "memory_hull_not_rewritten_for_reuse",
                "enterprise_recorded" if enterprise_receipts else "enterprise_context_not_supplied",
                "readiness_gate_emitted",
            ],
        }
        unsigned["receipt_id"] = "beast_harness_" + hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        unsigned["residue_seal"] = self.residue_seal.sign(unsigned, purpose="beast_thin_integration_harness_receipt")
        return unsigned

    def _execute_provider(self, request: CrystalReuseRequest) -> Dict[str, Any]:
        if self._should_use_local_execution_gateway(request):
            result = self.local_execution_gateway.complete(request)
            result.setdefault("provider", request.provider or "local_cpu")
            result.setdefault("model", request.model)
            result.setdefault("cost_usd", 0.0)
            result.setdefault(
                "total_tokens",
                int(result.get("prompt_tokens") or 0) + int(result.get("output_tokens") or 0),
            )
            result.setdefault("status", "completed")
            result.setdefault("called", True)
            result.setdefault("provider_result_id", self._result_id(request, result))
            return result
        result = self.provider_executor(request)
        if isinstance(result, str):
            result = {"response": result}
        normalized = dict(result)
        normalized.setdefault("called", True)
        normalized.setdefault("provider", request.provider or request.model)
        normalized.setdefault("model", request.model)
        normalized.setdefault("status", "completed")
        normalized.setdefault("provider_result_id", self._result_id(request, normalized))
        return normalized

    def _should_use_local_execution_gateway(self, request: CrystalReuseRequest) -> bool:
        if self.local_execution_gateway is None or self._provider_executor_overridden:
            return False
        provider = (request.provider or "").lower()
        explicit_live = bool(request.metadata.get("execute_live_local") or request.metadata.get("use_local_execution_gateway"))
        return explicit_live or provider in {"local_cpu", "ollama", "llama_cpp"}

    def _check_budget(self, context: Dict[str, Any], request: BeastHarnessRequest) -> Optional[Dict[str, Any]]:
        if not context.get("team_id"):
            return None
        return self.enterprise_manager.check_team_budget(
            str(context["team_id"]),
            projected_requests=1,
            projected_cost_usd=float(request.projected_cost_usd),
        )

    def _record_enterprise(
        self,
        context: Dict[str, Any],
        request: BeastHarnessRequest,
        *,
        trace_id: str,
        crystal_decision: Dict[str, Any],
        provider_result: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        team_id = str(context.get("team_id") or "")
        if not team_id:
            return None
        user_id = str(context.get("user_id") or "")
        key_id = str(context.get("key_id") or "")
        cost = float(provider_result.get("cost_usd") or request.projected_cost_usd or 0.0)
        tokens = int(provider_result.get("total_tokens") or request.projected_tokens or 0)
        usage = self.enterprise_manager.record_team_usage(
            team_id=team_id,
            user_id=user_id,
            key_id=key_id,
            provider=str(provider_result.get("provider") or request.provider),
            model=request.model,
            request_count=1,
            estimated_cost_usd=cost,
            total_tokens=tokens,
        )
        event = self.enterprise_manager.record_observability_event(
            team_id=team_id,
            user_id=user_id,
            event_type="beast.integration_harness.request",
            severity="info" if verification.get("verified") else "warning",
            trace_id=trace_id,
            payload={
                "crystal_action": crystal_decision.get("action"),
                "crystal_decision_id": crystal_decision.get("decision_id"),
                "provider_called": bool(provider_result.get("called")),
                "verified": bool(verification.get("verified")),
            },
        )
        trace = self.enterprise_manager.store_encrypted_trace(
            team_id=team_id,
            user_id=user_id,
            trace_id=trace_id,
            trace={
                "trace_id": trace_id,
                "request": asdict(request),
                "crystal_reuse_decision": crystal_decision,
                "provider_result": self._redact_provider_result(provider_result),
                "verification": verification,
            },
            metadata={"beast_object_type": "beast_thin_integration_harness_trace"},
        )
        return {"usage": usage, "observability_event": event, "encrypted_trace": trace}

    def _readiness_gate_receipt(self, trace_id: str) -> Dict[str, Any]:
        gate = self.readiness.production_ops_gate()
        receipt = {
            "beast_object_type": "beast_thin_integration_harness_readiness_gate",
            "version": "1.0",
            "trace_id": trace_id,
            "gate": "production_ops",
            "status": gate.get("status"),
            "lab_status": gate.get("lab_status"),
            "checks": gate.get("checks") or {},
            "external_checks": gate.get("external_checks") or {},
            "claim_boundary": gate.get("claim_boundary"),
        }
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return receipt

    @staticmethod
    def _enterprise_context(request: BeastHarnessRequest) -> Dict[str, Any]:
        claims = getattr(request.caller, "claims", {}) if isinstance(request.caller, AgentPassport) else {}
        context = dict(claims.get("enterprise") or {}) if isinstance(claims.get("enterprise"), dict) else {}
        context.update(request.enterprise or {})
        return context

    @staticmethod
    def _default_provider_executor(request: CrystalReuseRequest) -> Dict[str, Any]:
        return {
            "response": f"BEAST local provider placeholder for {request.task_class}: {request.prompt[:120]}",
            "provider": request.provider or "local",
            "model": request.model,
            "cost_usd": 0.0,
            "total_tokens": max(1, len(request.prompt.split()) + 12),
            "status": "completed",
        }

    @staticmethod
    def _default_provider_verifier(request: CrystalReuseRequest, provider_result: Dict[str, Any]) -> Dict[str, Any]:
        response = str(provider_result.get("response") or "")
        return {
            "beast_object_type": "beast_provider_result_verification",
            "version": "1.0",
            "verified": bool(response.strip()),
            "reason": "non_empty_provider_response" if response.strip() else "empty_provider_response",
            "response_sha256": "sha256:" + hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "model": request.model,
            "provider": request.provider,
        }

    @staticmethod
    def _reused_response(decision: Dict[str, Any]) -> str:
        reuse = ((decision.get("payload") or {}).get("reuse") or {})
        payload = reuse.get("payload") if isinstance(reuse.get("payload"), dict) else {}
        return str(payload.get("response") or "")

    @staticmethod
    def _redact_provider_result(provider_result: Dict[str, Any]) -> Dict[str, Any]:
        redacted = dict(provider_result)
        for key in ("api_key", "authorization", "secret", "token"):
            if key in redacted:
                redacted[key] = "[redacted]"
        return redacted

    @staticmethod
    def _trace_id(request: BeastHarnessRequest) -> str:
        raw = json.dumps(
            {
                "prompt": request.prompt,
                "model": request.model,
                "provider": request.provider,
                "metadata": request.metadata,
                "at": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
            default=str,
        )
        return "trace_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _result_id(request: CrystalReuseRequest, provider_result: Dict[str, Any]) -> str:
        raw = json.dumps(
            {"request": request.to_dict(), "provider_result": provider_result},
            sort_keys=True,
            default=str,
        )
        return "provider_result_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
