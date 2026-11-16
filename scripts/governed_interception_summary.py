#!/usr/bin/env python3
"""Assemble evidence/governed-interception-2026-11-16/summary.json from the live proof artefacts (no model calls)."""
from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gauntlet_large as gl  # noqa: E402
from app.kernel.compute.family_crystals import run_verify  # noqa: E402
from app.kernel.compute.structured_edit import edits_messages  # noqa: E402

EV = ROOT / "evidence" / "governed-interception-2026-11-16"
LIVE = EV / "live"
PRICES = {"openai/gpt-oss-120b:deepinfra": (0.037, 0.17), "moonshotai/Kimi-K2.7-Code:deepinfra": (0.68, 3.4)}


def latest(prefix: str) -> Path:
    return sorted(LIVE.glob(f"{prefix}-*.json"))[-1]


def prompt_tokens(names: set[str]) -> dict[str, int]:
    out = {}
    with tempfile.TemporaryDirectory(prefix="beast-gi-sum-") as tmp:
        for n in names:
            root = gl.make_repo(Path(tmp), n)
            failure = run_verify(gl.TASKS[n]["verify"], root)["output"]
            msgs = edits_messages(gl.context_files(root), failure, target=gl.TASKS[n]["target"])
            out[n] = round(sum(len(m["content"]) for m in msgs) / 3.6)
    return out


def main() -> int:
    routed = json.loads(latest("routed").read_text()); h2h = json.loads(latest("h2h").read_text())
    hard = json.loads(latest("hard").read_text())
    ptok = prompt_tokens({r["task"] for r in routed + h2h + hard})
    calls, transport, spend = [], [], defaultdict(lambda: {"calls": 0, "transport_errors": 0, "circuit_skips": 0, "completion_tokens": 0,
                                            "prompt_tokens_est": 0, "usd_est": 0.0})
    for phase, rows in (("routed", routed), ("h2h", h2h), ("hard", hard)):
        for r in rows:
            for i, c in enumerate(r["calls"]):
                key = f'{c["provider"]}:{c["model"]}'
                s = spend[key]
                if c["status"] == "skipped_circuit_open":
                    s["circuit_skips"] += 1; continue
                s["calls"] += 1
                if c["status"] == "transport_error":
                    s["transport_errors"] += 1; transport.append(c); continue
                pt = c.get("tokens_prompt") or round(ptok[r["task"]] * (1.0 + 0.25 * i))  # later attempts carry feedback turns
                s["completion_tokens"] += c["tokens_completion"]; s["prompt_tokens_est"] += pt
                pin, pout = PRICES.get(c["model"], (0.0, 0.0))
                s["usd_est"] += (pt * pin + c["tokens_completion"] * pout) / 1e6
                calls.append({"phase": phase, **c, "task": r["task"]})
    nontransport = [c for c in calls if c["status"] not in ("transport_error",)]
    base = json.loads((ROOT / "evidence" / "gauntlet-2026-11-16-large" / "summary.json").read_text())
    base_h2h = base["provider_h2h"]
    base_nemo = [v["nemotron"]["tokens_total"] for v in base_h2h.values() if v.get("nemotron", {}).get("passed")]
    summary = {
        "routed": {"tasks": len(routed), "accepted": sum(r["accepted"] for r in routed),
                   "rows": [{k: r[k] for k in ("task", "family", "source_files", "accepted", "accepted_by", "model_calls", "wall_s")} for r in routed]},
        "hard_rerun_with_feedback": {"tasks": len(hard), "accepted": sum(r["accepted"] for r in hard),
                                     "rows": [{k: r[k] for k in ("task", "accepted", "accepted_by", "model_calls", "wall_s")} for r in hard]},
        "h2h": [{"candidate": r["calls"][0]["provider"] + ":" + r["calls"][0]["model"] if r["calls"] else "", "task": r["task"],
                 "status": r["calls"][0]["status"] if r["calls"] else "", "accepted": r["accepted"]} for r in h2h],
        "per_call": {"calls_answered": len(nontransport), "json_valid": sum(bool(c["json_valid"]) for c in nontransport),
                     "early_stops": sum(bool(c["early_stop"]) for c in nontransport),
                     "median_completion_tokens": sorted(c["tokens_completion"] for c in nontransport)[len(nontransport) // 2],
                     "early_stop_headroom_tokens_sum": sum(c.get("budget_headroom_tokens") or 0 for c in nontransport),
                     "transport_errors": len(transport)},
        "spend": {k: {**v, "usd_est": round(v["usd_est"], 5)} for k, v in spend.items()},
        "spend_total_usd_est": round(sum(v["usd_est"] for v in spend.values()), 4),
        "spend_note": ("NIM: free-tier credits, no USD. Ollama: local. HF router: priced per Mtok; completion tokens counted from the "
                       "stream (chars/3.6 estimate), prompt tokens estimated from the rebuilt prompts (+25% per feedback attempt) because "
                       "early stop closes the stream before the usage chunk."),
        "baseline": {"source": "evidence/gauntlet-2026-11-16-large/summary.json",
                     "nemotron_h2h_passed": sum(1 for v in base_h2h.values() if v.get("nemotron", {}).get("passed")), "h2h_families": len(base_h2h),
                     "nemotron_tokens_total_per_pass_median": sorted(base_nemo)[len(base_nemo) // 2] if base_nemo else None,
                     "deepseek_gptoss_passed": sum(1 for v in base_h2h.values() for m in ("deepseek", "gpt-oss") if v.get(m, {}).get("passed")),
                     "rename_solved": bool(base_h2h.get("refactor-rename-symbol", {}).get("nemotron", {}).get("passed")),
                     "crystal_hit_rate": base["rates"]["crystal_hit_rate"], "false_accepts_total": base["rates"]["false_accepts_total"],
                     "spend": base["spend"]},
        "scorecard": json.loads(latest("scorecard").read_text()),
        "receipt_chains": [json.loads(p.read_text()) for p in sorted(LIVE.glob("receipt-chain-*.json"))],
        "lifecycle_demo": json.loads((EV / "lifecycle" / "lifecycle_demo.json").read_text()) if (EV / "lifecycle" / "lifecycle_demo.json").exists() else None,
        "placement": {p.stem: json.loads(p.read_text()) for p in sorted((EV / "placement").glob("placement_results_pass*.json"))},
    }
    (EV / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("routed", "hard_rerun_with_feedback", "per_call", "spend", "spend_total_usd_est")}, indent=1)[:6000])
    print(json.dumps({k: v for k, v in summary["baseline"].items() if k != "spend"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
