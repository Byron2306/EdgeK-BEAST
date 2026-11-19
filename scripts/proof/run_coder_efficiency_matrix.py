"""Paired navigation, diagnostic, and source-context ablations on bounded synthetic coding tasks."""
from __future__ import annotations

import argparse
import ast
import asyncio
from collections import defaultdict
from dataclasses import dataclass, replace
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
from urllib.error import HTTPError

from app.context.compression_tiers import STUB_MARK, _sqz, detect_compressors, long_code_compress, repo_map
from app.kernel.data_processing.cascade_output_compressor import compress_cascade_output, exact_lines
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
DIAGNOSTIC_EXPERIMENT = "diagnostic-compression"
DIAGNOSTIC_ARMS = {"closeout": "none", "rtk": "rtk", "sqz": "sqz"}
SOURCE_EXPERIMENT = "source-compression"
PREBOUND_SOURCE_EXPERIMENT = "source-compression-prebound"
NAV_GRAPH_EXPERIMENT = "worktree-navigation"
NAV_GRAPH_ARMS = ("file_list", "symbols", "graph")
REAL_GRAPH_EXPERIMENT = "real-repo-navigation"
GRAPH_EXPERIMENTS = (NAV_GRAPH_EXPERIMENT, REAL_GRAPH_EXPERIMENT)
SOURCE_EXPERIMENTS = (SOURCE_EXPERIMENT, PREBOUND_SOURCE_EXPERIMENT)
PACKET_EXPERIMENTS = (*SOURCE_EXPERIMENTS, *GRAPH_EXPERIMENTS)
SOURCE_ARMS = ("closeout", "longcodezip")
SOURCE_BUDGET_RATIO = 0.55
EXPERIMENT_ARMS = {"navigation": ARMS, DIAGNOSTIC_EXPERIMENT: DIAGNOSTIC_ARMS,
                   SOURCE_EXPERIMENT: SOURCE_ARMS, PREBOUND_SOURCE_EXPERIMENT: SOURCE_ARMS,
                   NAV_GRAPH_EXPERIMENT: NAV_GRAPH_ARMS, REAL_GRAPH_EXPERIMENT: ("file_list", "graph")}
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
    support: tuple[tuple[str, str], ...] = ()
    provenance: dict[str, Any] | None = None

    @property
    def import_name(self) -> str:
        return self.module.replace("/", ".")

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


def support_source(core: str, domain: str) -> str:
    # Fixture-only nearby utility functions, never executed by the test oracle.
    return core + "\n\n" + "\n\n".join(
        f'def {domain}_{name}(records):\n'
        '    selected = [str(record).strip() for record in records if record is not None]\n'
        '    normalized = [item.casefold() for item in selected if item]\n'
        '    counts = {item: normalized.count(item) for item in normalized}\n'
        '    ordered = sorted(counts, key=lambda item: (-counts[item], item))\n'
        '    return [(item, counts[item]) for item in ordered]\n'
        for name in ("audit_export", "summary_rows", "history_report", "admin_preview",
                     "legacy_snapshot", "bulk_export", "dashboard_rollup", "review_queue")
    )


SOURCE_TASKS = {
    "shipped_tariff": Task(
        "shipping", "Use the regional tariff lookup in shipping_rules for both the free-shipping threshold "
        "and base fee. Free shipping starts at the threshold. Preserve the tariff lookup's handling of unknown regions.",
        "from shipping_rules import tariff_for\n\ndef shipping_fee(total, region):\n"
        "    return 0 if total >= 50 else 4\n",
        "return 0 if total >= 50 else 4",
        "threshold, fee = tariff_for(region)\n    return 0 if total >= threshold else fee",
        "assert shipping_fee(59, 'coast') == 7\nassert shipping_fee(60, 'coast') == 0",
        "assert shipping_fee(69, 'remote') == 9\nassert shipping_fee(70, 'remote') == 0\n"
        "assert shipping_fee(44, 'unknown') == 5\nassert shipping_fee(45, 'unknown') == 0",
        (("shipping_rules.py", support_source(
            "TARIFFS = {'coast': (60, 7), 'remote': (70, 9)}\n\n"
            "def tariff_for(region):\n    return TARIFFS.get(region, (45, 5))\n", "tariff")),),
    ),
    "profile_normalize": Task(
        "provider_labels", "Normalize labels with the profile-specific separator pattern from label_rules. "
        "Trim outer whitespace, lowercase, collapse every separator run to one underscore, and preserve "
        "existing underscores and separators not listed for the selected profile.",
        "import re\nfrom label_rules import separator_pattern\n\ndef normalize_provider(label, profile):\n"
        "    return label.lower().replace('-', '_')\n",
        "label.lower().replace('-', '_')",
        're.sub(separator_pattern(profile), "_", label.strip().lower())',
        "assert normalize_provider('  A--..B  ', 'legacy') == 'a_b'\n"
        "assert normalize_provider('A..B', 'modern') == 'a..b'",
        "assert normalize_provider('A /-B', 'modern') == 'a_b'\n"
        "assert normalize_provider('A/B__C', 'legacy') == 'a/b__c'\n"
        "assert normalize_provider(' A--B ', 'unknown') == 'a_b'",
        (("label_rules.py", support_source(
            "PATTERNS = {'legacy': r'[\\s.\\-]+', 'modern': r'[\\s/\\-]+'}\n\n"
            "def separator_pattern(profile):\n    return PATTERNS.get(profile, r'[\\s\\-]+')\n", "label")),),
    ),
    "channel_retry": Task(
        "retry_policy", "Use the channel-specific attempt index from retry_rules before calculating "
        "exponential backoff. Keep the provided base, cap, and defaults.",
        "from retry_rules import attempt_index\n\ndef retry_delay(attempt, channel, base=2, cap=30):\n"
        "    return min(cap, base * 2 ** attempt)\n",
        "2 ** attempt", "2 ** attempt_index(attempt, channel)",
        "assert retry_delay(1, 'webhook') == 2\nassert retry_delay(1, 'queue') == 4",
        "assert retry_delay(-5, 'queue', 3, 9) == 3\n"
        "assert retry_delay(3, 'webhook', 3, 9) == 9\n"
        "assert retry_delay(2, 'unknown', 3, 30) == 12",
        (("retry_rules.py", support_source(
            "ONE_BASED_CHANNELS = {'webhook', 'email'}\n\n"
            "def attempt_index(attempt, channel):\n"
            "    return max(0, attempt - (1 if channel in ONE_BASED_CHANNELS else 0))\n", "retry")),),
    ),
}


