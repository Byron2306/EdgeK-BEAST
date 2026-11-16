#!/usr/bin/env python3
"""One crystallization gauntlet with live NIM + Ollama, then a sealed-memfd zero-model replay of the promoted crystal.

Part A: the cold episode solves a repo-local config-constant regression with a real NVIDIA NIM call (provider tier,
D9 provider_fallback, Governor `cloud` admit). It is distilled by the real CodingCrystalExtractor and reproduced on
3 held-out repos. It is promoted only with `--approve-by NAME`. Warm episodes then route through the D9 router: an
exact-band hit replays the crystal with zero model calls. A structural near-miss goes to the Ollama swarm specialist
(qwen3:4b), and a far task goes to NIM.

Part B: the promoted crystal is hydrated into a sealed memfd. Only the fd is passed to a separate replay process
(empty netns via `unshare -rn` when allowed). The child replays with zero model calls and is verified against the
expected postcondition. The run emits a receipt with measured bytes, copies, digests and seals, plus PGEC eq.(6) V_K
and a shadow credit.

All BEAST_* flags are set in-process only. State lives in .beast/gauntlets/2026-11-16 and evidence in
evidence/gauntlet-2026-11-16. No secret values are printed or written; the NIM key is loaded by name via SecretVault.
"""
from __future__ import annotations
try:  # closure-2026-11-16: governed egress shim
    from app.kernel.compute import governed_egress as _egress
except ModuleNotFoundError:  # run as a script: repo root not on sys.path yet
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from app.kernel.compute import governed_egress as _egress

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAMILY = "fix-failing-config-constant"
PY = "/usr/bin/python3"
SPECIALIST = {"execution_mode": "local_specialist_adapter", "model_ref": "ollama://qwen3:4b",
              "boundary_checks_passed": True}
FLAGS = {"BEAST_ADAPTIVE_ROUTER": "1", "BEAST_GOVERNOR_ENFORCE": "1", "BEAST_SWARM_SPECIALIST": "1",
         "BEAST_CRYSTAL_CAPSULE": "1", "BEAST_SWARM_SPECIALIST_MODEL": "qwen3:4b",
         "BEAST_QUALITY_CASCADE_SKIP": "gauntlet-2026-11-16:unittest-verifier-is-the-gate"}


def sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


# --- task family: a service config constant drifted from its contract test ---------------------------------------
def _constant_task(pkg: str, name: str, old: int, new: int, others: dict[str, Any]) -> dict[str, Any]:
    lines = [f"\"\"\"{pkg} service configuration.\"\"\"", ""]
    for key, value in [*others.items(), (name, old)]:
        lines.append(f"{key} = {value!r}")
    other_key, other_val = next(iter(others.items()))
    tests = (f"import unittest\nfrom {pkg}.config import {name}, {other_key}\n\n\n"
             f"class Contract(unittest.TestCase):\n"
             f"    def test_{name.lower()}_matches_contract(self):\n        self.assertEqual({name}, {new!r})\n\n"
             f"    def test_{other_key.lower()}_unchanged(self):\n        self.assertEqual({other_key}, {other_val!r})\n")
    return {"kind": "constant", "files": {f"{pkg}/__init__.py": "", f"{pkg}/config.py": "\n".join(lines) + "\n",
                                          f"test_{pkg}_contract.py": tests},
            "target": f"{pkg}/config.py", "verify": [PY, "-m", "unittest", f"test_{pkg}_contract"], "tests_run": 2,
            "fixed_line": f"{name} = {new!r}"}


TASKS = {
    "cold-billing": _constant_task("billing", "INVOICE_RETRY_LIMIT", 3, 5, {"SERVICE_NAME": "billing", "GRACE_DAYS": 14}),
    "heldout-scheduler": _constant_task("scheduler", "MAX_WORKERS", 4, 8, {"QUEUE": "default", "TICK_MS": 250}),
    "heldout-auth": _constant_task("auth", "TOKEN_TTL_MINUTES", 15, 30, {"ISSUER": "beast", "SKEW_SECONDS": 30}),
    "heldout-cache": _constant_task("cache", "CACHE_MAX_ENTRIES", 512, 1024, {"BACKEND": "lru", "SHARDS": 8}),
    "warm-ingest": _constant_task("ingest", "BATCH_SIZE", 100, 250, {"SOURCE": "kafka", "LINGER_MS": 20}),
    "warm-notify": _constant_task("notify", "MAX_EMAILS_PER_HOUR", 50, 60, {"SENDER": "ops", "RETRIES": 2}),
    "near-miss-pricing": {
        "kind": "logic",
        "files": {"pricing/__init__.py": "",
                  "pricing/tax.py": "\"\"\"VAT helpers.\"\"\"\n\n\ndef vat(amount):\n    return round(amount * 0.14, 2)\n",
                  "test_pricing_contract.py": ("import unittest\nfrom pricing.tax import vat\n\n\n"
                                               "class Contract(unittest.TestCase):\n    def test_vat_is_15_percent(self):\n"
                                               "        self.assertEqual(vat(100), 15.0)\n\n"
                                               "    def test_vat_zero(self):\n        self.assertEqual(vat(0), 0.0)\n")},
        "target": "pricing/tax.py", "verify": [PY, "-m", "unittest", "test_pricing_contract"], "tests_run": 2},
    "far-parser": {
        "kind": "exception",
        "files": {"parser/__init__.py": "",
                  "parser/ratio.py": "\"\"\"Ratio parsing.\"\"\"\n\n\ndef ratio(text):\n    num, den = text.split('/')\n"
                                     "    return int(num) / int(den)\n",
                  "test_parser_contract.py": ("import unittest\nfrom parser.ratio import ratio\n\n\n"
                                              "class Contract(unittest.TestCase):\n    def test_half(self):\n"
                                              "        self.assertEqual(ratio('1/2'), 0.5)\n\n"
                                              "    def test_zero_denominator_is_none(self):\n"
                                              "        self.assertIsNone(ratio('1/0'))\n")},
        "target": "parser/ratio.py", "verify": [PY, "-m", "unittest", "test_parser_contract"], "tests_run": 2},
}


