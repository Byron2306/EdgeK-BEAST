"""Direct coding execution for BEAST Coder.

The selected coding model chooses individual governed tool actions. This class
does not instantiate AgentPlannerRuntime, any fallback planner, or a planning
subagent. The existing provider classes are used solely as model/action
transport adapters until native tool-call transport replaces the JSON codec.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
import shutil
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
    "worktree.list", "worktree.read_file", "worktree.search_text", "git.status",
})
# Line-range reads. A bound worktree starts as a copy of the workspace, so both
# share coverage per path; an edit changes the file hash and resets it.
READ_RANGE_TOOLS = frozenset({"workspace.read_range", "worktree.read_file"})
# Names models invent by mixing the workspace.* and worktree.* families (run
# agent-a615d0b5-e4e194547191 asked for worktree.read_range twice). Only applied when the
# target is registered and the requested id is not.
TOOL_ALIASES = {
    "worktree.read_range": "worktree.read_file",
    "worktree.read": "worktree.read_file",
    "worktree.search": "worktree.search_text",
    "worktree.grep": "worktree.search_text",
    "worktree.replace": "worktree.replace_exact",
    "worktree.edit": "worktree.replace_exact",
    "worktree.write": "worktree.write_file",
    "workspace.read_file": "workspace.read_range",
    "workspace.read": "workspace.read_range",
    "workspace.search": "workspace.search_text",
    "workspace.grep": "workspace.search_text",
    "workspace.list_files": "workspace.list",
}
# Decision fields models put inside tool arguments ("unknown tool arguments: summary"
# rejected two worktree.replace_exact edits in the same run).
META_ARGUMENT_KEYS = frozenset({
    "summary", "rationale", "reason", "reasoning", "explanation", "description", "notes",
    "note", "thought", "thoughts", "execution_target", "decision_type", "tool_id",
})
MUTATION_TOOLS = frozenset({"worktree.replace_exact", "worktree.write_file"})
# Turns kept back so the model always gets to write its answer.
FINISH_RESERVE_TURNS = 2
# Consecutive duplicate reads before the runtime forces a written finish.
MAX_DUPLICATE_STREAK = 2
# File text carried verbatim between turns (newest reads first).
# Holds two full big reads (2000 lines / 50KB each, plus line-number gutters).
FILE_MEMORY_PROMPT_CHARS = 110000
FILE_MEMORY_STORE_CHARS = 120000
NOTES_PROMPT_CHARS = 6000
OBSERVATION_ITEM_CHARS = 3000
DEFAULT_READ_LINES = 2000
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
# Consecutive back-to-back chunk reads of one large file before the runtime demands a search.
EDIT_SCAN_CHUNKS = 3


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


def _memory_span(state: dict[str, Any], path: str, text: str) -> tuple[int, int] | None:
    """Line span of ``text`` in the newest FILE MEMORY chunk of ``path`` that holds it once."""
    text = str(text or "").strip("\n")
    if not path or not text:
        return None
    for item in reversed(list(state.get("file_memory") or [])):
        content = str(item.get("content") or "")
        if item.get("path") == path and content.count(text) == 1:
            start = int(item.get("start") or 1) + content[:content.index(text)].count("\n")
            return start, start + text.count("\n")
    return None


def _progress_epoch(state: dict[str, Any]) -> int:
    """Checklist items finished so far; a region's rewrite count restarts when this moves."""
    return sum(1 for i in state.get("checklist") or [] if i.get("done") or i.get("skipped"))


def _edited_region(state: dict[str, Any], path: str, start: int, end: int) -> dict[str, Any] | None:
    """The region of ``path`` this run already edited that overlaps start..end, if any."""
    for region in reversed(list(state.get("edited_regions") or [])):
        if region.get("path") == path and int(region["start"]) <= end and start <= int(region["end"]):
            return region
    return None


def _apply_edit_to_memory(state: dict[str, Any], path: str, old_text: str, new_text: str) -> bool:
    """Patch FILE MEMORY for ``path`` after a successful replace instead of discarding it.

    The chunk holding ``old_text`` gets ``new_text`` and later chunks shift by the line delta,
    so the model can make the next change without re-reading the file (run
    agent-dc053ed7-ab50b5653dd6 re-read 1300 lines after its first edit). Returns False when
    the edit cannot be located in memory; the caller then drops the stale memory.
    """
    if not path or not old_text:
        return False
    memory = list(state.get("file_memory") or [])
    hit = None
    for i in range(len(memory) - 1, -1, -1):
        item = memory[i]
        content = str(item.get("content") or "")
        if item.get("path") == path and content.count(old_text) == 1:
            hit = i
            break
    if hit is None:
        return False
    item = dict(memory[hit])
    content = str(item.get("content") or "")
    idx = content.index(old_text)
    edit_start = int(item.get("start") or 1) + content[:idx].count("\n")
    old_end = edit_start + old_text.count("\n")
    delta = new_text.count("\n") - old_text.count("\n")
    item["content"] = content.replace(old_text, new_text, 1)
    item["end"] = int(item.get("end") or 0) + delta
    patched: list[dict[str, Any]] = []
    for i, other in enumerate(memory):
        if i == hit:
            patched.append(item)
            continue
        if other.get("path") != path:
            patched.append(other)
            continue
        a, b = int(other.get("start") or 0), int(other.get("end") or 0)
        if b < edit_start:
            patched.append(other)
        elif a > old_end:
            patched.append({**other, "start": a + delta, "end": b + delta})
        # chunks overlapping the edit (other than the patched one) are stale: drop them
    state["file_memory"] = patched
    for item in state.get("checklist") or []:
        rng = item.get("site_range")
        if rng and rng[0] == path and int(rng[1]) > old_end:
            item["site_range"] = [path, int(rng[1]) + delta, int(rng[2]) + delta]
            item["site"] = f"{path}:{int(str(item.get('site', ':0')).rsplit(':', 1)[-1] or 0) + delta}"
        elif rng and rng[0] == path and int(rng[2]) >= edit_start:
            item["site_range"] = [path, int(rng[1]), int(rng[2]) + delta]
    reads = dict(state.get("reads") or {})
    info = dict(reads.get(path) or {})
    if info:
        info["sha256"] = ""  # next read records the new hash without wiping memory
        if info.get("total_lines"):
            info["total_lines"] = int(info["total_lines"]) + delta
        info["ranges"] = _merge_ranges([[int(m["start"]), int(m["end"])] for m in patched
                                        if m.get("path") == path])
        reads[path] = info
        state["reads"] = reads
    return True


def _normalize_tool_call(tool_id: str, arguments: dict[str, Any],
                         schemas: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any], list[str]]:
    """Map invented tool names to registered ones and drop decision fields from arguments.

    ``schemas`` maps registered tool ids to their input schema. Returns the tool id,
    arguments and a list of human-readable changes (empty when nothing changed).
    """
    changes: list[str] = []
    tool_id = str(tool_id or "").strip()
    args = dict(arguments or {})
    if tool_id not in schemas and tool_id.lower() in schemas:
        changes.append(f"tool {tool_id} -> {tool_id.lower()}")
        tool_id = tool_id.lower()
    if tool_id not in schemas:
        target = TOOL_ALIASES.get(tool_id)
        if target in schemas:
            changes.append(f"tool {tool_id} -> {target}")
            tool_id = target
    schema = schemas.get(tool_id)
    if isinstance(schema, dict):
        for key in [k for k in args if k in META_ARGUMENT_KEYS
                    and k not in ((schema.get("properties") or {}) if isinstance(schema.get("properties"), dict) else {})]:
            args.pop(key)
            changes.append(f"dropped argument {key}")
        args, notes = _repair_arguments(tool_id, args, schema)
        changes.extend(notes)
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        closed = schema.get("additionalProperties") is False
        aliased = bool(changes)
        for key in list(args):
            if key in props:
                kind = (props.get(key) or {}).get("type") if isinstance(props.get(key), dict) else None
                value = args[key]
                if kind == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
                    args[key] = int(value.strip())
                    changes.append(f"{key} string -> integer")
                elif kind == "boolean" and isinstance(value, str) and value.strip().lower() in {"true", "false"}:
                    args[key] = value.strip().lower() == "true"
                    changes.append(f"{key} string -> boolean")
                continue
            if key in META_ARGUMENT_KEYS or (closed and aliased):
                args.pop(key)
                changes.append(f"dropped argument {key}")
    return tool_id, args, changes


# ---- OpenCode-style tool surface (t211u) ---------------------------------------------
# Flat names are what the prompt advertises; registered ids stay valid as aliases.
FLAT_TOOLS = {
    "read": ("worktree.read_file", "workspace.read_range"),
    "grep": ("worktree.search_text", "workspace.search_text"),
    "glob": ("worktree.list", "workspace.list"),
    "ls": ("worktree.list", "workspace.list"),
    "edit": ("worktree.replace_exact", "worktree.replace_exact"),
    "write": ("worktree.write_file", "worktree.write_file"),
    "shell": ("worktree.verify", "worktree.verify"),
    "bash": ("worktree.verify", "worktree.verify"),
}
TODO_TOOL_IDS = frozenset({"todowrite", "todo.write", "todo_write", "checklist.write"})
# Argument names other agents use -> ours (only applied when the schema has the target key).
ARG_ALIASES = {"offset": "start_line", "limit_lines": "line_count", "filePath": "path", "file_path": "path",
               "file": "path", "oldString": "old_text", "newString": "new_text", "old_string": "old_text",
               "new_string": "new_text", "pattern": "query", "content_text": "content", "cmd": "command"}
DOOM_LOOP_REPEATS = 3
DOOM_LOOP_WINDOW = 8            # identical calls are counted over the last N calls, not only in a row
DOOM_LOOP_FINISH = 3            # this many doom loops in one run: tools off, summarise and stop
REGION_EDIT_LIMIT = 2           # successful edits of one region before a further rewrite is refused
# Runtime progress lines a client may have stored as 'assistant' turns (run agent-a615d0b5-c09297ce06db
# got eight of these as its conversation and lost the suggestions answer it was asked to implement).
_PROGRESS_LINE = re.compile(r"^(Skipped repeat read|Verifying edits:|Wrapping up:|Located item|Batched edit|"
                            r"All checklist items handled|Same \S+ call|Unknown tool|Diagnostics in|"
                            r"Step limit reached|Act phase:|Checklist \d+/\d+|Edit reverted|\S+ needs the isolated worktree)")
_COMPLETION_REPORT = re.compile(r"Checklist: \d+/\d+ done|^Implemented the requested|^Direct Coder stopped", re.M)
# Older tool output beyond roughly the newest 40k tokens is trimmed from the prompt.
PROMPT_TOOL_OUTPUT_CHARS = 160_000
_PLAN_INTENT = re.compile(r"\b(suggest\w*|recommend\w*|review|analy[sz]\w*|explain|assess|audit|describe|"
                          r"summari[sz]e|what|why|how|list|ideas?)\b", re.IGNORECASE)
_CONTINUE_INTENT = re.compile(r"^\s*(continue|resume|keep going|go on|carry on|next|proceed)\b", re.IGNORECASE)
_SCOPE_EXTRA = {"__file__", "__name__", "__doc__", "__spec__", "__loader__", "__package__",
                "__builtins__", "__path__", "__annotations__", "__dict__", "__class__", "__debug__"}


def _flat_tool_id(tool_id: str, bound: bool) -> str:
    key = str(tool_id or "").strip()
    pair = FLAT_TOOLS.get(key.lower())
    return (pair[0] if bound else pair[1]) if pair else key


