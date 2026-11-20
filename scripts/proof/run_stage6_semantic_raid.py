"""Resume a bounded synthetic task from a real Semantic RAID context checkpoint."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import shutil
from statistics import median
import subprocess
import sys
import time

from app.kernel.data_processing.context_packet import ContextPacketBuilder
from app.kernel.data_processing.semantic_raid import SemanticRaidStore
from scripts.proof.run_coder_efficiency_matrix import REPO, canonical, digest, git, write_json

ARMS = ("rebuild", "raid_intact", "raid_primary_corrupt", "raid_one_survivor",
        "raid_all_copies_lost", "raid_manifest_lost")
SIZES = (8, 24, 48)
TARGET = "app/settings.py"
CONTRACT = "app/contract.json"
ORIGINAL = "def retry_limit():\n    return 3\n"
FINAL = "def retry_limit():\n    return 7\n"
REFUSALS = {"raid_all_copies_lost": "no_valid_payload_copy",
            "raid_manifest_lost": "checkpoint_not_in_manifest"}
PACKET_KEYS = ("packet_id", "handoff_hash", "task_id", "task_class", "goal",
               "context_budget", "included_evidence", "excluded_evidence",
               "workspace_context", "packet_stats")


def files_for(size):
    return sorted([TARGET, CONTRACT, *(f"app/helper_{i:02d}.py" for i in range(size - 2))])


def create_workspace(root, size):
    (root / "app").mkdir(parents=True)
    for path in files_for(size):
        text = (ORIGINAL if path == TARGET else '{"retry_limit": 7}\n' if path == CONTRACT
                else f"def {Path(path).stem}():\n    return 3\n")
        (root / path).write_text(text, encoding="utf-8")


def build_packet(root, size):
    packet = ContextPacketBuilder().build(
        {"task_id": f"stage6-files-{size}", "task_class": "synthetic_resume",
         "intent": "Set the retry limit as specified in the contract. Context: " + " ".join(files_for(size)),
         "context_budget": {"max_files": size, "max_tokens": 8000}},
        workspace_root=str(root),
    )
    if sorted(row["source"] for row in packet["included_evidence"]) != files_for(size):
        raise RuntimeError("file context builder did not read the complete fixture set")
    return packet


def projected(packet):
    # This is the documented projection store_context_packet persists, not the
    # entire ContextPacket (e.g. privacy summary fields are intentionally absent).
    return {key: packet[key] for key in PACKET_KEYS}


def sha(value):
    return "sha256:" + digest(canonical(value))


def prepare(root, size):
    start = time.perf_counter_ns()
    packet = build_packet(root / "workspace", size)
    built = time.perf_counter_ns()
    store = SemanticRaidStore(root / "raid")
    shard = store.store_context_packet(packet)
    stored = time.perf_counter_ns()
    packet_digest = sha(projected(packet))
    if packet_digest != shard.digest or not store.integrity_report()["ok"]:
        raise RuntimeError("checkpoint binding or RAID preparation failed")
    receipt = {
        "worker_pid": os.getpid(), "shard": shard.to_dict(), "packet_sha256": packet_digest,
        "packet_bytes": len(canonical(projected(packet))),
        "build_ms": (built - start) / 1e6, "persist_ms": (stored - built) / 1e6,
        "store_bytes": sum(p.stat().st_size for p in store.root.rglob("*") if p.is_file()),
        "task_applied_before_interruption": False,
    }
    write_json(root / "checkpoint.json", receipt)
    return receipt


def restore_payload(store, checkpoint):
    shard = checkpoint["shard"]
    manifest = json.loads(store.manifest_path.read_text()) if store.manifest_path.is_file() else {}
    if (manifest.get("shards") or {}).get(shard["shard_id"]) != shard:
        return None, "checkpoint_not_in_manifest", {"repaired_refs": 0, "ok": False}
    report = store.reconstruct()
    if not report["ok"]:
        return None, "no_valid_payload_copy", report
    envelope = json.loads((store.root / shard["primary_ref"]).read_text())
    payload = envelope.get("payload")
    if (envelope.get("digest") != checkpoint["packet_sha256"]
            or sha(payload) != checkpoint["packet_sha256"] or not store.integrity_report()["ok"]):
        return None, "checkpoint_digest_mismatch", report
    return payload, "recovered", report


def apply_task(payload, workspace):
    evidence = {e["source"]: e for e in payload["included_evidence"] if e["kind"] == "file_snippet"}
    target = workspace / TARGET
    def bound_read(path):
        raw = (workspace / path).read_bytes()
        if ("sha256:" + digest(raw) != evidence[path]["content_hash"]
                or raw.decode().rstrip("\n") != evidence[path]["content"]):
            raise RuntimeError(f"{path} no longer matches prepared context")
        return raw

    before = bound_read(TARGET)
    contract = bound_read(CONTRACT)
    limit = json.loads(contract)["retry_limit"]
    if type(limit) is not int or not 0 <= limit <= 100:
        raise RuntimeError("out-of-scope contract value")
    old = "    return 3"
    if before.decode().count(old) != 1:
        raise RuntimeError("non-unique edit anchor")
    target.write_bytes(before.decode().replace(old, f"    return {limit}", 1).encode())


def resume(root, size, arm):
    workspace = root / "workspace"
    checkpoint = json.loads((root / "checkpoint.json").read_text())
    start = time.perf_counter_ns()
    source_reads = 0
    if arm == "rebuild":
        packet = build_packet(workspace, size)
        payload = projected(packet)
        source_reads = len(packet["included_evidence"])
        reason, reconstruction = "rebuilt", {"repaired_refs": 0, "ok": True}
    else:
        payload, reason, reconstruction = restore_payload(SemanticRaidStore(root / "raid"), checkpoint)
    obtained = time.perf_counter_ns()
    if payload is not None:
        if sha(payload) != checkpoint["packet_sha256"]:
            raise RuntimeError("resumed packet is not the checkpointed payload")
        apply_task(payload, workspace)
    finished = time.perf_counter_ns()
    return {"arm": arm, "worker_pid": os.getpid(), "task_resumed": payload is not None,
            "reason": reason, "context_source_reads": source_reads,
            "target_validation_reads": int(payload is not None),
            "contract_validation_reads": int(payload is not None),
            "repaired_refs": reconstruction["repaired_refs"], "reconstruction": reconstruction,
            "packet_sha256": sha(payload) if payload is not None else None,
            "context_ms": (obtained - start) / 1e6, "resume_ms": (finished - start) / 1e6}


def run_worker(role, root, size, arm="rebuild"):
    env = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL") if name in os.environ}
    start = time.perf_counter_ns()
    result = subprocess.run([sys.executable, "-B", "-m", "scripts.proof.run_stage6_semantic_raid",
                             "--worker", role, "--out", str(root.resolve()), "--size", str(size), "--arm", arm],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
    duration = (time.perf_counter_ns() - start) / 1e6
    if result.returncode:
        raise RuntimeError(f"{role} worker failed: {result.stderr[-1000:]}")
    return {**json.loads(result.stdout), "process_wall_ms": duration}


def damage(root, shard, arm):
    refs = [shard["primary_ref"], *shard["mirror_refs"]]
    if arm in {"raid_primary_corrupt", "raid_one_survivor", "raid_all_copies_lost"}:
        primary = root / refs[0]
        raw = json.loads(primary.read_text())
        raw["payload"]["goal"] = "damaged fixture copy"
        write_json(primary, raw)
    if arm in {"raid_one_survivor", "raid_all_copies_lost"}:
        (root / refs[1]).unlink()
    if arm == "raid_all_copies_lost":
        (root / refs[2]).unlink()
    if arm == "raid_manifest_lost":
        (root / "semantic_raid_manifest.json").unlink()


def verify_workspace(workspace, *, should_resume):
    target = (workspace / TARGET).read_text()
    if not should_resume:
        return target == ORIGINAL
    # Independent final behavior check. Only the expected fixed fixture bytes
    # can be compiled. No provider-supplied code is run.
    if target != FINAL:
        return False
    trusted = {}
    exec(compile(target, "<synthetic-stage6>", "exec"), trusted)
    return trusted["retry_limit"]() == 7 and (workspace / CONTRACT).read_text() == '{"retry_limit": 7}\n'


def tree_digest(root):
    return sha({p.relative_to(root).as_posix(): digest(p.read_bytes())
                for p in sorted(root.rglob("*")) if p.is_file()})


def run_block(out, *, size, repeat, seed):
    block = out / f"files-{size:02d}-pair-{repeat:03d}"
    prepared = block / "prepared"
    create_workspace(prepared / "workspace", size)
    preparation = run_worker("prepare", prepared, size)
    if (prepared / "workspace" / TARGET).read_text() != ORIGINAL:
        raise RuntimeError("writer must exit at the pre-mutation checkpoint")
    before = tree_digest(prepared / "workspace")
    arms = list(ARMS)
    random.Random(seed + size * 1009 + repeat).shuffle(arms)
    rows = []
    for arm in arms:
        root = block / arm
        root.mkdir()
        shutil.copytree(prepared / "workspace", root / "workspace")
        shutil.copyfile(prepared / "checkpoint.json", root / "checkpoint.json")
        if arm != "rebuild":
            shutil.copytree(prepared / "raid", root / "raid")
            damage(root / "raid", preparation["shard"], arm)
        row = run_worker("resume", root, size, arm)
        after = tree_digest(root / "workspace")
        should_resume = arm not in REFUSALS
        cols = {"rebuild": 0, "raid_intact": 0, "raid_primary_corrupt": 1, "raid_one_survivor": 2}
        correct = (row["worker_pid"] != preparation["worker_pid"]
                   and row["task_resumed"] == should_resume
                   and verify_workspace(root / "workspace", should_resume=should_resume))
        if should_resume:
            correct &= (row["packet_sha256"] == preparation["packet_sha256"] and row["repaired_refs"] == cols[arm]
                        and row["context_source_reads"] == (size if arm == "rebuild" else 0))
        else:
            correct &= (row["reason"] == REFUSALS[arm] and before == after and row["context_source_reads"] == 0
                        and row["target_validation_reads"] == 0 and row["contract_validation_reads"] == 0
                        and row["repaired_refs"] == 0)
        rows.append({**row, "files": size, "repeat": repeat, "verified": bool(correct),
                     "workspace_unchanged": before == after, "result_sha256": after})
    baseline = next(r for r in rows if r["arm"] == "rebuild")
    for row in rows:
        if row["task_resumed"] and row["result_sha256"] != baseline["result_sha256"]:
            row["verified"] = False
    return rows, {**preparation, "files": size, "repeat": repeat}


def summarize(rows, preparations):
    by_size = {}
    for size in sorted({r["files"] for r in rows}):
        selected = [r for r in rows if r["files"] == size]
        arms = {}
        for arm in ARMS:
            runs = [r for r in selected if r["arm"] == arm]
            arms[arm] = {"verified": sum(r["verified"] for r in runs),
                         "resumed": sum(r["task_resumed"] for r in runs),
                         "context_source_reads": sum(r["context_source_reads"] for r in runs),
                         "repaired_refs": sum(r["repaired_refs"] for r in runs),
                         "median_context_ms": round(median(r["context_ms"] for r in runs), 3),
                         "median_resume_ms": round(median(r["resume_ms"] for r in runs), 3)}
        rebuild_times = {r["repeat"]: r["context_ms"] for r in selected
                         if r["arm"] == "rebuild" and r["verified"]}
        deltas = {}
        for arm in ("raid_intact", "raid_primary_corrupt", "raid_one_survivor"):
            times = [r["context_ms"] - rebuild_times[r["repeat"]] for r in selected
                     if r["arm"] == arm and r["verified"] and r["repeat"] in rebuild_times]
            deltas[arm] = round(median(times), 3) if times else None
        by_size[str(size)] = {"arms": arms,
            "paired_median_context_ms_delta_vs_rebuild": deltas,
            "median_persist_ms": round(median(p["persist_ms"] for p in preparations if p["files"] == size), 3),
            "checkpoint_store_bytes": [p["store_bytes"] for p in preparations if p["files"] == size]}
    return {"schema": "beast.stage6.semantic_raid.v1", "verified": sum(r["verified"] for r in rows),
            "trials": len(rows), "resumed": sum(r["task_resumed"] for r in rows),
            "correct_refusals": sum(r["verified"] and not r["task_resumed"] for r in rows),
            "preparations": len(preparations), "provider_requests": 0, "by_size": by_size}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sizes", type=int, nargs="+", choices=SIZES, default=SIZES)
    p.add_argument("--repeats", type=int, choices=range(1, 21), default=5)
    p.add_argument("--seed", type=int, default=4327)
    p.add_argument("--worker", choices=("prepare", "resume"), help=argparse.SUPPRESS)
    p.add_argument("--arm", choices=ARMS, default="rebuild", help=argparse.SUPPRESS)
    p.add_argument("--size", type=int, choices=SIZES, default=8, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    out = args.out.resolve()
    if args.worker:
        result = prepare(out, args.size) if args.worker == "prepare" else resume(out, args.size, args.arm)
        print(json.dumps(result, sort_keys=True))
        return 0
    if len(set(args.sizes)) != len(args.sizes):
        p.error("fixture sizes must be unique")
    out.mkdir(parents=True)
    write_json(out / "plan.json", {"code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "sizes": list(args.sizes), "repeats": args.repeats, "seed": args.seed, "arms": ARMS,
        "scope": "Writer exits before mutation; fresh workers resume synthetic tasks. "
                 "Three local payload copies. No abrupt crash, disk independence, model resumption, or network."})
    rows, preparations = [], []
    with (out / "attempts.jsonl").open("ab") as attempts:
        for size in args.sizes:
            for repeat in range(1, args.repeats + 1):
                block, preparation = run_block(out, size=size, repeat=repeat, seed=args.seed)
                preparations.append(preparation)
                rows.extend(block)
                for row in block:
                    attempts.write(canonical(row) + b"\n")
                    print(f"{size}/{repeat} {row['arm']} {row['reason']} verified={row['verified']}", flush=True)
    report = summarize(rows, preparations)
    write_json(out / "summary.json", report)
    paths = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in paths))
    print("REPORT:", out)
    return int(report["verified"] != report["trials"])


if __name__ == "__main__":
    raise SystemExit(main())
