#!/usr/bin/env python3
"""Run a provider-free, physical Crystal IR coding gauntlet.

Every case creates a real temporary repository with broken source and tests.
The model/provider boundary is intentionally absent: this proves the local
Crystal IR -> grounding -> bounded Action IR -> execution -> verification
chain independently of Ollama or any external service.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import (  # noqa: E402
    CrystalExecutionEngine,
    CrystalExecutionError,
    CrystalExecutionRequest,
    ground_crystal_ir,
)
from app.kernel.compute.crystal_ir import (  # noqa: E402
    compile_intent_candidate,
    compile_crystal_ir_from_intent,
    deterministic_intent,
    deterministic_preflight,
)
from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe


def digest(value: object) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


CASES = [
    {
        "id": "provider_identifier_normalization",
        "capability": "typed string normalization",
        "objective": "provider identifier normalization",
        "symbol": "normalize_provider",
        "source": "def normalize_provider(value):\n    return value\n",
        "fixed": "def normalize_provider(value):\n    return str(value).strip().lower().replace('-', '_').replace(' ', '_')\n",
        "test": "from app.provider import normalize_provider\n\ndef test_provider_aliases():\n    assert normalize_provider(' NVIDIA-NIM ') == 'nvidia_nim'\n    assert normalize_provider('Open AI') == 'open_ai'\n",
    },
    {
        "id": "missing_import_repair",
        "capability": "dependency/import repair",
        "objective": "missing import repair",
        "symbol": "parse_amount",
        "source": "def parse_amount(value):\n    return Decimal(str(value))\n",
        "fixed": "from decimal import Decimal\n\ndef parse_amount(value):\n    return Decimal(str(value))\n",
        "test": "from decimal import Decimal\nfrom app.amount import parse_amount\n\ndef test_decimal_parser():\n    assert parse_amount('1.25') == Decimal('1.25')\n",
        "whole_file": True,
    },
    {
        "id": "arithmetic_correction",
        "capability": "semantic arithmetic correction",
        "objective": "one function arithmetic correction",
        "symbol": "calculate_total",
        "source": "def calculate_total(left, right):\n    return left - right\n",
        "fixed": "def calculate_total(left, right):\n    return left + right\n",
        "test": "from app.math_ops import calculate_total\n\ndef test_total():\n    assert calculate_total(7, 5) == 12\n",
    },
    {
        "id": "configuration_validation",
        "capability": "configuration contract enforcement",
        "objective": "configuration validation",
        "symbol": "validate_config",
        "source": "def validate_config(config):\n    return config\n",
        "fixed": "def validate_config(config):\n    if not isinstance(config, dict):\n        raise ValueError('config must be a mapping')\n    if not config.get('model'):\n        raise ValueError('model is required')\n    return config\n",
        "test": "import pytest\nfrom app.config import validate_config\n\ndef test_config_contract():\n    assert validate_config({'model': 'local'})['model'] == 'local'\n    with pytest.raises(ValueError):\n        validate_config([])\n    with pytest.raises(ValueError):\n        validate_config({})\n",
    },
    {
        "id": "secret_redaction",
        "capability": "secret handling policy",
        "objective": "secret redaction policy",
        "symbol": "redact_secret",
        "source": "def redact_secret(value):\n    return value\n",
        "fixed": "def redact_secret(value):\n    return '***' if value else ''\n",
        "test": "from app.secrets import redact_secret\n\ndef test_secret_is_not_exposed():\n    assert redact_secret('token-123') == '***'\n    assert redact_secret('') == ''\n",
    },
    {
        "id": "path_traversal_guard",
        "capability": "security boundary enforcement",
        "objective": "security path traversal repair",
        "symbol": "safe_join",
        "source": "import os\n\ndef safe_join(root, name):\n    return os.path.join(root, name)\n",
        "fixed": "import os\n\ndef safe_join(root, name):\n    base = os.path.abspath(root)\n    candidate = os.path.abspath(os.path.join(base, name))\n    if candidate != base and not candidate.startswith(base + os.sep):\n        raise ValueError('path escapes root')\n    return candidate\n",
        "test": "import pytest\nfrom app.paths import safe_join\n\ndef test_path_is_contained(tmp_path):\n    assert safe_join(str(tmp_path), 'a.txt').startswith(str(tmp_path))\n    with pytest.raises(ValueError):\n        safe_join(str(tmp_path), '../secret')\n",
        "whole_file": True,
    },
    {
        "id": "retry_backoff_policy",
        "capability": "bounded exponential retry policy",
        "objective": "retry policy correction",
        "symbol": "retry_delay",
        "source": "def retry_delay(attempt, base=0.25, cap=8.0):\n    return base * attempt\n",
        "fixed": "def retry_delay(attempt, base=0.25, cap=8.0):\n    return min(cap, base * (2 ** max(0, attempt - 1)))\n",
        "test": "from app.retry import retry_delay\n\ndef test_exponential_capped_backoff():\n    assert retry_delay(1) == 0.25\n    assert retry_delay(3) == 1.0\n    assert retry_delay(20) == 8.0\n",
    },
    {
        "id": "async_timeout_boundary",
        "capability": "async cancellation and timeout",
        "objective": "async request timeout repair",
        "symbol": "fetch_with_timeout",
        "source": "import asyncio\n\nasync def fetch_with_timeout(operation, timeout):\n    return await operation()\n",
        "fixed": "import asyncio\n\nasync def fetch_with_timeout(operation, timeout):\n    return await asyncio.wait_for(operation(), timeout=timeout)\n",
        "test": "import asyncio\nimport pytest\nfrom app.async_ops import fetch_with_timeout\n\nasync def slow():\n    await asyncio.sleep(0.05)\n    return 'ok'\n\ndef test_timeout_boundary():\n    with pytest.raises(asyncio.TimeoutError):\n        asyncio.run(fetch_with_timeout(slow, 0.001))\n",
        "whole_file": True,
    },
]

MODULES = {
    "provider_identifier_normalization": "provider",
    "missing_import_repair": "amount",
    "arithmetic_correction": "math_ops",
    "configuration_validation": "config",
    "secret_redaction": "secrets",
    "path_traversal_guard": "paths",
    "retry_backoff_policy": "retry",
    "async_timeout_boundary": "async_ops",
}


def write_case(root: Path, case: dict) -> tuple[Path, Path]:
    target = root / "workload" / f"{MODULES[case['id']]}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(case["source"], encoding="utf-8")
    (root / "workload" / "__init__.py").write_text("", encoding="utf-8")
    tests = root / "tests" / f"test_{case['id']}.py"
    tests.parent.mkdir(parents=True, exist_ok=True)
    tests.write_text(case["test"].replace("from app.", "from workload."), encoding="utf-8")
    return target, tests


def ir_for(case: dict):
    candidate = deterministic_intent(case["objective"], case["objective"], target_symbol=case["symbol"])
    if candidate is None:
        candidate = compile_intent_candidate({
            "s": "interpreted",
            "f": case["id"],
            "sym": case["symbol"],
            "fc": f"{case['id']}_failure",
            "fx": "bounded_local_repair",
            "c": ["tests_immutable", "network_forbidden", "single_effect", "minimal_scope"],
        })
    return candidate, compile_crystal_ir_from_intent(
        candidate,
        objective=case["objective"],
        target_file=f"workload/{MODULES[case['id']]}.py",
        target_symbol=case["symbol"],
    )


def execute(root: Path, ir, old: str, new: str, case_id: str, tests: Path, expected_hash: str):
    request = CrystalExecutionRequest(
        ir,
        old,
        new,
        "local-gauntlet-approval",
        f"local-gauntlet-{case_id}",
        str(root),
        (("python", "-m", "py_compile", ir.target_file), ("pytest", "-q", str(tests.relative_to(root)))),
        expected_hash,
    )
    return CrystalExecutionEngine().execute(request)


def negative_controls(root: Path, ir, grounded, case: dict, target: Path, tests: Path) -> dict:
    original = target.read_text(encoding="utf-8")
    results = {}
    target.write_text(original + "\n# stale unrelated mutation\n", encoding="utf-8")
    try:
        execute(root, ir, grounded.old, case["fixed"], case["id"], tests, grounded.file_sha256)
    except CrystalExecutionError:
        results["stale_fingerprint_blocked"] = True
    else:
        results["stale_fingerprint_blocked"] = False
    target.write_text(original, encoding="utf-8")
    try:
        execute(root, ir, grounded.old + "\n# hostile near match", case["fixed"], case["id"], tests, grounded.file_sha256)
    except CrystalExecutionError:
        results["hostile_near_match_blocked"] = True
    else:
        results["hostile_near_match_blocked"] = False
    target.write_text(original, encoding="utf-8")
    try:
        execute(root, ir, grounded.old, "complete replacement source", case["id"], tests, grounded.file_sha256)
    except CrystalExecutionError:
        results["placeholder_blocked"] = True
    else:
        results["placeholder_blocked"] = False
    target.write_text(original, encoding="utf-8")
    unsafe = deterministic_preflight({"target": {"file": "../outside.py", "symbol": case["symbol"]}, "authority": {"network_allowed": False, "tests_mutable": False, "maximum_effects": 1}})
    results["unsafe_target_refused"] = bool(unsafe and unsafe.status == "refuse")
    return results


def run_case(case: dict) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"beast-local-{case['id']}-") as temp:
        root = Path(temp)
        target, tests = write_case(root, case)
        candidate, ir = ir_for(case)
        preflight = deterministic_preflight({"target": {"file": ir.target_file, "symbol": ir.target_symbol}, "authority": {"network_allowed": False, "tests_mutable": False, "maximum_effects": 1}, "mission": {"objective": case["objective"]}})
        if preflight is not None:
            raise AssertionError(f"safe case was vetoed: {case['id']}: {preflight.to_dict()}")
        grounded = ground_crystal_ir(ir, str(root))
        current = target.read_text(encoding="utf-8")
        old, new = (current, case["fixed"]) if case.get("whole_file") else (grounded.old, case["fixed"])
        action_ir = {"kind": "replace_exact", "slot_type": "file" if case.get("whole_file") else "function", "path": ir.target_file, "symbol": ir.target_symbol, "old_sha256": digest(old), "new_sha256": digest(new), "maximum_effects": 1}
        rollback_probe = {}
        try:
            execute(root, ir, old, "def malformed(:\n", case["id"], tests, grounded.file_sha256)
        except CrystalExecutionError:
            rollback_probe = {"failed_candidate_rolled_back": target.read_text(encoding="utf-8") == current}
        receipt = execute(root, ir, old, new, case["id"], tests, grounded.file_sha256)
        negatives = negative_controls(root, ir, grounded, case, target, tests)
        return {
            "id": case["id"],
            "status": receipt["status"],
            "candidate": candidate.to_dict(),
            "pipeline": {"deterministic_preflight": "clear", "cartographer_grounding": "exact", "action_ir": action_ir, "syntax_preflight": "passed", "isolated_mutation": receipt["mutation_performed"], "verification": receipt["verification"], "rollback_probe": rollback_probe},
            "negative_controls": negatives,
            "receipt": receipt,
            "source_fingerprints": {"before": digest(current), "after": digest(target.read_bytes())},
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/crystal_ir_local_matrix_gauntlet.json")
    args = parser.parse_args()
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    rows = [run_case(case) for case in CASES]
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    metrics = {
        "cases": len(rows),
        "verified_repairs": sum(row["status"] == "verified" for row in rows),
        "provider_calls": 0,
        "rollback_probes_passed": sum(row["pipeline"]["rollback_probe"].get("failed_candidate_rolled_back") is True for row in rows),
        "stale_blocks": sum(row["negative_controls"]["stale_fingerprint_blocked"] for row in rows),
        "hostile_blocks": sum(row["negative_controls"]["hostile_near_match_blocked"] for row in rows),
        "placeholder_blocks": sum(row["negative_controls"]["placeholder_blocked"] for row in rows),
        "unsafe_target_refusals": sum(row["negative_controls"]["unsafe_target_refused"] for row in rows),
        "cpu_seconds": round((cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime), 6),
        "wall_seconds": round(time.perf_counter() - started, 3),
    }
    receipt = {"beast_object_type": "crystal_ir_local_matrix_gauntlet_receipt", "version": "1.0", "provider_calls": 0, "matrix": [{"id": item["id"], "objective": item["objective"], "capability": item["capability"]} for item in CASES], "metrics": metrics, "rows": rows, "claim_boundary": "Synthetic local repositories prove Crystal IR execution and safety controls, not model intelligence."}
    receipt["receipt_hash"] = digest(receipt)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pack = output.with_name(output.stem + "_pack")
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "matrix_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (pack / "README.md").write_text("# Crystal IR Local Matrix Gauntlet\n\nEight real temporary repositories, bounded edits, local verification, rollback, and refusal controls. No provider calls.\n", encoding="utf-8")
    manifest = {"files": {path.name: digest(path.read_bytes()) for path in pack.iterdir() if path.is_file()}}
    manifest["manifest_hash"] = digest(manifest)
    (pack / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(pack.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in pack.iterdir():
            if path.is_file():
                bundle.write(path, path.name)
    print(json.dumps({"path": str(output), "pack": str(pack.with_suffix('.zip')), "receipt_hash": receipt["receipt_hash"], "metrics": metrics}, indent=2, sort_keys=True))
    return 0 if metrics["verified_repairs"] == len(CASES) and all(metrics[key] == len(CASES) for key in ("rollback_probes_passed", "stale_blocks", "hostile_blocks", "placeholder_blocks", "unsafe_target_refusals")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
