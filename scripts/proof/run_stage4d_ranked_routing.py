"""Stage 4D paired fixed-order vs frozen scorecard-ranked NIM routing."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import random
from statistics import median
import time

import httpx

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.governed_client import Candidate, GovernedModelClient, NIM_BASE
from app.kernel.compute.json_stream_gate import schema_valid
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
from scripts.proof.run_coder_efficiency_matrix import REPO, Task, canonical, digest, git, write_json
from scripts.proof.run_stage4b_governed_proxy import MODEL, SCHEMA, check_repair, expected_edit

MODELS = ("nvidia/nemotron-3.5-lightning-30b-a3b", MODEL)
ARMS = ("fixed", "ranked")
FAMILIES = ("shipping", "retry")
DIALECT = "openai_json_schema"
PROTOCOL_REJECTIONS = {400, 401, 403, 404, 422, 429}


def fixture(family, variant):
    if family == "shipping":
        limit, fee = 40 + 7 * variant, 2 + variant
        old, new = f"total > {limit}", f"total >= {limit}"
        return Task(
            "shipping", f"Shipping costs {fee} units below {limit}, and is free at {limit} or more.",
            f"def shipping_fee(total):\n    return 0 if {old} else {fee}\n", old, new,
            f"assert shipping_fee({limit}) == 0\nassert shipping_fee({limit-1}) == {fee}",
            f"assert [shipping_fee(x) for x in (0, {limit-.5}, {limit}, {limit+.5}, 500)] == [{fee}, {fee}, 0, 0, 0]",
        )
    base, cap = 2 + variant, 24 + 3 * variant
    return Task(
        "retry_policy", "Compute exponential retry delay using base and cap. Negative attempts count as "
                        "attempt zero. Preserve the defaults.",
        f"def retry_delay(attempt, base={base}, cap={cap}):\n    return min(cap, base * 2 ** attempt)\n",
        "2 ** attempt", "2 ** max(0, attempt)",
        f"assert retry_delay(-1) == {base}\nassert retry_delay(8) == {cap}",
        "assert retry_delay(-8, 3, 9) == 3\nassert retry_delay(1, 3, 9) == 6\nassert retry_delay(4, 3, 9) == 9",
    )


def split_plan(seed, repeats):
    rng = random.Random(seed)
    def base(family, variant):
        return {"family": family, "variant": variant, "fixture": f"{family}-{variant:02d}",
                "provider_seed": rng.randrange(1, 2**31)}
    train = []
    calibration_blocks = [(family, v) for family in FAMILIES for v in range(2)]
    rng.shuffle(calibration_blocks)
    for family, v in calibration_blocks:
        row = base(family, v)
        slots = list(enumerate(MODELS))
        rng.shuffle(slots)
        train.extend({**row, "model": model, "trial_id": f"cal-{row['fixture']}-{i}"} for i, model in slots)
    evaluation = []
    eval_blocks = [(family, v) for family in FAMILIES for v in range(2, repeats + 2)]
    rng.shuffle(eval_blocks)
    for family, v in eval_blocks:
        row = base(family, v)
        arms = list(ARMS)
        rng.shuffle(arms)
        evaluation.extend({**row, "arm": arm, "trial_id": f"test-{row['fixture']}-{arm}"} for arm in arms)
    return train, evaluation


def messages_for(task):
    return [
        {"role": "system", "content": "Return one JSON object with an edits array containing exactly one "
                                      "object with path, old_text and new_text strings. Use a unique exact "
                                      "substring from the source and replace it. No Markdown."},
        {"role": "user", "content": f"{task.objective}\nFile {task.path}:\n{task.source}"},
    ]


def _mock_response(task, model):
    # Controls intentionally make Lightning fail only retry, with no live implication.
    value = expected_edit(task)
    if model == MODELS[0] and task.module == "retry_policy":
        value["edits"][0]["new_text"] = task.old  # shape-valid no-op
    prompt, completion = (45, 14) if model == MODELS[0] else (45, 19)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
        b"data: " + canonical({"choices": [{"delta": {"content": canonical(value).decode()}}]})
        + b"\n\ndata: " + canonical({"usage": {"prompt_tokens": prompt, "completion_tokens": completion}})
        + b"\n\ndata: [DONE]\n\n"))


class CountedTransport(httpx.AsyncBaseTransport):
    def __init__(self, backend, models, remaining):
        self.backend, self.models, self.remaining = backend, set(models), remaining
        self.requests = []

    async def handle_async_request(self, request):
        model = json.loads(request.content)["model"]
        if (self.remaining[0] <= 0 or model not in self.models
                or any(r["model"] == model for r in self.requests)):
            raise RuntimeError("Stage 4D request budget or candidate invariant violated")
        self.remaining[0] -= 1
        entry = {"model": model, "request_sha256": digest(request.content), "http_status": None}
        self.requests.append(entry)
        response = await self.backend.handle_async_request(request)
        entry["http_status"] = response.status_code
        return response

    async def aclose(self):
        await self.backend.aclose()


async def trial(out, row, *, live, posterior, remaining):
    task = fixture(row["family"], row["variant"])
    models = (row["model"],) if "model" in row else MODELS
    candidates = [
        Candidate("nim", model, "nim", NIM_BASE, key_env="NVIDIA_API_KEY" if live else "",
                  max_tokens=512, timeout_s=45, ttft_timeout_s=35, stall_timeout_s=15,
                  options={"seed": row["provider_seed"]})
        for model in models
    ]
    backend = httpx.AsyncHTTPTransport(retries=0) if live else httpx.MockTransport(
        lambda request: _mock_response(task, json.loads(request.content)["model"]))
    transport = CountedTransport(backend, models, remaining)
    card = CapabilityScorecard(persist=False)
    card.cells = deepcopy(posterior.cells)  # Evaluation cannot update the frozen calibration prior.
    log = out / "receipts" / (row["trial_id"] + ".jsonl")
    log.parent.mkdir(exist_ok=True)
    client = GovernedModelClient(
        candidates, scorecard=card, use_scorecard=row.get("arm") == "ranked",
        governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(log), enforce=True),
        transport=transport, max_attempts=len(candidates), feedback_turns=False,
        fixed_stream_dialect=DIALECT, drain_stream=True,
    )
    started = time.perf_counter()
    result = await client.complete(family=row["family"], messages=messages_for(task), schema=SCHEMA,
                                   verify=lambda action: check_repair(task, action), run_id=row["trial_id"])
    calls = [{"model": c.candidate.model, "status": c.status, "verified": bool(c.verify.get("passed")),
              "json_valid": c.json_valid, "latency_ms": round(c.latency_ms, 3),
              "verifier_reason": c.verify.get("reason"), **c.stream_observation}
             for c in result.calls]
    return {**row, "verified": result.accepted, "wall_ms": round((time.perf_counter() - started) * 1000, 3),
            "status": result.reason, "order": [r["model"] for r in result.ranking],
            "scores": [{"model": r["model"], **r["score"]} for r in result.ranking],
            "requests": transport.requests, "calls": calls}


def aggregate(rows):
    calls = [c for r in rows for c in r.get("calls", []) if c.get("requests") == 1]
    requests = sum(len(r.get("requests", [])) for r in rows)
    used = [c for c in calls if c.get("prompt_tokens") is not None and c.get("completion_tokens") is not None]
    verified = sum(bool(r.get("verified")) for r in rows)
    return {"attempted": len(rows), "verified": verified, "requests": requests,
            "requests_per_verified": round(requests / verified, 3) if verified else None,
            "requests_with_usage": len(used),
            "reported_input_tokens": sum(c["prompt_tokens"] for c in used) if len(used) == requests and requests else None,
            "reported_output_tokens": sum(c["completion_tokens"] for c in used) if len(used) == requests and requests else None,
            "median_wall_ms": median([r["wall_ms"] for r in rows if "wall_ms" in r])
                if any("wall_ms" in r for r in rows) else None}


async def run_matrix(out, *, live, seed, repeats, request_cap):
    train, evaluation = split_plan(seed, repeats)
    planned_cap = len(train) + len(evaluation) * len(MODELS)
    if request_cap < planned_cap:
        raise ValueError("request cap smaller than matrix worst case")
    remaining = [request_cap]
    posterior = CapabilityScorecard(persist=False)
    schema = "beast.stage4d.ranked_routing.v1"
    write_json(out / "plan.json", {
        "schema": schema, "code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "seed": seed, "request_cap": request_cap, "provider": "nim" if live else "scripted",
        "models_fixed_order": MODELS, "endpoint": NIM_BASE, "dialect": DIALECT,
        "calibration": train, "evaluation": evaluation,
        "fixture_sha256": {r["fixture"]: digest(canonical(asdict(fixture(r["family"], r["variant"]))))
                           for r in train + evaluation},
        "scope": "Synthetic fixture variants, not unseen task families. Frozen scorecard at evaluation. "
                 "Same candidates and two-candidate cap, no feedback, reuse, specialists or batching.",
    })
    abort = None
    cal, outcomes = [], []

    def store(name, row):
        with (out / f"{name}.jsonl").open("ab") as handle:
            handle.write(canonical(row) + b"\n")
        print(row["trial_id"], row["status"], "verified=", row.get("verified"), flush=True)

    for row in train + evaluation:
        calibration = "model" in row
        if abort is not None:
            break
        try:
            result = await trial(out, row, live=live, posterior=posterior, remaining=remaining)
        except Exception as exc:
            abort = {"trial_id": row["trial_id"], "reason": "harness_error", "error_type": type(exc).__name__}
            break
        (cal if calibration else outcomes).append(result)
        store("calibration" if calibration else "attempts", result)
        expected_order = [row["model"]] if calibration else list(MODELS)
        request_order = [r["model"] for r in result["requests"]]
        if (set(result["order"]) != set(expected_order)
                or (row.get("arm") != "ranked" and result["order"] != expected_order)
                or not request_order or request_order != result["order"][:len(request_order)]):
            abort = {"trial_id": row["trial_id"], "reason": "route_invariant_failed"}
        for r in result["requests"]:
            if r["http_status"] in PROTOCOL_REJECTIONS:
                abort = {"trial_id": row["trial_id"], "reason": "provider_protocol_rejected",
                         "model": r["model"], "http_status": r["http_status"]}
                break
        if calibration and abort is None:
            call, = result["calls"]
            if any(call.get(k) is None for k in ("prompt_tokens", "completion_tokens")):
                abort = {"trial_id": row["trial_id"], "reason": "calibration_usage_unavailable"}
                continue
            posterior.record(provider="nim", model=row["model"], family=row["family"], passed=call["verified"],
                             json_valid=call["json_valid"], latency_ms=call["latency_ms"],
                             tokens=call["prompt_tokens"] + call["completion_tokens"],
                             failure_kind="" if call["verified"] else call["status"], now=len(cal))
            if len(cal) == len(train):
                write_json(out / "frozen_scorecard.json", {
                    "schema": "beast.capability_scorecard.v1",
                    "cells": {key: asdict(cell) for key, cell in sorted(posterior.cells.items())},
                })
    blocks = defaultdict(dict)
    for r in outcomes:
        blocks[r["fixture"]][r["arm"]] = r
    pairs = []
    for name, block in blocks.items():
        if set(block) != set(ARMS):
            continue
        fixed, ranked = (block[arm] for arm in ARMS)
        pairs.append({"fixture": name, "different_first_choice": fixed["order"][0] != ranked["order"][0],
                      "request_delta_ranked_minus_fixed": len(ranked["requests"]) - len(fixed["requests"]),
                      "verified_delta_ranked_minus_fixed": int(ranked["verified"]) - int(fixed["verified"]),
                      "wall_ms_delta_ranked_minus_fixed": round(ranked["wall_ms"] - fixed["wall_ms"], 3)})
    paired = {k: sum(p[k] for p in pairs) for k in
              ("different_first_choice", "request_delta_ranked_minus_fixed", "verified_delta_ranked_minus_fixed")}
    paired.update(complete_pairs=len(pairs), planned_pairs=len(evaluation) // 2, rows=pairs)
    report = {"schema": schema, "evidence_class": "live_synthetic_frozen_rank" if live else "mock_controls_only",
              "abort": abort, "calibration": {"planned": len(train), **aggregate(cal)},
              "arms": {a: {"planned": len(evaluation) // 2,
                           **aggregate([r for r in outcomes if r["arm"] == a])} for a in ARMS},
              "paired": paired, "total_http_requests": request_cap - remaining[0]}
    write_json(out / "summary.json", report)
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in files))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", choices=("scripted", "nim"), default="scripted")
    parser.add_argument("--seed", type=int, default=4327)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--request-cap", type=int, default=32)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 8 or args.request_cap < 8 + 8 * args.repeats:
        parser.error("expected 1–8 repeats and a cap covering the worst-case requests")
    if schema_valid({"edits": []}, SCHEMA)[0]:
        parser.error("full jsonschema is required")
    live = args.provider == "nim"
    if live and not os.environ.get("NVIDIA_API_KEY"):
        parser.error("live mode requires NVIDIA_API_KEY")
    out = args.out.resolve()
    out.mkdir(parents=True)
    report = asyncio.run(run_matrix(out, live=live, seed=args.seed,
                                    repeats=args.repeats, request_cap=args.request_cap))
    print("REPORT:", out)
    if not live and any(a["verified"] != a["planned"] for a in report["arms"].values()):
        return 1
    return int(report["abort"] is not None)


if __name__ == "__main__":
    raise SystemExit(main())
