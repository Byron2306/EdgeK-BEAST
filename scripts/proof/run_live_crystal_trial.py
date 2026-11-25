#!/usr/bin/env python3
"""Capture one coding crystal from hosted NIM, then compare paired held-out repairs.

This trial never publishes. It uses only generated fixtures and a disposable
local signing key. The production IDE gateway and its registry are not used.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.compute.coding_crystal_runtime import ENABLE_ENV, KEY_ENV, learn_from_run, planner_runtime_extras
from app.kernel.compute.nim_picker import HOSTED_NEMOTRON_BASE_URL, HOSTED_NEMOTRON_MODEL
from app.kernel.governance.runtime import RuntimeGovernor
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore
from tests.crystal_fabric_support import MISFIT_ALREADY_GREEN, make_assertion_repo, verify_command

FAMILY = "fix-failing-assertion"
TRAIN = {"module": "calc", "constant": "RATE", "actual": 3, "expected": 4, "function": "rate"}
HOLDOUTS = (
    {"module": "shipping", "constant": "BASE", "actual": 17, "expected": 19, "function": "charge"},
    {"module": "greeting", "constant": "GREETING", "actual": "north", "expected": "south", "function": "greet"},
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def verify(root: Path, module: str) -> int:
    return subprocess.run(verify_command(module), cwd=root, capture_output=True, timeout=30, check=False).returncode


class TrialRuntime(AgentPlannerRuntime):
    """Keep the same provider and exact test command in both arms."""

    def __init__(self, *args, variant: dict, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = variant["module"]
        self.constant = variant["constant"]
        self.actual = variant["actual"]
        self.fixture_source = (Path(self.engine.workspace_root) / f"{self.module}.py").read_text().removesuffix("\n")

    def _canonical_edit(self, args: dict) -> dict:
        prefix = f"{self.constant} = "
        original = prefix + repr(self.actual)
        old, new = args.get("old_text"), args.get("new_text")
        if args.get("path") != f"{self.module}.py" or not isinstance(old, str) or not isinstance(new, str):
            raise ValueError("Edit is outside the fixture's single literal assignment")
        old, new = old.removesuffix("\n"), new.removesuffix("\n")
        if "\n" in old:
            first, _, trailing = old.partition("\n")
            new, separator, new_trailing = new.partition("\n")
            if old != self.fixture_source or first != original or not separator or trailing != new_trailing:
                raise ValueError("Whole-file edit must preserve all lines except the fixture literal")
        elif old != original:
            raise ValueError("Old text must match the original fixture literal")
        if len(new) > 128 or not new.startswith(prefix) or "\n" in new or "\r" in new:
            raise ValueError("Edit is outside the fixture's single literal assignment")
        try:
            literal = ast.parse(new[len(prefix):], mode="eval").body
        except (ValueError, SyntaxError):
            raise ValueError("Replacement must be a single literal") from None
        if not isinstance(literal, ast.Constant) or type(literal.value) is not type(self.actual):
            raise ValueError("Replacement must be a single literal of the original type")
        return {**args, "old_text": original, "new_text": prefix + repr(literal.value)}

    @classmethod
    def _required_phase_decision(cls, run, state, decision=None):
        request = run.get("request") or {}
        if (request.get("trial_model_only") and cls._latest_index(state, {"worktree.bind"}, completed_only=True) >= 0
                and cls._latest_index(state, {"worktree.verify"}) < 0):
            module = Path(request["implementation_target"]).stem
            return PlannerDecision(PlannerDecisionType.TOOL, tool_id="worktree.verify",
                                   arguments={"command": verify_command(module)},
                                   rationale="Record the untouched fixture's failing verifier before model edits.")
        return super()._required_phase_decision(run, state, decision)

    async def _authorize_tool(self, run, run_id, decision, *, defer=False):
        tool, args = decision.tool_id, decision.arguments
        if decision.execution_target not in ("", None, "local"):
            raise ValueError("Fixture admits only local tools")
        if tool not in {"workspace.list", "workspace.index", "workspace.search_text", "workspace.read_range",
                        "worktree.bind", "worktree.verify", "worktree.replace_exact", "worktree.sourceplan_draft"}:
            raise ValueError("Tool is outside the disposable repair fixture")
        if tool == "worktree.verify" and args != {"command": verify_command(self.module)}:
            raise ValueError("Only the predeclared verifier is admitted")
        if tool == "worktree.replace_exact":
            canonical = self._canonical_edit(args)
            if canonical != args:
                self.engine.emit(run_id, "agent.trial.edit_span_normalized", {
                    "tool_id": tool, "path": canonical["path"], "model_literal_preserved": True,
                })
                decision = replace(decision, arguments=canonical)
        return await super()._authorize_tool(run, run_id, decision, defer=defer)

    @classmethod
    def _default_verification_command(cls, state):
        changed = cls._latest_mutation_paths(state)
        return verify_command(Path(changed[0]).stem) if len(changed) == 1 else super()._default_verification_command(state)

    def _get_mutation_retry_provider(self, original_provider, run):
        return original_provider

    @staticmethod
    def _heuristic_continuation_allowed(run):
        return False


class MeteredNIM(NIMPlannerProvider):
    def __init__(self, governor: RuntimeGovernor):
        super().__init__(model=HOSTED_NEMOTRON_MODEL, base_url=HOSTED_NEMOTRON_BASE_URL,
                         runtime_governor=governor, max_retries=1)
        self.calls = 0

    def _request_json(self, payload):
        self.calls += 1
        return super()._request_json(payload)

    def _request_stream(self, payload):
        self.calls += 1
        return super()._request_stream(payload)


class NoFallback:
    calls = 0

    async def next_decision(self, prompt, *, run, turn):
        self.calls += 1
        from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

        return PlannerDecision(PlannerDecisionType.BLOCKED, blocker="The already-green negative control has no model fallback.")


def model_governor(root: Path) -> RuntimeGovernor:
    return RuntimeGovernor(
        policies={"providers": {"nvidia_nim": {"enabled": True, "runtime_max_concurrent": 1}}},
        db_path=str(root / "nim-runtime.sqlite3"),
    )


def run_arm(root: Path, variant: dict, provider, *, envelopes: EpisodeEnvelopeStore, planner=None,
            already_green: bool = False) -> dict:
    module = variant["module"]
    target, test = f"{module}.py", f"test_{module}.py"
    make_assertion_repo(root, **variant)
    source_before, test_before = digest(root / target), digest(root / test)
    before = verify(root, module)
    if before != (0 if already_green else 1):
        raise RuntimeError("Fixture's independent precheck did not return the expected result.")
    engine = AgentRunEngine(root)
    command = verify_command(module)
    run = engine.create_run(
        session_id="live-crystal-fixture", mode="agent", provider="nvidia_nim", model=HOSTED_NEMOTRON_MODEL,
        objective=(f"Fix the failing assertion by changing only the single incorrect constant in {target}. "
                   f"Read {target} and {test}. Never edit tests. Bind the worktree and run the existing "
                   f"unittest before and after your exact replacement. Verification command: {' '.join(command)}. "
                   "Use the actual failing assertion output to select the literal. For old_text and new_text, "
                   "supply the assignment line only, without surrounding source."),
        request={"task_family": FAMILY, "implementation_target": target,
                 "required_test_files": [test], "context_files": [target],
                 "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
                 "trial_model_only": planner is None},
    )
    run_id = run["run_id"]
    # Same narrow fixture approvals as the existing closed-loop proof.
    engine.store.create_approval(run_id, {"request_id": "mutate", "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, "mutate", {"approved": True, "scope": "run"})
    engine.store.create_approval(run_id, {"request_id": "verify", "tool_id": "worktree.verify",
                                         "safe_arguments": {"command": command},
                                         "capabilities": [{"id": "worktree.verify"}]})
    engine.store.resolve_approval(run_id, "verify", {"approved": True, "scope": "run"})
    start = time.monotonic()
    runtime = TrialRuntime(engine, provider, variant=variant, max_turns=14, observation_limit=24,
                           envelope_store=envelopes, crystal_planner=planner,
                           integration_coordinator=CoderIntegrationCoordinator(root, environ={}))
    final = asyncio.run(runtime.run(run_id, defer_approval=True))
    events = engine.store.events(run_id, limit=10000)
    checkpoint = final.get("checkpoint") or {}
    worktree = checkpoint.get("worktree_root")
    changed, independent_pass = [], False
    if worktree and not already_green:
        wt = Path(worktree)
        changed = sorted(git(wt, "diff", "--name-only", "HEAD").splitlines())
        independent_pass = (
            changed == [target] and (wt / test).is_file() and digest(wt / test) == test_before
            and verify(wt, module) == 0
        )
    try:
        sealed = envelopes.get(run_id).verification.get("passed") is True
    except LookupError:
        sealed = False
    replay = any(e["event_type"] == "agent.crystal.completed" for e in events)
    aborted = [e["payload"].get("reason") for e in events if e["event_type"] == "agent.crystal.aborted"]
    observations = (checkpoint.get("planner") or {}).get("observations", [])
    mutate = any(o.get("tool_id") == "worktree.replace_exact" and o.get("status") == "completed" for o in observations)
    original_unchanged = digest(root / target) == source_before and digest(root / test) == test_before
    return {
        "run_id": run_id, "state": final.get("state"), "before_rc": before,
        "event_chain_valid": engine.store.verify_chain(run_id).get("ok") is True,
        "independent_pass": independent_pass and original_unchanged,
        "sealed_pass": sealed, "crystal_completed": replay, "crystal_refusals": aborted,
        "changed_tracked_paths": changed, "fixture_sha256": [source_before, test_before],
        "original_unchanged": original_unchanged, "mutation_observed": mutate,
        "observed_provider_attempts": provider.calls, "model_turns": (final.get("budget") or {}).get("model_turns", 0),
        "tool_calls": (final.get("budget") or {}).get("tool_calls", 0),
        "wall_seconds": round(time.monotonic() - start, 3),
    }


def new_local_key(path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    data = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def save(path: Path, data: dict) -> None:
    payload = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
    print(payload, flush=True)


def good(arm: dict) -> bool:
    return (arm["state"] == "completed" and arm["independent_pass"]
            and arm["sealed_pass"] and arm["event_chain_valid"])


def env_for(root: Path) -> dict:
    return {ENABLE_ENV: "1", KEY_ENV: str(root / "trial-key.pem")}


def capture(root: Path, provider_factory=MeteredNIM) -> int:
    root.mkdir(mode=0o700, exist_ok=False)
    new_local_key(root / "trial-key.pem")
    env = env_for(root)
    train = root / "train"
    extras = planner_runtime_extras(train, env=env)
    source = run_arm(train, TRAIN, provider_factory(model_governor(root)), envelopes=extras["envelope_store"])
    report = {"model": HOSTED_NEMOTRON_MODEL, "source": source, "status": "capture_not_proven"}
    if good(source) and source["observed_provider_attempts"] > 0 and not source["crystal_completed"]:
        report["candidate"] = learn_from_run(train, source["run_id"], env=env)
        report["status"] = report["candidate"]["status"]
    save(root / "capture.json", report)
    return 0 if report["status"] == "verified_awaiting_operator_promotion" else 1


def compare(root: Path, approved_by: str, provider_factory=MeteredNIM) -> int:
    captured = json.loads((root / "capture.json").read_text(encoding="utf-8"))
    if captured["status"] != "verified_awaiting_operator_promotion":
        raise ValueError("Capture did not pass independent verification and held-out reproduction.")
    if not approved_by.strip():
        raise ValueError("Provide the reviewing operator's name with --approve-by.")
    env = env_for(root)
    train = root / "train"
    results_root = root / "comparison"
    results_root.mkdir()
    learned = learn_from_run(train, captured["source"]["run_id"], env=env, approved_by=approved_by)
    if learned["status"] != "promoted" or learned["crystal_id"] != captured["candidate"]["crystal_id"]:
        save(results_root / "comparison.json", {"status": "promotion_not_proven", "promotion": learned})
        return 1
    planner = planner_runtime_extras(train, env=env)["crystal_planner"]
    governor = model_governor(root)
    rows = []
    for idx, variant in enumerate(HOLDOUTS):
        row = {"case": variant["module"]}
        # Alternate A/B order to reduce simple ordering bias.
        for arm in (("off", "on") if idx == 0 else ("on", "off")):
            target = results_root / f"{variant['module']}-{arm}"
            envelopes = EpisodeEnvelopeStore(target.with_suffix(".sqlite3"))
            row[arm] = run_arm(target, variant, provider_factory(governor), envelopes=envelopes,
                               planner=planner if arm == "on" else None)
        off, on = row["off"], row["on"]
        row["passed"] = (
            good(off) and good(on) and off["fixture_sha256"] == on["fixture_sha256"]
            and not off["crystal_completed"] and on["crystal_completed"]
            and off["observed_provider_attempts"] > on["observed_provider_attempts"]
            and on["observed_provider_attempts"] == 0
        )
        rows.append(row)
        save(results_root / f"{variant['module']}.json", row)
    negative = run_arm(results_root / "already-green", MISFIT_ALREADY_GREEN, NoFallback(), planner=planner,
                       envelopes=EpisodeEnvelopeStore(results_root / "negative.sqlite3"), already_green=True)
    negative_pass = (negative["event_chain_valid"] and "precondition_not_failing" in negative["crystal_refusals"]
                     and not negative["crystal_completed"] and not negative["mutation_observed"]
                     and negative["original_unchanged"])
    passed = all(row["passed"] for row in rows) and negative_pass
    save(results_root / "comparison.json", {"status": "pass" if passed else "not_proven",
                                            "rows": rows, "negative": negative, "negative_pass": negative_pass})
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("capture", "compare"))
    parser.add_argument("--trial-dir", type=Path, required=True)
    parser.add_argument("--approve-by", default="")
    args = parser.parse_args()
    if not os.environ.get("NVIDIA_API_KEY"):
        parser.error("NVIDIA_API_KEY is not set in this shell. No key was read or printed.")
    root = args.trial_dir.expanduser().resolve()
    try:
        if args.phase == "capture":
            return capture(root)
        return compare(root, args.approve_by)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Trial stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
