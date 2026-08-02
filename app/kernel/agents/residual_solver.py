"""Interception boundary for bounded Ollama residual inference."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from app.kernel.compute.perceive import EdgeKIR
from app.kernel.agents.patch_compiler import contribution_accounting
from app.kernel.compute.forge_kv_coordinator import ForgeKVCoordinator
from app.kernel.compute.crystal_tongue import compile_crystal_tongue
from app.kernel.compute.crystal_ir import compile_crystal_ir
from app.kernel.compute.crystal_tongue_codebook import shared_codebook
from app.kernel.compute.crystal_tongue_c3 import compile_control_packet
from app.kernel.compute.capability_retriever import VerifiedCapabilityRetriever
from app.kernel.compute.deterministic_decomposer import decomposition_contract


class ResidualSolverBoundary:
    """Permit Ollama only after the compute interceptor approves the route."""

    def __init__(self, *, provider: Any, interceptor: Any, forge_kv: Optional[ForgeKVCoordinator] = None, retriever: Optional[VerifiedCapabilityRetriever] = None) -> None:
        self.provider = provider
        self.interceptor = interceptor
        self.forge_kv = forge_kv
        self.retriever = retriever

    async def solve(
        self,
        payload: Dict[str, Any],
        *,
        task_class: str = "code_change",
        model: Optional[str] = None,
        run_id: str = "",
    ) -> Dict[str, Any]:
        raw_unresolved = payload.get("unresolved_fields")
        unresolved = [str(item) for item in (raw_unresolved if raw_unresolved is not None else ["new"])]
        if not unresolved and payload.get("model_call_required") is False:
            resolved = payload.get("resolved_fields") if isinstance(payload.get("resolved_fields"), dict) else {}
            if not resolved:
                template = payload.get("action_template") if isinstance(payload.get("action_template"), dict) else {}
                if template.get("new") not in {None, "", "<UNRESOLVED>"}:
                    resolved = {"new": template["new"]}
            if not resolved:
                return {"status": "reuse_refused", "route": "crystal", "provider_called": False, "reason": "verified crystal had no resolved fields", "unresolved_fields": []}
            return {
                "status": "reused",
                "route": "crystal",
                "provider_called": False,
                "fields": resolved,
                "unresolved_fields": [],
                "model_packet": "",
                "model_packet_digest": "",
                "contribution_accounting": contribution_accounting({}, [], list(resolved)),
                "receipt": {"receipt_id": "crystal-reuse", "status": "reused", "route": "crystal", "provider_execution_requested": False},
            }
        model_input = self._build_model_input(payload, unresolved, retriever=self.retriever)
        forge_route = None
        if self.forge_kv is not None:
            forge_route = self.forge_kv.prepare(
                model_input,
                model=model or getattr(self.provider, "model", "ollama-residual"),
                tokenizer=str(payload.get("tokenizer") or "ollama-native"),
                exact_crystal=False,
                larger_model_available=bool(payload.get("larger_model_available")),
            )
            model_input["forge_kv_route"] = forge_route.to_dict()
        model_packet = json.dumps(model_input, sort_keys=True, separators=(",", ":"), default=str)
        model_packet_digest = "sha256:" + hashlib.sha256(model_packet.encode()).hexdigest()
        request = EdgeKIR(
            messages=[
                {"role": "system", "content": "You are a bounded residual solver. Return only declared fields."},
                {"role": "user", "content": model_packet},
            ],
            model=model or getattr(self.provider, "model", "ollama-residual"),
            max_tokens=96,
            temperature=0.0,
            tools=[],
            metadata={
                "task_class": task_class,
                "beast_task_class": task_class,
                "residual_fields": unresolved,
                "run_id": run_id,
                "residual_solver": True,
                "model_packet_digest": model_packet_digest,
                "forge_kv_route": forge_route.to_dict() if forge_route else None,
            },
        )
        interception = self.interceptor.begin(request, "ollama")
        route = self.interceptor.execution_route(interception)
        if route != "provider":
            return {
                "status": "not_permitted",
                "route": route,
                "reason": interception.gate.reason,
                "provider_called": False,
                "unresolved_fields": unresolved,
                "model_packet": model_packet,
                "model_packet_digest": model_packet_digest,
                "forge_kv_route": forge_route.to_dict() if forge_route else None,
            }
        try:
            result = await self.provider.solve_residual(model_input, run={"run_id": run_id, "task_class": task_class})
        except Exception as exc:
            self.interceptor.complete(
                interception,
                status="provider_error",
                provider_execution_requested=True,
                error_type=type(exc).__name__,
            )
            raise
        receipt = self.interceptor.complete(
            interception,
            response={"usage": result.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})},
            status="completed" if result.get("status") in {"solved", "residual_generated"} else "refused",
            provider_execution_requested=True,
        )
        return {
            **result,
            "verification_status": result.get("verification_status") or ("verified" if result.get("status") == "solved" else "pending"),
            "route": "provider",
            "provider_called": True,
            "model_packet": model_packet,
            "model_packet_digest": model_packet_digest,
            "forge_kv_route": forge_route.to_dict() if forge_route else None,
            "contribution_accounting": contribution_accounting(
                payload.get("action_ir") if isinstance(payload.get("action_ir"), dict) else {},
                unresolved,
                list((result.get("fields") or {}).keys()) if isinstance(result, dict) else [],
            ),
            "receipt": receipt.to_dict(),
        }

    @staticmethod
    def _build_model_input(payload: Dict[str, Any], unresolved: list[str], *, retriever: Optional[VerifiedCapabilityRetriever] = None) -> Dict[str, Any]:
        """Strip governance and preparation metadata before the model call."""
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        failure = str(payload.get("failure_summary") or payload.get("failure") or payload.get("verifier_failure") or "")
        contract = payload.get("residual_contract") if isinstance(payload.get("residual_contract"), dict) else {}
        current = str(contract.get("old") or payload.get("current_body") or payload.get("current_code") or "")
        guidance = payload.get("verified_patterns") or payload.get("crystal_guidance") or []
        if not guidance and retriever is not None:
            guidance = retriever.patterns_for_model(payload, limit=3)
        if not isinstance(guidance, list):
            guidance = [guidance]
        tongue = compile_crystal_tongue({
            **payload,
            "target": target,
            "current_body": current,
            "unresolved_fields": unresolved,
        })
        control_packet = compile_control_packet({
            **payload,
            "target": target,
            "current_body": current,
            "unresolved_fields": unresolved,
        })
        decomposition = decomposition_contract({
            **payload,
            "target": target,
            "current_body": current,
            "unresolved_fields": unresolved,
        })
        crystal_ir = None
        if isinstance(payload.get("crystal_ir"), dict):
            crystal_ir = compile_crystal_ir(payload["crystal_ir"])
        codebook, codebook_added, codebook_reused = shared_codebook(
            tongue,
            tokenizer_id=str(payload.get("tokenizer_id") or "fallback"),
        )
        protocol = str(payload.get("crystal_protocol") or "dual").lower()
        if protocol not in {"c1", "c2", "dual"}:
            raise ValueError("crystal_protocol must be c1, c2, or dual")
        result = {
            "task": "fill_replace_exact_new_value",
            "file": str(target.get("path") or payload.get("path") or ""),
            "symbol": str(target.get("symbol") or payload.get("symbol") or ""),
            "current_body": current[-2400:],
            "residual_contract": contract or {
                "field": "new",
                "scope": "exact_snippet",
                "value_schema": {"type": "nonempty_source_fragment"},
            },
            "failure": failure[-1600:],
            "verified_patterns": [str(item)[:400] for item in guidance[:3]],
            "allowed_response": payload.get("allowed_output") if isinstance(payload.get("allowed_output"), dict) else {"new": "string"},
            "unresolved_fields": list(unresolved),
            "crystal_codebook_id": codebook.lexicon_id,
            "crystal_codebook_new_entries": codebook_added,
            "crystal_codebook_reused_entries": codebook_reused,
            "crystal_control_packet": control_packet.render_prompt(),
            "crystal_control_packet_ir": control_packet.to_dict(),
            "crystal_control_packet_digest": control_packet.digest,
            "decomposition": decomposition["subproblems"],
            "active_subproblem": decomposition["active_subproblem"],
            "decomposition_order": decomposition["execution_order"],
        }
        if crystal_ir is not None:
            result["crystal_ir"] = crystal_ir.to_dict()
            result["crystal_ir_digest"] = crystal_ir.digest()
            result["crystal_ir_authority"] = crystal_ir.model_authority
        if protocol in {"c1", "dual"}:
            result["crystal_tongue"] = tongue.encode()
            result["crystal_tongue_ir"] = tongue.to_dict()
        if protocol in {"c2", "dual"}:
            result["crystal_tongue_v2"] = codebook.encode(tongue)
            result["crystal_codebook_prefix"] = codebook.stable_prefix()
        return result
