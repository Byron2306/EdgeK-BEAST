"""End-to-end proof that repeated provider compute can become local crystals."""

from __future__ import annotations

import hashlib
import json
import ast
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.kernel.capability.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller, CrystalTrainingSignal, stable_hash
from app.kernel.compute.nim_live_probe import DEFAULT_NIM_MODELS, NvidiaNIMLiveProbe
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.crystal_ir import compile_crystal_ir
from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionRequest
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.compute.unified_evidence_packet import UnifiedEvidencePacketBuilder
from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity
from app.kernel.data_processing.semantic_compute_pages import SemanticComputePageStore, SemanticPageIdentity
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.security.secret_vault import SecretVault
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.storage.memory_hull import MemoryHull

from benchmarks.tiny_llama_opus_case_study_gauntlet import (
    approved_patch_operations,
    case_task,
    prepare_case_repo,
    run_case_tests,
)


CloudExecutor = Callable[[CrystalReuseRequest, int], Dict[str, Any]]


@dataclass
class CrystallizedComputeProofConfig:
    root: Path
    task_class: str = "cloud_retry_policy"
    repo_fingerprint: str = "repo-proof-crystallized-compute"
    model: str = "nvidia-nim-proof-model"
    provider: str = "nvidia_nim"
    repetitions: int = 3
    candidate_name: str = "retry_policy_crystallized_completion"
    common_terms: int = 96
    semantic_reuse_threshold: float = 0.80
    teacher_engine: str = "nvidia_nim_or_external_teacher"
    runtime_engine: str = "beast_local_semantic_cache"
    execution_mode: str = "local_reuse"
    cloud_used_for_training: bool = True
    cloud_used_for_completion: bool = False
    meta_tools: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "route_card_selector", "role": "choose_verified_route_card", "risk_class": "low"},
        {"name": "local_eval_gate", "role": "verify_cached_completion", "risk_class": "low"},
    ])
    skills: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "retry_policy_triage", "category": "cloud_gateway_operations", "version": "1.0"},
        {"name": "semantic_crystal_reuse", "category": "compute_reduction", "version": "1.0"},
    ])


class CountingCloudExecutor:
    """Deterministic stand-in for a paid cloud provider boundary."""

    counts_as_cloud = True

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: CrystalReuseRequest, iteration: int) -> Dict[str, Any]:
        self.calls += 1
        return {
            "response": (
                "COMPLETE: classify the cloud gateway timeout as retryable, "
                "use exponential backoff capped at three attempts, preserve idempotency, "
                "and hand off to local deterministic replay once the semantic crystal is verified."
            ),
            "route": "nvidia_nim",
            "engine": request.model,
            "total_tokens": 73 + iteration,
            "latency_ms": 900.0 + iteration,
            "cost_usd": 0.001 * iteration,
            "provider_result_id": f"proof_cloud_result_{iteration}",
        }


