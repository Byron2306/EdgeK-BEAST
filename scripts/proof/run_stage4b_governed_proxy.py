"""Paired governed NIM proxy experiment on synthetic exact-edit fixtures."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import random
from statistics import median
import subprocess
import sys
import tempfile

import httpx

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.governed_client import Candidate, GovernedModelClient, NIM_BASE
from app.kernel.compute.json_stream_gate import schema_valid
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
from scripts.proof.run_coder_efficiency_matrix import TASKS, canonical, digest, write_json, git, REPO

ARMS = ("unconstrained_drain", "constrained_drain", "constrained_gate")
DIALECTS = ("openai_json_schema", "nim_guided_json")
MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
FIELDS = ("path", "old_text", "new_text")
SCHEMA = {"type": "object", "properties": {"edits": {
    "type": "array", "minItems": 1, "maxItems": 1, "items": {
        "type": "object", "properties": {k: {"type": "string"} for k in FIELDS},
        "required": list(FIELDS), "additionalProperties": False,
    },
}}, "required": ["edits"], "additionalProperties": False}


def make_plan(tasks, repeats, seed):
    rng = random.Random(seed)
    blocks = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    rng.shuffle(blocks)
    plan = []
    for task, repeat in blocks:
        provider_seed = rng.randrange(1, 2**31)
        arms = list(ARMS)
        rng.shuffle(arms)
        for arm in arms:
            plan.append({"trial_id": f"{task}-{repeat:02d}-{arm}", "task": task,
                         "repeat": repeat, "arm": arm, "provider_seed": provider_seed})
    return plan


def messages_for(name):
    task = TASKS[name]
    return [
        {"role": "system", "content": "Return a single JSON object with an edits array of exactly one "
                                      "object containing path, old_text, and new_text as strings. "
                                      "Use the smallest exact substring replacement. No Markdown."},
        {"role": "user", "content": f"{task.objective}\nFile {task.path}:\n{task.source}"},
    ]


def expected_edit(task):
    return {"edits": [{"path": task.path, "old_text": task.old, "new_text": task.new}]}


def check_repair(task, proposal):
    # The benchmark is intentionally exact-match. No arbitrary provider text is
    # executed, including in the unconstrained arm. Tests run only trusted fixtures.
    if proposal != expected_edit(task):
        return {"passed": False, "reason": "not_the_canonical_fixture_edit"}
    if task.source.count(task.old) != 1:
        raise RuntimeError("benchmark source anchor must occur exactly once")
    with tempfile.TemporaryDirectory(prefix="beast-stage4b-") as directory:
        root = Path(directory)
        path = root / task.path
        path.write_text(task.source)
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}

        def verifier(assertions):
            code = ("import sys; sys.path.insert(0, sys.argv[1])\n"
                    f"from {task.import_name} import *\n{assertions}")
            return subprocess.run([sys.executable, "-I", "-B", "-c", code, directory],
                                  cwd=root, env=env, capture_output=True, timeout=10).returncode

        before = (verifier(task.public), verifier(task.heldout))
        if before != (1, 1):
            raise RuntimeError("fixture must fail both checks before the known edit")
        path.write_text(task.source.replace(task.old, task.new, 1))
        after = (verifier(task.public), verifier(task.heldout))
        return {"passed": after == (0, 0), "reason": "fixture_behavior",
                "before_returncodes": before, "after_returncodes": after,
                "repaired_sha256": digest(path.read_bytes())}


class ScriptedSSE(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        for text in (json.dumps({"edits": []}), "\n", json.dumps(self.value), "\ntrailing words"):
            yield b"data: " + canonical({"choices": [{"delta": {"content": text}}]}) + b"\n\n"
        yield b'data: {"usage":{"prompt_tokens":24,"completion_tokens":16}}\n\n'
        yield b"data: [DONE]\n\n"


async def run_trial(out, row, *, model, dialect, controls=False, body_observer=None, transport=None):
    task = TASKS[row["task"]]
    arm = row["arm"]
    actual_dialect = "prompt_only" if arm == "unconstrained_drain" else dialect
    if controls:
        def respond(request):
            if body_observer is not None:
                body_observer(json.loads(request.content))
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=ScriptedSSE(expected_edit(task)))
        transport = httpx.MockTransport(respond)
    receipt_path = out / "receipts" / (row["trial_id"] + ".jsonl")
    receipt_path.parent.mkdir(exist_ok=True)
    receipt_path.touch(exist_ok=False)
    log = GovernorReceiptLog(receipt_path)
    candidate = Candidate(provider="nim", kind="nim", model=model, base_url=NIM_BASE,
                          key_env="NVIDIA_API_KEY" if transport is None else "", max_tokens=512,
                          timeout_s=45, ttft_timeout_s=35, stall_timeout_s=15,
                          options={"seed": row["provider_seed"]})
    client = GovernedModelClient(
        [candidate], transport=transport, use_scorecard=False, max_attempts=1, feedback_turns=False,
        fixed_stream_dialect=actual_dialect, drain_stream=arm != "constrained_gate",
        governor=ComputeGovernorSpine(receipts=log, enforce=True),
        scorecard=CapabilityScorecard(out / "scorecards" / (row["trial_id"] + ".json")),
    )
    result = await client.complete(family="stage4b", messages=messages_for(row["task"]), schema=SCHEMA,
                                   verify=lambda proposal: check_repair(task, proposal), run_id=row["trial_id"])
    if len(result.calls) != 1:
        raise RuntimeError("fixed candidate did not produce exactly one outcome")
    call = result.calls[0]
    return {**row, "dialect": actual_dialect, "status": call.status, "verified": result.accepted,
            "json_valid": call.json_valid, "early_stop": call.early_stop, "stop_reason": call.stop_reason,
            "ttft_ms": round(call.ttft_ms, 3), "latency_ms": round(call.latency_ms, 3),
            "verifier": call.verify, "requests": 0, **call.stream_observation,
            "receipt_sha256": digest(receipt_path.read_bytes())}


def summary(plan, rows, live, abort):
    arms = {}
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["task"], row["repeat"]][row["arm"]] = row
    for arm in ARMS:
        attempted = [r for r in rows if r["arm"] == arm and r["status"] != "not_run"]
        attempted_requests = sum(r.get("requests", 0) for r in attempted)
        count_usage = sum(r.get("prompt_tokens") is not None and r.get("completion_tokens") is not None
                          for r in attempted)
        successful_ms = [r["latency_ms"] for r in attempted if r.get("verified")]
        arms[arm] = {
            "planned": sum(r["arm"] == arm for r in plan),
            "attempted": len(attempted), "verified": sum(bool(r.get("verified")) for r in attempted),
            "requests": attempted_requests, "http_2xx": sum(r.get("http_status") == 200 for r in attempted),
            "json_valid": sum(bool(r.get("json_valid")) for r in attempted),
            "strict_documents_seen": sum(bool(r.get("strict_document_valid")) for r in attempted),
            "invalid_candidates": sum(r.get("invalid_candidates", 0) for r in attempted),
            "early_stops": sum(bool(r.get("early_stop")) for r in attempted),
            "done_frames": sum(bool(r.get("done_seen")) for r in attempted),
            "content_bytes": sum(r.get("content_bytes", 0) for r in attempted),
            "sse_line_bytes": sum(r.get("sse_line_bytes", 0) for r in attempted),
            "requests_with_usage": count_usage,
            "prompt_tokens": sum(r["prompt_tokens"] for r in attempted if r.get("prompt_tokens") is not None)
                if count_usage == attempted_requests and attempted_requests else None,
            "completion_tokens": sum(r["completion_tokens"] for r in attempted if r.get("completion_tokens") is not None)
                if count_usage == attempted_requests and attempted_requests else None,
            "median_verified_stream_ms": median(successful_ms) if successful_ms else None,
        }
    contrasts = {}
    for treatment, control in ((ARMS[1], ARMS[0]), (ARMS[2], ARMS[1])):
        contrasts[f"{treatment}_vs_{control}"] = [
            {"task": task, "repeat": repeat,
             "verified_delta": int(block[treatment]["verified"]) - int(block[control]["verified"]),
             "content_bytes_delta": block[treatment]["content_bytes"] - block[control]["content_bytes"],
             "latency_ms_delta": round(block[treatment]["latency_ms"] - block[control]["latency_ms"], 3)}
            for (task, repeat), block in pairs.items()
            if all(block.get(k, {}).get("http_status") == 200 for k in (treatment, control))
        ]
    return {"schema": "beast.stage4b.governed_proxy.v1",
            "evidence_class": "live_synthetic_exact_edit" if live else "mock_sse_control_only",
            "planned": len(plan), "attempted": sum(r["status"] != "not_run" for r in rows),
            "abort": abort, "arms": arms, "paired": contrasts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", choices=("scripted", "nim"), default="scripted")
    parser.add_argument("--dialect", choices=DIALECTS, default=DIALECTS[0])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--tasks", nargs="+", choices=list(TASKS), default=list(TASKS))
    parser.add_argument("--seed", type=int, default=4327)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--request-cap", type=int, default=0)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10 or len(set(args.tasks)) != len(args.tasks):
        parser.error("expected 1–10 repeats and unique tasks")
    if schema_valid({"edits": []}, SCHEMA)[0] or not schema_valid(expected_edit(TASKS["retry"]), SCHEMA)[0]:
        parser.error("full jsonschema is required; the gate's required-keys-only fallback is not comparable")
    plan = make_plan(tuple(args.tasks), args.repeats, args.seed)
    live = args.provider == "nim"
    if live and (not os.environ.get("NVIDIA_API_KEY") or args.request_cap < len(plan)):
        parser.error("live mode requires NVIDIA_API_KEY and --request-cap >= planned trials")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "plan.json", {
        "schema": "beast.stage4b.governed_proxy.v1", "rows": plan,
        "code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "jsonschema_version": importlib.metadata.version("jsonschema"),
        "provider": args.provider, "model": args.model, "endpoint": NIM_BASE,
        "dialect": args.dialect, "schema_sha256": digest(canonical(SCHEMA)),
        "request_cap": args.request_cap, "seed": args.seed, "max_output_tokens": 512,
        "fixture_sha256": {name: digest(canonical(vars(TASKS[name]))) for name in args.tasks},
        "scope": "One candidate and one request per attempt. Synthetic exact edits, no arbitrary execution. "
                 "Mock SSE controls are not live evidence. Client close is not provider cancellation or billing proof.",
    })
    abort = None
    rows = []
    for row in plan:
        try:
            result = ({**row, "status": "not_run", "verified": None} if abort
                      else asyncio.run(run_trial(out, row, model=args.model, dialect=args.dialect,
                                                 controls=not live)))
        except Exception as exc:
            result = {**row, "status": "harness_error", "verified": False, "error_type": type(exc).__name__}
            abort = {"trial_id": row["trial_id"], "reason": "harness_error"}
        if live and result.get("http_status") in (400, 401, 403, 404, 422, 429):
            abort = {"trial_id": row["trial_id"], "reason": "fixed_route_rejected",
                     "http_status": result["http_status"], "dialect": result["dialect"]}
        rows.append(result)
        with (out / "attempts.jsonl").open("ab") as f:
            f.write(canonical(result) + b"\n")
        print(row["trial_id"], result["status"], "verified=", result["verified"], flush=True)
    report = summary(plan, rows, live, abort)
    write_json(out / "summary.json", report)
    payloads = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in payloads))
    print("REPORT:", out, flush=True)
    return 1 if abort or (not live and not all(r["verified"] for r in rows)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
