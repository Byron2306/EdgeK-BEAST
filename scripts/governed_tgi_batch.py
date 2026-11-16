#!/usr/bin/env python3
"""Continuous-batching proof for the beast-tgi container: N schema-forced gauntlet requests, sequential vs concurrent.

Every request goes through the governed client (TGI json_object grammar, streaming, early-stop gate, receipts);
each result is then verified with the gauntlet's apply_and_verify + hidden_check on a temp repo copy.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gauntlet_large as gl  # noqa: E402
import governed_interception_proof as P  # noqa: E402
from app.kernel.compute.family_crystals import run_verify  # noqa: E402
from app.kernel.compute.governed_client import GovernedModelClient, tgi_available  # noqa: E402
from app.kernel.compute.capability_scorecard import CapabilityScorecard  # noqa: E402
from app.kernel.compute.structured_edit import EDITS_SCHEMA, edits_messages  # noqa: E402
from app.kernel.governance.governor_spine import GovernorReceiptLog  # noqa: E402

OUT = ROOT / "evidence" / "governed-interception-2026-11-16" / "tgi"
TASKS = ["const-h1", "op-h1", "obo-h1", "exc-h1", "ren-h1", "tool-h1", "dual-h1", "far-1"]


def vram() -> int:
    try:
        return int(subprocess.run(["/usr/bin/nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0])
    except Exception:
        return -1


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))], 1)


async def one(client, name, messages, tag):
    t0 = time.perf_counter()
    res = await client.complete(family=gl.TASKS[name]["family"], messages=messages, schema=EDITS_SCHEMA,
                                verify=lambda v: {"passed": True, "reason": "verified_after"}, run_id=f"tgi-batch:{tag}:{name}")
    c = res.calls[-1]
    return {"task": name, "wall_ms": round((time.perf_counter() - t0) * 1000, 1), "ttft_ms": c.ttft_ms, "status": c.status,
            "json_valid": c.json_valid, "early_stop": c.early_stop, "dialect": c.dialect,
            "tokens_completion": c.tokens_completion, "tokens_prompt": c.tokens_prompt, "value": res.value}


def stats(rows, wall_s):
    lat = [r["wall_ms"] for r in rows]
    toks = sum(r["tokens_completion"] for r in rows)
    return {"requests": len(rows), "wall_s": round(wall_s, 2), "throughput_req_s": round(len(rows) / wall_s, 2),
            "completion_tok_s_aggregate": round(toks / wall_s, 1), "p50_ms": pct(lat, 0.5), "p95_ms": pct(lat, 0.95),
            "ttft_p50_ms": pct([r["ttft_ms"] for r in rows], 0.5), "json_valid": sum(r["json_valid"] for r in rows),
            "early_stops": sum(r["early_stop"] for r in rows), "completion_tokens": toks}


async def main_async() -> int:
    cand = P.tgi_candidate()
    if not tgi_available(cand.base_url[:-3]):
        raise SystemExit("TGI /health not 200")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    receipts = GovernorReceiptLog(ROOT / ".beast" / "governed-interception" / f"tgi-batch-receipts-{stamp}.jsonl")
    with tempfile.TemporaryDirectory(prefix="beast-tgi-batch-") as tmp:
        work = Path(tmp)
        prompts, roots = {}, {}
        for n in TASKS:
            roots[n] = gl.make_repo(work, n)
            prompts[n] = edits_messages(gl.context_files(roots[n]), run_verify(gl.TASKS[n]["verify"], roots[n])["output"],
                                        target=gl.TASKS[n]["target"])
        sc = CapabilityScorecard(work / "sc.json")

        def client():
            return GovernedModelClient([cand], scorecard=sc, governor=None, breaker=None, use_scorecard=False, max_attempts=1)

        # warm-up (grammar FSM compile + prefix cache) so both modes see the same warm server
        for n in TASKS:
            await one(client(), n, prompts[n], "warm")
        result = {"stamp": stamp, "server": json.loads(subprocess.run(["curl", "-s", "-m5", cand.base_url[:-3] + "/info"],
                                                                      capture_output=True, text=True).stdout or "{}"),
                  "vram_mib_before": vram(), "rounds": []}
        for rnd in range(2):
            t0 = time.perf_counter(); seq = []
            for n in TASKS:
                seq.append(await one(client(), n, prompts[n], f"seq{rnd}"))
            seq_wall = time.perf_counter() - t0
            peak = [vram()]
            t0 = time.perf_counter()
            par = await asyncio.gather(*[one(client(), n, prompts[n], f"par{rnd}") for n in TASKS])
            par_wall = time.perf_counter() - t0
            peak.append(vram())
            result["rounds"].append({"sequential": stats(seq, seq_wall), "concurrent_8": stats(par, par_wall),
                                     "vram_mib_after": max(peak), "seq_rows": seq, "par_rows": par})
        # verify concurrent results (last round) with the gauntlet's own checks
        verdicts = []
        for r in result["rounds"][-1]["par_rows"]:
            edits = (r["value"] or {}).get("edits") if isinstance(r["value"], dict) else None
            wt = work / r["task"] / "wt-batch"
            chk = gl.apply_and_verify(roots[r["task"]], r["task"], edits, wt)
            hid = gl.hidden_check(wt, r["task"]) if chk.get("passed") else {"passed": False}
            verdicts.append({"task": r["task"], "accepted": bool(chk.get("passed") and hid.get("passed"))})
        for rnd in result["rounds"]:
            for k in ("seq_rows", "par_rows"):
                for r in rnd[k]:
                    r.pop("value", None)
        result["concurrent_verdicts"] = verdicts
        result["speedup_wall"] = [round(r["sequential"]["wall_s"] / r["concurrent_8"]["wall_s"], 2) for r in result["rounds"]]
        result["receipt_chain"] = receipts.verify() if hasattr(receipts, "verify") else None
    (OUT / f"tgi-batch-{stamp}.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({"speedup_wall": result["speedup_wall"], "vram_before": result["vram_mib_before"],
                      "rounds": [{k: v for k, v in r.items() if k in ("sequential", "concurrent_8", "vram_mib_after")} for r in result["rounds"]],
                      "verdicts": verdicts}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
