#!/usr/bin/env python3
"""Render evidence/gauntlet-2026-11-16-large/REPORT.md tables from the JSON receipts (no model calls)."""
from __future__ import annotations

import json
from pathlib import Path

E = Path(__file__).resolve().parents[1] / "evidence" / "gauntlet-2026-11-16-large"


def load(name, default=None):
    p = E / name
    return json.loads(p.read_text()) if p.exists() else default


def md(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def main() -> int:
    s, fam, warm = load("summary.json", {}), load("families.json", []), load("warm.json", [])
    lat, mem, neg = load("lattice_experiment.json", {}), load("memfd_receipts.json", []), load("negative_controls.json", [])
    fu, h2h, retry = load("followup_rename.json"), load("provider_head_to_head.json", {}), load("provider_retry_long_timeout.json")
    bench = (load("specialist_benchmark.json") or {})
    calls = load("model_calls.json", []) + ((fu or {}).get("model_calls") or []) + ((retry or {}).get("model_calls") or [])
    L = ["# Large gauntlet 2026-11-16 — report (generated from receipts)", ""]
    rows = []
    for f in fam + ([fu["family"]] if fu else []):
        tag = " (follow-up)" if fu and f is fu["family"] else ""
        rows.append({"family": f["family"] + tag, "cold solved by": f["cold"]["accepted_by"], "cold calls": f["cold"]["model_calls"],
                     "cold tokens": f["cold"]["tokens_total"], "cold wall ms": round(f["cold"]["wall_ms"]),
                     "crystal": f.get("distilled") or f.get("reason") or (f.get("extraction") or {}).get("refused"),
                     "distil equivalence": (f.get("extraction") or {}).get("equivalence", ""),
                     "held-out": f"{sum(1 for h in f.get('heldout') or [] if h['ok'] and h['independent']['passed'])}/{len(f.get('heldout') or [])}",
                     "promoted": bool(f.get("promotion"))})
    L += ["## Families: cold -> distil -> held-out -> promote", md(rows, list(rows[0]) if rows else []), ""]
    wrows = []
    for r in warm + ((fu or {}).get("warm") or []):
        wrows.append({"task": r["task"], "role": r["role"], "top sim": (r["candidates"] or [{}])[0].get("similarity", 0),
                      "route": r["route"]["route"], "accepted by": r["accepted_by"], "calls": r["model_calls"], "tokens": r["tokens_total"],
                      "wall ms": round(r["wall_ms"]), "visible pass": r["passed"],
                      "hidden pass": (r["independent"] or {}).get("passed"), "FALSE ACCEPT": r["false_accept"]})
    L += ["## Warm / near-miss / decoy / far (D9 router + Governor + verifier; hidden intent test is independent)",
          md(wrows, list(wrows[0]) if wrows else []), ""]
    sel = lat.get("selection") or {}
    rc = lat.get("receipt") or {}
    L += ["## Lattice on a fresh chained workload", f"- fresh tasks (seed {lat.get('seed')}): {lat.get('fresh_tasks')}",
          f"- lattice {sel.get('lattice_id')} selected={sel.get('selected')} used_to_complete={sel.get('used_to_complete')}",
          f"- route: {(sel.get('route_decision') or {}).get('route')} band={(sel.get('route_decision') or {}).get('band')} "
          f"sim={(sel.get('route_decision') or {}).get('similarity')} fingerprint_compatible={(sel.get('route_decision') or {}).get('fingerprint_compatible')}",
          "", md([{"crystal": c["crystal_id"], "family": c["task_family"], "composite": c["composite"], "similarity": c["similarity"],
                   "missing features": ",".join(k for k, v in c["features"].items() if not v)} for c in sel.get("candidates") or []],
                 ["crystal", "family", "composite", "similarity", "missing features"]), ""]
    if rc:
        L += [f"- children (in order): {rc['children']}; A_L = {rc['authority_A_L']}",
              "- per-child capsules: " + "; ".join(f"stage {st['stage']['index']} {st['crystal_id']} ok={st['ok']} bytes={st['capsule']['bytes_total']} "
                                                     f"seals={st['capsule']['seals_value']} pid={st['process']['child_pid']} "
                                                     f"net={st['network']['inet_sockets']}/{st['network']['connects']}/{st['network']['dns_lookups']}/{st['network']['http_sends']} "
                                                     f"child_ms={st['process']['child_wall_ms']}" for st in rc["per_child_replay"]),
              f"- independent verification: {rc['independent_verification']}",
              f"- cold baseline (same fresh task): {rc['cold_baseline_same_task']}",
              f"- avoided vs Nemotron cold: {rc['avoided_vs_nemotron_cold']}",
              f"- V_L (PGEC eq.6): {rc['v_l_pgec_eq6']['v_k']}  children V_Ci: {[c['recurrence_value']['v_k'] for c in rc['children_v_ci']]}",
              f"- composition premium: {rc['composition_premium']}", ""]
    L += ["### Lattice negative controls", md(lat.get("negative_controls") or [], ["task", "expect", "route", "lattice_selected", "accepted_by", "passed", "false_accept", "model_calls"]), ""]
    mrows = [{"family": m["family"], "crystal": m["crystal_id"], "ok": m["ok"], "bytes": m["capsule"]["bytes_total"], "seals": m["capsule"]["seals_value"],
              "child ms": m["process"]["child_wall_ms"], "net (sock/conn/dns/http)": "/".join(str((m.get("network") or {}).get(k)) for k in ("inet_sockets", "connects", "dns_lookups", "http_sends")),
              "calls avoided": (m.get("computation_saved") or {}).get("model_calls_avoided"), "tokens avoided": (m.get("computation_saved") or {}).get("tokens_avoided"),
              "V_K": (m.get("pgec_eq6") or {}).get("v_k"), "shadow credit": m["shadow_credit"]["units"], "refused": m.get("refused", "")}
             for m in mem + ([fu["memfd"]] if fu and fu.get("memfd") else [])]
    L += ["## Sealed memfd capsule replay per promoted crystal", md(mrows, list(mrows[0]) if mrows else []), ""]
    L += ["## Capsule negative controls", md(neg + ((fu or {}).get("negative_controls") or []), ["control", "accepted", "refused", "replay_ran"]), ""]
    hrows = []
    for task_rows in [h2h] + ([retry["rows"]] if retry else []):
        for task, provs in task_rows.items():
            for p, r in provs.items():
                st = [c.get("status") for c in r["calls"]]
                hrows.append({"task": task, "provider": p, "model": r["model"], "passed": r["passed"], "tokens": r["tokens_total"],
                              "reasoning tokens": r.get("reasoning_tokens"), "latency ms": r["latency_ms"], "call status": st})
    L += ["## Provider head-to-head cold baselines", md(hrows, list(hrows[0]) if hrows else []), ""]
    if bench:
        L += ["## Specialist crux fix: before vs after", md([{"model|config": k, **v} for k, v in bench["table"].items()],
                                                             ["model|config", "passed", "of", "false_accepts", "tokens", "wall_s"]), ""]
    spend = {}
    for c in calls:
        key = f"{c.get('provider')} {c.get('model')}"
        r = spend.setdefault(key, {"provider/model": key, "calls": 0, "errors/timeouts": 0, "circuit-open (not sent)": 0, "tokens": 0})
        if c.get("status") == "circuit_open":
            r["circuit-open (not sent)"] += 1
            continue
        r["calls"] += 1
        r["errors/timeouts"] += int(bool(c.get("failed")))
        r["tokens"] += int(c.get("tokens_total") or 0)
    L += ["## Model spend (every call in model_calls*.json)", md(list(spend.values()), ["provider/model", "calls", "errors/timeouts", "circuit-open (not sent)", "tokens"]), ""]
    if s:
        L += ["## Rates", "```", json.dumps(s.get("rates"), indent=1), "```"]
    (E / "REPORT.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