def make_repo(base: Path, name: str, label: str = "") -> Path:
    root = base / (label or name) / "repo"
    if root.parent.exists():
        shutil.rmtree(root.parent)
    for rel, text in TASKS[name]["files"].items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


# --- deterministic local applicability matcher (nominates only; verifiers decide) --------------------------------
MATCH_WEIGHTS = {"unittest_verify": 0.2, "single_literal_equality_failure": 0.3, "scalar_types_match": 0.2,
                 "unique_module_constant_equals_actual": 0.12, "single_python_target": 0.18}


def match(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    import ast
    import re

    from app.kernel.compute.crystal_memfd_capsule import _run_verify

    observed = _run_verify(task["verify"], root)
    found = re.findall(r"^AssertionError: (.+?) != (.+?)\s*$", observed["output"], re.MULTILINE)

    def lit(text: str) -> Any:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None

    content = (root / task["target"]).read_text(encoding="utf-8")
    actual = lit(found[0][0]) if len(found) == 1 else None
    expected = lit(found[0][1]) if len(found) == 1 else None
    constants = [line for line in content.splitlines()
                 if re.match(r"^[A-Z_][A-Z0-9_]*\s*=", line) and actual is not None
                 and lit(line.split("=", 1)[1].strip()) == actual and type(lit(line.split("=", 1)[1].strip())) is type(actual)]
    features = {"unittest_verify": task["verify"][1:3] == ["-m", "unittest"],
                "single_literal_equality_failure": len(found) == 1 and observed["returncode"] != 0,
                "scalar_types_match": actual is not None and expected is not None and type(actual) is type(expected),
                "unique_module_constant_equals_actual": len(constants) == 1,
                "single_python_target": task["target"].endswith(".py")}
    score = round(sum(MATCH_WEIGHTS[k] for k, v in features.items() if v), 4)
    return {"similarity": score, "features": features, "observed_failure": observed["output"][-600:],
            "matcher": "beast.gauntlet.applicability_matcher.v1 (local, deterministic, nominates only)"}


# --- model meters ------------------------------------------------------------------------------------------------
class Meter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def count(self, provider: str | None = None) -> int:
        return sum(1 for c in self.calls if provider is None or c["provider"] == provider)


METER = Meter()


def nim_chat(messages: list[dict[str, str]], *, max_tokens: int = 2048) -> dict[str, Any]:
    import httpx

    from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe
    from app.kernel.security.secret_vault import SecretVault

    SecretVault().load(override=False)
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY not loaded (expected in .beast/provider_secrets.env)")
    cfg = NvidiaNIMLiveProbe().config(timeout_seconds=90, max_tokens=max_tokens)
    errors = []
    for model in cfg.model_candidates[:4]:
        started = time.perf_counter()
        try:
            response = _egress.post(httpx, "gauntlet_memfd_replay", cfg.base_url + "/chat/completions", timeout=90,
                                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                                  json={"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens,
                                        "stream": False})
        except httpx.HTTPError as exc:
            errors.append({"model": model, "error": type(exc).__name__})
            continue
        latency = round((time.perf_counter() - started) * 1000, 3)
        if response.status_code >= 400:
            errors.append({"model": model, "status": response.status_code})
            METER.calls.append({"provider": "nvidia_nim", "model": model, "status": response.status_code,
                                "latency_ms": latency, "tokens_total": 0, "failed": True})
            continue
        body = response.json()
        usage = body.get("usage") or {}
        text = str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        call = {"provider": "nvidia_nim", "model": model, "base_url": cfg.base_url, "status": response.status_code,
                "latency_ms": latency, "tokens_prompt": int(usage.get("prompt_tokens") or 0),
                "tokens_completion": int(usage.get("completion_tokens") or 0),
                "tokens_total": int(usage.get("total_tokens") or 0), "usage_reported": bool(usage),
                "tokens_reasoning": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
                "finish_reason": str((body.get("choices") or [{}])[0].get("finish_reason") or ""),
                "response_sha256": sha(text.encode()), "response_text": text[:2000]}
        METER.calls.append(call)
        return {**call, "text": text, "model_errors_before": errors}
    raise RuntimeError(f"no NIM model answered: {errors}")


def parse_edit(text: str) -> dict[str, str] | None:
    import re

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    for blob in re.findall(r"\{.*?\}", text, flags=re.S) + [text]:
        try:
            value = json.loads(blob)
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("old_text"), str) and isinstance(value.get("new_text"), str):
            return {"old_text": value["old_text"].rstrip("\n"), "new_text": value["new_text"].rstrip("\n")}
    return None


