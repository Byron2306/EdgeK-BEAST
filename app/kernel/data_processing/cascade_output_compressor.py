"""RTK compression for Quality Cascade output (test, lint and log), with exact-preservation guarantees.

The real ``rtk`` binary (rtk-ai/rtk, Rust Token Killer) is used when it is on PATH; otherwise the BEAST native
stand-in prunes blank/duplicate lines. Either way a post-check re-appends, byte-exact, every line that safe
compression must keep: failing assertions and error lines, ``file:line`` locations (line numbers intact), traceback
frames and any caller-declared edit-target code. sqz is intentionally not used here (reserved for Perceive
transcript compaction). Install (not performed by BEAST):
``curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from typing import Any

KINDS = ("test", "lint", "log")
RTK_FILTERS = {"test": "pytest", "lint": "ruff", "log": ""}
EXACT_PATTERNS = (
    re.compile(r"^\s*E\s{2,}"),                                         # pytest assertion detail lines
    re.compile(r"\b(AssertionError|assert\s|FAILED\b|ERROR\b|Error:|Exception\b|Traceback)"),
    re.compile(r"(?:^|\s|\")[\w./\\-]+\.\w+:\d+(?::\d+)?"),               # file:line[:col]
    re.compile(r"^\s*File \"[^\"]+\", line \d+"),                     # Python traceback frames
    re.compile(r"^[\w./\\-]+:\d+:\d+: [A-Z]+\d+"),                      # ruff/flake8 diagnostics
)
EXACT_HEADER = "[beast-exact: lines preserved verbatim]"
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _native(text: str) -> str:
    kept: list[str] = []
    previous = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == previous:
            continue
        kept.append(line.rstrip("\n"))
        previous = stripped
    return "\n".join(kept)


def exact_lines(text: str, edit_targets: Iterable[str] = ()) -> list[str]:
    targets = [t for t in (str(x) for x in edit_targets) if t.strip()]
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        plain = ANSI.sub("", line)  # coloured tool output must not hide failures from the exact-line contract
        exact = any(p.search(plain) for p in EXACT_PATTERNS) or any(t in line or t in plain for t in targets)
        if exact and line not in out:
            out.append(line)
    for target in targets:  # multi-line edit targets must survive as a whole
        if "\n" in target and target in text and target not in out:
            out.append(target)
    return out


def _rtk(text: str, kind: str, timeout: float) -> tuple[str, str]:
    binary = shutil.which("rtk")
    if not binary:
        return "", ""
    commands = []
    if RTK_FILTERS.get(kind):
        commands.append([binary, "pipe", "--filter", RTK_FILTERS[kind]])
    commands.append([binary, "log"])
    for command in commands:
        try:
            done = subprocess.run(command, input=text, capture_output=True, text=True, timeout=timeout, check=False,
                                  env={**os.environ, "RTK_TELEMETRY_DISABLED": "1"})  # local-only: never ping
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout, " ".join(command[1:])
    return "", ""


def compress_cascade_output(text: str, *, kind: str = "test", edit_targets: Iterable[str] = (),
                            timeout: float = 10.0) -> dict[str, Any]:
    text = str(text or "")
    kind = kind if kind in KINDS else "log"
    compressed, command = _rtk(text, kind, timeout)
    backend = "rtk_binary" if compressed else "beast_native_rtk_stub"
    if not compressed:
        compressed = _native(text)
    required = exact_lines(text, edit_targets)
    missing = [line for line in required if line not in compressed]
    if missing:
        compressed = compressed.rstrip("\n") + "\n" + EXACT_HEADER + "\n" + "\n".join(missing)
    if len(compressed) >= len(text) and not missing:
        compressed, backend = text, "passthrough"
    return {
        "content": compressed,
        "backend": backend,
        "rtk_command": command,
        "kind": kind,
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "exact_lines_required": len(required),
        "exact_lines_restored": len(missing),
        "original_sha256": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "safe": all(line in compressed for line in required),
    }


__all__ = ["EXACT_HEADER", "compress_cascade_output", "exact_lines"]