UPSTREAM = {
    "package_name": {
        "repo": "packaging", "url": "https://github.com/pypa/packaging.git",
        "commit": "d8e3b31b734926ebbcaff654279f6855a73e052f",
        "module": "packaging/utils", "upstream_text": 're.compile(r"[-_.]+")',
        "seeded_text": 're.compile(r"[-_]+")',
        "objective": "Restore canonical project-name normalization so periods, underscores and hyphens "
                     "are folded together, including mixed runs. Requirement equality and hashing must agree "
                     "for equivalent names and continue to distinguish different version specifiers.",
        "public": "from packaging.requirements import Requirement\n"
                  "assert canonicalize_name('Sample.Project') == 'sample-project'\n"
                  "assert Requirement('Sample.Project>=1') == Requirement('sample-project>=1')",
        "heldout": "from packaging.requirements import Requirement\n"
                   "assert canonicalize_name('A_..--B') == 'a-b'\n"
                   "assert len({Requirement('OTHER__Pkg>=2'), Requirement('other..pkg>=2')}) == 1\n"
                   "assert Requirement('other..pkg>=2') != Requirement('other-pkg>=3')",
        "licenses": ("LICENSE", "LICENSE.APACHE", "LICENSE.BSD"),
    },
    "compact_unicode": {
        "repo": "itsdangerous", "url": "https://github.com/pallets/itsdangerous.git",
        "commit": "096c8d42545d3b68ea21a4f890fb2b2d8979c0bd",
        "module": "itsdangerous/_json", "upstream_text": 'kwargs.setdefault("ensure_ascii", False)',
        "seeded_text": 'kwargs.setdefault("ensure_ascii", True)',
        "objective": "Restore literal Unicode in the default compact JSON used by the URL-safe serializer. "
                     "Honor an explicit ASCII-only override and preserve compact separators and round-trips.",
        "public": "from itsdangerous import URLSafeSerializer\n"
                  "serializer = URLSafeSerializer('fixture').serializer\n"
                  "assert serializer.dumps({'name': 'café'}) == '{\"name\":\"café\"}'",
        "heldout": "from itsdangerous import URLSafeSerializer\n"
                   "s = URLSafeSerializer('fixture')\n"
                   "data = {'city': '東京', 'count': 2}\n"
                   "assert s.serializer.dumps(data) == '{\"city\":\"東京\",\"count\":2}'\n"
                   "assert s.serializer.dumps(data, ensure_ascii=True).isascii()\n"
                   "assert s.loads(s.dumps(data)) == data",
        "licenses": ("LICENSE.txt",),
    },
}


def load_real_tasks(root: Path) -> dict[str, Task]:
    result = {}
    for name, spec in UPSTREAM.items():
        repo = root / spec["repo"]
        commit = spec["commit"]
        if git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip() != commit:
            raise ValueError(f"missing exact upstream revision for {name}")
        prefix = f"src/{spec['repo']}/"
        package = git(repo, "ls-tree", "-r", "-z", "--name-only", commit, "--", prefix).split("\0")
        tracked_paths = [path for path in package if path and path.endswith(".py")]
        tracked_paths.extend(spec["licenses"])
        files = {}
        # Read pinned blobs, never a working copy or its configuration files.
        for path in sorted(tracked_paths):
            entry = git(repo, "ls-tree", commit, "--", path).split()
            if not entry or entry[0] not in {"100644", "100755"}:
                raise ValueError(f"not a regular pinned source file: {path}")
            files[path.removeprefix("src/")] = git(repo, "show", f"{commit}:{path}")
        pristine = files.pop(spec["module"] + ".py")
        fixed, broken = spec["upstream_text"], spec["seeded_text"]
        if pristine.count(fixed) != 1:
            raise ValueError(f"pinned mutation anchor drifted for {name}")
        provenance = {"url": spec["url"], "commit": commit, "source_scope": prefix,
                      "edit_path": spec["module"] + ".py",
                      "pristine_target_sha256": digest(pristine.encode()),
                      "support_sha256": {p: digest(body.encode()) for p, body in files.items()}}
        result[name] = Task(spec["module"], spec["objective"], pristine.replace(fixed, broken, 1),
                            broken, fixed, spec["public"], spec["heldout"], tuple(files.items()), provenance)
    return result


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


def make_plan(tasks: tuple[str, ...], repeats: int, seed: int, *, experiment: str = "navigation") -> list[dict[str, Any]]:
    rng = random.Random(seed)
    blocks = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    rng.shuffle(blocks)
    rows = []
    for task, repeat in blocks:
        arms = list(EXPERIMENT_ARMS[experiment])
        rng.shuffle(arms)
        for arm in arms:
            diagnostic = experiment == DIAGNOSTIC_EXPERIMENT
            hint, close = ARMS[arm] if experiment == "navigation" else (False, True)
            row = {"task": task, "repeat": repeat, "arm": arm, "reporelay": hint, "closeout": close,
                   "attempt_id": f"{task}-{repeat:02d}-{arm}"}
            if diagnostic:
                row["compression"] = DIAGNOSTIC_ARMS[arm]
            if experiment in PACKET_EXPERIMENTS:
                row["source_packet"] = arm
                if experiment in GRAPH_EXPERIMENTS:
                    row["graph_packet"] = arm
                if experiment != SOURCE_EXPERIMENT:
                    row["prebind"] = True
            rows.append(row)
    return rows


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=15)


def diagnostic_fixture(task: Task) -> Task:
    # Emit real public-verifier output with a near-identical pair among repeated lines.
    noise = "contract runner checkpoint: fixture validation has started"
    public = "\n".join([
        f"for _ in range(15): print({noise!r})",
        f"print('ERROR CONTRACT_CHECK {task.module} alpha-01: diagnostic marker')",
        f"for _ in range(15): print({noise!r})",
        f"print('ERROR CONTRACT_CHECK {task.module} alpha-02: diagnostic marker')",
        task.public,
    ])
    return replace(task, public=public)


