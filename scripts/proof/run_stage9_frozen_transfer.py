"""Evaluate frozen crystal ordering on new dependencies against a local planner."""

import argparse
import json
from pathlib import Path
import random
import subprocess
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from app.kernel.compute import family_crystals as fc
from app.kernel.compute.coding_crystals import resolve_constant
from scripts.gauntlet_large_tasks import _task, _unit, dual_diff
from scripts.proof.run_behemoth_phase2 import digest, install_fixture
from scripts.proof.run_stage9_lattice import read_children, run_sequence, signal_key

MECHANISMS = ("config_consumed_by_page", "page_unlocks_config")


def dependency_fixture(seed, mechanism):
    rng = random.Random(seed)
    pkg = f"transfer{seed:x}"
    old, new = rng.randrange(2, 4), rng.randrange(6, 9)
    source = f"PAGE_SIZE = {old}\n\ndef last_n(items, n):\n    return items[-n - 1:]\n"
    if mechanism == "config_consumed_by_page":
        source += "\n\ndef page(items):\n    return last_n(items, PAGE_SIZE)\n"
        imports = "PAGE_SIZE, page"
        cases = [("width", f"self.assertEqual(PAGE_SIZE, {new})"),
                 ("page", f"self.assertTrue(page(list(range(12))) == list(range({12-new}, 12)), 'page output mismatch')")]
        private = f"self.assertEqual(page(list(range(20))), list(range({20-new}, 20)))"
    elif mechanism == "page_unlocks_config":
        source += "\n\ndef configured_width():\n    return PAGE_SIZE if len(last_n([0, 1, 2, 3], 2)) == 2 else 0\n"
        imports = "PAGE_SIZE, last_n, configured_width"
        cases = [("width", f"self.assertEqual(configured_width(), {new})"),
                 ("page", "self.assertTrue(last_n(list(range(12)), 2) == [10, 11], 'page output mismatch')")]
        private = (f"self.assertEqual(configured_width(), {new})\n"
                   "self.assertEqual(last_n(['a', 'b', 'c', 'd', 'e'], 3), ['c', 'd', 'e'])")
    else:
        raise ValueError("unknown fixture mechanism")
    imp = f"from {pkg}.paging import {imports}"
    hidden = _unit(imp, [("intent", f"self.assertEqual(PAGE_SIZE, {new})\n{private}")])
    return _task("source_dependency", "holdout", pkg, {f"{pkg}/paging.py": source}, f"{pkg}/paging.py",
                 _unit(imp, cases), hidden)


def planner_order(bank, source, visible_failure):
    """Probe reviewed constant applicability once, then schedule without a learned graph."""
    constant = next(identifier for identifier, family in bank.items() if family == "fix-config-constant")
    other = next(identifier for identifier in bank if identifier != constant)
    return [constant, other] if resolve_constant(visible_failure, source) else [other, constant]


def load_frozen(path, expected_digest, children):
    raw = path.read_bytes()
    if digest(raw) != expected_digest:
        raise PermissionError("frozen graph failed its external digest pin")
    graph = json.loads(raw)
    roster = graph["component_ids"]
    if len(roster) != len(children) or set(roster) != set(children):
        raise PermissionError("frozen graph roster differs from pinned promoted crystals")
    for edge in graph["edges"].values():
        order = edge["order"]
        if len(order) != len(children) or set(order) != set(children):
            raise PermissionError("frozen edge is not a permutation of the component roster")
    return raw, graph


def evaluate_arm(label, children, frozen, signal, observed, root, task, folder, graph_pin):
    start = time.perf_counter()
    verify_calls = 0
    resolver_calls = 0
    original_verify = fc.run_verify
    def metered_verify(*args, **kwargs):
        nonlocal verify_calls
        verify_calls += 1
        return original_verify(*args, **kwargs)
    if label == "inspect_then_sequential":
        resolver_calls = 1
        order = planner_order({k: c.task_family for k, c in children.items()},
                              (root / task["target"]).read_text(), observed["output"])
    else:
        order = (frozen["edges"].get(signal) or {}).get("order")
    if not order:
        return {"verified": False, "refusal": "unseen_signature", "stages_attempted": 0,
                "dispatch_resolver_probes": resolver_calls, "verify_runs": 0,
                "fixture_unchanged": True, "total_ms": (time.perf_counter() - start) * 1000}
    with patch.object(fc, "run_verify", metered_verify):
        row = run_sequence(root, task, children, order, folder, graph_pin, label == "frozen_lattice")
    row.update(dispatch_resolver_probes=resolver_calls, verify_runs=verify_calls,
               total_ms=(time.perf_counter() - start) * 1000)
    return row


