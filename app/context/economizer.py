"""
EdgeK BEAST Gateway - Context Economizer
Reduces oversized request context before governance and provider execution.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import copy
import logging
import re

from app.context.budget import resolve_input_budget
from app.kernel.compute.perceive import EdgeKIR

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

    @staticmethod
    def _is_protected_message(message: Dict[str, Any]) -> bool:
        """Conservative exact-source boundary; unrecognized structured payloads stay intact."""
        if not isinstance(message, dict):
            return True
        if any(message.get(key) is True for key in
               ("exact_content", "preserve_exact", "source_integrity_required")):
            return True
        if message.get("content_integrity") in ("exact", "byte_exact", "protected"):
            return True
        if message.get("content_type") in (
            "source", "code", "diff", "patch", "json", "verification_receipt", "source_anchor"
        ):
            return True
        content = message.get("content")
        if not isinstance(content, str):
            return True
        if "```" in content:
            return True
        if re.search(r"(?m)^(?:[ \t]*(?:def |class |async def |from \S+ import |import |assert |return |raise |@pytest|@@ |diff --git|--- a/|\+\+\+ b/))", content):
            return True
        if re.search(r"(?m)^\s{4,}\S", content):
            return True
        if re.search(r"(?m)^\s*[\[{]\s*$|^\s*\"[^\"]+\"\s*:", content):
            return True
        if re.search(r"\bsha256:[0-9a-f]{64}\b", content):
            return True
        return False

    def _protected_messages_present(self, messages: List[Dict[str, Any]]) -> bool:
        return any(self._is_protected_message(message) for message in messages)

    def input_budget_for(self, ir: EdgeKIR) -> Dict[str, Any]:
        metadata = ir.metadata or {}
        return resolve_input_budget(
            model=str(ir.model or metadata.get("model") or ""),
            provider=str(metadata.get("provider") or ""),
            policies=self.policies,
            metadata=metadata,
            max_output_tokens=ir.max_tokens,
        )

    def economize(self, ir: EdgeKIR) -> ContextEconomyResult:
        meta_rules = self.policies.get("meta_rules", {})
        enabled = meta_rules.get("context_economizer_enabled", True)
        original_tokens = self._estimate_tokens(ir.messages or [])
        budget = self.input_budget_for(ir)
        max_input = int(budget["max_input_tokens"])
        target_paths = self._target_paths(ir)
        # Envelope-level exactness is an explicit contract for the *target*.
        # Linked (non-target) files may still be summarised to fit the model window.
        envelope_exact = (ir.metadata or {}).get("content_integrity") in (
            "exact", "byte_exact", "protected"
        )
        if envelope_exact:
            if original_tokens > max_input:
                messages, removed, chars_removed, notes = self._summarise_linked_context(
                    list(ir.messages or []), max_input, target_paths
                )
                final = self._estimate_tokens(messages)
                if final > max_input:
                    raise ValueError("protected_context_exceeds_input_budget")
                metadata = copy.deepcopy(ir.metadata or {})
                metadata["context_economy"] = {
                    "changed": True,
                    "original_tokens": original_tokens,
                    "final_tokens": final,
                    "target_tokens": max_input,
                    "within_input_budget": True,
                    "messages_removed": removed,
                    "chars_removed": chars_removed,
                    "strategy": "summarise_linked_keep_target",
                    "budget": budget,
                    "notes": notes,
                }
                economized = EdgeKIR(
                    messages=messages, model=ir.model, max_tokens=ir.max_tokens,
                    temperature=ir.temperature, top_p=ir.top_p, stream=ir.stream,
                    tools=ir.tools, tool_choice=ir.tool_choice, stop=ir.stop,
                    metadata=metadata,
                )
                return ContextEconomyResult(
                    ir=economized, changed=True, original_tokens=original_tokens,
                    final_tokens=final, strategy="summarise_linked_keep_target",
                    messages_removed=removed, chars_removed=chars_removed, notes=notes,
                )
            return self._unchanged(ir, original_tokens, "protected_exact_content", [
                "Exact envelope preserved byte-for-byte",
                f"Input budget {max_input} from {budget['source']}",
            ])

        ir = self._apply_compression_tiers(ir)
        original_tokens = self._estimate_tokens(ir.messages or []) if (ir.metadata or {}).get(
            "context_tiers") else original_tokens
        if not enabled:
            return self._unchanged(ir, original_tokens, "disabled", ["Context economizer disabled"])

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

        if self._protected_messages_present(ir.messages or []):
            target_tokens = max_input

        min_recent_messages = int(meta_rules.get("context_economizer_min_recent_messages", 4))
        max_message_chars = int(meta_rules.get("context_economizer_max_message_chars", 12000))
        preserve_system = bool(meta_rules.get("context_economizer_preserve_system", True))

        messages, messages_removed, chars_removed, notes = self._compress_messages(
            messages=ir.messages or [],
            target_tokens=target_tokens,
            min_recent_messages=min_recent_messages,
            max_message_chars=max_message_chars,
            preserve_system=preserve_system,
            target_paths=target_paths,
            hard_budget=max_input,
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
            "token_count_kind": "estimated_chars_div_4",
            "provider_tokens_measured": False,
            "budget": budget,
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
        preserve_system: bool,
        target_paths: Optional[set] = None,
        hard_budget: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int, int, List[str]]:
        notes = []
        chars_removed = 0
        messages_removed = 0
        # Coding lane: retain exact messages and current turn unchanged. Only
        # remove eligible older history; never rewrite code, system prompts,
        # structured tool results, or the latest user request.
        normalized = [copy.deepcopy(message) for message in messages]
        if self._estimate_tokens(normalized) <= target_tokens:
            return normalized, 0, 0, notes
        protected_indexes = {
            i for i, message in enumerate(normalized)
            if self._is_protected_message(message)
            or (preserve_system and message.get("role") == "system")
        }
        # Protect the latest user turn, even if it is ordinary prose.
        for i in range(len(normalized) - 1, -1, -1):
            if normalized[i].get("role") == "user":
                protected_indexes.add(i)
                break
        # Keep recent conversational continuity when possible, but allow
        # removal of old, unprotected messages first.
        eligible = [i for i in range(len(normalized)) if i not in protected_indexes]
        keep_recent = set(eligible[-max(0, min_recent_messages - 1):])
        removal_order = [i for i in eligible if i not in keep_recent] + [
            i for i in eligible if i in keep_recent
        ]
        removed = set()
        for i in removal_order:
            remaining = [m for j, m in enumerate(normalized) if j not in removed]
            if self._estimate_tokens(remaining) <= target_tokens:
                break
            removed.add(i)
            messages_removed += 1
            chars_removed += len(str(normalized[i].get("content", "")))
        compressed = [m for i, m in enumerate(normalized) if i not in removed]
        limit = int(hard_budget or target_tokens)
        if self._estimate_tokens(compressed) > target_tokens:
            linked_msgs, linked_removed, linked_chars, linked_notes = self._summarise_linked_context(
                compressed, limit, target_paths or set()
            )
            compressed = linked_msgs
            messages_removed += linked_removed
            chars_removed += linked_chars
            notes.extend(linked_notes)
        if self._estimate_tokens(compressed) > limit:
            raise ValueError("protected_context_exceeds_input_budget")
        if messages_removed and not any("Linked file" in n or "Omitted" in n for n in notes):
            notes.append(f"Omitted {messages_removed} eligible historical messages; protected content unchanged")
        elif messages_removed and not notes:
            notes.append(f"Omitted {messages_removed} eligible historical messages; protected content unchanged")
        return compressed, messages_removed, chars_removed, notes

    def _target_paths(self, ir: EdgeKIR) -> set:
        metadata = ir.metadata or {}
        paths = []
        for key in ("target_file", "target_path", "selected_file", "active_file"):
            if metadata.get(key):
                paths.append(str(metadata.get(key)))
        selection = metadata.get("selection") if isinstance(metadata.get("selection"), dict) else {}
        for key in ("path", "file", "file_path"):
            if selection.get(key):
                paths.append(str(selection.get(key)))
        files = metadata.get("context_files") or metadata.get("target_files") or []
        if isinstance(files, list) and files:
            first = files[0]
            paths.append(str(first.get("path") if isinstance(first, dict) else first))
        return {self._norm_path(path) for path in paths if path}

    @staticmethod
    def _norm_path(path: str) -> str:
        return str(path or "").replace("\\", "/").lstrip("./").lower()

    def _message_path(self, message: Dict[str, Any]) -> str:
        for key in ("path", "source", "file_path", "target_path"):
            if message.get(key):
                return self._norm_path(str(message.get(key)))
        return ""

    def _is_target_message(self, message: Dict[str, Any], target_paths: set) -> bool:
        role = str(message.get("context_role") or "")
        if role in {"workspace_files", "context_copy", "linked"}:
            # These carriers may contain both the target and linked files.
            return False
        if role in {"target", "selection", "user_prompt"}:
            return True
        if message.get("is_target") is True:
            return True
        path = self._message_path(message)
        return bool(path and path in target_paths)

    def _summarise_section(self, path: str, body: str, keep_chars: int = 800) -> str:
        lines = str(body or "").splitlines()
        head = "\n".join(lines[:40])
        if len(head) > keep_chars:
            head = head[:keep_chars]
        return (
            f"### {path}\n"
            f"[Linked file summarised to fit the model input budget; "
            f"{len(lines)} lines, {len(body)} chars. The target file and selection stay in full.]\n"
            f"{head}\n…"
        )

    def _summarise_message_content(self, content: str, target_paths: set, keep_chars: int = 800) -> Tuple[str, int]:
        """Summarise ###-delimited linked file sections; leave the target section intact."""
        text = str(content or "")
        pattern = re.compile(r"(?m)^### (.+)$")
        hits = list(pattern.finditer(text))
        if not hits:
            return self._summarise_section("linked", text, keep_chars), max(0, len(text) - keep_chars)
        parts = []
        removed = 0
        for index, hit in enumerate(hits):
            start = hit.end()
            end = hits[index + 1].start() if index + 1 < len(hits) else len(text)
            path = hit.group(1).strip()
            body = text[start:end]
            if self._norm_path(path) in target_paths or not target_paths:
                # When we cannot tell, keep the first section as the target if it is the only one
                # actually marked; otherwise summarise non-matching paths.
                if self._norm_path(path) in target_paths or (not target_paths and index == 0):
                    parts.append(f"### {path}{body}")
                    continue
            summarised = self._summarise_section(path, body, keep_chars)
            removed += max(0, len(body) - len(summarised))
            parts.append(summarised if not summarised.startswith("###") else summarised)
            # _summarise_section already includes the heading
        return "\n".join(parts), removed

    def _summarise_linked_context(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        target_paths: set,
    ) -> Tuple[List[Dict[str, Any]], int, int, List[str]]:
        notes: List[str] = []
        chars_removed = 0
        messages_removed = 0
        updated = [copy.deepcopy(m) for m in messages]
        originals = [str(m.get("content") or "") if isinstance(m, dict) else "" for m in messages]
        keep = 800
        while self._estimate_tokens(updated) > target_tokens and keep >= 40:
            for index, message in enumerate(updated):
                if self._estimate_tokens(updated) <= target_tokens:
                    break
                if self._is_target_message(message, target_paths):
                    continue
                role = str(message.get("context_role") or "")
                content = message.get("content")
                if not isinstance(content, str) or not content:
                    continue
                if role in {"user_prompt"}:
                    continue
                is_last_user = (
                    message.get("role") == "user"
                    and all(updated[j].get("role") != "user" for j in range(index + 1, len(updated)))
                    and role not in {"linked", "context_copy", "workspace_files"}
                )
                if is_last_user:
                    continue
                source = originals[index] if index < len(originals) else content
                new_content, removed = self._summarise_message_content(source, target_paths, keep_chars=keep)
                if removed <= 0 and "### " not in source:
                    new_content = self._summarise_section(self._message_path(message) or "linked", source, keep)
                    removed = max(0, len(source) - len(new_content))
                if new_content != content:
                    updated[index] = {**message, "content": new_content, "context_summarised": True}
                    chars_removed += max(0, len(content) - len(new_content))
                    notes.append("Summarised linked (non-target) file context to fit the model input budget")
            keep //= 2
        return updated, messages_removed, chars_removed, notes

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
            "token_count_kind": "estimated_chars_div_4",
            "provider_tokens_measured": False,
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

    def _apply_compression_tiers(self, ir: EdgeKIR) -> EdgeKIR:
        """Experimental tiers (BEAST_COMPRESSION_TIERS=1): only messages explicitly marked ``context_tier``."""
        from app.context.compression_tiers import default_router, tiers_enabled

        if not tiers_enabled() or not any(isinstance(m, dict) and m.get("context_tier") for m in ir.messages or []):
            return ir
        router = default_router()
        messages, receipts = [], []
        for message in ir.messages or []:
            tier = message.get("context_tier") if isinstance(message, dict) else None
            if tier not in ("longcodezip", "sqz") or not isinstance(message.get("content"), str):
                messages.append(message)
                continue
            try:
                out = router.compress(tier, message["content"], query=str(message.get("tier_query") or ""),
                                      edit_targets=message.get("edit_targets") or ())
            except PermissionError as exc:  # governor refused: keep the message unchanged
                receipts.append({"tier": tier, "refused": str(exc)})
                messages.append(message)
                continue
            passed = bool(out["fidelity"]["passed"])
            messages.append({**message, "content": out["content"] if passed else message["content"]})
            receipts.append({"tier": tier, "fidelity_passed": passed, "metrics": out["metrics"],
                             "governor_receipt_id": out["governor"]["receipt_id"]})
        metadata = copy.deepcopy(ir.metadata or {})
        metadata["context_tiers"] = receipts
        return EdgeKIR(messages=messages, model=ir.model, max_tokens=ir.max_tokens, temperature=ir.temperature,
                       top_p=ir.top_p, stream=ir.stream, tools=ir.tools, tool_choice=ir.tool_choice, stop=ir.stop,
                       metadata=metadata)

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total_chars = sum(len(str(message.get("content", ""))) for message in messages or [])
        return max(1, total_chars // 4)


def precheck_context_messages(
    messages,
    *,
    model: str = "",
    provider: str = "",
    policies: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the same economize path the provider stream will run; never raises on budget.

    Returns a ready flag, token counts, and the economy result so the handoff
    precheck and the stream cannot disagree on the budget.
    """
    meta = dict(metadata or {})
    if provider:
        meta.setdefault("provider", provider)
    ir = EdgeKIR(
        messages=[dict(item) for item in (messages or []) if isinstance(item, dict)],
        model=model, max_tokens=max_tokens, temperature=0.2, stream=True,
        metadata=meta,
    )
    economizer = ContextEconomizer(policies)
    budget = economizer.input_budget_for(ir)
    try:
        economy = economizer.economize(ir)
        return {
            "ready": True,
            "ok": True,
            "changed": economy.changed,
            "original_tokens": economy.original_tokens,
            "final_tokens": economy.final_tokens,
            "max_input_tokens": budget["max_input_tokens"],
            "context_window": budget["context_window"],
            "budget_source": budget["source"],
            "reason": "",
            "economy": economy,
        }
    except ValueError as exc:
        if "protected_context_exceeds_input_budget" not in str(exc):
            raise
        return {
            "ready": False,
            "ok": False,
            "changed": False,
            "original_tokens": economizer._estimate_tokens(ir.messages or []),
            "final_tokens": economizer._estimate_tokens(ir.messages or []),
            "max_input_tokens": budget["max_input_tokens"],
            "context_window": budget["context_window"],
            "budget_source": budget["source"],
            "reason": "protected_context_exceeds_input_budget",
            "economy": None,
        }
