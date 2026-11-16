#!/usr/bin/env python3
"""Closure step 1: rename + multi-file tasks through the governed path with the deterministic rename tool, then
crystallize (gauntlet registry only) and reuse the crystal on fresh tasks.

  --phase solve        model decides WHAT (constrained action), code.rename_symbol does WHERE; TGI-alone and chain
  --phase crystallize  ren-cold episode -> distil -> held-out ren-h1..h3 -> promote; rename+guard lattice -> held-out
                       refguard-h1..h3 -> promote; fresh seeded tasks solved crystal-first (0 model calls expected)
Evidence: evidence/closure-2026-11-16/01-rename-tool/. Registry: .beast/gauntlets/2026-11-16-closure/ (a copy of this
morning's promoted registry; the main registry is never touched).
"""
from __future__ import annotations

import argparse
import json
import shutil
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

OUT = ROOT / "evidence" / "closure-2026-11-16" / "01-rename-tool"
STATE = ROOT / ".beast" / "gauntlets" / "2026-11-16-closure"
MORNING = ROOT / ".beast" / "gauntlets" / "2026-11-16-large" / "family_crystals.sqlite3"
SOLVE_TASKS = ["ren-h1", "ren-h2", "ren-h3", "ren-w1", "ren-w2", "ren-near", "refguard-h1", "refguard-h2", "refguard-h3",
               "refguard-w1"]


def slim(row: dict) -> dict:
    return {k: row.get(k) for k in ("task", "family", "tool", "accepted", "accepted_by", "model_calls", "wall_s", "spend_usd", "reason")}


