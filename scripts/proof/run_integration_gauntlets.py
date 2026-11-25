#!/usr/bin/env python3
"""Run independently scoped BEAST proof suites and preserve their evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
CHECKS = "scripts/proof/integration_gauntlet_checks.py"
SUITES = {
    "crystals": (
        ["tests/test_crystal_fabric_closed_loop.py",
         "tests/test_coding_crystals.py::test_failed_envelope_records_negative_evidence_and_no_candidate",
         "tests/test_coding_crystal_wiring.py::test_learn_from_run_extracts_replays_three_variants_and_promotes"],
        "Disposable repos, real verifier and registry, scripted planner versus crystal reuse. No live model."),
    "lattice": (
        [f"{CHECKS}::test_flat_vs_lattice_nomination_on_same_registry",
         "tests/test_crystal_lattice_spine.py::test_two_child_composite_admitted_only_when_children_and_composite_pass",
         "tests/test_crystal_lattice_spine.py::test_child_demotion_cascades_upward"],
        "Same registry, flat versus lattice nomination and synthetic admission/demotion. No live composite replay."),
    "bus": (
        ["tests/test_consolidated_crystal_bus.py"],
        "Real Linux Unix-socket/memfd descriptor transfer with test keys and positive/negative custody controls. "
        "Not production authority, cross-host delivery or agent execution."),
    "kv": (
        ["tests/test_kv_cache_transport.py::test_lookup_returns_none_for_mismatch",
         "tests/test_kv_cache_transport.py::test_metadata_only_block_cannot_be_persisted_or_transferred",
         "tests/test_kv_cache_transport.py::test_engine_native_tensor_payload_round_trips_through_storage",
         "tests/test_kv_cache_transport.py::test_network_transfer_is_received_verified_and_persisted"],
        "Transport and digest checks with synthetic payload bytes and an in-process sender. "
        "No native model-engine import, token savings or latency claim."),
    "memory": (
        [f"{CHECKS}::test_memory_hull_empty_seed_tamper_recall",
         "tests/test_memory_hull_residue_passport.py::test_memory_hull_writes_editable_markdown_and_signed_sidecar",
         "tests/test_memory_hull_residue_passport.py::test_memory_hull_rejects_markdown_and_sidecar_tampering"],
        "Empty, intact, and tampered residue controls at Coder's advisory packet boundary. No model call."),
    "compression": (
        [f"{CHECKS}::test_focused_ask_provider_packet_compression_toggle", "tests/test_compression_tiers.py"],
        "Compressor correctness and focused Ask provider-handoff byte comparison, same task and scripted response. "
        "No provider-reported token savings."),
}


def run_suite(name: str, out: Path) -> dict:
    tests, boundary = SUITES[name]
    folder = out / name
    folder.mkdir()
    report = folder / "pytest.xml"
    cmd = [sys.executable, "-m", "pytest", "--noconftest", "-o", "addopts=", "-o", "cache_dir=" + str(folder / "cache"),
           "--basetemp", str(folder / "tmp"), "--junitxml", str(report), "-q", "-s", *tests]
    # Keep caller pytest settings from altering selection, and do not pass
    # real provider credentials or the normal gateway's state configuration.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "VIRTUAL_ENV")
           if key in os.environ}
    home = folder / "home"
    home.mkdir(mode=0o700)
    env["HOME"] = str(home)
    env["BEAST_STATE_ROOT"] = str(folder / "state")
    env["BEAST_RUNTIME_GOVERNOR_DB"] = str(folder / "runtime.db")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Fixture helpers initialize local stores; keep defaults rooted in the
    # per-suite environment rather than an inherited state setting.
    start = time.monotonic()
    with (folder / "run.log").open("w", encoding="utf-8") as log:
        try:
            code = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=300, check=False).returncode
        except subprocess.TimeoutExpired:
            code = 124
            log.write("\nGauntlet timed out.\n")
    evidence = []
    for line in (folder / "run.log").read_text(encoding="utf-8", errors="replace").splitlines():
        for prefix in ("GAUNTLET_EVIDENCE ", "CRYSTAL_FABRIC_EFFICIENCY "):
            if prefix in line:
                try:
                    evidence.append(json.loads(line.split(prefix, 1)[1]))
                except ValueError:
                    pass
    counts = dict.fromkeys(("tests", "failures", "errors", "skipped"), 0)
    try:
        if report.is_file():
            for suite in ElementTree.parse(report).getroot().iter("testsuite"):
                for key in counts:
                    counts[key] += int(suite.get(key, 0))
    except (OSError, ValueError, ElementTree.ParseError):
        counts["errors"] += 1
    status = ("FAIL" if code or counts["failures"] or counts["errors"] else
              "INCOMPLETE" if not counts["tests"] or counts["skipped"] else "PASS")
    result = {
        "schema": "beast.integration_gauntlet.v1", "suite": name, "status": status,
        "claim_boundary": boundary, "returncode": code, "counts": counts, "evidence": evidence,
        "suite_wall_seconds": round(time.monotonic() - start, 3),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "selected_test_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() if (ROOT / path).is_file() else None
            for path in sorted({spec.split("::")[0] for spec in tests})
        },
    }
    (folder / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{name:11s} {status:10s} {folder / 'receipt.json'}", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="+", choices=[*SUITES, "all"])
    parser.add_argument("--output", type=Path, help="New result directory. Default is a unique temporary directory.")
    args = parser.parse_args()
    if args.output:
        output = args.output.expanduser().resolve()
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix="beast-gauntlets-"))
    requested = list(SUITES) if "all" in args.suite else list(dict.fromkeys(args.suite))
    results = [run_suite(name, output) for name in requested]
    (output / "summary.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SUMMARY {output / 'summary.json'}", flush=True)
    return int(any(row["status"] != "PASS" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
