"""Phase 5: Streaming Interception — stop paying for output after the governed action is complete or invalid.

This module implements incremental JSON/Action IR parsing during generation,
early stopping on complete schema-valid objects, repair/escalation on invalid streams,
and detection of repetition, explanation leakage, and output-budget exhaustion.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple


@dataclass
class StreamInterceptionState:
    """State of an in-progress streaming interception."""
    partial_output: str = ""
    tokens_emitted: int = 0
    early_stopped: bool = False
    stop_reason: str = ""
    governed_object_found: Optional[Dict[str, Any]] = None
    schema_valid: bool = False
    repetition_detected: bool = False
    explanation_leakage: bool = False
    budget_exhausted: bool = False
    output_budget_tokens: Optional[int] = None
    raw_chunks_seen: int = 0
    upstream_cancel_requested: bool = False
    measured_tokens_saved: int = 0
    repair_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StreamInterceptionResult:
    """Result of processing a streaming chunk."""
    should_continue: bool
    should_stop: bool
    stop_reason: str = ""
    partial_object: Optional[Dict[str, Any]] = None
    schema_valid: bool = False
    state: StreamInterceptionState = field(default_factory=StreamInterceptionState)


@dataclass(frozen=True)
class ProviderStreamChunk:
    """Normalized provider stream chunk."""
    text: str
    token_count: int = 1
    raw: Optional[Dict[str, Any]] = None
    finish_reason: str = ""


@dataclass
class UpstreamCancellation:
    """Tracks and performs upstream stream cancellation."""
    cancel_callback: Optional[Callable[[str], Any]] = None
    requested: bool = False
    reason: str = ""
    calls: int = 0

    async def cancel(self, reason: str) -> None:
        self.requested = True
        self.reason = reason
        self.calls += 1
        if self.cancel_callback is None:
            return
        result = self.cancel_callback(reason)
        if hasattr(result, "__await__"):
            await result


@dataclass(frozen=True)
class StreamRepairDecision:
    """Repair lifecycle decision after a stream stop."""
    action: str  # "accept" | "repair" | "escalate"
    reason: str
    repaired_object: Optional[Dict[str, Any]] = None
    repair_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "stream_repair_decision",
            "version": "1.0",
            "action": self.action,
            "reason": self.reason,
            "repaired_object": self.repaired_object,
            "repair_prompt": self.repair_prompt,
        }


@dataclass(frozen=True)
class StreamSavingsMeasurement:
    """Measured token savings from stopping an upstream stream early."""
    baseline_output_tokens: Optional[int]
    emitted_tokens: int
    saved_tokens: int
    measurement_source: str
    early_stopped: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "stream_token_savings_measurement",
            "version": "1.0",
            "baseline_output_tokens": self.baseline_output_tokens,
            "emitted_tokens": self.emitted_tokens,
            "saved_tokens": self.saved_tokens,
            "measurement_source": self.measurement_source,
            "early_stopped": self.early_stopped,
        }


@dataclass(frozen=True)
class StreamInterceptionReport:
    """Complete report for a provider stream interception run."""
    emitted_chunks: List[str]
    final_state: StreamInterceptionState
    cancellation: UpstreamCancellation
    repair_decision: StreamRepairDecision
    savings: StreamSavingsMeasurement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "stream_interception_report",
            "version": "1.0",
            "emitted_chunks": len(self.emitted_chunks),
            "stop_reason": self.final_state.stop_reason,
            "tokens_emitted": self.final_state.tokens_emitted,
            "raw_chunks_seen": self.final_state.raw_chunks_seen,
            "upstream_cancel_requested": self.cancellation.requested,
            "upstream_cancel_reason": self.cancellation.reason,
            "upstream_cancel_calls": self.cancellation.calls,
            "repair_decision": self.repair_decision.to_dict(),
            "savings": self.savings.to_dict(),
        }


class ProviderStreamAdapter:
    """Normalize provider-specific streaming events and cancel upstream streams."""

    async def iter_chunks(self, stream: AsyncIterable[Any]) -> AsyncIterable[ProviderStreamChunk]:
        async for event in stream:
            chunk = self.normalize_event(event)
            if chunk is not None:
                yield chunk

    def normalize_event(self, event: Any) -> Optional[ProviderStreamChunk]:
        if isinstance(event, ProviderStreamChunk):
            return event
        if isinstance(event, str):
            return ProviderStreamChunk(text=event, token_count=self._count_tokens(event))
        if not isinstance(event, dict):
            return ProviderStreamChunk(text=str(event), token_count=1)

        text = self._extract_text(event)
        finish_reason = self._extract_finish_reason(event)
        if not text and not finish_reason:
            return None
        return ProviderStreamChunk(
            text=text,
            token_count=self._count_tokens(text) if text else 0,
            raw=event,
            finish_reason=finish_reason,
        )

    async def cancel_upstream(self, stream: Any, cancellation: UpstreamCancellation, reason: str) -> None:
        await cancellation.cancel(reason)
        closer = getattr(stream, "aclose", None)
        if closer is not None:
            result = closer()
            if hasattr(result, "__await__"):
                await result

    @staticmethod
    def _extract_text(event: Dict[str, Any]) -> str:
        choices = event.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
            message = first.get("message") if isinstance(first.get("message"), dict) else {}
            return str(delta.get("content") or message.get("content") or first.get("text") or "")
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            return str(delta.get("text") or "")
        content = event.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "".join(parts)
        return str(event.get("text") or event.get("completion") or event.get("delta") or "")

    @staticmethod
    def _extract_finish_reason(event: Dict[str, Any]) -> str:
        choices = event.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            return str(choices[0].get("finish_reason") or "")
        return str(event.get("stop_reason") or event.get("finish_reason") or "")

    @staticmethod
    def _count_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(re.findall(r"\S+", text)))


class StreamingInterceptionEngine:
    """Phase 5 engine for incremental parsing and early stopping during generation."""

    # Common Action IR / governed object patterns
    GOVERNED_OBJECT_PATTERNS = [
        r'\{[^}]*"action"[^}]*\}',  # {"action": ...}
        r'\{[^}]*"tool"[^}]*\}',    # {"tool": ...}
        r'\{[^}]*"patch"[^}]*\}',   # {"patch": ...}
        r'\{[^}]*"result"[^}]*\}',  # {"result": ...}
    ]

    # Repetition detection: same phrase repeated 3+ times
    REPETITION_THRESHOLD = 3

    # Explanation leakage markers (text that shouldn't appear in governed output)
    EXPLANATION_MARKERS = [
        "here's how", "let me explain", "the reason is", "because",
        "first,", "second,", "third,", "in conclusion", "to summarize",
    ]

    def __init__(
        self,
        max_output_tokens: int = 4096,
        schema_contract: Optional[Dict[str, Any]] = None,
    ):
        self.max_output_tokens = max_output_tokens
        self.schema_contract = schema_contract  # Optional JSON schema for validation

    def process_chunk(
        self,
        state: StreamInterceptionState,
        chunk: str,
        token_count: int = 1,
    ) -> StreamInterceptionResult:
        """Process an incoming generation chunk and determine if streaming should continue.
        
        Returns a result indicating:
        - should_continue: keep generating
        - should_stop: stop generation (complete, invalid, or budget exhausted)
        - stop_reason: why we stopped
        """
        state.partial_output += chunk
        state.tokens_emitted += token_count

        # Check 1: Budget exhaustion
        output_budget = state.output_budget_tokens or self.max_output_tokens
        if state.tokens_emitted >= output_budget:
            state.early_stopped = True
            state.budget_exhausted = True
            state.stop_reason = "output_budget_exhausted"
            return StreamInterceptionResult(
                should_continue=False,
                should_stop=True,
                stop_reason=state.stop_reason,
                state=state,
            )

        # Check 2: Repetition detection
        if self._detect_repetition(state.partial_output):
            state.early_stopped = True
            state.repetition_detected = True
            state.stop_reason = "repetition_detected"
            return StreamInterceptionResult(
                should_continue=False,
                should_stop=True,
                stop_reason=state.stop_reason,
                state=state,
            )

        # Check 3: Explanation leakage
        if self._detect_explanation_leakage(state.partial_output):
            state.early_stopped = True
            state.explanation_leakage = True
            state.stop_reason = "explanation_leakage"
            return StreamInterceptionResult(
                should_continue=False,
                should_stop=True,
                stop_reason=state.stop_reason,
                state=state,
            )

        # Check 4: Complete governed object found
        governed_obj, is_valid = self._extract_governed_object(state.partial_output)
        if governed_obj is not None:
            state.governed_object_found = governed_obj
            state.schema_valid = is_valid
            if is_valid:
                state.early_stopped = True
                state.stop_reason = "governed_object_complete"
                return StreamInterceptionResult(
                    should_continue=False,
                    should_stop=True,
                    stop_reason=state.stop_reason,
                    partial_object=governed_obj,
                    schema_valid=True,
                    state=state,
                )
            else:
                # Invalid object: stop and escalate for repair
                state.early_stopped = True
                state.stop_reason = "governed_object_invalid_escalate"
                return StreamInterceptionResult(
                    should_continue=False,
                    should_stop=True,
                    stop_reason=state.stop_reason,
                    partial_object=governed_obj,
                    schema_valid=False,
                    state=state,
                )

        # No stopping condition met — continue generation
        return StreamInterceptionResult(
            should_continue=True,
            should_stop=False,
            state=state,
        )

    def _extract_governed_object(self, text: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Attempt to extract a complete governed object (JSON) from the text.
        
        Returns (object, is_schema_valid) or (None, False) if no complete object found.
        """
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "{[":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            obj = self._find_governed_object(value)
            if obj is not None:
                return obj, self._validate_against_contract(obj)
        
        return None, False

    def _validate_against_contract(self, obj: Dict[str, Any]) -> bool:
        """Validate a governed object against the schema contract (if provided)."""
        if self.schema_contract is None:
            # No contract — accept any dict with governed keys
            return isinstance(obj, dict) and len(obj) > 0
        return self._validate_schema(obj, self.schema_contract)

    def repair_or_escalate(self, result: StreamInterceptionResult) -> StreamRepairDecision:
        """Create a repair lifecycle decision from the final stream state."""
        state = result.state
        if state.governed_object_found is not None and state.schema_valid:
            decision = StreamRepairDecision(
                action="accept",
                reason="governed_object_complete",
                repaired_object=state.governed_object_found,
            )
        elif state.governed_object_found is not None:
            decision = StreamRepairDecision(
                action="repair",
                reason="governed_object_schema_invalid",
                repair_prompt="Repair the governed JSON object so it satisfies the declared schema.",
            )
        else:
            decision = StreamRepairDecision(
                action="escalate",
                reason=state.stop_reason or "no_governed_object_available",
                repair_prompt="Escalate to a full provider response or a stricter repair prompt.",
            )
        state.repair_events.append(decision.to_dict())
        return decision

    def measure_tokens_saved(
        self,
        state: StreamInterceptionState,
        baseline_output_tokens: Optional[int] = None,
    ) -> StreamSavingsMeasurement:
        """Measure saved output tokens against an explicit baseline or stream budget."""
        baseline = baseline_output_tokens
        source = "provider_reported_completion_tokens"
        if baseline is None:
            baseline = state.output_budget_tokens or self.max_output_tokens
            source = "output_budget"
        saved = max(0, int(baseline or 0) - int(state.tokens_emitted or 0)) if state.early_stopped else 0
        state.measured_tokens_saved = saved
        return StreamSavingsMeasurement(
            baseline_output_tokens=baseline,
            emitted_tokens=state.tokens_emitted,
            saved_tokens=saved,
            measurement_source=source,
            early_stopped=state.early_stopped,
        )

    @staticmethod
    def _find_governed_object(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            if any(key in value for key in ("action", "tool", "patch", "governed")):
                return value
            for nested in value.values():
                found = StreamingInterceptionEngine._find_governed_object(nested)
                if found is not None:
                    return found
            if "result" in value:
                result = value.get("result")
                return result if isinstance(result, dict) else value
        if isinstance(value, list):
            for nested in value:
                found = StreamingInterceptionEngine._find_governed_object(nested)
                if found is not None:
                    return found
        return None

    @classmethod
    def _validate_schema(cls, value: Any, schema: Dict[str, Any]) -> bool:
        if not isinstance(schema, dict):
            return True
        if "const" in schema and value != schema["const"]:
            return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        if "anyOf" in schema:
            return any(cls._validate_schema(value, item) for item in schema.get("anyOf") or [])
        if "oneOf" in schema:
            return sum(1 for item in schema.get("oneOf") or [] if cls._validate_schema(value, item)) == 1
        if "allOf" in schema:
            return all(cls._validate_schema(value, item) for item in schema.get("allOf") or [])

        expected_type = schema.get("type")
        if expected_type is not None and not cls._type_matches(value, expected_type):
            return False

        if isinstance(value, dict):
            required = schema.get("required") or []
            if any(key not in value for key in required):
                return False
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            for key, child_schema in properties.items():
                if key in value and not cls._validate_schema(value[key], child_schema):
                    return False
            if schema.get("additionalProperties") is False:
                allowed = set(properties)
                if any(key not in allowed for key in value):
                    return False
        if isinstance(value, list) and isinstance(schema.get("items"), dict):
            return all(cls._validate_schema(item, schema["items"]) for item in value)
        return True

    @staticmethod
    def _type_matches(value: Any, expected_type: Any) -> bool:
        if isinstance(expected_type, list):
            return any(StreamingInterceptionEngine._type_matches(value, item) for item in expected_type)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "null":
            return value is None
        return True

    def _detect_repetition(self, text: str) -> bool:
        """Detect if the same phrase or token sequence is repeated excessively."""
        # Simple heuristic: split into sentences/phrases and check for duplicates
        # In production, this would use n-gram analysis or embedding similarity
        words = text.lower().split()
        if len(words) < 10:
            return False
        
        # Check for 3+ consecutive repeated phrases (3+ words)
        for i in range(len(words) - 6):
            phrase1 = " ".join(words[i:i+3])
            phrase2 = " ".join(words[i+3:i+6])
            if phrase1 == phrase2:
                # Check if this repeats a third time
                if i + 9 <= len(words):
                    phrase3 = " ".join(words[i+6:i+9])
                    if phrase1 == phrase3:
                        return True
        return False

    def _detect_explanation_leakage(self, text: str) -> bool:
        """Detect if the output contains explanatory text that should be stripped."""
        text_lower = text.lower()
        for marker in self.EXPLANATION_MARKERS:
            if marker in text_lower:
                return True
        return False

    def create_initial_state(self, max_tokens: Optional[int] = None) -> StreamInterceptionState:
        """Create a fresh interception state for a new generation."""
        return StreamInterceptionState(
            partial_output="",
            tokens_emitted=0,
            early_stopped=False,
            output_budget_tokens=max_tokens or self.max_output_tokens,
        )


class StreamingComputeInterceptor:
    """High-level streaming wrapper that combines the engine with governor decisions."""

    def __init__(
        self,
        engine: StreamingInterceptionEngine = None,
        governor=None,  # ComputeGovernor (optional, for future integration)
        provider_adapter: ProviderStreamAdapter = None,
    ):
        self.engine = engine or StreamingInterceptionEngine()
        self.governor = governor
        self.provider_adapter = provider_adapter or ProviderStreamAdapter()

    def intercept_stream(
        self,
        token_iterator,  # Iterable yielding (token, token_count) tuples
        max_tokens: Optional[int] = None,
    ) -> Tuple[List[str], StreamInterceptionState]:
        """Intercept a token stream, stopping early when governed object is complete/invalid.
        
        Returns (emitted_tokens, final_state)
        """
        state = self.engine.create_initial_state(max_tokens)
        emitted: List[str] = []

        for token, token_count in token_iterator:
            result = self.engine.process_chunk(state, token, token_count)
            emitted.append(token)

            if result.should_stop:
                break

        return emitted, state

    async def intercept_provider_stream(
        self,
        provider_stream: AsyncIterable[Any],
        max_tokens: Optional[int] = None,
        cancellation: Optional[UpstreamCancellation] = None,
        baseline_output_tokens: Optional[int] = None,
        compute_gate: Any = None,
    ) -> StreamInterceptionReport:
        """Intercept and cancel a real provider stream at the first safe stop."""
        if self.governor is not None:
            if compute_gate is None:
                raise PermissionError("governed streaming requires the shared compute gate")
            if getattr(compute_gate, "mode", None) != self.governor.mode:
                raise PermissionError("streaming gate is not bound to the active governor mode")
        state = self.engine.create_initial_state(max_tokens)
        emitted: List[str] = []
        cancellation = cancellation or UpstreamCancellation()
        final_result = StreamInterceptionResult(True, False, state=state)

        async for chunk in self.provider_adapter.iter_chunks(provider_stream):
            state.raw_chunks_seen += 1
            if chunk.text:
                final_result = self.engine.process_chunk(state, chunk.text, chunk.token_count)
                emitted.append(chunk.text)
            if final_result.should_stop:
                state.upstream_cancel_requested = True
                await self.provider_adapter.cancel_upstream(provider_stream, cancellation, final_result.stop_reason)
                break
            if chunk.finish_reason:
                break

        repair = self.engine.repair_or_escalate(final_result)
        savings = self.engine.measure_tokens_saved(state, baseline_output_tokens)
        return StreamInterceptionReport(
            emitted_chunks=emitted,
            final_state=state,
            cancellation=cancellation,
            repair_decision=repair,
            savings=savings,
        )

    def estimate_tokens_saved(
        self,
        state: StreamInterceptionState,
        original_budget: int,
    ) -> int:
        """Estimate how many tokens were saved by early stopping."""
        if not state.early_stopped:
            return 0
        return self.engine.measure_tokens_saved(state, original_budget).saved_tokens