def edit_prompt(task: dict[str, Any], content: str, failure: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": "You are a precise code repair agent. Reply with one JSON object only."},
            {"role": "user", "content": (
                f"The contract test fails. Fix {task['target']} with one exact single-line replacement.\n"
                f"Reply ONLY with JSON: {{\"old_text\": <the exact existing line>, \"new_text\": <the replacement line>}}."
                " If the fix is a module constant, new_text must be exactly `NAME = value` with no comment.\n\n"
                f"--- {task['target']} ---\n{content}\n--- failing test output ---\n{failure[-1500:]}")}]


def apply_and_verify(root: Path, task: dict[str, Any], edit: dict[str, str] | None, worktree: Path) -> dict[str, Any]:
    from app.kernel.compute.crystal_memfd_capsule import _run_verify

    if worktree.exists():
        shutil.rmtree(worktree)
    shutil.copytree(root, worktree)
    path = worktree / task["target"]
    text = path.read_text(encoding="utf-8")
    if not edit or not edit["old_text"] or text.count(edit["old_text"]) != 1:
        return {"applied": False, "passed": False, "reason": "edit_not_exact_unique"}
    path.write_text(text.replace(edit["old_text"], edit["new_text"], 1), encoding="utf-8")
    result = _run_verify(task["verify"], worktree)
    return {"applied": True, "passed": result["returncode"] == 0 and result["tests_run"] == task["tests_run"],
            "returncode": result["returncode"], "tests_run": result["tests_run"], "verify_ms": result["ms"],
            "output_tail": result["output"][-300:]}