def create_fixture(root: Path, task: Task) -> dict[str, str]:
    root.mkdir()
    files = {
        ".gitignore": ".beast/\n__pycache__/\n",
        task.path: task.source,
        "test_public.py": f"import unittest\nfrom {task.import_name} import *\n\n"
                          "class PublicContract(unittest.TestCase):\n    def test_contract(self):\n"
                          + "".join(f"        {line}\n" for line in task.public.splitlines()),
    }
    files.update(task.support)
    if not task.provenance:
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
        "import sys", "sys.path.insert(0, sys.argv[1])", f"from {task.import_name} import *", task.heldout,
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

    def __init__(self, root: Path, task: Task, *, prebind: bool = False):
        super().__init__(root)
        self.task = task
        self.prebind = prebind

    def list_tools(self, **kwargs: Any) -> list[dict[str, Any]]:
        allowed = TOOLS - {"worktree.bind"} if self.prebind else TOOLS
        return [tool for tool in super().list_tools(**kwargs) if tool.get("tool_id") in allowed]

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


def http_rejection(exc: HTTPError, key: str) -> dict[str, Any]:
    """Save bounded, redacted error fields, never request headers or a raw response."""
    def redact(text: str) -> str:
        if key:
            text = text.replace(key, "[REDACTED]")
        text = re.sub(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/._=~-]+",
                      "[REDACTED]", text)
        text = re.sub(r"(?i)\b(?:nvapi-|sk-)[A-Za-z0-9_-]+", "[REDACTED]", text)
        return text

    record: dict[str, Any] = {"status": exc.code}
    try:
        raw = exc.read(8192).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        raw = ""
        record["body_unavailable"] = True
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        body = None
    error = body.get("error", body) if isinstance(body, dict) else None
    if isinstance(error, dict):
        for name in ("code", "type", "param", "message", "detail", "title"):
            value = error.get(name)
            if type(value) in {str, int}:
                clean = " ".join(redact(str(value)).split())
                if clean:
                    record[name] = clean[:384]
    elif isinstance(error, str):
        record["message"] = " ".join(redact(error).split())[:384]
    if len(record) == 1 and raw:
        record["body_sha256"] = digest(redact(raw).encode())
    record["fingerprint"] = digest(canonical(record))
    return record


class MeasuredNIM(NIMPlannerProvider):
    def __init__(self, *, key: str, model: str):
        super().__init__(api_key=key, model=model, base_url="https://integrate.api.nvidia.com/v1",
                         stream=False, max_retries=0, timeout_seconds=45, enable_thinking=False,
                         allow_reasoning_as_action=False)
        self.requests: list[dict[str, Any]] = []

    def _request_json(self, payload):
        messages = payload.get("messages", [])
        user_content = next((m.get("content") for m in reversed(messages)
                             if m.get("role") == "user"), None)
        record = {"prompt_bytes": len(canonical(messages)),
                  "request_body_bytes": len(json.dumps(payload).encode("utf-8")),
                  "http_response_parsed": False,
                  "user_prompt_sha256": digest(user_content.encode()) if isinstance(user_content, str) else None}
        self.requests.append(record)
        start = time.perf_counter()
        try:
            result = super()._request_json(payload)
            usage = result.get("usage") or {}
            record.update(http_response_parsed=True, prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"))
            return result
        except HTTPError as exc:
            record["http_rejection"] = http_rejection(exc, self.api_key)
            raise
        finally:
            record["seconds"] = round(time.perf_counter() - start, 6)


class Scripted:
    """Control-plane check only. Decisions deliberately do not depend on the hint."""

    def __init__(self, task: Task, *, prebind: bool = False):
        self.steps = iter([
            *([] if prebind else [("worktree.bind", {})]),
            ("workspace.read_range", {"path": task.path, "start_line": 1, "line_count": 12}),
            ("worktree.replace_exact", {"path": task.path, "old_text": task.old, "new_text": task.new}),
            ("worktree.verify", {"command": list(PUBLIC)}),
        ])

    async def next_decision(self, prompt, *, run, turn):
        step = next(self.steps, None)
        if step is None:
            return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="Public verification passed.")
        return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id=step[0], arguments=step[1])


def project_diagnostic(raw: str, tier: str, policy: str, detection: dict[str, Any]):
    start = time.perf_counter()
    backend = "raw"
    reason = "pass_through"
    sent = raw
    if raw and tier != "none":
        try:
            status = detection.get(tier, {}) if policy == "upstream" else {}
            if tier == "rtk":
                result = compress_cascade_output(raw, kind="test", allow_binary=policy == "upstream",
                                                 binary_path=status.get("binary_path"))
                fidelity = result.get("safe")
            else:
                result = _sqz(raw, status, "test")
                fidelity = (result.get("fidelity") or {}).get("passed")
            backend = result["backend"]
            candidate = result["content"]
            if fidelity is not True or not set(exact_lines(raw)).issubset(candidate.splitlines()):
                reason = "fidelity_failed"
            elif policy == "upstream" and backend != f"{tier}_binary":
                reason = "upstream_not_applied"
            elif len(candidate.encode()) >= len(raw.encode()):
                reason = "not_smaller"
            else:
                reason, sent = "applied", candidate
        except (OSError, ValueError, KeyError, TypeError):
            reason = "backend_error"
    return sent, {"backend": backend, "reason": reason, "raw_sha256": digest(raw.encode()),
                  "sent_sha256": digest(sent.encode()), "raw_bytes": len(raw.encode()),
                  "sent_bytes": len(sent.encode()), "seconds": round(time.perf_counter() - start, 6)}


def build_source_packet(root: Path, task: Task, *, compress: bool) -> dict[str, Any]:
    """Project only nominated dependency files, never the editable source."""
    raw_rows, sent_rows, receipts = [], [], []
    started = time.perf_counter()
    for path in (task.path, *(name for name, _ in task.support)):
        raw = (root / path).read_bytes().decode("utf-8")
        content, reason, stubbed = raw, "editable_exact" if path == task.path else "raw_control", []
        if compress and path != task.path:
            # Both arms get the same files, in the same order. No pre-supplied answer symbols.
            result = long_code_compress(raw, query=task.objective, budget_ratio=SOURCE_BUDGET_RATIO)
            candidate = result["content"]
            if not result["fidelity"]["passed"]:
                reason = "fidelity_failed"
            elif len(candidate.encode()) >= len(raw.encode()):
                reason = "not_smaller"
            else:
                # Check projection parseability independently before submitting it.
                try:
                    ast.parse(candidate)
                except SyntaxError:
                    reason = "fidelity_failed"
                else:
                    content, reason, stubbed = candidate, "applied", result["stubbed"]
        raw_rows.append({"path": path, "source": raw})
        sent_rows.append({"path": path, "source": content})
        receipts.append({"path": path, "reason": reason, "stubbed": stubbed,
                         "raw_sha256": digest(raw.encode()), "sent_sha256": digest(content.encode()),
                         "raw_bytes": len(raw.encode()), "sent_bytes": len(content.encode())})
    return {"raw": canonical(raw_rows).decode(), "sent": canonical(sent_rows).decode(),
            "files": receipts, "seconds": round(time.perf_counter() - started, 6)}