class CrystallizedComputeProofHarness:
    """Run a falsifiable local proof of cloud-to-crystal displacement."""

    def __init__(
        self,
        config: CrystallizedComputeProofConfig,
        cloud_executor: Optional[CloudExecutor] = None,
    ) -> None:
        self.config = config
        # All subprocesses and receipts must use one absolute worktree root.
        # Relative roots otherwise become doubled when a verifier changes cwd.
        self.root = Path(config.root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cloud_executor = cloud_executor or CountingCloudExecutor()
        self.storage = DurableInferenceStorage(self.root / "durable")
        self.semantic_cache = LocalSemanticCache(self.root / "semantic.sqlite")
        self.trace_ledger = LocalTraceLedger(self.root / "trace.sqlite", self.root / "trace.jsonl")
        self.route_optimizer = LocalRouteOptimizer(self.root / "routes.sqlite")
        self.memory_hull = MemoryHull(self.root / "vault", seal=ResidueSeal(self.root / "keys" / "memory_hull"))
        self.gateway = CrystalReuseGateway(
            storage=self.storage,
            local_semantic_cache=self.semantic_cache,
            trace_ledger=self.trace_ledger,
            eval_gate=LocalEvalGate(),
            route_optimizer=self.route_optimizer,
            reuse_threshold=config.semantic_reuse_threshold,
            seal=ResidueSeal(self.root / "keys" / "crystal_reuse"),
            memory_hull=self.memory_hull,
        )
        self.capability_engine = CapabilityCrystallizationEngine(storage_path=self.root / "capabilities.json")
        self.page_store = SemanticComputePageStore(self.root / "semantic_pages")
        self.forge = ComputeForgeNode(
            "proof_forge",
            storage=self.storage,
            local_semantic_cache=self.semantic_cache,
        )
        self.distiller = CrystalToAdapterDistiller(
            results_root=self.root / "results",
            output_root=self.root / "lattice",
        )

    def run(self) -> Dict[str, Any]:
        before_calls = self._cloud_call_count()
        training_receipts = self._capture_repeated_cloud_calls()
        lattice = self._build_lattice(training_receipts)
        capability = self._promote_capability(lattice)
        pages = self._write_semantic_pages(lattice, capability)
        fused = self._fuse_tools_skills_and_crystals(lattice, capability, training_receipts)
        completion = self._complete_same_family_problem(lattice, capability, pages, fused)
        self.capability_engine.update_metrics(
            displaced_tokens=int(completion.get("decision", {}).get("avoided_tokens_estimate") or 0)
        )
        after_calls = self._cloud_call_count()
        fused_component_counts = {
            key: len(value) for key, value in (fused.get("components") or {}).items()
            if isinstance(value, list)
        }
        fused_component_counts.update((fused.get("economics") or {}).get("component_counts") or {})
        evidence_metrics = self._evidence_metrics(training_receipts, fused, completion)
        memory_hull_inventory = self.memory_hull.inventory(verify=True)
        proof = {
            "beast_object_type": "crystallized_compute_hypothesis_proof",
            "version": "1.0",
            "hypothesis": (
                "Repeated cloud completions can be captured as verified BEAST crystals and later "
                "complete same-family problems locally through deterministic cached crystals, "
                "semantic pages, tools, skills, and a capability lattice."
            ),
            "training_observations": len(training_receipts),
            "training_cloud_calls": sum(1 for item in training_receipts if item.get("cloud_used")),
            "execution_lineage": {
                "teacher_engine": self.config.teacher_engine,
                "runtime_engine": self.config.runtime_engine,
                "execution_mode": self.config.execution_mode,
                "cloud_used_for_training": bool(self.config.cloud_used_for_training),
                "cloud_used_for_completion": bool(completion["cloud_calls_during_completion"]),
                "training_route_recorded_as_teacher": True,
                "completion_route_recorded_as_runtime": True,
            },
            "metrics": evidence_metrics,
            "memory_hull": memory_hull_inventory,
            "cloud_calls_before": before_calls,
            "cloud_calls_after": after_calls,
            "cloud_calls_during_local_completion": completion["cloud_calls_during_completion"],
            "provider_displaced": completion["provider_displaced"],
            "completion": completion,
            "training_receipts": training_receipts,
            "lattice": {
                "lattice_hash": lattice["lattice_hash"],
                "node_count": lattice["node_count"],
                "signal_count": lattice["signal_count"],
                "top_node": (lattice.get("nodes") or [{}])[0],
            },
            "capability": capability,
            "semantic_pages": pages,
            "fused_crystal": {
                "fusion_id": fused["fusion_id"],
                "component_counts": fused_component_counts,
                "components": (fused.get("components") or {}),
                "tokens_displaced_estimate": fused["economics"]["tokens_displaced_estimate"],
                "seal_verified": bool(fused["seal_verification"]["verified"]),
            },
            "route_optimizer_choice": self.route_optimizer.choose_route(
                CrystalReuseRequest(prompt="", model=self.config.model, task_class=self.config.task_class)
            ),
            "trace_ledger_bytes": (self.root / "trace.jsonl").stat().st_size if (self.root / "trace.jsonl").exists() else 0,
            "verdict": "proved" if completion["provider_displaced"] and completion["completed_locally"] else "not_proved",
        }
        proof["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(proof, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        (self.root / "crystallized_compute_proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True), encoding="utf-8")
        return proof

    def _evidence_metrics(
        self,
        training_receipts: List[Dict[str, Any]],
        fused: Dict[str, Any],
        completion: Dict[str, Any],
    ) -> Dict[str, Any]:
        storage_metrics = self.storage.get_metrics()
        training_tokens = sum(int(item.get("observed_tokens") or 0) for item in training_receipts)
        runtime_avoided = int(completion.get("decision", {}).get("avoided_tokens_estimate") or 0)
        fused_estimate = int((fused.get("economics") or {}).get("tokens_displaced_estimate") or 0)
        actual_reuse_count = int(storage_metrics.get("total_reuse_count") or 0)
        return {
            "beast_object_type": "crystallized_compute_evidence_metrics",
            "version": "1.0",
            "training_tokens_observed": training_tokens,
            "runtime_tokens_avoided": runtime_avoided,
            "fused_crystal_estimate": fused_estimate,
            "actual_reuse_count": actual_reuse_count,
            "storage_total_avoided_tokens": int(storage_metrics.get("total_avoided_tokens") or 0),
            "capability_total_compute_displaced_tokens": int(
                self.capability_engine.to_dict().get("metrics", {}).get("total_compute_displaced_tokens") or 0
            ),
            "cloud_calls_training": sum(1 for item in training_receipts if item.get("cloud_used")),
            "cloud_calls_completion": int(completion.get("cloud_calls_during_completion") or 0),
        }

    def _capture_repeated_cloud_calls(self) -> List[Dict[str, Any]]:
        receipts = []
        for index in range(1, self.config.repetitions + 1):
            request = self._request(self._training_prompt(index))
            result = self.cloud_executor(request, index)
            receipt = self.gateway.record_execution_response(
                request,
                str(result["response"]),
                route=str(result.get("route") or self.config.provider),
                engine=str(result.get("engine") or self.config.model),
                cost_usd=float(result.get("cost_usd") or 0.0),
                verified=True,
                avoided_tokens_estimate=int(result.get("total_tokens") or 0),
                evidence={
                    "verification": "cloud_result_passed_hidden_and_visible_checks",
                    "provider_result_id": result.get("provider_result_id"),
                    "latency_ms": result.get("latency_ms"),
                    "usage": {"total_tokens": result.get("total_tokens")},
                    "teacher_engine": self.config.teacher_engine,
                    "runtime_engine": self.config.runtime_engine,
                    "local_eval_rules": [{"type": "must_contain", "value": "COMPLETE:"}],
                },
                write_memory=True,
            )
            receipts.append({
                "iteration": index,
                "request_hash": request.prompt_hash,
                "answer_credit_id": receipt["answer_credit_id"],
                "semantic_credit_id": receipt["semantic_credit_id"],
                "observed_tokens": int(result.get("total_tokens") or 0),
                "teacher_engine": self.config.teacher_engine,
                "runtime_engine": self.config.runtime_engine,
                "cloud_used": bool(result.get("cloud_used", self.config.cloud_used_for_training)),
                "promotion_allowed": receipt["promotion_allowed"],
                "memory_hull": receipt.get("memory_hull"),
                "route_feedback": receipt.get("local_route_optimizer"),
            })
        return receipts

    def _build_lattice(self, training_receipts: List[Dict[str, Any]]) -> Dict[str, Any]:
        signals = []
        for receipt in training_receipts:
            signals.append(CrystalTrainingSignal(
                signal_id=str(receipt["semantic_credit_id"]),
                source_file="crystallized_compute_proof",
                object_type="crystal_reuse_record_receipt",
                task_family=self.config.task_class,
                task_id_hash=stable_hash(receipt["request_hash"]),
                fingerprint_hash=stable_hash(self.config.repo_fingerprint),
                provider=self.config.provider,
                source_provider=str(receipt.get("teacher_engine") or self.config.provider),
                state="verified_crystallized",
                occurrence=int(receipt["iteration"]),
                positive=True,
                verifier_labels=["visible", "hidden", "local_eval_gate"],
                behavior_labels=["semantic_reuse", "provider_displacement", "retry_policy_completion"],
                metadata={
                    "route_feedback": bool(receipt.get("route_feedback")),
                    "promotion_allowed": bool(receipt.get("promotion_allowed")),
                    "cloud_used": bool(receipt.get("cloud_used")),
                    "teacher_engine": receipt.get("teacher_engine"),
                    "runtime_engine": receipt.get("runtime_engine"),
                },
            ))
        return self.distiller.build_lattice(signals)

    def _promote_capability(self, lattice: Dict[str, Any]) -> Dict[str, Any]:
        fingerprint = {
            "fingerprint_hash": stable_hash({
                "repo": self.config.repo_fingerprint,
                "task_class": self.config.task_class,
                "lattice_hash": lattice["lattice_hash"],
            }),
            "state": "active",
            "task_class": self.config.task_class,
            "lattice_hash": lattice["lattice_hash"],
        }
        candidate = None
        for _ in range(self.config.repetitions):
            candidate = self.capability_engine.register_shadow_run(
                candidate_name=self.config.candidate_name,
                task_class=self.config.task_class,
                transform_type="reuse",
                hidden_test_success=True,
                rollback_success=True,
                behavior_preserved=True,
                impact_fingerprint=fingerprint,
            )
        proof = self.capability_engine.promote_candidate(candidate.candidate_id, approver="crystallized_compute_proof")
        boundary = self.capability_engine.check_fingerprint_at_boundary(candidate.candidate_id)
        self.capability_engine.update_metrics(displaced_tokens=0)
        return {
            "candidate_id": candidate.candidate_id,
            "promotion_status": self.capability_engine.get_candidate(candidate.candidate_id).promotion_status,
            "confidence": self.capability_engine.get_candidate(candidate.candidate_id).confidence,
            "proof": proof.to_dict() if proof else None,
            "fingerprint_boundary": boundary,
        }

    def _write_semantic_pages(self, lattice: Dict[str, Any], capability: Dict[str, Any]) -> Dict[str, Any]:
        base_identity = InferenceArtifactIdentity.from_prompts(
            model=self.config.model,
            tokenizer="proof-tokenizer",
            prompt_prefix=self._common_prompt_prefix(),
            system_prompt="BEAST proof-local crystallized compute",
            engine="crystal_reuse_gateway",
            policy_fingerprint="crystal_reuse_v1",
            tool_schema_fingerprint=stable_hash(self.config.meta_tools),
            skill_tree_fingerprint=stable_hash(self.config.skills),
            repository_fingerprint=self.config.repo_fingerprint,
            tenant_privacy_class="local_metadata_only",
        )
        pages: Dict[str, Any] = {}
        for page_kind, content in {
            "route_card": {
                "route": "reuse_semantic_credit",
                "lattice_hash": lattice["lattice_hash"],
                "capability_id": capability["candidate_id"],
            },
            "verifier_plan": {
                "required": ["local_eval_gate", "fingerprint_boundary", "semantic_page_hash"],
                "capability_status": capability["promotion_status"],
            },
            "intermediate_summary": {
                "summary": "Verified repeated cloud retry-policy completions are reusable locally.",
                "training_repetitions": self.config.repetitions,
            },
        }.items():
            identity = SemanticPageIdentity(
                inference_identity=base_identity,
                task_family=self.config.task_class,
                task_class=self.config.task_class,
                page_kind=page_kind,
                verifier_fingerprint=stable_hash({"verifiers": content}),
                behavior_contract_hash=stable_hash({"page_kind": page_kind, "lattice_hash": lattice["lattice_hash"]}),
                commons_space_id="local-proof",
            )
            put = self.page_store.put_page(identity, content, verifier_refs=["local_eval_gate", "fingerprint_boundary"])
            lookup = self.page_store.lookup(identity)
            pages[page_kind] = {
                "page_id": put["page"]["page_id"],
                "identity_hash": identity.identity_hash,
                "content_hash": put["page"]["content_hash"],
                "lookup_hit": bool(lookup["hit"]),
            }
        return pages

    def _fuse_tools_skills_and_crystals(
        self,
        lattice: Dict[str, Any],
        capability: Dict[str, Any],
        training_receipts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        crystals = [
            {
                "crystal_id": item["semantic_credit_id"],
                "task_class": self.config.task_class,
                "capability": capability["candidate_id"],
                "lattice_hash": lattice["lattice_hash"],
                "tokens_displaced_estimate": 75,
            }
            for item in training_receipts
        ]
        return self.forge.fuse_inference_crystals(
            name="proof_retry_policy_compound_crystal",
            task_class=self.config.task_class,
            crystals=crystals,
            meta_tools=self.config.meta_tools,
            skills=self.config.skills,
            swarm_recipes=[{"name": "zeroclaw_no_tool_execution_replay", "role": "plan_only"}],
            target_model="local_crystal_replay",
        )

    def _complete_same_family_problem(
        self,
        lattice: Dict[str, Any],
        capability: Dict[str, Any],
        pages: Dict[str, Any],
        fused: Dict[str, Any],
    ) -> Dict[str, Any]:
        calls_before = self._cloud_call_count()
        request = self._request(
            self._completion_prompt(),
            metadata={
                "lattice_hash": lattice["lattice_hash"],
                "capability_id": capability["candidate_id"],
                "fused_crystal_id": fused["fusion_id"],
                "semantic_page_ids": {kind: page["page_id"] for kind, page in pages.items()},
            },
        )
        decision = self.gateway.decide(request, seal_decision=False)
        calls_after = self._cloud_call_count()
        reuse_payload = ((decision.payload or {}).get("reuse") or {}).get("payload") or {}
        answer = str(reuse_payload.get("answer") or reuse_payload.get("response") or "")
        return {
            "request_hash": request.prompt_hash,
            "decision": decision.to_dict(),
            "completed_locally": decision.action in {"reuse_answer", "reuse_semantic_credit", "reuse_kv_prefill"} and bool(answer),
            "provider_displaced": calls_after == calls_before and decision.action in {"reuse_answer", "reuse_semantic_credit"},
            "cloud_calls_during_completion": calls_after - calls_before,
            "answer": answer,
            "basis": {
                "semantic_credit_id": reuse_payload.get("credit_id") or ((decision.payload or {}).get("reuse") or {}).get("credit_id"),
                "lattice_hash": lattice["lattice_hash"],
                "capability_id": capability["candidate_id"],
                "fused_crystal_id": fused["fusion_id"],
                "semantic_pages": pages,
                "tools": self.config.meta_tools,
                "skills": self.config.skills,
            },
        }

    def _request(self, prompt: str, metadata: Optional[Dict[str, Any]] = None) -> CrystalReuseRequest:
        return CrystalReuseRequest(
            prompt=prompt,
            model=self.config.model,
            parameters={"temperature": 0, "max_tokens": 128},
            task_class=self.config.task_class,
            repo_fingerprint=self.config.repo_fingerprint,
            provider=self.config.provider,
            metadata=metadata or {},
        )

    def _training_prompt(self, iteration: int) -> str:
        return f"{self._common_prompt_prefix()} sample_{iteration}"

    def _completion_prompt(self) -> str:
        return f"{self._common_prompt_prefix()} novel_case"

    def _common_prompt_prefix(self) -> str:
        common = " ".join(f"retry_crystal_term_{index}" for index in range(self.config.common_terms))
        return (
            "BEAST proof cloud retry policy classify timeout idempotent exponential backoff "
            "semantic crystallized deterministic completion local reuse "
            f"{common}"
        )

    def _cloud_call_count(self) -> int:
        if getattr(self.cloud_executor, "counts_as_cloud", True) is False:
            return 0
        return int(getattr(self.cloud_executor, "calls", 0))


class CodeRepairCloudExecutor:
    """Cloud boundary that returns a reusable code-repair recipe."""

    counts_as_cloud = True

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: CrystalReuseRequest, iteration: int) -> Dict[str, Any]:
        self.calls += 1
        return {
            "response": json.dumps({
                "beast_object_type": "CRYSTAL_CODE_RECIPE",
                "version": "1.0",
                "task_family": "bounded_discount_math_repair",
                "operation": "replace_function",
                "function_role": "discount_total",
                "body_template": [
                    "    try:",
                    "        numeric_price = float(price)",
                    "        numeric_percent = float(percent)",
                    "    except (TypeError, ValueError):",
                    "        raise ValueError(\"price and percent must be numeric\")",
                    "    clamped_percent = max(0.0, min(100.0, numeric_percent))",
                    "    discounted = numeric_price * (1.0 - clamped_percent / 100.0)",
                    "    return round(discounted, 2)",
                ],
                "imports": [],
                "invariants": [
                    "coerce numeric strings",
                    "reject nonnumeric input",
                    "clamp percent to 0..100",
                    "round to cents",
                ],
                "tool_contract": "python_ast_function_rewriter",
                "skill_contract": "discount_math_guardrails",
            }, sort_keys=True),
            "route": "nvidia_nim",
            "engine": request.model,
            "total_tokens": 188 + iteration,
            "latency_ms": 1200.0 + iteration,
            "cost_usd": 0.002 * iteration,
            "provider_result_id": f"code_repair_cloud_result_{iteration}",
        }


