"""Local paired semantic-page reuse of BEAST worktree graph context."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import random
import shutil
from statistics import median
import tempfile
import time

from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity
from app.kernel.data_processing.semantic_compute_pages import SemanticComputePageStore, SemanticPageIdentity
from scripts.proof.run_coder_efficiency_matrix import REPO, build_graph_packet, canonical, digest, git, write_json

ARMS = ("rebuild", "reuse_exact", "rebuild_changed", "reuse_stale", "reuse_tampered")
SIZES = (8, 24, 48)
KIND = "intermediate_summary"
CONTRACT = "stage5a:entry-closure-and-selected-limit:v1"


def fixture(root, size, *, changed):
    sources = {
        "entry.py": "from policy import policy\n\ndef entry():\n    return policy()\n",
        "policy.py": f"from {'alternate' if changed else 'limit'} import LIMIT\n\ndef policy():\n    return LIMIT\n",
        "limit.py": "LIMIT = 17\n\ndef marker():\n    return LIMIT\n",
        "alternate.py": "LIMIT = 29\n\ndef marker():\n    return LIMIT\n",
    }
    for i in range(size - len(sources)):
        sources[f"helper_{i:02}.py"] = f"def helper_{i:02}():\n    return {i}\n"
    root.mkdir(parents=True)
    for name, value in sources.items():
        (root / name).write_text(value, encoding="utf-8")
    return sorted(sources)


def identity_for(root, paths):
    # Both arms pay for binding to current source bytes. A page hit does not
    # mean we avoided all filesystem reads.
    hashes = {path: digest((root / path).read_bytes()) for path in paths}
    inf = InferenceArtifactIdentity.from_prompts(
        model="no-model", tokenizer="none", engine="beast-workspace-graph",
        engine_version="stage5a-v1", prompt_prefix="entry.py dependency closure",
        system_prompt=CONTRACT, repository_fingerprint=digest(canonical(hashes)),
        tenant_privacy_class="local_metadata_only",
    )
    return SemanticPageIdentity(inf, "graph_context", "stage5a", KIND,
                                verifier_fingerprint=digest(CONTRACT.encode()),
                                behavior_contract_hash=digest(CONTRACT.encode()))


def rebuild(root, paths):
    with tempfile.TemporaryDirectory(prefix="beast-5a-graph-") as d:
        result = build_graph_packet(root, paths, "graph", Path(d) / "graph.sqlite3")
    return json.loads(result["sent"]), result["navigation"]


def consume(context, root):
    # The selected file comes from the actual context graph, not from the
    # fixture oracle. Only generated benchmark Python is read, never executed.
    edges = {}
    for edge in context["edges"]:
        edges.setdefault(edge["from"], set()).add(edge["to"])
    todo, seen = ["entry.py"], set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        todo.extend(edges.get(path, set()) - seen)
    leaves = sorted(seen - edges.keys())
    if len(leaves) != 1 or leaves[0] not in {"limit.py", "alternate.py"}:
        return {"reachable": sorted(seen), "selected": None, "limit": None}
    selected, = leaves
    tree = ast.parse((root / selected).read_text(encoding="utf-8"))
    limits = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "LIMIT"
              and isinstance(n.value, ast.Constant) and type(n.value.value) is int]
    return {"reachable": sorted(seen), "selected": selected,
            "limit": limits[0] if len(limits) == 1 else None}


def oracle(changed):
    name = "alternate.py" if changed else "limit.py"
    return {"reachable": sorted(["entry.py", "policy.py", name]),
            "selected": name, "limit": 29 if changed else 17}


def run_block(out, *, size, repeat, seed):
    root = out / f"files-{size:02}-pair-{repeat:03}"
    original, changed = root / "original", root / "changed"
    paths = fixture(original, size, changed=False)
    assert paths == fixture(changed, size, changed=True)
    warm_root = root / "warm"
    start = time.perf_counter_ns()
    warm_identity = identity_for(original, paths)
    original_packet, nav = rebuild(original, paths)
    if consume(original_packet, original) != oracle(False):
        raise RuntimeError("cannot seed a page that fails the dependent oracle")
    store = SemanticComputePageStore(warm_root)
    published = store.put_page(warm_identity, original_packet, verifier_refs=[CONTRACT], ttl_seconds=86_400)
    seed_page = published["page"]
    seed_receipt = {"files": size, "repeat": repeat, "elapsed_ms": (time.perf_counter_ns() - start) / 1e6,
                    "source_index_builds": 1, "cold_index_seconds": nav["cold_index_seconds"],
                    "page_id": seed_page["page_id"], "identity_hash": warm_identity.identity_hash,
                    "context_sha256": digest(canonical(original_packet))}
    write_json(root / "preparation.json", seed_receipt)

    arms = list(ARMS)
    random.Random(seed + 1009 * size + repeat).shuffle(arms)
    rows = []
    for arm in arms:
        state_root = root / arm
        state_root.mkdir()
        is_changed = arm in {"rebuild_changed", "reuse_stale"}
        source = changed if is_changed else original
        page_root = state_root / "store"
        if arm.startswith("reuse_"):
            # Stage a separate copy so no treatment sees another arm's receipt
            # updates or intentionally damaged page. Copy time is fixture setup.
            shutil.copytree(warm_root, page_root)
            if arm == "reuse_tampered":
                target = page_root / "pages" / f"{seed_page['page_id']}.json"
                raw = json.loads(target.read_text())
                raw["content"]["edges"] = []
                write_json(target, raw)

        start = time.perf_counter_ns()
        identity = identity_for(source, paths)
        bound = time.perf_counter_ns()
        lookup = None
        if arm.startswith("reuse_"):
            lookup = SemanticComputePageStore(page_root).lookup(identity, record_reuse=True)
        looked = time.perf_counter_ns()
        hit = bool(lookup and lookup["hit"])
        builds = int(not hit)
        context, nav = (lookup["page"]["content"], {}) if hit else rebuild(source, paths)
        result = consume(context, source)
        elapsed_ms = (time.perf_counter_ns() - start) / 1e6
        errors = (lookup or {}).get("validation", {}).get("errors", [])
        receipts = list((page_root / "receipts").glob("*.json"))
        context_hash = digest(canonical(context))
        result_hash = digest(canonical(result))
        result_ok = result == oracle(is_changed)
        receipt_joined = False
        if hit and len(receipts) == 1:
            receipt = json.loads(receipts[0].read_text())
            page = lookup["page"]
            receipt_joined = (receipt.get("verified") is True and receipt.get("reuse_count") == 1
                              and receipt.get("page_id") == page["page_id"]
                              and receipt.get("identity_hash") == identity.identity_hash
                              and receipt.get("content_hash") == page["content_hash"])
        reasons_ok = (
            (arm == "reuse_exact" and hit and receipt_joined)
            or (arm == "reuse_stale" and not hit and lookup["reason"] == "identity_or_kind_miss" and not receipts)
            or (arm == "reuse_tampered" and not hit and "content_hash_mismatch" in errors and not receipts)
            or (arm.startswith("rebuild") and lookup is None and not receipts)
        )
        row = {
            "arm": arm, "files": size, "repeat": repeat, "verified": result_ok and reasons_ok,
            "source_index_builds": builds, "page_hit": hit, "reuse_receipts": len(receipts),
            "reuse_receipt_joined": receipt_joined,
            "lookup_reason": lookup["reason"] if lookup else None, "lookup_errors": errors,
            "elapsed_ms": elapsed_ms, "identity_ms": (bound - start) / 1e6,
            "lookup_ms": (looked - bound) / 1e6 if lookup is not None else None,
            "cold_index_seconds": nav.get("cold_index_seconds"), "identity_hash": identity.identity_hash,
            "context_sha256": context_hash, "context_bytes": len(canonical(context)),
            "result": result, "result_sha256": result_hash,
        }
        write_json(state_root / "context.json", context)
        rows.append(row)
    by_arm = {row["arm"]: row for row in rows}
    for arm, baseline in (("reuse_exact", "rebuild"), ("reuse_tampered", "rebuild"), ("reuse_stale", "rebuild_changed")):
        a, b = by_arm[arm], by_arm[baseline]
        for field in ("identity_hash", "context_sha256", "result_sha256"):
            if a[field] != b[field]:
                a["verified"] = False
                a.setdefault("pair_mismatches", []).append(field)
    return rows, seed_receipt


def summarize(rows, preparations):
    sizes = sorted({r["files"] for r in rows})
    lanes = {}
    for size in sizes:
        arms = {}
        selected = [r for r in rows if r["files"] == size]
        for arm in ARMS:
            trials = [r for r in selected if r["arm"] == arm]
            arms[arm] = {"trials": len(trials), "verified": sum(r["verified"] for r in trials),
                         "source_index_builds": sum(r["source_index_builds"] for r in trials),
                         "median_ms": round(median(r["elapsed_ms"] for r in trials), 3)}
        diffs = {}
        for r in selected:
            diffs.setdefault(r["repeat"], {})[r["arm"]] = r
        deltas = [pair["rebuild"]["elapsed_ms"] - pair["reuse_exact"]["elapsed_ms"] for pair in diffs.values()
                  if pair["rebuild"]["verified"] and pair["reuse_exact"]["verified"]]
        lanes[str(size)] = {
            "arms": arms,
            "median_cold_creation_ms": round(median(r["elapsed_ms"] for r in preparations if r["files"] == size), 3),
            "paired_median_exact_reuse_ms_saved": round(median(deltas), 3) if deltas else None,
        }
    return {"schema": "beast.stage5a.semantic_pages.v1", "trials": len(rows),
            "verified": sum(r["verified"] for r in rows), "provider_requests": 0, "model_calls": 0,
            "preparations": len(preparations), "cold_page_builds": sum(r["source_index_builds"] for r in preparations),
            "exact_index_builds_avoided": sum(
                r["arm"] == "reuse_exact" and r["verified"] and not r["source_index_builds"] for r in rows),
            "by_size": lanes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", choices=SIZES, default=SIZES)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=4327)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20 or len(set(args.sizes)) != len(args.sizes):
        parser.error("expected 1–20 repeats and unique fixture sizes")
    out = args.out.resolve()
    out.mkdir(parents=True)
    write_json(out / "plan.json", {
        "schema": "beast.stage5a.semantic_pages.v1", "code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "seed": args.seed, "sizes": list(args.sizes), "repeats": args.repeats, "arms": ARMS,
        "contract": CONTRACT, "scope": "Local graph context only. Not engine KV or model-work savings. "
        "Includes binding to source bytes and actual reuse receipts. Cold page creation reported separately.",
    })
    rows, preparations = [], []
    with (out / "attempts.jsonl").open("ab") as attempts:
        for size in args.sizes:
            for repeat in range(1, args.repeats + 1):
                block, preparation = run_block(out, size=size, repeat=repeat, seed=args.seed)
                preparations.append(preparation)
                rows.extend(block)
                for row in block:
                    attempts.write(canonical(row) + b"\n")
                    print(f"{size}/{repeat} {row['arm']} hit={row['page_hit']} verified={row['verified']}")
    summary = summarize(rows, preparations)
    write_json(out / "summary.json", summary)
    paths = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in paths))
    print("REPORT:", out)
    return int(summary["verified"] != summary["trials"])


if __name__ == "__main__":
    raise SystemExit(main())