def build_graph_packet(root: Path, paths: list[str], arm: str, db_path: Path, *,
                       real_repo: bool = False, objective: str = "") -> dict[str, Any]:
    """Use the real BEAST index, not model guesses, for paths, symbols and edges."""
    if arm not in NAV_GRAPH_ARMS:
        raise ValueError("unknown graph arm")
    start = time.perf_counter()
    paths = sorted(set(paths))
    raw = canonical({"files": paths}).decode()
    payload: dict[str, Any] = {"files": paths}
    parser_modes: dict[str, int] = defaultdict(int)
    cold_seconds = warm_seconds = None
    if arm != "file_list":
        from app.kernel.data_processing.workspace_graph import WorkspaceGraph

        if real_repo and db_path.exists():
            raise FileExistsError(db_path)
        index_start = time.perf_counter()
        graph = WorkspaceGraph(str(db_path))
        indexed = graph.index_repository(str(root), max_files=60, include_patterns=["*.py"])
        cold_seconds = round(time.perf_counter() - index_start, 6)
        lookup_start = time.perf_counter()
        index = graph.graph_snapshot(node_limit=500, edge_limit=1000)
        warm_seconds = round(time.perf_counter() - lookup_start, 6)
        if indexed["errors"] or indexed["indexed_files"] != len(paths):
            raise RuntimeError("worktree graph indexed a different file set")
        known = set(paths)
        files = {item["id"]: item["label"] for item in index["nodes"]
                 if item["type"] == "file" and item["label"] in known}
        symbols = []
        for item in index["nodes"]:
            prop = item["properties"]
            if item["type"] != "symbol" or (prop.get("file") or prop.get("path")) not in known:
                continue
            symbols.append({"path": prop.get("file") or prop.get("path"), "name": item["label"], "line": prop["line"],
                            "kind": prop.get("kind", "")})
            parser_modes[prop.get("parser") or "fallback_or_unspecified"] += 1
        if not symbols:
            raise RuntimeError("worktree graph produced no symbols")
        payload["symbols"] = sorted(symbols, key=lambda x: (x["path"], x["line"], x["name"]))
        if arm == "graph":
            pairs = {(files[e["source"]], files[e["target"]]) for e in index["edges"]
                     if e["relation"] == "depends_on" and e["source"] in files and e["target"] in files}
            if not pairs:
                raise RuntimeError("worktree graph produced no local dependency edges")
            payload["edges"] = [{"from": src, "to": dst} for src, dst in sorted(pairs)]
    if real_repo and "symbols" in payload:
        terms = set(re.findall(r"[a-z0-9]+", objective.lower()))
        def relevant(symbol):
            terms_in_symbol = set(re.findall(r"[a-z0-9]+", (symbol["path"] + " " + symbol["name"]).lower()))
            return (-len(terms & terms_in_symbol), symbol["path"], symbol["line"], symbol["name"])
        symbols = sorted(payload["symbols"], key=relevant)
        edges = payload.pop("edges", [])
        payload["symbols"] = []
        payload["edges"] = []
        for edge in edges:
            payload["edges"].append(edge)
            if len(canonical(payload)) > 2400:
                payload["edges"].pop()
                break
        for symbol in symbols:
            payload["symbols"].append(symbol)
            if len(canonical(payload)) > 8000:
                payload["symbols"].pop()
                break
    sent = canonical(payload).decode()
    if len(sent.encode()) > 8000:
        raise RuntimeError("graph packet exceeds the fixed byte ceiling")
    return {"kind": "navigation", "raw": raw, "sent": sent, "files": [],
            "navigation": {"arm": arm, "paths": paths, "symbols": len(payload.get("symbols", [])),
                           "edges": len(payload.get("edges", [])), "parsers": dict(parser_modes),
                           "cold_index_seconds": cold_seconds, "indexed_snapshot_lookup_seconds": warm_seconds},
            "seconds": round(time.perf_counter() - start, 6)}


