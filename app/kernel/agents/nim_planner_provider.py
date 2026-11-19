"""OpenAI-compatible NVIDIA NIM planner for the canonical AgentRun loop."""

from __future__ import annotations
from app.kernel.compute import governed_egress as _egress  # closure-2026-11-16: governed egress shim

import asyncio
from copy import deepcopy
import json
import os
import time
import threading
import urllib.error
import urllib.request
from typing import Any

from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.agents.file_review import EXPLANATION_HEADER, FOCUSED_EXPLANATION_HEADER
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import PlannerDecisionError, parse_planner_decision
from app.kernel.compute.streaming_interceptor import StreamingComputeInterceptor, StreamingInterceptionEngine


class NIMPlannerProvider:
    """Stream one bounded planner decision from a local or hosted NIM."""

    ACTION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision_type": {"type": "string", "enum": ["tool", "complete", "blocked"]},
            "tool_id": {"type": "string"},
            "arguments": {"type": "object", "additionalProperties": True},
            "summary": {"type": "string"},
            "blocker": {"type": "string"},
            "rationale": {"type": "string"},
            "execution_target": {"type": "string"},
            "approval_id": {"type": "string"},
        },
        "required": ["decision_type", "arguments", "tool_id"],
        "additionalProperties": False,
    }

    EXPLANATION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision_type": {"type": "string", "enum": ["complete"]},
            "tool_id": {"type": "string", "enum": [""]},
            "summary": {"type": "string"},
            "arguments": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "line": {"type": "integer", "minimum": 1},
                                "evidence": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["path", "line", "evidence", "text"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["points"],
                "additionalProperties": False,
            },
        },
        "required": ["decision_type", "arguments", "tool_id"],
        "additionalProperties": False,
    }

    FOCUSED_EXPLANATION_SCHEMA = deepcopy(EXPLANATION_SCHEMA)
    FOCUSED_EXPLANATION_SCHEMA["properties"]["arguments"]["properties"]["points"]["items"] = {
        "type": "object",
        "properties": {"ref": {"type": "string"}, "text": {"type": "string"}},
        "required": ["ref", "text"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        route_dampener: RouteFlapDampener | None = None,
        route_id: str = "",
        on_token: Any = None,
        on_reasoning: Any = None,
        stream: bool | None = None,
        enable_thinking: bool = False,
        allow_reasoning_as_action: bool = True,
        stream_interceptor: StreamingComputeInterceptor | None = None,
        runtime_governor: Any = None,
    ) -> None:
        # Use an instruct model for the control plane by default. Reasoning
        # models are excellent for long answers but can spend the entire
        # planner budget emitting hidden deliberation before the JSON action.
        # Keep tool selection cheap and responsive. Larger models remain an
        # explicit option for residual reasoning after the action is bounded.
        self.model = str(model or os.environ.get("BEAST_NIM_MODEL") or "meta/llama-3.2-1b-instruct")
        self.base_url = str(
            base_url
            or os.environ.get("NVIDIA_NIM_BASE_URL")
            or "https://integrate.api.nvidia.com/v1"
        ).rstrip("/")
        self.api_key = str(api_key or os.environ.get("NVIDIA_API_KEY") or "")
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.max_retries = max(0, min(int(max_retries), 3))
        self.runtime_governor = runtime_governor
        self.route_dampener = route_dampener
        self.route_id = route_id or f"nim:{self.model}"
        self.on_token = on_token
        self.on_reasoning = on_reasoning
        self.stream = stream
        self.enable_thinking = enable_thinking
        self.allow_reasoning_as_action = allow_reasoning_as_action
        self.stream_interceptor = stream_interceptor or StreamingComputeInterceptor(
            StreamingInterceptionEngine(
                max_output_tokens=int(os.environ.get("BEAST_NIM_MAX_TOKENS", "2048")),
                schema_contract=self.ACTION_SCHEMA,
            )
        )
        self.last_partial_text = ""
        self.last_usage: dict[str, Any] = {}
        self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "model": self.model, "route_kind": "nim", "reason": "direct_nim_inference"}

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
    def _request_timeout(cls, *, run: dict[str, Any], default_timeout: float) -> float:
        base = max(30.0, float(default_timeout))
        if cls._is_repair_turn(run):
            return max(15.0, min(base, float(os.environ.get("BEAST_NIM_REPAIR_TIMEOUT", "30"))))
        planner = cls._planner_state(run)
        observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        turn = max(0, int(planner.get("turn") or 0))
        if turn >= 4 or len(observations) >= 3:
            return max(10.0, min(base, float(os.environ.get("BEAST_NIM_LATE_TURN_TIMEOUT", "20"))))
        if observations:
            return max(15.0, min(base, float(os.environ.get("BEAST_NIM_FOLLOWUP_TIMEOUT", "30"))))
        return base

    def _route_event(self, event: str) -> dict[str, Any]:
        if self.route_dampener is None:
            return {"route_id": self.route_id, "event": event, "penalty": 0.0, "suppressed": False}
        score = self.route_dampener.record(self.route_id, event)
        return {"route_id": self.route_id, "event": event, "penalty": round(score.penalty, 3), "suppressed": score.penalty >= self.route_dampener.suppress_at}

    @staticmethod
    def _structured_output_enabled() -> bool:
        raw = os.environ.get("BEAST_NIM_STRUCTURED_OUTPUTS", "1").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    def _request_payload(self, prompt: str, *, repair: str, turn: int) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are BEAST's bounded action controller. Return one JSON decision. For decision_type tool, tool_id is REQUIRED and must name an allowed tool. For complete or blocked, set tool_id to an empty string. Follow the user argument schemas exactly."},
                {"role": "user", "content": prompt + repair},
            ],
            "temperature": 0,
            "seed": 731947 + int(turn),
            "max_tokens": int(os.environ.get("BEAST_NIM_MAX_TOKENS", "2048")),
            "stream": self.stream if self.stream is not None else (
                os.environ.get("BEAST_NIM_PLANNER_STREAM", "0").strip().lower() in {"1", "true", "yes"}
            ),
        }
        if prompt.startswith(FOCUSED_EXPLANATION_HEADER):
            schema = self.FOCUSED_EXPLANATION_SCHEMA
        elif prompt.startswith(EXPLANATION_HEADER):
            schema = self.EXPLANATION_SCHEMA
        else:
            schema = self.ACTION_SCHEMA
        if self._structured_output_enabled():
            payload["structured_outputs"] = {"json": schema}
        if self.model.startswith("nvidia/nemotron-3.5-"):
            # These models otherwise spend the bounded controller budget on
            # hidden reasoning before emitting the executable JSON action.
            payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        # Keep the older nvext path available for compatibility with NIM
        # deployments that still expect guided_json passthrough.
        if os.environ.get("BEAST_NIM_GUIDED_JSON", "0").strip().lower() in {"1", "true", "yes"}:
            payload["nvext"] = {"guided_json": schema}
        return payload

    @staticmethod
    def _unwrap_argument_groups(raw: str) -> str:
        """Normalize a structured-output wrapper without changing authority.

        Some NIM models mirror the prompt's required/optional labels inside
        ``arguments``. The tool registry still validates the flattened keys,
        types, inspected path and approval before anything can execute.
        """
        try:
            payload = json.loads(str(raw or ""))
        except (TypeError, ValueError):
            return raw
        if not isinstance(payload, dict) or not isinstance(payload.get("arguments"), dict):
            return raw
        arguments = payload["arguments"]
        if not set(arguments).issubset({"required", "optional"}):
            return raw
        required = arguments.get("required")
        optional = arguments.get("optional")
        if not isinstance(required, dict) or (optional is not None and not isinstance(optional, dict)):
            return raw
        payload["arguments"] = {**required, **(optional or {})}
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    async def _call_request(request_method: Any, payload: dict[str, Any]) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        def deliver(result: Any = None, error: Exception | None = None) -> None:
            if future.done():
                return
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(result)

        def runner() -> None:
            try:
                result = request_method(payload)
            except Exception as exc:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(deliver, None, exc)
                return
            if not loop.is_closed():
                loop.call_soon_threadsafe(deliver, result)

        thread = threading.Thread(target=runner, name="nim-planner-request", daemon=True)
        thread.start()
        return await future

    def _governed_request(self, request_method: Any, payload: dict[str, Any], *,
                          run: dict[str, Any], turn: int) -> dict[str, Any]:
        # Run the lease in the transport worker. A caller timing out/cancelling
        # must not release the concurrency slot while the socket is still active.
        governor = self.runtime_governor
        if governor is None:
            return request_method(payload)
        provider = "nvidia_nim"
        policy = governor.policies.get("providers", {}).get(provider)
        if not isinstance(policy, dict) or not policy.get("enabled"):
            raise PlannerDecisionError("Hosted NIM is disabled or missing from the loaded provider policy.")
        admission = governor.begin_execution(
            provider=provider, model=self.model, session_id=str(run.get("session_id") or "default"),
            metadata={"run_id": str(run.get("run_id") or ""), "turn": turn,
                      "lane": "interactive", "client": "nim_planner"},
        )
        if not admission.allowed:
            raise PlannerDecisionError(admission.reason)
        try:
            result = request_method(payload)
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                affects_circuit = exc.code in {408, 429} or 500 <= exc.code < 600
                error_type = f"http_{exc.code}"
            else:
                affects_circuit = isinstance(exc, OSError)
                error_type = type(exc).__name__
            governor.complete_execution(admission.attempt_id, provider, success=False,
                                        error_type=error_type, affects_circuit=affects_circuit)
            raise
        # Transport is successful even if the caller later rejects the answer.
        governor.complete_execution(admission.attempt_id, provider, success=True)
        return result

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        self.last_partial_text = ""
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is required for the NIM planner")
        request_timeout = self._request_timeout(run=run, default_timeout=self.timeout_seconds)
        if self.route_dampener is not None and self.route_dampener.suppressed(self.route_id):
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "model": self.model, "route_kind": "dampened", "reason": "persistent_bad_route_memory"}
            self.last_usage = {"engine": "nvidia_nim", "model": self.model, "base_url": self.base_url, "timeout_seconds": request_timeout, "route": self._route_event("timeout")}
            raise PlannerDecisionError("NIM route dampened after repeated slow or failed planner turns")
        started = time.perf_counter()
        repair = ""
        last_error = ""
        for attempt in range(self.max_retries + 1):
            payload = self._request_payload(prompt, repair=repair, turn=turn)
            request_method = self._request_stream if payload["stream"] else self._request_json
            try:
                body = await asyncio.wait_for(
                    self._call_request(
                        lambda packet: self._governed_request(request_method, packet, run=run, turn=turn),
                        payload,
                    ),
                    timeout=request_timeout + 2.0,
                )
            except PlannerDecisionError:
                # An admission refusal is terminal for this provider, not a
                # transport error to retry or count against its health.
                self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim",
                                   "route_kind": "runtime_refused", "reason": "runtime_admission"}
                self.last_usage = {}
                raise
            except asyncio.TimeoutError:
                error = f"timeout after {request_timeout:.1f}s"
            except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
                error = f"{type(exc).__name__}: {exc}"
            else:
                error = ""
            if error:
                self.last_usage = {
                    "engine": "nvidia_nim",
                    "model": self.model,
                    "base_url": self.base_url,
                    "attempt": attempt + 1,
                    "prompt_chars": len(prompt + repair),
                    "completion_chars": 0,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "timeout_seconds": request_timeout,
                    "usage": {},
                    "error": error,
                }
                if self.route_dampener is not None:
                    lowered = error.casefold()
                    event = "timeout" if "timeout" in lowered or "timed out" in lowered else "schema"
                    self.last_usage["route"] = self._route_event(event)
                last_error = error
                if attempt < self.max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                raise RuntimeError(f"NIM planner request failed: {error}")
            raw = str(body.get("content") or "")
            # Nemotron reasoning models emit thinking in reasoning_content
            # instead of content. Fall back to it when content is absent.
            reasoning_text = str(body.get("reasoning_content") or "")
            if reasoning_text.strip() and not body.get("reasoning_streamed") and callable(self.on_reasoning):
                try:
                    self.on_reasoning(reasoning_text)
                except Exception:
                    pass
            if not raw.strip() and self.allow_reasoning_as_action:
                raw = reasoning_text
            raw = self._unwrap_argument_groups(raw)
            mode = str(run.get("mode") or "").strip().lower()
            if mode in {"chat", "analysis", "ask"} and raw.strip():
                try:
                    decision = parse_planner_decision(raw)
                except PlannerDecisionError:
                    self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "model": self.model, "route_kind": "direct_text_answer", "reason": "non_json_chat_completion"}
                    if self.route_dampener is not None:
                        self.last_usage["route"] = self._route_event("success")
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.COMPLETE,
                        arguments={},
                        summary=raw.strip(),
                        rationale="Recovered a non-JSON conversational completion from NIM for a non-mutating run.",
                    )
            self.last_usage = {
                "engine": "nvidia_nim",
                "model": self.model,
                "base_url": self.base_url,
                "attempt": attempt + 1,
                "prompt_chars": len(prompt + repair),
                "completion_chars": len(raw),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "timeout_seconds": request_timeout,
                "usage": body.get("usage") if isinstance(body.get("usage"), dict) else {},
                "finish_reason": body.get("finish_reason"),
            }
            if isinstance(body.get("stream_interception"), dict):
                self.last_usage["stream_interception"] = body["stream_interception"]
            try:
                decision = parse_planner_decision(raw)
                self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "model": self.model, "route_kind": "direct_generate", "reason": "nim_chat_completions"}
                if self.route_dampener is not None:
                    self.last_usage["route"] = self._route_event("success")
                return decision
            except PlannerDecisionError as exc:
                last_error = str(exc)
                if self.route_dampener is not None:
                    self.last_usage["route"] = self._route_event("schema")
                repair = f"\nREPAIR: The previous action was rejected: {str(exc)[:250]}. Return one JSON object; a tool decision MUST include tool_id naming the allowed tool and its arguments."
                if attempt < self.max_retries:
                    await asyncio.sleep(0.2)
        raise PlannerDecisionError(f"NIM failed to produce a valid planner decision: {last_error}")

    def _request_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        content: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason = ""
        max_tokens = int(payload.get("max_tokens") or os.environ.get("BEAST_NIM_MAX_TOKENS", "2048"))
        state = self.stream_interceptor.engine.create_initial_state(max_tokens)
        stopped_upstream = False
        with _egress.urlopen("nim_planner_provider", request, timeout=self.timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                item = json.loads(data)
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("usage"), dict):
                    usage = item["usage"]
                choices = item.get("choices") if isinstance(item.get("choices"), list) else []
                choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                finish_reason = str(choice.get("finish_reason") or finish_reason)
                delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                thought = str(delta.get("reasoning_content") or "")
                if thought:
                    reasoning.append(thought)
                    if callable(self.on_reasoning):
                        try:
                            self.on_reasoning(thought)
                        except Exception:
                            pass
                text = str(delta.get("content") or "")
                if text:
                    state.raw_chunks_seen += 1
                    content.append(text)
                    self.last_partial_text += text
                    if callable(self.on_token):
                        try:
                            self.on_token(text)
                        except Exception:
                            pass
                    normalized = self.stream_interceptor.provider_adapter.normalize_event(text)
                    token_count = normalized.token_count if normalized is not None else 1
                    result = self.stream_interceptor.engine.process_chunk(state, text, token_count)
                    if result.should_stop:
                        stopped_upstream = True
                        close = getattr(response, "close", None)
                        if callable(close):
                            close()
                        break
        report = self.stream_interceptor.finalize_interception(
            state,
            content,
            upstream_cancel_requested=stopped_upstream,
            baseline_output_tokens=max_tokens,
        )
        return {
            "content": "".join(content),
            # Stream callbacks have already received these deltas.
            "reasoning_content": "".join(reasoning),
            "reasoning_streamed": True,
            "usage": usage,
            "finish_reason": finish_reason,
            "stream_interception": report.to_dict(),
        }

    def _request_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with _egress.urlopen("nim_planner_provider", request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        choices = body.get("choices") if isinstance(body.get("choices"), list) else []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        content = str(message.get("content") or "")
        if content:
            self.last_partial_text += content
        if content and callable(self.on_token):
            try:
                self.on_token(content)
            except Exception:
                pass
        return {
            "content": content,
            "reasoning_content": str(message.get("reasoning_content") or ""),
            "usage": body.get("usage") if isinstance(body.get("usage"), dict) else {},
            "finish_reason": choice.get("finish_reason"),
        }
