#!/usr/bin/env python3
"""Rerun the four ambiguous-anchor failures through the governed chain (temp copies only).

Tasks: exc-h1, far-1, fresh-diff-6852 (seed 20261118), fresh-refguard-6bb5 (seed 20261116).
Spend cap via BEAST_CLOSURE_CAP_USD (default 0.05). Does not touch live services.
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

OUT = ROOT / "evidence" / "closure-2026-11-16" / "08-line-anchor"
TASKS = ["exc-h1", "far-1", "fresh-diff-6852", "fresh-refguard-6bb5"]
BEFORE = {
    "exc-h1": {"accepted": False, "source": "07-final-gauntlet chain",
               "note": "TGI tests_still_failing; GLM, DeepSeek and Kimi all hit edit old_text is not unique in target"},
    "far-1": {"accepted": False, "source": "07-final-gauntlet full",
              "note": "TGI and GLM tests_still_failing; DeepSeek and Kimi hit old_text not unique. Chain run had solved it (DeepSeek); stochastic."},
    "fresh-diff-6852": {"accepted": False, "source": "07-final-gauntlet full",
                        "note": "GLM old_text not unique; others tests_still_failing. Chain run had solved it (DeepSeek)."},
    "fresh-refguard-6bb5": {"accepted": False, "source": "01-rename-tool chain (seed 20261116)",
                            "note": "All four chain members failed; dominant mode was ambiguous exact-replace anchors."},
}


def main() -> int:
    SecretVault().load(override=False)
    os.environ.setdefault("BEAST_CLOSURE_CAP_USD", "0.05")
    cc.CAP_USD = float(os.environ["BEAST_CLOSURE_CAP_USD"])
    cc.SPEND["usd"] = 0.0
    cc.SPEND["calls"] = 0
    os.environ.update(BEAST_GOVERNED_INTERCEPTION="1", BEAST_FAMILY_CRYSTALS="1", BEAST_CRYSTAL_CAPSULE="1",
                      BEAST_GPU_SCHEDULER="1")
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    gl.TASKS.update(glt.fresh_lattice_tasks(20261118))
    gl.TASKS.update(glt.fresh_lattice2_tasks(20261116))
    missing = [n for n in TASKS if n not in gl.TASKS]
    if missing:
        print(json.dumps({"error": "missing_tasks", "missing": missing}), flush=True)
        return 2
    scorecard = CapabilityScorecard(OUT / "capability_scorecard.json")
    breaker = CircuitBreaker(open_after=2, cooldown_s=600)
    receipts = OUT / f"governor-receipts-{stamp}.jsonl"
    governor = ComputeGovernorSpine(receipts=GovernorReceiptLog(receipts), enforce=True)
    client = cc.make_client(cc.tool_chain(), governor, scorecard, breaker, max_attempts=4)
    body: dict = {"stamp": stamp, "cap_usd": cc.CAP_USD, "tasks": TASKS, "before": BEFORE, "rows": []}
    with tempfile.TemporaryDirectory(prefix="beast-line-anchor-") as tmp:
        for name in TASKS:
            root = gl.make_repo(Path(tmp), name, f"line-anchor-{name}")
            row = cc.governed_solve(client, name, root, root.parent / "g", f"closure-line-anchor:{name}")
            row.pop("worktree", None)
            slim = {k: v for k, v in row.items() if k != "ranking"}
            body["rows"].append(slim)
            print(json.dumps({"task": name, "accepted": row.get("accepted"), "by": row.get("accepted_by"),
                              "calls": row.get("model_calls"), "usd": row.get("spend_usd"),
                              "reason": row.get("reason"), "verdicts": row.get("verdicts")}, default=str), flush=True)
            (OUT / f"rerun-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
    body["spend_usd"] = round(cc.SPEND["usd"], 6)
    body["calls"] = cc.SPEND["calls"]
    body["governor"] = governor.receipts.verify()
    body["after"] = {r["task"]: {"accepted": bool(r.get("accepted")), "accepted_by": r.get("accepted_by"),
                                 "model_calls": r.get("model_calls"), "spend_usd": r.get("spend_usd"),
                                 "reason": r.get("reason"), "verdicts": r.get("verdicts")}
                     for r in body["rows"]}
    scorecard.save()
    (OUT / f"rerun-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
    (OUT / f"rerun-summary-{stamp}.json").write_text(json.dumps({
        "spend_usd": body["spend_usd"], "calls": body["calls"], "cap_usd": cc.CAP_USD,
        "accepted": sum(1 for r in body["rows"] if r.get("accepted")),
        "after": body["after"],
    }, indent=1, default=str))
    print(json.dumps({"summary": {"accepted": f"{sum(1 for r in body['rows'] if r.get('accepted'))}/{len(TASKS)}",
                                  "spend_usd": body["spend_usd"], "calls": body["calls"], "cap_usd": cc.CAP_USD}}),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
