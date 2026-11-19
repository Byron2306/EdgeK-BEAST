"""Local Ollama swarm specialist runner for D9 ``local_specialist_adapter`` proposals.

Flow (default-off, ``BEAST_SWARM_SPECIALIST``): D9 proposal → Compute Governor spine ``admit`` (strict ADMIT) →
``OllamaSwarmRunner`` generates a *proposal* → Quality Cascade gate → Output Governor gate → verifiers. Any
refusal or failed gate discards the output, records negative evidence and lets the caller fall back to the
provider. The specialist never grants execution (IEI v0.9 §7.12.1 / Table 15: 0.80-0.95 proposes only).
"""

from __future__ import annotations
from app.kernel.compute import governed_egress as _egress  # closure-2026-11-16: governed egress shim

import inspect
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.kernel.governance.governor_spine import ADMIT, Episode, Proposal, cascade_admission_input

SPECIALIST_ENV = "BEAST_SWARM_SPECIALIST"
MODEL_ENV = "BEAST_SWARM_SPECIALIST_MODEL"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
BASE_MODEL_PREFERENCE = ("qwen3:4b", "granite3.3:2b", "granite3.2:2b")
MAX_REPAIR_RETRIES = 2
THINK_RE = re.compile(r"<think>.*?</think>", re.S)
Gate = Callable[[str, Any], "tuple[bool, str]"]


def specialist_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(SPECIALIST_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def operational_specialist_route(reason: str, model: str = "") -> dict[str, Any]:
    from app.kernel.compute.adaptive_router import RouteDecision, RouteKind

    return RouteDecision(
        route=RouteKind.LOCAL_SPECIALIST_ADAPTER, similarity=0.0, band="operational",
        specialist_ref=f"ollama://{model}" if model else "", reasons=(reason,),
    ).to_dict()


def _base_url(env: Mapping[str, str]) -> str:
    raw = str(env.get("BEAST_OLLAMA_BASE_URL") or env.get("OLLAMA_HOST") or DEFAULT_BASE_URL).strip()
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    return raw.rstrip("/")


class OllamaSwarmRunner:
    """Native Ollama runner (``/api/tags``, ``/api/generate``); no BEAST authority of its own."""

    def __init__(self, *, base_url: str | None = None, timeout: float = 120.0,
                 transport: httpx.AsyncBaseTransport | None = None, env: Mapping[str, str] | None = None,
                 trust_env: bool = True, local_models_only: bool = False):
        env = os.environ if env is None else env
        self.base_url = (base_url or _base_url(env)).rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport
        self.trust_env = trust_env
        self.local_models_only = local_models_only

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self.transport, trust_env=self.trust_env)

    async def installed_models(self) -> list[str]:
        async with self._client() as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            return [str(m["name"]) for m in models if m.get("name") and (
                not self.local_models_only or not (
                    m.get("remote_host") or m.get("remote_model")
                    or str(m["name"]).lower().endswith((":cloud", "-cloud"))
                )
            )]

    async def generate(self, *, model: str, system: str, prompt: str, max_tokens: int = 512,
                       format: Any = None) -> dict[str, Any]:  # noqa: A002 - Ollama's field name
        payload: dict[str, Any] = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.0,
                "top_k": 1,
                "seed": 42,
                "num_predict": int(max_tokens),
                "repeat_penalty": 1.0,
            }
        }
        if format is not None:  # Ollama structured output: "json" or a JSON schema (grammar-constrained decoding)
            payload["format"] = format
        if model.lower().startswith("qwen3"):
            payload["think"] = False
        started = time.monotonic()
        async with self._client() as client:
            response = await _egress.apost(client, "swarm_specialist", "/api/generate", json=payload)
            response.raise_for_status()
            body = response.json()
        text = THINK_RE.sub("", str(body.get("response") or "")).strip()
        return {"text": text, "model": model, "done_reason": str(body.get("done_reason") or ""),
                "usage": {"prompt_tokens": int(body.get("prompt_eval_count") or 0),
                          "completion_tokens": int(body.get("eval_count") or 0)},
                "latency_ms": round((time.monotonic() - started) * 1000.0, 3)}


