"""Route read-only review and analysis prompts without weakening mutation policy.

The desktop IDE already classifies analysis prompts in agent mode and sends
them as ``mode=analysis``. The conversation-first TLI used to leave those
prompts on the mutating agent path, which then hit the heuristic planner
fallback and ended as ``policy_blocked``.
"""
from __future__ import annotations

import re
from pathlib import Path

_NEGATION = re.compile(r"\b(?:do not|don['’]t|never|must not|without)\b[^.!?;\n]*", re.IGNORECASE)
_PATCH = re.compile(
    r"\b(fix|change|modify|update|implement|add|remove|replace|refactor|write|patch|edit|make it|create)\b",
    re.IGNORECASE,
)
_ANALYSIS = re.compile(
    r"\b("
    r"look over|review|analy[sz]e|analysis|deep dive|inspect|explain|understand|"
    r"summari[sz]e|walk through|what does|how does|find risks|identify issues|audit|"
    r"list(?:\s+any)?\s+(?:weaknesses|issues|risks|problems)|"
    r"suggest(?:\s+any)?\s+(?:fixes|improvements|changes)"
    r")\b",
    re.IGNORECASE,
)
_REVIEW = re.compile(
    r"\b(review|audit|find risks|identify issues|list(?:\s+any)?\s+(?:weaknesses|issues|risks|problems))\b",
    re.IGNORECASE,
)
_THIS_FILE = re.compile(r"\bthis file\b", re.IGNORECASE)
_NAMED_FILE = re.compile(r"\b(?:the\s+)?([A-Za-z0-9._-]+)\s+file\b", re.IGNORECASE)
_EXTENSION_PATH = re.compile(
    r"(?<![\w./-])/?(?:[\w.-]+/)*[\w.-]+\.(?:py|js|ts|md|json|toml|ya?ml)(?![\w/-]|\.[\w.])"
)
_TOKEN = re.compile(r"[A-Za-z0-9._-]+")
_STOPWORDS = frozenset({
    "a", "an", "and", "any", "all", "the", "this", "that", "these", "those",
    "file", "files", "read", "reading", "please", "proceed", "with", "from",
    "into", "for", "to", "of", "in", "on", "it", "its", "or", "be", "is",
    "are", "was", "were", "do", "does", "how", "what", "when", "where", "why",
})
_HIDDEN_PARTS = {".", ".."}


def is_analysis_prompt(prompt: str) -> bool:
    """True when the prompt asks for inspection or review and not a patch."""
    text = str(prompt or "")
    if not text.strip():
        return False
    affirmative = _NEGATION.sub("", text.lower())
    return bool(_ANALYSIS.search(text)) and not bool(_PATCH.search(affirmative))


def is_review_prompt(prompt: str) -> bool:
    """True when an analysis prompt specifically asks for a review or audit."""
    return is_analysis_prompt(prompt) and bool(_REVIEW.search(str(prompt or "")))


def route_composer_mode(mode: str, prompt: str) -> str:
    """Map a TLI composer mode to the mode the gateway should receive.

    Explicit ``ask`` / ``review`` / ``edit`` selections are kept. Agent-mode
    analysis prompts are routed to ``ask`` or ``review`` so the run is created
    as read-only analysis, matching the desktop IDE.
    """
    selected = str(mode or "agent").strip().lower() or "agent"
    if selected in {"ask", "review", "edit"}:
        return selected
    if selected == "agent" and is_analysis_prompt(prompt):
        return "review" if is_review_prompt(prompt) else "ask"
    return selected


def _safe_relative_file(root: Path, candidate: Path) -> str | None:
    try:
        if candidate.is_absolute():
            return None
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return None
        relative = resolved.relative_to(root)
        if any(part.startswith(".") or part in _HIDDEN_PARTS for part in relative.parts):
            return None
        if resolved.is_symlink() or any(
            part.is_symlink()
            for part in list(resolved.parents)
            if part != root and root in part.parents
        ):
            return None
        return relative.as_posix()
    except (OSError, ValueError):
        return None


def _unique_visible_root_file(root: Path) -> str | None:
    try:
        visible = [
            path
            for path in root.iterdir()
            if path.is_file() and not path.name.startswith(".") and not path.is_symlink()
        ]
    except OSError:
        return None
    if len(visible) != 1:
        return None
    return _safe_relative_file(root, Path(visible[0].name))


def resolve_context_files(root: Path, prompt: str, *, limit: int = 4) -> tuple[str, ...]:
    """Attach mentioned workspace files, including extensionless names like ``beast``."""
    workspace = Path(root)
    files: list[str] = []

    def add(name: str) -> None:
        if len(files) >= limit:
            return
        relative = _safe_relative_file(workspace, Path(name))
        if relative and relative not in files:
            files.append(relative)

    for name in _EXTENSION_PATH.findall(str(prompt or "")):
        candidate = Path(name)
        if candidate.parent == Path(".") and _safe_relative_file(workspace, candidate) is None:
            continue
        add(name)
    for name in _NAMED_FILE.findall(str(prompt or "")):
        if name.lower() not in _STOPWORDS:
            add(name)
    if _THIS_FILE.search(str(prompt or "")):
        unique = _unique_visible_root_file(workspace)
        if unique:
            add(unique)
    if len(files) < limit:
        for token in _TOKEN.findall(str(prompt or "")):
            if token.lower() in _STOPWORDS or len(token) < 2:
                continue
            add(token)
            if len(files) >= limit:
                break
    return tuple(files[:limit])