# --- Part A ----------------------------------------------------------------------------------------------------
def cold_episode(work: Path, governor: Any, router: Any) -> dict[str, Any]:
    from app.kernel.compute.crystal_memfd_capsule import _run_verify
    from app.kernel.governance.governor_spine import Episode, Proposal
    from app.kernel.sensorium.episode_envelope import BUDGET_KEYS, ENVELOPE_SCHEMA, EpisodeEnvelope

    name, task = "cold-billing", TASKS["cold-billing"]
    started = time.perf_counter()
    root = make_repo(work, name)
    run_id = f"gauntlet-2026-11-16:{name}:{int(time.time())}"
    route = router.route_run({"request": {"task_family": FAMILY, "route_similarity": 0.0}}, specialist=SPECIALIST)
    steps, observations, tool_calls = [], [], 0

    def step(tool: str, source: str, result: dict[str, Any], *, path: str = "", args: dict | None = None,
             rc: Any = None, ms: float = 0.0) -> None:
        nonlocal tool_calls
        digest = sha({"tool": tool, "result": result, "args": args or {}, "i": len(steps)})
        steps.append({"index": len(steps), "tool_id": tool, "status": "completed", "source": source,
                      "arguments_digest": sha(args or {}), "safe_arguments": {"path": path} if path else {},
                      "result_digest": digest, "returncode": rc, "duration_ms": ms})
        observations.append({"evidence_digest": digest, "result": result, "arguments": args or {}})
        tool_calls += 1

    content = (root / task["target"]).read_text(encoding="utf-8")
    step("workspace.read_range", "runtime", {"content": content}, path=task["target"])
    worktree = work / name / "worktree"
    shutil.copytree(root, worktree)
    step("worktree.bind", "runtime", {"worktree": "bound"})
    first = _run_verify(task["verify"], worktree)
    step("worktree.verify", "runtime", {"stdout": "", "stderr": first["output"]}, rc=first["returncode"], ms=first["ms"])
    nim_calls, edit, verdict, attempts = [], None, None, []
    for attempt in range(2):
        proposal = Proposal(kind="cloud", provider="nvidia_nim", tool_id="gauntlet:cold_repair",
                            quality_cascade={"skipped": "cold_episode:no_crystal_or_specialist_route_for_family"},
                            signature_material={"run": run_id, "attempt": attempt}, estimate={"tokens_total": 1200.0})
        decision = governor.admit(Episode(run_id=run_id), proposal)
        messages = edit_prompt(task, content, first["output"] if attempt == 0 else
                               first["output"] + f"\nYour previous reply was rejected: {verdict}")
        call = governor.run_admitted(decision, proposal, lambda m=messages: nim_chat(m))
        nim_calls.append({k: v for k, v in call.items() if k != "text"} | {"governor": {
            "outcome": decision.outcome, "receipt_id": decision.receipt_id, "receipt_hash": decision.receipt_hash}})
        edit = parse_edit(call["text"])
        check = apply_and_verify(root, task, edit, work / name / f"probe-{attempt}")
        verdict = check.get("reason") or ("passed" if check["passed"] else "tests still failing")
        attempts.append({"edit": edit, "check": check})
        if check["passed"]:
            break
    if not attempts[-1]["check"]["passed"]:
        raise RuntimeError(f"cold episode: NIM did not produce a verified fix: {attempts}")
    target_path = worktree / task["target"]
    target_path.write_text(target_path.read_text().replace(edit["old_text"], edit["new_text"], 1))
    step("worktree.replace_exact", "model", {"replaced": True}, path=task["target"], args=dict(edit))
    final = _run_verify(task["verify"], worktree)
    step("worktree.verify", "runtime", {"stdout": "", "stderr": final["output"]}, rc=final["returncode"], ms=final["ms"])
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    ok_calls = [c for c in nim_calls if not c.get("failed")]
    budget = dict.fromkeys(BUDGET_KEYS, 0.0) | {
        "model_turns": float(len(ok_calls)), "tokens_prompt": float(sum(c["tokens_prompt"] for c in ok_calls)),
        "tokens_completion": float(sum(c["tokens_completion"] for c in ok_calls)),
        "tokens_total": float(sum(c["tokens_total"] for c in ok_calls)),
        "tokens_estimated_turns": float(sum(1 for c in ok_calls if not c["usage_reported"])),
        "tool_calls": float(tool_calls), "tool_calls_model": 1.0, "tool_calls_runtime": float(tool_calls - 1),
        "wall_ms": wall_ms}
    verification = {"present": True, "passed": final["returncode"] == 0, "failures_before_pass": 1,
                    "final_returncode": final["returncode"], "verify_steps": 2}
    envelope = EpisodeEnvelope(schema=ENVELOPE_SCHEMA, run_id=run_id, origin="gauntlet_cold_episode",
                               workspace_digest=sha({k: sha(v.encode()) for k, v in task["files"].items()}),
                               objective_digest=sha(f"{FAMILY}:{task['target']}".encode()), task_family=FAMILY,
                               mode="agent", provider="nvidia_nim", model=ok_calls[-1]["model"], state="verified",
                               implementation_target=task["target"], steps=tuple(steps), verification=verification,
                               negative_evidence=({"index": 2, "tool_id": "worktree.verify", "kind": "verification_failed",
                                                   "result_digest": steps[2]["result_digest"]},),
                               budget=budget, event_chain_head=sha(steps)).sealed()
    return {"run_id": run_id, "task": name, "route": route.to_dict(), "nim_calls": nim_calls, "attempts": attempts,
            "edit": edit, "budget": budget, "verification": verification, "wall_ms": wall_ms,
            "fixed_target_sha256": sha(target_path.read_bytes()), "envelope": envelope, "observations": observations,
            "worktree": str(worktree)}


def replay_task(work: Path, name: str, candidate: Any, *, tag: str) -> dict[str, Any]:
    from app.kernel.compute.crystal_memfd_capsule import check_postcondition, replay_crystal

    task = TASKS[name]
    root = make_repo(work, name, f"{name}-{tag}")
    before = len(METER.calls)
    worktree = root.parent / "worktree"
    replay = replay_crystal(candidate, {"implementation_target": task["target"], "verify_command": task["verify"]},
                            root, worktree)
    post = check_postcondition(worktree, {"verify_command": task["verify"], "implementation_target": task["target"],
                                          "tests_run": task["tests_run"]}) if replay["ok"] else {"passed": False}
    return {"task": name, "replay": replay, "postcondition": post, "model_calls_during_replay": len(METER.calls) - before,
            "passed": bool(replay["ok"] and post["passed"])}


