#!/usr/bin/env python3
"""Large crystallization gauntlet: 6 task families, NIM (Nemotron + DeepSeek + substitute) and 3 Ollama models,
D9 router + Governor + verifiers, family crystals, a lattice composite selected on a fresh chained workload, sealed
memfd capsule replay per crystal, and a before/after benchmark of the Ollama specialist crux fix.

State: .beast/gauntlets/2026-11-16-large (isolated registry). Evidence: evidence/gauntlet-2026-11-16-large.
All BEAST_* flags in-process only; keys loaded by name via SecretVault and never written; credits shadow-only.
Promotion only with --approve-by NAME, into the isolated gauntlet registry.
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
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gauntlet_large_tasks import FAMILY_ORDER, PREFIX, all_tasks, fresh_lattice_tasks  # noqa: E402

FLAGS = {"BEAST_ADAPTIVE_ROUTER": "1", "BEAST_GOVERNOR_ENFORCE": "1", "BEAST_SWARM_SPECIALIST": "1",
         "BEAST_CRYSTAL_CAPSULE": "1", "BEAST_FAMILY_CRYSTALS": "1", "BEAST_SWARM_SPECIALIST_MODEL": "qwen3:4b",
         "BEAST_QUALITY_CASCADE_SKIP": "gauntlet-2026-11-16-large:unittest-verifier-is-the-gate"}
SPECIALIST_MODEL = "qwen3:4b"
OLLAMA_MODELS = ("qwen3:4b", "granite3.3:2b", "granite3.2:2b")
PROVIDERS = {
    "nemotron": {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "max_tokens": 2048, "timeout": 90,
                 "extra": {"chat_template_kwargs": {"enable_thinking": False}}, "reasoning": "enable_thinking=False"},
    "deepseek": {"model": "deepseek-ai/deepseek-v4.1-flash", "max_tokens": 4096, "timeout": 75,
                 "extra": {"chat_template_kwargs": {"thinking": False}},
                 "reasoning": "thinking=False; <think> stripped; 4096-token budget for R1-style reasoning"},
    "gpt-oss": {"model": "openai/gpt-oss-20b", "max_tokens": 4096, "timeout": 90, "extra": {"reasoning_effort": "low"},
                "reasoning": "reasoning_effort=low; reasoning_content kept out of the edit; 4096 budget"},
}
BREAKER = {"deepseek": 0, "gpt-oss": 0, "nemotron": 0}
TASKS = all_tasks()
FEEDBACK_OUTPUT = False  # follow-up runs feed the post-edit test output back into the repair turn


def sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class Meter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.context: dict[str, str] = {}

    def add(self, row: dict[str, Any]) -> None:
        self.calls.append({**self.context, **row, "at": time.time()})


METER = Meter()


def specialist_ref(model: str) -> dict[str, Any]:
    return {"execution_mode": "local_specialist_adapter", "model_ref": f"ollama://{model}", "boundary_checks_passed": True}


# -- repos -----------------------------------------------------------------------------------------------------------
def make_repo(base: Path, name: str, label: str = "") -> Path:
    root = base / (label or name) / "repo"
    if root.parent.exists():
        shutil.rmtree(root.parent)
    for rel, text in TASKS[name]["files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def context_files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".json"} and not p.name.startswith("test_") and "__pycache__" not in p.parts
            and p.stat().st_size > 0}


def apply_and_verify(root: Path, name: str, edits: list[dict[str, str]] | None, wt: Path) -> dict[str, Any]:
    from app.kernel.compute.family_crystals import apply_plan, run_verify

    task = TASKS[name]
    if wt.exists():
        shutil.rmtree(wt)
    shutil.copytree(root, wt)
    if not edits:
        return {"applied": False, "passed": False, "reason": "no_parseable_edit"}
    if any(Path(e["path"]).name.startswith("test_") for e in edits):
        return {"applied": False, "passed": False, "reason": "edit_touches_tests"}
    from app.kernel.compute.structured_edit import degenerate_edit

    stubbed = next((r for r in (degenerate_edit(e) for e in edits) if r), None)
    if stubbed:
        return {"applied": False, "passed": False, "reason": stubbed}
    try:
        changed = apply_plan(wt, {"edits": edits})
    except (PermissionError, KeyError, OSError) as exc:
        detail = str(exc)
        return {"applied": False, "passed": False, "reason": f"edit_not_applicable:{detail}"[:200],
                "output_tail": detail[-1500:]}
    result = run_verify(task["verify"], wt)
    return {"applied": True, "changed": changed, "returncode": result["returncode"], "tests_run": result["tests_run"],
            "passed": result["returncode"] == 0 and result["tests_run"] == task["tests_run"], "verify_ms": result["ms"],
            "reason": "" if result["returncode"] == 0 else "tests_still_failing",
            "output_tail": "" if result["returncode"] == 0 else result["output"][-700:]}


def hidden_check(wt: Path, name: str) -> dict[str, Any]:
    """Independent intent check in a fresh copy and separate process; never shown to models or resolvers."""
    from app.kernel.compute.family_crystals import run_verify, tree_digest

    task = TASKS[name]
    with tempfile.TemporaryDirectory(prefix="beast-hidden-") as tmp:
        copy = Path(tmp) / "c"
        shutil.copytree(wt, copy)
        digest_before = sha(tree_digest(copy))
        visible = run_verify(task["verify"], copy)
        for rel, text in task["hidden"].items():
            (copy / rel).write_text(text, encoding="utf-8")
        hidden = run_verify(task["hidden_verify"], copy)
    return {"visible_rc": visible["returncode"], "hidden_rc": hidden["returncode"], "tree_digest": digest_before,
            "passed": visible["returncode"] == 0 and hidden["returncode"] == 0}


# -- providers (NIM) ---------------------------------------------------------------------------------------------------
_GOVERNED: dict[str, Any] = {}


def governed_provider_chat(name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Thin shim: the same NIM call through the ONE governed client (stream, schema-forced, breaker, receipts).

    Acceptance stays with the gauntlet's own apply_and_verify; here the client only requires a schema-valid
    edits object, so the verifier passes through.
    """
    from app.kernel.compute.governed_client import Candidate, GovernedModelClient, NIM_BASE
    from app.kernel.compute.structured_edit import EDITS_SCHEMA
    from app.kernel.security.secret_vault import SecretVault

    SecretVault().load(override=False)
    cfg = PROVIDERS[name]
    client = _GOVERNED.get(name)
    if client is None:
        client = GovernedModelClient([Candidate(provider="nim", model=cfg["model"], kind="nim", base_url=NIM_BASE,
                                                key_env="NVIDIA_API_KEY", max_tokens=cfg["max_tokens"],
                                                timeout_s=cfg["timeout"])], use_scorecard=False, max_attempts=1)
        _GOVERNED[name] = client
    res = asyncio.run(client.complete(family="gauntlet", messages=messages, schema=EDITS_SCHEMA,
                                      verify=lambda value: {"passed": True, "reason": "gauntlet_verifier_decides"},
                                      run_id=f"gauntlet:{name}:{time.time():.0f}"))
    call = res.calls[-1] if res.calls else None
    text = json.dumps(res.value) if res.accepted else ""
    row = {"provider": f"nim:{name}", "model": cfg["model"], "status": call.status if call else "no_call",
           "latency_ms": round(call.latency_ms, 3) if call else 0.0, "tokens_prompt": call.tokens_prompt if call else 0,
           "tokens_completion": call.tokens_completion if call else 0,
           "tokens_total": (call.tokens_prompt + call.tokens_completion) if call else 0, "governed": True,
           "early_stop": bool(call and call.early_stop), "dialect": call.dialect if call else "",
           "response_sha256": sha(text.encode()), "response_text": text[:1500], "failed": not res.accepted,
           "billable": bool(call and call.status not in {"skipped_circuit_open", "refused_governor"})}
    METER.add(row)
    return {**row, "text": text}