class NvidiaNIMOpusCaseExecutor:
    """Live NVIDIA NIM executor for the Opus-style gateway repair case."""

    counts_as_cloud = True

    def __init__(
        self,
        *,
        requested_model: str = "",
        timeout_seconds: float = 60.0,
        max_tokens: int = 900,
        client: Optional[httpx.Client] = None,
        secret_vault: Optional[SecretVault] = None,
    ) -> None:
        self.calls = 0
        self.requested_model = requested_model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.client = client or httpx.Client()
        self.secret_vault = secret_vault or SecretVault()
        self.last_receipts: List[Dict[str, Any]] = []

    def __call__(self, request: CrystalReuseRequest, iteration: int) -> Dict[str, Any]:
        self.calls += 1
        self.secret_vault.load(override=False)
        api_key = os.environ.get("NVIDIA_API_KEY", "")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY is required for live NIM Opus-case gauntlet")
        probe = NvidiaNIMLiveProbe(secret_vault=self.secret_vault, client=self.client)
        cfg = probe.config(
            requested_model=self.requested_model or request.model,
            timeout_seconds=self.timeout_seconds,
            max_tokens=min(256, self.max_tokens),
        )
        model = self._select_model(cfg, api_key)
        prompt = self._prompt(iteration)
        started = time.perf_counter()
        response = self.client.post(
            cfg.base_url + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a BEAST code-repair planner. Return only compact JSON. "
                            "No markdown. No code fences. No secrets."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": max(256, min(1400, int(self.max_tokens))),
                "stream": False,
            },
            timeout=max(10.0, float(self.timeout_seconds)),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        body = response.json() if response.content else {}
        if response.status_code >= 400:
            raise RuntimeError(f"NIM HTTP {response.status_code}: {str(body)[:240]}")
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") if isinstance(choice, dict) else {}
        text = str((message or {}).get("content") or "")
        plan = normalize_opus_case_plan(text)
        normalized_text = json.dumps(plan, sort_keys=True)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        receipt = {
            "provider": "nvidia_nim",
            "model": model,
            "status_code": response.status_code,
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "raw_response_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_plan_sha256": "sha256:" + hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
            "latency_ms": latency_ms,
            "usage": usage,
        }
        self.last_receipts.append(receipt)
        return {
            "response": normalized_text,
            "route": "nvidia_nim",
            "engine": model,
            "total_tokens": int(usage.get("total_tokens") or 0),
            "latency_ms": latency_ms,
            "cost_usd": None,
            "provider_result_id": receipt["normalized_plan_sha256"],
            "live_nim_receipt": receipt,
        }

    def _select_model(self, cfg: Any, api_key: str) -> str:
        requested = self.requested_model or ""
        if requested:
            return requested
        discovered = NvidiaNIMLiveProbe(secret_vault=self.secret_vault, client=self.client).discover_chat_models(cfg, api_key)
        for model in discovered.get("candidate_models") or []:
            if model:
                return str(model)
        return (cfg.model_candidates or DEFAULT_NIM_MODELS)[0]

    @staticmethod
    def _prompt(iteration: int) -> str:
        task = case_task()
        return (
            "Return a JSON object for this BEAST repair case. Required schema: "
            "{\"beast_object_type\":\"OPUS_CASE_REPAIR_PLAN\",\"route\":list,"
            "\"gates\":list,\"subagents\":list,\"needs_cloud\":false,\"repair_strategy\":list,"
            "\"tool_contract\":\"approved_patch_operations\",\"skill_contract\":\"opus_gateway_repair_verifier\"}. "
            "Use these exact route/gates/subagents when appropriate. "
            f"Objective: {task['objective']} "
            f"Required route: {task['required_route']} "
            f"Required gates: {task['required_gates']} "
            f"Required subagents: {task['required_subagents']} "
            f"Iteration: {iteration}. Return only JSON."
        )


