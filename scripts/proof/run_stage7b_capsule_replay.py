"""Compare matched pipe and sealed memfd replay using an existing promoted crystal."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sqlite3
from statistics import median
import subprocess
from tempfile import TemporaryDirectory
import time

from app.kernel.compute import crystal_memfd_capsule as cap
from app.kernel.compute.family_crystals import FamilyRegistry, tree_digest
from scripts.gauntlet_large_tasks import constant, constant_decoy
from scripts.proof.run_behemoth_phase2 import install_fixture, verify_independent

DEFAULT_CRYSTAL = "family-crystal:f3f8ad2739d13e5733d13336"


def snapshot(db, target):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(target)) as dest:
            source.backup(dest)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run_trial(arm, case, mode, payload, manifest, worktree, task, root):
    handed = payload
    if mode == "tampered":
        handed = payload[:-1] + bytes([payload[-1] ^ 1])
    t0 = time.perf_counter()
    seal_stats = None
    if arm == "pipe":
        receipt = cap.handoff_to_pipe_replay_child(handed, manifest)
    else:
        fd, seal_stats = cap.seal_capsule(manifest, handed, seal=mode != "unsealed")
        seal_stats["prepare_ms"] = (time.perf_counter() - t0) * 1000
        try:
            receipt = cap.handoff_to_replay_child(fd, manifest, admit_token=f"{case}-{arm}")
        finally:
            os.close(fd)
    wall_ms = (time.perf_counter() - t0) * 1000
    verify_t0 = time.perf_counter()
    independent = verify_independent(worktree, task, True) if worktree.exists() else None
    verify_ms = (time.perf_counter() - verify_t0) * 1000 if independent is not None else None
    verified = bool(receipt.get("ok") and independent and independent["passed"])
    refused = (
        receipt.get("ok") is False and
        ((mode == "near_miss" and not (independent and independent["passed"])) or
         (mode in {"tampered", "unsealed"} and "replay" not in receipt and independent is None and
          ("tampered" if mode == "tampered" else "not sealed") in receipt.get("refused", "")))
    )
    transport = receipt.get("parent_observed", {})
    row = {
        "case": case, "transport": arm, "mode": mode, "verified": verified,
        "check_passed": verified if mode == "positive" else refused,
        "manifest_digest": manifest["manifest_digest"],
        "payload_digest_expected": manifest["payload_sha256"],
        "receiver_capsule": receipt.get("capsule"),
        "receiver_refusal": receipt.get("refused"),
        "receiver_process_id": receipt.get("pid"),
        "receiver_reported_model_calls": (receipt.get("replay") or {}).get("model_calls"),
        "receiver_observed_network": {k: receipt.get("network", {}).get(k) for k in
                                       ("inet_sockets", "connects", "dns_lookups", "http_sends")},
        "receiver_created_worktree": worktree.exists(),
        "receiver_worktree_digest": independent["source_tree_hash"] if independent and
                                    "source_tree_hash" in independent else None,
        "independent_verifier": independent,
        "handoff_and_receiver_wall_ms": wall_ms,
        "independent_verify_wall_ms": verify_ms,
        "receiver_timings_ms": {k: receipt.get(k) for k in
                               ("receive_and_frame_ms", "open_and_verify_frame_ms", "hydrate_ms", "child_wall_ms")},
        "receiver_pipe_bytes_read": receipt.get("pipe_bytes_read"),
        "sender_handoff": transport, "sender_seal": seal_stats,
        "pristine_fixture_unchanged": tree_digest(root) == {path: cap.sha256_bytes(data.encode())
                                                          for path, data in task["files"].items()},
    }
    row["check_passed"] = row["check_passed"] and row["pristine_fixture_unchanged"]
    if mode == "positive":
        row["check_passed"] = (row["check_passed"] and
                               row["receiver_capsule"]["manifest_digest"] == manifest["manifest_digest"] and
                               row["receiver_capsule"]["payload_sha256_child"] == manifest["payload_sha256"])
    return row


def run(args):
    args.out.mkdir(mode=0o700, exist_ok=False)
    os.environ[cap.CAPSULE_ENV] = "1"
    rows, pairs = [], []
    with TemporaryDirectory(prefix="beast-stage7b-capsule-") as temp:
        temp = Path(temp)
        registry = temp / "registry.sqlite3"
        snapshot(args.db, registry)
        db_sha = sha(registry)
        record = FamilyRegistry(registry).get(args.crystal_id)
        candidate = record["crystal_object"]
        if (record["status"] != "promoted" or not (record.get("promotion") or {}).get("approved_by")
                or candidate.task_family != "fix-config-constant" or candidate.component_ids):
            raise ValueError("requires the promoted, standalone fix-config-constant crystal")
        rng = random.Random(args.seed)
        cases = []
        for index in range(args.repeats):
            value = rng.randrange(100, 900)
            cases.append((f"fresh-{index + 1}", "positive", constant(
                "heldout", f"handoffsample{index + 1}", "MAX_BATCH_SIZE", value, value + 13, ("RETRY_DELAY", 8))))
        cases.extend((
            ("behavior-near-miss", "near_miss", constant_decoy("portcontrol")),
            ("tampered", "tampered", cases[0][2]),
            ("unsealed", "unsealed", cases[0][2]),
        ))
        for case, mode, task in cases:
            folder = temp / case
            root = install_fixture(folder / "fixture", task)
            worktree = folder / "worktree"
            payload = cap.build_payload(
                candidate, registry_record_digest=record["record_digest"], promotion=record["promotion"],
                parameters={"implementation_target": task["target"], "verify_command": task["verify"]},
                postcondition={"implementation_target": task["target"], "verify_command": task["verify"],
                               "tests_run": task["tests_run"], "expect_returncode": 0},
                binding={"root": str(root), "worktree": str(worktree)},
            )
            manifest = cap.build_manifest(payload, crystal_id=candidate.crystal_id, crystal_digest=candidate.digest)
            order = ["memfd"] if mode == "unsealed" else ["pipe", "memfd"]
            rng.shuffle(order)
            arms = []
            for arm in order:
                row = run_trial(arm, case, mode, payload, manifest, worktree, task, root)
                arms.append(row)
                rows.append(row)
                if worktree.exists():
                    worktree.rename(folder / f"{arm}-tree")
                print(f"{case} {arm} verified={row['verified']} check_passed={row['check_passed']}", flush=True)
            if mode == "positive":
                same_tree = all(arm["check_passed"] for arm in arms) and len(
                    {arm["receiver_worktree_digest"] for arm in arms}
                ) == 1
                timing_delta = None
                if same_tree:
                    pipe, memfd = (next(arm for arm in arms if arm["transport"] == name)
                                   for name in ("pipe", "memfd"))
                    timing_delta = (memfd["handoff_and_receiver_wall_ms"] + memfd["independent_verify_wall_ms"]
                                    - pipe["handoff_and_receiver_wall_ms"] - pipe["independent_verify_wall_ms"])
                pairs.append({"case": case, "order": order, "verified_equal_final_trees": same_tree,
                              "memfd_minus_pipe_verified_wall_ms": timing_delta})
    passed = sum(row["check_passed"] for row in rows)
    timing_deltas = [pair["memfd_minus_pipe_verified_wall_ms"] for pair in pairs
                     if pair["memfd_minus_pipe_verified_wall_ms"] is not None]
    summary = {
        "schema": "beast.stage7b.capsule_replay.v1",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "kernel_release": platform.release(), "seed": args.seed,
        "crystal_id": candidate.crystal_id, "crystal_digest": candidate.digest,
        "registry_record_digest": record["record_digest"], "registry_snapshot_sha256": db_sha,
        "checks_passed": passed, "checks_planned": len(rows),
        "verified_pairs": sum(pair["verified_equal_final_trees"] for pair in pairs),
        "planned_pairs": len(pairs), "pairs": pairs,
        "median_paired_memfd_minus_pipe_verified_wall_ms": median(timing_deltas) if timing_deltas else None,
        "scope": "Local custody snapshot, synthetic config family, no Commons transfer or cold solve. "
                 "Parent time includes preparation and fresh worker launch. No wire-byte or zero-copy claim.",
    }
    outputs = [args.out / "summary.json", args.out / "attempts.jsonl"]
    outputs[0].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    outputs[1].write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (args.out / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in outputs))
    print(f"REPORT={args.out}")
    return 0 if passed == len(rows) and summary["verified_pairs"] == len(pairs) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="existing promoted registry snapshot")
    parser.add_argument("--crystal-id", default=DEFAULT_CRYSTAL)
    parser.add_argument("--seed", type=int, default=27321)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 11), metavar="1..10")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.db = args.db.resolve()
    args.out = args.out.resolve()
    if not args.db.is_file():
        parser.error("registry snapshot does not exist")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