def experiment(args):
    args.out.mkdir(mode=0o700, exist_ok=False)
    report = args.out / "report"
    report.mkdir()
    labels = ["frozen_lattice", "inspect_then_sequential"]
    rows = []
    with TemporaryDirectory(prefix="beast-stage9-transfer-") as scratch:
        work = Path(scratch)
        db_snapshot = work / "read-only-snapshot.sqlite3"
        children = read_children(args.db, db_snapshot, args.component_id)
        registry_digest = digest(db_snapshot.read_bytes())
        raw, frozen = load_frozen(args.graph, args.graph_sha256, children)
        (report / "input_frozen_graph.json").write_bytes(raw)
        fixtures = [(args.seed + n, MECHANISMS[n % len(MECHANISMS)]) for n in range(args.repeats * 2)]
        fixtures.append((args.seed + args.repeats * 2, "wrong_family"))
        for seed, mechanism in fixtures:
            negative = mechanism == "wrong_family"
            task = (dual_diff("negative", f"negative{seed:x}", "PAGE_SIZE", 21, 53)
                    if negative else dependency_fixture(seed, mechanism))
            base = work / str(seed)
            root = install_fixture(base / "input", task)
            observed = fc.run_verify(task["verify"], root)
            if observed["failures"] != 2:
                raise RuntimeError("expected two measured visible defects")
            signal = signal_key(observed["output"])
            order = random.Random(seed).sample(labels, len(labels))
            arms = {}
            for label in order:
                arms[label] = evaluate_arm(label, children, frozen, signal, observed, root, task,
                                           base / label, args.graph_sha256)
            rows.append({"seed": seed, "mechanism": mechanism, "negative": negative,
                         "signal": signal, "shared_initial_verify_runs": 1, "execution_order": order, "arms": arms})
            print(f"{mechanism} seed={seed} signal={signal} " +
                  " ".join(f"{label}={arms[label]['verified']}" for label in order), flush=True)

    positives = [row for row in rows if not row["negative"]]
    controls_ok = (all(not arm["verified"] for arm in rows[-1]["arms"].values()) and
                   all(arm["fixture_unchanged"] and arm["stages_attempted"] <= 2
                       for row in rows for arm in row["arms"].values()))

    def metrics(group, label):
        attempts = [row["arms"][label] for row in group]
        return {key: sum(arm[key] for arm in attempts)
                for key in ("verified", "dispatch_resolver_probes", "verify_runs", "stages_attempted", "total_ms")}

    summary = {
        "schema": "beast.stage9.frozen_transfer.v1",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "frozen_graph_sha256": args.graph_sha256, "registry_snapshot_sha256": registry_digest,
        "positive_cases": len(positives), "cases_per_mechanism": args.repeats,
        "arms": {label: metrics(positives, label) for label in labels},
        "by_mechanism": {mechanism: {label: metrics([row for row in positives if row["mechanism"] == mechanism], label)
                                      for label in labels} for mechanism in MECHANISMS},
        "negative_verified_arms": [label for label in labels if rows[-1]["arms"][label]["verified"]],
        "controls_passed": controls_ok, "max_stages_per_arm": 2, "shared_initial_verify_runs": len(rows),
        "scope": "Frozen graph, two constructed source-level dependency mechanisms, same promoted components. "
                 "One non-model resolver applicability probe for planner dispatch. Counted verifier executions "
                 "include internal resolver probes and independent verification. No hosted requests.",
    }
    paths = [report / name for name in ("input_frozen_graph.json", "attempts.jsonl", "summary.json")]
    paths[1].write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    paths[2].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (report / "SHA256SUMS").write_text("".join(f"{digest(path.read_bytes())[7:]}  {path.name}\n" for path in paths))
    print(f"REPORT={report}")
    return 0 if controls_ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--graph-sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--component-id", action="append", default=[])
    parser.add_argument("--seed", type=int, default=74113)
    parser.add_argument("--repeats", type=int, choices=(2, 4, 6), default=4)
    args = parser.parse_args()
    args.db, args.graph, args.out = args.db.resolve(), args.graph.resolve(), args.out.resolve()
    if not args.db.is_file() or not args.graph.is_file():
        parser.error("existing registry and frozen graph required")
    if args.seed < 1 or (args.component_id and len(set(args.component_id)) != 2):
        parser.error("supply a positive seed and, if pinning components, two distinct IDs")
    return experiment(args)


if __name__ == "__main__":
    raise SystemExit(main())