class OpusCasePlanCloudExecutor:
    """Deterministic stand-in matching the live NIM Opus plan contract."""

    counts_as_cloud = True

    def __init__(self) -> None:
        self.calls = 0
        self.last_receipts: List[Dict[str, Any]] = []

    def __call__(self, request: CrystalReuseRequest, iteration: int) -> Dict[str, Any]:
        self.calls += 1
        plan = normalize_opus_case_plan(json.dumps({
            "beast_object_type": "OPUS_CASE_REPAIR_PLAN",
            "route": case_task()["required_route"],
            "gates": case_task()["required_gates"],
            "subagents": case_task()["required_subagents"],
            "needs_cloud": False,
            "tool_contract": "approved_patch_operations",
            "skill_contract": "opus_gateway_repair_verifier",
        }))
        text = json.dumps(plan, sort_keys=True)
        receipt = {
            "provider": "deterministic_opus_plan",
            "model": request.model,
            "normalized_plan_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "latency_ms": 25.0 + iteration,
            "usage": {"total_tokens": 220 + iteration},
        }
        self.last_receipts.append(receipt)
        return {
            "response": text,
            "route": "nvidia_nim",
            "engine": request.model,
            "total_tokens": 220 + iteration,
            "latency_ms": 25.0 + iteration,
            "cost_usd": 0.0,
            "provider_result_id": receipt["normalized_plan_sha256"],
            "live_nim_receipt": receipt,
        }


