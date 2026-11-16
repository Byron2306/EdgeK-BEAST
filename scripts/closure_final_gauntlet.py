#!/usr/bin/env python3
"""Closure step 7: final gauntlet through the governed path end to end (temp-workspace copies only).

Task sets:
  morning13 = this morning's 13-task set (routed 10 + h2h 3), so the numbers compare with routed 7/10, hard-5 1/5, TGI chain 11/13
  fresh     = unseen seeded harder tasks (fresh_lattice + fresh_lattice2, seed 20261118)
Runs:
  chain   = governed chain only (TGI -> Fireworks GLM -> Fireworks DeepSeek -> HF Kimi; rename tool; verifier; no crystals)
  full    = full governed path: family crystals + lattice capsules first, then the same chain; scorecard + receipts
Registry: .beast/gauntlets/2026-11-16-closure (gauntlet registry only; no promotion in this step). Spend cap via closure_common.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import closure_common as cc
from closure_common import ROOT, gl
import gauntlet_large_tasks as glt

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.governed_client import CircuitBreaker
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
from app.kernel.security.secret_vault import SecretVault

OUT = ROOT / "evidence" / "closure-2026-11-16" / "07-final-gauntlet"
STATE = ROOT / ".beast" / "gauntlets" / "2026-11-16-closure"
MORNING13 = ["const-h1", "op-h1", "obo-h1", "exc-h1", "ren-h1", "ren-h2", "tool-h1", "refguard-h1", "dual-h1", "far-1",
             "const-h2", "refguard-h2", "ren-h3"]
ROUTED10, HARD5 = MORNING13[:10], ["ren-h1", "ren-h2", "ren-h3", "refguard-h1", "refguard-h2"]
SEED = 20261118


def score(rows: list[dict], names: list[str]) -> str:
    by = {r["task"]: r for r in rows}
    return f"{sum(1 for n in names if by.get(n, {}).get('accepted'))}/{len(names)}"


def main() -> int:
    SecretVault().load(override=False)
    os.environ.update(BEAST_GOVERNED_INTERCEPTION="1", BEAST_FAMILY_CRYSTALS="1", BEAST_CRYSTAL_CAPSULE="1", BEAST_GPU_SCHEDULER="1")
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    fresh = {**glt.fresh_lattice_tasks(SEED), **glt.fresh_lattice2_tasks(SEED)}
    gl.TASKS.update(fresh)
    fresh_names = sorted(fresh)
    scorecard = CapabilityScorecard(STATE / "capability_scorecard.json")
    breaker = CircuitBreaker(open_after=2, cooldown_s=600)
    body: dict = {"seed": SEED, "morning13": MORNING13, "fresh": fresh_names, "runs": {}}
    only = set(sys.argv[1:]) or {"chain", "full"}

    if "chain" in only:
        governor = ComputeGovernorSpine(receipts=GovernorReceiptLog(OUT / f"governor-receipts-chain-{stamp}.jsonl"), enforce=True)
        chain = cc.make_client(cc.tool_chain(), governor, scorecard, breaker, max_attempts=4)
        rows = []
        with tempfile.TemporaryDirectory(prefix="beast-closure-final-") as tmp:
            for name in MORNING13 + fresh_names:
                root = gl.make_repo(Path(tmp), name, f"chain-{name}")
                row = cc.governed_solve(chain, name, root, root.parent / "g", f"closure-final:chain:{name}")
                row.pop("worktree", None)
                rows.append(row)
                print(json.dumps({"run": "chain", "task": name, "accepted": row["accepted"], "by": row.get("accepted_by"),
                                  "calls": row["model_calls"], "usd": row["spend_usd"]}), flush=True)
                body["runs"]["chain"] = rows
                (OUT / f"final-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
        body["chain_governor"] = governor.receipts.verify()

    if "full" in only:
        g = cc.ClosureGauntlet(STATE, OUT, "", lambda gov: cc.make_client(cc.tool_chain(), gov, scorecard, breaker),
                               receipts=f"governor-receipts-full-{stamp}.jsonl")
        for crystal in g.registry.promoted():
            if not crystal.component_ids:
                g.crystal_of[crystal.task_family] = crystal.crystal_id
        body["promoted_crystals"] = {f: c for f, c in sorted(g.crystal_of.items())}
        rows = []
        for name in MORNING13 + fresh_names:
            r = gl.public(g.solve(name, "final"))
            r = {k: (str(v) if isinstance(v, Path) else v) for k, v in r.items() if not str(k).startswith("_")}
            r["accepted"] = bool(r.get("passed")) and not r.get("false_accept")
            rows.append(r)
            print(json.dumps({"run": "full", "task": name, "accepted": r["accepted"], "by": r.get("accepted_by"),
                              "route": r.get("route"), "calls": r.get("model_calls"), "fa": r.get("false_accept")}, default=str), flush=True)
            body["runs"]["full"] = rows
            (OUT / f"final-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
        body["full_governor"] = g.governor.receipts.verify()
        body["episodes"] = g.episodes

    summary = {}
    for run, rows in body["runs"].items():
        summary[run] = {"morning13": score(rows, MORNING13), "routed10": score(rows, ROUTED10), "hard5": score(rows, HARD5),
                        "fresh": score(rows, fresh_names), "all": score(rows, MORNING13 + fresh_names),
                        "false_accepts": sum(1 for r in rows if r.get("false_accept")),
                        "model_calls": sum(int(r.get("model_calls") or 0) for r in rows)}
    body["summary"] = summary
    body["spend_usd"] = round(cc.SPEND["usd"], 6)
    body["calls"] = cc.SPEND["calls"]
    scorecard.save()
    (OUT / f"final-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
    (OUT / f"final-summary-{stamp}.json").write_text(json.dumps({"summary": summary, "spend_usd": body["spend_usd"],
                                                                  "calls": body["calls"], "seed": SEED, "fresh": fresh_names}, indent=1))
    print(json.dumps({"summary": summary, "spend_usd": body["spend_usd"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
