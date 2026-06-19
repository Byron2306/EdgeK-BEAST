"""
EdgeK BEAST Gateway - Context Economizer
Reduces oversized request context before governance and provider execution.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import copy
import logging

from app.kernel.perceive import EdgeKIR

logger = logging.getLogger(__name__)


@dataclass
class ContextEconomyResult:
    """Result of context economy processing."""

    ir: EdgeKIR
    changed: bool
    original_tokens: int
    final_tokens: int
    strategy: str
    messages_removed: int
    chars_removed: int
    notes: List[str]


class ContextEconomizer:
    """Policy-driven context compression for EdgeK IR messages."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.policies = policies or {}

    def economize(self, ir: EdgeKIR) -> ContextEconomyResult:
        meta_rules = self.policies.get("meta_rules", {})
        enabled = meta_rules.get("context_economizer_enabled", True)
        original_tokens = self._estimate_tokens(ir.messages)

        if not enabled:
            return self._unchanged(ir, original_tokens, "disabled", ["Context economizer disabled"])

        max_input = int(meta_rules.get("max_input_tokens_per_request", 8000))
        trigger_ratio = float(meta_rules.get("context_compression_trigger_ratio", 0.85))
        trigger_tokens = max(1, int(max_input * trigger_ratio))

        if original_tokens <= trigger_tokens:
            return self._unchanged(
                ir,
                original_tokens,
                "within_budget",
                [f"Input estimate {original_tokens} below trigger {trigger_tokens}"]
            )

        target_ratio = float(meta_rules.get("context_compression_ratio_target", 0.3))
        target_tokens = max(1, int(original_tokens * (1.0 - target_ratio)))
        if original_tokens > max_input:
            target_tokens = min(target_tokens, int(max_input * 0.9))
        target_tokens = max(1, min(target_tokens, trigger_tokens))

        min_recent_messages = int(meta_rules.get("context_economizer_min_recent_messages", 4))
        max_message_chars = int(meta_rules.get("context_economizer_max_message_chars", 12000))
        preserve_system = bool(meta_rules.get("context_economizer_preserve_system", True))

        messages, messages_removed, chars_removed, notes = self._compress_messages(
            messages=ir.messages or [],
            target_tokens=target_tokens,
            min_recent_messages=min_recent_messages,
            max_message_chars=max_message_chars,
            preserve_system=preserve_system
        )
        final_tokens = self._estimate_tokens(messages)

        metadata = copy.deepcopy(ir.metadata or {})
        metadata["context_economy"] = {
            "changed": True,
            "original_tokens": original_tokens,
            "final_tokens": final_tokens,
            "target_tokens": target_tokens,
            "within_target": final_tokens <= target_tokens,
            "within_input_budget": final_tokens <= max_input,
            "messages_removed": messages_removed,
            "chars_removed": chars_removed,
            "strategy": "deterministic_trim",
            "notes": notes
        }

        economized_ir = EdgeKIR(
            messages=messages,
            model=ir.model,
            max_tokens=ir.max_tokens,
            temperature=ir.temperature,
            top_p=ir.top_p,
            stream=ir.stream,
            tools=ir.tools,
            tool_choice=ir.tool_choice,
            stop=ir.stop,
            metadata=metadata
        )

        logger.info(
            "Context economized from %s to %s estimated tokens",
            original_tokens,
            final_tokens
        )

        return ContextEconomyResult(
            ir=economized_ir,
            changed=True,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            strategy="deterministic_trim",
            messages_removed=messages_removed,
            chars_removed=chars_removed,
            notes=notes
        )

    def _compress_messages(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        min_recent_messages: int,
        max_message_chars: int,
        preserve_system: bool
    ) -> Tuple[List[Dict[str, Any]], int, int, List[str]]:
        notes = []
        chars_removed = 0
        messages_removed = 0
        normalized = [copy.deepcopy(message) for message in messages]

        for message in normalized:
            content = message.get("content")
            if isinstance(content, str):
                compacted = " ".join(content.split())
                chars_removed += max(0, len(content) - len(compacted))
                message["content"] = compacted

        trimmed = []
        for message in normalized:
            content = message.get("content")
            if isinstance(content, str) and len(content) > max_message_chars:
                half = max(1, (max_message_chars - 80) // 2)
                omitted = len(content) - (half * 2)
                message["content"] = (
                    content[:half]
                    + f"\n\n[EdgeK context economy: {omitted} characters omitted from middle]\n\n"
                    + content[-half:]
                )
                chars_removed += max(0, omitted)
            trimmed.append(message)

        normalized = trimmed
        if self._estimate_tokens(normalized) <= target_tokens:
            if chars_removed:
                notes.append("Whitespace and long-message trimming reached target")
            return normalized, messages_removed, chars_removed, notes

        system_messages = []
        non_system_messages = []
        for message in normalized:
            if preserve_system and message.get("role") == "system":
                system_messages.append(message)
            else:
                non_system_messages.append(message)

        recent_count = min(len(non_system_messages), max(1, min_recent_messages))
        recent_messages = non_system_messages[-recent_count:]
        older_messages = non_system_messages[:-recent_count]

        kept_older = []
        for message in reversed(older_messages):
            candidate = system_messages + list(reversed(kept_older + [message])) + recent_messages
            if self._estimate_tokens(candidate) <= target_tokens:
                kept_older.append(message)
            else:
                messages_removed += 1
                chars_removed += len(str(message.get("content", "")))

        kept_older = list(reversed(kept_older))
        compressed = system_messages + kept_older + recent_messages

        if messages_removed:
            summary = {
                "role": "system",
                "content": (
                    f"[EdgeK context economy: {messages_removed} older messages omitted "
                    f"to satisfy the input budget.]"
                )
            }
            insert_at = len(system_messages)
            compressed.insert(insert_at, summary)
            notes.append(f"Omitted {messages_removed} older messages")

        while self._estimate_tokens(compressed) > target_tokens and len(compressed) > len(system_messages) + 1:
            removable_index = len(system_messages)
            if compressed[removable_index].get("content", "").startswith("[EdgeK context economy:"):
                removable_index += 1
            removed = compressed.pop(removable_index)
            messages_removed += 1
            chars_removed += len(str(removed.get("content", "")))

        if self._estimate_tokens(compressed) > target_tokens:
            compressed = self._force_trim_recent(compressed, target_tokens, preserve_system)
            notes.append("Applied final recent-message trimming")

        return compressed, messages_removed, chars_removed, notes

    def _force_trim_recent(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        preserve_system: bool
    ) -> List[Dict[str, Any]]:
        if not messages:
            return messages

        trimmed = [copy.deepcopy(message) for message in messages]
        protected_indexes = {
            index for index, message in enumerate(trimmed)
            if preserve_system and message.get("role") == "system"
        }

        iterations = 0
        while self._estimate_tokens(trimmed) > target_tokens and iterations < 100:
            iterations += 1
            candidates = [
                (index, len(str(message.get("content", ""))))
                for index, message in enumerate(trimmed)
                if index not in protected_indexes and isinstance(message.get("content"), str)
            ]
            if not candidates:
                break
            index, length = max(candidates, key=lambda item: item[1])
            if length <= 160:
                break
            content = trimmed[index]["content"]
            keep = max(80, int(length * 0.75))
            trimmed[index]["content"] = (
                content[:keep]
                + "\n\n[EdgeK context economy: tail omitted to fit budget]"
            )

        if self._estimate_tokens(trimmed) > target_tokens:
            for index, message in enumerate(trimmed):
                if index in protected_indexes or not isinstance(message.get("content"), str):
                    continue
                content = message["content"]
                if len(content) > 80:
                    message["content"] = (
                        content[:80]
                        + "\n\n[EdgeK context economy: aggressively trimmed to fit budget]"
                    )

        return trimmed

    def _unchanged(
        self,
        ir: EdgeKIR,
        tokens: int,
        strategy: str,
        notes: List[str]
    ) -> ContextEconomyResult:
        metadata = copy.deepcopy(ir.metadata or {})
        metadata.setdefault("context_economy", {
            "changed": False,
            "original_tokens": tokens,
            "final_tokens": tokens,
            "target_tokens": tokens,
            "within_target": True,
            "within_input_budget": True,
            "strategy": strategy,
            "notes": notes
        })
        unchanged_ir = EdgeKIR(
            messages=ir.messages,
            model=ir.model,
            max_tokens=ir.max_tokens,
            temperature=ir.temperature,
            top_p=ir.top_p,
            stream=ir.stream,
            tools=ir.tools,
            tool_choice=ir.tool_choice,
            stop=ir.stop,
            metadata=metadata
        )
        return ContextEconomyResult(
            ir=unchanged_ir,
            changed=False,
            original_tokens=tokens,
            final_tokens=tokens,
            strategy=strategy,
            messages_removed=0,
            chars_removed=0,
            notes=notes
        )

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total_chars = sum(len(str(message.get("content", ""))) for message in messages or [])
        return max(1, total_chars // 4)