def _scope_diagnostics(source: str, line_range: tuple[int, int] | None = None,
                       functions: set[str] | None = None) -> tuple[list[str], set[str]]:
    """Per-function undefined names (pyflakes-style, stdlib symtable).

    A name a function reads that is not local, not from an enclosing function, not defined at
    module level and not a builtin raises NameError when the function runs (run
    agent-ae64e89c-20be546057f7: _is_safe_path used `workspace`, a local of
    command_reinstall_surfaces). Only functions overlapping ``line_range`` or named in
    ``functions`` are reported. Returns (messages, names of the functions checked)."""
    import ast
    import builtins
    import symtable

    try:
        tree = ast.parse(source)
        top = symtable.symtable(source, "<edit>", "exec")
    except (SyntaxError, ValueError) as exc:
        return [f"syntax error: {exc}"], set()
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in tree.body):
        return [], set()
    module_names = {sym.get_name() for sym in top.get_symbols()
                    if sym.is_assigned() or sym.is_imported() or sym.is_namespace()}
    spans: dict[tuple[str, int], int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            spans[(node.name, first)] = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
            spans[(node.name, node.lineno)] = int(getattr(node, "end_lineno", node.lineno) or node.lineno)

    def declared_globals(table: Any) -> None:
        for sym in table.get_symbols():
            if sym.is_declared_global() and sym.is_assigned():
                module_names.add(sym.get_name())
        for child in table.get_children():
            declared_globals(child)

    declared_globals(top)
    known = module_names | set(dir(builtins)) | _SCOPE_EXTRA
    messages: list[str] = []
    checked: set[str] = set()

    def visit(table: Any, outer: str = "") -> None:
        for child in table.get_children():
            name = child.get_name()
            start = int(child.get_lineno() or 0)
            end = spans.get((name, start), start)
            qual = f"{outer}.{name}" if outer else name
            wanted = ((line_range is not None and start <= line_range[1] and end >= line_range[0])
                      or (functions is not None and (qual in functions or name in functions)))
            if child.get_type() in ("function", "class") and wanted:
                checked.add(qual)
                for sym in child.get_symbols():
                    if (sym.is_referenced() and sym.is_global() and not sym.is_declared_global()
                            and sym.get_name() not in known):
                        line = next((n.lineno for n in ast.walk(tree) if isinstance(n, ast.Name)
                                     and n.id == sym.get_name() and start <= n.lineno <= end), start)
                        messages.append(f"line {line}: undefined name '{sym.get_name()}' in {qual}() "
                                        "(not local, not a parameter, not defined at module level)")
            visit(child, qual if child.get_type() in ("function", "class") else outer)

    visit(top)
    return messages, checked


def _repair_arguments(tool_id: str, args: dict[str, Any], schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fix arguments against a tool's JSON schema: rename common aliases, drop unknown keys
    (closed schemas), coerce integer/number/boolean/string/array values. Returns notes."""
    import shlex

    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if not props:
        return args, []
    notes: list[str] = []
    out = dict(args)
    for src, dst in ARG_ALIASES.items():
        if src in out and src not in props and dst in props and dst not in out:
            out[dst] = out.pop(src)
            notes.append(f"renamed argument {src} -> {dst}")
    if "limit" in out and "limit" not in props and "line_count" in props and "line_count" not in out:
        out["line_count"] = out.pop("limit")
        notes.append("renamed argument limit -> line_count")
    if schema.get("additionalProperties") is False:
        for key in [k for k in out if k not in props]:
            out.pop(key)
            notes.append(f"dropped unknown argument {key}")
    for key, value in list(out.items()):
        spec = props.get(key) if isinstance(props.get(key), dict) else {}
        kind = spec.get("type")
        try:
            if kind == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
                out[key] = int(value.strip())
            elif kind == "integer" and isinstance(value, float) and value.is_integer():
                out[key] = int(value)
            elif kind == "number" and isinstance(value, str):
                out[key] = float(value.strip())
            elif kind == "boolean" and isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0", "yes", "no"}:
                out[key] = value.strip().lower() in {"true", "1", "yes"}
            elif kind == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = str(value)
            elif kind == "array" and isinstance(value, str):
                text = value.strip()
                parsed = json.loads(text) if text.startswith("[") else (shlex.split(text) if key in {"command", "argv", "args"} else [text])
                out[key] = parsed
            else:
                continue
            notes.append(f"{key}: {type(value).__name__} -> {kind}")
        except (ValueError, json.JSONDecodeError):
            continue
    return out, notes


def _unknown_tool_message(tool_id: str, schemas: dict[str, dict[str, Any]]) -> str:
    import difflib

    valid = sorted(schemas)
    close = difflib.get_close_matches(str(tool_id), valid, n=2, cutoff=0.5)
    hint = f" Did you mean {' or '.join(close)}?" if close else ""
    return (f"Unknown tool {tool_id!r}.{hint} Use exactly one of these tool ids: "
            + ", ".join(valid))


# ---- edit runs: act phase, checklist, auto-verify ---------------------------
# Run agent-a615d0b5-5f90e8e56782 ("patch in your first 5") bound a worktree, read the
# target ranges, then spent 15 turns asking for the same lines and re-binding while
# thinking at length each turn. These pieces turn "I have the text" into an edit.
ACT_STALLS = 2                 # refused/served repeat requests before the act phase
ACT_EXCERPT_LINES = 160
ACT_EXCERPT_CHARS = 9000
AUTO_VERIFY_TIMEOUT = 120
_GUTTER = re.compile(r"^\s*\d{1,6}\| ?")
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_FIRST_N = re.compile(r"\b(?:first|top)\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b",
                      re.IGNORECASE)
_ITEM = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?\s*(?:(?:improvement|suggestion|recommendation|fix|change|patch)\s*#?\s*)?"
    r"(\d{1,2})\s*(?:[.):]|\s[\u2014\u2013-])\s*(?:\*\*)?\s*(.+?)\s*$",
    re.IGNORECASE,
)
_DONE = re.compile(r"\bDONE\s*#?\s*(\d{1,2})\b")
_SKIP = re.compile(r"\bSKIP\s*#?\s*(\d{1,2})\b\s*[:\-\u2014]?\s*([^\n]{0,200})")


def _requested_count(objective: str) -> int:
    match = _FIRST_N.search(str(objective or ""))
    if not match:
        return 0
    word = match.group(1).lower()
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word, 0)


def _inline_items_to_lines(text: str) -> str:
    """'... (1) Split X. (2) Add Y.' -> one item per line (run agent-11f1ac77-2dc79c62ff9e)."""
    return re.sub(r"(?:(?<=\s)|^)\((\d{1,2})\)\s+", lambda m: "\n" + m.group(1) + ") ", str(text or ""))


def _extract_suggestions(text: str) -> list[str]:
    """Numbered items 1..k from an earlier answer, in order, first occurrence each."""
    items = _extract_line_items(text)
    if len(items) < 2:
        inline = _extract_line_items(_inline_items_to_lines(text))
        if len(inline) > len(items):
            return inline
    return items


def _extract_line_items(text: str) -> list[str]:
    found: dict[int, str] = {}
    for line in str(text or "").splitlines():
        match = _ITEM.match(line)
        if not match:
            continue
        number = int(match.group(1))
        title = re.sub(r"\*\*|`", "", match.group(2)).strip(" *:-\u2014")
        title = re.sub(r"(?:\s+-\s+(?:done|skipped\b.*))+$", "", title, flags=re.IGNORECASE).strip()
        if number not in found and title and number == len(found) + 1:
            found[number] = title[:160]
    return [found[k] for k in sorted(found)]


_IDENT = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)\(?\)?`|\b([a-z][a-z0-9]*_[a-z0-9_]+)\b")
# Map unbound worktree reads to their workspace equivalents (run agent-a615d0b5-c230388cc73c
# was refused 'tool worktree.list requires an isolated worktree' four times before binding).
PARALLEL_TOOL_IDS = frozenset({"parallel", "multi_tool_use.parallel", "batch", "tools.parallel"})
# Inflected forms count too: 'proceed implementing your first 5 suggestions for patching.' (run
# agent-a615d0b5-c09297ce06db) matched none of the bare verbs and looked like a suggest-only run.
_EDIT_INTENT = re.compile(r"\b(implement\w*|fix(?:es|ed|ing)?|patch\w*|add(?:s|ed|ing)?|chang(?:e|es|ed|ing)|"
                          r"edit(?:s|ed|ing)?|refactor\w*|appl(?:y|ies|ied|ying)|writ(?:e|es|ing)|"
                          r"creat(?:e|es|ed|ing)|updat(?:e|es|ed|ing)|renam(?:e|es|ed|ing)|remov(?:e|es|ed|ing)|"
                          r"delet(?:e|es|ed|ing)|replac(?:e|es|ed|ing)|improv(?:e|es|ed|ing)|harden\w*|"
                          r"mak(?:e|es|ing))\b", re.IGNORECASE)
WORKTREE_CHECKPOINT_KEYS = ("worktree_task_id", "worktree_root", "worktree_branch",
                            "worktree_base_commit", "worktree_prefix")
UNBOUND_READ_MAP = {"worktree.list": "workspace.list", "worktree.read_file": "workspace.read_range",
                    "worktree.search_text": "workspace.search_text"}


def _suggestion_details(text: str, count: int) -> list[str]:
    """Body text of numbered items 1..count (between an item line and the next)."""
    if len(_extract_line_items(text)) < 2:
        text = _inline_items_to_lines(text)
    lines = str(text or "").splitlines()
    starts: list[int] = []
    for i, line in enumerate(lines):
        match = _ITEM.match(line)
        if match and int(match.group(1)) == len(starts) + 1:
            starts.append(i)
    starts.append(len(lines))
    return ["\n".join(lines[starts[k]:starts[k + 1]])[:2000] for k in range(min(count, len(starts) - 1))]


def _symbols(text: str) -> list[str]:
    """Code identifiers named in a suggestion, most specific first (functions before others)."""
    found: list[str] = []
    for match in _IDENT.finditer(str(text or "")):
        sym = (match.group(1) or match.group(2) or "").split(".")[-1]
        if len(sym) >= 5 and sym not in found and not sym.startswith(("e_g", "i_e")):
            found.append(sym)
    found.sort(key=lambda sym: 0 if sym.startswith(("command_", "_", "cmd_")) else 1)
    return found[:4]


def _build_checklist(objective: str, conversation: list[dict[str, str]]) -> list[dict[str, Any]]:
    count = _requested_count(objective)
    if count < 2:
        return []
    answers = [m.get("content") or "" for m in conversation or [] if m.get("role") == "assistant"]
    for answer in reversed(answers):
        items = _extract_suggestions(answer)
        if len(items) >= count:
            details = _suggestion_details(answer, count)
            # A later summary may repeat the titles without the detail; take each item's richest
            # description from any answer with the same title (run agent-ae64e89c-2880373c7da3).
            richer: dict[str, str] = {}
            for other in answers:
                other_items = _extract_suggestions(other)
                for k, d in enumerate(_suggestion_details(other, len(other_items))):
                    key = other_items[k][:30].lower()
                    if len(d) > len(richer.get(key, "")):
                        richer[key] = d
            out = []
            for i, title in enumerate(items[:count]):
                detail = details[i] if i < len(details) else title
                detail = max(detail, richer.get(title[:30].lower(), ""), key=len)
                out.append({"n": i + 1, "title": title, "done": False, "symbols": _symbols(detail)})
            return out
    return []


def _render_checklist(checklist: list[dict[str, Any]]) -> str:
    if not checklist:
        return ""
    lines = []
    for item in checklist:
        mark = "x" if item.get("done") else ("-" if item.get("skipped") else " ")
        extra = f" (skipped: {item.get('skip_reason')})" if item.get("skipped") else ""
        site = f" @ {item['site']}" if item.get("site") else ""
        lines.append(f"  [{mark}] {item['n']}. {item['title']}{site}{extra}")
    pending = [item for item in checklist if not item.get("done") and not item.get("skipped")]
    nxt = (f"NEXT: item {pending[0]['n']}, as the smallest working change (one function or a few "
           f"lines; its located code is in FILE MEMORY / EXACT TEXT; otherwise worktree.search_text, never "
           f"page through the file or restructure it). Several items at once: worktree.replace_exact "
           f"{{path, edits: [{{item: n, old_lines: 'A-B', new_text}}, ...]}} with non-overlapping spans. Put DONE {pending[0]['n']} at the start of the summary of "
           f"the edit that finishes it (it counts only if that edit succeeds). If the code it refers to "
           f"does not exist in the file, start the summary with SKIP {pending[0]['n']}: <reason> and move on."
           ) if pending else (
        "All items are done: run worktree.verify (or return complete; the runtime verifies).")
    return "CHECKLIST (one change at a time):\n" + "\n".join(lines) + "\n" + nxt + "\n"


_LINE_SPAN = re.compile(r"^\s*(\d{1,6})\s*(?:-|\.\.|to|,)\s*(\d{1,6})\s*$")


def _resolve_old_lines(state: dict[str, Any], arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """worktree.replace_exact by line span: {path, old_lines: 'A-B', new_text} -> old_text from FILE MEMORY.

    Python source is full of double quotes, and JSON-constrained decoding ends a string at
    the first unescaped one (run agent-bde5eaf1-b6bfb0fdcb1f lost five edits to
    'unknown tool arguments: dry_run", "false"))...'). Referencing the lines avoids copying them.
    Returns (arguments, error); error is '' on success or when no span was given.
    """
    args = dict(arguments or {})
    span = args.pop("old_lines", None)
    start, end = args.pop("start_line", None), args.pop("end_line", None)
    if span is None and start is not None and end is not None:
        span = f"{start}-{end}"
    if span is None:
        return dict(arguments or {}), ""
    match = _LINE_SPAN.match(str(span))
    if not match:
        return args, f"old_lines must look like 'START-END', got {span!r}"
    a, b = int(match.group(1)), int(match.group(2))
    if b < a or b - a > 400:
        return args, "old_lines span must be 1-400 lines with START <= END"
    path = _canonical_path(state, str(args.get("path") or ""))
    text = _memory_slice(state, path, a, b)
    if not text:
        return args, (f"lines {a}-{b} of {path} are not in FILE MEMORY (or the file changed since "
                      "you read them); read them first, then edit")
    following = [ln.strip() for ln in _memory_slice(state, path, b + 1, b + 4).splitlines() if ln.strip()]
    new_lines = [ln.strip() for ln in str(args.get("new_text") or "").splitlines()]
    hit = next((i for i in range(len(new_lines))
                if len(following) >= 3 and new_lines[i:i + len(following)] == following), None)
    if hit is not None:
        # new_text runs past line b: tell the model the exact span that makes the edit a
        # replacement instead of a duplication (run agent-a615d0b5-c09297ce06db only got
        # "extend old_lines" and re-sent the same edit).
        tail = len(new_lines) - hit
        suggest = b + tail
        while suggest > b and not _memory_slice(state, path, a, suggest):
            suggest -= 1
        return args, (f"new_text already contains lines {b + 1}-{b + 4} of {path} (from new_text line {hit + 1} "
                      f"on), which come right after old_lines {a}-{b}; applied as is, the edit would duplicate "
                      f"them. Fix: send the SAME edit again with old_lines '{a}-{suggest}' so the lines your "
                      "new_text rewrites are replaced, not repeated"
                      + ("" if suggest >= b + tail else f" (read lines {suggest + 1}-{b + tail} first)")
                      + f"; or end new_text before the line '{following[0][:80]}'.")
    if not args.get("old_text"):
        args["old_text"] = text.rstrip("\n")
    return args, ""


def _loose_match(state: dict[str, Any], path: str, old_text: str) -> str:
    """Exact text in FILE MEMORY that equals old_text after trimming each line's whitespace.

    OpenCode-style fallback for near-miss copies (indentation or trailing spaces). Returns ''
    unless exactly one window in memory matches."""
    want = [ln.strip() for ln in str(old_text or "").strip("\n").splitlines()]
    if not want or not any(want):
        return ""
    hits: set[str] = set()
    for item in state.get("file_memory") or []:
        if item.get("path") != path:
            continue
        lines = str(item.get("content") or "").splitlines()
        for i in range(0, max(0, len(lines) - len(want) + 1)):
            if [ln.strip() for ln in lines[i:i + len(want)]] == want:
                hits.add("\n".join(lines[i:i + len(want)]))
    return hits.pop() if len(hits) == 1 else ""


def _closest_lines(state: dict[str, Any], path: str, old_text: str, count: int = 12) -> str:
    """The numbered memory lines most similar to old_text's first line, for a retry without a re-read."""
    import difflib
    first = next((ln.strip() for ln in str(old_text or "").splitlines() if ln.strip()), "")
    if not first:
        return ""
    best = (0.0, None, 0)
    for item in state.get("file_memory") or []:
        if item.get("path") != path:
            continue
        lines = str(item.get("content") or "").splitlines()
        for i, line in enumerate(lines):
            ratio = difflib.SequenceMatcher(None, first, line.strip()).ratio()
            if ratio > best[0]:
                best = (ratio, item, i)
    if best[1] is None or best[0] < 0.5:
        return ""
    item, i = best[1], best[2]
    start = max(0, i - 2)
    lines = str(item.get("content") or "").splitlines()[start:start + count]
    return _gutter_excerpt("\n".join(lines), int(item.get("start") or 1) + start)


def _strip_gutter(text: str) -> tuple[str, bool]:
    lines = str(text or "").split("\n")
    body = [line for line in lines if line.strip()]
    if not body or not all(_GUTTER.match(line) for line in body):
        return text, False
    return "\n".join(_GUTTER.sub("", line, count=1) for line in lines), True


def _gutter_excerpt(content: str, start: int) -> str:
    return "\n".join(f"{start + i:>5}| {line}" for i, line in enumerate(str(content).split("\n")))


def _auto_verify_command(paths: list[str], watch_names: list[str] | None = None,
                         functions: dict[str, list[str]] | None = None) -> list[str]:
    """python -c script: py_compile every edited Python file, flag names the edits use but no
    one defines (run agent-ae64e89c-761611896972 called a helper it never wrote), then --help
    smoke for scripts."""
    script = (
        "import ast, builtins, py_compile, subprocess, sys\n"
        f"paths = {sorted(set(paths))!r}\n"
        f"watch = set({sorted(set(watch_names or []))[:200]!r})\n"
        "def undefined(src):\n"
        "    tree = ast.parse(src); defined = set(dir(builtins)); used = set()\n"
        "    for n in ast.walk(tree):\n"
        "        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): defined.add(n.name)\n"
        "        elif isinstance(n, ast.Name):\n"
        "            (used if isinstance(n.ctx, ast.Load) else defined).add(n.id)\n"
        "        elif isinstance(n, ast.arg): defined.add(n.arg)\n"
        "        elif isinstance(n, ast.alias): defined.add((n.asname or n.name).split('.')[0])\n"
        "        elif isinstance(n, ast.ExceptHandler) and n.name: defined.add(n.name)\n"
        "        elif isinstance(n, (ast.Global, ast.Nonlocal)): defined.update(n.names)\n"
        "        elif isinstance(n, ast.MatchAs) and n.name: defined.add(n.name)\n"
        "    return sorted((used - defined) & watch)\n"
        "from typing import Any\n"
        f"_SCOPE_EXTRA = set({sorted(_SCOPE_EXTRA)!r})\n"
        f"funcs = {dict((k, sorted(v)[:40]) for k, v in (functions or {}).items())!r}\n"
        + inspect.getsource(_scope_diagnostics) +
        "rc = 0\n"
        "for p in paths:\n"
        "    try:\n"
        "        head = open(p, 'r', encoding='utf-8', errors='replace').readline()\n"
        "    except OSError as exc:\n"
        "        print('missing', p, exc); rc = 1; continue\n"
        "    is_py = p.endswith('.py') or (head.startswith('#!') and 'python' in head)\n"
        "    if not is_py:\n"
        "        continue\n"
        "    try:\n"
        "        py_compile.compile(p, doraise=True); print('py_compile ok', p)\n"
        "    except py_compile.PyCompileError as exc:\n"
        "        print('py_compile FAILED', p, exc); rc = 1; continue\n"
        "    missing = undefined(open(p, encoding='utf-8', errors='replace').read()) if watch else []\n"
        "    if missing:\n"
        "        print('UNDEFINED names used by the edit (define or import them):', p, ', '.join(missing)); rc = 1\n"
        "    wanted = set(funcs.get(p) or [])\n"
        "    if wanted:\n"
        "        scope, _ = _scope_diagnostics(open(p, encoding='utf-8', errors='replace').read(), None, wanted)\n"
        "        for m in scope: print('SCOPE', p, m)\n"
        "        rc = rc or (1 if scope else 0)\n"
        "    if not p.endswith('.py'):\n"
        "        try:\n"
        "            r = subprocess.run([sys.executable, p, '--help'], capture_output=True, text=True, timeout=60)\n"
        "        except subprocess.TimeoutExpired:\n"
        "            print('--help timed out', p); rc = 1; continue\n"
        "        print('--help rc', r.returncode, p); print(r.stdout[-1500:]); print(r.stderr[-1500:])\n"
        "        rc = rc or r.returncode\n"
        "sys.exit(rc)\n"
    )
    return ["python", "-c", script]


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
        count = max(1, min(int(arguments.get("line_count") or DEFAULT_READ_LINES), 2000))
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
        bound = bool((run.get("checkpoint") or {}).get("worktree_root"))
        act_block = self._render_act_block(state) if bound and state.get("act_phase") else ""
        large = self._large_files(state)
        if large and (run.get("checkpoint") or {}).get("worktree_root") and not finishing:
            finish_block += ("LARGE FILES " + json.dumps(large) + ": do not read these top to bottom. To change "
                             "them, workspace.search_text for the exact function/symbol, read a narrow range "
                             f"(<= {EDIT_NARROW_READ_LINES} lines) around the hit, then worktree.replace_exact. "
                             "Edit one suggestion at a time.\n")
        if act_block and not finishing:
            finish_block = act_block
        elif finishing and (run.get("checkpoint") or {}).get("worktree_root"):
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
            "worktree.replace_exact also accepts old_lines 'START-END' (line numbers you have read) "
            "instead of old_text; the runtime copies those exact lines. "
            "Make independent tool calls in parallel in ONE decision: tool_id 'parallel' with arguments "
            "{calls: [{tool_id, arguments}, ...]} (reads/searches run concurrently; edits run in order, one "
            "file at a time). Prefer one big read (up to 2000 lines) or a search over many small reads. "
            "Keep summary text under 4 lines. "
            "Short tool names (preferred): read {path, start_line, line_count}, grep {query, path}, "
            "glob {path}, edit {path, old_lines|old_text, new_text}, write {path, content}, "
            "shell {command: [argv]}, todowrite {todos: [{content, status}]} (rewrite the whole list; "
            "status pending|in_progress|completed|cancelled). The long ids in TOOLS also work. "
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
            f"FILE MEMORY (verbatim text you already read):\n"
            f"{self._render_file_memory(state, budget=max(20000, min(FILE_MEMORY_PROMPT_CHARS, PROMPT_TOOL_OUTPUT_CHARS - len(observations) - len(self._render_notes(state)))))}\n"
            f"PRIOR OBSERVATIONS: {observations}\n"
            f"{_render_checklist(state.get('checklist') or [])}"
            f"{self._suggest_rules(state)}"
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

    def _pin_from_store(self, run: dict[str, Any], items: list[dict[str, str]]) -> list[dict[str, str]]:
        """The newest earlier answer in this session that lists numbered suggestions.

        Clients send only their last few messages; run agent-a615d0b5-c09297ce06db got eight
        progress lines and no suggestions, so 'implement your first 5' had no checklist."""
        store = getattr(self.engine, "store", None)
        session_id = str(run.get("session_id") or "")
        if not session_id or not hasattr(store, "list_runs"):
            return []
        try:
            priors = [r for r in store.list_runs(session_id=session_id, limit=40)
                      if r.get("run_id") != run.get("run_id")
                      and float(r.get("created_at") or 0) <= float(run.get("created_at") or 1e18)]
        except Exception:
            return []
        present = {m["content"][:200] for m in items}
        for prior in sorted(priors, key=lambda r: float(r.get("created_at") or 0), reverse=True):
            answer = self._final_answer(prior)
            if (answer and answer[:200] not in present and len(_extract_suggestions(answer)) >= 2
                    and not _COMPLETION_REPORT.search(answer)):
                return [{"role": "user", "content": str(prior.get("objective") or "")[:600], "pinned": "1"},
                        {"role": "assistant", "content": answer[:CONVERSATION_MESSAGE_CHARS], "pinned": "1"}]
        return []

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
                if role == "assistant" and _PROGRESS_LINE.match(content):
                    continue
                if role in {"user", "assistant"} and content:
                    items.append({"role": role, "content": content[:CONVERSATION_MESSAGE_CHARS]})
        else:
            session_id = str(run.get("session_id") or "")
            store = self.engine.store
            if session_id and hasattr(store, "list_runs"):
                priors = [r for r in store.list_runs(session_id=session_id, limit=40)
                          if r.get("run_id") != run.get("run_id")
                          and float(r.get("created_at") or 0) <= float(run.get("created_at") or 1e18)]
                priors.sort(key=lambda r: float(r.get("created_at") or 0))
                window = priors[-(CONVERSATION_MESSAGES // 2):]
                # Pin the newest earlier answer that lists numbered suggestions, so "implement the
                # first 3" still sees step 1's detail after later runs (run agent-ae64e89c-20be546057f7
                # lost it from the 8-message window and took 14 turns instead of 5).
                pinned: list[dict[str, str]] = []
                for prior in reversed(priors[:-(CONVERSATION_MESSAGES // 2)] if len(priors) > CONVERSATION_MESSAGES // 2 else []):
                    answer = self._final_answer(prior)
                    if answer and len(_extract_suggestions(answer)) >= 2 and not _COMPLETION_REPORT.search(answer):
                        pinned = [{"role": "user", "content": str(prior.get("objective") or "")[:600], "pinned": "1"},
                                  {"role": "assistant", "content": answer[:CONVERSATION_MESSAGE_CHARS], "pinned": "1"}]
                        break
                items.extend(pinned)
                for prior in window:
                    objective = str(prior.get("objective") or "").strip()
                    if objective:
                        items.append({"role": "user", "content": objective[:CONVERSATION_MESSAGE_CHARS]})
                    answer = self._final_answer(prior)
                    if answer:
                        items.append({"role": "assistant", "content": answer[:CONVERSATION_MESSAGE_CHARS]})
        if not any(m["role"] == "assistant" and len(_extract_suggestions(m["content"])) >= 2 for m in items):
            items = self._pin_from_store(run, items) + items
        pinned_items = [m for m in items if m.get("pinned")]
        rest = [m for m in items if not m.get("pinned")][-(CONVERSATION_MESSAGES):]
        while rest and sum(len(m["content"]) for m in pinned_items + rest) > CONVERSATION_TOTAL_CHARS + (
                sum(len(m["content"]) for m in pinned_items)):
            rest.pop(0)
        return [{"role": m["role"], "content": m["content"]} for m in pinned_items + rest]

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
    def _render_file_memory(state: dict[str, Any], budget: int = 0) -> str:
        budget = int(budget or FILE_MEMORY_PROMPT_CHARS)
        blocks: list[str] = []
        used = 0
        evicted: list[str] = []
        for item in reversed(list(state.get("file_memory") or [])):
            header = f"--- {item.get('path')} lines {item.get('start')}-{item.get('end')} (NNNNN| is the line number, not file text) ---\n"
            body = _gutter_excerpt(str(item.get("content") or ""), int(item.get("start") or 1))
            if used + len(header) + len(body) > budget:
                room = budget - used - len(header) - 200
                if room > 4000 and not evicted:
                    # Show the part that fits rather than nothing (big reads exceed the budget).
                    kept = body[:room].rsplit("\n", 1)[0]
                    shown_end = int(item.get("start") or 1) + kept.count("\n")
                    blocks.insert(0, header + kept + f"\n(lines {shown_end + 1}-{item.get('end')} not shown: "
                                  "use worktree.search_text to locate code there)")
                    used += len(header) + len(kept)
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
                       "content": str(result.get("content") or "")[:52000]})
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
    def _render_act_block(state: dict[str, Any]) -> str:
        excerpts = []
        for item in list(state.get("act_excerpts") or [])[-2:]:
            text = _memory_slice(state, item["path"], int(item["start"]), int(item["end"]))
            if text:
                excerpts.append(f"--- EXACT TEXT {item['path']} lines {item['start']}-{item['end']} ---\n"
                                + _gutter_excerpt(text.rstrip("\n"), int(item["start"]))[:ACT_EXCERPT_CHARS])
        return (
            "ACT NOW. You already have the text you need; reading and re-binding are closed for this "
            "step. Your next decision MUST be worktree.replace_exact (or worktree.write_file) for the "
            "NEXT change you have not made yet (never rewrite lines you already edited). Easiest form: arguments {path, old_lines: 'START-END', new_text} where "
            "START-END are line numbers from the EXACT TEXT below; the runtime fills old_text with those "
            "exact lines, so you do not copy them (the 'NNNN| ' gutter is not part of the file). "
            "new_text replaces those whole lines: keep their indentation. JSON tip, not a task: write every double quote inside new_text as \\\" "
            "or the edit is cut off; keep the file's own quote style. Several independent edits: one 'parallel' decision or edits:[...]. "
            "No explanations: summary under 4 lines. If all edits are done, return complete (the runtime verifies).\n" + ("\n".join(excerpts) + "\n" if excerpts else "")
        )

    def _reuse_session_worktree(self, run_id: str, run: dict[str, Any], state: dict[str, Any]) -> bool:
        """One long-lived worktree per session: adopt the newest earlier run's worktree if it
        still exists, so a follow-up request needs no bind (and earlier edits stay visible)."""
        if os.environ.get("BEAST_DIRECT_CODER_SESSION_WORKTREE", "1") == "0":
            return False
        if (run.get("checkpoint") or {}).get("worktree_root") or str(run.get("mode") or "agent") not in {"agent", "edit"}:
            return False
        session_id = str(run.get("session_id") or "")
        store = getattr(self.engine, "store", None)
        if not session_id or not hasattr(store, "list_runs") or not hasattr(self.engine, "merge_checkpoint"):
            return False
        try:
            priors = [r for r in store.list_runs(session_id=session_id, limit=8) if r.get("run_id") != run_id]
        except Exception:
            return False
        for prior in sorted(priors, key=lambda r: float(r.get("created_at") or 0), reverse=True):
            checkpoint = prior.get("checkpoint") or {}
            root = str(checkpoint.get("worktree_root") or "")
            if not root or not os.path.isdir(root) or not checkpoint.get("worktree_task_id"):
                continue
            if checkpoint.get("worktree_execution_target") not in (None, "", "local"):
                continue
            self.engine.merge_checkpoint(run_id, {k: checkpoint.get(k) for k in WORKTREE_CHECKPOINT_KEYS
                                                  if checkpoint.get(k) is not None})
            state["bound"] = True
            state["path_prefix"] = str(checkpoint.get("worktree_prefix") or "")
            state["reads_since_edit"] = 0
            state.setdefault("observations", []).append({
                "tool_id": "runtime.worktree", "status": "completed",
                "result": {"worktree_root": root, "reused_from": prior.get("run_id"),
                           "note": "This session's isolated worktree is already bound (with earlier edits). "
                                   "Do not call worktree.bind; read/edit with worktree.* tools."}})
            self._emit(run_id, "agent.coder.worktree_reused", worktree_root=root,
                       from_run=str(prior.get("run_id") or ""))
            return True
        return False

    async def _run_parallel(self, run_id: str, state: dict[str, Any], decision: PlannerDecision) -> None:
        """Execute one decision's independent calls: reads concurrently (asyncio.gather), edits
        queued in order (one file at a time), anything else refused with a reason."""
        calls = (decision.arguments or {}).get("calls")
        if not isinstance(calls, list) or not calls:
            calls = (decision.arguments or {}).get("tool_uses") or []
        schemas = self._tool_schemas()
        bound = bool(state.get("bound"))
        reads: list[tuple[str, dict[str, Any]]] = []
        edits: list[dict[str, Any]] = []
        refused: list[str] = []
        for raw in list(calls)[:12]:
            if not isinstance(raw, dict):
                continue
            tool_id = str(raw.get("tool_id") or raw.get("recipient_name") or raw.get("name") or "").strip()
            tool_id = tool_id.removeprefix("functions.")
            args = dict(raw.get("arguments") or raw.get("parameters") or {})
            if not bound and tool_id in UNBOUND_READ_MAP:
                tool_id = UNBOUND_READ_MAP[tool_id]
            if schemas:
                tool_id, args, _ = _normalize_tool_call(tool_id, args, schemas)
            if tool_id in MUTATION_TOOLS or tool_id in {"worktree.replace", "worktree.edit"}:
                if tool_id == "worktree.write_file":
                    refused.append("worktree.write_file: issue it on its own")
                    continue
                edits.append({**args, "item": args.get("item") or raw.get("item")})
            elif tool_id in READ_ONLY_TOOLS and (bound or not tool_id.startswith("worktree.")):
                if self._duplicate_reason(state, tool_id, args):
                    refused.append(f"{tool_id} {args.get('path') or args.get('query') or ''}: already in FILE MEMORY")
                    continue
                reads.append((tool_id, args))
            else:
                refused.append(f"{tool_id or '?'}: not allowed in parallel (issue it on its own)")

        async def one(tool_id: str, args: dict[str, Any]) -> tuple[str, dict[str, Any], Any]:
            try:
                return tool_id, args, await self.engine.execute_tool(
                    run_id, tool_id, args, execution_target="local", approval_id="")
            except Exception as exc:  # one failed read must not sink the others
                return tool_id, args, exc

        self._emit(run_id, "agent.coder.parallel", reads=len(reads), edits=len(edits), refused=len(refused))
        for tool_id, args, result in await asyncio.gather(*(one(t, a) for t, a in reads)):
            if isinstance(result, Exception):
                state.setdefault("observations", []).append(
                    {"tool_id": tool_id, "status": "failed", "arguments": args, "error": str(result)[:600]})
                continue
            self._remember(state, tool_id, args, result)
            if tool_id in READ_RANGE_TOOLS and bound:
                state["reads_since_edit"] = int(state.get("reads_since_edit") or 0) + 1
            state.setdefault("observations", []).append(self._compact_observation(tool_id, result))
        if edits:
            expanded, error = self._expand_batch(state, {"edits": edits}, str(decision.summary or ""))
            if error:
                refused.append(f"edits: {error}")
            else:
                state["queued_edits"] = list(state.get("queued_edits") or []) + expanded
        if refused:
            state.setdefault("observations", []).append(
                {"tool_id": "parallel", "status": "partial", "error": "; ".join(refused)[:1500]})

    async def _fold_or_end_turn(self, run_id: str, state: dict[str, Any], turn: int, kind: str) -> dict[str, Any]:
        """Runtime-answered decisions cost no extra model turn once per turn (folded)."""
        state["observations"] = list(state.get("observations") or [])[-16:]
        if state.get("fold_turn") != turn and turn + 1 < self.max_turns:
            state["fold_turn"] = turn
            self._emit(run_id, "agent.coder.skip_folded", tool_id=kind, kind=kind)
            self._save(run_id, state)
            return await self._run_turn(run_id)
        state["turn"] = turn + 1
        self._save(run_id, state)
        self._transition(run_id, AgentRunState.OBSERVING)
        return self._snapshot(run_id)

    def _todowrite(self, run_id: str, state: dict[str, Any], args: dict[str, Any]) -> None:
        """Replace the checklist with the model's full list (OpenCode todowrite)."""
        todos = args.get("todos") or args.get("items") or []
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except json.JSONDecodeError:
                todos = [{"content": line, "status": "pending"} for line in todos.splitlines() if line.strip()]
        old = {str(i.get("title") or "")[:60].lower(): i for i in state.get("checklist") or []}
        checklist = []
        for k, todo in enumerate(list(todos)[:20]):
            if isinstance(todo, str):
                todo = {"content": todo}
            if not isinstance(todo, dict):
                continue
            title = str(todo.get("content") or todo.get("title") or "").strip()[:160]
            if not title:
                continue
            status = str(todo.get("status") or "pending").lower()
            prev = old.get(title[:60].lower(), {})
            item = {"n": k + 1, "title": title, "done": status in {"completed", "done"},
                    "symbols": prev.get("symbols") or _symbols(title)}
            if status in {"cancelled", "canceled", "skipped"}:
                item["skipped"], item["skip_reason"] = True, str(todo.get("reason") or "cancelled")[:200]
            for key in ("site", "site_range"):
                if prev.get(key):
                    item[key] = prev[key]
            checklist.append(item)
        state["checklist"] = checklist
        state.setdefault("observations", []).append({
            "tool_id": "todowrite", "status": "completed",
            "result": {"todos": [{"n": i["n"], "title": i["title"],
                                  "status": "completed" if i.get("done") else ("cancelled" if i.get("skipped") else "pending")}
                                 for i in checklist]}})
        self._emit(run_id, "agent.coder.checklist", items=checklist,
                   done=sum(1 for i in checklist if i.get("done")),
                   skipped=sum(1 for i in checklist if i.get("skipped")), total=len(checklist))

    def _previous_checklist(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        """'continue' resumes the session's last checklist at its first incomplete item."""
        store = getattr(self.engine, "store", None)
        session_id = str(run.get("session_id") or "")
        if not session_id or not hasattr(store, "list_runs"):
            return []
        try:
            priors = [r for r in store.list_runs(session_id=session_id, limit=12) if r.get("run_id") != run.get("run_id")]
        except Exception:
            return []
        for prior in sorted(priors, key=lambda r: float(r.get("created_at") or 0), reverse=True):
            items = ((prior.get("checkpoint") or {}).get("direct_coder") or {}).get("checklist") or []
            if items and any(not i.get("done") and not i.get("skipped") for i in items):
                return [{k: v for k, v in dict(i).items() if k not in {"site", "site_range"}} for i in items]
        return []

    @staticmethod
    def _suggest_rules(state: dict[str, Any]) -> str:
        if not state.get("plan_run"):
            return ""
        return ("SUGGESTION RULES (plan run, no edits): number each suggestion '1.', '2.', ... on its own line. "
                "Each must name the exact function(s) in backticks and their line range(s) from FILE MEMORY, "
                "and describe one small concrete change (under ~40 changed lines) that can be implemented "
                "and verified on its own. No vague refactors such as 'split into modules' or 'add docstrings "
                "everywhere'.\n")

    def _step_limit_summary(self, state: dict[str, Any], reason: str = "") -> str:
        checklist = state.get("checklist") or []
        done = [f"{i['n']}. {i['title']}" for i in checklist if i.get("done")]
        left = [f"{i['n']}. {i['title']}" + (f" (skipped: {i.get('skip_reason')})" if i.get("skipped") else "")
                for i in checklist if not i.get("done")]
        edits = int(state.get("edit_count") or 0)
        lines = [(reason or f"Stopped at the step limit ({self.max_turns} turns)")
                 + f" with {edits} edit(s) in the worktree"
                 + (" (verified)." if state.get("verified_after_edit") else " (not verified).")]
        if edits and not state.get("verified_after_edit") and state.get("rollback_hint"):
            lines.append("To discard these edits: " + str(state["rollback_hint"]))
        if checklist:
            lines.append("Done: " + ("; ".join(done) if done else "nothing yet"))
            lines.append("Left: " + ("; ".join(left) if left else "nothing"))
        notes = list(state.get("notes") or [])[-3:]
        if notes:
            lines.append("Last notes: " + " | ".join(n[:200] for n in notes))
        lines.append("Say 'continue' to resume at the first item that is left.")
        return "\n".join(lines)

    async def _doom(self, run_id: str, state: dict[str, Any], turn: int, tool_id: str,
                    arguments: dict[str, Any], message: str) -> dict[str, Any]:
        """Refuse a repeated action; after DOOM_LOOP_FINISH of them the next decision ends the run."""
        state["doom_count"] = int(state.get("doom_count") or 0) + 1
        if state["doom_count"] >= DOOM_LOOP_FINISH:
            state["force_finish"] = True
            message += " This run has looped too often: your next decision ends it with a summary."
        self._emit(run_id, "agent.coder.doom_loop", tool_id=tool_id, repeats=DOOM_LOOP_REPEATS,
                   count=state["doom_count"], finishing=bool(state.get("force_finish")))
        state.setdefault("observations", []).append({"tool_id": tool_id, "status": "refused", "error": message})
        state["recent_calls"] = []
        self._note_stall(run_id, state, tool_id, arguments)
        return await self._fold_or_end_turn(run_id, state, turn, "doom_loop")

    @staticmethod
    def _record_edited_region(state: dict[str, Any], path: str, new_text: str, turn: int) -> None:
        span = _memory_span(state, path, new_text)
        if not span:
            return
        regions = [dict(r) for r in state.get("edited_regions") or []]
        hit = next((r for r in reversed(regions) if r.get("path") == path
                    and int(r["start"]) <= span[1] and span[0] <= int(r["end"])), None)
        epoch = _progress_epoch(state)
        if hit:
            same_item = int(hit.get("epoch") or 0) == epoch
            hit.update(start=min(int(hit["start"]), span[0]), end=max(int(hit["end"]), span[1]),
                       count=int(hit.get("count") or 1) + 1 if same_item else 1, turn=turn + 1, epoch=epoch)
        else:
            regions.append({"path": path, "start": span[0], "end": span[1], "count": 1, "turn": turn + 1,
                            "epoch": epoch})
        state["edited_regions"] = regions[-24:]

    def _bound_target(self, run_id: str, state: dict[str, Any], path: str) -> str:
        root = str((self._snapshot(run_id).get("checkpoint") or {}).get("worktree_root") or "")
        if not root or not path:
            return ""
        prefix = str(state.get("path_prefix") or "")
        candidates = [os.path.join(root, path)] + ([os.path.join(root, prefix, path)] if prefix else [])
        return next((c for c in candidates if os.path.isfile(c)), "")

    def _parseable_source(self, run_id: str, state: dict[str, Any], path: str) -> tuple[str, str] | None:
        """(target, source) of a Python file in the bound worktree that parses now, else None."""
        target = self._bound_target(run_id, state, path)
        if not target:
            return None
        try:
            with open(target, encoding="utf-8") as handle:
                source = handle.read()
        except (OSError, UnicodeDecodeError):
            return None
        if not (target.endswith(".py") or source.startswith("#!") and "python" in source.split("\n", 1)[0]):
            return None
        try:
            ast.parse(source)
        except (SyntaxError, ValueError):
            return None
        return target, source

    def _revert_if_syntax_broken(self, run_id: str, state: dict[str, Any], pre_edit: tuple[str, str],
                                 decision: PlannerDecision) -> str:
        """An edit that turns a parseable file into a SyntaxError is undone at once.

        Run agent-a615d0b5-c09297ce06db ended budget_exhausted with py_compile failing at line
        347 of its worktree copy; the worktree must never be left unparseable by one edit.
        Returns the error for the model ('' when the edit parses)."""
        target, before = pre_edit
        try:
            with open(target, encoding="utf-8") as handle:
                after = handle.read()
        except (OSError, UnicodeDecodeError):
            return ""
        try:
            ast.parse(after)
            return ""
        except (SyntaxError, ValueError) as exc:
            line = int(getattr(exc, "lineno", 0) or 0)
            msg = str(getattr(exc, "msg", "") or exc)
        tmp = target + ".beast-revert"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(before)
            shutil.copymode(target, tmp)   # keep the executable bit (tester/beast is 0755)
            os.replace(tmp, target)
        except OSError as exc:
            return ""
        context = ""
        if line:
            lines = after.splitlines()
            lo, hi = max(1, line - 4), min(len(lines), line + 3)
            context = "\n".join(f"{n:6d}| {lines[n - 1]}" for n in range(lo, hi + 1))
        path = str((decision.arguments or {}).get("path") or "")
        self._emit(run_id, "agent.coder.edit_reverted", path=path, line=line, message=msg[:200])
        return (f"Edit reverted: it made {path} fail to parse ({msg} at line {line}), so the runtime restored "
                "the file to its text before this edit (FILE MEMORY still shows that text). Lines around the "
                f"error after your edit were:\n{context}\nSend the edit again with balanced brackets and "
                "quotes, the same indentation, and old_lines covering every line new_text replaces.")

    def _edit_diagnostics(self, run_id: str, state: dict[str, Any], path: str, new_text: str) -> list[str]:
        """Diagnostics in the edit result (OpenCode LSP-style): scope errors in the edited code."""
        root = str((self._snapshot(run_id).get("checkpoint") or {}).get("worktree_root") or "")
        if not root or not path:
            return []
        prefix = str(state.get("path_prefix") or "")
        candidates = [os.path.join(root, path)] + ([os.path.join(root, prefix, path)] if prefix else [])
        target = next((c for c in candidates if os.path.isfile(c)), "")
        if not target:
            return []
        try:
            with open(target, encoding="utf-8", errors="replace") as handle:
                source = handle.read()
        except OSError:
            return []
        if not (target.endswith(".py") or source.startswith("#!") and "python" in source.split("\n", 1)[0]):
            return []
        idx = source.find(new_text) if new_text else -1
        if idx < 0:
            return []
        start = source[:idx].count("\n") + 1
        span = (start, start + new_text.count("\n"))
        messages, checked = _scope_diagnostics(source, span)
        funcs = dict(state.get("edited_funcs") or {})
        funcs[path] = sorted(set(funcs.get(path) or []) | checked)[:40]
        state["edited_funcs"] = funcs
        if messages:
            self._emit(run_id, "agent.coder.diagnostics", path=path, messages=messages[:8])
        return messages[:8]

    @staticmethod
    def _checklist_resolved(state: dict[str, Any]) -> bool:
        checklist = state.get("checklist") or []
        return bool(checklist and state.get("bound") and state.get("edited_paths")
                    and not state.get("queued_edits")
                    and all(i.get("done") or i.get("skipped") for i in checklist)
                    and not (state.get("auto_verify_epoch") == state.get("edit_count")
                             and not state.get("verified_after_edit")))

    @staticmethod
    def _checklist_summary(state: dict[str, Any]) -> str:
        parts = []
        for item in state.get("checklist") or []:
            mark = "done" if item.get("done") else f"skipped ({item.get('skip_reason') or 'n/a'})"
            parts.append(f"{item['n']}. {item['title']} - {mark}")
        return "Implemented the requested changes:\n" + "\n".join(parts)

    def _expand_batch(self, state: dict[str, Any], args: dict[str, Any],
                      summary: str) -> tuple[list[dict[str, Any]], str]:
        """{path, edits:[{item, old_lines|old_text, new_text, path?}]} -> resolved single edits.

        Every old_text is resolved from FILE MEMORY before the first edit runs, so later
        spans keep pointing at the text the model saw."""
        out: list[dict[str, Any]] = []
        spans: list[tuple[str, int, int]] = []
        for k, raw in enumerate(list(args.get("edits") or [])[:8]):
            if not isinstance(raw, dict):
                return [], f"edits[{k}] must be an object"
            one = {"path": raw.get("path") or args.get("path"), **{key: v for key, v in raw.items() if key != "path"}}
            item_n = one.pop("item", None)
            span = one.get("old_lines")
            resolved, error = _resolve_old_lines(state, one)
            if error:
                return [], f"edits[{k}]: {error}"
            old, had = _strip_gutter(str(resolved.get("old_text") or ""))
            new = str(resolved.get("new_text") or "")
            if had:
                new, _ = _strip_gutter(new)
            if not resolved.get("path") or not old:
                return [], f"edits[{k}] needs path and old_lines (or old_text)"
            match = _LINE_SPAN.match(str(span or ""))
            if match:
                key = (_canonical_path(state, str(resolved["path"])), int(match.group(1)), int(match.group(2)))
                if any(p == key[0] and not (key[2] < a or key[1] > b) for p, a, b in spans):
                    return [], f"edits[{k}] overlaps an earlier edit; use non-overlapping spans"
                spans.append(key)
            tag = f"DONE {item_n}" if str(item_n or "").isdigit() else ""
            out.append({"path": resolved["path"], "old_text": old, "new_text": new, "item": item_n,
                        "summary": (tag + " " + summary).strip() if tag else summary})
        return out, ""

    async def _prelocate(self, run_id: str, state: dict[str, Any]) -> None:
        """Find each checklist item's code with worktree.search_text and load it into FILE
        MEMORY right after binding, so the first edit turn already has the exact text."""
        cache: dict[str, dict[str, Any]] = {}
        paths_read: list[str] = []
        for item in state.get("checklist") or []:
            if item.get("done") or item.get("skipped") or item.get("site"):
                continue
            hit = None
            for sym in list(item.get("symbols") or [])[:3]:
                for query in (f"def {sym}(", sym):
                    if query not in cache:
                        try:
                            obs = await self.engine.execute_tool(
                                run_id, "worktree.search_text", {"query": query, "limit": 8},
                                execution_target="local", approval_id="")
                            cache[query] = obs if isinstance(obs, dict) else {}
                        except Exception:
                            cache[query] = {}
                    matches = ((cache[query].get("result") or {}).get("matches") or [])
                    if matches:
                        hit = matches[0]
                        break
                if hit:
                    break
            if not hit:
                continue
            path, line = str(hit.get("path") or ""), int(hit.get("line") or 1)
            start = max(1, line - 4)
            args = {"path": path, "start_line": start, "line_count": 90}
            try:
                obs = await self.engine.execute_tool(run_id, "worktree.read_file", args,
                                                     execution_target="local", approval_id="")
            except Exception:
                continue
            if not isinstance(obs, dict) or not isinstance(obs.get("result"), dict):
                continue
            self._remember(state, "worktree.read_file", args, obs)
            canon = _canonical_path(state, path)
            end = int(obs["result"].get("end_line") or start + 89)
            item["site"] = f"{canon}:{line}"
            item["site_range"] = [canon, start, end]
            paths_read.append(f"item {item['n']} -> {canon} lines {start}-{end}")
            self._emit(run_id, "agent.coder.prelocate", item=item["n"], path=canon, line=line,
                       start=start, end=end)
        if paths_read:
            state.setdefault("observations", []).append({
                "tool_id": "runtime.edit_sites", "status": "completed",
                "result": {"located": paths_read,
                           "hint": "The code for these items is in FILE MEMORY; edit with old_lines now."}})
            self._focus_next_site(run_id, state)

    def _focus_next_site(self, run_id: str, state: dict[str, Any]) -> None:
        """Show the next pending item's located code as EXACT TEXT and go straight to acting."""
        for item in state.get("checklist") or []:
            if item.get("done") or item.get("skipped"):
                continue
            rng = item.get("site_range")
            if not rng:
                return
            path, start, end = str(rng[0]), int(rng[1]), int(rng[2])
            # line numbers may have moved: find the stored chunk that now covers the site
            for chunk in reversed(list(state.get("file_memory") or [])):
                if chunk.get("path") == path and int(chunk["start"]) <= end and int(chunk["end"]) >= start:
                    start, end = max(start, int(chunk["start"])), min(end, int(chunk["end"]))
                    break
            if _memory_slice(state, path, start, end):
                state["act_excerpts"] = [{"path": path, "start": start, "end": end}]
                state["act_phase"] = True
                self._emit(run_id, "agent.coder.act_phase", reason=f"item {item['n']} located",
                           stalls=int(state.get("stalls") or 0), excerpts=state["act_excerpts"])
            return

    def _note_stall(self, run_id: str, state: dict[str, Any], tool_id: str, arguments: dict[str, Any]) -> None:
        """A refused or served repeat request in a bound worktree; enough of them start the act phase."""
        if tool_id in READ_RANGE_TOOLS:
            r_path, r_start, r_end = _requested_range(arguments or {})
            if _edited_region(state, _canonical_path(state, r_path), r_start, r_end):
                # A confirm-read of lines this run just edited: pushing those lines back as
                # "ACT NOW" excerpts made run agent-a615d0b5-c09297ce06db rewrite them 8 times.
                return
        state["stalls"] = int(state.get("stalls") or 0) + 1
        if tool_id in READ_RANGE_TOOLS:
            path, start, end = _requested_range(arguments or {})
            path = _canonical_path(state, path)
            total = int(((state.get("reads") or {}).get(path) or {}).get("total_lines") or 0)
            end = min(end, total, start + ACT_EXCERPT_LINES - 1) if total else min(end, start + ACT_EXCERPT_LINES - 1)
            if _memory_slice(state, path, start, end):
                excerpts = [e for e in (state.get("act_excerpts") or [])
                            if (e["path"], e["start"], e["end"]) != (path, start, end)]
                state["act_excerpts"] = (excerpts + [{"path": path, "start": start, "end": end}])[-2:]
        if state["stalls"] >= ACT_STALLS and not state.get("act_phase"):
            state["act_phase"] = True
            self._emit(run_id, "agent.coder.act_phase", reason="repeat requests for text already in memory",
                       stalls=state["stalls"], excerpts=list(state.get("act_excerpts") or []))

    def _update_checklist(self, run_id: str, state: dict[str, Any], summary: str, *,
                          edit_succeeded: bool = False, is_edit: bool = False) -> None:
        """DONE n counts only with a successful edit: on that edit itself, or on a later
        decision when an edit succeeded since the last DONE (run agent-680b3463-4384429de2df
        ticked items whose edits had failed). SKIP n: reason records an item that cannot be done."""
        checklist = state.get("checklist") or []
        if not checklist:
            return
        changed = False
        text = str(summary or "")
        for match in _SKIP.finditer(text):
            n = int(match.group(1))
            for item in checklist:
                if item["n"] == n and not item.get("done") and not item.get("skipped"):
                    item["skipped"] = True
                    item["skip_reason"] = match.group(2).strip()[:200] or "not applicable"
                    changed = True
        claims = [int(m.group(1)) for m in _DONE.finditer(text)]
        skipped_now = {int(m.group(1)) for m in _SKIP.finditer(text)}
        if is_edit and edit_succeeded and not claims:
            # One change per item: an edit that names no item finishes the next pending one
            # (run agent-bde5eaf1-b6bfb0fdcb1f made 3 edits but ticked only 2).
            pending = [i["n"] for i in checklist if not i.get("done") and not i.get("skipped")
                       and i["n"] not in skipped_now]
            claims = pending[:1]
        credited = edit_succeeded if is_edit else int(state.get("edits_since_done") or 0) > 0
        if claims and credited:
            for n in claims:
                for item in checklist:
                    if item["n"] == n and not item.get("done") and not item.get("skipped"):
                        item["done"] = True
                        changed = True
            state["edits_since_done"] = 0
        if changed:
            state["checklist"] = checklist
            self._emit(run_id, "agent.coder.checklist", items=checklist,
                       done=sum(1 for i in checklist if i.get("done")),
                       skipped=sum(1 for i in checklist if i.get("skipped")), total=len(checklist))

    def _tool_schemas(self) -> dict[str, dict[str, Any]]:
        try:
            tools = self.engine.tool_registry.list()
        except Exception:
            return {}
        return {str(t.get("tool_id")): (t.get("input_schema") or {}) for t in tools or []
                if isinstance(t, dict) and t.get("tool_id")}

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
        scan = state.get("scan") or {}
        if (total > LARGE_FILE_LINES or not total) and scan.get("path") == path \
                and int(scan.get("streak") or 0) >= EDIT_SCAN_CHUNKS \
                and abs(start - int(scan.get("end") or 0) - 1) <= 5 and end - start + 1 < 1000:
            return (f"Stop paging through {path} in small chunks. Either read the rest in ONE call "
                    f"(start_line {start}, line_count 2000) or use worktree.search_text for the exact "
                    "function or string you need. If FILE MEMORY already holds the code, edit it now "
                    "with old_lines.")
        if reads >= EDIT_READ_HARD_CAP:
            return ("Reading is closed for this edit: you have read enough. Make the change now with "
                    "worktree.replace_exact (copy the old text exactly from FILE MEMORY), or return "
                    "decision_type blocked saying what is missing.")
        covered = any(a <= start and end <= b for a, b in
                      (((state.get("reads") or {}).get(path) or {}).get("ranges") or []))
        if (reads >= EDIT_READ_BUDGET and covered and (total > LARGE_FILE_LINES or not total)
                and end - start + 1 > EDIT_NARROW_READ_LINES):
            return (f"{path} is too large to read top to bottom in an edit run ({total or 'many'} lines). "
                    "Use workspace.search_text for the function or symbol you must change (names are in "
                    "CONVERSATION SO FAR / NOTES), then read at most "
                    f"{EDIT_NARROW_READ_LINES} lines around the hit and edit with worktree.replace_exact.")
        return ""

    def _finishing_reason(self, state: dict[str, Any], turn: int) -> str:
        remaining_including_this = self.max_turns - turn
        if remaining_including_this <= FINISH_RESERVE_TURNS:
            return f"turn budget nearly spent: {remaining_including_this} turn(s) left"
        if int(state.get("duplicate_streak") or 0) >= MAX_DUPLICATE_STREAK and not state.get("bound"):
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
        if state.get("edit_count") and not state.get("verified_after_edit") and state.get("rollback_hint"):
            lines.append("Edits in the worktree are not verified. To discard them: " + str(state["rollback_hint"]))
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
            objective_text = str(run.get("objective") or "")
            checklist = _build_checklist(objective_text, state["conversation"])
            if not checklist and _CONTINUE_INTENT.search(objective_text):
                checklist = self._previous_checklist(run)
            state["plan_run"] = bool(_PLAN_INTENT.search(objective_text) and not _EDIT_INTENT.search(objective_text)
                                     and not checklist and str(run.get("mode") or "agent") != "edit")
            if checklist:
                state["checklist"] = checklist
                self._emit(run_id, "agent.coder.checklist", items=checklist, done=0, total=len(checklist))
            if state["conversation"]:
                self._emit(run_id, "agent.coder.history_attached",
                           messages=len(state["conversation"]),
                           chars=sum(len(m["content"]) for m in state["conversation"]))
            self._save(run_id, state)
            self._emit(run_id, "agent.coder.started",
                       engine="direct_coder_v1", model=run.get("model"))
            state["advisory"] = await direct_coder_hooks.prepare(self.engine, run_id, run)
            if not command and self._reuse_session_worktree(run_id, run, state):
                run = self._snapshot(run_id)
                if state.get("checklist"):
                    await self._prelocate(run_id, state)
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
            if (decision is None and not command and not state.get("bound") and not state.get("implicit_bind")
                    and not (run.get("checkpoint") or {}).get("worktree_root")
                    and str(run.get("mode") or "agent") in {"agent", "edit"}
                    and _EDIT_INTENT.search(str(run.get("objective") or ""))
                    and (state.get("checklist") or state.get("conversation"))
                    and os.environ.get("BEAST_DIRECT_CODER_IMPLICIT_BIND", "1") != "0"):
                # One harness-owned bind for edit requests: no model turn spent on bind ceremony.
                state["implicit_bind"] = True
                self._emit(run_id, "agent.coder.auto_bind", requested_tool="edit request")
                decision = PlannerDecision(
                    decision_type=PlannerDecisionType.TOOL, tool_id="worktree.bind",
                    arguments={"objective": str(run.get("objective") or "Direct Coder edit")[:400]},
                    rationale="Bind the isolated worktree for this edit request.")
                source = "runtime"
            if decision is None and state.get("queued_edits") and not command:
                # Batched edits from one model decision run back to back without a model turn.
                queued = list(state["queued_edits"])
                item = queued.pop(0)
                state["queued_edits"] = queued
                decision = PlannerDecision(
                    decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                    arguments={k: item[k] for k in ("path", "old_text", "new_text")},
                    summary=str(item.get("summary") or ""))
                self._emit(run_id, "agent.coder.batch_edit", remaining=len(queued),
                           item=item.get("item"), path=item.get("path"))
                source = "model"
            if decision is None and not command and self._checklist_resolved(state):
                # Every requested change is in: verify and finish without another model turn.
                decision = PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    summary=self._checklist_summary(state))
                source = "runtime"
                self._emit(run_id, "agent.coder.runtime_finish",
                           edits=int(state.get("edit_count") or 0),
                           verified=bool(state.get("verified_after_edit")))
            if decision is None:
                try:
                    finishing = self._finishing_reason(state, turn)
                    if finishing and not state.get("finishing_announced"):
                        state["finishing_announced"] = True
                        self._emit(run_id, "agent.coder.finishing", reason=finishing,
                                   turns_left=self.max_turns - turn)
                    prompt = self._prompt(run, state, finishing=finishing)
                    # Edit runs think once to plan (usually the bind turn); after that the model
                    # has the plan and the text, and long hidden reasoning each turn only delays
                    # the edit (run agent-a615d0b5-5f90e8e56782).
                    edit_quiet = (bool((run.get("checkpoint") or {}).get("worktree_root"))
                                  and os.environ.get("BEAST_DIRECT_CODER_EDIT_THINKING", "0") != "1")
                    decision = await self._ask(run_id, prompt, run, turn + 1,
                                               quiet_thinking=bool(finishing) or edit_quiet, state=state)
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
                    if (((turn + 1 >= self.max_turns and state.get("bound")) or state.get("force_finish"))
                            and decision.decision_type is PlannerDecisionType.TOOL):
                        # Step limit (or repeated doom loops): tools off, answer with what is done and left.
                        forced = bool(state.get("force_finish"))
                        self._emit(run_id, "agent.coder.step_limit_summary", tool_id=decision.tool_id,
                                   reason="doom_loops" if forced else "step_limit")
                        decision = PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=self._step_limit_summary(
                            state, f"Stopped early after {state.get('doom_count')} repeated-action loops" if forced else ""))
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

        if source == "model" and not (decision.decision_type is PlannerDecisionType.TOOL
                                      and decision.tool_id in MUTATION_TOOLS):
            self._update_checklist(run_id, state, str(decision.summary or decision.rationale or ""))
        bound_now = str((self._snapshot(run_id).get("checkpoint") or {}).get("worktree_root") or "")
        if (decision.decision_type is PlannerDecisionType.COMPLETE and not command and bound_now
                and state.get("edited_paths") and not state.get("verified_after_edit")
                and state.get("auto_verify_epoch") != state.get("edit_count")):
            # Verify edits before completion instead of refusing and spending another model turn.
            state["auto_verify_epoch"] = state.get("edit_count")
            state["pending_complete_summary"] = str(decision.summary or "")
            self._emit(run_id, "agent.coder.auto_verify", paths=list(state.get("edited_paths") or []))
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL, tool_id="worktree.verify",
                arguments={"command": _auto_verify_command(list(state.get("edited_paths") or []),
                                                           list(state.get("edit_names") or []),
                                                           dict(state.get("edited_funcs") or {})),
                           "timeout_seconds": AUTO_VERIFY_TIMEOUT},
                rationale="Runtime verification of the edited files before completion.")
            source = "runtime"
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
            if source == "model" and decision.decision_type is PlannerDecisionType.TOOL:
                flat = _flat_tool_id(decision.tool_id, bool(state.get("bound")))
                if flat != decision.tool_id:
                    self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                               tool_id=flat, changes=[f"tool {decision.tool_id} -> {flat}"])
                    decision = replace(decision, tool_id=flat)
            if (source == "model" and decision.decision_type is PlannerDecisionType.TOOL
                    and decision.tool_id.strip().lower() in TODO_TOOL_IDS):
                self._todowrite(run_id, state, dict(decision.arguments or {}))
                return await self._fold_or_end_turn(run_id, state, turn, "todowrite")
            if (source == "model" and decision.decision_type is PlannerDecisionType.TOOL
                    and state.get("plan_run") and (decision.tool_id in MUTATION_TOOLS
                                                   or decision.tool_id in {"worktree.bind", "worktree.replace",
                                                                           "worktree.edit", "edit", "write"})):
                # Plan vs build: analysis/suggest runs answer; they never edit.
                self._emit(run_id, "agent.coder.tool_rejected", tool_id=decision.tool_id, reason="plan_run",
                           message="plan run: no edits")
                state.setdefault("observations", []).append({
                    "tool_id": decision.tool_id, "status": "refused",
                    "error": ("This is a plan (analysis/suggest) run: do not bind or edit. Return decision_type "
                              "complete with the written answer. The operator can ask you to implement it next.")})
                return await self._fold_or_end_turn(run_id, state, turn, "plan_run")
            if (source == "model" and decision.decision_type is PlannerDecisionType.TOOL
                    and decision.tool_id.strip().lower() in PARALLEL_TOOL_IDS):
                await self._run_parallel(run_id, state, decision)
                state["turn"] = turn + 1
                state["observations"] = list(state.get("observations") or [])[-16:]
                self._save(run_id, state)
                self._transition(run_id, AgentRunState.OBSERVING)
                return self._snapshot(run_id)
            if (source == "model" and decision.decision_type is PlannerDecisionType.TOOL
                    and decision.tool_id.startswith("worktree.") and decision.tool_id != "worktree.bind"
                    and not state.get("bound")
                    and not str((self._snapshot(run_id).get("checkpoint") or {}).get("worktree_root") or "")):
                mapped = UNBOUND_READ_MAP.get(decision.tool_id)
                if mapped:
                    args_u = dict(decision.arguments or {})
                    if mapped == "workspace.read_range" and "line_count" not in args_u and args_u.get("end_line"):
                        try:
                            args_u["line_count"] = int(args_u.pop("end_line")) - int(args_u.get("start_line") or 1) + 1
                        except (TypeError, ValueError):
                            args_u.pop("end_line", None)
                    self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                               tool_id=mapped, changes=[f"no worktree bound yet: {decision.tool_id} -> {mapped}"])
                    decision = replace(decision, tool_id=mapped, arguments=args_u)
                elif not state.get("auto_bound"):
                    # Edits/verify need the isolated worktree: bind it now (once) instead of a rejection.
                    state["auto_bound"] = True
                    self._emit(run_id, "agent.coder.auto_bind", requested_tool=decision.tool_id)
                    state.setdefault("observations", []).append({
                        "tool_id": "runtime.hint", "status": "info",
                        "result": {"hint": f"{decision.tool_id} needs the isolated worktree, so the runtime "
                                           "bound it for you. Repeat that call now; do not call worktree.bind."}})
                    decision = PlannerDecision(
                        decision_type=PlannerDecisionType.TOOL, tool_id="worktree.bind",
                        arguments={"objective": str(run.get("objective") or "Direct Coder edit")[:400]},
                        rationale="Bind the isolated worktree the requested edit needs.")
                    source = "runtime"
            if (source == "model" and decision.tool_id in {"worktree.replace_exact", "worktree.replace",
                                                           "worktree.edit"}
                    and isinstance((decision.arguments or {}).get("edits"), list)):
                batch_args = dict(decision.arguments or {})
                expanded, batch_error = self._expand_batch(state, batch_args, str(decision.summary or ""))
                if batch_error or not expanded:
                    batch_error = batch_error or "edits must be a non-empty list"
                    self._emit(run_id, "agent.coder.tool_rejected", tool_id=decision.tool_id,
                               message=batch_error, reason="batch_edits")
                    state.setdefault("observations", []).append({
                        "tool_id": decision.tool_id, "status": "failed", "error": batch_error})
                    state["turn"] = turn + 1
                    state["observations"] = list(state.get("observations") or [])[-16:]
                    self._save(run_id, state)
                    self._transition(run_id, AgentRunState.OBSERVING)
                    return self._snapshot(run_id)
                first = expanded.pop(0)
                state["queued_edits"] = expanded
                self._emit(run_id, "agent.coder.batch_edit", remaining=len(expanded),
                           item=first.get("item"), path=first.get("path"))
                decision = replace(decision, tool_id="worktree.replace_exact",
                                   arguments={k: first[k] for k in ("path", "old_text", "new_text")},
                                   summary=str(first.get("summary") or ""))
            if source == "model" and decision.tool_id in {"worktree.replace_exact", "worktree.replace",
                                                          "worktree.edit"} and any(
                    k in (decision.arguments or {}) for k in ("old_lines", "end_line")):
                resolved, span_error = _resolve_old_lines(state, dict(decision.arguments or {}))
                if span_error:
                    self._emit(run_id, "agent.coder.tool_rejected", tool_id=decision.tool_id,
                               message=span_error, reason="old_lines")
                    state.setdefault("observations", []).append({
                        "tool_id": decision.tool_id, "status": "failed", "error": span_error,
                        "arguments": {k: v for k, v in (decision.arguments or {}).items() if k != "new_text"}})
                    state["turn"] = turn + 1
                    state["observations"] = list(state.get("observations") or [])[-16:]
                    self._save(run_id, state)
                    self._transition(run_id, AgentRunState.OBSERVING)
                    return self._snapshot(run_id)
                self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                           tool_id="worktree.replace_exact", changes=["old_lines -> old_text from FILE MEMORY"])
                decision = replace(decision, tool_id="worktree.replace_exact", arguments=resolved)
            if source == "model" and decision.tool_id in {"worktree.replace_exact", "worktree.replace"}:
                # The act prompt shows text with a 'NNNN| ' gutter; models sometimes copy it.
                args0 = dict(decision.arguments or {})
                old, had = _strip_gutter(str(args0.get("old_text") or ""))
                if had:
                    args0["old_text"] = old
                    args0["new_text"], _ = _strip_gutter(str(args0.get("new_text") or ""))
                    self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                               tool_id=decision.tool_id, changes=["stripped line-number gutter"])
                    decision = replace(decision, arguments=args0)
                old_now = str((decision.arguments or {}).get("old_text") or "")
                edit_path = _canonical_path(state, str((decision.arguments or {}).get("path") or ""))
                in_memory = any(old_now and old_now in str(m.get("content") or "")
                                for m in state.get("file_memory") or [] if m.get("path") == edit_path)
                if old_now and not in_memory:
                    exact = _loose_match(state, edit_path, old_now)
                    if exact and exact != old_now:
                        args1 = dict(decision.arguments or {})
                        args1["old_text"] = exact
                        self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                                   tool_id=decision.tool_id, changes=["old_text matched FILE MEMORY ignoring whitespace"])
                        decision = replace(decision, arguments=args1)
            if source == "model":
                schemas = self._tool_schemas()
                if schemas:
                    new_id, new_args, changes = _normalize_tool_call(
                        decision.tool_id, dict(decision.arguments or {}), schemas)
                    if changes:
                        self._emit(run_id, "agent.coder.tool_call_normalized", requested_tool=decision.tool_id,
                                   tool_id=new_id, changes=changes)
                        decision = replace(decision, tool_id=new_id, arguments=new_args)
                    if changes:
                        state["pending_arg_repair"] = changes
                    if decision.tool_id not in schemas:
                        # OpenCode 'invalid' tool: an unknown name is a normal result listing the
                        # valid tools, folded into the same turn, never a hard rejection.
                        message = _unknown_tool_message(decision.tool_id, schemas)
                        self._emit(run_id, "agent.coder.invalid_tool", tool_id=decision.tool_id,
                                   message=message[:600])
                        state.setdefault("observations", []).append({
                            "tool_id": "invalid", "status": "completed",
                            "arguments": {"requested_tool": decision.tool_id},
                            "result": {"error": message[:1500],
                                       "flat_tools": sorted(FLAT_TOOLS) + ["todowrite", "parallel"]},
                        })
                        return await self._fold_or_end_turn(run_id, state, turn, "invalid_tool")
            if source == "model" and decision.decision_type is PlannerDecisionType.TOOL \
                    and not state.get("resuming_approval_id"):
                args_now = dict(decision.arguments or {})
                if decision.tool_id in READ_RANGE_TOOLS:
                    r_path, r_start, r_end = _requested_range(args_now)
                    sig = f"read:{_canonical_path(state, r_path)}:{r_start}-{r_end}"
                else:
                    sig = decision.tool_id + json.dumps(args_now, sort_keys=True, default=str)[:4000]
                window = list(state.get("recent_calls") or [])[-(DOOM_LOOP_WINDOW - 1):]
                state["recent_calls"] = window + [sig]
                doom = ""
                if window.count(sig) >= DOOM_LOOP_REPEATS - 1:
                    doom = (f"Doom loop: {decision.tool_id} with these arguments {DOOM_LOOP_REPEATS} times in the "
                            f"last {DOOM_LOOP_WINDOW} calls. You already have its result.")
                    if decision.tool_id in READ_RANGE_TOOLS:
                        region = _edited_region(state, _canonical_path(state, r_path), r_start, r_end)
                        if region:
                            doom += (f" Lines {region['start']}-{region['end']} already hold your edit "
                                     f"(applied {region['count']}x, last at turn {region['turn']}); there is "
                                     "nothing to confirm.")
                    doom += " Act on it now: the next change, mark the checklist item (todowrite or SKIP n), or complete."
                elif decision.tool_id == "worktree.replace_exact":
                    e_path = _canonical_path(state, str(args_now.get("path") or ""))
                    span = _memory_span(state, e_path, str(args_now.get("old_text") or ""))
                    region = _edited_region(state, e_path, *span) if span else None
                    if (region and int(region.get("count") or 0) >= REGION_EDIT_LIMIT
                            and int(region.get("epoch") or 0) == _progress_epoch(state)
                            and not (state.get("needs_fix") or {}).get(e_path)):
                        doom = (f"Refused: you already rewrote {e_path} lines {region['start']}-{region['end']} "
                                f"{region['count']} times and the result passed the syntax check, so that change "
                                "is applied. Do not rewrite this region again. Mark the item done (DONE n), move "
                                "to the next item somewhere else, or complete.")
                if doom:
                    await_doom = await self._doom(run_id, state, turn, decision.tool_id, args_now, doom)
                    return await_doom
                old_t, new_t = str(args_now.get("old_text") or ""), str(args_now.get("new_text") or "")
                if (decision.tool_id == "worktree.replace_exact" and old_t
                        and re.sub(r"\s+", "", old_t) == re.sub(r"\s+", "", new_t)):
                    # A whitespace-only replace counted as 'done' in run agent-f86eb92e-f35599dd63f1.
                    message = ("Refused: this edit changes only whitespace, so it implements nothing. Make the "
                               "real change for the item, or SKIP n: reason if it cannot be done.")
                    self._emit(run_id, "agent.coder.tool_rejected", tool_id=decision.tool_id,
                               reason="no_op_edit", message=message)
                    state.setdefault("observations", []).append(
                        {"tool_id": decision.tool_id, "status": "refused", "error": message})
                    return await self._fold_or_end_turn(run_id, state, turn, "no_op_edit")
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
                    self._note_stall(run_id, state, decision.tool_id, dict(decision.arguments or {}))
                    state.setdefault("observations", []).append({
                        "tool_id": decision.tool_id, "status": "refused",
                        "arguments": dict(decision.arguments or {}), "error": budget_reason,
                    })
                    if state.get("fold_turn") != turn and turn + 1 < self.max_turns:
                        state["fold_turn"] = turn
                        state["observations"] = list(state.get("observations") or [])[-16:]
                        self._emit(run_id, "agent.coder.skip_folded", tool_id=decision.tool_id, kind="refused")
                        self._save(run_id, state)
                        return await self._run_turn(run_id)
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
                    region = _edited_region(state, path, start, end)
                    note = ("Exact current text from FILE MEMORY. Copy old_text from here "
                            "into worktree.replace_exact now; do not read these lines again.")
                    if region:
                        note = (f"This is the CURRENT text AFTER your edit of lines {region['start']}-{region['end']} "
                                f"(turn {region['turn']}): the edit is applied. Do not rewrite these lines unless a "
                                "diagnostic or verify failure points here. Continue with the next item, or complete.")
                    state.setdefault("observations", []).append({
                        "tool_id": EXCERPT_TOOL, "status": "completed",
                        "requested_tool": decision.tool_id, "arguments": dict(decision.arguments or {}),
                        "result": {"path": path, "start_line": start, "end_line": end,
                                   "content": excerpt[:EXCERPT_CHARS], "note": note},
                    })
                    self._note_stall(run_id, state, decision.tool_id, dict(decision.arguments or {}))
                    if state.get("fold_turn") != turn:
                        # Hand the text back in the same turn instead of a separate model turn.
                        state["fold_turn"] = turn
                        state["observations"] = list(state.get("observations") or [])[-16:]
                        self._emit(run_id, "agent.coder.skip_folded", tool_id=decision.tool_id, kind="served")
                        self._save(run_id, state)
                        return await self._run_turn(run_id)
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
                if bound_root and source == "model":
                    self._note_stall(run_id, state, decision.tool_id, dict(decision.arguments or {}))
                    if state.get("fold_turn") != turn and turn + 1 < self.max_turns:
                        state["fold_turn"] = turn
                        state["observations"] = list(state.get("observations") or [])[-16:]
                        self._emit(run_id, "agent.coder.skip_folded", tool_id=decision.tool_id, kind="skipped")
                        self._save(run_id, state)
                        return await self._run_turn(run_id)
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
            pre_edit: tuple[str, str] | None = None
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
                if decision.tool_id in MUTATION_TOOLS:
                    pre_edit = self._parseable_source(run_id, state, str(args.get("path") or ""))
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
                message = str(exc)
                if "unknown tool arguments" in message or "missing required tool arguments" in message:
                    schema = self._tool_schemas().get(decision.tool_id) or {}
                    allowed_args = sorted((schema.get("properties") or {}).keys())
                    message += (f". {decision.tool_id} accepts only: {', '.join(allowed_args)}"
                                f" (required: {', '.join(schema.get('required') or [])}). "
                                "Put your notes in the decision summary, not in arguments.")
                self._emit(run_id, "agent.coder.tool_rejected",
                           tool_id=decision.tool_id, message=message[:600])
                entry = {"tool_id": decision.tool_id,
                         "status": "failed", "error": message[:1200]}
            repairs = state.pop("pending_arg_repair", None)
            if repairs and isinstance(entry, dict):
                entry["arg_repair"] = list(repairs)[:12]
            if pre_edit is not None and isinstance(entry, dict) and entry.get("status") == "completed":
                reverted = self._revert_if_syntax_broken(run_id, state, pre_edit, decision)
                if reverted:
                    entry = {"tool_id": decision.tool_id, "status": "failed", "error": reverted,
                             "arguments": {k: v for k, v in dict(decision.arguments or {}).items() if k != "new_text"}}
                    canonical = None
            state.setdefault("observations", []).append(entry)
            if (decision.tool_id == "worktree.bind" and entry.get("status") == "completed"
                    and isinstance(canonical, dict) and isinstance(canonical.get("result"), dict)):
                state["path_prefix"] = str(canonical["result"].get("workspace_prefix") or "")
                state["reads_since_edit"] = 0
                state["bound"] = True
                if state.get("checklist") and not command:
                    await self._prelocate(run_id, state)
            if decision.tool_id in READ_ONLY_TOOLS and isinstance(canonical, dict):
                self._remember(state, decision.tool_id, dict(decision.arguments or {}), canonical)
                if decision.tool_id in READ_RANGE_TOOLS and bound_root:
                    state["reads_since_edit"] = int(state.get("reads_since_edit") or 0) + 1
                    r_path, r_start, r_end = _requested_range(dict(decision.arguments or {}))
                    r_path = _canonical_path(state, r_path)
                    scan = dict(state.get("scan") or {})
                    if scan.get("path") == r_path and abs(r_start - int(scan.get("end") or 0) - 1) <= 5:
                        scan["streak"] = int(scan.get("streak") or 0) + 1
                    else:
                        scan = {"path": r_path, "streak": 1}
                    scan["end"] = r_end
                    state["scan"] = scan
            if decision.tool_id in MUTATION_TOOLS and source == "model":
                ok_edit = entry.get("status") == "completed"
                if ok_edit:
                    state["edits_since_done"] = int(state.get("edits_since_done") or 0) + 1
                self._update_checklist(run_id, state, str(decision.summary or decision.rationale or ""),
                                       edit_succeeded=ok_edit, is_edit=True)
                if not ok_edit and "found 0" in str(entry.get("error") or ""):
                    near = _closest_lines(state, _canonical_path(state, str(decision.arguments.get("path") or "")),
                                          str(decision.arguments.get("old_text") or ""))
                    state.setdefault("observations", []).append({
                        "tool_id": "runtime.hint", "status": "info",
                        "error": ("old_text was not found. "
                                  + (f"Closest lines in FILE MEMORY (retry with old_lines from these numbers):\n{near}\n"
                                     if near else
                                     "worktree.search_text for one short, distinctive line (e.g. the def line), "
                                     "then edit with old_lines. ")
                                  + "If the function does not exist, SKIP that checklist item with the reason."),
                    })
            if decision.tool_id in MUTATION_TOOLS and entry.get("status") == "completed":
                state["reads_since_edit"] = 0
                state["stalls"] = 0
                state["act_phase"] = False
                state["act_excerpts"] = []
                state["edit_count"] = int(state.get("edit_count") or 0) + 1
                new_names = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b(?=\s*\()",
                                           str(decision.arguments.get("new_text") or "")))
                state["edit_names"] = sorted(set(state.get("edit_names") or []) | new_names)[:200]
                state["verified_after_edit"] = False
                edited = _canonical_path(state, str(decision.arguments.get("path") or ""))
                if edited:
                    state["edited_paths"] = sorted(set(state.get("edited_paths") or []) | {edited})
                state["seen_calls"] = [k for k in (state.get("seen_calls") or []) if not k.startswith("worktree.")]
                if edited:
                    patched = (decision.tool_id == "worktree.replace_exact" and _apply_edit_to_memory(
                        state, edited, str(decision.arguments.get("old_text") or ""),
                        str(decision.arguments.get("new_text") or "")))
                    if not patched:
                        reads = dict(state.get("reads") or {})
                        reads.pop(edited, None)
                        state["reads"] = reads
                        # Line numbers and text changed: stale memory would feed old_lines/old_text wrong text.
                        state["file_memory"] = [m for m in (state.get("file_memory") or []) if m.get("path") != edited]
                    self._emit(run_id, "agent.coder.memory_after_edit", path=edited,
                               action="patched" if patched else "dropped")
                    state["rereads"] = []
                    state["served_from_memory"] = []
                    state["scan"] = {}
                    diagnostics = self._edit_diagnostics(run_id, state, edited,
                                                         str(decision.arguments.get("new_text") or ""))
                    if diagnostics and isinstance(entry, dict):
                        entry["diagnostics"] = diagnostics
                        state["verified_after_edit"] = False
                    needs_fix = dict(state.get("needs_fix") or {})
                    needs_fix[edited] = bool(diagnostics)
                    state["needs_fix"] = needs_fix
                    self._record_edited_region(state, edited, str(decision.arguments.get("new_text") or ""), turn)
                    if bound_root and not state.get("rollback_hint"):
                        prefix = str(state.get("path_prefix") or "")
                        rel = edited if not prefix or edited.startswith(prefix + "/") else f"{prefix}/{edited}"
                        state["rollback_hint"] = f"git -C {bound_root} checkout -- {rel}"
                    # verify results are about the old text: an identical verify after an edit is no loop
                    state["recent_calls"] = [c for c in (state.get("recent_calls") or [])
                                             if not c.startswith("worktree.verify")]
                self._focus_next_site(run_id, state)
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
            if not command and decision.tool_id == "worktree.verify":
                result = (canonical or {}).get("result") if isinstance(canonical, dict) else None
                ok = (entry.get("status") == "completed" and isinstance(result, dict)
                      and result.get("ok") is True and int(result.get("returncode") or 0) == 0)
                state["verified_after_edit"] = bool(ok and state.get("edit_count"))
                if not ok:
                    state["needs_fix"] = {p: True for p in state.get("edited_paths") or []}
                pending_summary = state.pop("pending_complete_summary", None)
                if ok and pending_summary is not None and source == "runtime":
                    done = [i for i in (state.get("checklist") or []) if i.get("done")]
                    verified_line = ("Verified by the runtime: py_compile and --help smoke passed for "
                                     + ", ".join(state.get("edited_paths") or []) + ".")
                    summary = (pending_summary.strip() + "\n\n" + verified_line
                               + (f"\nChecklist: {len(done)}/{len(state.get('checklist') or [])} done." if state.get("checklist") else ""))
                    state["turn"] = turn + 1
                    self._save(run_id, state)
                    self._emit(run_id, "agent.coder.completed", summary=summary)
                    self._transition(run_id, AgentRunState.COMPLETED)
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
