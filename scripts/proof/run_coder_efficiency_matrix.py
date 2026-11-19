"""Paired RepoRelay × deterministic-closeout ablation on bounded synthetic coding tasks."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
from statistics import median
import subprocess
import sys
import time
from typing import Any

from app.context.compression_tiers import repo_map
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES
from app.kernel.agents.tool_runtime import ToolExecutionFailed, local_binding_error, local_binding_identity

REPO = Path(__file__).resolve().parents[2]
PUBLIC = ("python", "-m", "unittest", "-q", "test_public")
ARMS = {
    "direct": (False, False), "reporelay": (True, False),
    "closeout": (False, True), "both": (True, True),
}
TOOLS = frozenset({
    "workspace.index", "workspace.list", "workspace.read_range", "workspace.search_text",
    "worktree.read_file", "worktree.list", "worktree.search_text",
    "worktree.bind", "worktree.replace_exact", "worktree.verify", "worktree.status", "worktree.diff",
})


@dataclass(frozen=True)
class Task:
    module: str
    objective: str
    source: str
    old: str
    new: str
    public: str
    heldout: str

    @property
    def path(self) -> str:
        return self.module + ".py"


TASKS = {
    "shipping": Task(
        "shipping", "Shipping costs 4 units on orders below 50 and is free at 50 or more.",
        "def shipping_fee(total):\n    return 0 if total > 50 else 4\n",
        "total > 50", "total >= 50",
        "assert shipping_fee(50) == 0\nassert shipping_fee(49) == 4",
        "assert [shipping_fee(x) for x in (0, 12, 49.99, 50, 50.01, 120)] == [4, 4, 4, 0, 0, 0]",
    ),
    "normalize": Task(
        "provider_labels", "Normalize provider labels by trimming outer whitespace, lowercasing, and replacing each run of whitespace or hyphens with a single underscore. Keep existing underscores.",
        'import re\n\ndef normalize_provider(label):\n    return label.lower().replace("-", "_")\n',
        'label.lower().replace("-", "_")', 're.sub(r"[\\s-]+", "_", label.strip().lower())',
        'assert normalize_provider(" NVIDIA-NIM ") == "nvidia_nim"',
        'assert normalize_provider(" Open  -\tAI ") == "open_ai"\nassert normalize_provider("a__B") == "a__b"\nassert normalize_provider("  ") == ""',
    ),
    "retry": Task(
        "retry_policy", "Compute exponential retry delay using the provided base and cap. Negative attempts count as attempt zero. Do not change the defaults.",
        "def retry_delay(attempt, base=2, cap=30):\n    return min(cap, base * 2 ** attempt)\n",
        "2 ** attempt", "2 ** max(0, attempt)",
        "assert retry_delay(-1) == 2\nassert retry_delay(6) == 30",
        "assert retry_delay(-8, 3, 9) == 3\nassert retry_delay(1, 3, 9) == 6\nassert retry_delay(4, 3, 9) == 9",
    ),
}


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, obj: Any) -> None:
    with path.open("ab") as out:
        out.write(canonical(obj) + b"\n")
        out.flush()
        os.fsync(out.fileno())


def make_plan(tasks: tuple[str, ...], repeats: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    blocks = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    rng.shuffle(blocks)
    rows = []
    for task, repeat in blocks:
        arms = list(ARMS)
        rng.shuffle(arms)
        for arm in arms:
            hint, close = ARMS[arm]
            rows.append({"task": task, "repeat": repeat, "arm": arm,
                         "reporelay": hint, "closeout": close,
                         "attempt_id": f"{task}-{repeat:02d}-{arm}"})
    return rows


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=15)


def create_fixture(root: Path, task: Task) -> dict[str, str]:
    root.mkdir()
    files = {
        ".gitignore": ".beast/\n__pycache__/\n",
        task.path: task.source,
        "test_public.py": f"import unittest\nfrom {task.module} import *\n\n"
                          "class PublicContract(unittest.TestCase):\n    def test_contract(self):\n"
                          + "".join(f"        {line}\n" for line in task.public.splitlines()),
    }
    for index in range(1, 9):
        files[f"helpers/format_{index:02d}.py"] = f"def format_item_{index}(value):\n    return str(value)\n"
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(source, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=BEAST Benchmark", "-c", "user.email=beast@example.invalid",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture")
    return {name: digest((root / name).read_bytes()) for name in files}


def heldout(root: Path, task: Task) -> dict[str, Any]:
    code = "\n".join([
        "import sys", "sys.path.insert(0, sys.argv[1])", f"from {task.module} import *", task.heldout,
    ])
    start = time.perf_counter()
    try:
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(root)], cwd=root,
                                capture_output=True, timeout=15)
        return {"exit": result.returncode, "stderr_sha256": digest(result.stderr),
                "seconds": round(time.perf_counter() - start, 6)}
    except subprocess.TimeoutExpired:
        return {"exit": 124, "seconds": round(time.perf_counter() - start, 6)}


def changed_paths(root: Path) -> list[str]:
    tracked = git(root, "diff", "--name-only", "HEAD", "-z").split("\0")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted(set(tracked + untracked) - {""})


class FixtureEngine(AgentRunEngine):
    """Scope the experiment to one mutable fixture file and one fixed verifier in all arms."""

    def __init__(self, root: Path, task: Task):
        super().__init__(root)
        self.task = task

    def list_tools(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [tool for tool in super().list_tools(**kwargs) if tool.get("tool_id") in TOOLS]

    async def execute_tool(self, run_id: str, tool_id: str, arguments=None, **kwargs):
        args = arguments or {}
        if tool_id not in TOOLS or kwargs.get("execution_target", "local") != "local":
            raise ValueError("benchmark scope: tool or destination not allowed")
        if tool_id == "worktree.replace_exact" and args.get("path") != self.task.path:
            raise ValueError("benchmark scope: only the fixture implementation file can be edited")
        if tool_id == "worktree.bind":
            if local_binding_identity(self.store.get_run(run_id) or {}):
                raise ValueError("benchmark scope: worktree already bound")
            safe = {"objective", "task_id", "base_ref", "provider", "risk"}
            if set(args) - safe or args.get("base_ref") not in (None, "", "HEAD"):
                raise ValueError("benchmark scope: bind from fixture HEAD")
            # Do not let model-selected labels or providers affect the experiment.
            args = {"objective": self.task.objective, "base_ref": "HEAD", "provider": "local"}
        if tool_id == "worktree.verify" and tuple(args.get("command") or ()) != PUBLIC:
            raise ValueError("benchmark scope: use the fixed public test command exactly")
        return await super().execute_tool(run_id, tool_id, args, **kwargs)


class MeteredProvider:
    def __init__(self, delegate: Any):
        self.delegate = delegate
        self.decisions = 0
        self.prompt_bytes = 0
        self.hint_deliveries = 0
        self.model_seconds = 0.0

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
        self.decisions += 1
        self.prompt_bytes += len(prompt.encode())
        self.hint_deliveries += "[REPORELAY NAVIGATION ONLY]" in prompt
        start = time.perf_counter()
        try:
            return await self.delegate.next_decision(prompt, run=run, turn=turn)
        finally:
            self.model_seconds += time.perf_counter() - start


class MeasuredNIM(NIMPlannerProvider):
    def __init__(self, *, key: str, model: str):
        super().__init__(api_key=key, model=model, base_url="https://integrate.api.nvidia.com/v1",
                         stream=False, max_retries=0, timeout_seconds=45, enable_thinking=False,
                         allow_reasoning_as_action=False)
        self.requests: list[dict[str, Any]] = []

    def _request_json(self, payload):
        record = {"prompt_bytes": len(canonical(payload.get("messages", []))), "http_response_parsed": False}
        self.requests.append(record)
        start = time.perf_counter()
        try:
            result = super()._request_json(payload)
            usage = result.get("usage") or {}
            record.update(http_response_parsed=True, prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"))
            return result
        finally:
            record["seconds"] = round(time.perf_counter() - start, 6)


class Scripted:
    """Control-plane check only. Decisions deliberately do not depend on the hint."""

    def __init__(self, task: Task):
        self.steps = iter([
            ("worktree.bind", {}),
            ("workspace.read_range", {"path": task.path, "start_line": 1, "line_count": 12}),
            ("worktree.replace_exact", {"path": task.path, "old_text": task.old, "new_text": task.new}),
            ("worktree.verify", {"command": list(PUBLIC)}),
        ])

    async def next_decision(self, prompt, *, run, turn):
        step = next(self.steps, None)
        if step is None:
            return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="Public verification passed.")
        return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id=step[0], arguments=step[1])


class ExperimentRuntime(DirectCoderRuntime):
    def __init__(self, *args, hint: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.hint = hint

    def _prompt(self, run, state):
        prompt = super()._prompt(run, state)
        if self.hint:
            prompt += "\n[REPORELAY NAVIGATION ONLY]\n" + self.hint
        return prompt


def worktree_for(engine: FixtureEngine, run: dict[str, Any]) -> Path | None:
    identity = local_binding_identity(run)
    if identity is None or local_binding_error(engine.workspace_root, identity):
        return None
    return Path(identity[0])


def verification_ok(run: dict[str, Any]) -> bool:
    cp = run.get("checkpoint") or {}
    verify = cp.get("verification") or {}
    return bool(verify.get("ok") is True and verify.get("returncode") == 0
                and not verify.get("stale") and tuple(verify.get("command") or ()) == PUBLIC
                and verify.get("mutation_epoch") == cp.get("worktree_mutation_epoch") and cp.get("worktree_mutation_epoch"))


async def attempt(out: Path, row: dict[str, Any], args: argparse.Namespace, key: str) -> dict[str, Any]:
    task = TASKS[row["task"]]
    root = out / "fixtures" / row["attempt_id"]
    anchors = create_fixture(root, task)
    before = heldout(root, task)
    baseline_public = subprocess.run(
        [sys.executable, "-B", *PUBLIC[1:]], cwd=root, capture_output=True, timeout=15,
    ).returncode
    if before["exit"] != 1 or baseline_public != 1:
        raise RuntimeError("fixture must fail both public and independent tests before any agent action")
    engine = FixtureEngine(root, task)
    objective = (task.objective + " Work in one isolated worktree and change only the implementation. "
                 "Verify with the exact argv python -m unittest -q test_public. Do not apply the worktree.")
    run = engine.create_run(session_id="efficiency-matrix", objective=objective,
                            mode="agent", provider=args.provider, model=args.model if args.provider == "nim" else "scripted",
                            request={"autonomy": "autopilot", "execution_target": "local", "launch_strategy": "direct_coder"})
    rid = run["run_id"]
    delegate = MeasuredNIM(key=key, model=args.model) if args.provider == "nim" else Scripted(task)
    provider = MeteredProvider(delegate)
    start = time.perf_counter()
    hint, hint_seconds, fidelity = "", 0.0, False
    if row["reporelay"]:
        t = time.perf_counter()
        result = repo_map(root, focus=re.findall(r"[A-Za-z_]{3,}", task.objective), budget_tokens=320)
        fidelity = result["fidelity"]["passed"] is True
        hint = result["content"] if fidelity else ""
        hint_seconds = time.perf_counter() - t
        engine.emit(rid, "agent.integration.fired" if hint else "agent.integration.skipped", {
            "capability": "compression.reporelay", "fidelity_passed": fidelity,
            "implementation": result["implementation"], "hint_bytes": len(hint.encode()),
        })
    runtime = ExperimentRuntime(engine, provider, hint=hint, max_turns=args.max_turns)
    closed = False
    terminal = {state.value for state in TERMINAL_STATES} | {"paused", "waiting_for_approval"}
    for _ in range(args.max_turns + 1):
        epoch = (run.get("checkpoint") or {}).get("worktree_mutation_epoch") or 0
        run = await runtime.run_one_turn(rid)
        if run["state"] in terminal:
            break
        new_epoch = (run.get("checkpoint") or {}).get("worktree_mutation_epoch") or 0
        if row["closeout"] and new_epoch > epoch:
            wt = worktree_for(engine, run)
            if wt is None or changed_paths(wt) != [task.path]:
                continue
            engine.emit(rid, "agent.efficiency.closeout_started", {"mutation_epoch": new_epoch})
            try:
                await engine.execute_tool(rid, "worktree.verify", {"command": list(PUBLIC)})
            except ToolExecutionFailed:
                # Keep the failed test observation available for a bounded repair turn.
                state = runtime._state(rid)
                verify = (engine.store.get_run(rid).get("checkpoint") or {}).get("verification") or {}
                state.setdefault("observations", []).append({"tool_id": "worktree.verify", "status": "failed",
                    "result": {"returncode": verify.get("returncode"), "stdout": verify.get("stdout_tail"),
                               "stderr": verify.get("stderr_tail")}})
                runtime._save(rid, state)
                run = engine.store.get_run(rid)
                continue
            run = engine.store.get_run(rid)
            if verification_ok(run):
                engine.emit(rid, "agent.coder.completed", {
                    "summary": f"Edited {task.path}; public verification exit 0; left in {wt}.",
                    "deterministic": True,
                })
                engine.store.transition(rid, AgentRunState.COMPLETED)
                run = engine.store.get_run(rid)
                closed = True
                break
    seconds = time.perf_counter() - start
    wt = worktree_for(engine, run)
    independent = heldout(wt, task) if wt else {"exit": None, "seconds": 0}
    paths = changed_paths(wt) if wt else []
    unchanged = not changed_paths(root) and all(digest((root / path).read_bytes()) == sha for path, sha in anchors.items())
    chain = engine.store.verify_chain(rid)
    valid = chain.get("ok") is True and chain.get("head_matches") is True
    events = engine.store.events(rid, limit=10000)
    event_path = out / "events" / f"{row['attempt_id']}.jsonl"
    event_path.write_bytes(b"".join(canonical(e) + b"\n" for e in events))
    observations = [e["payload"].get("observation") or {} for e in events
                    if e["event_type"] in {"agent.tool.completed", "agent.tool.failed"}]
    read_tools = {"workspace.read_range", "worktree.read_file"}
    read_count = sum(observation.get("tool_id") in read_tools for observation in observations)
    first_read = next((i for i, observation in enumerate(observations, 1)
                       if observation.get("tool_id") in read_tools and observation.get("status") == "completed"
                       and (observation.get("result") or {}).get("path") == task.path), None)
    requests = getattr(delegate, "requests", [])
    if args.provider == "nim":
        write_json(out / "provider" / f"{row['attempt_id']}.json", requests)
    token_rows = [r for r in requests if isinstance(r.get("prompt_tokens"), int) and isinstance(r.get("completion_tokens"), int)]
    observed_tokens = len(token_rows)
    return {**row, "run_id": rid, "state": run["state"], "verified": bool(
                run["state"] == "completed" and verification_ok(run) and independent["exit"] == 0
                and paths == [task.path] and unchanged and valid),
            "baseline_independent_exit": before["exit"], "baseline_public_exit": baseline_public,
            "independent_exit": independent["exit"],
            "independent_seconds": independent["seconds"], "public_verification": verification_ok(run),
            "changed_paths": paths, "original_unchanged": unchanged, "event_chain_valid": valid,
            "fixture_files_sha256": anchors, "result_file_sha256": digest((wt / task.path).read_bytes()) if wt else None,
            "events_sha256": digest(event_path.read_bytes()), "deterministic_closeout": closed,
            "repo_hint_delivered": bool(provider.hint_deliveries), "hint_prompt_count": provider.hint_deliveries,
            "repo_hint_fidelity": fidelity, "repo_hint_seconds": round(hint_seconds, 6),
            "decisions": provider.decisions, "provider_attempts": len(requests), "local_model_calls_requested": 0,
            "prompt_tokens_observed": sum(r["prompt_tokens"] for r in token_rows) if token_rows else None,
            "completion_tokens_observed": sum(r["completion_tokens"] for r in token_rows) if token_rows else None,
            "requests_with_usage": observed_tokens, "prompt_bytes": provider.prompt_bytes,
            "model_seconds": round(provider.model_seconds, 6), "wall_seconds": round(seconds, 6),
            "source_read_calls": read_count, "first_target_read_tool_number": first_read,
            "tool_seconds": round(sum(int(o.get("duration_ms") or 0) for o in observations) / 1000, 6),
            "tool_completions": sum(e["event_type"] == "agent.tool.completed" for e in events),
            "tool_failures": sum(e["event_type"] == "agent.tool.failed" for e in events)}


def summarize(rows: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[row["arm"]].append(row)
        blocks[(row["task"], row["repeat"])][row["arm"]] = row
    results = {}
    for name in ARMS:
        arm = grouped[name]
        good = sum(row["verified"] for row in arm)
        calls = sum(row["provider_attempts"] for row in arm) if all("provider_attempts" in row for row in arm) else None
        total_seconds = sum(row["wall_seconds"] for row in arm) if all("wall_seconds" in row for row in arm) else None
        results[name] = {"attempts": len(arm), "verified": good,
                         "verified_rate": good / len(arm) if arm else None,
                         "total_agent_wall_seconds": total_seconds,
                         "agent_seconds_per_verified": total_seconds / good if total_seconds is not None and good else None,
                         "provider_attempts": calls,
                         "provider_attempts_per_verified": calls / good if calls is not None and good else None,
                         "median_wall_seconds": median([row["wall_seconds"] for row in arm if "wall_seconds" in row])
                         if any("wall_seconds" in row for row in arm) else None}
    pairs = [{"task": task, "repeat": repeat, "arm": arm,
              "decision_delta": trial["decisions"] - block["direct"]["decisions"],
              "provider_attempt_delta": trial["provider_attempts"] - block["direct"]["provider_attempts"],
              "verified_delta": int(trial["verified"]) - int(block["direct"]["verified"]),
              "source_read_delta": trial["source_read_calls"] - block["direct"]["source_read_calls"],
              "wall_seconds_delta": round(trial["wall_seconds"] - block["direct"]["wall_seconds"], 6)}
             for (task, repeat), block in blocks.items() if "decisions" in block.get("direct", {})
             for arm, trial in block.items() if arm != "direct" and "decisions" in trial]
    contrasts = []
    for (task, repeat), block in blocks.items():
        if block.keys() != ARMS.keys() or not all("decisions" in trial for trial in block.values()):
            continue
        measures = {}
        for field in ("provider_attempts", "decisions", "source_read_calls", "wall_seconds", "verified"):
            a, r, c, b = (float(block[name][field]) for name in ("direct", "reporelay", "closeout", "both"))
            measures[field] = {
                "reporelay_effect": round(((r - a) + (b - c)) / 2, 6),
                "closeout_effect": round(((c - a) + (b - r)) / 2, 6),
                "interaction": round((b - c) - (r - a), 6),
            }
        contrasts.append({"task": task, "repeat": repeat, "metrics": measures})
    return {"evidence_class": "scripted_control_only" if provider == "scripted" else "live_synthetic_pilot",
            "arms": results, "paired_against_direct": pairs, "factorial_contrasts": contrasts}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tasks", nargs="+", choices=list(TASKS), default=list(TASKS))
    parser.add_argument("--provider", choices=["scripted", "nim"], default="scripted")
    parser.add_argument("--model", default="nvidia/nemotron-3.5-super-vl-120b-a12b")
    parser.add_argument("--seed", type=int, default=4317)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--request-cap", type=int, default=0, help="required live request ceiling")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20 or not 5 <= args.max_turns <= 32:
        parser.error("repeats must be 1–20 and max-turns 5–32")
    if len(set(args.tasks)) != len(args.tasks):
        parser.error("task names must be unique")
    plan = make_plan(tuple(args.tasks), args.repeats, args.seed)
    key = os.environ.get("NVIDIA_API_KEY", "") if args.provider == "nim" else ""
    if args.provider == "nim" and (not key or args.request_cap < len(plan) * args.max_turns):
        parser.error("live mode requires NVIDIA_API_KEY and --request-cap >= planned attempts × max-turns")
    # This is a separate benchmark process. Do not hand model/provider credentials to fixture code.
    previous = dict(os.environ)
    safe_env = {
        name: previous[name] for name in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM",
                                          "SSL_CERT_FILE", "SSL_CERT_DIR", "SYSTEMROOT") if name in previous
    }
    os.environ.clear()
    os.environ.update(safe_env, BEAST_DIRECT_CODER_INTEGRATIONS="0")
    try:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=False)
        for directory in ("fixtures", "events", "provider", "home", "tmp"):
            (out / directory).mkdir()
        os.environ.update(HOME=str(out / "home"), TMPDIR=str(out / "tmp"))
        if args.provider == "nim":
            os.environ["BEAST_NIM_MAX_TOKENS"] = "2048"
        frozen = {"schema": "beast.coder.efficiency.v1", "code_head": git(REPO, "rev-parse", "HEAD").strip(),
                  "provider": args.provider, "model": args.model if args.provider == "nim" else None,
                  "seed": args.seed, "max_turns": args.max_turns, "request_cap": args.request_cap,
                  "public_command": PUBLIC, "plan": plan,
                  "harness_sha256": digest(Path(__file__).read_bytes()), "python": sys.version.split()[0],
                  "reporelay_budget_estimated_tokens": 320, "nim_stream": False, "nim_max_retries": 0,
                  "nim_max_output_tokens": 2048 if args.provider == "nim" else None,
                  "heldout_sha256": {name: digest(TASKS[name].heldout.encode()) for name in args.tasks},
                  "claim_boundary": "Synthetic fixtures, no operating-system network isolation. "
                                    "Scripted mode does not measure model efficacy. Live counts are adapter request attempts."}
        write_json(out / "plan.json", frozen)
        rows = []
        for row in plan:
            try:
                result = asyncio.run(attempt(out, row, args, key))
            except Exception as exc:
                result = {**row, "state": "harness_error", "verified": False, "error_type": type(exc).__name__}
                if args.provider == "scripted":
                    result["error"] = str(exc)[:600]
            append_jsonl(out / "attempts.jsonl", result)
            rows.append(result)
            print(row["attempt_id"], result["state"], "verified=", result["verified"],
                  "attempts=", result.get("provider_attempts"), flush=True)
        summary = summarize(rows, args.provider)
        write_json(out / "summary.json", summary)
        paths = [out / "plan.json", out / "attempts.jsonl", out / "summary.json",
                 *sorted((out / "events").glob("*.jsonl")), *sorted((out / "provider").glob("*.json"))]
        (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in paths))
        print("REPORT:", out)
        return int(any(row["state"] == "harness_error" for row in rows)
                   or (args.provider == "scripted" and not all(row["verified"] for row in rows)))
    finally:
        os.environ.clear()
        os.environ.update(previous)


if __name__ == "__main__":
    raise SystemExit(main())