def phase_solve(stamp: str, seed: int) -> dict:
    fresh = glt.fresh_lattice2_tasks(seed)
    gl.TASKS.update(fresh)
    tasks = SOLVE_TASKS + sorted(fresh)
    receipts = GovernorReceiptLog(OUT / f"governor-receipts-solve-{stamp}.jsonl")
    governor = ComputeGovernorSpine(receipts=receipts, enforce=True)
    scorecard = CapabilityScorecard(STATE / "capability_scorecard.json")
    breaker = CircuitBreaker(open_after=2, cooldown_s=600)
    rows: dict[str, list] = {"tgi_alone_tool": [], "chain_tool": []}
    with tempfile.TemporaryDirectory(prefix="beast-closure-rename-") as tmp:
        work = Path(tmp)
        tgi = cc.make_client([cc.tgi_candidate()], governor, scorecard, breaker, max_attempts=2)
        chain = cc.make_client(cc.tool_chain(), governor, scorecard, breaker, max_attempts=4)
        for label, client in (("tgi_alone_tool", tgi), ("chain_tool", chain)):
            for name in tasks:
                root = gl.make_repo(work, name, f"{label}-{name}")
                row = cc.governed_solve(client, name, root, root.parent / "g", f"closure-solve:{label}:{name}")
                row.pop("worktree", None)
                rows[label].append(row)
                print(json.dumps({"set": label, **slim(row)}), flush=True)
                (OUT / f"solve-{stamp}.json").write_text(json.dumps(rows, indent=1, default=str))
    summary = {label: {"accepted": sum(r["accepted"] for r in rs), "total": len(rs),
                       "model_calls": sum(r["model_calls"] for r in rs), "spend_usd": round(sum(r["spend_usd"] for r in rs), 6),
                       "by": sorted({r["accepted_by"] for r in rs if r["accepted"]})} for label, rs in rows.items()}
    summary["tasks"] = tasks
    summary["seed"] = seed
    scorecard.save()
    (OUT / f"solve-summary-{stamp}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary), flush=True)
    return summary


def learn_lattice(g: cc.ClosureGauntlet, families: tuple[str, str], heldout: list[str]) -> dict:
    from app.kernel.compute import family_crystals as fc
    from app.kernel.compute.heldout_replay import HeldOutReplayGate

    if not all(f in g.crystal_of for f in families):
        return {"composite": None, "reason": "children_not_promoted", "families": families}
    children = [g.crystal(g.crystal_of[f]) for f in families]
    comp = fc.compose(children, source_run_id="closure-2026-11-16:lattice:refguard")
    g.registry.add_candidate(comp, provenance={"children": [c.crystal_id for c in children]})
    rows = []

    def run_variant(variant: str) -> bool:
        root = gl.make_repo(g.work, variant, f"{variant}-lattice-heldout")
        t = gl.TASKS[variant]
        res = fc.replay_family(comp, {"implementation_target": t["target"], "verify_command": t["verify"]}, root, root.parent / "wt")
        ind = gl.hidden_check(root.parent / "wt", variant) if res["ok"] else {"passed": False}
        rows.append({"task": variant, "ok": res["ok"], "independent": ind, "wall_ms": res.get("wall_ms"), "reason": res.get("reason")})
        return bool(res["ok"] and ind["passed"])

    receipt = HeldOutReplayGate().evaluate(comp.crystal_id, heldout, run_variant, minimum_successes=3,
                                           envelope_digest=comp.source_envelope_digest,
                                           reproduction={"lattice": True, "approved_by": g.approve})
    out = {"composite": comp.crystal_id, "children": list(comp.component_ids), "families": list(families),
           "authority_A_L": list(comp.authority), "heldout": rows, "digest": comp.digest}
    if receipt.promoted and g.approve:
        record = g.registry.promote(comp.crystal_id, receipt, approved_by=g.approve)
        out["promotion"] = {"status": record["status"], "record_digest": record["record_digest"], **record["promotion"]}
        g.crystal_of["lattice-refguard"] = comp.crystal_id
    return out


def phase_crystallize(stamp: str, seed: int, approve: str) -> dict:
    STATE.mkdir(parents=True, exist_ok=True)
    reg = STATE / "family_crystals.sqlite3"
    if not reg.exists():
        shutil.copy2(MORNING, reg)  # copy of this morning's promoted gauntlet registry; original untouched
    scorecard = CapabilityScorecard(STATE / "capability_scorecard.json")
    breaker = CircuitBreaker(open_after=2, cooldown_s=600)
    g = cc.ClosureGauntlet(STATE, OUT, approve, lambda gov: cc.make_client(cc.tool_chain(), gov, scorecard, breaker),
                           receipts=f"governor-receipts-crystallize-{stamp}.jsonl")
    for crystal in g.registry.promoted():
        if not crystal.component_ids:
            g.crystal_of[crystal.task_family] = crystal.crystal_id
    body: dict = {"registry": str(reg.relative_to(ROOT)), "seeded_from": str(MORNING.relative_to(ROOT)),
                  "promoted_before": sorted(g.crystal_of)}
    t0 = time.time()
    body["rename_family"] = _clean(g.learn_family("refactor-rename-symbol"))
    body["refguard_lattice"] = learn_lattice(g, ("refactor-rename-symbol", "fix-unhandled-exception"),
                                             ["refguard-h1", "refguard-h2", "refguard-h3"])
    fresh = glt.fresh_lattice2_tasks(seed)
    gl.TASKS.update(fresh)
    body["fresh_seed"] = seed
    body["fresh"] = [_clean(gl.public(g.solve(n, "fresh"))) for n in sorted(fresh)]
    body["episodes"] = g.episodes
    body["model_calls_total"] = len(gl.METER.calls)
    body["spend_usd"] = round(cc.SPEND["usd"], 6)
    body["governor_chain"] = g.governor.receipts.verify()
    body["wall_s"] = round(time.time() - t0, 2)
    scorecard.save()
    (OUT / f"crystallize-{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
    print(json.dumps({"rename": body["rename_family"].get("distilled"), "promoted": bool(body["rename_family"].get("promotion")),
                      "lattice": body["refguard_lattice"].get("composite"), "lattice_promoted": bool(body["refguard_lattice"].get("promotion")),
                      "fresh": [(f.get("task"), f.get("accepted_by"), f.get("passed"), f.get("false_accept"), f.get("model_calls")) for f in body["fresh"]],
                      "spend_usd": body["spend_usd"]}, default=str), flush=True)
    return body


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["solve", "crystallize"], required=True)
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--approve-by", default="")
    a = ap.parse_args()
    SecretVault().load(override=False)
    import os
    os.environ["BEAST_GOVERNED_INTERCEPTION"] = "1"
    os.environ["BEAST_FAMILY_CRYSTALS"] = "1"
    os.environ["BEAST_CRYSTAL_CAPSULE"] = "1"
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    if a.phase == "solve":
        phase_solve(stamp, a.seed)
    else:
        phase_crystallize(stamp, a.seed + 1, a.approve_by.strip())
    print(json.dumps({"spend_usd": round(cc.SPEND["usd"], 6), "calls": cc.SPEND["calls"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