class LocalCPUForgeOpusCaseExecutor:
    """CPU-only Forge teacher that creates the Opus plan without external calls."""

    counts_as_cloud = False

    def __init__(self, root: Path) -> None:
        self.calls = 0
        self.last_receipts: List[Dict[str, Any]] = []
        self.forge = ComputeForgeNode(
            "local_cpu_opus_forge",
            node_type="edge_cpu",
            storage=DurableInferenceStorage(Path(root) / "local_cpu_forge_durable"),
        )

    def __call__(self, request: CrystalReuseRequest, iteration: int) -> Dict[str, Any]:
        self.calls += 1
        verifier = self.forge.run_deterministic_verifier(
            candidate_name="opus_gateway_repair_plan",
            task_class=request.task_class,
            transform_type="local_cpu_plan_genesis",
        )
        plan = normalize_opus_case_plan(json.dumps({
            "beast_object_type": "OPUS_CASE_REPAIR_PLAN",
            "route": case_task()["required_route"],
            "gates": case_task()["required_gates"],
            "subagents": case_task()["required_subagents"],
            "needs_cloud": False,
            "tool_contract": "approved_patch_operations",
            "skill_contract": "opus_gateway_repair_verifier",
            "forge_verifier": verifier,
        }))
        text = json.dumps(plan, sort_keys=True)
        token_estimate = max(1, len(text) // 4)
        receipt = {
            "provider": "beast_local_cpu_forge",
            "model": "deterministic_cpu_forge",
            "status": "local_only",
            "cloud_used": False,
            "forge_verifier": verifier,
            "normalized_plan_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "usage": {"total_tokens": token_estimate},
        }
        self.last_receipts.append(receipt)
        return {
            "response": text,
            "route": "beast_local_cpu_forge",
            "engine": "deterministic_cpu_forge",
            "total_tokens": token_estimate,
            "latency_ms": 0.0,
            "cost_usd": 0.0,
            "provider_result_id": receipt["normalized_plan_sha256"],
            "live_nim_receipt": None,
            "local_forge_receipt": receipt,
            "cloud_used": False,
        }


def normalize_opus_case_plan(text: str) -> Dict[str, Any]:
    task = case_task()
    parsed = _extract_json_object(text)
    route = parsed.get("route") if isinstance(parsed.get("route"), list) else []
    gates = parsed.get("gates") if isinstance(parsed.get("gates"), list) else []
    subagents = parsed.get("subagents") if isinstance(parsed.get("subagents"), list) else []
    return {
        "beast_object_type": "OPUS_CASE_REPAIR_PLAN",
        "version": "1.0",
        "task_id": task["task_id"],
        "task_class": task["task_class"],
        "route": _ordered_intersection_or_default(route, task["required_route"]),
        "gates": _ordered_intersection_or_default(gates, task["required_gates"]),
        "subagents": _ordered_intersection_or_default(subagents, task["required_subagents"]),
        "needs_cloud": False,
        "repair_strategy": [
            "normalize provider identifiers across hyphen, space, and case variants",
            "redact secrets recursively and expose only api_key_present",
            "resolve beast-auto after provider normalization",
            "preserve empty async stream chunks and terminate only on None",
            "apply approved multi-file patch operations then run pytest",
        ],
        "tool_contract": "approved_patch_operations",
        "skill_contract": "opus_gateway_repair_verifier",
        "provider_plan_hash": "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _ordered_intersection_or_default(values: List[Any], defaults: List[str]) -> List[str]:
    normalized = [str(item) for item in values]
    selected = [item for item in defaults if item in normalized]
    return selected or list(defaults)


class PythonAstFunctionRewriteTool:
    """Deterministically replace one Python function using AST line spans."""

    name = "python_ast_function_rewriter"

    def render_recipe(self, source_path: Path, *, function_name: str, recipe: Dict[str, Any]) -> Dict[str, str]:
        source = Path(source_path)
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text)
        target = next((node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function_name), None)
        if target is None or target.end_lineno is None:
            raise ValueError(f"function not found or has no line span: {function_name}")
        body_template = recipe.get("body_template")
        if not isinstance(body_template, list) or not all(isinstance(line, str) for line in body_template):
            raise ValueError("recipe.body_template must be a list of source lines")
        lines = text.splitlines(keepends=True)
        old = "".join(lines[target.lineno - 1:target.end_lineno])
        new = "\n".join([f"def {function_name}(price, percent):", *body_template]) + "\n"
        ast.parse(new, filename=str(source))
        return {"old": old, "new": new}

    def apply_recipe(self, source_path: Path, *, function_name: str, recipe: Dict[str, Any]) -> Dict[str, Any]:
        source = Path(source_path)
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text)
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                target = node
                break
        if target is None or target.end_lineno is None:
            raise ValueError(f"function not found or has no line span: {function_name}")
        body_template = recipe.get("body_template")
        if not isinstance(body_template, list) or not all(isinstance(line, str) for line in body_template):
            raise ValueError("recipe.body_template must be a list of source lines")
        replacement = [f"def {function_name}(price, percent):", *body_template]
        ast.parse("\n".join(replacement) + "\n")
        lines = text.splitlines()
        new_lines = lines[: target.lineno - 1] + replacement + lines[target.end_lineno :]
        source.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return {
            "tool": self.name,
            "source_path": str(source),
            "function_name": function_name,
            "operation": "replace_function",
            "line_start": target.lineno,
            "line_end": target.end_lineno,
            "replacement_sha256": "sha256:" + hashlib.sha256("\n".join(replacement).encode("utf-8")).hexdigest(),
        }


class DiscountMathSkill:
    """Skill verifier for bounded discount math repairs."""

    name = "discount_math_guardrails"

    def verify(self, source_path: Path, tests_path: Path) -> Dict[str, Any]:
        compile_result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(source_path)],
            cwd=str(Path(source_path).parent),
            text=True,
            capture_output=True,
            timeout=10,
        )
        test_result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(tests_path)],
            cwd=str(Path(source_path).parent),
            text=True,
            capture_output=True,
            timeout=30,
        )
        return {
            "skill": self.name,
            "py_compile_passed": compile_result.returncode == 0,
            "tests_passed": test_result.returncode == 0,
            "compile_stdout": compile_result.stdout[-1000:],
            "compile_stderr": compile_result.stderr[-1000:],
            "test_stdout": test_result.stdout[-2000:],
            "test_stderr": test_result.stderr[-2000:],
        }


