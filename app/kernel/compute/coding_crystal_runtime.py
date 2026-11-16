"""Production wiring for reviewed coding crystals (default OFF).

Enable with ``BEAST_CODING_CRYSTALS=1``. Activation capabilities are signed with
the existing ARDA runtime Ed25519 key, loaded by path only (never copied, printed
or re-permissioned); a key readable by group/other fails closed. Durable state
lives under ``<workspace>/.beast``.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

ENABLE_ENV = "BEAST_CODING_CRYSTALS"
KEY_ENV = "BEAST_CODING_CRYSTAL_KEY"
DEFAULT_KEY_PATH = Path("~/.local/state/beast/compute_plane/authority/arda-runtime-ed25519.pem").expanduser()
FAMILY = "fix-failing-assertion"


def _enabled(env: Mapping[str, str]) -> bool:
    return str(env.get(ENABLE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


NODE_ENV = "BEAST_COMMONS_NODE_ID"
LATTICE_ENV = "BEAST_CRYSTAL_LATTICE"
USER_ENV = "BEAST_COMMONS_USER_ID"
DEFAULT_NODE_ID = "beast-control-plane"


def _paths(workspace: Path) -> dict[str, Path]:
    beast = Path(workspace).expanduser().resolve() / ".beast"
    return {
        "registry": beast / "crystals" / "coding_crystals.sqlite3",
        "ledger": beast / "crystals" / "coding_crystal_capabilities.sqlite3",
        "envelopes": beast / "sensorium" / "episode_envelopes.sqlite3",
        "shadow_ledger": beast / "crystals" / "coding_crystal_shadow_ledger.sqlite3",
    }


def _load_key(env: Mapping[str, str]) -> tuple[Any, str]:
    """Return (private_key, reason). The key material never leaves this function's caller objects."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    path = Path(str(env.get(KEY_ENV) or DEFAULT_KEY_PATH)).expanduser()
    try:
        info = path.stat()
    except OSError:
        return None, "key_missing"
    if not stat.S_ISREG(info.st_mode):
        return None, "key_invalid"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return None, "key_permissions_too_open"
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (ValueError, TypeError, OSError):
        return None, "key_invalid"
    if not isinstance(key, Ed25519PrivateKey):
        return None, "key_invalid"
    return key, "ready"


def _key_id(key: Any) -> str:
    from cryptography.hazmat.primitives import serialization

    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "arda-runtime-ed25519:" + hashlib.sha256(public).hexdigest()[:16]


