"""Learn two-crystal order edges from verified episodes and test frozen routing.

Constructed synthetic fixtures, promoted standalone crystals, distinct local
training processes. This does not claim unsupervised discovery of new opcodes,
cross-host learning, or production promotion.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from app.kernel.compute import family_crystals as fc
from scripts.gauntlet_large_tasks import _task, _unit, dual_diff
from scripts.proof.run_behemoth_phase2 import digest, execute, install_fixture

FAMILIES = {"fix-config-constant", "fix-off-by-one"}


def signal_key(output):
    literals = len(re.findall(r"^AssertionError: -?\d+ != -?\d+\s*$", output, re.M))
    return f"integer_mismatches:{literals}"


def learn_edges(rows):
    votes = defaultdict(lambda: defaultdict(set))
    for row in rows:
        if row["verified"]:
            votes[row["signal"]][tuple(row["order"])].add(row["node_id"])
    result = {}
    for signal, orders in sorted(votes.items()):
        ranked = sorted(orders, key=lambda order: (-len(orders[order]), order))
        best = ranked[0]
        if len(orders[best]) < 2 or (len(ranked) > 1 and len(orders[best]) == len(orders[ranked[1]])):
            continue
        result[signal] = {"order": list(best), "verified_nodes": sorted(orders[best])}
    return result


def make_fixture(seed, gated):
    rng = random.Random(seed)
    pkg = f"pager{seed:x}"
    old = rng.randrange(10, 80)
    new = old + rng.randrange(9, 31)
    src = f"PAGE_SIZE = {old}\n\ndef last_n(items, n):\n    return items[-n - 1:]\n"
    call = "last_n(list(range(8)), 2)"
    # In one fixture class the pagination test is gated on configuration.
    # In the other, its integer mismatch makes the constant resolver ambiguous.
    check = (f"self.assertTrue(PAGE_SIZE == {new} and {call} == [6, 7], 'paging contract')"
             if gated else f"self.assertEqual(len({call}), 2)")
    visible = _unit(f"from {pkg}.paging import PAGE_SIZE, last_n",
                    [("size", f"self.assertEqual(PAGE_SIZE, {new})"), ("page", check)])
    hidden = _unit(f"from {pkg}.paging import PAGE_SIZE, last_n",
                   [("intent", f"self.assertEqual(PAGE_SIZE, {new})\n"
                    "self.assertEqual(last_n(['a', 'b', 'c', 'd'], 2), ['c', 'd'])\n"
                    "self.assertEqual(last_n([4, 8, 9, 2, 6], 3), [9, 2, 6])")])
    return _task("composition_fixture", "pilot", pkg, {f"{pkg}/paging.py": src}, f"{pkg}/paging.py",
                 visible, hidden)


def read_children(db, snapshot, component_ids):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as dest:
            source.backup(dest)
    registry = fc.FamilyRegistry(snapshot)
    selected = [crystal for crystal in registry.promoted() if crystal.task_family in FAMILIES
                and not crystal.component_ids and (not component_ids or crystal.crystal_id in component_ids)]
    if len(selected) != 2 or {crystal.task_family for crystal in selected} != FAMILIES:
        raise ValueError("need one promoted standalone crystal in each supported family; pin ambiguous entries with --component-id")
    if not all(registry.get(c.crystal_id).get("promotion", {}).get("approved_by") for c in selected):
        raise PermissionError("standalone crystal approval missing")
    return {c.crystal_id: c for c in sorted(selected, key=lambda c: c.crystal_id)}


def run_sequence(root, task, children, order, folder, run_id, lattice):
    pristine = digest(fc.tree_digest(root))
    folder.mkdir()
    started = time.perf_counter()
    ordered = [children[identifier] for identifier in order]
    candidate = fc.compose(ordered, source_run_id=run_id) if lattice else None
    result = execute(root, task, candidate, ordered, folder, "lattice" if lattice else "sequential")
    receipts = result["stage_receipts"]
    return {
        "order": list(order), "verified": result["passed"], "final_tree": result["tree_after"],
        "fixture_unchanged": pristine == digest(fc.tree_digest(root)),
        "private": result.get("private"), "reason": result.get("reason"),
        "stages_attempted": len(receipts),
        "stage_model_calls_reported": sum(item["execution"]["model_calls"] for item in receipts),
        "stage_tool_calls_reported": sum(item["execution"]["tool_calls"] for item in receipts),
        "stage_outcomes": [item["execution"]["ok"] for item in receipts],
        "composite_id": candidate.crystal_id if candidate else None,
        "total_ms": (time.perf_counter() - started) * 1000,
    }


def case_setup(base, task):
    root = install_fixture(base / "input", task)
    observed = fc.run_verify(task["verify"], root)
    if observed["returncode"] == 0 or observed["failures"] != 2:
        raise RuntimeError("fixture must begin with two measured defects")
    return root, signal_key(observed["output"])


def train(input_path, output):
    config = json.loads(input_path.read_text())
    children = {value["crystal_id"]: fc.FamilyCrystal.from_dict(value) for value in config["children"]}
    rows = []
    with TemporaryDirectory(prefix="beast-stage9-node-") as work:
        for seed, gated in config["episodes"]:
            task = make_fixture(seed, gated)
            base = Path(work) / str(seed)
            root, signal = case_setup(base, task)
            for index, order in enumerate(itertools.permutations(children)):
                result = run_sequence(root, task, children, order, base / str(index), f"training-{seed}", False)
                rows.append({"node_id": config["node_id"], "node_pid": os.getpid(),
                             "seed": seed, "signal": signal, **result})
    output.write_text(json.dumps(rows, sort_keys=True))


def experiment(args):
    args.out.mkdir(mode=0o700, exist_ok=False)
    report = args.out / "report"
    report.mkdir()
    training = []
    with TemporaryDirectory(prefix="beast-stage9-") as work:
        work = Path(work)
        registry_snapshot = work / "registry.sqlite3"
        children = read_children(args.db, registry_snapshot, args.component_id)
        snapshot_hash = digest(registry_snapshot.read_bytes())
        train_started = time.perf_counter()
        for slot in range(3):
            node_id = f"local-train-{slot + 1}"
            node_input, node_output = work / f"{node_id}.json", work / f"{node_id}-episodes.json"
            # Distinct fixture instances per process. Workers do not get holdout seeds.
            episodes = [(args.train_seed + slot * 2 + index, bool(index)) for index in range(2)]
            node_input.write_text(json.dumps({"node_id": node_id, "episodes": episodes,
                                              "children": [c.to_dict() for c in children.values()]}))
            subprocess.run([sys.executable, "-m", "scripts.proof.run_stage9_lattice", "_train",
                            str(node_input), str(node_output)], check=True, timeout=180)
            training.extend(json.loads(node_output.read_text()))
        training_wall_ms = (time.perf_counter() - train_started) * 1000
        graph = {"min_distinct_nodes": 2, "component_ids": list(children), "edges": learn_edges(training)}
        freeze = report / "frozen_graph.json"
        freeze.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n")
        graph_sha = digest(freeze.read_bytes())
        frozen = json.loads(freeze.read_text())["edges"]
        heldout = []
        for index in range(args.pairs * 2 + 1):
            seed = args.holdout_seed + index
            negative = index == args.pairs * 2
            task = dual_diff("negative", f"neg{seed:x}", "PAGE_SIZE", 22, 53) if negative else make_fixture(seed, bool(index % 2))
            base = work / f"evaluation-{seed}"
            root, signal = case_setup(base, task)
            plan = frozen.get(signal)
            blinded_order = list(children)
            # Preassigned alternation independent of the observed signal. Equal representation in each class.
            if (index // 2) % 2:
                blinded_order.reverse()
            arms = {"sequential": (blinded_order, False)}
            if plan:
                arms.update(lattice=(plan["order"], True), same_order_sequential=(plan["order"], False))
            labels = sorted(arms)
            random.Random(seed).shuffle(labels)
            row = {"seed": seed, "signal": signal, "negative": negative, "execution_order": labels, "arms": {}}
            for label in labels:
                order, lattice = arms[label]
                row["arms"][label] = run_sequence(root, task, children, order, base / label, graph_sha, lattice)
            heldout.append(row)
            print(f"seed={seed} negative={negative} " +
                  " ".join(f"{label}={row['arms'][label]['verified']}" for label in labels), flush=True)
    positives = heldout[:-1]
    negative = heldout[-1]
    def passed(row, arm):
        return row["arms"].get(arm, {}).get("verified") is True
    same_order_equivalent = sum(
        passed(row, "lattice") and passed(row, "same_order_sequential")
        and row["arms"]["lattice"]["final_tree"] == row["arms"]["same_order_sequential"]["final_tree"]
        for row in positives)
    summary = {
        "schema": "beast.stage9.learned_lattice.v1",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scope": "Constructed two-family order dependencies, three local processes, no hosted calls requested. "
                 "Held-out parameters and packages, not held-out dependency mechanisms. No promotion or cross-host claim.",
        "arms": {arm: sum(passed(row, arm) for row in positives)
                 for arm in ("lattice", "sequential", "same_order_sequential")},
        "frozen_graph_sha256": graph_sha, "learned_edges": len(frozen),
        "registry_snapshot_sha256": snapshot_hash,
        "components": [{ "id": c.crystal_id, "digest": c.digest, "family": c.task_family }
                       for c in children.values()],
        "training_wall_ms": training_wall_ms,
        "train_seed": args.train_seed, "holdout_seed": args.holdout_seed,
        "training_attempts": len(training), "local_training_processes": len({r["node_pid"] for r in training}),
        "heldout_positives": len(positives), "same_order_identical_verified_trees": same_order_equivalent,
        "negative_verified_arms": [arm for arm in negative["arms"] if passed(negative, arm)],
        "fixture_integrity": all(arm["fixture_unchanged"] for row in heldout for arm in row["arms"].values()),
        "max_stages_per_arm": 2,
    }
    paths = [freeze, report / "training.jsonl", report / "heldout.jsonl", report / "summary.json"]
    for path, rows in zip(paths[1:3], (training, heldout), strict=True):
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    paths[3].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (report / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths))
    print(f"REPORT={report}")
    return 0 if not summary["negative_verified_arms"] and summary["fixture_integrity"] else 1


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "_train":
        train(Path(sys.argv[2]), Path(sys.argv[3]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--component-id", action="append", default=[],
                        help="pin exactly two standalone components by specifying this flag twice")
    parser.add_argument("--train-seed", type=int, default=9013)
    parser.add_argument("--holdout-seed", type=int, default=9239)
    parser.add_argument("--pairs", type=int, default=4, choices=(2, 4, 6), help="cases per dependency shape")
    args = parser.parse_args()
    args.db, args.out = args.db.resolve(), args.out.resolve()
    if args.component_id and len(set(args.component_id)) != 2:
        parser.error("supply two distinct --component-id values")
    if not args.db.is_file():
        parser.error("existing custody registry required")
    if min(args.train_seed, args.holdout_seed) <= 0 or set(range(args.train_seed, args.train_seed + 6)) & set(
        range(args.holdout_seed, args.holdout_seed + args.pairs * 2 + 1)
    ):
        parser.error("supply positive, non-overlapping training and held-out seeds")
    return experiment(args)


if __name__ == "__main__":
    raise SystemExit(main())