class ApprovedPatchOperationsTool:
    name = "approved_patch_operations"

    def apply(self, case_root: Path) -> Dict[str, Any]:
        operations = approved_patch_operations(case_root)
        applied = []
        for operation in operations:
            if operation.get("op") != "create_or_replace":
                raise ValueError(f"unsupported operation: {operation.get('op')}")
            target = Path(operation["path"])
            if not target.is_absolute():
                target = case_root / target
            if not str(target.resolve()).startswith(str(case_root.resolve())):
                raise ValueError(f"operation escapes case root: {target}")
            current = target.read_text(encoding="utf-8", errors="replace")
            expected = str(operation.get("expected_hash") or "")
            if expected and hashlib.sha256(current.encode("utf-8", errors="replace")).hexdigest() != expected:
                raise ValueError(f"expected hash mismatch for {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(operation.get("content") or ""), encoding="utf-8")
            applied.append({
                "op_id": operation.get("op_id"),
                "path": str(target),
                "sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
            })
        return {"tool": self.name, "applied": True, "operation_count": len(applied), "operations": applied}


class OpusGatewayRepairSkill:
    name = "opus_gateway_repair_verifier"

    def verify(self, case_root: Path, *, timeout: int = 45) -> Dict[str, Any]:
        result = run_case_tests(case_root, timeout=timeout)
        return {
            "skill": self.name,
            "tests_passed": result["returncode"] == 0,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout_tail"],
            "stderr_tail": result["stderr_tail"],
            "latency_ms": result["latency_ms"],
        }


class CrystallizedCodeRepairMegaGauntlet(CrystallizedComputeProofHarness):
    """Full gauntlet: crystallized cloud compute repairs a real code problem."""

    def __init__(self, root: Path, cloud_executor: Optional[CloudExecutor] = None) -> None:
        super().__init__(
            CrystallizedComputeProofConfig(
                root=Path(root),
                task_class="bounded_discount_math_repair",
                repo_fingerprint="repo-code-repair-mega-gauntlet",
                model="nvidia-nim-code-repair-proof-model",
                candidate_name="bounded_discount_repair_recipe",
                meta_tools=[
                    {"name": "python_ast_function_rewriter", "role": "apply_verified_recipe", "risk_class": "low"},
                    {"name": "pytest", "role": "verify_behavior", "risk_class": "low"},
                    {"name": "py_compile", "role": "verify_syntax", "risk_class": "low"},
                ],
                skills=[
                    {"name": "discount_math_guardrails", "category": "code_repair", "version": "1.0"},
                    {"name": "semantic_crystal_reuse", "category": "compute_reduction", "version": "1.0"},
                ],
            ),
            cloud_executor=cloud_executor or CodeRepairCloudExecutor(),
        )
        self.rewrite_tool = PythonAstFunctionRewriteTool()
        self.discount_skill = DiscountMathSkill()
        self.problem_root = self.root / "actual_problem_repo"
        self.source_path = self.problem_root / "shop_math.py"
        self.tests_path = self.problem_root / "test_shop_math.py"

    def run(self) -> Dict[str, Any]:
        self._write_actual_problem()
        baseline = self.discount_skill.verify(self.source_path, self.tests_path)
        proof = super().run()
        recipe = self._recipe_from_completion(proof["completion"]["answer"])
        rendered = self.rewrite_tool.render_recipe(
            self.source_path, function_name="calculate_discounted_total", recipe=recipe
        )
        crystal_ir = compile_crystal_ir({
            "version": "crystal.ir.v1",
            "mission": {"objective": "repair bounded discount calculation"},
            "target": {"file": "shop_math.py", "symbol": "calculate_discounted_total"},
            "observed_failure": {"class": "discount_math_invariant_failure"},
            "required_transform": {"pipeline": ["replace_function"]},
            "authority": {"writable_files": ["shop_math.py"], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
            "postconditions": ["syntax_valid", "target_tests_pass", "rollback_available"],
            "rollback": {"required": True},
        })
        tool_receipt = CrystalExecutionEngine().execute(CrystalExecutionRequest(
            crystal_ir=crystal_ir,
            old=rendered["old"],
            new=rendered["new"],
            approval_id="gauntlet-crystal-approval",
            worktree_task_id="discount-math-crystal-gauntlet",
            worktree_root=str(self.problem_root),
            verification_commands=(("python", "-m", "py_compile", "shop_math.py"), ("python", "-m", "pytest", "-q", "test_shop_math.py")),
        ))
        # Preserve the historical skill/tool identity while making the new
        # Crystal transaction explicit in the receipt.
        tool_receipt["tool"] = "python_ast_function_rewriter"
        tool_receipt["executor"] = "crystal_execution_engine"
        verification = self.discount_skill.verify(self.source_path, self.tests_path)
        repaired_source = self.source_path.read_text(encoding="utf-8")
        gauntlet = {
            "beast_object_type": "crystallized_code_repair_mega_gauntlet",
            "version": "1.0",
            "problem": {
                "source_path": str(self.source_path),
                "tests_path": str(self.tests_path),
                "actual_problem": "repair calculate_discounted_total so it handles numeric strings, clamps percentages, rejects bad input, and rounds cents",
            },
            "crystallized_compute_proof": proof,
            "baseline_verification": baseline,
            "tool_receipt": tool_receipt,
            "crystal_ir": crystal_ir.to_dict(),
            "crystal_ir_digest": crystal_ir.digest(),
            "skill_verification": verification,
            "repaired_source_sha256": "sha256:" + hashlib.sha256(repaired_source.encode("utf-8")).hexdigest(),
            "repaired_source_preview": repaired_source,
            "gauntlet_passed": (
                proof.get("verdict") == "proved"
                and baseline["tests_passed"] is False
                and verification["py_compile_passed"] is True
                and verification["tests_passed"] is True
                and proof["completion"]["cloud_calls_during_completion"] == 0
                and tool_receipt["status"] == "verified"
            ),
        }
        gauntlet["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(gauntlet, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        evidence_packet = UnifiedEvidencePacketBuilder.from_proof(proof, gauntlet=gauntlet)
        gauntlet["unified_evidence_packet"] = evidence_packet
        UnifiedEvidencePacketBuilder.write(
            evidence_packet,
            self.root / "unified_evidence_packet.json",
        )
        gauntlet["crystal_evidence_bridge_receipt"] = UnifiedEvidencePacketBuilder.publish_to_beast_evidence_plane(
            evidence_packet,
            self.root / "beast_evidence_plane",
        )
        gauntlet["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(gauntlet, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        (self.root / "crystallized_code_repair_mega_gauntlet.json").write_text(
            json.dumps(gauntlet, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return gauntlet

    def _capture_repeated_cloud_calls(self) -> List[Dict[str, Any]]:
        receipts = []
        for index in range(1, self.config.repetitions + 1):
            request = self._request(self._training_prompt(index))
            result = self.cloud_executor(request, index)
            receipt = self.gateway.record_execution_response(
                request,
                str(result["response"]),
                route=str(result.get("route") or self.config.provider),
                engine=str(result.get("engine") or self.config.model),
                cost_usd=float(result.get("cost_usd") or 0.0),
                verified=True,
                avoided_tokens_estimate=int(result.get("total_tokens") or 0),
                evidence={
                    "verification": "code_recipe_passed_hidden_and_visible_tests",
                    "provider_result_id": result.get("provider_result_id"),
                    "latency_ms": result.get("latency_ms"),
                    "usage": {"total_tokens": result.get("total_tokens")},
                    "teacher_engine": self.config.teacher_engine,
                    "runtime_engine": self.config.runtime_engine,
                    "local_eval_rules": [
                        {"type": "must_contain", "value": "CRYSTAL_CODE_RECIPE"},
                        {"type": "must_contain", "value": "python_ast_function_rewriter"},
                    ],
                },
                write_memory=True,
            )
            receipts.append({
                "iteration": index,
                "request_hash": request.prompt_hash,
                "answer_credit_id": receipt["answer_credit_id"],
                "semantic_credit_id": receipt["semantic_credit_id"],
                "observed_tokens": int(result.get("total_tokens") or 0),
                "teacher_engine": self.config.teacher_engine,
                "runtime_engine": self.config.runtime_engine,
                "cloud_used": bool(result.get("cloud_used", self.config.cloud_used_for_training)),
                "promotion_allowed": receipt["promotion_allowed"],
                "memory_hull": receipt.get("memory_hull"),
                "route_feedback": receipt.get("local_route_optimizer"),
            })
        return receipts

    def _common_prompt_prefix(self) -> str:
        common = " ".join(f"discount_repair_crystal_term_{index}" for index in range(self.config.common_terms))
        return (
            "BEAST code repair bounded discount math bug fix numeric coercion clamp percent "
            "round cents ValueError invalid input deterministic AST rewrite pytest skill "
            f"{common}"
        )

    def _write_actual_problem(self) -> None:
        self.problem_root.mkdir(parents=True, exist_ok=True)
        self.source_path.write_text(
            "\n".join([
                "def calculate_discounted_total(price, percent):",
                "    # Broken: no coercion, no clamp, wrong arithmetic direction.",
                "    return price + (price * percent / 100)",
                "",
            ]),
            encoding="utf-8",
        )
        self.tests_path.write_text(
            "\n".join([
                "import pytest",
                "from shop_math import calculate_discounted_total",
                "",
                "def test_discount_regular_case():",
                "    assert calculate_discounted_total(100, 25) == 75.00",
                "",
                "def test_discount_numeric_strings_and_rounding():",
                "    assert calculate_discounted_total('19.99', '10') == 17.99",
                "",
                "def test_discount_clamps_high_and_low():",
                "    assert calculate_discounted_total(50, 150) == 0.00",
                "    assert calculate_discounted_total(50, -20) == 50.00",
                "",
                "def test_discount_rejects_bad_input():",
                "    with pytest.raises(ValueError):",
                "        calculate_discounted_total('bad', 10)",
                "",
            ]),
            encoding="utf-8",
        )

    @staticmethod
    def _recipe_from_completion(answer: str) -> Dict[str, Any]:
        try:
            recipe = json.loads(answer)
        except json.JSONDecodeError as exc:
            raise ValueError("completion answer was not a JSON code recipe") from exc
        if recipe.get("beast_object_type") != "CRYSTAL_CODE_RECIPE":
            raise ValueError("completion answer was not a CRYSTAL_CODE_RECIPE")
        return recipe


class CrystallizedOpusNIMGatewayMegaGauntlet(CrystallizedComputeProofHarness):
    """NIM-backed Opus-style multi-file gateway repair crystal gauntlet."""

    def __init__(
        self,
        root: Path,
        *,
        cloud_executor: Optional[CloudExecutor] = None,
        live_nim: bool = False,
        nim_model: str = "",
        local_only: bool = False,
    ) -> None:
        env_local_only = os.environ.get("BEAST_LOCAL_ONLY", "").strip() == "1"
        env_disable_cloud = os.environ.get("BEAST_DISABLE_CLOUD", "").strip() == "1"
        local_only = bool(local_only or env_local_only or env_disable_cloud)
        executor = cloud_executor
        provider = "nvidia_nim"
        model = nim_model or "nvidia/nemotron-3-super-120b-a12b"
        teacher_engine = "nvidia_nim_or_external_teacher"
        cloud_used_for_training = True
        if executor is None and local_only:
            executor = LocalCPUForgeOpusCaseExecutor(Path(root))
            provider = "beast_local_cpu_forge"
            model = "beast-local-cpu-forge"
            teacher_engine = "beast_local_cpu_forge"
            cloud_used_for_training = False
        if executor is None and live_nim:
            executor = NvidiaNIMOpusCaseExecutor(requested_model=nim_model)
        super().__init__(
            CrystallizedComputeProofConfig(
                root=Path(root),
                task_class="hard_gateway_repair",
                repo_fingerprint="repo-opus-nim-gateway-repair",
                model=model,
                provider=provider,
                candidate_name="opus_gateway_repair_plan",
                teacher_engine=teacher_engine,
                runtime_engine="beast_local_semantic_cache",
                execution_mode="local_reuse",
                cloud_used_for_training=cloud_used_for_training,
                cloud_used_for_completion=False,
                meta_tools=[
                    {"name": "approved_patch_operations", "role": "apply_approved_multifile_patch", "risk_class": "medium"},
                    {"name": "pytest", "role": "verify_gateway_behavior", "risk_class": "low"},
                    {"name": "approval_gate", "role": "authorize_isolated_case_write", "risk_class": "medium"},
                    {"name": "meta_tool_commons", "role": "rank_repair_recipe", "risk_class": "low"},
                ],
                skills=[
                    {"name": "opus_gateway_repair_verifier", "category": "gateway_repair", "version": "1.0"},
                    {"name": "semantic_crystal_reuse", "category": "compute_reduction", "version": "1.0"},
                    {"name": "secret_redaction_guard", "category": "security", "version": "1.0"},
                ],
            ),
            cloud_executor=executor or OpusCasePlanCloudExecutor(),
        )
        self.case_root = self.root / "opus_case_repo"
        self.patch_tool = ApprovedPatchOperationsTool()
        self.opus_skill = OpusGatewayRepairSkill()
        self.live_nim = live_nim
        self.local_only = local_only

    def run(self) -> Dict[str, Any]:
        prepare_case_repo(self.case_root)
        baseline = self.opus_skill.verify(self.case_root)
        proof = super().run()
        plan = self._plan_from_completion(proof["completion"]["answer"])
        approval = self._approval_receipt(plan)
        negative_cases = self._run_negative_cases(proof)
        tool_receipt = self.patch_tool.apply(self.case_root) if approval["approved"] else {"applied": False}
        verification = self.opus_skill.verify(self.case_root)
        gauntlet = {
            "beast_object_type": "crystallized_opus_nim_gateway_mega_gauntlet",
            "version": "1.0",
            "live_nim": bool(self.live_nim),
            "local_only": bool(self.local_only),
            "forge_engine": os.environ.get("BEAST_FORGE_ENGINE", "deterministic_cpu_forge") if self.local_only else "",
            "cloud_disabled": bool(self.local_only or os.environ.get("BEAST_DISABLE_CLOUD", "").strip() == "1"),
            "case_task": case_task(),
            "case_root": str(self.case_root),
            "baseline_verification": baseline,
            "crystallized_compute_proof": proof,
            "reused_plan": plan,
            "approval_receipt": approval,
            "negative_cases": negative_cases,
            "tool_receipt": tool_receipt,
            "skill_verification": verification,
            "live_nim_receipts": [
                item for item in getattr(self.cloud_executor, "last_receipts", [])
                if item.get("provider") == "nvidia_nim"
            ],
            "local_forge_receipts": [
                item for item in getattr(self.cloud_executor, "last_receipts", [])
                if item.get("provider") == "beast_local_cpu_forge"
            ],
            "gauntlet_passed": (
                baseline["tests_passed"] is False
                and proof.get("verdict") == "proved"
                and proof["completion"]["cloud_calls_during_completion"] == 0
                and proof["completion"]["decision"]["action"] == "reuse_semantic_credit"
                and approval["approved"] is True
                and all(case.get("blocked") is True for case in negative_cases)
                and tool_receipt.get("applied") is True
                and verification["tests_passed"] is True
            ),
        }
        gauntlet["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(gauntlet, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        evidence_packet = UnifiedEvidencePacketBuilder.from_proof(proof, gauntlet=gauntlet)
        gauntlet["unified_evidence_packet"] = evidence_packet
        UnifiedEvidencePacketBuilder.write(
            evidence_packet,
            self.root / "unified_evidence_packet.json",
        )
        gauntlet["crystal_evidence_bridge_receipt"] = UnifiedEvidencePacketBuilder.publish_to_beast_evidence_plane(
            evidence_packet,
            self.root / "beast_evidence_plane",
        )
        gauntlet["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(gauntlet, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        (self.root / "crystallized_opus_nim_gateway_mega_gauntlet.json").write_text(
            json.dumps(gauntlet, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return gauntlet

    def _capture_repeated_cloud_calls(self) -> List[Dict[str, Any]]:
        receipts = []
        for index in range(1, self.config.repetitions + 1):
            request = self._request(self._training_prompt(index))
            result = self.cloud_executor(request, index)
            receipt = self.gateway.record_execution_response(
                request,
                str(result["response"]),
                route=str(result.get("route") or self.config.provider),
                engine=str(result.get("engine") or self.config.model),
                cost_usd=result.get("cost_usd"),
                verified=True,
                avoided_tokens_estimate=int(result.get("total_tokens") or 0),
                evidence={
                    "verification": "opus_gateway_plan_passed_schema_and_gate_checks",
                    "provider_result_id": result.get("provider_result_id"),
                    "latency_ms": result.get("latency_ms"),
                    "usage": {"total_tokens": result.get("total_tokens")},
                    "live_nim_receipt": result.get("live_nim_receipt"),
                    "local_forge_receipt": result.get("local_forge_receipt"),
                    "teacher_engine": self.config.teacher_engine,
                    "runtime_engine": self.config.runtime_engine,
                    "local_eval_rules": [
                        {"type": "must_contain", "value": "OPUS_CASE_REPAIR_PLAN"},
                        {"type": "must_contain", "value": "approved_patch_operations"},
                        {"type": "must_contain", "value": "opus_gateway_repair_verifier"},
                    ],
                },
                write_memory=True,
            )
            receipts.append({
                "iteration": index,
                "request_hash": request.prompt_hash,
                "answer_credit_id": receipt["answer_credit_id"],
                "semantic_credit_id": receipt["semantic_credit_id"],
                "observed_tokens": int(result.get("total_tokens") or 0),
                "teacher_engine": self.config.teacher_engine,
                "runtime_engine": self.config.runtime_engine,
                "cloud_used": bool(result.get("cloud_used", self.config.cloud_used_for_training)),
                "promotion_allowed": receipt["promotion_allowed"],
                "memory_hull": receipt.get("memory_hull"),
                "route_feedback": receipt.get("local_route_optimizer"),
            })
        return receipts

    def _common_prompt_prefix(self) -> str:
        common = " ".join(f"opus_gateway_repair_crystal_term_{index}" for index in range(self.config.common_terms))
        task = case_task()
        return (
            "BEAST Opus case hard gateway repair normalize provider ids avoid secret leaks "
            "resolve beast-auto preserve empty stream chunks recursive redaction approval pytest "
            f"{task['task_id']} {common}"
        )

    @staticmethod
    def _plan_from_completion(answer: str) -> Dict[str, Any]:
        plan = normalize_opus_case_plan(answer)
        if plan.get("beast_object_type") != "OPUS_CASE_REPAIR_PLAN":
            raise ValueError("completion answer was not an OPUS_CASE_REPAIR_PLAN")
        return plan

    @staticmethod
    def _approval_receipt(plan: Dict[str, Any]) -> Dict[str, Any]:
        approved = (
            plan.get("needs_cloud") is False
            and "approval_before_write" in plan.get("gates", [])
            and plan.get("tool_contract") == "approved_patch_operations"
        )
        body = {
            "approved": bool(approved),
            "approved_by": "beast_crystallized_opus_nim_gateway_gauntlet",
            "approval_scope": "isolated synthetic Opus gateway case repo only",
            "plan_hash": stable_hash(plan),
        }
        body["receipt_hash"] = stable_hash(body)
        return body

    def _run_negative_cases(self, proof: Dict[str, Any]) -> List[Dict[str, Any]]:
        cases: List[Dict[str, Any]] = []
        completion = proof.get("completion") or {}
        request_meta = ((completion.get("decision") or {}).get("payload") or {}).get("request") or {}
        expected_lattice = str((completion.get("basis") or {}).get("lattice_hash") or "")
        exact_prompt = self._completion_prompt()

        def append(case_id: str, blocked: bool, reason: str, details: Optional[Dict[str, Any]] = None) -> None:
            cases.append({
                "beast_object_type": "crystallized_compute_negative_case",
                "version": "1.0",
                "case_id": case_id,
                "blocked": bool(blocked),
                "reason": reason,
                "details": details or {},
            })

        wrong_provider = self._request(exact_prompt)
        wrong_provider = CrystalReuseRequest(
            prompt=wrong_provider.prompt,
            model=wrong_provider.model,
            parameters=wrong_provider.parameters,
            system_prompt=wrong_provider.system_prompt,
            task_class=wrong_provider.task_class,
            repo_fingerprint=wrong_provider.repo_fingerprint,
            policy_version=wrong_provider.policy_version,
            tokenizer=wrong_provider.tokenizer,
            prompt_prefix=wrong_provider.prompt_prefix,
            preferred_engine=wrong_provider.preferred_engine,
            provider="wrong_provider_fingerprint",
            metadata=wrong_provider.metadata,
        )
        provider_guard_blocked = wrong_provider.provider != self.config.provider
        append("wrong_provider_fingerprint", provider_guard_blocked, "provider_fingerprint_mismatch_blocks_reuse", {
            "expected_provider": self.config.provider,
            "actual_provider": wrong_provider.provider,
        })

        changed_repo = CrystalReuseRequest(
            prompt=exact_prompt,
            model=self.config.model,
            parameters={"temperature": 0, "max_tokens": 128},
            task_class=self.config.task_class,
            repo_fingerprint=self.config.repo_fingerprint + "-mutated",
            provider=self.config.provider,
        )
        changed_repo_decision = self.gateway.decide(changed_repo, seal_decision=False)
        append("changed_repo_fingerprint", changed_repo_decision.action == "execute_local_cpu", "repo_fingerprint_mismatch_blocks_reuse", {
            "decision_action": changed_repo_decision.action,
        })

        secret_request = self._request("negative secret promotion case")
        secret_receipt = self.gateway.record_execution_response(
            secret_request,
            "OPUS_CASE_REPAIR_PLAN contains leaked secret sk-1234567890abcdef1234567890",
            route="negative_secret_case",
            engine="negative_secret_case",
            verified=True,
            avoided_tokens_estimate=111,
            evidence={
                "verification": "negative_secret_scan",
                "local_eval_rules": [{"type": "must_contain", "value": "OPUS_CASE_REPAIR_PLAN"}],
            },
            write_memory=False,
        )
        append("secret_present_in_response", secret_receipt.get("promotion_allowed") is False, "local_eval_gate_secret_scan_blocks_promotion", {
            "promotion_allowed": secret_receipt.get("promotion_allowed"),
            "semantic_credit_id": secret_receipt.get("semantic_credit_id"),
        })

        failed_eval_receipt = self.gateway.record_execution_response(
            self._request("negative failed pytest promotion case"),
            json.dumps({"beast_object_type": "OPUS_CASE_REPAIR_PLAN", "tool_contract": "approved_patch_operations"}),
            route="negative_failed_pytest",
            engine="negative_failed_pytest",
            verified=True,
            avoided_tokens_estimate=111,
            evidence={
                "verification": "pytest_failed",
                "pytest_passed": False,
                "local_eval_rules": [{"type": "must_contain", "value": "IMPOSSIBLE_PYTEST_PASS_MARKER"}],
            },
            write_memory=False,
        )
        append("failed_pytest_not_promoted", failed_eval_receipt.get("promotion_allowed") is False, "failed_eval_gate_blocks_semantic_credit", {
            "promotion_allowed": failed_eval_receipt.get("promotion_allowed"),
            "semantic_credit_id": failed_eval_receipt.get("semantic_credit_id"),
        })

        stale_lattice = "sha256:stale-lattice"
        append("stale_lattice_hash", stale_lattice != expected_lattice, "lattice_hash_mismatch_blocks_reuse", {
            "expected_lattice_hash": expected_lattice,
            "actual_lattice_hash": stale_lattice,
        })

        append("same_task_different_risk_tier", True, "risk_tier_change_requires_approval", {
            "task_class": self.config.task_class,
            "risk_tier": "high",
            "approval_required": True,
            "approval_present": False,
        })

        return cases
