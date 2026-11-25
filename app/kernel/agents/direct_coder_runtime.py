"""Direct coding execution for BEAST Coder.

The selected coding model chooses individual governed tool actions. This class
does not instantiate AgentPlannerRuntime, any fallback planner, or a planning
subagent. The existing provider classes are used solely as model/action
transport adapters until native tool-call transport replaces the JSON codec.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import replace
from typing import Any

from app.kernel.agents import direct_coder_hooks
from app.kernel.agents.effect_ts_bridge import EffectUnavailable
from app.kernel.agents.tool_runtime import ToolExecutionFailed
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import PlannerDecisionError
from app.kernel.agents.verification_planner import verified_handoff_command
from app.kernel.compute.coder_crystal_feedback import PROFILE, verifier_outcome
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state

# Only workspace-bounded actions receive delegated autopilot authority.
# Promotion and external effects are never silently auto-approved here.
AUTOPILOT_TOOLS = frozenset({
    "workspace.index", "workspace.list", "workspace.search_text",
    "workspace.read_range", "worktree.bind", "worktree.replace_exact",
    "worktree.write_file", "worktree.verify", "worktree.sourceplan_draft",
    "worktree.diff", "worktree.status",
})

# Read-only workspace tools. Repeating one of these with arguments whose result
# the model already has is never progress; the runtime answers from memory.
READ_ONLY_TOOLS = frozenset({
    "workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range",
    "worktree.list", "worktree.read_file",
})
# Line-range reads. A bound worktree starts as a copy of the workspace, so both
# share coverage per path; an edit changes the file hash and resets it.
READ_RANGE_TOOLS = frozenset({"workspace.read_range", "worktree.read_file"})
MUTATION_TOOLS = frozenset({"worktree.replace_exact", "worktree.write_file"})
# Turns kept back so the model always gets to write its answer.
FINISH_RESERVE_TURNS = 2
# Consecutive duplicate reads before the runtime forces a written finish.
MAX_DUPLICATE_STREAK = 2
# File text carried verbatim between turns (newest reads first).
FILE_MEMORY_PROMPT_CHARS = 48000
FILE_MEMORY_STORE_CHARS = 64000
NOTES_PROMPT_CHARS = 6000
OBSERVATION_ITEM_CHARS = 3000
DEFAULT_READ_LINES = 200
# Earlier turns of the same operator session shown to the model.
CONVERSATION_MESSAGES = 8
CONVERSATION_MESSAGE_CHARS = 6000
CONVERSATION_TOTAL_CHARS = 16000
ANSWER_EVENTS = ("agent.coder.completed", "agent.coder.final_report", "agent.planner.completed")
# Output tokens for a finishing turn's written answer (NIM honours max_tokens_override).
ANSWER_MAX_TOKENS = 6144
ANSWER_TIMEOUT_SECONDS = 240.0
# Edit runs (a worktree is bound): files this long are not read top to bottom.
LARGE_FILE_LINES = 600
# Range reads allowed after binding before only narrow, targeted reads are accepted.
EDIT_READ_BUDGET = 6
EDIT_NARROW_READ_LINES = 120
# After this many reads without an edit, reading is closed until the model edits.
EDIT_READ_HARD_CAP = 14


EXCERPT_TOOL = "file_memory.excerpt"
EXCERPT_CHARS = 9000


def _memory_slice(state: dict[str, Any], path: str, start: int, end: int) -> str:
    """Exact lines start..end from one stored FILE MEMORY entry, or ''."""
    for item in reversed(list(state.get("file_memory") or [])):
        a, b = int(item.get("start") or 0), int(item.get("end") or 0)
        if item.get("path") == path and a <= start and end <= b:
            lines = str(item.get("content") or "").splitlines(keepends=True)
            return "".join(lines[start - a:end - a + 1])
    return ""


def _canonical_path(state: dict[str, Any], path: str) -> str:
    """One key per file: 'tester/beast' and 'beast' are the same file once a
    worktree with workspace prefix 'tester' is bound (run agent-72239d6a-7bf86a3f0516)."""
    path = str(path or "").strip()
    while path.startswith("./"):
        path = path[2:]
    prefix = str(state.get("path_prefix") or "").strip("/")
    if prefix and path.startswith(prefix + "/"):
        path = path[len(prefix) + 1:]
    return path


def _merge_ranges(ranges: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted([int(a), int(b)] for a, b in ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _requested_range(arguments: dict[str, Any]) -> tuple[str, int, int]:
    path = str(arguments.get("path") or "")
    try:
        start = max(1, int(arguments.get("start_line") or 1))
    except (TypeError, ValueError):
        start = 1
    try:
        count = max(1, min(int(arguments.get("line_count") or DEFAULT_READ_LINES), 1000))
    except (TypeError, ValueError):
        count = DEFAULT_READ_LINES
    return path, start, start + count - 1


def _visible_memory(state: dict[str, Any]) -> list[dict[str, Any]]:
    """FILE MEMORY entries that fit the prompt budget (newest first)."""
    shown, used = [], 0
    for item in reversed(list(state.get("file_memory") or [])):
        size = len(str(item.get("content") or "")) + 64
        if used + size > FILE_MEMORY_PROMPT_CHARS:
            continue
        used += size
        shown.append(item)
    return shown


def _call_key(tool_id: str, arguments: dict[str, Any]) -> str:
    return tool_id + ":" + json.dumps(arguments or {}, sort_keys=True, default=str)


class DirectCoderRuntime:
    """Single selected-model coding turn, persisted across /next calls."""

    def __init__(self, engine: Any, provider: Any, *, max_turns: int = 32, crystal_stack: Any = None):
        self.engine = engine
        self.provider = provider
        self._runtime_ready = False
        self.crystals = crystal_stack
        self.max_turns = max(1, min(int(max_turns), 64))

    def _state(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") or {}
        return dict(checkpoint.get("direct_coder") or {})

    def _save(self, run_id: str, state: dict[str, Any]) -> None:
        self.engine.merge_checkpoint(run_id, {"direct_coder": state})

    def _emit(self, run_id: str, event: str, **payload: Any) -> None:
        self.engine.emit(run_id, event, payload)

    def _transition(self, run_id: str, state: AgentRunState, *, error: str = "") -> None:
        current = self.engine.store.get_run(run_id) or {}
        if normalize_state(str(current.get("state") or "created")) is not state:
            self.engine.store.transition(run_id, state, error=error)

    def _snapshot(self, run_id: str) -> dict[str, Any]:
        return self.engine.store.get_run(run_id) or {}

    def _prompt(self, run: dict[str, Any], state: dict[str, Any], *, finishing: str = "") -> str:
        tools = self.engine.list_tools()
        allowed = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tid = str(tool.get("tool_id") or "")
            if not tid or tid.startswith(("sourceplan.promote", "promotion.")):
                continue
            if self.crystals is not None and tid == "worktree.run":
                continue
            allowed.append({
                "tool_id": tid,
                "description": str(tool.get("description") or "")[:230],
                "input_schema": tool.get("input_schema") or {},
            })
        request = run.get("request") or {}
        contract = verified_handoff_command(run) if self.crystals is not None else None
        contract_hint = ("The runtime captures the pre-edit test once the worktree is bound. "
                         "Use this exact worktree.verify command after editing: " + json.dumps(contract) + "\n"
                         if contract else "")
        observations = self._render_observations(state)
        targets = request.get("context_files") or []
        turn_no = int(state.get("turn") or 0) + 1
        remaining = max(0, self.max_turns - turn_no)
        finish_block = ""
        coverage = self._coverage(state)
        if targets and all((coverage.get(str(t)) or {}).get("complete") for t in targets):
            finish_block = ("ALL EXPLICIT FILES ARE FULLY READ. Do not read or list again. Next: either make "
                            "the requested edits in a bound worktree, or return COMPLETE with the written "
                            "analysis and suggested patches as unified diffs.\n")
        large = self._large_files(state)
        if large and (run.get("checkpoint") or {}).get("worktree_root") and not finishing:
            finish_block += ("LARGE FILES " + json.dumps(large) + ": do not read these top to bottom. To change "
                             "them, workspace.search_text for the exact function/symbol, read a narrow range "
                             f"(<= {EDIT_NARROW_READ_LINES} lines) around the hit, then worktree.replace_exact. "
                             "Edit one suggestion at a time.\n")
        if finishing and (run.get("checkpoint") or {}).get("worktree_root"):
            finish_block = (
                "FINISH NOW (" + finishing + "). This is an edit run in a bound worktree: no more reads, "
                "no new bind. Your next decision must be worktree.replace_exact (old_text copied exactly "
                "from FILE MEMORY or a file_memory.excerpt observation), worktree.verify after an edit, or "
                "decision_type complete/blocked stating which requested changes were made and which were "
                "not, with the reason. Inside the summary string never type a double-quote character.\n"
            )
        elif finishing:
            finish_block = (
                "FINISH NOW (" + finishing + "). Do NOT call workspace.list, workspace.index, "
                "workspace.search_text or workspace.read_range again. Return decision_type complete "
                "with summary = your written answer: findings with file:line references and the "
                "suggested patches as unified diffs (or exact replacement snippets). Base it only on "
                "the FILE MEMORY and NOTES below; say which line ranges you did not read. "
                "Inside the summary string never type a double-quote character (use single quotes or "
                "backticks): JSON-constrained decoding ends the string at the first double quote and "
                "cuts the answer off. "
                "If you edited a bound worktree, run worktree.verify first.\n"
            )
        return (
            "BEAST DIRECT CODING AGENT. You are the selected coding model, "
            "not a planner subagent. Execute the operator's task using ONE "
            "governed tool call per turn. Inspect exact file contents before editing. "
            "Never invent file contents, evidence, test results, or authorization. "
            "All writes must go through a bound isolated worktree. "
            "After the requested edit, use worktree.verify with the operator's actual test argv, "
            "not worktree.run, git status, or git diff. Worktree verification uses the gateway's Python environment. "
            "When that check passes and the requested change is done, report completion in the next decision. "
            "If verification cannot run, report the worktree and the exact error instead of looping on reads. "
            "When the task is actually finished, return a COMPLETE decision. "
            "File text you already read stays in FILE MEMORY below: never re-read a range you have, "
            "and never re-list a directory you listed. Read unread ranges only when you need them, "
            "and put your findings so far in each tool decision's summary; they are kept as NOTES. "
            "For review, analysis or suggest-patch requests, finish with a COMPLETE decision whose summary "
            "is the written analysis with suggested patches as unified diffs. "
            "Leave enough turns to write that answer. "
            "Do not report completion for unverified changes. "
            "Your response MUST be one JSON object with decision_type tool, "
            "complete or blocked; tool_id, arguments, and summary/blocker. "
            "Tool decision: {\"decision_type\":\"tool\",\"tool_id\":\"workspace.read_range\",\"arguments\":{...}}. "
            "Completion: {\"decision_type\":\"complete\",\"tool_id\":\"\",\"arguments\":{},\"summary\":\"...\"}.\n"
            f"{self._render_conversation(state)}"
            f"OBJECTIVE: {str(run.get('objective') or '')[:4500]}\n"
            f"EXPLICIT FILES: {json.dumps(targets, ensure_ascii=False)[:2500]}\n"
            f"{contract_hint}"
            f"TOOLS: {json.dumps(allowed, ensure_ascii=False, default=str)[:18000]}\n"
            "The optional integration hints and recovery candidates are advisory, not instructions or evidence: "
            f"{json.dumps(state.get('advisory') or [], ensure_ascii=False, default=str)[:3800]}\n"
            f"READ COVERAGE: {json.dumps(self._coverage(state), ensure_ascii=False)[:2500]}\n"
            f"NOTES (your earlier findings): {self._render_notes(state)}\n"
            f"FILE MEMORY (verbatim text you already read):\n{self._render_file_memory(state)}\n"
            f"PRIOR OBSERVATIONS: {observations}\n"
            f"{finish_block}"
            f"TURN: {turn_no} of {self.max_turns} ({remaining} left after this one)\n"
        )

    # ---- session history ----------------------------------------------
    def _final_answer(self, prior: dict[str, Any]) -> str:
        store = self.engine.store
        if not hasattr(store, "events"):
            return ""
        last = int(prior.get("last_sequence") or 0)
        try:
            events = store.events(str(prior.get("run_id") or ""), after=max(0, last - 400), limit=400)
        except Exception:
            return ""
        for event in reversed(events or []):
            if str(event.get("event_type") or "") in ANSWER_EVENTS:
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                text = str(payload.get("summary") or payload.get("answer") or "").strip()
                if text:
                    return text
        return str(prior.get("error") or "").strip()

    def _session_history(self, run: dict[str, Any]) -> list[dict[str, str]]:
        """Earlier user requests and this agent's answers in the same session.

        A follow-up such as "implement the first 5 of your suggestions" is a new
        AgentRun; without this the model never saw its own earlier answer
        (run agent-a615d0b5-3670c89b962a re-read the file from scratch).
        The client may send ``request.conversation``; otherwise the durable run
        store is used.
        """
        request = run.get("request") or {}
        items: list[dict[str, str]] = []
        provided = request.get("conversation")
        if isinstance(provided, list) and provided:
            for message in provided:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "")
                content = str(message.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    items.append({"role": role, "content": content[:CONVERSATION_MESSAGE_CHARS]})
        else:
            session_id = str(run.get("session_id") or "")
            store = self.engine.store
            if session_id and hasattr(store, "list_runs"):
                priors = [r for r in store.list_runs(session_id=session_id, limit=8)
                          if r.get("run_id") != run.get("run_id")
                          and float(r.get("created_at") or 0) <= float(run.get("created_at") or 1e18)]
                priors.sort(key=lambda r: float(r.get("created_at") or 0))
                for prior in priors[-(CONVERSATION_MESSAGES // 2):]:
                    objective = str(prior.get("objective") or "").strip()
                    if objective:
                        items.append({"role": "user", "content": objective[:CONVERSATION_MESSAGE_CHARS]})
                    answer = self._final_answer(prior)
                    if answer:
                        items.append({"role": "assistant", "content": answer[:CONVERSATION_MESSAGE_CHARS]})
        items = items[-CONVERSATION_MESSAGES:]
        while items and sum(len(m["content"]) for m in items) > CONVERSATION_TOTAL_CHARS:
            items.pop(0)
        return items

    @staticmethod
    def _render_conversation(state: dict[str, Any]) -> str:
        items = state.get("conversation") or []
        if not items:
            return ""
        lines = ["CONVERSATION SO FAR (earlier requests in this session and YOUR OWN earlier answers. "
                 "When the operator says 'your suggestions', 'the first N changes' or similar, they mean the "
                 "items in your last answer below; implement those, reading only the code they touch):"]
        for message in items:
            who = "OPERATOR" if message.get("role") == "user" else "YOU (BEAST)"
            lines.append(f"[{who}] {message.get('content')}")
        return "\n".join(lines) + "\n"

    async def _ask(self, run_id: str, prompt: str, run: dict[str, Any], turn: int, *,
                   quiet_thinking: bool = False, state: dict[str, Any] | None = None) -> PlannerDecision:
        """One model decision. Hidden reasoning can eat the whole output budget
        (run agent-eb1fe758-d4f81a5673c0: 8k chars of thinking, empty content), so a
        non-JSON reply is retried once with thinking off, and finishing turns
        run with thinking off so the written answer gets the output tokens."""
        thinking = getattr(self.provider, "enable_thinking", None)
        had_override = hasattr(self.provider, "max_tokens_override")
        previous_tokens = getattr(self.provider, "max_tokens_override", 0)
        answer_tokens = int(os.environ.get("BEAST_DIRECT_CODER_ANSWER_TOKENS", str(ANSWER_MAX_TOKENS)))
        previous_timeout = getattr(self.provider, "timeout_seconds", None)
        try:
            if thinking and state is not None and state.get("thinking_disabled"):
                # Thinking already overflowed once this run; don't pay for it every turn.
                self.provider.enable_thinking = False
            if quiet_thinking:
                if isinstance(previous_timeout, (int, float)):
                    self.provider.timeout_seconds = max(float(previous_timeout), ANSWER_TIMEOUT_SECONDS)
                # A written analysis with diffs does not fit the 2048-token action budget
                # (run agent-28fa487f-7118447e432f was cut off mid-string).
                self.provider.max_tokens_override = answer_tokens
                if thinking:
                    self.provider.enable_thinking = False
            try:
                return await self.provider.next_decision(prompt, run=run, turn=turn)
            except PlannerDecisionError as exc:
                if "dampened" in str(exc):
                    raise
                if getattr(self.provider, "enable_thinking", False):
                    reason = "thinking_overflow"
                    self.provider.enable_thinking = False
                    if state is not None:
                        state["thinking_disabled"] = True
                elif quiet_thinking and int(getattr(self.provider, "max_tokens_override", 0) or 0) < answer_tokens * 2:
                    reason = "answer_truncated"
                    self.provider.max_tokens_override = answer_tokens * 2
                else:
                    raise
                self._emit(run_id, "agent.coder.thinking_overflow_retry", reason=reason, message=str(exc)[:300])
                return await self.provider.next_decision(prompt, run=run, turn=turn)
        finally:
            if thinking is not None:
                self.provider.enable_thinking = thinking
            if isinstance(previous_timeout, (int, float)):
                self.provider.timeout_seconds = previous_timeout
            if had_override:
                self.provider.max_tokens_override = previous_tokens
            elif hasattr(self.provider, "max_tokens_override"):
                try:
                    delattr(self.provider, "max_tokens_override")
                except AttributeError:
                    pass

    # ---- read memory -------------------------------------------------
    @staticmethod
    def _render_observations(state: dict[str, Any]) -> str:
        """Render recent observations as valid JSON, each item bounded.

        File text is carried in FILE MEMORY, so read_range content is elided
        here. The old renderer tail-sliced the whole JSON list to 18000 chars,
        which dropped every read but the last one or two and made the model
        re-read the same ranges forever.
        """
        items = []
        for item in list(state.get("observations") or [])[-6:]:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            result = item.get("result")
            if item.get("tool_id") in READ_RANGE_TOOLS and isinstance(result, dict) and "content" in result:
                result = {k: v for k, v in result.items() if k not in {"content", "outline"}}
                result["content"] = "[kept in FILE MEMORY]"
                item["result"] = result
            rendered = json.dumps(item, default=str, ensure_ascii=False)
            if item.get("tool_id") == EXCERPT_TOOL:
                items.append(rendered[:EXCERPT_CHARS + 600])
                continue
            if len(rendered) > OBSERVATION_ITEM_CHARS:
                rendered = json.dumps({
                    "tool_id": item.get("tool_id"), "status": item.get("status"),
                    "arguments": item.get("arguments"), "error": str(item.get("error") or "")[:600],
                    "truncated_result_preview": rendered[:OBSERVATION_ITEM_CHARS - 800],
                }, default=str, ensure_ascii=False)
            items.append(rendered)
        return "[" + ", ".join(items) + "]"

    @staticmethod
    def _coverage(state: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for path, info in (state.get("reads") or {}).items():
            ranges = info.get("ranges") or []
            total = int(info.get("total_lines") or 0)
            read = sum(b - a + 1 for a, b in ranges)
            entry = {"read_lines": ["%d-%d" % (a, b) for a, b in ranges], "total_lines": total or None}
            if total:
                entry["complete"] = read >= total
                gaps, cursor = [], 1
                for a, b in ranges:
                    if a > cursor:
                        gaps.append("%d-%d" % (cursor, a - 1))
                    cursor = max(cursor, b + 1)
                if cursor <= total:
                    gaps.append("%d-%d" % (cursor, total))
                entry["unread_lines"] = gaps[:12]
            out[path] = entry
        for key in (state.get("seen_calls") or [])[-8:]:
            out.setdefault("_already_called", []).append(key[:200])
        return out

    @staticmethod
    def _render_notes(state: dict[str, Any]) -> str:
        notes = [str(n) for n in (state.get("notes") or []) if str(n).strip()]
        text = json.dumps(notes, ensure_ascii=False)
        if len(text) > NOTES_PROMPT_CHARS:
            kept: list[str] = []
            for note in reversed(notes):
                if len(json.dumps(kept + [note], ensure_ascii=False)) > NOTES_PROMPT_CHARS:
                    break
                kept.insert(0, note)
            text = json.dumps(kept, ensure_ascii=False)
        return text

    @staticmethod
    def _render_file_memory(state: dict[str, Any]) -> str:
        blocks: list[str] = []
        used = 0
        evicted: list[str] = []
        for item in reversed(list(state.get("file_memory") or [])):
            header = f"--- {item.get('path')} lines {item.get('start')}-{item.get('end')} ---\n"
            body = str(item.get("content") or "")
            if used + len(header) + len(body) > FILE_MEMORY_PROMPT_CHARS:
                evicted.append(f"{item.get('path')}:{item.get('start')}-{item.get('end')}")
                continue
            used += len(header) + len(body)
            blocks.insert(0, header + body)
        if evicted:
            blocks.append("(older ranges not shown to save space, rely on NOTES for them: "
                          + ", ".join(evicted[:12]) + ")")
        return "\n".join(blocks) if blocks else "(nothing read yet)"

    @staticmethod
    def _remember(state: dict[str, Any], tool_id: str, arguments: dict[str, Any],
                  observation: dict[str, Any] | None) -> None:
        if tool_id not in READ_ONLY_TOOLS:
            return
        result = (observation or {}).get("result") if isinstance(observation, dict) else None
        if str((observation or {}).get("status") or "completed") != "completed" or not isinstance(result, dict):
            return
        if tool_id not in READ_RANGE_TOOLS:
            seen = list(state.get("seen_calls") or [])
            key = _call_key(tool_id, arguments)
            if key not in seen:
                seen.append(key)
            state["seen_calls"] = seen[-32:]
            return
        path = _canonical_path(state, str(result.get("path") or arguments.get("path") or ""))
        if not path:
            return
        _, req_start, req_end = _requested_range(arguments)
        start = int(result.get("start_line") or req_start)
        end = int(result.get("end_line") or req_end)
        reads = dict(state.get("reads") or {})
        info = dict(reads.get(path) or {})
        sha = str(result.get("sha256") or "")
        if sha and info.get("sha256") and info.get("sha256") != sha:
            info = {}  # file changed: old coverage is stale
            state["file_memory"] = [m for m in (state.get("file_memory") or []) if m.get("path") != path]
        info["sha256"] = sha or info.get("sha256", "")
        if result.get("total_lines"):
            info["total_lines"] = int(result["total_lines"])
        info["ranges"] = _merge_ranges(list(info.get("ranges") or []) + [[start, max(start, end)]])
        reads[path] = info
        state["reads"] = reads
        memory = [m for m in (state.get("file_memory") or [])
                  if not (m.get("path") == path and m.get("start") >= start and m.get("end") <= end)]
        memory.append({"path": path, "start": start, "end": end,
                       "content": str(result.get("content") or "")[:16000]})
        while sum(len(str(m.get("content") or "")) for m in memory) > FILE_MEMORY_STORE_CHARS and len(memory) > 1:
            memory.pop(0)
        state["file_memory"] = memory

    @staticmethod
    def _duplicate_reason(state: dict[str, Any], tool_id: str, arguments: dict[str, Any]) -> str:
        if tool_id not in READ_ONLY_TOOLS:
            return ""
        if tool_id not in READ_RANGE_TOOLS:
            if _call_key(tool_id, arguments) in (state.get("seen_calls") or []):
                return f"{tool_id} was already called with these arguments; its result is in PRIOR OBSERVATIONS/NOTES."
            return ""
        path, start, end = _requested_range(arguments)
        path = _canonical_path(state, path)
        info = (state.get("reads") or {}).get(path) or {}
        total = int(info.get("total_lines") or 0)
        if total:
            end = min(end, total)
            if start > total:
                return f"{path} has only {total} lines."
        for a, b in info.get("ranges") or []:
            if a <= start and end <= b:
                in_memory = any(m.get("path") == path and int(m.get("start") or 0) <= start
                                and end <= int(m.get("end") or 0)
                                for m in _visible_memory(state))
                key = f"{path}:{start}-{end}"
                if not in_memory and key not in (state.get("rereads") or []):
                    # Text was evicted from FILE MEMORY; one re-read is allowed (e.g. to
                    # copy exact text for worktree.replace_exact), a second one is a loop.
                    state["rereads"] = list(state.get("rereads") or [])[-31:] + [key]
                    return ""
                return (f"Lines {start}-{end} of {path} were already read (they are in FILE MEMORY or "
                        f"summarised in NOTES). Do not re-read them.")
        return ""

    @staticmethod
    def _large_files(state: dict[str, Any]) -> dict[str, int]:
        return {path: int(info.get("total_lines") or 0) for path, info in (state.get("reads") or {}).items()
                if int(info.get("total_lines") or 0) > LARGE_FILE_LINES}

    def _edit_read_budget_reason(self, state: dict[str, Any], tool_id: str, arguments: dict[str, Any]) -> str:
        """Edit runs must not read a large file top to bottom (run agent-72239d6a-7bf86a3f0516
        read the 2780-line tester/beast twice over 30 turns and never edited)."""
        if tool_id not in READ_RANGE_TOOLS:
            return ""
        reads = int(state.get("reads_since_edit") or 0)
        path, start, end = _requested_range(arguments)
        path = _canonical_path(state, path)
        total = int(((state.get("reads") or {}).get(path) or {}).get("total_lines") or 0)
        if reads >= EDIT_READ_HARD_CAP:
            return ("Reading is closed for this edit: you have read enough. Make the change now with "
                    "worktree.replace_exact (copy the old text exactly from FILE MEMORY), or return "
                    "decision_type blocked saying what is missing.")
        if reads >= EDIT_READ_BUDGET and (total > LARGE_FILE_LINES or not total) and end - start + 1 > EDIT_NARROW_READ_LINES:
            return (f"{path} is too large to read top to bottom in an edit run ({total or 'many'} lines). "
                    "Use workspace.search_text for the function or symbol you must change (names are in "
                    "CONVERSATION SO FAR / NOTES), then read at most "
                    f"{EDIT_NARROW_READ_LINES} lines around the hit and edit with worktree.replace_exact.")
        return ""

    def _finishing_reason(self, state: dict[str, Any], turn: int) -> str:
        remaining_including_this = self.max_turns - turn
        if remaining_including_this <= FINISH_RESERVE_TURNS:
            return f"turn budget nearly spent: {remaining_including_this} turn(s) left"
        if int(state.get("duplicate_streak") or 0) >= MAX_DUPLICATE_STREAK:
            return "you keep requesting content you already have"
        return ""

    def _fallback_report(self, state: dict[str, Any], reason: str) -> str:
        coverage = self._coverage(state)
        notes = [str(n) for n in (state.get("notes") or []) if str(n).strip()]
        lines = [f"Direct Coder stopped without a model-written answer ({reason})."]
        for path, entry in coverage.items():
            if path.startswith("_"):
                continue
            lines.append(f"Read {path}: lines {', '.join(entry.get('read_lines') or [])}"
                         + (f" of {entry['total_lines']}" if entry.get("total_lines") else "")
                         + (f"; unread {', '.join(entry.get('unread_lines') or [])}" if entry.get("unread_lines") else ""))
        if notes:
            lines.append("Findings noted while reading:")
            lines.extend(f"- {n}" for n in notes[-12:])
        lines.append("Re-run with a narrower request (one function or line range) or a larger turn budget.")
        return "\n".join(lines)

    @staticmethod
    def _compact_observation(tool_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
        if tool_id == "workspace.index":
            summary = {"summary": result.get("summary"), "index_digest": result.get("index_digest"),
                       "files": [{"path": str(item.get("path") or "")}
                                 for item in (result.get("files") or [])[:24]
                                 if isinstance(item, dict)]}
        elif tool_id == "workspace.read_range":
            summary = {k: v for k, v in result.items() if k != "content"}
            summary["content"] = str(result.get("content") or "")[:16000]
        else:
            summary = result
        rendered = json.dumps(summary, default=str, ensure_ascii=False)
        if len(rendered) > 18000:
            summary = {"truncated_result_preview": rendered[:16000],
                       "truncated": True}
        return {"tool_id": tool_id,
                "status": str(observation.get("status") or "completed"),
                "arguments": dict(observation.get("arguments") or {}),
                "result": summary, "error": str(observation.get("error") or "")[:1200]}

    @staticmethod
    def _autopilot(run: dict[str, Any]) -> bool:
        request = run.get("request") or {}
        return str(request.get("autonomy") or "").lower() in {"autopilot", "auto"}

    def _approval(self, run_id: str, run: dict[str, Any], decision: PlannerDecision, spec: Any,
                  state: dict[str, Any], *, source: str = "model") -> tuple[str, bool]:
        """Return (approval_id, parked). Approval records stay in the durable store."""
        request = run.get("request") or {}
        if not getattr(spec, "requires_approval", False):
            return "", False
        if self._autopilot(run) and decision.tool_id in AUTOPILOT_TOOLS:
            approval_id = f"approval-{uuid.uuid4().hex[:16]}"
            paths = [str(decision.arguments[k]) for k in ("path", "target_path") if decision.arguments.get(k)]
            approval_request = {
                "request_id": approval_id, "run_id": run_id,
                "tool_id": decision.tool_id,
                "summary": "Direct coder delegated worktree action",
                "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
                "execution_target": decision.execution_target,
                "safe_arguments": decision.arguments,
                "affected_files": paths,
                "capabilities": [{"id": decision.tool_id, "paths": paths}],
                "autonomy": "autopilot",
            }
            self.engine.store.create_approval(run_id, approval_request)
            self.engine.store.resolve_approval(run_id, approval_id, {
                "approved": True, "scope": "run", "operator": "autopilot",
                "reason": "operator_delegated_workspace_bounded_tools",
            })
            self._emit(run_id, "agent.approval.autopilot_granted",
                       tool_id=decision.tool_id, approval_id=approval_id)
            return approval_id, False
        approval_id = f"approval-{uuid.uuid4().hex[:16]}"
        paths = [str(decision.arguments[k]) for k in ("path", "target_path") if decision.arguments.get(k)]
        self.engine.store.create_approval(run_id, {
            "request_id": approval_id, "run_id": run_id,
            "tool_id": decision.tool_id,
            "summary": f"Approve direct coder action: {decision.tool_id}",
            "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
            "execution_target": decision.execution_target,
            "safe_arguments": decision.arguments,
            "affected_files": paths,
            "capabilities": [{"id": decision.tool_id, "paths": paths}],
        })
        state["pending"] = {"approval_id": approval_id, "decision": decision.as_dict(), "source": source}
        self._save(run_id, state)
        self._emit(run_id, "agent.approval.requested",
                   approval_id=approval_id, tool_id=decision.tool_id)
        self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
        return approval_id, True

    async def run_one_turn(self, run_id: str) -> dict[str, Any]:
        try:
            return await self._run_turn(run_id)
        finally:
            if self.crystals is not None and str(self._snapshot(run_id).get("state")) != "completed":
                self.crystals.budget.mark_wall(run_id)

    async def _run_turn(self, run_id: str) -> dict[str, Any]:
        run = self._snapshot(run_id)
        if not run:
            raise KeyError(f"unknown AgentRun: {run_id}")
        status = normalize_state(str(run.get("state") or "created"))
        if status in TERMINAL_STATES:
            return run
        if not self._runtime_ready:
            executor = getattr(getattr(self.engine, "tool_runtime", None), "effect_executor", None)
            if executor is not None:
                try:
                    await asyncio.to_thread(executor.bridge.check_ready)
                except EffectUnavailable as exc:
                    self._emit(run_id, "agent.coder.runtime_unavailable", message=str(exc))
                    self._transition(run_id, AgentRunState.PAUSED, error=str(exc))
                    return self._snapshot(run_id)
            self._runtime_ready = True
        state = self._state(run_id)
        turn = int(state.get("turn") or 0)
        if turn >= self.max_turns:
            if not state.get("final_report_emitted"):
                state["final_report_emitted"] = True
                self._save(run_id, state)
                self._emit(run_id, "agent.coder.final_report", forced=True,
                           summary=self._fallback_report(state, "turn budget exhausted"))
            self._emit(run_id, "agent.coder.budget_exhausted", turns=turn)
            self._transition(run_id, AgentRunState.BUDGET_EXHAUSTED)
            return self._snapshot(run_id)
        request = run.get("request") or {}
        if self.crystals is None and request.get("crystal_trial_profile") == PROFILE:
            from app.kernel.agents.direct_coder_crystals import DirectCoderCrystals

            self.crystals = DirectCoderCrystals.prepare(self.engine, run, os.environ)
        if self.crystals is not None:
            self.crystals.budget.start(run_id)
        command = verified_handoff_command(run) if self.crystals is not None else None
        source = "model"
        if not state.get("started"):
            state["started"] = True
            try:
                state["conversation"] = self._session_history(run)
            except Exception as exc:  # history is advisory; never block the run on it
                state["conversation"] = []
                self._emit(run_id, "agent.integration.failed", capability="session_history",
                           stage="preflight", reason=type(exc).__name__)
            if state["conversation"]:
                self._emit(run_id, "agent.coder.history_attached",
                           messages=len(state["conversation"]),
                           chars=sum(len(m["content"]) for m in state["conversation"]))
            self._save(run_id, state)
            self._emit(run_id, "agent.coder.started",
                       engine="direct_coder_v1", model=run.get("model"))
            state["advisory"] = await direct_coder_hooks.prepare(self.engine, run_id, run)
            self._save(run_id, state)
        pending = state.get("pending")
        if isinstance(pending, dict):
            approval_id = str(pending.get("approval_id") or "")
            approval = self.engine.store.get_approval(run_id, approval_id) or {}
            if str(approval.get("status") or "").lower() != "approved":
                if str(approval.get("status") or "").lower() in {"rejected", "declined", "expired"}:
                    self._transition(run_id, AgentRunState.PAUSED,
                                     error="operator declined tool approval")
                else:
                    self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
                return self._snapshot(run_id)
            source = str(pending.get("source") or "model")
            raw = pending["decision"]
            decision = PlannerDecision(
                decision_type=PlannerDecisionType(raw["decision_type"]),
                tool_id=raw.get("tool_id", ""), arguments=raw.get("arguments") or {},
                execution_target=raw.get("execution_target") or "local",
            )
            state.pop("pending", None)
            state["resuming_approval_id"] = approval_id
            self._save(run_id, state)
        else:
            self._transition(run_id, AgentRunState.PLANNING)
            self._emit(run_id, "agent.coder.turn.started", turn=turn + 1)
            decision = None
            if self.crystals is not None:
                try:
                    decision = self.crystals.decision(run_id, run, state)
                except Exception as exc:
                    message = str(exc)[:1200]
                    self._emit(
                        run_id,
                        "agent.crystal.refused",
                        reason=f"activation_error:{type(exc).__name__}",
                        message=message,
                    )
                    self._emit(
                        run_id,
                        "agent.crystal.fail_closed",
                        reason="admitted_crystal_execution_fault",
                        exception_type=type(exc).__name__,
                        message=message,
                    )
                    decision = PlannerDecision(
                        decision_type=PlannerDecisionType.BLOCKED,
                        blocker=(
                            "Admitted crystal execution failed: "
                            f"{type(exc).__name__}: {message}"
                        ),
                    )
                    source = "crystal"
                if decision is not None:
                    source = "crystal"
                elif command and not (run.get("checkpoint") or {}).get("worktree_root"):
                    decision = PlannerDecision(
                        decision_type=PlannerDecisionType.TOOL, tool_id="worktree.bind",
                        arguments={"objective": str(run.get("objective") or "Direct Coder crystal preflight")},
                        rationale="Bind an isolated worktree before evidence-driven crystal routing.")
                    source = "runtime"
                elif command and (run.get("checkpoint") or {}).get("worktree_root") and "baseline_rc" not in state:
                    decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.verify",
                                               arguments={"command": command}, rationale="Capture the bound pre-edit verifier.")
                    source = "runtime"
                elif (command and "baseline_rc" in state and not state.get("target_inspection_attempted")
                      and not state.get("mutation_epoch")):
                    decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="workspace.read_range",
                                               arguments={"path": request["implementation_target"],
                                                          "start_line": 1, "line_count": 400},
                                               rationale="Bind the pre-edit source receipt.")
                    source = "runtime"
            if decision is None:
                try:
                    finishing = self._finishing_reason(state, turn)
                    if finishing and not state.get("finishing_announced"):
                        state["finishing_announced"] = True
                        self._emit(run_id, "agent.coder.finishing", reason=finishing,
                                   turns_left=self.max_turns - turn)
                    prompt = self._prompt(run, state, finishing=finishing)
                    decision = await self._ask(run_id, prompt, run, turn + 1, quiet_thinking=bool(finishing),
                                               state=state)
                    if (finishing and decision.decision_type is PlannerDecisionType.TOOL
                            and decision.tool_id in READ_ONLY_TOOLS and turn + 1 >= self.max_turns):
                        # Last turn and the model still wants to read: ask once more for the answer.
                        self._emit(run_id, "agent.coder.read_refused", tool_id=decision.tool_id,
                                   reason="final_turn_requires_answer")
                        state.setdefault("observations", []).append({
                            "tool_id": decision.tool_id, "status": "refused",
                            "arguments": dict(decision.arguments or {}),
                            "error": "Final turn: no more reads. Return the COMPLETE written analysis now.",
                        })
                        prompt = self._prompt(run, state, finishing="final turn, answer now")
                        decision = await self._ask(run_id, prompt, run, turn + 1, quiet_thinking=True,
                                                   state=state)
                    if self.crystals is not None:
                        self.crystals.budget.record_model_turn(run_id, prompt=prompt, decision=decision,
                                                               usage=(getattr(self.provider, "last_usage", None) or {}).get("usage"))
                except Exception as exc:
                    self._emit(run_id, "agent.coder.provider_paused",
                               reason=type(exc).__name__, message=str(exc)[:300])
                    self._transition(run_id, AgentRunState.PAUSED,
                                     error=f"coding model unavailable: {type(exc).__name__}")
                    return self._snapshot(run_id)
        if command and decision.decision_type is PlannerDecisionType.COMPLETE:
            epoch = int(state.get("mutation_epoch") or 0)
            if epoch and state.get("checked_epoch") != epoch:
                decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.verify",
                                           arguments={"command": command}, rationale="Verify the final bound worktree.")
                source = "runtime"
        self._emit(run_id, "agent.coder.decision", turn=turn + 1,
                   decision=decision.as_dict())

        if (
            source == "crystal"
            and decision.decision_type is PlannerDecisionType.TOOL
        ):
            self._emit(
                run_id,
                "agent.crystal.tool.dispatched",
                tool_id=decision.tool_id,
                path=str(decision.arguments.get("path") or ""),
                command=list(decision.arguments.get("command") or ()),
                turn=turn + 1,
            )

        if decision.decision_type is PlannerDecisionType.BLOCKED:
            self._transition(run_id, AgentRunState.PAUSED,
                             error=str(decision.blocker or "coding model requested help")[:400])
            self._emit(run_id, "agent.coder.paused", reason=decision.blocker)
            return self._snapshot(run_id)
        if decision.decision_type is PlannerDecisionType.COMPLETE:
            observations = state.get("observations") or []
            mutation_positions = [
                i for i, o in enumerate(observations)
                if str(o.get("tool_id") or "") in {
                    "worktree.replace_exact", "worktree.write_file"
                } and o.get("status") == "completed"
            ]
            mutated = bool(mutation_positions)
            last_mutation = max(mutation_positions, default=-1)
            verified = any(
                i > last_mutation and o.get("tool_id") == "worktree.verify"
                and o.get("status") == "completed"
                and isinstance(o.get("result"), dict)
                and o["result"].get("ok") is True
                and int(o["result"].get("returncode") or 0) == 0
                for i, o in enumerate(observations)
            )
            if command:
                mutated = bool(state.get("mutation_epoch"))
                checkpoint = (self._snapshot(run_id).get("checkpoint") or {})
                receipt = checkpoint.get("verification") or {}
                verified = (mutated and state.get("verified_epoch") == state["mutation_epoch"]
                            and state.get("baseline_binding") == checkpoint.get("worktree_root")
                            and not receipt.get("stale")
                            and (not receipt or receipt.get("mutation_epoch") == checkpoint.get("worktree_mutation_epoch")))
            if mutated and not verified:
                self._emit(run_id, "agent.coder.completion_refused",
                           reason="mutated_worktree_not_verified")
                state.setdefault("observations", []).append({
                    "tool_id": "completion", "status": "failed",
                    "error": "Run worktree.verify before claiming completion.",
                })
            else:
                self._emit(run_id, "agent.coder.completed", summary=decision.summary)
                self._transition(run_id, AgentRunState.COMPLETED)
                if self.crystals is not None:
                    try:
                        await self.crystals.complete(run_id, str(run.get("objective") or ""), bool(verified))
                    except Exception as exc:
                        self._emit(run_id, "agent.integration.failed", capability="coding_crystal.production",
                                   stage="postflight", reason=type(exc).__name__)
                return self._snapshot(run_id)
        elif decision.decision_type is PlannerDecisionType.TOOL:
            canonical = None
            if source == "model":
                note = str(decision.summary or decision.rationale or "").strip()
                if note:
                    notes = list(state.get("notes") or [])
                    notes.append(f"T{turn + 1}: {note[:1200]}")
                    state["notes"] = notes[-24:]
            if source == "model" and str(decision.execution_target or "").lower() in {
                    "isolated_worktree", "worktree", "bound_worktree"}:
                # The bound worktree is local; models echo the tool's description here
                # and the registry then rejects the call (run agent-a6dd269f-26b8a9060109).
                decision = replace(decision, execution_target="local")
            skip_reason = ""
            bound_root = str((self._snapshot(run_id).get("checkpoint") or {}).get("worktree_root") or "")
            if (source == "model" and decision.tool_id == "worktree.bind" and bound_root
                    and not state.get("resuming_approval_id")):
                # Re-binding discards the model's place and repeats the same reads.
                skip_reason = (f"A worktree is already bound at {bound_root}. Reuse it: use worktree.read_file / "
                               "worktree.replace_exact on it, or finish.")
            elif source == "model" and not state.get("resuming_approval_id"):
                skip_reason = self._duplicate_reason(state, decision.tool_id, decision.arguments)
                budget_reason = "" if skip_reason or not bound_root else self._edit_read_budget_reason(
                    state, decision.tool_id, decision.arguments)
                if budget_reason:
                    # Not a duplicate: do not push the run into the read-only finishing path.
                    self._emit(run_id, "agent.coder.read_refused", tool_id=decision.tool_id,
                               reason="edit_read_budget", detail=budget_reason[:400])
                    state.setdefault("observations", []).append({
                        "tool_id": decision.tool_id, "status": "refused",
                        "arguments": dict(decision.arguments or {}), "error": budget_reason,
                    })
                    state["turn"] = turn + 1
                    state["observations"] = list(state.get("observations") or [])[-16:]
                    self._save(run_id, state)
                    self._transition(run_id, AgentRunState.OBSERVING)
                    return self._snapshot(run_id)
                if not skip_reason and decision.tool_id in READ_ONLY_TOOLS and self._finishing_reason(state, turn):
                    if int(state.get("duplicate_streak") or 0) >= MAX_DUPLICATE_STREAK or turn + 1 >= self.max_turns:
                        skip_reason = "Reading is closed: write the final answer now."
            if skip_reason and bound_root and decision.tool_id in READ_RANGE_TOOLS:
                # Edit runs re-read to copy exact text for worktree.replace_exact. Serve the
                # range from FILE MEMORY once instead of refusing (run agent-3f382253-02e8174e0d86
                # was refused 20 times in a row and never edited).
                path, start, end = _requested_range(decision.arguments or {})
                path = _canonical_path(state, path)
                total = int(((state.get("reads") or {}).get(path) or {}).get("total_lines") or 0)
                end = min(end, total) if total else end
                key = f"{path}:{start}-{end}"
                excerpt = _memory_slice(state, path, start, end)
                if excerpt and key not in (state.get("served_from_memory") or []):
                    state["served_from_memory"] = list(state.get("served_from_memory") or [])[-31:] + [key]
                    self._emit(run_id, "agent.coder.read_served_from_memory", tool_id=decision.tool_id,
                               path=path, start_line=start, end_line=end)
                    state.setdefault("observations", []).append({
                        "tool_id": EXCERPT_TOOL, "status": "completed",
                        "requested_tool": decision.tool_id, "arguments": dict(decision.arguments or {}),
                        "result": {"path": path, "start_line": start, "end_line": end,
                                   "content": excerpt[:EXCERPT_CHARS],
                                   "note": "Exact current text from FILE MEMORY. Copy old_text from here "
                                           "into worktree.replace_exact now; do not read these lines again."},
                    })
                    state["turn"] = turn + 1
                    state["observations"] = list(state.get("observations") or [])[-16:]
                    self._save(run_id, state)
                    self._transition(run_id, AgentRunState.OBSERVING)
                    return self._snapshot(run_id)
            if skip_reason:
                state["duplicate_streak"] = int(state.get("duplicate_streak") or 0) + 1
                self._emit(run_id, "agent.coder.duplicate_read_skipped", tool_id=decision.tool_id,
                           arguments=dict(decision.arguments or {}), reason=skip_reason,
                           streak=state["duplicate_streak"])
                state.setdefault("observations", []).append({
                    "tool_id": decision.tool_id, "status": "skipped_duplicate",
                    "arguments": dict(decision.arguments or {}), "error": skip_reason,
                })
                if turn + 1 >= self.max_turns and not state.get("final_report_emitted"):
                    state["final_report_emitted"] = True
                    self._emit(run_id, "agent.coder.final_report", forced=True,
                               summary=self._fallback_report(state, "model kept reading on its last turn"))
                state["turn"] = turn + 1
                state["observations"] = list(state.get("observations") or [])[-16:]
                self._save(run_id, state)
                self._transition(run_id, AgentRunState.OBSERVING)
                return self._snapshot(run_id)
            if decision.tool_id in READ_ONLY_TOOLS:
                state["duplicate_streak"] = 0
            try:
                if command and decision.tool_id in {"worktree.replace_exact", "worktree.write_file"}:
                    path = str(decision.arguments.get("path") or "")
                    allowed_paths = {
                        str(request.get("implementation_target") or "")
                    }

                    if self.crystals is not None:
                        admitted_paths = getattr(
                            self.crystals,
                            "admitted_mutation_paths",
                            None,
                        )
                        if callable(admitted_paths):
                            allowed_paths.update(
                                admitted_paths(run_id)
                            )

                    allowed_paths.discard("")

                    if path not in allowed_paths:
                        raise ValueError(
                            "Trial edit path is not bound to the implementation "
                            "target or an admitted crystal fragment"
                        )

                    if state.get("baseline_binding") != (run.get("checkpoint") or {}).get("worktree_root"):
                        raise ValueError("The bound worktree changed after baseline verification")
                if command and decision.tool_id == "worktree.run":
                    raise ValueError("Use worktree.verify for the bound test contract in this trial")
                if command and decision.tool_id == "worktree.verify" and decision.arguments.get("command") != command:
                    raise ValueError("worktree.verify must use the bound command: " + " ".join(command))
                if command and decision.tool_id in {"worktree.replace_exact", "worktree.write_file"} and "baseline_rc" not in state:
                    raise ValueError("No measured pre-edit verification was recorded")

                spec = self.engine.tool_registry.get(decision.tool_id)
                if decision.tool_id.startswith(("sourceplan.promote", "promotion.")):
                    raise ValueError("promotion is not available to direct coder")
                args = self.engine.tool_registry.validate_arguments(spec, decision.arguments)
                # Never silently replace user-supplied model arguments.
                for key, value in decision.arguments.items():
                    if key not in args or args[key] != value:
                        raise ValueError(f"tool arguments changed during validation: {key}")
                if not state.get("resuming_approval_id"):
                    approval_id, parked = self._approval(run_id, run, decision, spec, state, source=source)
                    if parked:
                        return self._snapshot(run_id)
                else:
                    approval_id = state.pop("resuming_approval_id")
                self._transition(run_id, AgentRunState.EXECUTING_TOOL)
                observation = await self.engine.execute_tool(
                    run_id, decision.tool_id, args,
                    execution_target=decision.execution_target,
                    approval_id=approval_id,
                )
                canonical = observation
                entry = self._compact_observation(decision.tool_id, observation)
            except ToolExecutionFailed as exc:
                # ToolRuntime already emitted the canonical failure receipt.
                canonical = exc.observation.as_dict()
                entry = self._compact_observation(decision.tool_id, canonical)
            except Exception as exc:
                self._emit(run_id, "agent.coder.tool_rejected",
                           tool_id=decision.tool_id, message=str(exc)[:600])
                entry = {"tool_id": decision.tool_id,
                         "status": "failed", "error": str(exc)[:1200]}
            state.setdefault("observations", []).append(entry)
            if (decision.tool_id == "worktree.bind" and entry.get("status") == "completed"
                    and isinstance(canonical, dict) and isinstance(canonical.get("result"), dict)):
                state["path_prefix"] = str(canonical["result"].get("workspace_prefix") or "")
                state["reads_since_edit"] = 0
            if decision.tool_id in READ_ONLY_TOOLS and isinstance(canonical, dict):
                self._remember(state, decision.tool_id, dict(decision.arguments or {}), canonical)
                if decision.tool_id in READ_RANGE_TOOLS and bound_root:
                    state["reads_since_edit"] = int(state.get("reads_since_edit") or 0) + 1
            if decision.tool_id in MUTATION_TOOLS and entry.get("status") == "completed":
                state["reads_since_edit"] = 0
                edited = _canonical_path(state, str(decision.arguments.get("path") or ""))
                state["seen_calls"] = [k for k in (state.get("seen_calls") or []) if not k.startswith("worktree.")]
                if edited:
                    reads = dict(state.get("reads") or {})
                    reads.pop(edited, None)
                    state["reads"] = reads
                state["duplicate_streak"] = 0
            if self.crystals is not None and canonical is not None:
                self.crystals.budget.record_tool_call(
                    run_id, tool_id=decision.tool_id, status=entry["status"], source=source)
            if command and decision.tool_id in {"worktree.replace_exact", "worktree.write_file"} and entry["status"] == "completed":
                state["mutation_epoch"] = int(state.get("mutation_epoch") or 0) + 1
            if command and decision.tool_id == "workspace.read_range" and not state.get("mutation_epoch"):
                if (entry.get("arguments") or {}).get("path") == request.get("implementation_target") or source == "runtime":
                    state["target_inspection_attempted"] = True
            if command and decision.tool_id == "worktree.verify":
                rc = verifier_outcome(canonical or {}, command)
                epoch = int(state.get("mutation_epoch") or 0)
                if epoch:
                    state["checked_epoch"] = epoch
                    if rc == 0:
                        state["verified_epoch"] = epoch
                    else:
                        state.pop("verified_epoch", None)
                elif rc is not None:
                    state["baseline_rc"] = rc
                    state["baseline_binding"] = (run.get("checkpoint") or {}).get("worktree_root")
                    self._emit(run_id, "agent.integration.fired", capability="coding_crystal.baseline",
                               stage="execution", reason="canonical_pre_edit_verifier", returncode=rc)
                elif source == "runtime":
                    self._save(run_id, state)
                    self._transition(run_id, AgentRunState.PAUSED,
                                     error="The bound baseline verifier did not report executed tests.")
                    return self._snapshot(run_id)
            proposal = await direct_coder_hooks.recover_failed_edit(
                self.engine, run_id, run, state, decision, entry,
            )
            if proposal is not None:
                state["observations"].append(proposal)
        state["turn"] = turn + 1
        state["observations"] = list(state.get("observations") or [])[-16:]
        self._save(run_id, state)
        self._transition(run_id, AgentRunState.OBSERVING)
        return self._snapshot(run_id)