def resolve_runner_model(model_ref: str, installed: Sequence[str], *,
                         env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Exact specialist model if installed; else an installed base model (recorded as a substitution)."""
    env = os.environ if env is None else env
    names = set(installed)
    wanted = str(model_ref or "").removeprefix("ollama://")
    for candidate in (wanted, f"{wanted}:latest"):
        if wanted and candidate in names:
            return candidate, "exact_specialist"
    preference = [str(env.get(MODEL_ENV) or "").strip(), *BASE_MODEL_PREFERENCE]
    for candidate in preference:
        if candidate and candidate in names:
            return candidate, "base_model_substitute"
    return "", "no_installed_model"


def _crystal_task_spec(ir: Any) -> tuple[str, str, dict[str, Any] | None]:
    """
    Extract a structured task specification from the IR for crystalline specialist execution.
    
    Returns (system_directive, task_specification_json, response_schema)
    """
    metadata = getattr(ir, "metadata", None) or {}
    messages = getattr(ir, "messages", None) or []
    
    # Extract the actual task from metadata (set by integration harness / dispatcher)
    objective = metadata.get("objective") or metadata.get("task_objective") or ""
    source_context = metadata.get("source_context") or ""
    diagnostic_context = metadata.get("diagnostic_context") or ""
    task_family = metadata.get("task_family") or "general"
    response_schema = metadata.get("response_schema")
    
    # Default schema for structured specialist output: forces JSON, no reasoning
    default_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "string", "description": "The raw result (code fix, analysis, etc.)"},
        },
        "required": ["result"],
        "additionalProperties": False,
    }
    
    # Build the crystal directive - the specialist's immutable role definition
    # NO reasoning, NO explanation. Output ONLY the result (code fix, etc.)
    # Inference/reasoning ONLY happens on RETRY after gate failure
    crystal_directive = (
        f"# CRYSTAL SPECIALIST: {task_family.upper()}\n"
        f"# Deterministic specialist function. Output ONLY the result.\n"
        f"# NO reasoning, NO explanation, NO conversation. Raw output only.\n"
        f"# Gates verify output. Failed gates trigger retry with minimal feedback."
    )
    
    # Build structured task spec
    task_spec = {
        "task_family": task_family,
        "objective": objective,
        "source_context": source_context,
        "diagnostic_context": diagnostic_context,
        "constraints": {
            "max_tokens": getattr(ir, "max_tokens", None),
            "deterministic": True,
            "schema_enforced": True,
            "output_raw_result_only": True,
        }
    }
    
    # If no metadata objective, fall back to extracting from messages
    if not objective and messages:
        # Last user message is typically the task
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            task_spec["objective"] = str(user_msgs[-1].get("content", ""))
        system_msgs = [m for m in messages if m.get("role") == "system"]
        if system_msgs:
            crystal_directive = str(system_msgs[0].get("content", crystal_directive))
    
    # Use provided schema or default structured output schema
    schema = response_schema if response_schema is not None else default_schema
    
    return crystal_directive, json.dumps(task_spec, separators=(",", ":"), default=str), schema


# -- default gates ---------------------------------------------------------------------------------------

def cascade_gate(text: str, ir: Any) -> tuple[bool, str]:
    cascade = cascade_admission_input(getattr(ir, "metadata", None) or {})
    if cascade and (cascade.get("passed") is True or cascade.get("skipped")):
        return True, "quality_cascade_passed" if cascade.get("passed") else str(cascade.get("skipped"))
    return False, "quality_cascade_not_passed"


def output_governor_gate(text: str, ir: Any) -> tuple[bool, str]:
    from app.kernel.sensorium.episode_envelope import _contains_secret

    metadata = getattr(ir, "metadata", None) or {}
    if not text.strip():
        return False, "empty_output"
    if _contains_secret(text):
        return False, "secret_material_in_output"
    contract = metadata.get("output_contract")
    if isinstance(contract, Mapping) and contract.get("root") and contract.get("allowed_paths"):
        from pathlib import Path

        from app.kernel.governance.output_governor import output_gate, provider_output_profile

        result = output_gate(Path(str(contract["root"])), text, list(contract["allowed_paths"]),
                             provider_output_profile(str(contract.get("provider") or "ollama")))
        return result.ok, "output_gate_compiled" if result.ok else f"output_gate:{result.error}"[:200]
    fmt = str((metadata.get("response_format") or {}).get("type") if isinstance(metadata.get("response_format"), Mapping)
              else metadata.get("response_format") or "")
    if fmt in {"json", "json_object"}:
        try:
            json.loads(text)
        except ValueError:
            return False, "declared_json_format_invalid"
    return True, "output_governor_passed"


def completion_verifier(text: str, ir: Any, generation: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    if generation is not None and generation.get("done_reason") not in {"stop", ""}:
        return False, f"generation_not_complete:{generation.get('done_reason')}"
    if "<think>" in text:
        return False, "reasoning_leak"
    return True, "completion_verified"


@dataclass
class SpecialistOutcome:
    dispatched: bool
    reason: str
    response: dict[str, Any] | None = None
    receipt: dict[str, Any] = field(default_factory=dict)


class SwarmSpecialistDispatch:
    def __init__(self, *, runner: OllamaSwarmRunner, governor: Any, quality_gate: Gate = cascade_gate,
                 output_governor: Gate = output_governor_gate, verifiers: Iterable[Callable[..., Any]] = (),
                 negative_evidence: Callable[[dict[str, Any]], Any] | None = None,
                 env: Mapping[str, str] | None = None):
        self.runner, self.governor = runner, governor
        self.quality_gate, self.output_governor = quality_gate, output_governor
        self.verifiers = list(verifiers) or [completion_verifier]
        self.negative_evidence = negative_evidence or (lambda item: None)
        self.env = os.environ if env is None else env

    def _refuse(self, reason: str, receipt: dict[str, Any]) -> SpecialistOutcome:
        receipt["outcome"] = "provider_fallback"
        if receipt.get("generated"):
            self.negative_evidence({"kind": "specialist_output_rejected", "reason": reason,
                                    "model": receipt.get("model"), "governor_receipt": receipt.get("governor_receipt")})
        return SpecialistOutcome(False, reason, None, receipt)

    async def dispatch(self, ir: Any, route: Mapping[str, Any], *, run_id: str = "",
                       progress: Callable[[str], None] | None = None) -> SpecialistOutcome:
        receipt: dict[str, Any] = {"proposal_only": True, "execution_granted": False, "route": route.get("route")}
        if route.get("route") != "local_specialist_adapter":
            return SpecialistOutcome(False, "not_a_specialist_proposal", None, receipt)
        max_tokens = max(16, min(int(getattr(ir, "max_tokens", None) or 512), 1024))
        metadata = getattr(ir, "metadata", None) or {}
        schema = metadata.get("response_schema")
        retries = max(0, min(int(metadata.get("repair_retries") or 0), MAX_REPAIR_RETRIES))
        token_budget = int(metadata.get("token_budget") or max_tokens * (1 + retries))
        decision = self.governor.admit(
            Episode(run_id=run_id or str(metadata.get("run_id") or "specialist")),
            Proposal(kind="local_specialist", provider="ollama", route_decision=dict(route),
                     estimate={"tokens_total": float(token_budget)}))
        receipt["governor_receipt"] = decision.receipt_id
        receipt["governor_outcome"] = decision.outcome
        if decision.outcome != ADMIT:  # strict: shadow mode never dispatches a refused/deferred specialist
            return self._refuse(f"governor_{decision.outcome}", receipt)
        if progress is not None:
            progress("model_discovery")
        try:
            installed = await self.runner.installed_models()
        except Exception as exc:  # noqa: BLE001
            return self._refuse(f"runner_unavailable:{type(exc).__name__}", receipt)
        model, resolution = resolve_runner_model(str(route.get("specialist_ref") or ""), installed, env=self.env)
        receipt.update({"model": model, "model_resolution": resolution, "installed_models": installed,
                        "response_schema": bool(schema), "repair_retries_allowed": retries,
                        "token_budget": token_budget})
        if not model:
            return self._refuse("no_installed_model", receipt)
        system_directive, task_spec_json, schema = _crystal_task_spec(ir)
        attempts: list[dict[str, Any]] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        receipt["attempts"], receipt["usage"] = attempts, usage
        receipt["task_spec"] = json.loads(task_spec_json)
        reason = "no_attempt"
        for attempt in range(1 + retries):
            spent = usage["prompt_tokens"] + usage["completion_tokens"]
            if attempt and attempts and spent + attempts[-1]["tokens"] > token_budget:
                receipt["budget_exhausted"] = True
                break
            kwargs: dict[str, Any] = {"model": model, "system": system_directive, "prompt": task_spec_json, "max_tokens": max_tokens}
            if schema is not None:
                kwargs["format"] = schema
            if progress is not None:
                progress("model_inference")
            try:
                generation = await self.runner.generate(**kwargs)
            except Exception as exc:  # noqa: BLE001
                reason = f"runner_error:{type(exc).__name__}"
                attempts.append({"attempt": attempt, "reason": reason, "tokens": 0})
                break
            if progress is not None:
                progress("output_validation")
            receipt["generated"] = True
            used = int(generation["usage"]["prompt_tokens"]) + int(generation["usage"]["completion_tokens"])
            usage["prompt_tokens"] += int(generation["usage"]["prompt_tokens"])
            usage["completion_tokens"] += int(generation["usage"]["completion_tokens"])
            ok, reason, gates = self._gate(generation, ir)
            attempts.append({"attempt": attempt, "reason": reason, "tokens": used,
                             "latency_ms": generation.get("latency_ms"), "gates": gates})
            receipt["gates"] = gates
            if ok:
                receipt.update({"latency_ms": sum(float(a.get("latency_ms") or 0) for a in attempts),
                                "outcome": "specialist_output_accepted"})
                return SpecialistOutcome(True, "specialist_output_accepted",
                                         {"text": generation["text"], "model": model}, receipt)
            from app.kernel.compute.structured_edit import repair_message

            task_spec_json = f"{task_spec_json}\nassistant: {generation['text'][:600]}\nuser: {repair_message(generation['text'], reason)['content']}"
        return self._refuse(reason, receipt)

    def _gate(self, generation: Mapping[str, Any], ir: Any) -> tuple[bool, str, list[dict[str, Any]]]:
        text = str(generation["text"])
        gates: list[dict[str, Any]] = []
        for name, gate in (("quality_cascade", self.quality_gate), ("output_governor", self.output_governor)):
            ok, why = gate(text, ir)
            gates.append({"gate": name, "passed": bool(ok), "reason": why})
            if not ok:
                return False, f"{name}_failed:{why}", gates
        for verifier in self.verifiers:
            takes_generation = len(inspect.signature(verifier).parameters) >= 3
            ok, why = verifier(text, ir, generation) if takes_generation else verifier(text, ir)
            gates.append({"gate": "verifier", "passed": bool(ok), "reason": why})
            if not ok:
                return False, f"verifier_failed:{why}", gates
        return True, "specialist_output_accepted", gates


__all__ = ["MODEL_ENV", "OllamaSwarmRunner", "SPECIALIST_ENV", "SpecialistOutcome", "SwarmSpecialistDispatch",
           "cascade_gate", "completion_verifier", "output_governor_gate", "resolve_runner_model",
           "specialist_enabled"]