def _build(workspace: Path, env: Mapping[str, str]) -> tuple[dict[str, Any], str]:
    if not _enabled(env):
        return {}, "disabled"
    key, reason = _load_key(env)
    if key is None:
        return {}, reason
    from app.kernel.compute.coding_crystals import CodingCrystalAuthority, CodingCrystalPlanner, CodingCrystalRegistry
    from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

    paths = _paths(workspace)
    authority = CodingCrystalAuthority(key, key_id=_key_id(key))
    ledger = OneUseCapabilityLedger({CodingCrystalAuthority.AUTHORITY: authority.verifier()}, paths["ledger"])
    registry = CodingCrystalRegistry(paths["registry"])
    from app.kernel.compute.crystal_economy import CrystalReuseEconomy, CrystalShadowLedger

    envelopes = EpisodeEnvelopeStore(paths["envelopes"])
    from app.kernel.governance.governor_spine import (
        ComputeGovernorSpine,
        GovernorReceiptLog,
        enforcement_enabled,
        forensic_sink,
    )

    governor = None
    if enforcement_enabled(env):  # Compute Governor spine, default off: D7 settles only from governor receipts
        beast = paths["registry"].parent.parent
        governor = ComputeGovernorSpine(enforce=True, receipts=GovernorReceiptLog(
            beast / "governor" / "receipts.jsonl", sinks=[forensic_sink(beast / "evidence" / "governor")]))
    shadow = CrystalShadowLedger(paths["shadow_ledger"], local_node_id=str(env.get(NODE_ENV) or DEFAULT_NODE_ID),
                                 local_publisher_id=authority.key_id,
                                 governor_settlement=governor.receipts.settle if governor else None)
    economy = CrystalReuseEconomy(shadow, envelope_store=envelopes, local_user_id=str(env.get(USER_ENV) or "operator"))
    lattice = None
    if str(env.get(LATTICE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}:  # lattice spine, default off
        from app.kernel.compute.crystal_lattice_spine import default_lattice

        lattice = default_lattice(workspace, registry)
    extras: dict[str, Any] = {
        "crystal_planner": CodingCrystalPlanner(registry, authority, ledger, economy=economy, lattice=lattice),
        "envelope_store": envelopes,
    }
    from app.kernel.compute.adaptive_router import CodingCrystalRouter, router_enabled

    if router_enabled(env):  # D9, default off: routing nominates; D6 activation gates still decide
        extras["adaptive_router"] = CodingCrystalRouter(registry, envelopes, lattice=lattice)
    if governor is not None:
        governor.lattice = lattice
        extras["governor"] = governor
        from app.kernel.governance.memory_contract import MemoryReader, crystal_source

        extras["memory_reader"] = MemoryReader(exact=[crystal_source(registry)])  # Perceive tier 1 (exact ids)
    return extras, "ready"


def planner_runtime_extras(workspace: str | Path, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Keyword arguments for ``AgentPlannerRuntime``; empty (crystals off) unless enabled and the key is sound."""
    extras, _ = _build(Path(workspace), os.environ if env is None else env)
    return extras


def crystal_runtime_status(workspace: str | Path, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if env is None else env
    extras, reason = _build(Path(workspace), env)
    status: dict[str, Any] = {"enabled": bool(extras), "reason": reason, "flag": ENABLE_ENV,
                              "key_path": str(Path(str(env.get(KEY_ENV) or DEFAULT_KEY_PATH)).expanduser())}
    if extras:
        planner = extras["crystal_planner"]
        status.update({"key_id": planner.authority.key_id, "registry": str(planner.registry.path),
                       "promoted": planner.registry.active_for_family(FAMILY) is not None})
    return status


# --- offline learning: extract → held-out replay on synthetic variants → promote --------------

_VARIANTS = (
    {"module": "pricing", "constant": "TAX", "actual": 7, "expected": 9, "function": "tax"},
    {"module": "limits", "constant": "MAX_ITEMS", "actual": 10, "expected": 12, "function": "max_items"},
    {"module": "greeting", "constant": "WORD", "actual": "hi", "expected": "hello", "function": "word"},
)


def _variant_repo(root: Path, variant: Mapping[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    module, constant, function = variant["module"], variant["constant"], variant["function"]
    git("init", "-q")
    git("config", "user.email", "beast@example.invalid")
    git("config", "user.name", "BEAST Crystal Replay")
    (root / f"{module}.py").write_text(f"{constant} = {variant['actual']!r}\n\n\ndef {function}():\n    return {constant}\n",
                                       encoding="utf-8")
    (root / f"test_{module}.py").write_text(
        f"import unittest\n\nimport {module}\n\n\nclass ReplayCase(unittest.TestCase):\n    def test_{function}(self):\n"
        f"        self.assertEqual({module}.{function}(), {variant['expected']!r})\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "variant")


class _NoModel:
    """Held-out replay must not consult any model."""

    last_route = {"provider": "none", "engine": "none", "route_kind": "replay_no_model", "reason": "heldout_replay"}

    def __init__(self) -> None:
        self.calls = 0

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
        from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

        self.calls += 1
        return PlannerDecision(decision_type=PlannerDecisionType.BLOCKED, blocker="held-out replay never consults a model")


def _replay_variant(root: Path, planner: Any, variant: Mapping[str, Any]) -> bool:
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.agents.run_engine import AgentRunEngine

    _variant_repo(root, variant)
    module = variant["module"]
    command = ["python3", "-m", "unittest", "discover", "-p", f"test_{module}.py", "-q"]
    engine = AgentRunEngine(root)
    run_id = engine.create_run(session_id="coding-crystal-replay", objective="held-out replay", mode="agent",
                               provider="none", model="none", request={
                                   "post_session_closure": "verified_handoff", "post_session_test_runner": "unittest",
                                   "required_test_files": [f"test_{module}.py"], "context_files": [f"{module}.py"],
                                   "implementation_target": f"{module}.py", "task_family": FAMILY})["run_id"]
    engine.store.create_approval(run_id, {"request_id": "mutate", "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, "mutate", {"approved": True, "scope": "run"})
    engine.store.create_approval(run_id, {"request_id": "verify", "tool_id": "worktree.verify",
                                          "safe_arguments": {"command": command}, "capabilities": [{"id": "worktree.verify"}]})
    engine.store.resolve_approval(run_id, "verify", {"approved": True, "scope": "run"})
    provider = _NoModel()
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=14, crystal_planner=planner).run(run_id))
    events = engine.store.events(run_id, limit=1000)
    return (final.get("state") == "completed" and provider.calls == 0
            and any(e["event_type"] == "agent.crystal.completed" for e in events))


def learn_from_run(workspace: str | Path, run_id: str, *, env: Mapping[str, str] | None = None,
                   scratch: str | Path | None = None, approved_by: str = "") -> dict[str, Any]:
    """Extract a candidate from a sealed run, replay it on 3 held-out variants without a model, promote if all pass."""
    from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalPlanner, replay_candidate

    env = os.environ if env is None else env
    extras, reason = _build(Path(workspace), env)
    if not extras:
        raise PermissionError(f"coding crystals are not enabled: {reason}")
    planner = extras["crystal_planner"]
    registry = planner.registry
    envelope = extras["envelope_store"].get(run_id)
    from app.kernel.agents.run_engine import AgentRunEngine

    run = AgentRunEngine(Path(workspace)).store.get_run(run_id) or {}
    observations = ((run.get("checkpoint") or {}).get("planner") or {}).get("observations") or []
    candidate = CodingCrystalExtractor().extract(envelope, observations, registry=registry)
    if candidate is None:
        negatives = registry.negatives(envelope.task_family)
        return {"status": "refused", "reason": negatives[-1]["kind"] if negatives else "refused", "run_id": run_id}
    registry.add_candidate(candidate)
    replay_planner = CodingCrystalPlanner(registry, planner.authority, planner.ledger, replay_candidate_id=candidate.crystal_id,
                                          economy=planner.economy)
    base = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="beast-crystal-replay-"))
    try:
        receipt = replay_candidate(registry, candidate, list(_VARIANTS),
                                   lambda variant: _replay_variant(base / variant["module"], replay_planner, variant),
                                   promote=bool(approved_by.strip()),
                                   reproduction={"mode": "learn", "run_id": run_id,
                                                 "approved_by": approved_by.strip() or None})
    finally:
        if scratch is None:
            shutil.rmtree(base, ignore_errors=True)
    return {"status": _status(receipt, approved_by), "crystal_id": candidate.crystal_id,
            "receipt": asdict(receipt), "run_id": run_id, "approved_by": approved_by.strip() or None}


def _status(receipt: Any, approved_by: str) -> str:
    if not receipt.promoted:
        return "replay_failed"
    return "promoted" if approved_by.strip() else "verified_awaiting_operator_promotion"


def _require(workspace: str | Path, env: Mapping[str, str] | None) -> dict[str, Any]:
    extras, reason = _build(Path(workspace), os.environ if env is None else env)
    if not extras:
        raise PermissionError(f"coding crystals are not enabled: {reason}")
    return extras


def publication_bundle(workspace: str | Path, crystal_id: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Signed, privacy-filtered bundle for a locally promoted crystal (signed with the runtime key)."""
    from app.kernel.compute.crystal_publication import build_publication_bundle

    planner = _require(workspace, env)["crystal_planner"]
    record = planner.registry.get(crystal_id)
    return build_publication_bundle(record, planner.authority, key_id=planner.authority.key_id)


def stage_bundle(bundle: Mapping[str, Any], stage: str | Path) -> dict[str, Any]:
    """Write the dataset layout locally (offline), using the ForgeKV atomic writer."""
    from app.kernel.compute.crystal_publication import DATASET_CARD, _chunk_path
    from app.kernel.compute.forge_kv_dataset_writer import _atomic_write

    root = Path(stage)
    prefix = root / "crystals" / str(bundle["task_family"]) / str(bundle["crystal_id"])
    for name, data in bundle["files"].items():
        _atomic_write(prefix / name, data)
    for digest, payload in bundle["chunks"].items():
        _atomic_write(root / _chunk_path(digest), payload)
    _atomic_write(root / "README.md", DATASET_CARD.encode("utf-8"))
    return {"staged": str(root), "crystal_id": bundle["crystal_id"], "bundle_digest": bundle["bundle_digest"],
            "online_published": False}


def reproduce_imported(workspace: str | Path, crystal_id: str, *, env: Mapping[str, str] | None = None,
                       scratch: str | Path | None = None, approved_by: str = "") -> dict[str, Any]:
    """Promote a quarantined (imported) crystal only after no-model held-out reproduction on this node."""
    from app.kernel.compute.coding_crystals import CodingCrystalPlanner
    from app.kernel.compute.crystal_publication import reproduce_quarantined

    planner = _require(workspace, env)["crystal_planner"]
    replay_planner = CodingCrystalPlanner(planner.registry, planner.authority, planner.ledger, replay_candidate_id=crystal_id,
                                          economy=planner.economy)
    base = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="beast-crystal-repro-"))
    try:
        receipt = reproduce_quarantined(planner.registry, crystal_id, list(_VARIANTS),
                                        lambda variant: _replay_variant(base / variant["module"], replay_planner, variant),
                                        promote=bool(approved_by.strip()))
    finally:
        if scratch is None:
            shutil.rmtree(base, ignore_errors=True)
    status = _status(receipt, approved_by)
    return {"status": "still_quarantined" if status == "replay_failed" else status, "crystal_id": crystal_id,
            "receipt": asdict(receipt), "approved_by": approved_by.strip() or None}