class ExperimentRuntime(DirectCoderRuntime):
    def __init__(self, *args, hint: str = "", compression: str | None = None,
                 compression_backend: str = "native", detection=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hint = hint
        self.compression = compression
        self.compression_backend = compression_backend
        self.detection = detection or {}
        self.compression_receipts = []
        self.source_packet = None
        self.source_packet_receipt = None

    def _prompt(self, run, state):
        prompt = super()._prompt(run, state)
        if self.compression is not None:
            observations = list(state.get("observations") or [])
            receipts = []
            required = set()
            delivered_fields = []
            for index in range(max(0, len(observations) - 5), len(observations)):
                item = observations[index]
                if item.get("tool_id") != "worktree.verify" or item.get("status") != "failed":
                    continue
                result = dict(item.get("result") or {})
                for field in ("stdout", "stderr"):
                    raw = result.get(field)
                    if not isinstance(raw, str) or not raw:
                        continue
                    sent, receipt = project_diagnostic(raw, self.compression, self.compression_backend,
                                                       self.detection)
                    result[field] = sent
                    receipts.append({"field": field, **receipt})
                    required.update(exact_lines(raw))
                    if sent != raw:
                        delivered_fields.append(json.dumps(sent, ensure_ascii=False))
                observations[index] = {**item, "result": result}
            if receipts:
                rendered = super()._prompt(run, {**state, "observations": observations})
                # Recheck the rendered prompt after the parent runtime's context cap.
                applied = bool(delivered_fields and all(field in rendered for field in delivered_fields)
                               and all(json.dumps(line, ensure_ascii=False)[1:-1] in rendered
                                       for line in required)
                               and len(rendered.encode()) < len(prompt.encode()))
                actual = rendered if applied else prompt
                record = {"tier": self.compression, "attempted_fields": receipts, "applied": applied,
                          "turn": int(state.get("turn") or 0) + 1,
                          "raw_prompt_sha256": digest(prompt.encode()), "sent_prompt_sha256": digest(actual.encode()),
                          "raw_prompt_bytes": len(prompt.encode()), "sent_prompt_bytes": len(actual.encode()),
                          "bytes_saved": len(prompt.encode()) - len(actual.encode())}
                self.compression_receipts.append(record)
                self.engine.emit(run["run_id"], "agent.efficiency.compression_prompt", record)
                prompt = actual
        if self.source_packet is not None and self.source_packet_receipt is None:
            packet = self.source_packet
            header = ("\nBOUND WORKTREE SOURCE PACKET. The editable file is exact; "
                      "dependency bodies may be stubbed. Use worktree reads when needed.\n")
            if packet.get("kind") == "navigation":
                header = ("\nBOUND WORKTREE NAVIGATION PACKET. These paths and optional symbols and edges "
                          "are navigation only. Use exact source reads to make changes.\n")
            raw, sent = prompt + header + packet["raw"], prompt + header + packet["sent"]
            receipt = {"turn": int(state.get("turn") or 0) + 1,
                       "files": packet["files"], "stage_seconds": packet["seconds"],
                       "raw_prompt_sha256": digest(raw.encode()), "sent_prompt_sha256": digest(sent.encode()),
                       "raw_prompt_bytes": len(raw.encode()), "sent_prompt_bytes": len(sent.encode()),
                       "bytes_saved": len(raw.encode()) - len(sent.encode())}
            self.source_packet_receipt = receipt
            event = "agent.efficiency.source_packet_prompt"
            if packet.get("kind") == "navigation":
                receipt["navigation"] = packet["navigation"]
                receipt["packet"] = json.loads(packet["sent"])
                event = "agent.efficiency.navigation_packet_prompt"
            self.engine.emit(run["run_id"], event, receipt)
            prompt = sent
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


async def record_failed_verification(engine, runtime, rid, *, baseline=False):
    try:
        await engine.execute_tool(rid, "worktree.verify", {"command": list(PUBLIC)})
    except ToolExecutionFailed:
        state = runtime._state(rid)
        run = engine.store.get_run(rid)
        verify = (run.get("checkpoint") or {}).get("verification") or {}
        if baseline and (verify.get("returncode") != 1
                         or "alpha-01" not in str(verify.get("stdout_tail"))
                         or "alpha-02" not in str(verify.get("stdout_tail"))):
            raise RuntimeError("baseline diagnostic verifier did not expose both markers")
        state.setdefault("observations", []).append({"tool_id": "worktree.verify", "status": "failed",
            "result": {"returncode": verify.get("returncode"), "stdout": verify.get("stdout_tail"),
                       "stderr": verify.get("stderr_tail")}})
        runtime._save(rid, state)
        return run, True
    if baseline:
        raise RuntimeError("baseline diagnostic verifier unexpectedly passed")
    return engine.store.get_run(rid), False


async def bind_fixture_before_first_turn(engine, runtime, run):
    """Use the real scoped bind and approval, but spend no model turn on setup."""
    run_id = run["run_id"]
    tool = "worktree.bind"
    args = {"objective": engine.task.objective, "base_ref": "HEAD", "provider": "local"}
    decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id=tool, arguments=args)
    approval_id, parked = runtime._approval(run_id, run, decision, engine.tool_registry.get(tool), {})
    if parked:
        raise RuntimeError("fixture prebind did not receive the existing scoped approval")
    engine.store.transition(run_id, AgentRunState.EXECUTING_TOOL)
    observation = await engine.execute_tool(run_id, tool, args, approval_id=approval_id)
    engine.store.transition(run_id, AgentRunState.OBSERVING)
    snapshot = engine.store.get_run(run_id)
    bound = worktree_for(engine, snapshot)
    if bound is None or git(bound, "rev-parse", "HEAD") != git(engine.workspace_root, "rev-parse", "HEAD"):
        raise RuntimeError("fixture prebind did not produce an exact validated binding")
    state = runtime._state(run_id)
    state["observations"] = [runtime._compact_observation(tool, observation)]
    runtime._save(run_id, state)
    engine.emit(run_id, "agent.efficiency.prebind_completed", {"base_commit": git(bound, "rev-parse", "HEAD").strip()})
    return bound