async def specialist_attempt(work: Path, name: str, route: dict[str, Any], governor: Any, root: Path) -> dict[str, Any]:
    from app.kernel.agents.swarm_specialist import OllamaSwarmRunner, SwarmSpecialistDispatch
    from app.kernel.compute.crystal_memfd_capsule import _run_verify

    task = TASKS[name]
    content = (root / task["target"]).read_text(encoding="utf-8")
    failure = _run_verify(task["verify"], root)["output"]
    checks: list[dict[str, Any]] = []

    def unittest_verifier(text: str, _ir: Any) -> tuple[bool, str]:
        edit = parse_edit(text)
        check = apply_and_verify(root, task, edit, work / name / "specialist-probe")
        checks.append({"edit": edit, "check": check})
        return bool(check["passed"]), "unittest_postcondition_passed" if check["passed"] else check.get("reason", "tests_failed")

    msgs = edit_prompt(task, content, failure)
    ir = SimpleNamespace(messages=msgs, metadata={"run_id": f"gauntlet:{name}"}, max_tokens=1024)
    runner = OllamaSwarmRunner(timeout=180)
    original = runner.generate

    async def metered(**kwargs: Any) -> dict[str, Any]:
        out = await original(**kwargs)
        METER.calls.append({"provider": "ollama", "model": out["model"], "latency_ms": out["latency_ms"],
                            "tokens_prompt": out["usage"]["prompt_tokens"],
                            "tokens_completion": out["usage"]["completion_tokens"],
                            "tokens_total": out["usage"]["prompt_tokens"] + out["usage"]["completion_tokens"],
                            "response_sha256": sha(out["text"].encode()), "response_text": out["text"][:2000]})
        return out

    runner.generate = metered  # type: ignore[method-assign]
    dispatch = SwarmSpecialistDispatch(runner=runner, governor=governor, verifiers=[unittest_verifier])
    outcome = await dispatch.dispatch(ir, route, run_id=f"gauntlet:{name}")
    return {"dispatched": outcome.dispatched, "reason": outcome.reason, "receipt": outcome.receipt, "checks": checks}


