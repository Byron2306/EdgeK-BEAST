"""Paired governed NIM proxy experiment on synthetic behavior-verified fixtures."""
from __future__ import annotations

import argparse
import ast
import asyncio
from collections import Counter, defaultdict
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


SAFE_CALLS = {"min", "max", "abs", "int", "float", "str", "len", "round"}
STRING_METHODS = {"strip", "lstrip", "rstrip", "lower", "casefold", "replace", "split", "join"}
NODES = (
    ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If, ast.Assign, ast.Expr,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.IfExp, ast.Call,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Pow, ast.Mod, ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def supported_fixture_source(task, source):
    """Allow simple arithmetic and string repairs, not arbitrary Python programs."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return "invalid_python"
    baseline = ast.parse(task.source)
    base_fn = baseline.body[-1]
    have_re = len(baseline.body) == 2 and ast.unparse(baseline.body[0]) == "import re"
    body = tree.body
    if have_re and body and isinstance(body[0], ast.Import) and ast.unparse(body[0]) == "import re":
        body = body[1:]
    if len(body) != 1 or type(body[0]) is not ast.FunctionDef:
        return "outside_fixture_subset"
    fn = body[0]
    if (fn.name != base_fn.name or ast.dump(fn.args) != ast.dump(base_fn.args)
            or fn.decorator_list or fn.returns or getattr(fn, "type_params", ())):
        return "outside_fixture_subset"
    nodes = list(ast.walk(fn))
    if len(nodes) > 160:
        return "outside_fixture_subset"
    args = {a.arg for a in fn.args.args}
    locals_ = {n.id for n in nodes if type(n) is ast.Name and type(n.ctx) is ast.Store}
    identifiers = args | locals_
    if any(name.startswith("_") for name in identifiers) or locals_ & (SAFE_CALLS | {"re"}):
        return "outside_fixture_subset"
    call_functions = {n.func for n in nodes if type(n) is ast.Call}
    re_receivers = set()
    for c in call_functions:
        if type(c) is ast.Name and c.id in SAFE_CALLS:
            continue
        if type(c) is not ast.Attribute:
            return "outside_fixture_subset"
        if have_re and c.attr == "sub" and type(c.value) is ast.Name and c.value.id == "re":
            re_receivers.add(c.value)
        elif c.attr not in STRING_METHODS:
            return "outside_fixture_subset"
    for node in nodes:
        if node is not fn and type(node) is ast.FunctionDef:
            return "outside_fixture_subset"
        if type(node) is ast.Attribute:
            if node not in call_functions:
                return "outside_fixture_subset"
            continue
        if type(node) not in NODES:
            return "outside_fixture_subset"
        if type(node) is ast.Name and (node.id not in identifiers and node not in call_functions
                                      and node not in re_receivers):
            return "outside_fixture_subset"
        if type(node) is ast.Assign and (len(node.targets) != 1 or type(node.targets[0]) is not ast.Name):
            return "outside_fixture_subset"
        if type(node) is ast.Constant:
            v = node.value
            if not (v is None or type(v) is bool or (type(v) in {int, float} and abs(v) <= 10000)
                    or (type(v) is str and len(v) <= 256)):
                return "outside_fixture_subset"
    return None


def check_repair(task, proposal):
    evidence = {"passed": False, "anchor_valid": False, "behavior_executed": False,
                "canonical_exact_match": proposal == expected_edit(task),
                "proposal_sha256": digest(canonical(proposal))}

    def refused(reason):
        return {**evidence, "reason": reason}

    if not schema_valid(proposal, SCHEMA)[0]:
        return refused("invalid_proposal")
    edits = proposal.get("edits")
    if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
        return refused("invalid_proposal")
    path, old, new = (edits[0].get(key) for key in FIELDS)
    if not all(isinstance(text, str) for text in (path, old, new)):
        return refused("invalid_proposal")
    if path != task.path:
        return refused("disallowed_path")
    if not old:
        return refused("empty_anchor")
    index = task.source.find(old)
    if index < 0:
        return refused("missing_anchor")
    if task.source.find(old, index + 1) >= 0:
        return refused("ambiguous_anchor")
    evidence["anchor_valid"] = True
    if old == new:
        return refused("no_change")
    if len(new) > 4096:
        return refused("outside_fixture_subset")
    patched = task.source[:index] + new + task.source[index + len(old):]
    invalid = supported_fixture_source(task, patched)
    if invalid:
        return refused(invalid)
    with tempfile.TemporaryDirectory(prefix="beast-stage4b-") as directory:
        root = Path(directory)
        fixture = root / task.path
        fixture.write_text(task.source, encoding="utf-8")
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}

        def verifier(assertions):
            code = ("import sys, resource\n"
                    "resource.setrlimit(resource.RLIMIT_CPU, (2, 2))\n"
                    "resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))\n"
                    "resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))\n"
                    "sys.path.insert(0, sys.argv[1])\n"
                    f"from {task.import_name} import *\n{assertions}")
            try:
                return subprocess.run([sys.executable, "-I", "-B", "-c", code, directory],
                                      cwd=root, env=env, capture_output=True, timeout=4).returncode
            except subprocess.TimeoutExpired:
                return 124

        before = (verifier(task.public), verifier(task.heldout))
        if before != (1, 1):
            raise RuntimeError("fixture must fail both checks before applying the proposal")
        fixture.write_text(patched, encoding="utf-8")
        after = (verifier(task.public), verifier(task.heldout))
        return {**evidence, "passed": after == (0, 0), "behavior_executed": True,
                "reason": "fixture_behavior_pass" if after == (0, 0) else "fixture_behavior_failed",
                "before_returncodes": before, "after_returncodes": after,
                "repaired_sha256": digest(fixture.read_bytes())}

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
            whole_file_edit = {"edits": [{"path": task.path, "old_text": task.source,
                                         "new_text": task.source.replace(task.old, task.new, 1)}]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=ScriptedSSE(whole_file_edit))
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
            "anchor_valid": sum(bool(r.get("verifier", {}).get("anchor_valid")) for r in attempted),
            "canonical_exact_matches": sum(bool(r.get("verifier", {}).get("canonical_exact_match")) for r in attempted),
            "behavior_executed": sum(bool(r.get("verifier", {}).get("behavior_executed")) for r in attempted),
            "verifier_reasons": dict(Counter(r["verifier"]["reason"] for r in attempted
                                             if r.get("verifier", {}).get("reason"))),
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
    return {"schema": "beast.stage4b.governed_proxy.v2",
            "evidence_class": "live_synthetic_scoped_behavior" if live else "mock_sse_control_only",
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
        "schema": "beast.stage4b.governed_proxy.v2", "rows": plan,
        "code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "jsonschema_version": importlib.metadata.version("jsonschema"),
        "provider": args.provider, "model": args.model, "endpoint": NIM_BASE,
        "dialect": args.dialect, "schema_sha256": digest(canonical(SCHEMA)),
        "request_cap": args.request_cap, "seed": args.seed, "max_output_tokens": 512,
        "fixture_sha256": {name: digest(canonical(vars(TASKS[name]))) for name in args.tasks},
        "scope": "One candidate and one request per attempt. Synthetic repairs in a bounded Python subset. Separate resource-limited fixture workers, no OS sandbox claim. "
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
