#!/usr/bin/env python3
"""Harder live coding-crystal / lattice gauntlet.

Forms two distinct leaves from live NIM repairs, promotes each after 3/3
held-out replay, admits them as lattice leaves, then attempts a LIVE
composite (COMPOSES_WITH hyperedge) whose held-out variants need both
leaves. Reuse arms compare crystal-on versus crystal-off provider calls.

Tasks run on temporary copies under an evidence workspace. The production
gateway, ARDA, and system services are not touched. Provider secret values
are never printed.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.compute.coding_crystal_runtime import (
    AUTO_PROMOTE_ENV,
    ENABLE_ENV,
    KEY_ENV,
    LATTICE_ENV,
    LATTICE_LEDGER_ENV,
    learn_from_run,
    planner_runtime_extras,
)
from app.kernel.compute.coding_crystals import CodingCrystalPlanner
from app.kernel.compute.crystal_lattice_spine import compose_candidates
from app.kernel.compute.heldout_replay import HeldOutReplayGate
from app.kernel.compute.nim_picker import HOSTED_NEMOTRON_BASE_URL
from app.kernel.governance.runtime import RuntimeGovernor
from app.kernel.security.secret_vault import SecretVault
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

FAMILY = "fix-failing-assertion"
COMPOSITE_FAMILY = "fix-two-assertions"
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
# Public NVIDIA NIM list price as of 2026-11 (integrate.api.nvidia.com), USD / 1M tokens.
# Used only to estimate spend from returned usage; recorded as an estimate.
# The hosted integrate.api.nvidia.com trial endpoint used here is free for
# prototyping. Token counts are always recorded. estimated_usd stays 0.00
# unless BEAST_NIM_BILLABLE=1, in which case public list prices are used
# only as a commercial-equivalent footnote.
NIM_PRICE = {
    "nvidia/nemotron-3.5-super-vl-120b-a12b": {"input": 0.06, "output": 0.35},
    "nvidia/nemotron-3.5-lightning-30b-a3b": {"input": 0.025, "output": 0.12},
}

# Leaf A: one integer root cause, four files, three assertions (Codex-hard style).
PACKAGE_BURST = {
    "name": "burst-limit",
    "target": "rate_limit.py",
    "tests": ["test_rate_limit.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_rate_limit.py", "-q"],
    "expected_change": ["rate_limit.py"],
    "files": {
        "rate_limit.py": "BURST_LIMIT = 24\n\n\ndef burst_limit():\n    return BURST_LIMIT\n",
        "limiter/__init__.py": "from .service import allowed_burst\n",
        "limiter/policy.py": 'TIERS = {"free", "enterprise"}\n\n\ndef valid_tier(value: str) -> bool:\n    return value in TIERS\n',
        "limiter/service.py": (
            "from rate_limit import burst_limit\n\n\n"
            "def allowed_burst(client_tier: str) -> int:\n"
            "    if client_tier == \"enterprise\":\n"
            "        return burst_limit()\n"
            "    return max(1, burst_limit() // 4)\n"
        ),
        "test_rate_limit.py": (
            "import unittest\n\nimport rate_limit\nfrom limiter.service import allowed_burst\n\n\n"
            "class RateLimitContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(rate_limit.burst_limit(), 32)\n\n"
            "    def test_enterprise_service_contract(self):\n"
            "        self.assertEqual(allowed_burst(\"enterprise\"), 32)\n\n"
            "    def test_free_tier_derivation(self):\n"
            "        self.assertEqual(allowed_burst(\"free\"), 8)\n"
        ),
    },
}

# Fresh integer variant for reuse (same root-cause family, different names/values).
PACKAGE_QUOTA = {
    "name": "quota-limit",
    "target": "quota.py",
    "tests": ["test_quota.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_quota.py", "-q"],
    "expected_change": ["quota.py"],
    "files": {
        "quota.py": "MAX_ITEMS = 10\n\n\ndef max_items():\n    return MAX_ITEMS\n",
        "catalog/__init__.py": "from .service import allowed_items\n",
        "catalog/policy.py": 'TIERS = {"free", "enterprise"}\n',
        "catalog/service.py": (
            "from quota import max_items\n\n\n"
            "def allowed_items(client_tier: str) -> int:\n"
            "    if client_tier == \"enterprise\":\n"
            "        return max_items()\n"
            "    return max(1, max_items() // 2)\n"
        ),
        "test_quota.py": (
            "import unittest\n\nimport quota\nfrom catalog.service import allowed_items\n\n\n"
            "class QuotaContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(quota.max_items(), 12)\n\n"
            "    def test_enterprise_service_contract(self):\n"
            "        self.assertEqual(allowed_items(\"enterprise\"), 12)\n\n"
            "    def test_free_tier_derivation(self):\n"
            "        self.assertEqual(allowed_items(\"free\"), 6)\n"
        ),
    },
}

# Leaf B: one string root cause, multi-file package.
PACKAGE_VOICE = {
    "name": "voice-greeting",
    "target": "voice.py",
    "tests": ["test_voice.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_voice.py", "-q"],
    "expected_change": ["voice.py"],
    "files": {
        "voice.py": 'GREETING = "hi"\n\n\ndef greeting():\n    return GREETING\n',
        "greeter/__init__.py": "from .service import welcome\n",
        "greeter/style.py": 'TONES = {"formal", "casual"}\n',
        "greeter/service.py": (
            "from voice import greeting\n\n\n"
            "def welcome(tone: str) -> str:\n"
            "    word = greeting()\n"
            "    if tone == \"formal\":\n"
            "        return word.capitalize()\n"
            "    return word\n"
        ),
        "test_voice.py": (
            "import unittest\n\nimport voice\nfrom greeter.service import welcome\n\n\n"
            "class VoiceContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(voice.greeting(), \"hello\")\n\n"
            "    def test_casual_welcome(self):\n"
            "        self.assertEqual(welcome(\"casual\"), \"hello\")\n\n"
            "    def test_formal_welcome(self):\n"
            "        self.assertEqual(welcome(\"formal\"), \"Hello\")\n"
        ),
    },
}

PACKAGE_SALUTE = {
    "name": "voice-salute",
    "target": "salute.py",
    "tests": ["test_salute.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_salute.py", "-q"],
    "expected_change": ["salute.py"],
    "files": {
        "salute.py": 'WORD = "hey"\n\n\ndef word():\n    return WORD\n',
        "messenger/__init__.py": "from .service import banner\n",
        "messenger/service.py": (
            "from salute import word\n\n\n"
            "def banner(shout: bool) -> str:\n"
            "    text = word()\n"
            "    return text.upper() if shout else text\n"
        ),
        "test_salute.py": (
            "import unittest\n\nimport salute\nfrom messenger.service import banner\n\n\n"
            "class SaluteContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(salute.word(), \"welcome\")\n\n"
            "    def test_quiet_banner(self):\n"
            "        self.assertEqual(banner(False), \"welcome\")\n\n"
            "    def test_loud_banner(self):\n"
            "        self.assertEqual(banner(True), \"WELCOME\")\n"
        ),
    },
}

# Composite held-out variants: two independent defects, two isolated verify commands.
COMPOSITE_VARIANTS = (
    {
        "id": "tax-and-word",
        "left": {"target": "pricing.py", "constant": "TAX", "actual": 7, "expected": 9, "function": "tax"},
        "right": {"target": "greeting.py", "constant": "WORD", "actual": "hi", "expected": "hello", "function": "word"},
    },
    {
        "id": "items-and-title",
        "left": {"target": "limits.py", "constant": "MAX_ITEMS", "actual": 10, "expected": 12, "function": "max_items"},
        "right": {"target": "title.py", "constant": "LABEL", "actual": "draft", "expected": "final", "function": "label"},
    },
    {
        "id": "base-and-salute",
        "left": {"target": "shipping.py", "constant": "BASE", "actual": 17, "expected": 19, "function": "charge"},
        "right": {"target": "salute.py", "constant": "GREET", "actual": "hey", "expected": "welcome", "function": "greet"},
    },
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str, check: bool = True) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip() if check else (
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True).stdout.strip()
    )


def _purge_pycache(root: Path) -> None:
    """Avoid same-second stale .pyc reuse after an in-place literal edit."""
    for path in root.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)
    for path in root.rglob("*.pyc"):
        path.unlink(missing_ok=True)


def run_verify(root: Path, command: list[str]) -> subprocess.CompletedProcess:
    _purge_pycache(root)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = list(command)
    if cmd and Path(cmd[0]).name.startswith("python"):
        if "-B" not in cmd:
            cmd.insert(1, "-B")
    return subprocess.run(cmd, cwd=root, capture_output=True, timeout=30, check=False, text=True, env=env)


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def clear_package_files(root: Path) -> None:
    for item in list(root.iterdir()):
        if item.name in {".git", ".beast"}:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "beast@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "BEAST Lattice Gauntlet"], cwd=root, check=True)


def commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-qm", message], cwd=root, check=True, capture_output=True)


def module_files(spec: dict[str, Any]) -> dict[str, str]:
    target = spec["target"]
    name = Path(target).stem
    constant, actual, expected, function = spec["constant"], spec["actual"], spec["expected"], spec["function"]
    return {
        target: f"{constant} = {actual!r}\n\n\ndef {function}():\n    return {constant}\n",
        f"test_{name}.py": (
            f"import unittest\n\nimport {name}\n\n\nclass ReplayCase(unittest.TestCase):\n"
            f"    def test_{function}(self):\n        self.assertEqual({name}.{function}(), {expected!r})\n"
        ),
    }


def write_composite_variant(root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    files = {}
    files.update(module_files(variant["left"]))
    files.update(module_files(variant["right"]))
    write_tree(root, files)
    left_name = Path(variant["left"]["target"]).stem
    right_name = Path(variant["right"]["target"]).stem
    return {
        "left_verify": ["python3", "-m", "unittest", "discover", "-p", f"test_{left_name}.py", "-q"],
        "right_verify": ["python3", "-m", "unittest", "discover", "-p", f"test_{right_name}.py", "-q"],
        "combined_verify": ["python3", "-m", "unittest", "discover", "-q"],
        "left_target": variant["left"]["target"],
        "right_target": variant["right"]["target"],
        "left_test": f"test_{left_name}.py",
        "right_test": f"test_{right_name}.py",
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


def env_for(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        ENABLE_ENV: "1",
        AUTO_PROMOTE_ENV: "1",
        LATTICE_ENV: "1",
        KEY_ENV: str(root / "trial-key.pem"),
        LATTICE_LEDGER_ENV: str(root / "lattice-ledger"),
        "BEAST_COMMONS_ROOT": str(root / "commons"),
        "BEAST_COMMONS_NODE_ID": "hard-lattice-gauntlet",
        "BEAST_COMMONS_USER_ID": "gauntlet",
    })
    return env


class MeteredNIM(NIMPlannerProvider):
    def __init__(self, governor: RuntimeGovernor, model: str):
        super().__init__(model=model, base_url=HOSTED_NEMOTRON_BASE_URL, runtime_governor=governor, max_retries=1)
        self.calls = 0
        self.usage_events: list[dict[str, Any]] = []

    def _record(self):
        usage = dict(getattr(self, "last_usage", {}) or {})
        token_usage = usage.get("usage") if isinstance(usage.get("usage"), dict) else {}
        self.usage_events.append({
            "prompt_tokens": int(token_usage.get("prompt_tokens") or 0),
            "completion_tokens": int(token_usage.get("completion_tokens") or 0),
            "total_tokens": int(token_usage.get("total_tokens") or 0),
        })

    def _request_json(self, payload):
        self.calls += 1
        result = super()._request_json(payload)
        self._record()
        return result

    def _request_stream(self, payload):
        self.calls += 1
        result = super()._request_stream(payload)
        self._record()
        return result


class NoModel:
    last_route = {"provider": "none", "engine": "none", "route_kind": "replay_no_model", "reason": "heldout_replay"}

    def __init__(self) -> None:
        self.calls = 0

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
        from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

        self.calls += 1
        return PlannerDecision(decision_type=PlannerDecisionType.BLOCKED,
                               blocker="held-out replay never consults a model")


def estimate_spend(model: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    price = NIM_PRICE.get(model, {"input": 0.0, "output": 0.0})
    prompt = sum(int(e.get("prompt_tokens") or 0) for e in events)
    completion = sum(int(e.get("completion_tokens") or 0) for e in events)
    billable = os.environ.get("BEAST_NIM_BILLABLE", "").strip().lower() in {"1", "true", "yes"}
    list_usd = (prompt / 1_000_000) * float(price["input"]) + (completion / 1_000_000) * float(price["output"])
    return {
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "estimated_usd": round(list_usd, 6) if billable else 0.0,
        "commercial_equivalent_usd": round(list_usd, 6) if price["input"] or price["output"] else None,
        "pricing_note": (
            "NVIDIA hosted trial endpoint (integrate.api.nvidia.com) is free for prototyping; "
            "commercial_equivalent_usd uses public list prices from modelmenu.dev (checked Nov 2026) "
            "and is not a charge on this run."
        ),
        "calls": len(events),
    }


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, default=str)
    path.write_text(payload + "\n", encoding="utf-8")
    print(payload, flush=True)


def model_governor(root: Path) -> RuntimeGovernor:
    return RuntimeGovernor(
        policies={"providers": {"nvidia_nim": {"enabled": True, "runtime_max_concurrent": 1}}},
        db_path=str(root / "nim-runtime.sqlite3"),
    )


def lattice_snapshot(planner) -> dict[str, Any]:
    lattice = getattr(planner, "lattice", None)
    if lattice is None:
        return {"present": False}
    nodes = lattice.nodes()
    edges = lattice.edges()
    return {
        "present": True,
        "verify": lattice.verify(),
        "nodes": nodes,
        "edges": edges,
        "leaf_count": sum(1 for n in nodes if n.get("kind") == "crystal" and n.get("status") == "admitted"),
        "composite_count": sum(1 for n in nodes if n.get("kind") == "composite" and n.get("status") == "admitted"),
        "composes_with": [e for e in edges if e.get("edge_type") == "COMPOSES_WITH"],
    }


def run_package(root: Path, package: dict[str, Any], provider, *, envelopes: EpisodeEnvelopeStore,
                planner=None, learner=None, model: str, session_id: str) -> dict[str, Any]:
    clear_package_files(root)
    write_tree(root, package["files"])
    commit_all(root, f"fixture {package['name']}")
    fingerprints = {rel: digest(root / rel) for rel in package["files"]}
    before = run_verify(root, package["verify"]).returncode
    if before != 1:
        raise RuntimeError(f"Fixture {package['name']} precheck expected failures, got rc={before}")
    engine = AgentRunEngine(root)
    command = list(package["verify"])
    target = package["target"]
    tests = list(package["tests"])
    context = [rel for rel in package["files"] if not Path(rel).name.startswith("test_")]
    run = engine.create_run(
        session_id=session_id, mode="agent", provider="nvidia_nim", model=model,
        objective=(
            f"Fix the failing assertions in this package by changing only the single incorrect constant "
            f"in {target}. Read {target} and the tests {', '.join(tests)}. Never edit tests. Bind the "
            f"worktree and run the existing unittest before and after your exact replacement. "
            f"Verification command: {' '.join(command)}. Use the failing assertion output to select the "
            "literal. For old_text and new_text, supply the assignment line only."
        ),
        request={"task_family": FAMILY, "implementation_target": target,
                 "required_test_files": tests, "context_files": context,
                 "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
                 "autonomy": "autopilot",
                 "trial_model_only": planner is None},
    )
    run_id = run["run_id"]
    engine.store.create_approval(run_id, {"request_id": "mutate", "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, "mutate", {"approved": True, "scope": "run"})
    engine.store.create_approval(run_id, {"request_id": "verify", "tool_id": "worktree.verify",
                                          "safe_arguments": {"command": command},
                                          "capabilities": [{"id": "worktree.verify"}]})
    engine.store.resolve_approval(run_id, "verify", {"approved": True, "scope": "run"})
    start = time.monotonic()
    runtime = AgentPlannerRuntime(
        engine, provider, max_turns=16, observation_limit=32,
        envelope_store=envelopes, crystal_planner=planner, crystal_learner=learner,
        integration_coordinator=CoderIntegrationCoordinator(root, environ={}),
    )
    final = asyncio.run(runtime.run(run_id, defer_approval=True))
    events = engine.store.events(run_id, limit=10000)
    checkpoint = final.get("checkpoint") or {}
    worktree = checkpoint.get("worktree_root")
    changed, independent_pass = [], False
    if worktree:
        wt = Path(worktree)
        changed = sorted(p for p in git(wt, "diff", "--name-only", "HEAD").splitlines() if p)
        tests_unchanged = all((wt / rel).is_file() and digest(wt / rel) == fingerprints[rel] for rel in tests)
        expected = set(package.get("expected_change") or [target])
        independent_pass = (
            tests_unchanged and set(changed) == expected and run_verify(wt, command).returncode == 0
        )
    try:
        sealed = envelopes.get(run_id).verification.get("passed") is True
    except LookupError:
        sealed = False
    observations = (checkpoint.get("planner") or {}).get("observations", [])
    original_unchanged = all(digest(root / rel) == fingerprints[rel] for rel in package["files"])
    usage_events = list(getattr(provider, "usage_events", []))
    # Only count usage recorded during this call.
    prior = getattr(provider, "_usage_cursor", 0)
    new_events = usage_events[prior:]
    provider._usage_cursor = len(usage_events)
    return {
        "run_id": run_id,
        "package": package["name"],
        "state": final.get("state"),
        "before_rc": before,
        "event_chain_valid": engine.store.verify_chain(run_id).get("ok") is True,
        "independent_pass": independent_pass and original_unchanged,
        "sealed_pass": sealed,
        "crystal_completed": any(e["event_type"] == "agent.crystal.completed" for e in events),
        "crystal_formed": any(e["event_type"] == "agent.crystal.formed" for e in events),
        "crystal_activated": any(e["event_type"] == "agent.crystal.activated" for e in events),
        "crystal_refusals": [e["payload"].get("reason") for e in events if e["event_type"] == "agent.crystal.aborted"],
        "changed_tracked_paths": changed,
        "original_unchanged": original_unchanged,
        "mutation_observed": any(o.get("tool_id") == "worktree.replace_exact" and o.get("status") == "completed"
                                 for o in observations),
        "observed_provider_attempts": getattr(provider, "calls", 0),
        "model_turns": (final.get("budget") or {}).get("model_turns", 0),
        "tool_calls": (final.get("budget") or {}).get("tool_calls", 0),
        "wall_seconds": round(time.monotonic() - start, 3),
        "usage": estimate_spend(model, new_events),
        "events": [e.get("event_type") for e in events if str(e.get("event_type") or "").startswith("agent.crystal.")],
    }


def good_source(arm: dict[str, Any]) -> bool:
    return (arm["state"] == "completed" and arm["independent_pass"]
            and arm["sealed_pass"] and arm["event_chain_valid"])


def promote_and_admit(hub: Path, env: dict[str, str], run_id: str, approved_by: str) -> dict[str, Any]:
    learned = learn_from_run(hub, run_id, env=env, approved_by=approved_by)
    extras = planner_runtime_extras(hub, env=env)
    planner = extras["crystal_planner"]
    admitted = False
    witness = {}
    if learned.get("status") == "promoted" and planner.lattice is not None:
        crystal_id = learned["crystal_id"]
        try:
            node = planner.lattice.node(crystal_id)
            admitted = node.get("status") == "admitted"
        except LookupError:
            result = planner.lattice.add_crystal(crystal_id, publisher_id=planner.authority.key_id)
            witness = result.get("witness") or {}
            admitted = result["node"].get("status") == "admitted"
        except ValueError as exc:
            learned["lattice_error"] = str(exc)
    learned["lattice_admitted"] = admitted
    learned["lattice_witness"] = witness
    learned["lattice"] = lattice_snapshot(planner)
    return learned


def replay_named_crystal(root: Path, planner, crystal_id: str, *, target: str, test: str,
                         command: list[str]) -> dict[str, Any]:
    replay_planner = CodingCrystalPlanner(
        planner.registry, planner.authority, planner.ledger,
        replay_candidate_id=crystal_id, economy=planner.economy, lattice=planner.lattice,
    )
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="composite-heldout", objective="held-out composite child replay",
        mode="agent", provider="none", model="none", request={
            "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
            "required_test_files": [test], "context_files": [target],
            "implementation_target": target, "task_family": FAMILY,
        },
    )["run_id"]
    engine.store.create_approval(run_id, {"request_id": "mutate", "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, "mutate", {"approved": True, "scope": "run"})
    engine.store.create_approval(run_id, {"request_id": "verify", "tool_id": "worktree.verify",
                                          "safe_arguments": {"command": command},
                                          "capabilities": [{"id": "worktree.verify"}]})
    engine.store.resolve_approval(run_id, "verify", {"approved": True, "scope": "run"})
    provider = NoModel()
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=14, crystal_planner=replay_planner).run(run_id))
    events = engine.store.events(run_id, limit=1000)
    return {
        "run_id": run_id,
        "state": final.get("state"),
        "provider_calls": provider.calls,
        "completed": final.get("state") == "completed",
        "zero_inference": provider.calls == 0,
        "crystal_completed": any(e["event_type"] == "agent.crystal.completed" for e in events),
        "isolated_pass": run_verify(Path((final.get("checkpoint") or {}).get("worktree_root") or root), command).returncode == 0
        if (final.get("checkpoint") or {}).get("worktree_root") else run_verify(root, command).returncode == 0,
        "worktree": (final.get("checkpoint") or {}).get("worktree_root"),
    }


def replay_composite_variant(base: Path, planner, left_id: str, right_id: str, variant: dict[str, Any]) -> bool:
    root = base / variant["id"]
    if root.exists():
        shutil.rmtree(root)
    init_repo(root)
    meta = write_composite_variant(root, variant)
    commit_all(root, f"composite variant {variant['id']}")
    if run_verify(root, meta["combined_verify"]).returncode == 0:
        return False
    left = replay_named_crystal(root, planner, left_id, target=meta["left_target"], test=meta["left_test"],
                                command=meta["left_verify"])
    # Child A must fix only its isolated tests; the shared repo files live in the worktree.
    worktree = Path(left["worktree"] or root)
    if not (left["completed"] and left["zero_inference"] and left["crystal_completed"]
            and run_verify(worktree, meta["left_verify"]).returncode == 0
            and run_verify(worktree, meta["combined_verify"]).returncode != 0):
        return False
    # Continue the second child from a sibling repo, not a subdirectory of the
    # first worktree's git root. A nested path can bind against the parent
    # snapshot and drop the first leaf's edit.
    stage = root.parent / f"{variant['id']}-after-left"
    if stage.exists():
        shutil.rmtree(stage)
    # Do not copy the first worktree's .git file: it points back at the parent
    # repo, and a later bind would snapshot the unfixed parent tree.
    shutil.copytree(worktree, stage, ignore=shutil.ignore_patterns(".beast", ".git"))
    init_repo(stage)
    commit_all(stage, "after-left-leaf")
    right = replay_named_crystal(stage, planner, right_id, target=meta["right_target"], test=meta["right_test"],
                                 command=meta["right_verify"])
    right_tree = Path(right["worktree"] or stage)
    return bool(
        right["completed"] and right["zero_inference"] and right["crystal_completed"]
        and run_verify(right_tree, meta["right_verify"]).returncode == 0
        and run_verify(right_tree, meta["combined_verify"]).returncode == 0
    )


def fixtures_ok() -> list[str]:
    errors = []
    with tempfile.TemporaryDirectory(prefix="beast-lattice-fixtures-") as raw:
        root = Path(raw)
        for package in (PACKAGE_BURST, PACKAGE_QUOTA, PACKAGE_VOICE, PACKAGE_SALUTE):
            init_repo(root)
            clear_package_files(root)
            write_tree(root, package["files"])
            if run_verify(root, package["verify"]).returncode == 0:
                errors.append(f"{package['name']} unexpectedly passed before the fix")
        # Manual repairs should pass.
        cases = [
            (PACKAGE_BURST, "rate_limit.py", "BURST_LIMIT = 24", "BURST_LIMIT = 32"),
            (PACKAGE_QUOTA, "quota.py", "MAX_ITEMS = 10", "MAX_ITEMS = 12"),
            (PACKAGE_VOICE, "voice.py", 'GREETING = "hi"', 'GREETING = "hello"'),
            (PACKAGE_SALUTE, "salute.py", 'WORD = "hey"', 'WORD = "welcome"'),
        ]
        for package, path, old, new in cases:
            clear_package_files(root)
            write_tree(root, package["files"])
            text = (root / path).read_text()
            (root / path).write_text(text.replace(old, new, 1))
            if run_verify(root, package["verify"]).returncode != 0:
                errors.append(f"{package['name']} still failed after the manual root-cause edit")
        # Composite variant is red until both sides are fixed.
        croot = root / "composite"
        init_repo(croot)
        meta = write_composite_variant(croot, COMPOSITE_VARIANTS[0])
        if run_verify(croot, meta["combined_verify"]).returncode == 0:
            errors.append("composite variant passed before either leaf was applied")
        left, right = COMPOSITE_VARIANTS[0]["left"], COMPOSITE_VARIANTS[0]["right"]
        (croot / meta["left_target"]).write_text(
            (croot / meta["left_target"]).read_text().replace(
                f"{left['constant']} = {left['actual']!r}",
                f"{left['constant']} = {left['expected']!r}",
                1,
            )
        )
        if run_verify(croot, meta["left_verify"]).returncode != 0:
            errors.append("composite left isolated tests failed after left fix")
        if run_verify(croot, meta["combined_verify"]).returncode == 0:
            errors.append("composite combined tests passed after only the left fix")
        (croot / meta["right_target"]).write_text(
            (croot / meta["right_target"]).read_text().replace(
                f"{right['constant']} = {right['actual']!r}",
                f"{right['constant']} = {right['expected']!r}",
                1,
            )
        )
        if run_verify(croot, meta["combined_verify"]).returncode != 0:
            errors.append("composite combined tests failed after both fixes")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("fixtures", "form-leaves", "reuse", "composite", "all"), default="all")
    parser.add_argument("--approve-by", default="Byron")
    parser.add_argument("--model", default=os.environ.get("BEAST_LIVE_CRYSTAL_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    os.chdir(ROOT)
    vault = SecretVault().load()
    if not os.environ.get("NVIDIA_API_KEY") and args.phase not in {"fixtures"}:
        parser.error("NVIDIA_API_KEY was not loaded from the local secret vault. No key was printed.")
    # Never persist vault summaries with fingerprints into evidence if avoidable; presence only.
    print(json.dumps({
        "vault_loaded": bool(vault.get("exists")),
        "nvidia_present": bool(os.environ.get("NVIDIA_API_KEY")),
        "fireworks_present": bool(os.environ.get("FIREWORKS_API_KEY")),
        "model": args.model,
        "phase": args.phase,
    }), flush=True)

    if args.phase in {"fixtures", "all"}:
        errors = fixtures_ok()
        if errors:
            print("FIXTURE FAILURES:", *errors, sep="\n- ", flush=True)
            return 2
        print("fixtures ok", flush=True)
        if args.phase == "fixtures":
            return 0

    evidence = args.evidence_dir.expanduser().resolve()
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    report_path = evidence / "report.json"
    report: dict[str, Any] = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    report.setdefault("model", args.model)
    report.setdefault("tasks", [])
    report.setdefault("spend", [])

    hub = evidence / "workspace"
    key_path = evidence / "trial-key.pem"
    if not key_path.exists():
        new_local_key(key_path)
    env = env_for(evidence)
    init_repo(hub)
    extras = planner_runtime_extras(hub, env=env)
    if not extras:
        raise RuntimeError("coding crystals did not enable on the evidence workspace")
    planner = extras["crystal_planner"]
    envelopes = extras["envelope_store"]
    learner = extras.get("crystal_learner")
    governor = model_governor(evidence)
    os.environ.setdefault("BEAST_NIM_MAX_TOKENS", "4096")

    def persist() -> None:
        report["lattice"] = lattice_snapshot(planner)
        report["spend_total"] = {
            "prompt_tokens": sum(s.get("prompt_tokens") or 0 for s in report["spend"]),
            "completion_tokens": sum(s.get("completion_tokens") or 0 for s in report["spend"]),
            "estimated_usd": round(sum(float(s.get("estimated_usd") or 0) for s in report["spend"]), 6),
        }
        save(report_path, report)

    if args.phase in {"form-leaves", "all"}:
        provider = MeteredNIM(governor, args.model)
        for key, package in (("leaf_a", PACKAGE_BURST), ("leaf_b", PACKAGE_VOICE)):
            existing = next((t for t in report["tasks"] if t.get("id")==key and t.get("status")=="promoted"
                             and (t.get("formation") or {}).get("lattice_admitted")), None)
            if existing:
                print(f"{key} already promoted and admitted; skipping live formation", flush=True)
                continue
            # Formation must not see an already-admitted sibling, or the second
            # leaf is skipped as reuse (same fix-failing-assertion family).
            arm = run_package(hub, package, provider, envelopes=envelopes, planner=None, learner=None,
                              model=args.model, session_id=f"hard-lattice-{key}")
            # Provider.calls is cumulative; record per-arm attempts from usage.
            arm["observed_provider_attempts"] = arm["usage"]["calls"]
            task = {"id": key, "kind": "formation", "source": arm, "status": "capture_not_proven"}
            report["spend"].append(arm["usage"])
            if good_source(arm) and arm["usage"]["calls"] > 0 and not arm["crystal_completed"]:
                task["formation"] = promote_and_admit(hub, env, arm["run_id"], args.approve_by)
                task["status"] = task["formation"].get("status")
            elif arm["crystal_completed"]:
                task["status"] = "reused_existing_crystal"
                task["formation"] = {"status": "skipped", "reason": "episode_used_existing_crystal"}
            report["tasks"] = [t for t in report["tasks"] if t.get("id") != key] + [task]
            persist()
            if task["status"] != "promoted" or not (task.get("formation") or {}).get("lattice_admitted"):
                print(f"{key} did not promote and admit; stopping before later phases", flush=True)
                persist()
                return 1
        # Refresh planner after admissions.
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]

    if args.phase in {"reuse", "all"}:
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]
        # Use a fresh MeteredNIM so crystal-off spend is isolated per arm.
        rows = []
        for key, package in (("reuse_a", PACKAGE_QUOTA), ("reuse_b", PACKAGE_SALUTE)):
            row = {"id": key, "package": package["name"]}
            for arm_name, use_planner in (("off", False), ("on", True)):
                provider = MeteredNIM(governor, args.model)
                arm = run_package(
                    hub, package, provider, envelopes=EpisodeEnvelopeStore(evidence / f"{key}-{arm_name}.sqlite3"),
                    planner=planner if use_planner else None, learner=None,
                    model=args.model, session_id=f"hard-lattice-{key}-{arm_name}",
                )
                arm["observed_provider_attempts"] = arm["usage"]["calls"]
                report["spend"].append(arm["usage"])
                row[arm_name] = arm
            off, on = row["off"], row["on"]
            row["passed"] = (
                good_source(off) and good_source(on)
                and not off["crystal_completed"] and on["crystal_completed"]
                and off["observed_provider_attempts"] > on["observed_provider_attempts"]
                and on["observed_provider_attempts"] == 0
                and on["model_turns"] == 0
            )
            rows.append(row)
            report["tasks"] = [t for t in report["tasks"] if t.get("id") != key] + [
                {"id": key, "kind": "reuse", **row, "status": "pass" if row["passed"] else "not_proven"}
            ]
            persist()
        report["reuse_all_passed"] = all(r["passed"] for r in rows)
        persist()

    if args.phase in {"composite", "all"}:
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]
        leaves = [n for n in planner.lattice.nodes() if n.get("kind") == "crystal" and n.get("status") == "admitted"]
        if len(leaves) < 2:
            report["composite"] = {"status": "not_attempted", "reason": "fewer_than_two_admitted_leaves",
                                   "leaf_count": len(leaves)}
            persist()
            return 1
        # Use the two formation crystals in admission order.
        left_id, right_id = leaves[0]["node_id"], leaves[1]["node_id"]
        left = planner.registry.get(left_id)["candidate_object"]
        right = planner.registry.get(right_id)["candidate_object"]
        # Shared envelope digest for the composite witness: bind to leaf A's source episode.
        source_digest = left.source_envelope_digest
        composite = compose_candidates(
            [left, right], task_family=COMPOSITE_FAMILY, source_run_id="hard-lattice-composite",
            source_envelope_digest=source_digest,
            learned_budget={k: float(v) for k, v in (left.learned_budget or {"cpu_ms": 1, "tokens": 1}).items()},
        )
        gate = HeldOutReplayGate()
        base = evidence / "composite-heldout"
        receipt = gate.evaluate(
            composite.crystal_id, list(COMPOSITE_VARIANTS),
            lambda variant: replay_composite_variant(base, planner, left_id, right_id, variant),
            minimum_successes=3,
            envelope_digest=source_digest,
            reproduction={"mode": "live_composite", "left": left_id, "right": right_id, "approved_by": args.approve_by},
        )
        admitted = planner.lattice.admit_composite(
            composite, verifier=receipt, publisher_id=planner.authority.key_id, approved_by=args.approve_by,
        )
        snapshot = lattice_snapshot(planner)
        live_edge = (
            admitted.get("outcome") == "ADMIT"
            and receipt.promoted and receipt.successes == 3 and receipt.attempts == 3
            and any(e.get("edge_type") == "COMPOSES_WITH"
                    and set(e.get("source_ids") or []) == {left_id, right_id}
                    and e.get("target_id") == composite.crystal_id
                    for e in snapshot.get("edges") or [])
        )
        report["composite"] = {
            "status": "live_composite_admitted" if live_edge else "not_proven",
            "left_id": left_id,
            "right_id": right_id,
            "crystal_id": composite.crystal_id,
            "receipt": {
                "attempts": receipt.attempts,
                "successes": receipt.successes,
                "promoted": receipt.promoted,
                "reason": receipt.reason,
                "structured": receipt.structured,
                "evidence_root": receipt.evidence_root,
                "variant_ids": list(receipt.variant_ids),
                "variant_results": list(receipt.variant_results),
            },
            "admission": admitted,
            "live_composite_edge": live_edge,
            "lattice": snapshot,
        }
        persist()
        return 0 if live_edge else 1

    persist()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