def warm_episode(work: Path, name: str, router: Any, governor: Any, registry: Any) -> dict[str, Any]:
    from app.kernel.compute.crystal_memfd_capsule import check_postcondition, replay_crystal
    from app.kernel.governance.governor_spine import Episode, Proposal

    task = TASKS[name]
    started = time.perf_counter()
    root = make_repo(work, name, f"{name}-warm")
    matched = match(root, task)
    route = router.route_run({"request": {"task_family": FAMILY, "route_similarity": matched["similarity"]}},
                             specialist=SPECIALIST)
    rd = route.to_dict()
    calls_before = len(METER.calls)
    out: dict[str, Any] = {"task": name, "match": matched, "route": rd}
    if rd["route"] == "crystal_replay":
        proposal = Proposal(kind="crystal", crystal_id=rd["crystal_id"], route_decision=rd,
                            signature_material={"task": name})
        decision = governor.admit(Episode(run_id=f"gauntlet:{name}"), proposal)
        candidate = registry.get(rd["crystal_id"])["candidate_object"]
        worktree = root.parent / "worktree"

        def run() -> dict[str, Any]:
            replay = replay_crystal(candidate, {"implementation_target": task["target"], "verify_command": task["verify"]},
                                    root, worktree)
            post = check_postcondition(worktree, {"verify_command": task["verify"], "tests_run": task["tests_run"],
                                                  "implementation_target": task["target"]})
            return {"replay": replay, "postcondition": post}

        result = governor.run_admitted(decision, proposal, run)
        out.update(result, governor={"outcome": decision.outcome, "receipt_id": decision.receipt_id},
                   passed=bool(result["replay"]["ok"] and result["postcondition"]["passed"]))
        if out["passed"]:
            registry.record_reuse(rd["crystal_id"], run_id=f"gauntlet:{name}", outcome="verified")
    else:
        if rd["route"] == "local_specialist_adapter":
            out["specialist"] = asyncio.run(specialist_attempt(work, name, rd, governor, root))
            out["passed"] = bool(out["specialist"]["dispatched"])
        if not out.get("passed"):
            content = (root / task["target"]).read_text(encoding="utf-8")
            proposal = Proposal(kind="cloud", provider="nvidia_nim", tool_id="gauntlet:fallback_repair",
                                quality_cascade={"skipped": "specialist_refused_or_not_nominated"},
                                signature_material={"task": name}, estimate={"tokens_total": 1200.0})
            decision = governor.admit(Episode(run_id=f"gauntlet:{name}:provider"), proposal)
            call = governor.run_admitted(decision, proposal,
                                         lambda: nim_chat(edit_prompt(task, content, matched["observed_failure"])))
            check = apply_and_verify(root, task, parse_edit(call["text"]), root.parent / "provider-probe")
            out["provider"] = {"model": call["model"], "tokens_total": call["tokens_total"], "check": check,
                               "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id}}
            out["passed"] = bool(check["passed"])
    new_calls = METER.calls[calls_before:]
    out["model_calls"] = [{k: c.get(k) for k in ("provider", "model", "tokens_total", "latency_ms")} for c in new_calls]
    out["tokens_total"] = sum(int(c.get("tokens_total") or 0) for c in new_calls)
    out["wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return out


# --- Part B ----------------------------------------------------------------------------------------------------
def memfd_experiment(work: Path, cold: dict[str, Any], registry: Any, router: Any, governor: Any,
                     promotion: dict[str, Any]) -> dict[str, Any]:
    from app.kernel.compute import crystal_memfd_capsule as cap
    from app.kernel.compute.crystal_economy import LEDGER_POLICY, budget_view, recurrence_value
    from app.kernel.compute.kv_memfd_handoff import HEADER
    from app.kernel.governance.governor_spine import Episode, Proposal

    task = TASKS["cold-billing"]
    root = make_repo(work, "cold-billing", "memfd-billing")
    matched = match(root, task)
    route = router.route_run({"request": {"task_family": FAMILY, "route_similarity": matched["similarity"]}},
                             specialist=SPECIALIST).to_dict()
    if route["route"] != "crystal_replay":
        raise RuntimeError(f"memfd experiment expected a crystal_replay route, got {route['route']}")
    record = registry.get(route["crystal_id"])
    candidate = record["candidate_object"]
    params = {"implementation_target": task["target"], "verify_command": task["verify"]}
    post = {"verify_command": task["verify"], "implementation_target": task["target"], "expect_returncode": 0,
            "tests_run": task["tests_run"], "target_sha256_after": cold["fixed_target_sha256"]}

    def capsule_for(postcondition: dict[str, Any], tag: str) -> tuple[bytes, dict[str, Any], Path]:
        wt = root.parent / f"worktree-{tag}"
        payload = cap.build_payload(candidate, registry_record_digest=record["record_digest"], promotion=promotion,
                                    parameters=params, postcondition=postcondition,
                                    binding={"root": str(root), "worktree": str(wt)})
        return payload, cap.build_manifest(payload, crystal_id=candidate.crystal_id, crystal_digest=candidate.digest), wt

    payload, manifest, worktree = capsule_for(post, "main")
    proposal = Proposal(kind="crystal", crystal_id=candidate.crystal_id, route_decision=route,
                        signature_material={"memfd_capsule": manifest["manifest_digest"]})
    decision = governor.admit(Episode(run_id="gauntlet:memfd-replay"), proposal)
    calls_before = len(METER.calls)

    def run() -> dict[str, Any]:
        fd, seal_stats = cap.seal_capsule(manifest, payload)
        try:
            refused = cap.write_attempt_refused(fd)
            child = cap.handoff_to_replay_child(fd, manifest, admit_token=decision.receipt_hash or decision.receipt_id)
        finally:
            os.close(fd)
        return {"seal": seal_stats, "write_attempt_after_seal": refused, "child": child}

    t0 = time.perf_counter()
    result = governor.run_admitted(decision, proposal, run)
    hydrate_replay_ms = round((time.perf_counter() - t0) * 1000, 3)
    parent_verify = cap.check_postcondition(worktree, post)
    header = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode()
    capsule_bytes = HEADER.pack(len(header)) + header + payload
    baseline = cap.pipe_copy_baseline(capsule_bytes)
    child = result["child"]
    replay_budget = {"model_turns": 0, "tool_calls": child["replay"]["tool_calls"], "tokens_total": 0,
                     "tokens_estimated_turns": 0, "wall_ms": child["child_wall_ms"]}
    value = recurrence_value(budget_view(cold["budget"]), budget_view(replay_budget))
    receipt = {
        "beast_object_type": "crystal_memfd_replay_receipt", "version": "1.0",
        "crystal_id": candidate.crystal_id, "crystal_digest": candidate.digest,
        "registry_record_digest": record["record_digest"], "promotion": promotion,
        "route_decision": {k: route[k] for k in ("route", "similarity", "band", "fingerprint_compatible", "digest")},
        "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id, "receipt_hash": decision.receipt_hash,
                     "admit_token_echoed_by_child": child.get("admit_token_echo") == (decision.receipt_hash or decision.receipt_id),
                     "one_use": True},
        "capsule": {"bytes_total": result["seal"]["capsule_bytes"], "payload_bytes": manifest["payload_bytes"],
                    "header_bytes": result["seal"]["header_bytes"], "payload_sha256": manifest["payload_sha256"],
                    "payload_sha256_child": child["capsule"]["payload_sha256_child"],
                    "manifest_digest": manifest["manifest_digest"],
                    "seals_readback_parent": result["seal"]["seal_names"],
                    "seals_readback_child": child["capsule"]["seal_names"],
                    "seals_value": result["seal"]["seals_readback"],
                    "write_after_seal": result["write_attempt_after_seal"]},
        "copies": {"memfd": {"write_calls_into_memfd": result["seal"]["write_calls"],
                             "bytes_copied_into_memfd": result["seal"]["bytes_written"],
                             "fd_passes_scm_rights": child["fds_received"],
                             "fd_pass_socket_bytes": child["parent_observed"]["fd_pass_bytes_sent"],
                             "payload_bytes_through_socket": 0, "child_mmaps_read_only": child["capsule"]["mmaps"],
                             "child_bytes_read_via_read_syscalls": 0,
                             "transport_copy_bytes": result["seal"]["bytes_written"],
                             "child_userland_parse_copy_bytes": child["capsule"]["payload_bytes_parse_copy"],
                             "end_to_end_ms": child["parent_observed"]["end_to_end_ms"]},
                   "pipe_baseline": baseline,
                   "transport_copy_bytes_saved": baseline["transport_copies_bytes"] - result["seal"]["bytes_written"]},
        "replay": {"process": f"separate child pid {child.get('pid')}",
                   "isolation": child["parent_observed"]["isolation"], "ok": child["ok"],
                   "edit_derived_by_resolve_constant": child["replay"].get("edit"),
                   "steps": [{k: s.get(k) for k in ("opcode", "ms", "returncode", "expect")} for s in child["replay"]["trace"]],
                   "tool_calls": child["replay"]["tool_calls"], "replay_wall_ms": child["replay"]["wall_ms"],
                   "child_wall_ms": child["child_wall_ms"], "hydrate_ms": child["hydrate_ms"],
                   "parent_hydrate_handoff_replay_ms": hydrate_replay_ms,
                   "cold_episode_wall_ms": cold["wall_ms"],
                   "speedup_vs_cold": round(cold["wall_ms"] / max(child["child_wall_ms"], 1e-9), 2)},
        "no_model_calls_proof": {"child_network_counters": {k: child["network"][k] for k in
                                                           ("inet_sockets", "connects", "dns_lookups", "http_sends")},
                                 "child_net_dev_after": child["network"]["net_dev_after"],
                                 "parent_model_calls_during_replay": len(METER.calls) - calls_before,
                                 "model_calls": 0},
        "postcondition": {"expected": post, "child": child["postcondition"], "parent_independent": parent_verify},
        "computation_saved": {"model_calls_avoided": int(cold["budget"]["model_turns"]),
                              "tokens_avoided": int(cold["budget"]["tokens_total"]),
                              "tokens_prompt_avoided": int(cold["budget"]["tokens_prompt"]),
                              "tokens_completion_avoided": int(cold["budget"]["tokens_completion"]),
                              "cold_models": sorted({c["model"] for c in cold["nim_calls"] if not c.get("failed")}),
                              "wall_ms_saved": round(cold["wall_ms"] - child["child_wall_ms"], 3)},
        "pgec_eq6": value,
        "shadow_credit": {"units": value["credit"], **LEDGER_POLICY},
    }
    receipt["receipt_digest"] = sha(receipt)
    return receipt


def negative_controls(work: Path, cold: dict[str, Any], registry: Any, promotion: dict[str, Any]) -> list[dict[str, Any]]:
    from app.kernel.compute import crystal_memfd_capsule as cap

    task = TASKS["cold-billing"]
    record = registry.get(next(iter([cold["crystal_id"]])))
    candidate = record["candidate_object"]
    out = []
    for label in ("tampered_payload", "unsealed_memfd", "wrong_postcondition"):
        root = make_repo(work, "cold-billing", f"neg-{label}")
        post = {"verify_command": task["verify"], "implementation_target": task["target"], "expect_returncode": 0,
                "tests_run": task["tests_run"],
                "target_sha256_after": "sha256:" + "0" * 64 if label == "wrong_postcondition" else cold["fixed_target_sha256"]}
        payload = cap.build_payload(candidate, registry_record_digest=record["record_digest"], promotion=promotion,
                                    parameters={"implementation_target": task["target"], "verify_command": task["verify"]},
                                    postcondition=post, binding={"root": str(root), "worktree": str(root.parent / "wt")})
        manifest = cap.build_manifest(payload, crystal_id=candidate.crystal_id, crystal_digest=candidate.digest)
        body = payload.replace(b'"tests_run":2', b'"tests_run":3', 1) if label == "tampered_payload" else payload
        fd, _ = cap.seal_capsule(manifest, body, seal=label != "unsealed_memfd")
        try:
            child = cap.handoff_to_replay_child(fd, manifest, admit_token="negative-control")
        finally:
            os.close(fd)
        failed = [k for k, v in ((child.get("postcondition") or {}).get("checks") or {}).items() if not v]
        reason = child.get("refused") or (f"postcondition_failed:{','.join(failed)}" if failed else "")
        out.append({"control": label, "accepted": child["ok"], "refused": reason,
                    "replay_ran": "replay" in child, "postcondition": child.get("postcondition"),
                    "credit_units": 0.0})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--approve-by", default="", help="operator approving promotion of THIS gauntlet crystal")
    parser.add_argument("--out", default=str(ROOT / "evidence" / "gauntlet-2026-11-16"))
    parser.add_argument("--state", default=str(ROOT / ".beast" / "gauntlets" / "2026-11-16"))
    args = parser.parse_args()
    os.environ.update(FLAGS)  # in-process only

    from app.kernel.compute.adaptive_router import CodingCrystalRouter
    from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalRegistry, replay_candidate
    from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

    out, state = Path(args.out), Path(args.state)
    if state.exists():
        shutil.rmtree(state)
    out.mkdir(parents=True, exist_ok=True)
    work = state / "work"
    work.mkdir(parents=True)
    registry = CodingCrystalRegistry(state / "coding_crystals.sqlite3")
    envelopes = EpisodeEnvelopeStore(state / "episode_envelopes.sqlite3")
    receipt_log = out / "governor_receipts.jsonl"
    if receipt_log.exists():
        receipt_log.unlink()
    governor = ComputeGovernorSpine(receipts=GovernorReceiptLog(receipt_log), enforce=True)
    router = CodingCrystalRouter(registry, envelopes)

    print("[A1] cold episode (live NIM)...", flush=True)
    cold = cold_episode(work, governor, router)
    envelopes.put(cold["envelope"])
    candidate = CodingCrystalExtractor().extract(cold["envelope"], cold["observations"], registry=registry)
    if candidate is None:
        raise SystemExit(f"extractor refused: {registry.negatives(FAMILY)}")
    registry.add_candidate(candidate)
    cold["crystal_id"] = candidate.crystal_id
    print(f"[A2] distilled {candidate.crystal_id}; held-out reproduction...", flush=True)
    heldout_rows: list[dict[str, Any]] = []

    def run_variant(name: str) -> bool:
        row = replay_task(work, name, candidate, tag="heldout")
        heldout_rows.append(row)
        return row["passed"]

    approve = args.approve_by.strip()
    receipt = replay_candidate(registry, candidate, ["heldout-scheduler", "heldout-auth", "heldout-cache"], run_variant,
                               promote=bool(approve), reproduction={"approved_by": approve or None,
                                                                    "source": "gauntlet-2026-11-16"})
    record = registry.get(candidate.crystal_id)
    promotion = {"crystal_id": candidate.crystal_id, "status": record["status"], "approved_by": approve or None,
                 "heldout_receipt": record.get("receipt") or receipt.__dict__, "record_digest": record["record_digest"],
                 "crystal_digest": candidate.digest, "source_envelope_digest": candidate.source_envelope_digest,
                 "promoted_at": time.time()}
    if record["status"] != "promoted":
        (out / "crystal_promotion.json").write_text(json.dumps(promotion, indent=2, default=str))
        print("not promoted (pass --approve-by NAME); stopping before warm/memfd", flush=True)
        return 2
    print("[A3] warm episodes through D9...", flush=True)
    warm = [warm_episode(work, n, router, governor, registry)
            for n in ("warm-ingest", "warm-notify", "near-miss-pricing", "far-parser")]
    print("[B] memfd capsule replay...", flush=True)
    memfd = memfd_experiment(work, cold, registry, router, governor, promotion)
    negatives = negative_controls(work, cold, registry, promotion)
    chain = governor.receipts.verify() if hasattr(governor.receipts, "verify") else None

    cold_public = {k: v for k, v in cold.items() if k not in {"envelope", "observations"}}
    cold_public["envelope_digest"] = cold["envelope"].envelope_digest
    files = {"cold_episode.json": cold_public, "crystal_promotion.json": {**promotion, "heldout_rows": heldout_rows},
             "warm_episodes.json": warm, "memfd_receipt.json": memfd, "negative_controls.json": negatives,
             "model_calls.json": METER.calls}
    summary = {"family": FAMILY, "crystal_id": candidate.crystal_id, "approved_by": approve,
               "cold": {"wall_ms": cold["wall_ms"], "model_turns": cold["budget"]["model_turns"],
                        "tokens_total": cold["budget"]["tokens_total"],
                        "models": [c["model"] for c in cold["nim_calls"]]},
               "warm": [{"task": w["task"], "similarity": w["match"]["similarity"], "route": w["route"]["route"],
                         "passed": w["passed"], "model_calls": len(w["model_calls"]), "tokens_total": w["tokens_total"],
                         "wall_ms": w["wall_ms"]} for w in warm],
               "memfd": {k: memfd[k] for k in ("capsule", "computation_saved", "pgec_eq6", "shadow_credit")},
               "negative_controls": [{k: n[k] for k in ("control", "accepted", "refused")} for n in negatives],
               "governor_chain": getattr(chain, "__dict__", chain), "receipt_digests": {}}
    for fname, body in files.items():
        raw = json.dumps(body, indent=2, sort_keys=True, default=str)
        (out / fname).write_text(raw + "\n")
        summary["receipt_digests"][fname] = sha(raw.encode())
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    key = os.environ.get("NVIDIA_API_KEY", "")
    if key and any(key in p.read_text() for p in out.glob("*.json*")):
        raise SystemExit("secret material found in evidence; aborting (files left for inspection)")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