def provider_chat(name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    import re

    import httpx

    from app.kernel.security.secret_vault import SecretVault

    if os.environ.get("BEAST_GOVERNED_INTERCEPTION", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return governed_provider_chat(name, messages)
    cfg = PROVIDERS[name]
    if BREAKER.get(name, 0) >= 2:
        row = {"provider": f"nim:{name}", "model": cfg["model"], "status": "circuit_open", "tokens_total": 0,
               "latency_ms": 0.0, "failed": True, "billable": False}
        METER.add(row)
        return {**row, "text": ""}
    SecretVault().load(override=False)
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY not loaded")
    started = time.perf_counter()
    body: dict[str, Any] = {"model": cfg["model"], "messages": messages, "temperature": 0, "max_tokens": cfg["max_tokens"],
                            "stream": False, **cfg["extra"]}
    try:
        response = _egress.post(httpx, "gauntlet_large", "https://integrate.api.nvidia.com/v1/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {key}"}, timeout=cfg["timeout"])
        if response.status_code == 400 and cfg["extra"]:  # option not accepted by this model: retry plain once
            body = {k: v for k, v in body.items() if k not in cfg["extra"]}
            response = _egress.post(httpx, "gauntlet_large", "https://integrate.api.nvidia.com/v1/chat/completions", json=body,
                                  headers={"Authorization": f"Bearer {key}"}, timeout=cfg["timeout"])
    except httpx.HTTPError as exc:
        BREAKER[name] = BREAKER.get(name, 0) + 1
        row = {"provider": f"nim:{name}", "model": cfg["model"], "status": type(exc).__name__, "tokens_total": 0,
               "latency_ms": round((time.perf_counter() - started) * 1000, 3), "failed": True, "billable": "unknown"}
        METER.add(row)
        return {**row, "text": ""}
    latency = round((time.perf_counter() - started) * 1000, 3)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    raw = str(message.get("content") or "")
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    usage = data.get("usage") or {}
    reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    failed = response.status_code >= 400
    BREAKER[name] = BREAKER.get(name, 0) + 1 if failed else 0
    row = {"provider": f"nim:{name}", "model": cfg["model"], "status": response.status_code, "latency_ms": latency,
           "tokens_prompt": int(usage.get("prompt_tokens") or 0), "tokens_completion": int(usage.get("completion_tokens") or 0),
           "tokens_total": int(usage.get("total_tokens") or 0), "tokens_reasoning": reasoning,
           "finish_reason": str(choice.get("finish_reason") or ""), "reasoning_in_content": "<think>" in raw,
           "reasoning_budget_exhausted": not text and choice.get("finish_reason") == "length",
           "response_sha256": sha(text.encode()), "response_text": text[:1500], "failed": failed, "billable": not failed}
    METER.add(row)
    return {**row, "text": text}


def provider_solve(name: str, root: Path, task_name: str, governor: Any, wt: Path, *, attempts: int = 2,
                   reason: str = "provider_tier") -> dict[str, Any]:
    from app.kernel.compute.family_crystals import run_verify
    from app.kernel.compute.structured_edit import edits_messages, parse_edits, repair_message
    from app.kernel.governance.governor_spine import Episode, Proposal

    task = TASKS[task_name]
    failure = run_verify(task["verify"], root)["output"]
    messages = edits_messages(context_files(root), failure, target=task["target"])
    calls, tries = [], []
    for attempt in range(attempts):
        proposal = Proposal(kind="cloud", provider="nvidia_nim", tool_id=f"gauntlet-large:{name}",
                            quality_cascade={"skipped": reason}, signature_material={"task": task_name, "a": attempt},
                            estimate={"tokens_total": float(PROVIDERS[name]["max_tokens"])})
        decision = governor.admit(Episode(run_id=f"large:{task_name}:{name}:{attempt}"), proposal)
        if decision.outcome != "admit":
            tries.append({"refused": f"governor_{decision.outcome}"})
            break
        call = governor.run_admitted(decision, proposal, lambda m=list(messages): provider_chat(name, m))
        calls.append({k: v for k, v in call.items() if k not in {"text", "response_text"}} | {"governor": decision.receipt_id})
        edits = parse_edits(call["text"], default_path=task["target"])
        check = apply_and_verify(root, task_name, edits, wt)
        tries.append({"edits": edits, "check": check})
        if check["passed"] or call.get("status") == "circuit_open" or call.get("failed"):
            break
        feedback = (check.get("reason") or "tests_failed") + (
            f"; test output after applying your edits:\n{check['output_tail']}" if FEEDBACK_OUTPUT and check.get("output_tail") else "")
        messages = [*messages, {"role": "assistant", "content": call["text"][:1200] or "(empty)"},
                    repair_message(call["text"], feedback)]
    ok = bool(tries and tries[-1].get("check", {}).get("passed"))
    return {"provider": name, "model": PROVIDERS[name]["model"], "passed": ok, "calls": calls, "attempts": tries,
            "tokens_total": sum(int(c.get("tokens_total") or 0) for c in calls),
            "latency_ms": round(sum(float(c.get("latency_ms") or 0) for c in calls), 3),
            "edits": tries[-1].get("edits") if ok else None, "worktree": str(wt) if ok else ""}


# -- specialist (Ollama) ---------------------------------------------------------------------------------------------
def specialist_solve(model: str, root: Path, task_name: str, governor: Any, wt: Path, *, config: str = "after",
                     route: dict[str, Any] | None = None) -> dict[str, Any]:
    from gauntlet_memfd_replay import edit_prompt

    from app.kernel.agents.swarm_specialist import OllamaSwarmRunner, SwarmSpecialistDispatch
    from app.kernel.compute.adaptive_router import AdaptiveRouter
    from app.kernel.compute.family_crystals import run_verify
    from app.kernel.compute.structured_edit import EDITS_SCHEMA, edits_messages, parse_edit, parse_edits

    task = TASKS[task_name]
    failure = run_verify(task["verify"], root)["output"]
    checks: list[dict[str, Any]] = []

    def verifier(text: str, _ir: Any) -> tuple[bool, str]:
        if config == "before":
            single = parse_edit(text)
            edits = [{"path": task["target"], **single}] if single else None
        else:
            edits = parse_edits(text, default_path=task["target"])
        check = apply_and_verify(root, task_name, edits, wt)
        checks.append({"edits": edits, "check": check})
        return bool(check["passed"]), "unittest_postcondition_passed" if check["passed"] else check.get("reason", "tests_failed")

    if config == "before":  # exactly the 2026-11-16 small-gauntlet configuration
        content = (root / task["target"]).read_text(encoding="utf-8")
        ir = SimpleNamespace(messages=edit_prompt(task, content, failure), max_tokens=1024,
                             metadata={"run_id": f"large:{task_name}:{model}:before"})
    else:
        ir = SimpleNamespace(messages=edits_messages(context_files(root), failure, target=task["target"]), max_tokens=512,
                             metadata={"run_id": f"large:{task_name}:{model}:after", "response_schema": EDITS_SCHEMA,
                                       "repair_retries": 2})
    route = route or AdaptiveRouter().route(similarity=0.85, specialist=specialist_ref(model)).to_dict()
    runner = OllamaSwarmRunner(timeout=300)
    original = runner.generate

    async def metered(**kwargs: Any) -> dict[str, Any]:
        try:
            out = await original(**kwargs)
        except Exception as exc:
            METER.add({"provider": "ollama", "model": kwargs.get("model"), "status": type(exc).__name__, "tokens_total": 0,
                       "failed": True, "config": config})
            raise
        METER.add({"provider": "ollama", "model": out["model"], "latency_ms": out["latency_ms"], "config": config,
                   "tokens_prompt": out["usage"]["prompt_tokens"], "tokens_completion": out["usage"]["completion_tokens"],
                   "tokens_total": out["usage"]["prompt_tokens"] + out["usage"]["completion_tokens"],
                   "done_reason": out.get("done_reason"), "structured": "format" in kwargs,
                   "response_sha256": sha(out["text"].encode()), "response_text": out["text"][:1500]})
        return out

    runner.generate = metered  # type: ignore[method-assign]
    started = time.perf_counter()
    outcome = asyncio.run(SwarmSpecialistDispatch(runner=runner, governor=governor, verifiers=[verifier])
                          .dispatch(ir, route, run_id=f"large:{task_name}:{model}:{config}"))
    receipt = outcome.receipt
    return {"model": model, "config": config, "passed": bool(outcome.dispatched), "reason": outcome.reason,
            "attempts": len(receipt.get("attempts") or [1 if receipt.get("generated") else 0]),
            "usage": receipt.get("usage"), "governor": receipt.get("governor_receipt"),
            "tokens_total": sum((receipt.get("usage") or {}).values()) if isinstance(receipt.get("usage"), dict) else 0,
            "wall_ms": round((time.perf_counter() - started) * 1000, 3), "checks": checks,
            "edits": checks[-1]["edits"] if outcome.dispatched and checks else None,
            "worktree": str(wt) if outcome.dispatched else ""}


# -- envelopes / budgets -----------------------------------------------------------------------------------------------
def make_envelope(run_id: str, task_name: str, provider: str, model: str, budget: dict[str, Any], edits: list[dict[str, str]],
                  fail_out: str, pass_out: str) -> Any:
    from app.kernel.sensorium.episode_envelope import ENVELOPE_SCHEMA, EpisodeEnvelope

    task = TASKS[task_name]
    steps = []
    for tool, src, result, path, rc in (("workspace.read_range", "runtime", {"target": task["target"]}, task["target"], None),
                                        ("worktree.bind", "runtime", {"worktree": "bound"}, "", None),
                                        ("worktree.verify", "runtime", {"stderr": fail_out[-400:]}, "", 1),
                                        ("worktree.replace_exact", "model", {"edits": len(edits)}, task["target"], None),
                                        ("worktree.verify", "runtime", {"stderr": pass_out[-400:]}, "", 0)):
        steps.append({"index": len(steps), "tool_id": tool, "status": "completed", "source": src,
                      "arguments_digest": sha(edits if src == "model" else {}), "safe_arguments": {"path": path} if path else {},
                      "result_digest": sha({"r": result, "i": len(steps)}), "returncode": rc, "duration_ms": 0.0})
    return EpisodeEnvelope(schema=ENVELOPE_SCHEMA, run_id=run_id, origin="gauntlet_large_cold_episode",
                           workspace_digest=sha({k: sha(v.encode()) for k, v in task["files"].items()}),
                           objective_digest=sha(f"{task['family']}:{task['target']}".encode()), task_family=task["family"],
                           mode="agent", provider=provider, model=model, state="verified", implementation_target=task["target"],
                           steps=tuple(steps), verification={"present": True, "passed": True, "failures_before_pass": 1,
                                                             "final_returncode": 0, "verify_steps": 2},
                           negative_evidence=({"index": 2, "tool_id": "worktree.verify", "kind": "verification_failed",
                                               "result_digest": steps[2]["result_digest"]},),
                           budget=budget, event_chain_head=sha(steps)).sealed()


def budget_for(calls: list[dict[str, Any]], tool_calls: int, wall_ms: float) -> dict[str, Any]:
    from app.kernel.sensorium.episode_envelope import BUDGET_KEYS

    ok = [c for c in calls if not c.get("failed")]
    return dict.fromkeys(BUDGET_KEYS, 0.0) | {
        "model_turns": float(len(ok)), "tokens_prompt": float(sum(int(c.get("tokens_prompt") or 0) for c in ok)),
        "tokens_completion": float(sum(int(c.get("tokens_completion") or 0) for c in ok)),
        "tokens_total": float(sum(int(c.get("tokens_total") or 0) for c in ok)), "tokens_estimated_turns": 0.0,
        "tool_calls": float(tool_calls), "tool_calls_model": float(len(ok)), "tool_calls_runtime": float(max(0, tool_calls - len(ok))),
        "wall_ms": wall_ms}


# -- the pipeline --------------------------------------------------------------------------------------------------------
class Gauntlet:
    def __init__(self, state: Path, out: Path, approve: str, receipts: str = "governor_receipts.jsonl"):
        from app.kernel.compute.family_crystals import FamilyRegistry
        from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
        from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

        self.state, self.out, self.approve = state, out, approve
        self.work = state / "work"
        self.work.mkdir(parents=True, exist_ok=True)
        self.registry = FamilyRegistry(state / "family_crystals.sqlite3")
        self.envelopes = EpisodeEnvelopeStore(state / "episode_envelopes.sqlite3")
        log = out / receipts
        if log.exists():
            log.unlink()
        self.governor = ComputeGovernorSpine(receipts=GovernorReceiptLog(log), enforce=True)
        self.cold_budgets: dict[str, dict[str, Any]] = {}
        self.crystal_of: dict[str, str] = {}
        self.records: list[dict[str, Any]] = []

    def crystal(self, crystal_id: str) -> Any:
        return self.registry.get(crystal_id)["crystal_object"]

    def solve(self, name: str, phase: str, *, label: str = "") -> dict[str, Any]:
        from app.kernel.compute import family_crystals as fc
        from app.kernel.governance.governor_spine import Episode, Proposal

        METER.context = {"task": name, "phase": phase}
        task = TASKS[name]
        started = time.perf_counter()
        calls_before = len(METER.calls)
        root = make_repo(self.work, name, label or f"{name}-{phase}")
        observed = fc.run_verify(task["verify"], root)
        ranked = fc.discover(self.registry, root, task, observed)
        best = ranked[0] if ranked else None
        best_obj = self.crystal(best["crystal_id"]) if best else None
        decision = fc.route(self.registry, best_obj, best["similarity"] if best else 0.0, specialist_ref(SPECIALIST_MODEL))
        rd = decision.to_dict()
        rec: dict[str, Any] = {"task": name, "family": task["family"], "role": task["role"], "phase": phase,
                               "observed_failures": observed["failures"], "candidates": ranked[:6], "route": rd,
                               "tiers": [], "accepted_by": None}
        solution: Path | None = None
        edits = None
        if rd["route"] == "crystal_replay":
            crystal = best_obj
            proposal = Proposal(kind="crystal", crystal_id=crystal.crystal_id, route_decision=rd,
                                signature_material={"task": name, "phase": phase})
            admit = self.governor.admit(Episode(run_id=f"large:{name}:{phase}:crystal"), proposal)
            tier = {"tier": "lattice" if crystal.component_ids else "crystal", "crystal_id": crystal.crystal_id,
                    "governor": {"outcome": admit.outcome, "receipt_id": admit.receipt_id}}
            if admit.outcome == "admit":
                if crystal.component_ids:
                    result = self.governor.run_admitted(admit, proposal, lambda: self.lattice_capsules(crystal, root, name, admit))
                    tier.update(result)
                    ok = result["passed"]
                    final = Path(result["final_worktree"]) if ok else None
                else:
                    wt = root.parent / "crystal-wt"
                    result = self.governor.run_admitted(admit, proposal, lambda: fc.replay_family(
                        crystal, {"implementation_target": task["target"], "verify_command": task["verify"]}, root, wt))
                    check = fc.run_verify(task["verify"], wt) if result["ok"] else None
                    ok = bool(result["ok"] and check and check["returncode"] == 0 and check["tests_run"] == task["tests_run"])
                    tier.update(replay={k: result.get(k) for k in ("ok", "reason", "tool_calls", "wall_ms", "changed")},
                                refused_at=None if ok else (result.get("trace") or [{}])[-1])
                    final = wt if ok else None
                tier["passed"] = ok
                if ok:
                    solution, rec["accepted_by"] = final, tier["tier"]
                    self.registry.record_reuse(crystal.crystal_id, run_id=f"large:{name}:{phase}", outcome="verified")
                else:
                    self.registry.record_negative(task["family"], kind="crystal_postcondition_refused", crystal_id=crystal.crystal_id)
            rec["tiers"].append(tier)
        elif rd["route"] == "local_specialist_adapter":
            res = specialist_solve(SPECIALIST_MODEL, root, name, self.governor, root.parent / "specialist-wt", route=rd)
            rec["tiers"].append({"tier": "specialist", **{k: v for k, v in res.items() if k not in {"checks"}},
                                 "last_check": (res["checks"] or [{}])[-1].get("check")})
            if res["passed"]:
                solution, edits, rec["accepted_by"] = Path(res["worktree"]), res["edits"], f"specialist:{SPECIALIST_MODEL}"
        if solution is None:
            for provider in ("nemotron", "deepseek"):
                res = provider_solve(provider, root, name, self.governor, root.parent / f"{provider}-wt",
                                     reason="fallback_after_" + (rec["tiers"][-1]["tier"] if rec["tiers"] else "router"))
                rec["tiers"].append({"tier": f"provider:{provider}", **{k: v for k, v in res.items() if k != "attempts"},
                                     "last_check": (res["attempts"] or [{}])[-1].get("check")})
                if res["passed"]:
                    solution, edits, rec["accepted_by"] = Path(res["worktree"]), res["edits"], f"provider:{provider}"
                    break
        new_calls = METER.calls[calls_before:]
        rec["model_calls"] = len([c for c in new_calls if c.get("status") != "circuit_open"])
        rec["tokens_total"] = sum(int(c.get("tokens_total") or 0) for c in new_calls)
        rec["wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        rec["passed"] = solution is not None
        rec["independent"] = hidden_check(solution, name) if solution else None
        rec["false_accept"] = bool(solution is not None and not rec["independent"]["passed"])
        rec["_solution"], rec["_edits"], rec["_root"], rec["_calls"] = solution, edits, root, new_calls
        self.records.append(rec)
        print(f"  {phase:8} {name:24} sim={best['similarity'] if best else 0:.2f} route={rd['route']:24} "
              f"by={rec['accepted_by']} calls={rec['model_calls']} tok={rec['tokens_total']} "
              f"ok={rec['passed']} FA={rec['false_accept']} {rec['wall_ms']:.0f}ms", flush=True)
        return rec

    # -- cold -> distil -> held-out -> promote ----------------------------------------------------------------------
    def learn_family(self, family: str) -> dict[str, Any]:
        from app.kernel.compute import family_crystals as fc
        from app.kernel.compute.heldout_replay import HeldOutReplayGate

        name = f"{PREFIX[family]}-cold"
        rec = self.solve(name, "cold")
        out: dict[str, Any] = {"family": family, "cold": public(rec)}
        if not rec["passed"] or rec["accepted_by"] in {"crystal", "lattice"}:
            out["distilled"] = None
            out["reason"] = "solved_by_existing_crystal" if rec["passed"] else "cold_unsolved"
            return out
        calls = [c for c in rec["_calls"] if c.get("status") != "circuit_open"]
        budget = budget_for(calls, tool_calls=5, wall_ms=rec["wall_ms"])
        self.cold_budgets[family] = budget
        model_call = next((c for c in reversed(calls) if not c.get("failed")), {})
        env = make_envelope(f"large:{name}:{int(time.time())}", name, str(model_call.get("provider")), str(model_call.get("model")),
                            budget, rec["_edits"] or [], "fail", "pass")
        self.envelopes.put(env)
        task = TASKS[name]
        params = {"implementation_target": task["target"], "verify_command": task["verify"]}
        crystal, info = fc.extract_family(family, env, root=rec["_root"], parameters=params, model_worktree=rec["_solution"],
                                          scratch=rec["_root"].parent / "distil")
        out["extraction"] = {k: v for k, v in info.items() if k != "replay"}
        if crystal is None:
            self.registry.record_negative(family, kind=info["refused"], evidence_digest=env.envelope_digest)
            out["distilled"] = None
            return out
        self.registry.add_candidate(crystal, provenance={"cold_task": name, "accepted_by": rec["accepted_by"]})
        rows = []

        def run_variant(variant: str) -> bool:
            METER.context = {"task": variant, "phase": "heldout"}
            before = len(METER.calls)
            root = make_repo(self.work, variant, f"{variant}-heldout")
            t = TASKS[variant]
            res = fc.replay_family(crystal, {"implementation_target": t["target"], "verify_command": t["verify"]},
                                   root, root.parent / "wt")
            ind = hidden_check(root.parent / "wt", variant) if res["ok"] else {"passed": False}
            rows.append({"task": variant, "ok": res["ok"], "independent": ind, "wall_ms": res.get("wall_ms"),
                         "model_calls": len(METER.calls) - before, "reason": res.get("reason")})
            return bool(res["ok"] and ind["passed"])

        heldout = [f"{PREFIX[family]}-h{i}" for i in (1, 2, 3)]
        receipt = HeldOutReplayGate().evaluate(crystal.crystal_id, heldout, run_variant, minimum_successes=3,
                                               envelope_digest=env.envelope_digest,
                                               reproduction={"source": "gauntlet-2026-11-16-large", "approved_by": self.approve})
        out["heldout"] = rows
        if receipt.promoted and self.approve:
            record = self.registry.promote(crystal.crystal_id, receipt, approved_by=self.approve)
            self.crystal_of[family] = crystal.crystal_id
            out["promotion"] = {"status": record["status"], "record_digest": record["record_digest"], **record["promotion"]}
        out["distilled"] = crystal.crystal_id
        out["crystal_digest"] = crystal.digest
        return out

    def learn_composite(self, families: tuple[str, str]) -> dict[str, Any]:
        from app.kernel.compute import family_crystals as fc
        from app.kernel.compute.heldout_replay import HeldOutReplayGate

        if not all(f in self.crystal_of for f in families):
            return {"composite": None, "reason": "children_not_promoted", "families": families}
        children = [self.crystal(self.crystal_of[f]) for f in families]
        comp = fc.compose(children, source_run_id="gauntlet-2026-11-16-large:lattice")
        self.registry.add_candidate(comp, provenance={"children": [c.crystal_id for c in children]})
        rows = []

        def run_variant(variant: str) -> bool:
            root = make_repo(self.work, variant, f"{variant}-heldout")
            t = TASKS[variant]
            res = fc.replay_family(comp, {"implementation_target": t["target"], "verify_command": t["verify"]}, root,
                                   root.parent / "wt")
            ind = hidden_check(root.parent / "wt", variant) if res["ok"] else {"passed": False}
            rows.append({"task": variant, "ok": res["ok"], "independent": ind, "wall_ms": res.get("wall_ms")})
            return bool(res["ok"] and ind["passed"])

        receipt = HeldOutReplayGate().evaluate(comp.crystal_id, ["dual-h1", "dual-h2", "dual-h3"], run_variant,
                                               minimum_successes=3, envelope_digest=comp.source_envelope_digest,
                                               reproduction={"lattice": True, "approved_by": self.approve})
        out = {"composite": comp.crystal_id, "children": list(comp.component_ids), "families": list(families),
               "authority_A_L": list(comp.authority), "heldout": rows, "digest": comp.digest}
        if receipt.promoted and self.approve:
            record = self.registry.promote(comp.crystal_id, receipt, approved_by=self.approve)
            out["promotion"] = {"status": record["status"], "record_digest": record["record_digest"], **record["promotion"]}
            self.crystal_of["lattice"] = comp.crystal_id
        return out

    # -- capsules ---------------------------------------------------------------------------------------------------
    def capsule_replay(self, crystal: Any, root: Path, wt: Path, name: str, post: dict[str, Any], admit_token: str,
                       stage: dict[str, Any] | None = None, *, tamper: str = "") -> dict[str, Any]:
        from app.kernel.compute import crystal_memfd_capsule as cap
        from app.kernel.compute.kv_memfd_handoff import HEADER

        task = TASKS[name]
        record = self.registry.get(crystal.crystal_id)
        params = {"implementation_target": task["target"], "verify_command": task["verify"]}
        if stage:
            params["lattice_stage"] = stage
        payload = cap.build_payload(crystal, registry_record_digest=record["record_digest"], promotion=record.get("promotion") or {},
                                    parameters=params, postcondition=post, binding={"root": str(root), "worktree": str(wt)})
        manifest = cap.build_manifest(payload, crystal_id=crystal.crystal_id, crystal_digest=crystal.digest)
        body = payload.replace(b'"tests_run":2', b'"tests_run":3', 1) if tamper == "tampered_payload" else payload
        t0 = time.perf_counter()
        fd, seal = cap.seal_capsule(manifest, body, seal=tamper != "unsealed_memfd")
        try:
            refused = cap.write_attempt_refused(fd) if tamper != "unsealed_memfd" else {"refused": False}
            child = cap.handoff_to_replay_child(fd, manifest, admit_token=admit_token)
        finally:
            os.close(fd)
        header = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode()
        capsule = HEADER.pack(len(header)) + header + payload
        failed = [k for k, v in ((child.get("postcondition") or {}).get("checks") or {}).items() if not v]
        return {
            "crystal_id": crystal.crystal_id, "stage": stage and {"composite_id": stage["composite"]["crystal_id"], "index": stage["index"]},
            "ok": bool(child.get("ok")), "refused": child.get("refused") or (f"postcondition_failed:{','.join(failed)}" if failed else ""),
            "capsule": {"bytes_total": seal["capsule_bytes"], "payload_bytes": manifest["payload_bytes"],
                        "payload_sha256": manifest["payload_sha256"], "manifest_digest": manifest["manifest_digest"],
                        "payload_sha256_child": (child.get("capsule") or {}).get("payload_sha256_child"),
                        "seals_value": seal["seals_readback"], "seals_parent": seal["seal_names"],
                        "seals_child": (child.get("capsule") or {}).get("seal_names"), "write_after_seal": refused},
            "copies": {"write_calls_into_memfd": seal["write_calls"], "bytes_copied_into_memfd": seal["bytes_written"],
                       "fd_passes": child.get("fds_received"), "fd_pass_socket_bytes": child["parent_observed"]["fd_pass_bytes_sent"],
                       "payload_bytes_through_socket": 0, "child_mmaps_read_only": (child.get("capsule") or {}).get("mmaps"),
                       "child_read_syscall_bytes": 0, "pipe_baseline_copy_bytes": 2 * len(capsule),
                       "transport_bytes_saved_vs_pipe": 2 * len(capsule) - seal["bytes_written"]},
            "process": {"child_pid": child.get("pid"), "isolation": child["parent_observed"]["isolation"],
                        "admit_token_echoed": child.get("admit_token_echo") == admit_token,
                        "child_wall_ms": child.get("child_wall_ms"), "hydrate_ms": child.get("hydrate_ms"),
                        "parent_end_to_end_ms": round((time.perf_counter() - t0) * 1000, 3)},
            "replay": {"tool_calls": (child.get("replay") or {}).get("tool_calls"), "model_calls": 0,
                       "wall_ms": (child.get("replay") or {}).get("wall_ms"), "changed": (child.get("replay") or {}).get("changed"),
                       "steps": [{k: s.get(k) for k in ("opcode", "expect", "returncode", "failures", "refused", "plan")}
                                 for s in (child.get("replay") or {}).get("trace") or []]},
            "network": {k: (child.get("network") or {}).get(k) for k in ("inet_sockets", "connects", "dns_lookups", "http_sends")}
                       | {"lo_after": ((child.get("network") or {}).get("net_dev_after") or {}).get("lo")},
            "postcondition": child.get("postcondition"),
        }

    def lattice_capsules(self, comp: Any, root: Path, name: str, admit: Any) -> dict[str, Any]:
        """Replay each child, in order, from its own sealed memfd capsule in a separate empty-netns process."""
        task = TASKS[name]
        token = admit.receipt_hash or admit.receipt_id
        stages, src = [], root
        calls_before = len(METER.calls)
        t0 = time.perf_counter()
        for index, child_id in enumerate(comp.component_ids):
            child = self.crystal(child_id)
            last = index == len(comp.component_ids) - 1
            wt = root.parent / f"lattice-stage{index}"
            post = {"verify_command": task["verify"], "implementation_target": task["target"], "tests_run": task["tests_run"],
                    "expect_returncode": 0 if last else 1}
            res = self.capsule_replay(child, src, wt, name, post, token, {"composite": comp.to_dict(), "index": index})
            stages.append(res)
            if not res["ok"]:
                break
            src = wt
        ok = len(stages) == len(comp.component_ids) and all(s["ok"] for s in stages)
        return {"passed": ok, "stages": stages, "final_worktree": str(src), "lattice_wall_ms": round((time.perf_counter() - t0) * 1000, 3),
                "model_calls_during_lattice": len(METER.calls) - calls_before,
                "tool_calls": sum(int(s["replay"]["tool_calls"] or 0) for s in stages)}


def public(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def write(out: Path, name: str, body: Any) -> str:
    raw = json.dumps(body, indent=2, sort_keys=True, default=str)
    (out / name).write_text(raw + "\n")
    return sha(raw.encode())


def h2h(g: Gauntlet, name: str, providers: tuple[str, ...], phase: str) -> dict[str, Any]:
    rows = {}
    for provider in providers:
        METER.context = {"task": name, "phase": phase}
        started = time.perf_counter()
        root = make_repo(g.work, name, f"{name}-{phase}-{provider}")
        res = provider_solve(provider, root, name, g.governor, root.parent / "wt", reason=f"{phase}_cold_baseline")
        res["wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        res["independent"] = hidden_check(Path(res["worktree"]), name) if res["passed"] else None
        res["budget"] = budget_for([c for c in res["calls"] if c.get("status") != "circuit_open"], 5, res["wall_ms"])
        res["reasoning_tokens"] = sum(int(c.get("tokens_reasoning") or 0) for c in res["calls"])
        rows[provider] = res
        print(f"  {phase:8} {name:24} {provider:9} ok={res['passed']} tok={res['tokens_total']} "
              f"lat={res['latency_ms']:.0f}ms calls={len(res['calls'])}", flush=True)
    return rows


def memfd_for(g: Gauntlet, family: str) -> dict[str, Any]:
    from app.kernel.compute import family_crystals as fc
    from app.kernel.compute.crystal_economy import LEDGER_POLICY, budget_view, recurrence_value
    from app.kernel.governance.governor_spine import Episode, Proposal

    crystal = g.crystal(g.crystal_of[family])
    name = f"{PREFIX[family]}-w1"
    task = TASKS[name]
    root = make_repo(g.work, name, f"{name}-memfd")
    ref = root.parent / "reference"
    fc.replay_family(crystal, {"implementation_target": task["target"], "verify_command": task["verify"]}, root, ref)
    pristine, after = fc.tree_digest(root), fc.tree_digest(ref)
    files = {k: v for k, v in after.items() if pristine.get(k) != v}
    post = {"verify_command": task["verify"], "implementation_target": task["target"], "tests_run": task["tests_run"],
            "expect_returncode": 0, "files_sha256_after": files}
    observed = fc.run_verify(task["verify"], root)
    ranked = fc.discover(g.registry, root, task, observed)
    rd = fc.route(g.registry, g.crystal(ranked[0]["crystal_id"]), ranked[0]["similarity"], specialist_ref(SPECIALIST_MODEL)).to_dict()
    if rd["route"] != "crystal_replay" or rd["crystal_id"] != crystal.crystal_id:
        return {"family": family, "task": name, "crystal_id": crystal.crystal_id, "ok": False,
                "refused": f"router did not propose this crystal ({rd['route']}, sim {ranked[0]['similarity']})",
                "candidates": ranked[:3], "capsule": {"bytes_total": 0, "seals_value": 0}, "process": {"child_wall_ms": None},
                "network": {}, "pgec_eq6": None, "shadow_credit": {"units": 0.0}}
    proposal = Proposal(kind="crystal", crystal_id=crystal.crystal_id, route_decision=rd, signature_material={"memfd": name})
    admit = g.governor.admit(Episode(run_id=f"large:memfd:{family}"), proposal)
    before = len(METER.calls)
    res = g.governor.run_admitted(admit, proposal, lambda: g.capsule_replay(
        crystal, root, root.parent / "capsule-wt", name, post, admit.receipt_hash or admit.receipt_id))
    res["parent_independent"] = hidden_check(root.parent / "capsule-wt", name) if res["ok"] else None
    cold = g.cold_budgets.get(family) or {}
    reuse = {"model_turns": 0, "tool_calls": res["replay"]["tool_calls"] or 0, "tokens_total": 0,
             "tokens_estimated_turns": 0, "wall_ms": res["process"]["child_wall_ms"] or 0}
    value = recurrence_value(budget_view(cold), budget_view(reuse)) if cold else None
    res.update(family=family, task=name, route={k: rd[k] for k in ("route", "similarity", "band", "fingerprint_compatible", "digest")},
               governor={"outcome": admit.outcome, "receipt_id": admit.receipt_id, "receipt_hash": admit.receipt_hash},
               parent_model_calls_during_replay=len(METER.calls) - before,
               computation_saved={"model_calls_avoided": int(cold.get("model_turns") or 0),
                                  "tokens_avoided": int(cold.get("tokens_total") or 0),
                                  "wall_ms_saved": round(float(cold.get("wall_ms") or 0) - float(reuse["wall_ms"]), 3)},
               pgec_eq6=value, shadow_credit={"units": value["credit"] if value and res["ok"] else 0.0, **LEDGER_POLICY})
    res["receipt_digest"] = sha(res)
    return res


def lattice_experiment(g: Gauntlet, seed: int) -> dict[str, Any]:
    from app.kernel.compute import family_crystals as fc
    from app.kernel.compute.crystal_economy import LEDGER_POLICY, _scaled, budget_view, recurrence_value

    fresh = fresh_lattice_tasks(seed)
    TASKS.update(fresh)
    names = {t["family"]: n for n, t in fresh.items()}
    dual, single, diff = names["fresh-lattice"], names["fresh-single"], names["fresh-lattice-diff"]
    out: dict[str, Any] = {"seed": seed, "fresh_tasks": {"dual": dual, "single": single, "diff": diff},
                           "fresh_task_digests": {n: sha(TASKS[n]["files"]) for n in (dual, single, diff)},
                           "never_seen": "generated at run time from the seed after distillation, held-out and promotion"}
    print("[L1] cold baseline on the fresh chained task (real model calls, crystals ignored)", flush=True)
    out["cold_baseline"] = h2h(g, dual, ("nemotron", "deepseek"), "lattice-cold")
    comp_id = g.crystal_of.get("lattice")
    print("[L2] pipeline on the fresh chained task (no crystal id handed in)", flush=True)
    rec = g.solve(dual, "lattice")
    tier = rec["tiers"][0] if rec["tiers"] else {}
    selected = rec["route"]["route"] == "crystal_replay" and rec["route"]["crystal_id"] == comp_id and tier.get("tier") == "lattice"
    used = bool(selected and tier.get("passed") and rec["accepted_by"] == "lattice")
    cands = rec["candidates"]
    singles = [c for c in cands if not c["composite"]]
    out["selection"] = {"lattice_id": comp_id, "selected": selected, "used_to_complete": used,
                        "route_decision": rec["route"], "candidates": cands,
                        "why": {
                            "lattice": next((c for c in cands if c["crystal_id"] == comp_id), None),
                            "single_crystals": [{"crystal_id": c["crystal_id"], "family": c["task_family"], "similarity": c["similarity"],
                                                 "missing": [k for k, v in c["features"].items() if not v]} for c in singles],
                            "specialist": "AdaptiveRouter nominates the local specialist only in the structural band "
                                          "(0.80-0.95) or when no fingerprint-compatible crystal exists; the lattice scored "
                                          f"{cands[0]['similarity'] if cands else 0} with fingerprints compatible",
                            "provider": "provider_fallback only below 0.80 or after a verifier refusal; the measured cold "
                                        "baseline below shows what it would have cost"}}
    if not used:
        out["selection"]["failure"] = "lattice not selected/used: see route_decision and candidates"
    out["pipeline"] = public(rec)
    if used:
        cold = out["cold_baseline"]["nemotron"]["budget"]
        lattice_budget = {"model_turns": 0, "tool_calls": tier["tool_calls"], "tokens_total": 0, "tokens_estimated_turns": 0,
                          "wall_ms": tier["lattice_wall_ms"]}
        v_l = recurrence_value(budget_view(cold), budget_view(lattice_budget))
        comp = g.crystal(comp_id)
        steps = {cid: len(g.crystal(cid).steps) for cid in comp.component_ids}
        total = sum(steps.values())
        children = []
        for cid in comp.component_ids:
            fam = g.crystal(cid).task_family
            v = recurrence_value(budget_view(g.cold_budgets[fam]), _scaled(budget_view(lattice_budget), steps[cid] / total))
            children.append({"crystal_id": cid, "family": fam, "share": round(steps[cid] / total, 6), "recurrence_value": v,
                             "attribution": "child_measured_baseline_minus_step_proportional_reuse_cost"})
        gross = [max(0.0, c["recurrence_value"]["v_k"]) for c in children]
        vl = max(0.0, v_l["v_k"])
        scaled = sum(gross) > vl
        surplus = 0.0 if scaled else max(0.0, vl - sum(gross))
        final = Path(tier["final_worktree"])
        out["receipt"] = {
            "beast_object_type": "lattice_memfd_replay_receipt", "lattice_id": comp_id, "children": list(comp.component_ids),
            "authority_A_L": list(comp.authority), "route_decision": rec["route"],
            "governor": tier.get("governor"), "per_child_replay": tier["stages"],
            "independent_verification": {**rec["independent"], "process": "separate unittest processes on a fresh copy",
                                         "final_tree_digest_parent": sha(fc.tree_digest(final)),
                                         "digest_matches_verified_copy": sha(fc.tree_digest(final)) == rec["independent"]["tree_digest"]},
            "bytes_copies": {"capsules": len(tier["stages"]),
                             "bytes_into_memfds": sum(s["copies"]["bytes_copied_into_memfd"] for s in tier["stages"]),
                             "payload_bytes_through_sockets": 0, "fd_passes": sum(int(s["copies"]["fd_passes"] or 0) for s in tier["stages"]),
                             "pipe_baseline_bytes": sum(s["copies"]["pipe_baseline_copy_bytes"] for s in tier["stages"])},
            "zero_model_proof": {"model_calls_during_lattice": tier["model_calls_during_lattice"],
                                 "child_network": [s["network"] for s in tier["stages"]]},
            "cold_baseline_same_task": {p: {k: r[k] for k in ("passed", "tokens_total", "latency_ms", "wall_ms", "reasoning_tokens")}
                                        | {"calls": len(r["calls"])} for p, r in out["cold_baseline"].items()},
            "avoided_vs_nemotron_cold": {"model_calls": int(cold["model_turns"]), "tokens": int(cold["tokens_total"]),
                                         "wall_ms": round(float(cold["wall_ms"]) - float(tier["lattice_wall_ms"]), 3)},
            "v_l_pgec_eq6": v_l, "children_v_ci": children,
            "composition_premium": {"rule": "S = max(0, V_L - sum(max(0, V_Ci))); children scaled to V_L when they exceed it",
                                    "v_l": vl, "sum_children": round(sum(gross), 6), "children_scaled_to_v_l": scaled,
                                    "surplus_S": round(surplus, 6),
                                    "credited_premium": 0.0,
                                    "credited_reason": "scaled_children_exhaust_v_l" if scaled else
                                    "lattice_publisher_controls_every_child (one local controller published children and lattice)"},
            "shadow_credit": {"units": v_l["credit"], **LEDGER_POLICY},
        }
        out["receipt"]["receipt_digest"] = sha(out["receipt"])
    print("[L3] negative controls on fresh tasks", flush=True)
    neg = []
    for name, expect in ((single, "single crystal, not lattice"), (diff, "no exact lattice; fallback")):
        r = g.solve(name, "lattice-neg")
        neg.append({"task": name, "expect": expect, "route": r["route"]["route"], "route_crystal": r["route"].get("crystal_id"),
                    "lattice_selected": r["route"].get("crystal_id") == comp_id and r["route"]["route"] == "crystal_replay",
                    "top_candidates": r["candidates"][:3], "accepted_by": r["accepted_by"], "passed": r["passed"],
                    "false_accept": r["false_accept"], "model_calls": r["model_calls"], "tokens_total": r["tokens_total"]})
    out["negative_controls"] = neg
    return out


def bench(g: Gauntlet, out: Path) -> dict[str, Any]:
    tasks = ["const-cold", "op-cold", "obo-cold", "exc-cold", "const-near", "op-near", "obo-near", "exc-near"]
    rows = []
    for model in OLLAMA_MODELS:
        for config in ("before", "after"):
            for name in tasks:
                METER.context = {"task": name, "phase": f"bench-{config}"}
                root = make_repo(g.work, name, f"{name}-bench-{model.replace(':', '_')}-{config}")
                try:
                    res = specialist_solve(model, root, name, g.governor, root.parent / "wt", config=config)
                except Exception as exc:  # noqa: BLE001
                    res = {"model": model, "config": config, "passed": False, "reason": f"error:{type(exc).__name__}",
                           "attempts": 0, "tokens_total": 0, "wall_ms": 0, "checks": []}
                res["independent"] = hidden_check(Path(res["worktree"]), name) if res.get("passed") else None
                res["false_accept"] = bool(res.get("passed") and not res["independent"]["passed"])
                rows.append({"task": name, **{k: v for k, v in res.items() if k != "checks"},
                             "last_reason": ((res.get("checks") or [{}])[-1].get("check") or {}).get("reason")})
                print(f"  bench {model:14} {config:6} {name:12} ok={res['passed']} att={res.get('attempts')} "
                      f"tok={res.get('tokens_total')} {res.get('wall_ms', 0):.0f}ms {res.get('reason')}", flush=True)
                write(out, "specialist_benchmark.json", rows)
    table = {}
    for model in OLLAMA_MODELS:
        for config in ("before", "after"):
            sel = [r for r in rows if r["model"] == model and r["config"] == config]
            table[f"{model}|{config}"] = {"passed": sum(r["passed"] for r in sel), "of": len(sel),
                                          "false_accepts": sum(r["false_accept"] for r in sel),
                                          "tokens": sum(int(r.get("tokens_total") or 0) for r in sel),
                                          "wall_s": round(sum(float(r.get("wall_ms") or 0) for r in sel) / 1000, 1)}
    return {"rows": rows, "table": table}


def run_all(args: Any) -> int:
    out, state = Path(args.out), Path(args.state)
    if state.exists():
        shutil.rmtree(state)
    out.mkdir(parents=True, exist_ok=True)
    g = Gauntlet(state, out, args.approve_by.strip())
    t_start = time.time()
    digests: dict[str, str] = {}
    print("[H] provider head-to-head cold baselines (Nemotron vs DeepSeek vs gpt-oss substitute)", flush=True)
    head = {f: h2h(g, f"{PREFIX[f]}-cold", ("nemotron", "deepseek", "gpt-oss"), "h2h") for f in FAMILY_ORDER}
    digests["provider_head_to_head.json"] = write(out, "provider_head_to_head.json", head)
    print("[A] learn: cold -> distil -> held-out -> promote, per family", flush=True)
    learned = [g.learn_family(f) for f in FAMILY_ORDER]
    digests["families.json"] = write(out, "families.json", learned)
    print("[C] lattice composite (off-by-one -> config constant)", flush=True)
    composite = g.learn_composite(("fix-off-by-one", "fix-config-constant"))
    digests["composite.json"] = write(out, "composite.json", composite)
    print("[W] warm / near-miss / decoy / far", flush=True)
    warm_names = [f"{PREFIX[f]}-{r}" for f in FAMILY_ORDER for r in ("w1", "w2", "near")] + ["const-decoy", "dual-w1", "far-1", "far-2"]
    warm = [public(g.solve(n, "warm")) for n in warm_names]
    digests["warm.json"] = write(out, "warm.json", warm)
    print("[L] lattice on a fresh chained workload", flush=True)
    lattice = lattice_experiment(g, args.seed or int(time.time()))
    digests["lattice_experiment.json"] = write(out, "lattice_experiment.json", lattice)
    print("[M] memfd capsule replay per promoted crystal + negative controls", flush=True)
    memfd = [memfd_for(g, f) for f in FAMILY_ORDER if f in g.crystal_of]
    digests["memfd_receipts.json"] = write(out, "memfd_receipts.json", memfd)
    negatives = []
    if "refactor-rename-symbol" in g.crystal_of:
        crystal = g.crystal(g.crystal_of["refactor-rename-symbol"])
        t = TASKS["ren-w2"]
        for label in ("tampered_payload", "unsealed_memfd", "wrong_postcondition"):
            root = make_repo(g.work, "ren-w2", f"neg-{label}")
            post = {"verify_command": t["verify"], "implementation_target": t["target"], "tests_run": 2, "expect_returncode": 0,
                    "files_sha256_after": {t["target"]: "sha256:" + "0" * 64} if label == "wrong_postcondition" else {}}
            res = g.capsule_replay(crystal, root, root.parent / "wt", "ren-w2", post, "negative-control", tamper=label)
            negatives.append({"control": label, "accepted": res["ok"], "refused": res["refused"],
                              "replay_ran": bool(res["replay"]["steps"]), "credit_units": 0.0})
    digests["negative_controls.json"] = write(out, "negative_controls.json", {"lattice": lattice["negative_controls"], "capsule_tamper": negatives})
    bench_out = None
    if args.bench:
        print("[B] specialist before/after benchmark (3 Ollama models x 8 tasks x 2 configs)", flush=True)
        bench_out = bench(g, out)
        digests["specialist_benchmark.json"] = write(out, "specialist_benchmark.json", bench_out)
    calls = METER.calls
    digests["model_calls.json"] = write(out, "model_calls.json", calls)
    families_table = []
    for item in learned:
        f = item["family"]
        w = [r for r in warm if r["family"] == f]
        families_table.append({
            "family": f, "cold_by": item["cold"]["accepted_by"], "cold_calls": item["cold"]["model_calls"],
            "cold_tokens": item["cold"]["tokens_total"], "cold_wall_ms": item["cold"]["wall_ms"], "crystal": item.get("distilled"),
            "equivalence": (item.get("extraction") or {}).get("equivalence") or (item.get("extraction") or {}).get("refused"),
            "heldout_passed": sum(1 for h in item.get("heldout") or [] if h["ok"] and h["independent"]["passed"]),
            "promoted": bool(item.get("promotion")),
            "warm": [{k: r[k] for k in ("task", "role", "accepted_by", "model_calls", "tokens_total", "wall_ms", "passed", "false_accept")}
                     | {"similarity": (r["candidates"] or [{}])[0].get("similarity"), "route": r["route"]["route"]} for r in w]})
    warm_exact = [r for r in warm if r["role"] == "warm" and r["family"] in FAMILY_ORDER]
    hits = [r for r in warm_exact if r["accepted_by"] == "crystal"]
    nears = [r for r in warm if r["role"] == "near"]
    saved_calls = sum(int((g.cold_budgets.get(r["family"]) or {}).get("model_turns") or 0) for r in hits)
    saved_tokens = sum(int((g.cold_budgets.get(r["family"]) or {}).get("tokens_total") or 0) for r in hits)
    all_recs = [public(r) for r in g.records]
    spend = {}
    for c in calls:
        key = f"{c.get('provider')}|{c.get('model')}"
        row = spend.setdefault(key, {"calls": 0, "failed_or_timeout": 0, "circuit_open_skipped": 0, "tokens": 0})
        if c.get("status") == "circuit_open":
            row["circuit_open_skipped"] += 1
            continue
        row["calls"] += 1
        row["failed_or_timeout"] += int(bool(c.get("failed")))
        row["tokens"] += int(c.get("tokens_total") or 0)
    summary = {
        "approved_by": g.approve, "started_at": t_start, "duration_s": round(time.time() - t_start, 1),
        "families": families_table, "composite": {k: composite.get(k) for k in ("composite", "children", "authority_A_L")}
        | {"promoted": bool(composite.get("promotion"))},
        "rates": {"warm_exact_tasks": len(warm_exact), "crystal_hits": len(hits),
                  "crystal_hit_rate": round(len(hits) / max(1, len(warm_exact)), 3),
                  "near_miss": [{k: r[k] for k in ("task", "accepted_by", "passed", "false_accept")} | {"route": r["route"]["route"]}
                                for r in nears],
                  "near_miss_correct": sum(1 for r in nears if r["accepted_by"] not in {"crystal", "lattice"} and not r["false_accept"]),
                  "false_accepts_total": sum(1 for r in all_recs if r["false_accept"])
                  + sum(1 for b in (bench_out or {}).get("rows", []) if b.get("false_accept")),
                  "pipeline_episodes": len(all_recs)},
        "saved_by_crystal_hits": {"model_calls": saved_calls, "tokens": saved_tokens},
        "memfd": [{"family": m["family"], "crystal": m["crystal_id"], "ok": m["ok"], "bytes": m["capsule"]["bytes_total"],
                   "seals": m["capsule"]["seals_value"], "child_wall_ms": m["process"]["child_wall_ms"],
                   "net": m["network"], "v_k": (m["pgec_eq6"] or {}).get("v_k"), "credit": m["shadow_credit"]["units"]} for m in memfd],
        "shadow_credits_total": round(sum(m["shadow_credit"]["units"] for m in memfd), 6),
        "lattice": {k: lattice["selection"][k] for k in ("lattice_id", "selected", "used_to_complete")}
        | {"negative_controls": lattice["negative_controls"],
           "v_l": (lattice.get("receipt") or {}).get("v_l_pgec_eq6", {}).get("v_k"),
           "premium": (lattice.get("receipt") or {}).get("composition_premium")},
        "negative_controls": negatives, "specialist_benchmark": (bench_out or {}).get("table"),
        "provider_h2h": {f: {p: {k: r[k] for k in ("passed", "tokens_total", "latency_ms", "reasoning_tokens")} for p, r in rows.items()}
                         for f, rows in head.items()},
        "spend": spend, "receipt_digests": digests,
        "governor_chain": g.governor.receipts.verify(),
    }
    write(out, "summary.json", summary)
    key = os.environ.get("NVIDIA_API_KEY", "")
    if key and any(key in p.read_text() for p in out.glob("*.json*")):
        raise SystemExit("secret material found in evidence; aborting")
    print(json.dumps({k: summary[k] for k in ("rates", "saved_by_crystal_hits", "lattice", "shadow_credits_total", "spend")},
                     indent=1, default=str))
    return 0


def followup_rename(args: Any) -> int:
    """Targeted follow-up on the existing isolated registry: rename family with test-output feedback in repairs."""
    global FEEDBACK_OUTPUT
    FEEDBACK_OUTPUT = True
    out, state = Path(args.out), Path(args.state)
    g = Gauntlet(state, out, args.approve_by.strip(), receipts="governor_receipts_followup.jsonl")
    for crystal in g.registry.promoted():
        if not crystal.component_ids:
            g.crystal_of[crystal.task_family] = crystal.crystal_id
    for item in json.loads((out / "families.json").read_text()):
        cold = item["cold"]
        g.cold_budgets[item["family"]] = budget_for([], 5, cold["wall_ms"]) | {
            "model_turns": float(cold["model_calls"]), "tokens_total": float(cold["tokens_total"])}
    calls_before = len(METER.calls)
    t0 = time.time()
    family = "refactor-rename-symbol"
    learned = g.learn_family(family)
    warm = [public(g.solve(n, "warm")) for n in ("ren-w1", "ren-w2", "ren-near")]
    memfd = memfd_for(g, family) if family in g.crystal_of else None
    target_family = family if family in g.crystal_of else "toolchain-regenerate"
    crystal = g.crystal(g.crystal_of[target_family])
    neg_task = f"{PREFIX[target_family]}-w2"
    t = TASKS[neg_task]
    negatives = []
    for label in ("tampered_payload", "unsealed_memfd", "wrong_postcondition"):
        root = make_repo(g.work, neg_task, f"neg-{label}")
        post = {"verify_command": t["verify"], "implementation_target": t["target"], "tests_run": 2, "expect_returncode": 0,
                "files_sha256_after": {t["target"]: "sha256:" + "0" * 64} if label == "wrong_postcondition" else {}}
        res = g.capsule_replay(crystal, root, root.parent / "wt", neg_task, post, "negative-control", tamper=label)
        negatives.append({"control": label, "crystal_id": crystal.crystal_id, "task": neg_task, "accepted": res["ok"],
                          "refused": res["refused"], "replay_ran": bool(res["replay"]["steps"]), "credit_units": 0.0})
    body = {"why": "main run: Nemotron renamed the definition but not the call sites (2 attempts, repair turn carried only "
                   "'tests_still_failing'); DeepSeek/gpt-oss tiers were circuit-open. Follow-up feeds the post-edit test "
                   "output into the repair turn.", "started_at": t0, "family": learned, "warm": warm, "memfd": memfd,
            "negative_controls": negatives, "model_calls": METER.calls[calls_before:],
            "governor_chain": g.governor.receipts.verify()}
    write(out, "followup_rename.json", body)
    print(json.dumps({"distilled": learned.get("distilled"), "promoted": bool(learned.get("promotion")),
                      "warm": [(w["task"], w["accepted_by"], w["passed"], w["false_accept"]) for w in warm],
                      "memfd_ok": (memfd or {}).get("ok"), "negatives": [(n["control"], n["accepted"]) for n in negatives]},
                     default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-by", default="")
    parser.add_argument("--out", default=str(ROOT / "evidence" / "gauntlet-2026-11-16-large"))
    parser.add_argument("--state", default=str(ROOT / ".beast" / "gauntlets" / "2026-11-16-large"))
    parser.add_argument("--bench", action="store_true", help="run the specialist before/after benchmark (slow)")
    parser.add_argument("--seed", type=int, default=0, help="fresh-lattice seed (default: time-based)")
    parser.add_argument("--followup", choices=["rename"], default="")
    args = parser.parse_args()
    os.environ.update(FLAGS)
    return followup_rename(args) if args.followup == "rename" else run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
