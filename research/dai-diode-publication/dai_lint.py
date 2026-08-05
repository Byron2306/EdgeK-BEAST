#!/usr/bin/env python3
"""Publication hygiene linter for DAI-Diode candidates.

This is not a substitute for semantic verification. It prevents avoidable
publication failures: leaked private keys, unresolved templates, production
assertions, path-dependent implementation digests, authority escalation, and
misreported arena denominators.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import dai_publication_core as core


class LintFailure(core.PublicationError):
    """A fail-closed publication lint failure."""


PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
)
SECRET_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"replace-with", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"template_not_resolved"),
    re.compile(r"example\.invalid"),
)
TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".toml", ".ini", ".py", ".sh"}
SKIP_PREFIXES = ("artifacts/", "core/CORE_CAPSULE.zip", "templates/")


def _iter_values(value: Any, pointer: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            yield child_pointer, child
            yield from _iter_values(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            yield child_pointer, child
            yield from _iter_values(child, child_pointer)


def _lint_python(path: Path, relative: str, errors: list[str], warnings: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (UnicodeDecodeError, SyntaxError) as exc:
        errors.append(f"{relative}: Python parse failure: {exc}")
        return
    is_test = relative.startswith("tests/") or "/tests/" in relative or Path(relative).name.startswith("test_")
    if not is_test:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                errors.append(f"{relative}:{node.lineno}: production assert is forbidden")
    if "__file__.encode" in source or "str(__file__)" in source:
        errors.append(f"{relative}: path-dependent implementation digest pattern detected")
    if "python -O" in source and "forbidden" not in source.lower() and "refuse" not in source.lower():
        warnings.append(f"{relative}: references optimized Python without an obvious refusal gate")


def _lint_json(path: Path, relative: str, errors: list[str], warnings: list[str]) -> None:
    try:
        value = core.load_json_file(path)
    except core.PublicationError as exc:
        errors.append(f"{relative}: {exc}")
        return
    for pointer, child in _iter_values(value):
        key = pointer.rsplit("/", 1)[-1]
        if key in {"production_authority_allowed", "execution_authority_allowed"} and child is not False:
            errors.append(f"{relative}{pointer}: authority must be explicitly false")
        if key in {"private_key", "private_key_pem", "secret", "api_key", "access_token"} and child:
            errors.append(f"{relative}{pointer}: secret-bearing field must not be published")
        if isinstance(child, float) and (child != child or child in {float("inf"), float("-inf")}):
            errors.append(f"{relative}{pointer}: non-finite number is forbidden")
    if relative.endswith("arena/RESULTS.json") or relative == "arena/RESULTS.json":
        _lint_arena_metrics(value, relative, errors)


def _lint_arena_metrics(value: Any, relative: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{relative}: arena results must be an object")
        return
    required = {
        "total_case_count",
        "answer_case_count",
        "refusal_case_count",
        "unresolved_case_count",
        "answer_case_correct_count",
        "refusal_case_correct_count",
        "unresolved_case_correct_count",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append(f"{relative}: explicit metric denominators are missing: {missing}")
        return
    counts = {key: value[key] for key in required}
    if any(not isinstance(item, int) or item < 0 for item in counts.values()):
        errors.append(f"{relative}: arena metric counts must be non-negative integers")
        return
    if counts["answer_case_count"] + counts["refusal_case_count"] + counts["unresolved_case_count"] != counts["total_case_count"]:
        errors.append(f"{relative}: answer/refusal/unresolved denominators do not sum to total")
    pairs = (
        ("answer_case_correct_count", "answer_case_count"),
        ("refusal_case_correct_count", "refusal_case_count"),
        ("unresolved_case_correct_count", "unresolved_case_count"),
    )
    for correct, total in pairs:
        if counts[correct] > counts[total]:
            errors.append(f"{relative}: {correct} exceeds {total}")


def lint_candidate(candidate: Path, *, stage: str) -> dict[str, Any]:
    core.refuse_optimized_python()
    candidate = candidate.resolve()
    records = core.inventory_directory(candidate)
    errors: list[str] = []
    warnings: list[str] = []
    scanned_text_files = 0
    scanned_json_files = 0
    scanned_python_files = 0
    for record in records:
        relative = record.path
        path = candidate / relative
        if any(relative == prefix or relative.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if stage == "final" and (".template." in relative or relative.endswith(".template")):
            errors.append(f"{relative}: template file is forbidden in a final candidate")
        data = path.read_bytes()
        if any(marker in data for marker in PRIVATE_KEY_MARKERS):
            errors.append(f"{relative}: private key material detected")
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                errors.append(f"{relative}: probable credential/token detected")
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            continue
        scanned_text_files += 1
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{relative}: declared text file is not UTF-8")
            continue
        if stage == "final":
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern.search(text):
                    errors.append(f"{relative}: unresolved publication placeholder matches {pattern.pattern!r}")
                    break
            if re.search(r"(?:/home/|/Users/|/mnt/data/|[A-Za-z]:\\\\)", text):
                warnings.append(f"{relative}: host-specific absolute path detected; verify it is not digest material")
        if suffix == ".json":
            scanned_json_files += 1
            _lint_json(path, relative, errors, warnings)
        if suffix == ".py":
            scanned_python_files += 1
            _lint_python(path, relative, errors, warnings)
    world_first_mentions = []
    for record in records:
        if record.path.startswith(SKIP_PREFIXES):
            continue
        if Path(record.path).suffix.lower() not in {".md", ".txt"}:
            continue
        text = (candidate / record.path).read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            if "world first" in lower and "to our knowledge" not in lower and "cannot" not in lower and "not " not in lower:
                world_first_mentions.append(f"{record.path}:{line_number}")
    if world_first_mentions:
        warnings.append(f"unqualified 'world first' wording requires manual review: {world_first_mentions}")
    report = {
        "schema": "dai.publication-lint-report.v1",
        "stage": stage,
        "passed": not errors,
        "file_count": len(records),
        "scanned_text_file_count": scanned_text_files,
        "scanned_json_file_count": scanned_json_files,
        "scanned_python_file_count": scanned_python_files,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--stage", choices=("rc", "final"), default="rc")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = lint_candidate(args.candidate, stage=args.stage)
        if args.output:
            core.write_canonical_json(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    except (core.PublicationError, OSError) as exc:
        print(f"DAI publication lint failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
