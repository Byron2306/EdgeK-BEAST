#!/usr/bin/env python3
"""Declarative semantic attack runner for the frozen DAI-Diode core.

The adapter receives a mutated JSON input and must write a canonical JSON result.
An attack passes only when the declared rejection/refusal contract is observed,
including authority remaining false. A crash is not automatically a pass.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import dai_publication_core as core


class AttackError(core.PublicationError):
    """A fail-closed semantic attack validation error."""


def fail(message: str) -> None:
    raise AttackError(message)


def _pointer_parent(document: Any, pointer: str) -> tuple[Any, str]:
    parts = core._json_pointer_parts(pointer)
    if not parts:
        fail("operation may not replace the document root")
    escaped = [part.replace("~", "~0").replace("/", "~1") for part in parts[:-1]]
    parent_pointer = "/" + "/".join(escaped) if escaped else ""
    return core.json_pointer_get(document, parent_pointer), parts[-1]


def apply_operations(document: Any, operations: Any) -> Any:
    if not isinstance(operations, list):
        fail("attack operations must be a list")
    result = copy.deepcopy(document)
    for operation in operations:
        if not isinstance(operation, dict):
            fail("attack operation must be an object")
        op = operation.get("op")
        pointer = operation.get("pointer")
        if op in {"remove_json_pointer", "set_json_pointer", "remove_list_item_by_id"}:
            result = core._apply_ablation_operations(result, [operation])
        elif op == "append_json_pointer":
            target = core.json_pointer_get(result, pointer)
            if not isinstance(target, list):
                fail(f"append target is not a list: {pointer}")
            target.append(copy.deepcopy(operation.get("value")))
        elif op == "duplicate_list_item_by_id":
            target = core.json_pointer_get(result, pointer)
            if not isinstance(target, list):
                fail(f"duplicate target is not a list: {pointer}")
            id_field = operation.get("id_field", "id")
            identifier = operation.get("id")
            matches = [item for item in target if isinstance(item, dict) and item.get(id_field) == identifier]
            if len(matches) != 1:
                fail(f"duplicate operation requires exactly one matching item: {identifier!r}")
            target.append(copy.deepcopy(matches[0]))
        elif op == "copy_json_pointer":
            source = operation.get("source")
            value = copy.deepcopy(core.json_pointer_get(result, source))
            core.json_pointer_set(result, pointer, value)
        elif op == "swap_json_pointers":
            other = operation.get("other")
            left = copy.deepcopy(core.json_pointer_get(result, pointer))
            right = copy.deepcopy(core.json_pointer_get(result, other))
            core.json_pointer_set(result, pointer, right)
            core.json_pointer_set(result, other, left)
        elif op == "replace_text":
            current = core.json_pointer_get(result, pointer)
            old = operation.get("old")
            new = operation.get("new")
            if not isinstance(current, str) or not isinstance(old, str) or not isinstance(new, str):
                fail("replace_text requires string target, old, and new")
            if old not in current:
                fail(f"replace_text old value not found at {pointer}")
            core.json_pointer_set(result, pointer, current.replace(old, new, 1))
        elif op == "flip_boolean":
            current = core.json_pointer_get(result, pointer)
            if not isinstance(current, bool):
                fail(f"flip_boolean target is not boolean: {pointer}")
            core.json_pointer_set(result, pointer, not current)
        else:
            fail(f"unsupported semantic attack operation: {op!r}")
    return result


def _expectation_failures(output: Any, expected: Any, returncode: int) -> list[str]:
    if not isinstance(expected, dict):
        fail("expected contract must be an object")
    failures: list[str] = []
    expected_returncode = expected.get("returncode", 0)
    if returncode != expected_returncode:
        failures.append(f"returncode: expected {expected_returncode}, got {returncode}")
    json_expectations = expected.get("json", {})
    if not isinstance(json_expectations, dict):
        fail("expected.json must be a JSON-pointer map")
    for pointer, expected_value in json_expectations.items():
        try:
            actual = core.json_pointer_get(output, pointer)
        except core.PublicationError as exc:
            failures.append(str(exc))
            continue
        if actual != expected_value:
            failures.append(f"{pointer}: expected {expected_value!r}, got {actual!r}")
    reason = expected.get("reason_code_contains")
    if reason is not None:
        try:
            reason_codes = core.json_pointer_get(output, expected.get("reason_codes_pointer", "/reason_codes"))
        except core.PublicationError as exc:
            failures.append(str(exc))
        else:
            if not isinstance(reason_codes, list) or reason not in reason_codes:
                failures.append(f"reason code {reason!r} not present in {reason_codes!r}")
    if isinstance(output, dict):
        if output.get("production_authority_allowed") is not False:
            failures.append("production authority was not explicitly false")
        if output.get("execution_authority_allowed") is not False:
            failures.append("execution authority was not explicitly false")
    else:
        failures.append("adapter output is not an object")
    return failures


def _adapter_identity(command: str) -> dict[str, Any]:
    arguments = shlex.split(command)
    identity: dict[str, Any] = {
        "command_digest": core.sha256_bytes(command.encode("utf-8")),
        "arguments": arguments,
    }
    for argument in arguments:
        path = Path(argument)
        if path.is_file() and not path.is_symlink():
            identity["first_existing_file"] = str(path.resolve())
            identity["first_existing_file_digest"] = core.sha256_file(path)
            break
    return identity


def _run_adapter(
    command_template: str,
    *,
    input_path: Path,
    output_path: Path,
    cwd: Path,
    timeout: int,
) -> dict[str, Any]:
    command = command_template.replace("{input}", str(input_path)).replace("{output}", str(output_path))
    arguments = shlex.split(command)
    if not arguments:
        fail("adapter command is empty")
    environment = os.environ.copy()
    environment["DAI_ATTACK_INPUT"] = str(input_path)
    environment["DAI_ATTACK_OUTPUT"] = str(output_path)
    started = time.monotonic()
    completed = subprocess.run(
        arguments,
        cwd=str(cwd),
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    output: Any = {}
    parse_error: str | None = None
    if output_path.is_file():
        try:
            output = core.load_json_file(output_path)
        except core.PublicationError as exc:
            parse_error = str(exc)
    else:
        parse_error = "adapter output missing"
    return {
        "returncode": completed.returncode,
        "output": output,
        "parse_error": parse_error,
        "stdout_digest": core.sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_digest": core.sha256_bytes(completed.stderr.encode("utf-8")),
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
        "elapsed_ms": elapsed_ms,
    }


def run_attack_plan(
    plan_path: Path,
    *,
    adapter: str,
    output_path: Path,
    subject_core_capsule_sha256: str,
    timeout: int,
) -> dict[str, Any]:
    core.refuse_optimized_python()
    if not core.SHA256_RE.fullmatch(subject_core_capsule_sha256):
        fail("subject core capsule digest is invalid")
    plan = core.load_json_file(plan_path)
    if not isinstance(plan, dict) or plan.get("schema") != "dai.semantic-attack-plan.v1":
        fail("unsupported semantic attack plan schema")
    baseline_relative = core.normalize_relative_path(plan.get("baseline_input"))
    baseline_path = plan_path.parent.joinpath(*Path(baseline_relative).parts)
    baseline = core.load_json_file(baseline_path)
    baseline_expected = plan.get("baseline_expected")
    attacks = plan.get("attacks")
    if not isinstance(attacks, list) or not attacks:
        fail("semantic attack plan contains no attacks")
    attack_ids = [item.get("id") for item in attacks if isinstance(item, dict)]
    if len(attack_ids) != len(attacks) or any(not isinstance(item, str) or not item for item in attack_ids):
        fail("every attack must have a non-empty string id")
    if len(set(attack_ids)) != len(attack_ids):
        fail("semantic attack IDs must be unique")
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="dai-semantic-attack-") as temporary:
        temporary_root = Path(temporary)

        def execute(case_id: str, value: Any, expected: Any, ordinal: int, threat_class: str) -> dict[str, Any]:
            input_path = temporary_root / f"{ordinal:04d}-{case_id}.input.json"
            output_file = temporary_root / f"{ordinal:04d}-{case_id}.output.json"
            core.write_canonical_json(input_path, value)
            execution = _run_adapter(
                adapter,
                input_path=input_path,
                output_path=output_file,
                cwd=plan_path.parent,
                timeout=timeout,
            )
            failures: list[str] = []
            if execution["parse_error"]:
                failures.append(execution["parse_error"])
            else:
                failures.extend(
                    _expectation_failures(
                        execution["output"],
                        expected,
                        execution["returncode"],
                    )
                )
            return {
                "id": case_id,
                "threat_class": threat_class,
                "passed": not failures,
                "failures": failures,
                "input_digest": core.sha256_file(input_path),
                "output_digest": core.sha256_file(output_file) if output_file.is_file() else None,
                "returncode": execution["returncode"],
                "stdout_digest": execution["stdout_digest"],
                "stderr_digest": execution["stderr_digest"],
                "stdout_tail": execution["stdout_tail"],
                "stderr_tail": execution["stderr_tail"],
                "elapsed_ms": execution["elapsed_ms"],
            }

        baseline_result = execute("baseline", baseline, baseline_expected, 0, "control")
        if not baseline_result["passed"]:
            results.append(baseline_result)
        else:
            results.append(baseline_result)
            for index, attack in enumerate(attacks, start=1):
                if not isinstance(attack, dict):
                    fail("attack entry is not an object")
                mutated = apply_operations(baseline, attack.get("operations", []))
                results.append(
                    execute(
                        attack["id"],
                        mutated,
                        attack.get("expected"),
                        index,
                        str(attack.get("threat_class", "unspecified")),
                    )
                )
    report = {
        "schema": "dai.semantic-mutation-report.v1",
        "subject_core_capsule_sha256": subject_core_capsule_sha256,
        "plan_digest": core.sha256_file(plan_path),
        "baseline_input_digest": core.sha256_file(baseline_path),
        "adapter_identity": _adapter_identity(adapter),
        "passed": all(item["passed"] for item in results),
        "case_count": len(results),
        "attack_count": len(results) - 1,
        "passed_count": sum(1 for item in results if item["passed"]),
        "results": results,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    core.write_canonical_json(output_path, report)
    if not report["passed"]:
        fail(f"semantic attack plan failed; see {output_path}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subject-core-capsule-sha256", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_attack_plan(
            args.plan,
            adapter=args.adapter,
            output_path=args.output,
            subject_core_capsule_sha256=args.subject_core_capsule_sha256,
            timeout=args.timeout,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (core.PublicationError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"DAI semantic attack failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
