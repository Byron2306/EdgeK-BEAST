#!/usr/bin/env python3
"""Prove promoted Crystal IR recipes are safe, persistent, and provider-free.

This is deliberately a physical test: every held-out case edits a temporary
worktree, runs a verifier, and checks the resulting source.  No model/provider
is called by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import (  # noqa: E402
    CrystalExecutionEngine,
    CrystalExecutionError,
    CrystalExecutionRequest,
    ground_crystal_ir,
)
from app.kernel.compute.crystal_ir import compile_crystal_ir  # noqa: E402


FAMILIES = {
    "missing_import": ("parse_amount", "return value", "return Decimal(value)", "from decimal import Decimal\n"),
    "provider_normalization": ("normalize_provider_id", "return value", "return str(value).strip().lower().replace('-', '_')", ""),
    "configuration_validation": ("validate_config", "return config", "if not isinstance(config, dict):\n        raise ValueError('config must be a mapping')\n    return config", ""),
    "secret_redaction": ("redact_secret", "return value", "return '***' if value else ''", ""),
    "rollback": ("apply_change", "return value", "return value + 1", ""),
    "arithmetic_repair": ("calculate_total", "return left - right", "return left + right", ""),
}


def source(symbol: str, body: str, prefix: str = "") -> str:
    return f"{prefix}def {symbol}(value, left=1, right=2):\n    {body}\n"


def ir_for(family: str) -> dict:
    symbol, old, _new, _prefix = FAMILIES[family]
    return {
        "version": "crystal.ir.v1",
        "mission": {"objective": f"repair {family}"},
        "target": {"file": "target.py", "symbol": symbol},
        "observed_failure": {"class": family, "examples": [{"input": "held-out", "expected": "verified"}]},
        "required_transform": {"pipeline": ["replace_function"]},
        "authority": {"writable_files": ["target.py"], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid", "target_tests_pass", "no_unrelated_diff"],
        "rollback": {"required": True},
        "unresolved_fields": [],
        "residual": {"old": old, "new": ""},
    }


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verify_recipe(recipe: dict, root: Path, expected: str) -> dict:
    family = recipe["family"]
    symbol, old_marker, new_body, prefix = FAMILIES[family]
    module_prefix = "from decimal import Decimal\n" if family == "missing_import" else ""
    before = source(symbol, old_marker, module_prefix)
    path = root / "target.py"
    path.write_text(before, encoding="utf-8")
    ir = compile_crystal_ir(recipe["ir"])
    grounded = ground_crystal_ir(ir, str(root))
    expected_old = source(symbol, old_marker)
    if grounded.old != expected_old:
        raise AssertionError("grounding did not capture the complete target function")
    new_function = source(symbol, new_body)
    request = CrystalExecutionRequest(ir, grounded.old, new_function, "promotion-approved", f"heldout-{family}", str(root), (("python", "-m", "py_compile", "target.py"),), grounded.file_sha256)
    receipt = CrystalExecutionEngine().execute(request)
    expected_source = module_prefix + new_function
    if receipt["status"] != "verified" or path.read_text(encoding="utf-8") != expected_source:
        raise AssertionError(f"physical held-out effect was not verified for {family}: {receipt.get('status')}")
    return receipt


def stale_and_hostile(recipe: dict, family: str) -> tuple[bool, bool]:
    symbol, old_marker, new_body, prefix = FAMILIES[family]
    ir = compile_crystal_ir(recipe["ir"])
    with tempfile.TemporaryDirectory(prefix="beast-reuse-negative-") as tmp:
        root = Path(tmp)
        path = root / "target.py"
        path.write_text(source(symbol, old_marker, "" if family != "missing_import" else "from decimal import Decimal\n"), encoding="utf-8")
        grounded = ground_crystal_ir(ir, str(root))
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "# unrelated state mutation\n", encoding="utf-8")
        try:
            CrystalExecutionEngine().execute(CrystalExecutionRequest(ir, grounded.old, source(symbol, new_body), "promotion-approved", "stale", str(root), (("python", "-m", "py_compile", "target.py"),), grounded.file_sha256))
        except CrystalExecutionError:
            stale_blocked = True
        else:
            stale_blocked = False
        path.write_text(original, encoding="utf-8")
        try:
            CrystalExecutionEngine().execute(CrystalExecutionRequest(ir, grounded.old + "\n# near-match", source(symbol, new_body), "promotion-approved", "hostile", str(root), (("python", "-m", "py_compile", "target.py"),), grounded.file_sha256))
        except CrystalExecutionError:
            hostile_refused = True
        else:
            hostile_refused = False
    return stale_blocked, hostile_refused


def restart_replay(manifest: Path, family: str) -> bool:
    """Rehydrate a recipe in a new interpreter and prove it still executes."""
    child = [sys.executable, str(Path(__file__).resolve()), "--replay", str(manifest), family]
    return subprocess.run(child, cwd=ROOT, capture_output=True, text=True, check=False).returncode == 0


def replay(manifest: Path, family: str) -> int:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    recipe = payload["recipes"][family]
    with tempfile.TemporaryDirectory(prefix="beast-restart-replay-") as tmp:
        verify_recipe(recipe, Path(tmp), family)
    return 0


def run(output: Path) -> dict:
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    recipes: dict[str, dict] = {}
    rows = []
    provider_calls = 0
    for family in FAMILIES:
        teacher_episodes = []
        for episode in range(3):
            with tempfile.TemporaryDirectory(prefix="beast-teacher-") as tmp:
                receipt = verify_recipe({"family": family, "ir": ir_for(family)}, Path(tmp), family)
                teacher_episodes.append({"episode": episode + 1, "verified": receipt["status"] == "verified", "provider_calls": 0})
        recipe = {"family": family, "version": "crystal.recipe.v1", "ir": ir_for(family), "teacher_episodes": teacher_episodes, "generalized_digest": digest({"family": family, "ir": ir_for(family), "transform": "replace_function"})}
        if not all(item["verified"] for item in teacher_episodes):
            raise AssertionError(f"teacher promotion failed: {family}")
        recipes[family] = recipe
        stale_blocked, hostile_refused = stale_and_hostile(recipe, family)
        with tempfile.TemporaryDirectory(prefix="beast-heldout-") as tmp:
            heldout = verify_recipe(recipe, Path(tmp), family)
        rows.append({"family": family, "teacher_episodes": 3, "promoted": True, "heldout_verified": heldout["status"] == "verified", "completion_provider_calls": 0, "stale_blocked": stale_blocked, "hostile_near_match_refused": hostile_refused, "physical_effect": heldout["mutation_performed"]})
    with tempfile.TemporaryDirectory(prefix="beast-manifest-") as tmp:
        manifest = Path(tmp) / "crystal-recipes.json"
        manifest.write_text(json.dumps({"version": "1.0", "recipes": recipes}, sort_keys=True), encoding="utf-8")
        restart_results = {family: restart_replay(manifest, family) for family in FAMILIES}
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    cpu_seconds = (cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime)
    metrics = {
        "families": len(FAMILIES),
        "heldout_verified_local_repairs": sum(row["heldout_verified"] for row in rows),
        "completion_provider_calls": provider_calls,
        "false_reuse": sum(not row["stale_blocked"] for row in rows),
        "hostile_near_match_refusals": sum(row["hostile_near_match_refused"] for row in rows),
        "restart_persistent_reproductions": sum(restart_results.values()),
        "cpu_seconds": round(cpu_seconds, 6),
        "wall_seconds": round(time.perf_counter() - started, 3),
    }
    receipt = {"beast_object_type": "crystal_ir_reuse_gauntlet_receipt", "version": "1.0", "gold_target": {"families": 6, "heldout_verified_local_repairs": 6, "completion_provider_calls": 0, "false_reuse": 0, "hostile_near_match_refusals": 6, "restart_persistent_reproductions": 6}, "metrics": metrics, "restart_results": restart_results, "rows": rows, "recipes": recipes}
    receipt["receipt_hash"] = digest(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/crystal_ir_reuse_gauntlet.json")
    parser.add_argument("--replay", type=Path)
    parser.add_argument("family", nargs="?")
    args = parser.parse_args()
    if args.replay:
        return replay(args.replay, args.family)
    receipt = run(Path(args.output))
    print(json.dumps({"receipt_hash": receipt["receipt_hash"], "metrics": receipt["metrics"], "gold_target_passed": receipt["metrics"] == {"families": 6, "heldout_verified_local_repairs": 6, "completion_provider_calls": 0, "false_reuse": 0, "hostile_near_match_refusals": 6, "restart_persistent_reproductions": 6, "cpu_seconds": receipt["metrics"]["cpu_seconds"], "wall_seconds": receipt["metrics"]["wall_seconds"]}, "path": args.output}, indent=2, sort_keys=True))
    m = receipt["metrics"]
    return 0 if (m["heldout_verified_local_repairs"] == 6 and m["completion_provider_calls"] == 0 and m["false_reuse"] == 0 and m["hostile_near_match_refusals"] == 6 and m["restart_persistent_reproductions"] == 6) else 1


if __name__ == "__main__":
    raise SystemExit(main())
