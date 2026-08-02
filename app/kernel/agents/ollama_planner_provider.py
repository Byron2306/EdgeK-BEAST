"""Live Ollama planner adapter for the canonical BEAST AgentRun loop."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import PlannerDecisionError, parse_planner_decision
from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.local.ollama_config import ollama_model
from app.kernel.compute.ollama_pressure_controller import OllamaPressureController
from app.kernel.compute.ollama_cpu_profile import request_options
from app.kernel.sensorium.ollama_runtime_sensor import OllamaRuntimeSensor
from app.kernel.sensorium.workspace_invalidation import WorkspaceInvalidationBus


class OllamaPlannerProvider:
    """Use Ollama as a bounded next-action planner."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        default_approval_id: str = "",
        temperature: float = 0.0,
        seed: int = 731947,
        route_dampener: RouteFlapDampener | None = None,
        route_id: str = "",
        forge_kv_manager: Any = None,
        crystal_gateway: CrystalReuseGateway | None = None,
        engine: str | None = None,
        llama_cpp_base_url: str | None = None,
        execution_gateway: Any = None,
        compute_governor: Any = None,
        pressure_controller: OllamaPressureController | None = None,
        runtime_sensor: OllamaRuntimeSensor | None = None,
        invalidation_bus: WorkspaceInvalidationBus | None = None,
        on_token: Any = None,
    ) -> None:
        self.model = ollama_model(model)
        configured_base_url = (
            base_url
            or os.environ.get("BEAST_OLLAMA_BASE_URL")
            or os.environ.get("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        )
        self.base_url = self._normalize_base_url(configured_base_url)
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.default_approval_id = str(default_approval_id or "")
        self.temperature = float(temperature)
        self.seed = int(seed)
        self.last_usage: dict[str, Any] = {}
        self.route_dampener = route_dampener
        self.route_id = route_id or f"ollama:{self.model}"
        self.forge_kv_manager = forge_kv_manager
        self.crystal_gateway = crystal_gateway
        self.engine = str(engine or os.environ.get("BEAST_PLANNER_ENGINE", "ollama")).strip().lower()
        self.llama_cpp_base_url = self._normalize_base_url(
            llama_cpp_base_url or os.environ.get("LLAMA_CPP_BASE_URL", "http://127.0.0.1:11435")
        )
        self.execution_gateway = execution_gateway
        self.compute_governor = compute_governor
        self.pressure_controller = pressure_controller
        self.runtime_sensor = runtime_sensor or OllamaRuntimeSensor()
        self.invalidation_bus = invalidation_bus or WorkspaceInvalidationBus()
        self.on_token = on_token
        self._pressure_decision = None
        self._runtime_before: dict[str, Any] | None = None
        self._preflight_ok = False
        self.last_partial_text = ""
        self.last_route = {"provider": "ollama", "engine": self.engine or "ollama", "route_kind": "ollama", "reason": "direct_local_inference"}

    def close(self) -> None:
        manager = self.forge_kv_manager
        if manager is not None and hasattr(manager, "close"):
            manager.close()

    def record_verified_decision(self, *, prompt: str, decision: PlannerDecision, run: dict[str, Any], evidence: dict[str, Any]) -> None:
        """Promote only a planner response that cleared runtime verification."""
        if self.crystal_gateway is None:
            return
        request = CrystalReuseRequest(
            prompt=prompt,
            model=self.model,
            system_prompt="You are BEAST's governed local planner. Return one JSON action only.",
            task_class="agent_planner",
            repo_fingerprint=str(run.get("repository_fingerprint") or run.get("repo_fingerprint") or "") or None,
            tokenizer=str(run.get("tokenizer") or "ollama-native"),
            prompt_prefix=self._split_native_planner_prompt(prompt)[0],
            provider="ollama",
            parameters={"temperature": self.temperature},
        )
        response = json.dumps(decision.as_dict(), sort_keys=True, separators=(",", ":"))
        self.crystal_gateway.record_execution_response(
            request,
            response,
            route=str(self.last_usage.get("engine") or "ollama"),
            engine=str(self.last_usage.get("engine") or "ollama"),
            verified=True,
            evidence=evidence,
            write_memory=True,
        )

    def _route_event(self, event: str) -> dict[str, Any]:
        if self.route_dampener is None:
            return {"route_id": self.route_id, "event": event, "penalty": 0.0, "suppressed": False}
        score = self.route_dampener.record(self.route_id, event)
        return {"route_id": self.route_id, "event": event, "penalty": round(score.penalty, 3), "suppressed": score.penalty >= self.route_dampener.suppress_at}

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        """Return the Ollama server origin expected by the native /api endpoints.

        Operators sometimes provide an OpenAI-compatible endpoint such as
        ``http://127.0.0.1:11434/v1`` or even the full completion path.  This
        adapter uses Ollama's native ``/api/tags`` and ``/api/generate`` routes,
        so known API suffixes must be removed before request paths are appended.
        """
        normalized = str(value or "").strip().rstrip("/")
        for suffix in (
            "/v1/chat/completions",
            "/api/generate",
            "/api/chat",
            "/api/tags",
            "/v1",
            "/api",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].rstrip("/")
                break
        if not normalized:
            raise ValueError("Ollama base URL is empty after normalization")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"http://{normalized}"
        return normalized

    async def probe(self) -> dict[str, Any]:
        payload = await asyncio.to_thread(self._request_json, "/api/tags", None, 10.0)
        models = [str(item.get("name") or "") for item in payload.get("models", []) if isinstance(item, dict)]
        return {"ok": self.model in models, "model": self.model, "models": models, "base_url": self.base_url}

    async def _preflight(self) -> None:
        if self._preflight_ok:
            return
        timeout = max(1.0, float(os.environ.get("BEAST_OLLAMA_PREFLIGHT_TIMEOUT", "4")))
        try:
            payload = await asyncio.to_thread(self._request_json, "/api/tags", None, timeout)
        except OSError as exc:
            if self.route_dampener is not None:
                self.last_usage["route"] = self._route_event("incorrect")
            raise PlannerDecisionError(
                f"Ollama config preflight failed for {self.base_url}: {exc}. "
                "Check BEAST_OLLAMA_BASE_URL/OLLAMA_HOST and confirm the native Ollama /api/tags endpoint is reachable."
            ) from exc
        models = [str(item.get("name") or "") for item in payload.get("models", []) if isinstance(item, dict)]
        if self.model not in models:
            if self.route_dampener is not None:
                self.last_usage["route"] = self._route_event("incorrect")
            preview = ", ".join(models[:8]) or "no models reported"
            raise PlannerDecisionError(
                f"Ollama model {self.model!r} is not installed at {self.base_url}; available: {preview}. "
                f"Run `ollama pull {self.model}` or choose one of the listed models."
            )
        self._preflight_ok = True

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        self.last_partial_text = ""
        if self.route_dampener is not None and self.route_dampener.suppressed(self.route_id):
            self.last_route = {"provider": "ollama", "engine": self.engine or "ollama", "route_kind": "dampened", "reason": "persistent_bad_route_memory"}
            self.last_usage = {"route": self._route_event("timeout"), "timeout_seconds": self._request_timeout(prompt, run=run, turn=turn)}
            raise PlannerDecisionError("Ollama route dampened after repeated slow or failed planner turns")
        await self._preflight()
        self._prepare_sensorium(run)
        reused = self._try_crystal_reuse(prompt, run=run, turn=turn)
        if reused is not None:
            self.last_route = {"provider": "ollama", "engine": "crystal_reuse", "route_kind": "crystal_reuse", "reason": "verified_replay"}
            self._finish_sensorium()
            return reused
        self._govern_request(prompt, run=run, turn=turn)
        self._apply_pressure_budget(reuse_mode="cold")
        request_timeout = self._request_timeout(prompt, run=run, turn=turn)
        if self.engine in {"llama.cpp", "llama_cpp", "llamacpp"}:
            result = await self._next_decision_with_llama_cpp(prompt, run=run, turn=turn, timeout_seconds=request_timeout)
            self.last_route = {"provider": "ollama", "engine": "llama.cpp", "route_kind": "llama_cpp", "reason": "explicit_engine"}
            self._finish_sensorium()
            return result
        if self.forge_kv_manager is not None:
            try:
                result = await self._next_decision_with_native_context(prompt, run=run, turn=turn)
                self.last_route = {"provider": "ollama", "engine": "ollama", "route_kind": "native_context", "reason": "suffix_only_context_reuse"}
                self._finish_sensorium()
                return result
            except Exception as exc:
                self.last_usage = {"forge_kv": {"mode": "cold_ollama_fallback", "reason": f"{type(exc).__name__}: {exc}"}}
        if self.execution_gateway is not None:
            try:
                result = await self._next_decision_via_execution_gateway(prompt, run=run, turn=turn)
                self.last_route = {"provider": "ollama", "engine": str(self.last_usage.get("engine") or "execution_gateway"), "route_kind": "execution_gateway", "reason": "shared_local_execution"}
                self._finish_sensorium()
                return result
            except Exception as exc:
                self.last_usage = {"execution_gateway": {"mode": "direct_provider_fallback", "reason": f"{type(exc).__name__}: {exc}"}}
        repair_hint = ""
        last_error = ""
        for attempt in range(self.max_retries + 1):
            request_prompt = prompt + repair_hint + (
                "\n\nIMPORTANT: Return exactly one JSON object. Do not use markdown fences. "
                "For worktree.bind, worktree.replace_exact, worktree.write_file, and worktree.verify, "
                "include the supplied approval_id when one is shown in RUN AUTHORITY."
            )
            if self.default_approval_id:
                request_prompt += f"\n\nRUN AUTHORITY:\n{{\"approval_id\": {json.dumps(self.default_approval_id)}}}"
            payload = {
                "model": self.model,
                "prompt": request_prompt,
                # Stream deltas into the durable run ledger. The final
                # decision is still parsed and validated as one typed packet;
                # streaming only improves visibility and cancellation.
                "stream": True,
                "options": {
                    "temperature": self.temperature,
                    "seed": self.seed + int(turn),
                    # Planner turns need a compact tool decision, not a large
                    # code-generation window.  Oversizing this on a local CPU
                    # makes an IDE appear hung before it can issue its first
                    # tool call.
                    "num_ctx": self._num_ctx(),
                    "num_predict": self._num_predict(),
                    "num_thread": self._num_thread(),
                    "num_batch": self._num_batch(),
                },
                "keep_alive": os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
            }
            try:
                request_method = self._request_stream_json if callable(self.on_token) else self._request_json
                body = await asyncio.to_thread(request_method, "/api/generate", payload, request_timeout)
                self.last_usage = {
                    "prompt_chars": len(request_prompt),
                    "prompt_bytes": len(request_prompt.encode("utf-8")),
                    "prompt_eval_count": body.get("prompt_eval_count"),
                    "completion_eval_count": body.get("eval_count"),
                    "total_duration_ns": body.get("total_duration"),
                    "load_duration_ns": body.get("load_duration"),
                    "eval_duration_ns": body.get("eval_duration"),
                    "latency_ms": round(float(body.get("total_duration") or 0) / 1_000_000.0, 3) if body.get("total_duration") is not None else None,
                    "timeout_seconds": request_timeout,
                }
                raw = str(body.get("response") or "")
                mode = str(run.get("mode") or "").strip().lower()
                if mode in {"chat", "analysis", "ask"} and raw.strip():
                    try:
                        decision = parse_planner_decision(raw)
                    except PlannerDecisionError:
                        self.last_route = {"provider": "ollama", "engine": "ollama", "route_kind": "direct_text_answer", "reason": "non_json_chat_completion"}
                        if self.route_dampener is not None:
                            self.last_usage["route"] = self._route_event("success")
                        self._finish_sensorium()
                        return PlannerDecision(
                            decision_type=PlannerDecisionType.COMPLETE,
                            arguments={},
                            summary=raw.strip(),
                            rationale="Recovered a non-JSON conversational completion from Ollama for a non-mutating run.",
                        )
                decision = parse_planner_decision(raw)
                if (
                    decision.decision_type is PlannerDecisionType.TOOL
                    and self.default_approval_id
                    and decision.tool_id in {"worktree.bind", "worktree.write_file", "worktree.replace_exact", "worktree.verify"}
                    and not decision.approval_id
                ):
                    decision = PlannerDecision(
                        decision_type=decision.decision_type,
                        rationale=decision.rationale,
                        tool_id=decision.tool_id,
                        arguments=decision.arguments,
                        execution_target=decision.execution_target,
                        approval_id=self.default_approval_id,
                        summary=decision.summary,
                        blocker=decision.blocker,
                    )
                self.last_route = {"provider": "ollama", "engine": "ollama", "route_kind": "direct_generate", "reason": "native_api_generate"}
                if self.route_dampener is not None:
                    self.last_usage["route"] = self._route_event("success")
                self._finish_sensorium()
                return decision
            except (OSError, ValueError, PlannerDecisionError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                if self.route_dampener is not None:
                    lowered = last_error.casefold()
                    event = "schema" if isinstance(exc, (ValueError, PlannerDecisionError, json.JSONDecodeError)) else "timeout" if "timeout" in lowered or "timed out" in lowered else "incorrect"
                    self.last_usage["route"] = self._route_event(event)
                repair_hint = (
                    "\n\nYOUR PREVIOUS DECISION WAS INVALID. Correct only the JSON contract. "
                    f"ERROR: {last_error}"
                )
                await asyncio.sleep(min(1.0 * (attempt + 1), 3.0))
        self._finish_sensorium()
        raise PlannerDecisionError(f"Ollama failed to produce a valid planner decision: {last_error}")

    @staticmethod
    def _planner_state(run: dict[str, Any]) -> dict[str, Any]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        return planner

    @classmethod
    def _is_repair_turn(cls, run: dict[str, Any]) -> bool:
        planner = cls._planner_state(run)
        if int(planner.get("repair_cycles") or 0) > 0:
            return True
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        return bool(failures)

    @classmethod
    def _request_timeout(cls, prompt: str, *, run: dict[str, Any], turn: int) -> float:
        del prompt, turn
        base = max(5.0, float(os.environ.get("BEAST_OLLAMA_PLANNER_TIMEOUT", "30")))
        if cls._is_repair_turn(run):
            return max(6.0, min(base, float(os.environ.get("BEAST_OLLAMA_REPAIR_TIMEOUT", "12"))))
        planner = cls._planner_state(run)
        observed = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        if observed:
            return max(6.0, min(base, float(os.environ.get("BEAST_OLLAMA_FOLLOWUP_TIMEOUT", "14"))))
        return base

    def _workspace_root(self, run: dict[str, Any]) -> str:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        return str(run.get("workspace_root") or run.get("root") or request.get("workspace_root") or "")

    def _request_stream_json(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Consume Ollama NDJSON while preserving the final usage envelope."""
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
            method="POST",
        )
        aggregate: dict[str, Any] = {}
        response_parts: list[str] = []
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    continue
                aggregate.update({key: value for key, value in item.items() if key != "response"})
                text = str(item.get("response") or "")
                if text:
                    response_parts.append(text)
                    self.last_partial_text += text
                    if callable(self.on_token):
                        try:
                            self.on_token(text)
                        except Exception:
                            pass
                if item.get("done") is True:
                    break
        aggregate["response"] = "".join(response_parts)
        return aggregate

    def _prepare_sensorium(self, run: dict[str, Any]) -> None:
        root = self._workspace_root(run)
        changes = self.invalidation_bus.poll(root) if root else []
        if changes and self.forge_kv_manager is not None and hasattr(self.forge_kv_manager, "invalidate_all"):
            self.forge_kv_manager.invalidate_all(reason="workspace_changed_before_planner_turn")
        self._runtime_before = self.runtime_sensor.sample()

    def _finish_sensorium(self) -> None:
        if self._runtime_before is None:
            return
        after = self.runtime_sensor.sample()
        usage = dict(self.last_usage)
        if getattr(self, "_governance_usage", None) is not None:
            usage.setdefault("compute_governor", self._governance_usage)
        if self._pressure_decision is not None:
            usage.setdefault("pressure", self._pressure_decision.to_dict())
        usage["runtime_sensor"] = {
            "before": self._runtime_before,
            "after": after,
            "delta": self.runtime_sensor.delta(self._runtime_before, after),
        }
        self.last_usage = usage
        self._runtime_before = None

    def _govern_request(self, prompt: str, *, run: dict[str, Any], turn: int) -> None:
        """Attach the real compute-governor decision to every planner call."""
        if self.compute_governor is None:
            return
        from app.kernel.compute.perceive import EdgeKIR
        ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            max_tokens=self._num_predict(),
            temperature=self.temperature,
            tools=[],
            metadata={"task_class": "agent_planner", "turn": int(turn), "run_id": str(run.get("run_id") or "")},
        )
        plan = self.compute_governor.build_plan(ir, "ollama")
        gate = self.compute_governor.evaluate(plan)
        if not gate.allowed:
            raise PlannerDecisionError(f"compute governor denied planner request: {gate.reason}")
        self._governance_usage = {
            "plan_id": plan.plan_id,
            "gate_id": gate.gate_id,
            "mode": gate.mode,
            "decision": gate.decision,
            "selected_rung": gate.selected_rung,
            "recommended_rung": gate.recommended_rung,
            "predicted_avoidable_work": gate.predicted_avoidable_work,
        }
        self.last_usage["compute_governor"] = self._governance_usage

    def _apply_pressure_budget(self, *, reuse_mode: str = "cold") -> None:
        self._pressure_decision = None
        if self.pressure_controller is None:
            return
        requested_predict = int(os.environ.get("BEAST_OLLAMA_NUM_PREDICT", "96"))
        decision = self.pressure_controller.decide(
            num_ctx=int(os.environ.get("BEAST_OLLAMA_NUM_CTX", "768")),
            num_predict=requested_predict,
            min_predict=64,
            reuse_mode=reuse_mode,
        )
        self._pressure_decision = decision
        self.last_usage["pressure"] = decision.to_dict()
        if not decision.admitted:
            raise PlannerDecisionError(f"Ollama admission suppressed by host pressure: {decision.reason}")

    def _num_ctx(self) -> int:
        return int(self._pressure_decision.num_ctx if self._pressure_decision else os.environ.get("BEAST_OLLAMA_NUM_CTX", "768"))

    def _num_predict(self) -> int:
        return int(self._pressure_decision.num_predict if self._pressure_decision else os.environ.get("BEAST_OLLAMA_NUM_PREDICT", "96"))

    def _request_options(self) -> dict[str, int]:
        if self._pressure_decision is not None:
            return {
                "num_thread": int(self._pressure_decision.num_thread),
                "num_batch": int(self._pressure_decision.num_batch),
            }
        return request_options()

    def _num_thread(self) -> int:
        return self._request_options()["num_thread"]

    def _num_batch(self) -> int:
        return self._request_options()["num_batch"]

    async def _next_decision_via_execution_gateway(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        """Use the shared engine fabric when native context reuse is unavailable."""
        from types import SimpleNamespace
        request = SimpleNamespace(
            model=self.model,
            prompt=prompt + "\n\nReturn exactly one JSON object. Do not use markdown fences.",
            system_prompt="You are BEAST's governed local planner. Return one JSON action only.",
            parameters={"max_tokens": self._num_predict()},
            preferred_engine=(run.get("preferred_engine") or (run.get("request") or {}).get("preferred_engine")),
            task_class="agent_planner",
        )
        result = await asyncio.to_thread(self.execution_gateway.complete, request)
        self.last_usage = {
            "engine": result.get("engine_id") or "ollama",
            "execution_gateway": {"mode": "shared_local_execution_gateway", "route": result.get("route", "local_cpu")},
            "prompt_chars": len(request.prompt),
            "prompt_eval_count": result.get("prompt_tokens"),
            "completion_eval_count": result.get("output_tokens"),
            "latency_ms": result.get("latency_ms"),
        }
        return parse_planner_decision(str(result.get("response") or ""))

    def _try_crystal_reuse(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision | None:
        """Let exact verified planner crystals short-circuit live inference."""
        if self.crystal_gateway is None:
            return None
        request = CrystalReuseRequest(
            prompt=prompt,
            model=self.model,
            system_prompt="You are BEAST's governed local planner. Return one JSON action only.",
            task_class="agent_planner",
            repo_fingerprint=str(run.get("repository_fingerprint") or run.get("repo_fingerprint") or "") or None,
            tokenizer=str(run.get("tokenizer") or "ollama-native"),
            prompt_prefix=self._split_native_planner_prompt(prompt)[0],
            provider="ollama",
            parameters={"temperature": self.temperature, "seed": self.seed + int(turn)},
        )
        decision = self.crystal_gateway.decide(request)
        reuse = decision.payload.get("reuse") if isinstance(decision.payload, dict) else {}
        payload = reuse.get("payload") if isinstance(reuse, dict) else {}
        raw = payload.get("answer") or payload.get("response") if isinstance(payload, dict) else None
        if decision.action != "reuse_answer" or not raw:
            self.last_usage = {"crystal_reuse": {"action": decision.action, "source": decision.source, "decision_id": decision.decision_id}}
            return None
        parsed = parse_planner_decision(str(raw))
        self.last_usage = {
            "crystal_reuse": {"action": decision.action, "source": decision.source, "decision_id": decision.decision_id, "avoided_tokens": decision.avoided_tokens_estimate},
            "pressure": {"profile": "crystal", "zero_inference": True, "num_thread": 0, "num_batch": 0},
        }
        return parsed

    async def _next_decision_with_llama_cpp(self, prompt: str, *, run: dict[str, Any], turn: int, timeout_seconds: float) -> PlannerDecision:
        """Use llama.cpp prompt-cache reuse when explicitly selected.

        This is prompt-cache routing, not hidden-state injection. The server
        must be started with ``--cache-prompt``; otherwise its response remains
        correct but telemetry records a cold engine path.
        """
        stable, suffix = self._split_native_planner_prompt(prompt)
        request_prompt = stable + ("\n" + suffix if suffix else "")
        if self.default_approval_id:
            request_prompt += f"\nRUN AUTHORITY:\n{{\"approval_id\": {json.dumps(self.default_approval_id)}}}"
        payload = {
            "prompt": request_prompt,
            "n_predict": self._num_predict(),
            "temperature": self.temperature,
            "seed": self.seed + int(turn),
            "cache_prompt": True,
            "stop": ["\\nTURN:"],
        }
        body = await asyncio.to_thread(self._request_llama_cpp_json, "/completion", payload, timeout_seconds)
        self.last_usage = {
            "engine": "llama.cpp",
            "prompt_chars": len(request_prompt),
            "stable_prefix_chars": len(stable),
            "suffix_chars": len(suffix),
            "cache_prompt": True,
            "prompt_eval_count": body.get("tokens_evaluated"),
            "completion_eval_count": body.get("tokens_predicted"),
            "total_duration_ns": body.get("timings", {}).get("prompt_ms") if isinstance(body.get("timings"), dict) else None,
            "timeout_seconds": timeout_seconds,
        }
        return parse_planner_decision(str(body.get("content") or body.get("response") or ""))

    @staticmethod
    def _split_native_planner_prompt(prompt: str) -> tuple[str, str]:
        marker = "\nTURN:"
        if marker not in prompt:
            return prompt, ""
        stable, suffix = prompt.split(marker, 1)
        return stable, "TURN:" + suffix

    async def _next_decision_with_native_context(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        self._apply_pressure_budget(reuse_mode="kv")
        stable_prefix, suffix = self._split_native_planner_prompt(prompt)
        request_suffix = suffix or prompt
        if self.default_approval_id:
            request_suffix += f"\nRUN AUTHORITY:\n{{\"approval_id\": {json.dumps(self.default_approval_id)}}}"
        block, result = await asyncio.to_thread(
            self._native_context_transaction,
            stable_prefix,
            request_suffix,
            run,
            turn,
        )
        if result.get("error"):
            raise OSError(str(result["error"]))
        self.last_usage = {
            "prompt_chars": len(request_suffix),
            "prompt_eval_count": result.get("prompt_eval_count"),
            "completion_eval_count": result.get("eval_count"),
            "total_duration_ns": result.get("total_duration"),
            "load_duration_ns": result.get("load_duration"),
            "eval_duration_ns": result.get("eval_duration"),
            "forge_kv": {"mode": "native_context", "context_id": block.context_id, "stable_prefix_chars": len(stable_prefix), "suffix_chars": len(request_suffix), "suffix_only": True},
        }
        decision = parse_planner_decision(str(result.get("response") or ""))
        if (
            decision.decision_type is PlannerDecisionType.TOOL
            and self.default_approval_id
            and decision.tool_id in {"worktree.bind", "worktree.write_file", "worktree.replace_exact", "worktree.verify"}
            and not decision.approval_id
        ):
            decision = PlannerDecision(
                decision_type=decision.decision_type,
                rationale=decision.rationale,
                tool_id=decision.tool_id,
                arguments=decision.arguments,
                execution_target=decision.execution_target,
                approval_id=self.default_approval_id,
                summary=decision.summary,
                blocker=decision.blocker,
            )
        return decision

    def _native_context_transaction(self, stable_prefix: str, suffix: str, run: dict[str, Any], turn: int) -> tuple[Any, dict[str, Any]]:
        """Perform prefill and suffix generation in one executor transaction."""
        block = self.forge_kv_manager.get_or_create_context(
            self.model,
            stable_prefix,
            "You are BEAST's governed local planner. Return one JSON action only.",
            model_digest=str(run.get("model_digest") or ""),
            tokenizer_hint=str(run.get("tokenizer") or "ollama-native"),
            template="beast-planner-v1",
            options={"num_ctx": self._num_ctx(), "num_thread": self._num_thread(), "num_batch": self._num_batch()},
            keep_alive=os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
        )
        if not getattr(block, "native_context_available", False):
            raise OSError("native Ollama context unavailable; refusing suffix-only planner request")
        result = self.forge_kv_manager.generate_with_context(
            block,
            suffix,
            48,
            options={"temperature": self.temperature, "seed": self.seed + int(turn), "num_ctx": self._num_ctx(), "num_thread": self._num_thread(), "num_batch": self._num_batch()},
            keep_alive=os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
        )
        return block, result

    async def solve_residual(self, payload: dict[str, Any], *, run: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fill one compiler-declared hole without granting planning authority."""
        self._prepare_sensorium(run or {})
        if self.route_dampener is not None and self.route_dampener.suppressed(self.route_id):
            return {"status": "route_suppressed", "reason": "Ollama route dampened after repeated instability", "unresolved_fields": [str(item) for item in (payload.get("unresolved_fields") if payload.get("unresolved_fields") is not None else ["new"])], "usage": {"route": self._route_event("timeout")}}
        allowed = payload.get("allowed_output") if isinstance(payload.get("allowed_output"), dict) else payload.get("allowed_response") if isinstance(payload.get("allowed_response"), dict) else {}
        raw_unresolved = payload.get("unresolved_fields")
        unresolved = [str(item) for item in (raw_unresolved if raw_unresolved is not None else ["new"])]
        forge_route = payload.get("forge_kv_route") if isinstance(payload.get("forge_kv_route"), dict) else {}
        if forge_route.get("injectable") is True and self.forge_kv_manager is not None:
            result = await self._solve_with_native_context(payload, unresolved, forge_route)
            self._finish_sensorium()
            return result
        prompt = (
            "Return exactly one JSON object for the declared residual fields. "
            "Do not choose files, tools, commands, approvals, or verification. "
            "The value for new must be non-empty replacement text for ONLY the exact old snippet, never a whole file. "
            "Example shape: {\"new\": \"str(value).strip().lower()\"}. "
            f"Allowed fields: {json.dumps(unresolved)}. Allowed output contract: {json.dumps(allowed)}.\n"
            f"Payload: {json.dumps(payload, sort_keys=True)}"
        )
        started = time.perf_counter()
        prompt_bytes = len(prompt.encode("utf-8"))
        try:
            body = await asyncio.to_thread(self._request_json, "/api/generate", {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": self.temperature,
                    "seed": self.seed,
                    "num_ctx": int(os.environ.get("BEAST_OLLAMA_RESIDUAL_NUM_CTX", "1024")),
                    "num_predict": int(os.environ.get("BEAST_OLLAMA_RESIDUAL_NUM_PREDICT", "96")),
                    "num_thread": self._num_thread(),
                    "num_batch": self._num_batch(),
                },
                "keep_alive": os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
            }, self.timeout_seconds)
            route_event = self._route_event("success")
        except Exception:
            route_event = self._route_event("timeout")
            raise
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        raw = body.get("response") if isinstance(body, dict) else None
        usage = {
            "prompt_chars": len(prompt),
            "prompt_bytes": prompt_bytes,
            "prompt_eval_count": body.get("prompt_eval_count"),
            "completion_eval_count": body.get("eval_count"),
            "prompt_tokens": body.get("prompt_eval_count"),
            "completion_tokens": body.get("eval_count"),
            "total_tokens": (int(body["prompt_eval_count"]) + int(body["eval_count"])) if body.get("prompt_eval_count") is not None and body.get("eval_count") is not None else None,
            "total_duration_ns": body.get("total_duration"),
            "load_duration_ns": body.get("load_duration"),
            "eval_duration_ns": body.get("eval_duration"),
            "wall_time_ms": elapsed_ms,
            "route": route_event,
        }
        result = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(result, dict):
            raise PlannerDecisionError("Ollama residual response must be a JSON object")
        if result.get("refusal"):
            self.last_usage = usage
            self._finish_sensorium()
            return {"status": "refused", "refusal": str(result["refusal"]), "unresolved_fields": unresolved, "usage": usage}
        unknown = set(result) - set(unresolved) - {"status", "reason", "refusal"}
        if unknown:
            raise PlannerDecisionError(f"Ollama residual returned unauthorized fields: {sorted(unknown)}")
        missing = [field for field in unresolved if field not in result]
        if missing:
            raise PlannerDecisionError(f"Ollama residual omitted fields: {', '.join(missing)}")
        for field in unresolved:
            value = result.get(field)
            if not isinstance(value, str) or not value.strip():
                raise PlannerDecisionError(f"Ollama residual field {field!r} must be a non-empty string")
            lowered = value.casefold()
            forbidden = ("complete replacement source", "replacement code here", "insert code", "your code", "example implementation", "todo")
            if any(marker in lowered for marker in forbidden):
                raise PlannerDecisionError(f"Ollama residual field {field!r} contains a placeholder")
        self.last_usage = usage
        self._finish_sensorium()
        return {"status": "residual_generated", "verification_status": "pending", "fields": {field: result[field] for field in unresolved}, "reason": result.get("reason", ""), "usage": usage}

    async def _solve_with_native_context(self, payload: dict[str, Any], unresolved: list[str], route: dict[str, Any]) -> dict[str, Any]:
        """Inject only the unresolved suffix into an existing Ollama context."""
        context_id = str(route.get("block_id") or "")
        block = self.forge_kv_manager.contexts.get(context_id)
        if block is None or not block.native_context_available:
            raise PlannerDecisionError("Forge KV route claimed native injection but context is unavailable")
        suffix = str(route.get("provider_prompt") or "")
        prompt = (
            "Return exactly one JSON object for these residual fields: "
            f"{json.dumps(unresolved)}. The value must replace only the declared exact snippet. "
            f"Residual suffix: {suffix}"
        )
        result = await asyncio.to_thread(
            self.forge_kv_manager.generate_with_context,
            block,
            prompt,
            96,
            options={"temperature": self.temperature, "num_ctx": int(os.environ.get("BEAST_OLLAMA_RESIDUAL_NUM_CTX", "1024")), "num_thread": self._num_thread(), "num_batch": self._num_batch()},
            keep_alive=os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
        )
        raw = result.get("response") or ""
        try:
            decoded = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PlannerDecisionError("Ollama native-context residual was not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise PlannerDecisionError("Ollama native-context residual must be an object")
        fields = {field: decoded.get(field) for field in unresolved}
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            raise PlannerDecisionError("Ollama native-context residual omitted a non-empty field")
        usage = {"prompt_chars": len(prompt), "prompt_eval_count": result.get("prompt_eval_count"), "completion_eval_count": result.get("eval_count"), "total_duration_ns": result.get("total_duration"), "load_duration_ns": result.get("load_duration"), "eval_duration_ns": result.get("eval_duration"), "wall_time_ms": result.get("latency_ms"), "forge_kv": {"mode": "native_context", "block_id": context_id, "suffix_only": True}}
        self.last_usage = usage
        return {"status": "residual_generated", "verification_status": "pending", "fields": fields, "reason": "forge_kv_native_context", "usage": usage}

    def _request_json(self, path: str, payload: dict[str, Any] | None, timeout_seconds: float) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                body = response.read().decode("utf-8", errors="replace")
                status = int(getattr(response, "status", 200) or 200)
        except urllib.error.HTTPError as exc:
            content_type = str(exc.headers.get("Content-Type") or "").lower() if exc.headers else ""
            body = exc.read().decode("utf-8", errors="replace")
            preview = " ".join(body[:500].split())
            raise OSError(
                "Ollama transport returned "
                f"HTTP {exc.code} from {url}; content_type={content_type!r}; "
                f"body={preview!r}. Confirm BEAST_OLLAMA_BASE_URL points to the "
                "Ollama server origin, normally http://127.0.0.1:11434."
            ) from exc
        except urllib.error.URLError as exc:
            raise OSError(f"Ollama transport could not reach {url}: {exc.reason}") from exc

        if status < 200 or status >= 300:
            preview = " ".join(body[:500].split())
            raise OSError(
                f"Ollama transport returned HTTP {status} from {url}; "
                f"content_type={content_type!r}; body={preview!r}"
            )
        if "json" not in content_type and body.lstrip().startswith("<"):
            preview = " ".join(body[:500].split())
            raise OSError(
                f"Ollama expected JSON but received HTML from {url}; "
                f"content_type={content_type!r}; body={preview!r}"
            )
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            preview = " ".join(body[:500].split())
            raise OSError(
                f"Ollama returned invalid JSON from {url}; "
                f"content_type={content_type!r}; body={preview!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise OSError(f"Ollama returned a non-object JSON payload from {url}")
        return parsed

    def _request_llama_cpp_json(self, path: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        url = f"{self.llama_cpp_base_url}{path}"
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8", errors="replace"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise PlannerDecisionError(f"llama.cpp planner route failed at {url}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise PlannerDecisionError("llama.cpp planner response must be an object")
        return parsed
