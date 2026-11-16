"""Shared helpers for the 2026-11-16 closure runs: the governed tool chain + crystal-first Gauntlet adapter.

* ``tool_chain()``: TGI (local GPU, $0) -> Fireworks GLM-5.3-Flash -> Fireworks DeepSeek-V4.1-Flash -> HF Kimi-K2.7-Code.
* ``governed_solve()``: one governed episode; rename/multi-file families force the ``code.rename_symbol`` action schema,
  everything else the exact-edits schema; verifier = visible tests + hidden intent check on temp copies.
* ``ClosureGauntlet``: the existing ``gauntlet_large.Gauntlet`` (crystal discover -> route -> replay/lattice capsules ->
  distil -> held-out -> promote) with its provider tier swapped for ``governed_solve`` and the Ollama specialist tier
  disabled while TGI holds the GPU.
No prompts, outputs or credentials are written; spend is metered per call.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gauntlet_large as gl  # noqa: E402

from app.kernel.compute.capability_scorecard import CapabilityScorecard  # noqa: E402
from app.kernel.compute.family_crystals import run_verify  # noqa: E402
from app.kernel.compute.governed_client import (Candidate, CircuitBreaker, GovernedModelClient, HF_ROUTER_BASE,  # noqa: E402
                                                provider_lane_candidates, tgi_available)
from app.kernel.compute.governed_refactor import action_for_family, apply_action_to_copy  # noqa: E402

TGI = os.environ.get("TGI_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
SPEND = {"usd": 0.0, "calls": 0}
CAP_USD = float(os.environ.get("BEAST_CLOSURE_CAP_USD", "0.30"))


def tgi_candidate() -> Candidate:
    return Candidate(provider="tgi", model="Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", kind="tgi", base_url=TGI + "/v1",
                     placement="gpu_full", rung="local_specialist", max_tokens=768, ttft_timeout_s=90, stall_timeout_s=20,
                     timeout_s=180)


def kimi() -> Candidate:
    return Candidate(provider="hf", model="moonshotai/Kimi-K2.7-Code:deepinfra", kind="hf_router", base_url=HF_ROUTER_BASE,
                     key_env="HF_TOKEN", key_file="~/.cache/huggingface/token", max_tokens=2048, ttft_timeout_s=60,
                     stall_timeout_s=30, timeout_s=120, usd_per_mtok_in=0.68, usd_per_mtok_out=3.4)


def fireworks(names=("glm-5p3-flash", "deepseek-v4p1-flash")) -> list[Candidate]:
    lanes = {c.model.rsplit("/", 1)[-1]: c for c in provider_lane_candidates(providers=["fireworks"])}
    return [lanes[n] for n in names if n in lanes]


def tool_chain(*, tgi: bool = True) -> list[Candidate]:
    out = [tgi_candidate()] if tgi and tgi_available(TGI) else []
    return out + fireworks() + [kimi()]


def make_client(cands: list[Candidate], governor: Any, scorecard: CapabilityScorecard, breaker: CircuitBreaker,
                *, max_attempts: int = 4, use_scorecard: bool = False) -> GovernedModelClient:
    return GovernedModelClient(cands, scorecard=scorecard, governor=governor, breaker=breaker, use_scorecard=use_scorecard,
                               max_attempts=max_attempts, feedback_turns=True)


def governed_solve(client: GovernedModelClient, name: str, root: Path, workdir: Path, run_id: str,
                   *, force_edits: bool = False) -> dict[str, Any]:
    """One governed episode on a temp repo. Returns acceptance (visible+hidden), action, worktree, metered calls."""
    if SPEND["usd"] >= CAP_USD:
        return {"task": name, "accepted": False, "reason": "closure_spend_cap_reached", "calls": [], "model_calls": 0}
    task = gl.TASKS[name]
    failure = run_verify(task["verify"], root)["output"]
    spec = action_for_family("" if force_edits else task["family"], "" if force_edits else failure)
    messages = spec["messages"](gl.context_files(root), failure, target=task["target"])
    verdicts: list[dict[str, Any]] = []
    worktrees: list[Path] = []

    def verify(value: Any) -> dict[str, Any]:
        wt = workdir / f"wt{len(verdicts)}"
        if spec["tool"]:
            applied = apply_action_to_copy(root, value, wt)
            if applied.get("applied"):
                res = run_verify(task["verify"], wt)
                vis = res["returncode"] == 0 and res["tests_run"] == task["tests_run"]
                check = {"passed": vis, "reason": "" if vis else "tests_still_failing", "output_tail": res["output"][-700:],
                         "changed": applied["changed"]}
            else:
                check = {"passed": False, "reason": applied.get("reason"),
                         "output_tail": applied.get("output_tail") or applied.get("reason") or ""}
        else:
            check = gl.apply_and_verify(root, name, (value or {}).get("edits") if isinstance(value, dict) else None, wt)
        hidden = gl.hidden_check(wt, name) if check.get("passed") else {"passed": False}
        v = {"passed": bool(check.get("passed") and hidden.get("passed")), "visible_passed": bool(check.get("passed")),
             "hidden_passed": bool(hidden.get("passed")),
             "reason": check.get("reason") or ("" if hidden.get("passed") else "hidden_check_failed"),
             "files_changed": len(check.get("changed") or []),
             "feedback": (check.get("output_tail") or "") if not check.get("passed") else
             ("" if hidden.get("passed") else "an independent intent check failed: keep behaviour for all inputs")}
        verdicts.append(v)
        worktrees.append(wt)
        return v

    started = time.perf_counter()
    res = asyncio.run(client.complete(family=task["family"], messages=messages, schema=spec["schema"], verify=verify, run_id=run_id))
    pub = res.public()
    spend = sum(c["spend_usd"] for c in pub["calls"])
    SPEND["usd"] += spend
    SPEND["calls"] += pub["model_calls"]
    for c in pub["calls"]:
        gl.METER.add({"provider": c["provider"], "model": c["model"], "status": c["status"],
                      "failed": c["status"] != "ok", "tokens_prompt": c["tokens_prompt"],
                      "tokens_completion": c["tokens_completion"], "tokens_total": c["tokens_prompt"] + c["tokens_completion"],
                      "spend_usd": c["spend_usd"]})
    win = next((i for i, v in enumerate(verdicts) if v["passed"]), None)
    return {"task": name, "family": task["family"], "tool": spec["tool"] or "exact_edits", "wall_s": round(time.perf_counter() - started, 2),
            "spend_usd": round(spend, 6), **pub, "action": res.value if res.accepted else None,
            "worktree": worktrees[win] if win is not None else None,
            "verdicts": [{k: v for k, v in d.items() if k != "feedback"} for d in verdicts]}


class ClosureGauntlet(gl.Gauntlet):
    """Existing crystal-first gauntlet; provider tier = governed tool chain, specialist tier off (GPU is TGI's)."""

    def __init__(self, state: Path, out: Path, approve: str, client_factory, receipts: str = "governor_receipts.jsonl"):
        super().__init__(state, out, approve, receipts=receipts)
        self.client = client_factory(self.governor)
        self.episodes: list[dict[str, Any]] = []
        gauntlet = self

        def provider_solve(provider, root, task_name, governor, wt, *, attempts=2, reason=""):
            if provider != "nemotron":  # one governed chain covers every tier; second slot is a no-op
                return {"passed": False, "worktree": None, "edits": None, "attempts": [], "skipped": "governed_chain_already_ran"}
            ep = governed_solve(gauntlet.client, task_name, root, wt.parent / "governed", f"closure:{task_name}:{reason}")
            gauntlet.episodes.append({k: v for k, v in ep.items() if k not in {"worktree", "ranking"}} | {"worktree": None})
            action = ep.get("action") or {}
            return {"passed": bool(ep["accepted"]), "worktree": str(ep["worktree"]) if ep.get("worktree") else None,
                    "edits": [action] if action else None, "accepted_by": ep.get("accepted_by"), "model_calls": ep["model_calls"],
                    "spend_usd": ep["spend_usd"], "attempts": [{"check": {"accepted_by": ep.get("accepted_by")}}]}

        def specialist_solve(model, root, task_name, governor, wt, **kw):
            return {"passed": False, "worktree": None, "edits": None, "checks": [], "skipped": "gpu_owned_by_tgi"}

        gl.provider_solve = provider_solve
        gl.specialist_solve = specialist_solve