async def attempt(out: Path, row: dict[str, Any], args: argparse.Namespace, key: str) -> dict[str, Any]:
    source_experiment = "source_packet" in row
    prebind = bool(row.get("prebind"))
    task = args.materialized_tasks[row["task"]] if args.experiment == REAL_GRAPH_EXPERIMENT else (
        SOURCE_TASKS if source_experiment else TASKS)[row["task"]]
    real_repo = bool(task.provenance)
    diagnostic = "compression" in row
    if diagnostic:
        task = diagnostic_fixture(task)
    root = out / "fixtures" / row["attempt_id"]
    anchors = create_fixture(root, task)
    before = heldout(root, task)
    baseline_public = subprocess.run(
        [sys.executable, "-B", *PUBLIC[1:]], cwd=root, capture_output=True, timeout=15,
    ).returncode
    if before["exit"] != 1 or baseline_public != 1:
        raise RuntimeError("fixture must fail both public and independent tests before any agent action")
    engine = FixtureEngine(root, task, prebind=prebind)
    objective = (task.objective + " Work in one isolated worktree and change only the implementation. "
                 "Verify with the exact argv python -m unittest -q test_public. Do not apply the worktree.")
    if prebind:
        objective += " The isolated worktree is already bound; use it without rebinding."
    run = engine.create_run(session_id="efficiency-matrix", objective=objective,
                            mode="agent", provider=args.provider, model=args.model if args.provider == "nim" else "scripted",
                            request={"autonomy": "autopilot", "execution_target": "local", "launch_strategy": "direct_coder"})
    rid = run["run_id"]
    delegate = MeasuredNIM(key=key, model=args.model) if args.provider == "nim" else Scripted(task, prebind=prebind)
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
    runtime = ExperimentRuntime(engine, provider, hint=hint, max_turns=args.max_turns,
                                compression=row.get("compression"),
                                compression_backend=getattr(args, "compression_backend", "native"),
                                detection=getattr(args, "compression_detection", {}))
    if prebind:
        bound = await bind_fixture_before_first_turn(engine, runtime, run)
        if "graph_packet" in row:
            paths = [p for p in git(bound, "ls-files", "-z").split("\0") if p.endswith(".py")]
            runtime.source_packet = build_graph_packet(
                bound, paths, row["graph_packet"], out / "tmp" / row["attempt_id"] / "graph.sqlite3",
                real_repo=real_repo, objective=task.objective)
        else:
            runtime.source_packet = build_source_packet(bound, task, compress=row["source_packet"] == "longcodezip")
        run = engine.store.get_run(rid)
    closed = preflight = False
    terminal = {state.value for state in TERMINAL_STATES} | {"paused", "waiting_for_approval"}
    for _ in range(args.max_turns + 1):
        epoch = (run.get("checkpoint") or {}).get("worktree_mutation_epoch") or 0
        run = await runtime.run_one_turn(rid)
        if run["state"] in terminal:
            break
        if diagnostic and not preflight and worktree_for(engine, run) is not None:
            run, preflight = await record_failed_verification(engine, runtime, rid, baseline=True)
        if source_experiment and runtime.source_packet is None:
            bound = worktree_for(engine, run)
            if bound is not None:
                runtime.source_packet = build_source_packet(
                    bound, task, compress=row["source_packet"] == "longcodezip")
        new_epoch = (run.get("checkpoint") or {}).get("worktree_mutation_epoch") or 0
        if row["closeout"] and new_epoch > epoch:
            wt = worktree_for(engine, run)
            if wt is None or changed_paths(wt) != [task.path]:
                continue
            engine.emit(rid, "agent.efficiency.closeout_started", {"mutation_epoch": new_epoch})
            run, failed = await record_failed_verification(engine, runtime, rid)
            if failed:
                continue
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
    rejection = requests[0].get("http_rejection") if len(requests) == 1 else None
    first_turn_rejection = (
        rejection if run["state"] == "paused" and provider.decisions == 1 and not preflight
        # Mechanical worktree prebind is not a model action.
        and not any(e["event_type"] == "agent.coder.decision" for e in events)
        and rejection and 400 <= rejection["status"] < 500 else None
    )
    experiment_metrics = {}
    if source_experiment:
        receipt = runtime.source_packet_receipt
        joined = bool(receipt and any(r.get("user_prompt_sha256") == receipt["sent_prompt_sha256"]
                                      for r in requests))
        experiment_metrics = {
            "source_packet_rendered": int(receipt is not None),
            "source_packet_provider_deliveries": int(joined),
            "source_packet_first_turn_provider_delivered": bool(
                receipt and receipt["turn"] == 1 and requests
                and requests[0].get("user_prompt_sha256") == receipt["sent_prompt_sha256"]
            ),
            "source_packet_provider_compressed_deliveries": int(bool(joined and receipt["bytes_saved"] > 0)),
            "source_packet_provider_prompt_bytes_saved": max(0, receipt["bytes_saved"]) if joined else 0,
            "source_packet_stage_seconds": runtime.source_packet["seconds"] if runtime.source_packet else 0,
            "provider_message_bytes": sum(r["prompt_bytes"] for r in requests),
            "provider_request_body_bytes": sum(r["request_body_bytes"] for r in requests),
        }
    if real_repo:
        nav = (runtime.source_packet or {}).get("navigation") or {}
        experiment_metrics.update(cold_index_seconds=nav.get("cold_index_seconds"),
                                  indexed_snapshot_lookup_seconds=nav.get("indexed_snapshot_lookup_seconds"))
    if diagnostic:
        joined = {r["user_prompt_sha256"] for r in requests if r.get("user_prompt_sha256")}
        applied = [r for r in runtime.compression_receipts if r["applied"]]
        submitted = [r for r in applied if r["sent_prompt_sha256"] in joined]
        experiment_metrics = {"diagnostic_preflight": preflight,
                              "compression_deliveries": len(applied),
                              "compression_prompt_bytes_saved": sum(r["bytes_saved"] for r in applied),
                              "compression_provider_deliveries": len(submitted),
                              "compression_provider_prompt_bytes_saved": sum(r["bytes_saved"] for r in submitted),
                              "compression_stage_seconds": round(sum(
                                  field["seconds"] for r in runtime.compression_receipts
                                  for field in r["attempted_fields"]), 6),
                              "provider_message_bytes": sum(r["prompt_bytes"] for r in requests),
                              "provider_request_body_bytes": sum(r["request_body_bytes"] for r in requests)}
    return {**row, **experiment_metrics, "run_id": rid, "state": run["state"],
            "first_turn_http_rejection": first_turn_rejection, "verified": bool(
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


def summarize(rows: list[dict[str, Any]], provider: str, *, experiment: str = "navigation") -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    planned: dict[str, int] = defaultdict(int)
    not_run: dict[str, int] = defaultdict(int)
    for row in rows:
        planned[row["arm"]] += 1
        if row["state"] == "not_run":
            not_run[row["arm"]] += 1
            continue
        grouped[row["arm"]].append(row)
        blocks[(row["task"], row["repeat"])][row["arm"]] = row
    results = {}
    diagnostic = experiment == DIAGNOSTIC_EXPERIMENT
    source_experiment = experiment in PACKET_EXPERIMENTS
    for name in EXPERIMENT_ARMS[experiment]:
        arm = grouped[name]
        good = sum(row["verified"] for row in arm)
        calls = sum(row["provider_attempts"] for row in arm) if all("provider_attempts" in row for row in arm) else None
        total_seconds = sum(row["wall_seconds"] for row in arm) if all("wall_seconds" in row for row in arm) else None
        results[name] = {"planned": planned[name], "not_run": not_run[name],
                         "attempts": len(arm), "verified": good,
                         "verified_rate": good / len(arm) if arm else None,
                         "total_agent_wall_seconds": total_seconds,
                         "agent_seconds_per_verified": total_seconds / good if total_seconds is not None and good else None,
                         "provider_attempts": calls,
                         "provider_attempts_per_verified": calls / good if calls is not None and good else None,
                         "median_wall_seconds": median([row["wall_seconds"] for row in arm if "wall_seconds" in row])
                         if any("wall_seconds" in row for row in arm) else None}
    if diagnostic or source_experiment:
        fields = ("provider_attempts", "provider_message_bytes", "provider_request_body_bytes", "prompt_tokens_observed",
                  "completion_tokens_observed", "wall_seconds", "source_read_calls")
        def complete(row, field):
            return row.get(field) is not None and (not field.endswith("_observed")
                or row.get("requests_with_usage") == row.get("provider_attempts"))
        for name, arm in grouped.items():
            covered = [row for row in arm if complete(row, "prompt_tokens_observed")]
            results[name].update(
                trials_with_complete_usage=len(covered),
                requests_with_usage=sum(r.get("requests_with_usage", 0) for r in arm),
                provider_message_bytes=sum(r["provider_message_bytes"] for r in arm)
                    if all("provider_message_bytes" in r for r in arm) else None,
                provider_request_body_bytes=sum(r["provider_request_body_bytes"] for r in arm)
                    if all("provider_request_body_bytes" in r for r in arm) else None,
                compression_provider_deliveries=sum(r.get("compression_provider_deliveries", 0) for r in arm),
                compression_provider_prompt_bytes_saved=sum(r.get("compression_provider_prompt_bytes_saved", 0) for r in arm),
                compression_stage_seconds=round(sum(r.get("compression_stage_seconds", 0.0) for r in arm), 6),
                diagnostic_preflights=sum(bool(r.get("diagnostic_preflight")) for r in arm),
                provider_input_tokens_total=sum(r["prompt_tokens_observed"] for r in covered) if len(covered) == len(arm) else None,
                provider_output_tokens_total=sum(r["completion_tokens_observed"] for r in covered) if len(covered) == len(arm) else None,
            )
            if source_experiment:
                for field in ("source_packet_rendered", "source_packet_provider_deliveries",
                              "source_packet_provider_compressed_deliveries",
                              "source_packet_first_turn_provider_delivered",
                              "source_packet_provider_prompt_bytes_saved", "source_packet_stage_seconds"):
                    results[name][field] = sum(r.get(field, 0) for r in arm)
        def comparisons(baseline, treatments=None):
            pairs = []
            metrics = fields + (("first_target_read_tool_number",) if experiment in GRAPH_EXPERIMENTS else ())
            for (task, repeat), block in blocks.items():
                control = block.get(baseline)
                if control is None:
                    continue
                for arm, row in block.items():
                    if arm == baseline or (treatments is not None and arm not in treatments):
                        continue
                    pairs.append({"task": task, "repeat": repeat, "arm": arm,
                                  "verified_delta": int(row["verified"]) - int(control["verified"]),
                                  "arm_state": row["state"], "control_state": control["state"],
                                  "deltas": {field: round(row[field] - control[field], 6)
                                             if complete(row, field) and complete(control, field) else None
                                             for field in metrics}})
            return pairs

        pairs = ({"paired_against_file_list": comparisons("file_list"),
                  "paired_graph_against_symbols": comparisons("symbols", {"graph"})}
                 if experiment == NAV_GRAPH_EXPERIMENT else
                 {"paired_against_file_list": comparisons("file_list")} if experiment == REAL_GRAPH_EXPERIMENT else
                 {"paired_against_closeout": comparisons("closeout")})
        if experiment == REAL_GRAPH_EXPERIMENT:
            for arm_name, arm_rows in grouped.items():
                for field in ("cold_index_seconds", "indexed_snapshot_lookup_seconds"):
                    values = [r[field] for r in arm_rows if r.get(field) is not None]
                    results[arm_name][field] = {"n": len(values), "median": median(values) if values else None,
                                                "total": sum(values) if values else None}
        evidence_class = ("scripted_control_only" if provider == "scripted" else
                          "live_upstream_seeded_pilot" if experiment == REAL_GRAPH_EXPERIMENT else "live_synthetic_pilot")
        return {"evidence_class": evidence_class,
                "experiment": experiment, "arms": results, **pairs}
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
    parser.add_argument("--experiment", choices=tuple(EXPERIMENT_ARMS), default="navigation")
    parser.add_argument("--compression-backend", choices=("native", "upstream"), default="native")
    parser.add_argument("--tasks", nargs="+", choices=tuple(TASKS) + tuple(SOURCE_TASKS) + tuple(UPSTREAM))
    parser.add_argument("--repo-fixtures", type=Path, help="parent of pinned packaging and itsdangerous Git checkouts")
    parser.add_argument("--provider", choices=["scripted", "nim"], default="scripted")
    parser.add_argument("--model", default="nvidia/nemotron-3.5-super-vl-120b-a12b")
    parser.add_argument("--seed", type=int, default=4317)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--request-cap", type=int, default=0, help="required live request ceiling")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20 or not 5 <= args.max_turns <= 32:
        parser.error("repeats must be 1–20 and max-turns 5–32")
    if args.experiment == REAL_GRAPH_EXPERIMENT:
        if args.repo_fixtures is None:
            parser.error("real-repo-navigation requires --repo-fixtures")
        task_set = load_real_tasks(args.repo_fixtures)
        args.materialized_tasks = task_set
    else:
        task_set = SOURCE_TASKS if args.experiment in PACKET_EXPERIMENTS else TASKS
    args.tasks = args.tasks or list(task_set)
    if any(task not in task_set for task in args.tasks):
        parser.error("selected task is not part of this experiment")
    if args.experiment in SOURCE_EXPERIMENTS and args.compression_backend != "native":
        parser.error("source compression uses the BEAST-native LongCodeZip-style implementation")
    if len(set(args.tasks)) != len(args.tasks):
        parser.error("task names must be unique")
    plan = make_plan(tuple(args.tasks), args.repeats, args.seed, experiment=args.experiment)
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
        if args.experiment == DIAGNOSTIC_EXPERIMENT and args.compression_backend == "upstream":
            detected = detect_compressors()
            args.compression_detection = {tier: detected[tier] for tier in ("rtk", "sqz")}
            missing = [tier for tier, entry in args.compression_detection.items() if not entry["real_tool"]]
            if missing:
                parser.error("upstream binaries could not be identified: " + ", ".join(missing))
            for entry in args.compression_detection.values():
                with Path(entry["binary_path"]).open("rb") as binary:
                    entry["binary_sha256"] = hashlib.file_digest(binary, "sha256").hexdigest()
        if args.provider == "nim":
            os.environ["BEAST_NIM_MAX_TOKENS"] = "2048"
        frozen = {"schema": "beast.coder.efficiency.v1", "code_head": git(REPO, "rev-parse", "HEAD").strip(),
                  "provider": args.provider, "model": args.model if args.provider == "nim" else None,
                  "seed": args.seed, "max_turns": args.max_turns, "request_cap": args.request_cap,
                  "public_command": PUBLIC, "plan": plan,
                  "harness_sha256": digest(Path(__file__).read_bytes()), "python": sys.version.split()[0],
                  "reporelay_budget_estimated_tokens": 320, "nim_stream": False, "nim_max_retries": 0,
                  "nim_max_output_tokens": 2048 if args.provider == "nim" else None,
                  "provider_rejection_gate": {
                      "enabled": args.provider == "nim", "consecutive_trials": 2, "distinct_arms": True,
                      "condition": "matching first-turn HTTP 4xx fingerprints before any model decision",
                  },
                  "heldout_sha256": {name: digest(task_set[name].heldout.encode()) for name in args.tasks},
                  "claim_boundary": "Synthetic fixtures, no operating-system network isolation. "
                                    "Scripted mode does not measure model efficacy. Live counts are adapter request attempts."}
        if args.experiment == DIAGNOSTIC_EXPERIMENT:
            frozen.update(experiment=args.experiment, compression_backend=args.compression_backend,
                          compression_detection=getattr(args, "compression_detection", {}),
                          diagnostic_preflight="real fixed verifier after bind, before agent mutation",
                          backend_sha256={
                              str(Path(fn.__code__.co_filename).relative_to(REPO)):
                              digest(Path(fn.__code__.co_filename).read_bytes())
                              for fn in (compress_cascade_output, _sqz)
                          })
        if args.experiment in SOURCE_EXPERIMENTS:
            frozen.update(
                experiment=args.experiment, compression_backend="beast_native_longcodezip_style",
                source_budget_ratio=SOURCE_BUDGET_RATIO, source_packet_cadence="first post-bind prompt only",
                source_binding=("harness_before_first_request" if args.experiment == PREBOUND_SOURCE_EXPERIMENT
                                else "model_selected_bind"),
                source_backend_sha256=digest(Path(long_code_compress.__code__.co_filename).read_bytes()),
                source_packet_fixture_sha256={
                    name: {task_set[name].path: digest(task_set[name].source.encode()),
                           **{path: digest(code.encode()) for path, code in task_set[name].support}}
                    for name in args.tasks},
            )
        if args.experiment in GRAPH_EXPERIMENTS:
            frozen.update(experiment=args.experiment, packet_binding="before_first_request",
                          packet_limit_bytes=8000, packet_cadence="first_request_only",
                          graph_index_scope="tracked Python files, isolated database per attempt",
                          graph_backend_sha256=digest((REPO / "app/kernel/data_processing/workspace_graph.py").read_bytes()))
        if args.experiment == REAL_GRAPH_EXPERIMENT:
            for name in args.tasks:
                task = task_set[name]
                upstream = out / "tmp" / f"{name}-pristine"
                original = replace(task, source=task.source.replace(task.old, task.new, 1))
                create_fixture(upstream, original)
                public_rc = subprocess.run([sys.executable, "-B", *PUBLIC[1:]], cwd=upstream,
                                           capture_output=True, timeout=15).returncode
                if public_rc != 0 or heldout(upstream, original)["exit"] != 0:
                    raise RuntimeError(f"pristine upstream validation failed for {name}")
                mutant = out / "tmp" / f"{name}-seeded"
                create_fixture(mutant, task)
                mutant_rc = subprocess.run([sys.executable, "-B", *PUBLIC[1:]], cwd=mutant,
                                           capture_output=True, timeout=15).returncode
                if mutant_rc != 1 or heldout(mutant, task)["exit"] != 1:
                    raise RuntimeError(f"seeded regression did not fail both checks for {name}")
            frozen.update(upstream={name: task_set[name].provenance for name in args.tasks},
                          claim_boundary="Pinned real open-source package code with seeded regressions and independent "
                                         "behavior checks. Not historical issues or model-training-blinded. "
                                         "Cold index build and lookup against the built index are measured separately. "
                                         "These task fixtures are not OS-network-isolated.")
        write_json(out / "plan.json", frozen)
        rows = []
        prior_rejection = None
        abort = None
        for row in plan:
            if abort is not None:
                result = {**row, "state": "not_run", "verified": None,
                          "not_run_reason": "batch_aborted_provider_rejection"}
            else:
                try:
                    result = asyncio.run(attempt(out, row, args, key))
                except Exception as exc:
                    result = {**row, "state": "harness_error", "verified": False, "error_type": type(exc).__name__}
                    if args.provider == "scripted":
                        result["error"] = str(exc)[:600]
                rejection = result.get("first_turn_http_rejection") if args.provider == "nim" else None
                if rejection is None:
                    prior_rejection = None
                else:
                    fingerprint = rejection["fingerprint"]
                    if (prior_rejection is not None and prior_rejection["fingerprint"] == fingerprint
                            and prior_rejection["arm"] != row["arm"]):
                        abort = {"rejection": rejection,
                                 "trigger_attempt_ids": [prior_rejection["attempt_id"], row["attempt_id"]]}
                        print(f"BATCH_ABORT=provider_rejection HTTP={rejection['status']} "
                              f"fingerprint={fingerprint}", flush=True)
                    prior_rejection = {"fingerprint": fingerprint, "arm": row["arm"],
                                       "attempt_id": row["attempt_id"]}
            append_jsonl(out / "attempts.jsonl", result)
            rows.append(result)
            print(row["attempt_id"], result["state"], "verified=", result["verified"],
                  "attempts=", result.get("provider_attempts"), flush=True)
        summary = summarize(rows, args.provider, experiment=args.experiment)
        skipped = sum(row["state"] == "not_run" for row in rows)
        summary["batch"] = {"status": "aborted_provider_rejection" if abort else "completed",
                            "planned": len(plan), "attempted": len(rows) - skipped,
                            "not_run": skipped, "abort": abort}
        write_json(out / "summary.json", summary)
        paths = [out / "plan.json", out / "attempts.jsonl", out / "summary.json",
                 *sorted((out / "events").glob("*.jsonl")), *sorted((out / "provider").glob("*.json"))]
        (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in paths))
        print("REPORT:", out)
        if abort is not None:
            return 3
        return int(any(row["state"] == "harness_error" for row in rows)
                   or (args.provider == "scripted" and not all(row["verified"] for row in rows)))
    finally:
        os.environ.clear()
        os.environ.update(previous)


if __name__ == "__main__":
    raise SystemExit(main())
