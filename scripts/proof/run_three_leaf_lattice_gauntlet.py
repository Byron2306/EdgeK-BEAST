#!/usr/bin/env python3
"""Harder 3-leaf live coding-crystal / lattice gauntlet.

Forms three fresh multi-file defect families (integer, string, boolean/branch)
from live NIM repairs. Each leaf must seal, pass 3/3 held-out replay, and
admit to the lattice. Reuse is measured off vs on for a sibling variant of
each family. A 3-way composite is then verified on three-defect held-out
variants with no model calls. If the earlier 2-leaf composite
(coding-crystal:d6408abd53c27ec6a8a58507) can be imported, a nested
composite (that composite plus a new leaf) is attempted.

Refactor-only tasks are not formed here: learn_from_run still requires a
failing verification before a passing one (failures_before_pass >= 1) around
an exact replacement. An episode that only refactors green tests never
seals a crystal.

Tasks run on temporary copies under an evidence workspace. Production
services are not touched. Provider secret values are never printed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_HELPERS = Path(__file__).resolve().parent / "run_hard_lattice_gauntlet.py"
_spec = importlib.util.spec_from_file_location("hard_lattice_gauntlet_helpers", _HELPERS)
hg = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hg)

from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras
from app.kernel.compute.crystal_lattice_spine import compose_candidates
from app.kernel.compute.heldout_replay import HeldOutReplayGate, ReplayReceipt
from app.kernel.security.secret_vault import SecretVault
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

FAMILY = hg.FAMILY
TRIPLE_FAMILY = "fix-three-assertions"
NESTED_FAMILY = "fix-nested-assertions"
DEFAULT_MODEL = hg.DEFAULT_MODEL
PREVIOUS_COMPOSITE_ID = "coding-crystal:d6408abd53c27ec6a8a58507"
PREVIOUS_EVIDENCE = ROOT / ".beast/evidence/hard-lattice-gauntlet-20261125-b"

# Leaf I: integer root cause (fresh names/values, not burst/quota).
PACKAGE_RETRY = {
    "name": "retry-budget",
    "target": "retry_budget.py",
    "tests": ["test_retry_budget.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_retry_budget.py", "-q"],
    "expected_change": ["retry_budget.py"],
    "files": {
        "retry_budget.py": "RETRY_LIMIT = 3\n\n\ndef retry_limit():\n    return RETRY_LIMIT\n",
        "retries/__init__.py": "from .service import attempts_for\n",
        "retries/policy.py": 'MODES = {"fast", "patient"}\n',
        "retries/service.py": (
            "from retry_budget import retry_limit\n\n\n"
            "def attempts_for(mode: str) -> int:\n"
            "    budget = retry_limit()\n"
            "    if mode == \"patient\":\n"
            "        return budget\n"
            "    return max(1, budget - 2)\n"
        ),
        "test_retry_budget.py": (
            "import unittest\n\nimport retry_budget\nfrom retries.service import attempts_for\n\n\n"
            "class RetryBudgetContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(retry_budget.retry_limit(), 5)\n\n"
            "    def test_patient_mode(self):\n"
            "        self.assertEqual(attempts_for(\"patient\"), 5)\n\n"
            "    def test_fast_mode(self):\n"
            "        self.assertEqual(attempts_for(\"fast\"), 3)\n"
        ),
    },
}

PACKAGE_WINDOW = {
    "name": "window-budget",
    "target": "window_budget.py",
    "tests": ["test_window_budget.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_window_budget.py", "-q"],
    "expected_change": ["window_budget.py"],
    "files": {
        "window_budget.py": "WINDOW_SECONDS = 15\n\n\ndef window_seconds():\n    return WINDOW_SECONDS\n",
        "windows/__init__.py": "from .service import allowed_window\n",
        "windows/service.py": (
            "from window_budget import window_seconds\n\n\n"
            "def allowed_window(burst: bool) -> int:\n"
            "    span = window_seconds()\n"
            "    return span if not burst else max(1, span // 3)\n"
        ),
        "test_window_budget.py": (
            "import unittest\n\nimport window_budget\nfrom windows.service import allowed_window\n\n\n"
            "class WindowBudgetContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(window_budget.window_seconds(), 30)\n\n"
            "    def test_steady_window(self):\n"
            "        self.assertEqual(allowed_window(False), 30)\n\n"
            "    def test_burst_window(self):\n"
            "        self.assertEqual(allowed_window(True), 10)\n"
        ),
    },
}

# Leaf S: string root cause (fresh names/values, not voice/salute).
PACKAGE_PREFIX = {
    "name": "error-prefix",
    "target": "prefix.py",
    "tests": ["test_prefix.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_prefix.py", "-q"],
    "expected_change": ["prefix.py"],
    "files": {
        "prefix.py": 'PREFIX = "err"\n\n\ndef prefix():\n    return PREFIX\n',
        "formatter/__init__.py": "from .service import format_error\n",
        "formatter/style.py": 'CASES = {"plain", "loud"}\n',
        "formatter/service.py": (
            "from prefix import prefix\n\n\n"
            "def format_error(message: str, loud: bool = False) -> str:\n"
            "    tag = prefix()\n"
            "    if loud:\n"
            "        return f\"{tag.upper()}: {message}\"\n"
            "    return f\"{tag}: {message}\"\n"
        ),
        "test_prefix.py": (
            "import unittest\n\nimport prefix\nfrom formatter.service import format_error\n\n\n"
            "class PrefixContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(prefix.prefix(), \"error\")\n\n"
            "    def test_plain_format(self):\n"
            "        self.assertEqual(format_error(\"boom\"), \"error: boom\")\n\n"
            "    def test_loud_format(self):\n"
            "        self.assertEqual(format_error(\"boom\", loud=True), \"ERROR: boom\")\n"
        ),
    },
}

PACKAGE_STATUS = {
    "name": "status-label",
    "target": "status.py",
    "tests": ["test_status.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_status.py", "-q"],
    "expected_change": ["status.py"],
    "files": {
        "status.py": 'STATUS = "open"\n\n\ndef status():\n    return STATUS\n',
        "labels/__init__.py": "from .service import badge\n",
        "labels/service.py": (
            "from status import status\n\n\n"
            "def badge(upper: bool) -> str:\n"
            "    text = status()\n"
            "    return text.upper() if upper else text\n"
        ),
        "test_status.py": (
            "import unittest\n\nimport status\nfrom labels.service import badge\n\n\n"
            "class StatusContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertEqual(status.status(), \"ready\")\n\n"
            "    def test_plain_badge(self):\n"
            "        self.assertEqual(badge(False), \"ready\")\n\n"
            "    def test_loud_badge(self):\n"
            "        self.assertEqual(badge(True), \"READY\")\n"
        ),
    },
}

# Leaf B: boolean / branch root cause. The service branches on identity, but
# the wrong ALLOW_ANONYMOUS constant makes the anonymous path fail.
PACKAGE_ACCESS = {
    "name": "anonymous-access",
    "target": "access.py",
    "tests": ["test_access.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_access.py", "-q"],
    "expected_change": ["access.py"],
    "files": {
        "access.py": "ALLOW_ANONYMOUS = False\n\n\ndef allow_anonymous():\n    return ALLOW_ANONYMOUS\n",
        "gate/__init__.py": "from .service import can_enter\n",
        "gate/policy.py": "ROLES = {\"member\", \"guest\"}\n",
        "gate/service.py": (
            "from access import allow_anonymous\n\n\n"
            "def can_enter(identity: str | None) -> bool:\n"
            "    if identity:\n"
            "        return True\n"
            "    return allow_anonymous()\n"
        ),
        "test_access.py": (
            "import unittest\n\nimport access\nfrom gate.service import can_enter\n\n\n"
            "class AccessContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertTrue(access.allow_anonymous())\n\n"
            "    def test_member_path(self):\n"
            "        self.assertTrue(can_enter(\"ada\"))\n\n"
            "    def test_anonymous_branch(self):\n"
            "        self.assertTrue(can_enter(None))\n"
        ),
    },
}

PACKAGE_OPEN_GATE = {
    "name": "default-open",
    "target": "open_gate.py",
    "tests": ["test_open_gate.py"],
    "verify": ["python3", "-m", "unittest", "discover", "-p", "test_open_gate.py", "-q"],
    "expected_change": ["open_gate.py"],
    "files": {
        "open_gate.py": "DEFAULT_OPEN = False\n\n\ndef default_open():\n    return DEFAULT_OPEN\n",
        "portal/__init__.py": "from .service import admit\n",
        "portal/service.py": (
            "from open_gate import default_open\n\n\n"
            "def admit(ticket: str | None) -> bool:\n"
            "    if ticket:\n"
            "        return True\n"
            "    return default_open()\n"
        ),
        "test_open_gate.py": (
            "import unittest\n\nimport open_gate\nfrom portal.service import admit\n\n\n"
            "class OpenGateContract(unittest.TestCase):\n"
            "    def test_direct_contract(self):\n"
            "        self.assertTrue(open_gate.default_open())\n\n"
            "    def test_ticket_path(self):\n"
            "        self.assertTrue(admit(\"pass-1\"))\n\n"
            "    def test_unticketed_branch(self):\n"
            "        self.assertTrue(admit(None))\n"
        ),
    },
}

LEAVES = (
    ("leaf_int", PACKAGE_RETRY, "integer"),
    ("leaf_str", PACKAGE_PREFIX, "string"),
    ("leaf_bool", PACKAGE_ACCESS, "boolean_branch"),
)
REUSE = (
    ("reuse_int", PACKAGE_WINDOW, "integer"),
    ("reuse_str", PACKAGE_STATUS, "string"),
    ("reuse_bool", PACKAGE_OPEN_GATE, "boolean_branch"),
)

TRIPLE_VARIANTS = (
    {
        "id": "retries-prefix-anon",
        "parts": [
            {"target": "retries.py", "constant": "RETRY_LIMIT", "actual": 3, "expected": 5, "function": "retry_limit"},
            {"target": "prefix.py", "constant": "PREFIX", "actual": "err", "expected": "error", "function": "prefix"},
            {"target": "access.py", "constant": "ALLOW_ANONYMOUS", "actual": False, "expected": True,
             "function": "allow_anonymous"},
        ],
    },
    {
        "id": "window-status-open",
        "parts": [
            {"target": "window.py", "constant": "WINDOW_SECONDS", "actual": 15, "expected": 30, "function": "window_seconds"},
            {"target": "status.py", "constant": "STATUS", "actual": "open", "expected": "ready", "function": "status"},
            {"target": "open_gate.py", "constant": "DEFAULT_OPEN", "actual": False, "expected": True,
             "function": "default_open"},
        ],
    },
    {
        "id": "ttl-label-guest",
        "parts": [
            {"target": "ttl.py", "constant": "TTL", "actual": 8, "expected": 16, "function": "ttl"},
            {"target": "label.py", "constant": "LABEL", "actual": "draft", "expected": "final", "function": "label"},
            {"target": "guest.py", "constant": "GUEST_OK", "actual": False, "expected": True, "function": "guest_ok"},
        ],
    },
)


def env_for(root: Path) -> dict[str, str]:
    env = hg.env_for(root)
    env["BEAST_COMMONS_NODE_ID"] = "three-leaf-gauntlet"
    return env


def write_triple_variant(root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    files: dict[str, str] = {}
    parts_meta = []
    for part in variant["parts"]:
        files.update(hg.module_files(part))
        name = Path(part["target"]).stem
        parts_meta.append({
            "target": part["target"],
            "test": f"test_{name}.py",
            "verify": ["python3", "-m", "unittest", "discover", "-p", f"test_{name}.py", "-q"],
        })
    hg.write_tree(root, files)
    return {
        "parts": parts_meta,
        "combined_verify": ["python3", "-m", "unittest", "discover", "-q"],
    }


def fixtures_ok() -> list[str]:
    errors: list[str] = []
    with hg.tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for package in (PACKAGE_RETRY, PACKAGE_WINDOW, PACKAGE_PREFIX, PACKAGE_STATUS, PACKAGE_ACCESS, PACKAGE_OPEN_GATE):
            hg.clear_package_files(root)
            hg.write_tree(root, package["files"])
            if hg.run_verify(root, package["verify"]).returncode != 1:
                errors.append(f"{package['name']} did not fail before the root-cause edit")
            path = package["target"]
            # Infer the single assignment edit from the first source line.
            first = package["files"][path].splitlines()[0]
            name, _, raw = first.partition("=")
            # Expected values are encoded in the tests; apply the known fixes.
            replacements = {
                "retry_budget.py": ("RETRY_LIMIT = 3", "RETRY_LIMIT = 5"),
                "window_budget.py": ("WINDOW_SECONDS = 15", "WINDOW_SECONDS = 30"),
                "prefix.py": ('PREFIX = "err"', 'PREFIX = "error"'),
                "status.py": ('STATUS = "open"', 'STATUS = "ready"'),
                "access.py": ("ALLOW_ANONYMOUS = False", "ALLOW_ANONYMOUS = True"),
                "open_gate.py": ("DEFAULT_OPEN = False", "DEFAULT_OPEN = True"),
            }
            old, new = replacements[path]
            text = (root / path).read_text()
            (root / path).write_text(text.replace(old, new, 1))
            if hg.run_verify(root, package["verify"]).returncode != 0:
                errors.append(f"{package['name']} still failed after the manual root-cause edit")
        croot = root / "triple"
        hg.init_repo(croot)
        meta = write_triple_variant(croot, TRIPLE_VARIANTS[0])
        if hg.run_verify(croot, meta["combined_verify"]).returncode == 0:
            errors.append("triple variant passed before any leaf was applied")
        for index, part in enumerate(TRIPLE_VARIANTS[0]["parts"]):
            target = meta["parts"][index]["target"]
            (croot / target).write_text(
                (croot / target).read_text().replace(
                    f"{part['constant']} = {part['actual']!r}",
                    f"{part['constant']} = {part['expected']!r}",
                    1,
                )
            )
            if hg.run_verify(croot, meta["parts"][index]["verify"]).returncode != 0:
                errors.append(f"triple isolated tests failed after fix {index}")
            combined = hg.run_verify(croot, meta["combined_verify"]).returncode
            if index < 2 and combined == 0:
                errors.append(f"triple combined tests passed after only {index + 1} fix(es)")
            if index == 2 and combined != 0:
                errors.append("triple combined tests failed after all three fixes")
    return errors


def replay_leaf(root: Path, planner, crystal_id: str, *, target: str, test: str, command: list[str]) -> dict[str, Any]:
    return hg.replay_named_crystal(root, planner, crystal_id, target=target, test=test, command=command)


def replay_triple_variant(base: Path, planner, crystal_ids: list[str], variant: dict[str, Any]) -> bool:
    root = base / variant["id"]
    if root.exists():
        shutil.rmtree(root)
    hg.init_repo(root)
    meta = write_triple_variant(root, variant)
    hg.commit_all(root, f"triple variant {variant['id']}")
    if hg.run_verify(root, meta["combined_verify"]).returncode == 0:
        return False
    current = root
    for index, (crystal_id, part) in enumerate(zip(crystal_ids, meta["parts"], strict=True)):
        result = replay_leaf(current, planner, crystal_id, target=part["target"], test=part["test"],
                             command=part["verify"])
        worktree = Path(result["worktree"] or current)
        isolated_ok = (
            result["completed"] and result["zero_inference"] and result["crystal_completed"]
            and hg.run_verify(worktree, part["verify"]).returncode == 0
        )
        combined_rc = hg.run_verify(worktree, meta["combined_verify"]).returncode
        last = index == len(crystal_ids) - 1
        if not isolated_ok or (combined_rc == 0) != last:
            return False
        if last:
            return True
        stage = root.parent / f"{variant['id']}-after-{index}"
        if stage.exists():
            shutil.rmtree(stage)
        shutil.copytree(worktree, stage, ignore=shutil.ignore_patterns(".beast", ".git"))
        hg.init_repo(stage)
        hg.commit_all(stage, f"after-leaf-{index}")
        current = stage
    return False


def receipt_from_record(record: dict[str, Any]) -> ReplayReceipt | None:
    raw = record.get("receipt") or {}
    if not raw:
        return None
    allowed = {field.name for field in ReplayReceipt.__dataclass_fields__.values()}
    payload = {k: v for k, v in raw.items() if k in allowed}
    if "variant_ids" in payload:
        payload["variant_ids"] = tuple(payload["variant_ids"])
    if "variant_results" in payload:
        payload["variant_results"] = tuple(payload["variant_results"])
    try:
        return ReplayReceipt(**payload)
    except TypeError:
        return None


def import_previous_composite(src_evidence: Path, dest_planner, dest_publisher: str) -> dict[str, Any]:
    """Copy the previously admitted 2-leaf composite and its children into this lattice."""
    if not src_evidence.exists():
        return {"ok": False, "reason": f"previous evidence missing: {src_evidence}"}
    src_env = hg.env_for(src_evidence)
    src_hub = src_evidence / "workspace"
    extras = planner_runtime_extras(src_hub, env=src_env)
    if not extras:
        return {"ok": False, "reason": "previous evidence did not enable coding crystals"}
    src = extras["crystal_planner"]
    try:
        node = src.lattice.node(PREVIOUS_COMPOSITE_ID)
    except Exception as exc:
        return {"ok": False, "reason": f"previous composite unavailable: {type(exc).__name__}: {exc}"}
    child_ids = list(node.get("component_ids") or [])
    imported: list[str] = []
    for crystal_id in child_ids + [PREVIOUS_COMPOSITE_ID]:
        try:
            record = src.registry.get(crystal_id)
        except Exception as exc:
            return {"ok": False, "reason": f"registry get failed for {crystal_id}: {exc}", "imported": imported}
        dest_planner.registry.add_candidate(record["candidate_object"])
        existing = dest_planner.registry.get(crystal_id)
        if existing["status"] != "promoted":
            receipt = receipt_from_record(record)
            if receipt is None or not receipt.promoted:
                return {"ok": False, "reason": f"no reusable receipt for {crystal_id}", "imported": imported}
            dest_planner.registry.promote(crystal_id, receipt)
        if crystal_id != PREVIOUS_COMPOSITE_ID:
            try:
                dest_planner.lattice.node(crystal_id)
            except LookupError:
                dest_planner.lattice.add_crystal(crystal_id, publisher_id=dest_publisher)
        imported.append(crystal_id)
    # Re-admit the previous composite against the imported children if needed.
    try:
        dest_planner.lattice.node(PREVIOUS_COMPOSITE_ID)
        admitted = True
        admission = {"status": "already_present"}
    except LookupError:
        composite = dest_planner.registry.get(PREVIOUS_COMPOSITE_ID)["candidate_object"]
        receipt = receipt_from_record(dest_planner.registry.get(PREVIOUS_COMPOSITE_ID))
        if receipt is None:
            return {"ok": False, "reason": "imported composite has no receipt", "imported": imported}
        admission = dest_planner.lattice.admit_composite(
            composite, verifier=receipt, publisher_id=dest_publisher, approved_by="Byron",
        )
        admitted = admission.get("outcome") == "ADMIT"
    return {
        "ok": admitted,
        "composite_id": PREVIOUS_COMPOSITE_ID,
        "child_ids": child_ids,
        "imported": imported,
        "admission": admission,
        "src": str(src_evidence),
    }


def admitted_leaf_ids(planner, report: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    ids = []
    for key in keys:
        task = next((t for t in report.get("tasks") or [] if t.get("id") == key), None)
        crystal_id = ((task or {}).get("formation") or {}).get("crystal_id")
        if crystal_id:
            ids.append(crystal_id)
    if len(ids) == len(keys):
        return ids
    # Fall back to lattice order for admitted non-composite crystals added this run.
    leaves = [n["node_id"] for n in planner.lattice.nodes()
              if n.get("kind") == "crystal" and n.get("status") == "admitted"
              and n.get("node_id") not in {PREVIOUS_COMPOSITE_ID}]
    return leaves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("fixtures", "form-leaves", "reuse", "composite", "nested", "all"),
                        default="all")
    parser.add_argument("--approve-by", default="Byron")
    parser.add_argument("--model", default=os.environ.get("BEAST_LIVE_CRYSTAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--import-composite-from", type=Path, default=PREVIOUS_EVIDENCE)
    args = parser.parse_args()

    os.chdir(ROOT)
    vault = SecretVault().load()
    if not os.environ.get("NVIDIA_API_KEY") and args.phase not in {"fixtures"}:
        parser.error("NVIDIA_API_KEY was not loaded from the local secret vault. No key was printed.")
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
    report["refactor_only_note"] = (
        "Refactor-only tasks still will not form crystals: the extractor requires "
        "failures_before_pass >= 1 around an exact replacement, so a green-to-green "
        "refactor episode never seals."
    )

    hub = evidence / "workspace"
    key_path = evidence / "trial-key.pem"
    if not key_path.exists():
        hg.new_local_key(key_path)
    env = env_for(evidence)
    hg.init_repo(hub)
    extras = planner_runtime_extras(hub, env=env)
    if not extras:
        raise RuntimeError("coding crystals did not enable on the evidence workspace")
    planner = extras["crystal_planner"]
    envelopes = extras["envelope_store"]
    governor = hg.model_governor(evidence)
    os.environ.setdefault("BEAST_NIM_MAX_TOKENS", "4096")

    def persist() -> None:
        report["lattice"] = hg.lattice_snapshot(planner)
        report["spend_total"] = {
            "prompt_tokens": sum(s.get("prompt_tokens") or 0 for s in report["spend"]),
            "completion_tokens": sum(s.get("completion_tokens") or 0 for s in report["spend"]),
            "estimated_usd": round(sum(float(s.get("estimated_usd") or 0) for s in report["spend"]), 6),
            "commercial_equivalent_usd": round(
                sum(float(s.get("commercial_equivalent_usd") or 0) for s in report["spend"]), 6
            ),
        }
        hg.save(report_path, report)

    if args.phase in {"form-leaves", "all"}:
        for key, package, kind in LEAVES:
            existing = next((t for t in report["tasks"] if t.get("id") == key and t.get("status") == "promoted"
                             and (t.get("formation") or {}).get("lattice_admitted")), None)
            if existing:
                print(f"{key} already promoted and admitted; skipping live formation", flush=True)
                continue
            provider = hg.MeteredNIM(governor, args.model)
            # Formation must not see an already-admitted sibling of the same family.
            arm = hg.run_package(
                hub, package, provider, envelopes=envelopes, planner=None, learner=None,
                model=args.model, session_id=f"three-leaf-{key}",
            )
            arm["observed_provider_attempts"] = arm["usage"]["calls"]
            arm["root_cause_type"] = kind
            task = {"id": key, "kind": "formation", "root_cause_type": kind, "source": arm, "status": "capture_not_proven"}
            report["spend"].append(arm["usage"])
            if hg.good_source(arm) and arm["usage"]["calls"] > 0 and not arm["crystal_completed"]:
                task["formation"] = hg.promote_and_admit(hub, env, arm["run_id"], args.approve_by)
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
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]

    if args.phase in {"reuse", "all"}:
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]
        rows = []
        for key, package, kind in REUSE:
            row = {"id": key, "package": package["name"], "root_cause_type": kind}
            for arm_name, use_planner in (("off", False), ("on", True)):
                provider = hg.MeteredNIM(governor, args.model)
                arm = hg.run_package(
                    hub, package, provider,
                    envelopes=EpisodeEnvelopeStore(evidence / f"{key}-{arm_name}.sqlite3"),
                    planner=planner if use_planner else None, learner=None,
                    model=args.model, session_id=f"three-leaf-{key}-{arm_name}",
                )
                arm["observed_provider_attempts"] = arm["usage"]["calls"]
                report["spend"].append(arm["usage"])
                row[arm_name] = arm
            off, on = row["off"], row["on"]
            row["passed"] = (
                hg.good_source(off) and hg.good_source(on)
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
        leaf_ids = admitted_leaf_ids(planner, report, ("leaf_int", "leaf_str", "leaf_bool"))
        if len(leaf_ids) < 3:
            report["composite"] = {"status": "not_attempted", "reason": "fewer_than_three_admitted_leaves",
                                   "leaf_ids": leaf_ids}
            persist()
            return 1
        children = [planner.registry.get(cid)["candidate_object"] for cid in leaf_ids]
        source_digest = "sha256:" + "0" * 64
        for task in report.get("tasks") or []:
            formation = task.get("formation") or {}
            if task.get("id") == "leaf_int" and formation.get("source_envelope_digest"):
                source_digest = formation["source_envelope_digest"]
                break
        composite = compose_candidates(
            children, task_family=TRIPLE_FAMILY, source_run_id="three-leaf-composite",
            source_envelope_digest=source_digest, learned_budget={"prompt_tokens": 0, "completion_tokens": 0},
        )
        gate = HeldOutReplayGate()
        base = evidence / "triple-heldout"
        receipt = gate.evaluate(
            composite.crystal_id, list(TRIPLE_VARIANTS),
            lambda variant: replay_triple_variant(base, planner, leaf_ids, variant),
            minimum_successes=3,
            envelope_digest=source_digest,
            reproduction={"mode": "live_triple_composite", "leaves": leaf_ids, "approved_by": args.approve_by},
        )
        admitted = planner.lattice.admit_composite(
            composite, verifier=receipt, publisher_id=planner.authority.key_id, approved_by=args.approve_by,
        )
        snapshot = hg.lattice_snapshot(planner)
        live_edge = (
            admitted.get("outcome") == "ADMIT"
            and receipt.promoted and receipt.successes == 3 and receipt.attempts == 3
            and any(e.get("edge_type") == "COMPOSES_WITH"
                    and set(e.get("source_ids") or []) == set(leaf_ids)
                    and e.get("target_id") == composite.crystal_id
                    for e in snapshot.get("edges") or [])
        )
        report["composite"] = {
            "status": "live_triple_composite_admitted" if live_edge else "not_proven",
            "leaf_ids": leaf_ids,
            "crystal_id": composite.crystal_id,
            "receipt": {
                "attempts": receipt.attempts, "successes": receipt.successes, "promoted": receipt.promoted,
                "reason": receipt.reason, "structured": receipt.structured,
                "evidence_root": receipt.evidence_root, "variant_ids": list(receipt.variant_ids),
                "variant_results": list(receipt.variant_results),
            },
            "admission": admitted,
            "live_composite_edge": live_edge,
            "model_calls": 0,
            "lattice": snapshot,
        }
        persist()
        if not live_edge:
            print("3-way composite was not proven; continuing to nested if requested", flush=True)

    if args.phase in {"nested", "all"}:
        planner = planner_runtime_extras(hub, env=env)["crystal_planner"]
        imported = import_previous_composite(Path(args.import_composite_from).expanduser().resolve(),
                                             planner, planner.authority.key_id)
        report["nested_import"] = imported
        persist()
        bool_id = next((((t.get("formation") or {}).get("crystal_id"))
                        for t in report.get("tasks") or [] if t.get("id") == "leaf_bool"), None)
        if not imported.get("ok") or not bool_id:
            report["nested"] = {
                "status": "not_attempted",
                "reason": "import_or_boolean_leaf_unavailable",
                "import": imported,
                "boolean_leaf": bool_id,
            }
            persist()
            persist()
            return 0 if (report.get("composite") or {}).get("live_composite_edge") else 1
        children = [
            planner.registry.get(PREVIOUS_COMPOSITE_ID)["candidate_object"],
            planner.registry.get(bool_id)["candidate_object"],
        ]
        source_digest = "sha256:" + "0" * 64
        nested = compose_candidates(
            children, task_family=NESTED_FAMILY, source_run_id="three-leaf-nested",
            source_envelope_digest=source_digest, learned_budget={"prompt_tokens": 0, "completion_tokens": 0},
        )
        # Held-out: apply previous composite's two leaves plus the new boolean leaf.
        # That is the operational meaning of nesting d6408abd under a new child.
        child_ids = list(imported.get("child_ids") or []) + [bool_id]
        if len(child_ids) != 3:
            report["nested"] = {"status": "not_attempted", "reason": "imported composite did not have two children",
                                "child_ids": child_ids}
            persist()
            return 0 if (report.get("composite") or {}).get("live_composite_edge") else 1
        gate = HeldOutReplayGate()
        base = evidence / "nested-heldout"
        receipt = gate.evaluate(
            nested.crystal_id, list(TRIPLE_VARIANTS),
            lambda variant: replay_triple_variant(base, planner, child_ids, variant),
            minimum_successes=3,
            envelope_digest=source_digest,
            reproduction={"mode": "nested_composite", "parent": PREVIOUS_COMPOSITE_ID,
                          "new_leaf": bool_id, "approved_by": args.approve_by},
        )
        admitted = planner.lattice.admit_composite(
            nested, verifier=receipt, publisher_id=planner.authority.key_id, approved_by=args.approve_by,
        )
        snapshot = hg.lattice_snapshot(planner)
        live_edge = (
            admitted.get("outcome") == "ADMIT"
            and receipt.promoted and receipt.successes == 3 and receipt.attempts == 3
            and any(e.get("edge_type") == "COMPOSES_WITH"
                    and set(e.get("source_ids") or []) == {PREVIOUS_COMPOSITE_ID, bool_id}
                    and e.get("target_id") == nested.crystal_id
                    for e in snapshot.get("edges") or [])
        )
        report["nested"] = {
            "status": "live_nested_composite_admitted" if live_edge else "not_proven",
            "parent_composite_id": PREVIOUS_COMPOSITE_ID,
            "new_leaf_id": bool_id,
            "replay_child_ids": child_ids,
            "crystal_id": nested.crystal_id,
            "receipt": {
                "attempts": receipt.attempts, "successes": receipt.successes, "promoted": receipt.promoted,
                "reason": receipt.reason, "structured": receipt.structured,
                "evidence_root": receipt.evidence_root, "variant_ids": list(receipt.variant_ids),
                "variant_results": list(receipt.variant_results),
            },
            "admission": admitted,
            "live_composite_edge": live_edge,
            "model_calls": 0,
            "lattice": snapshot,
        }
        persist()

    persist()
    composite_ok = bool((report.get("composite") or {}).get("live_composite_edge"))
    leaves_ok = all(
        t.get("status") == "promoted" and (t.get("formation") or {}).get("lattice_admitted")
        for t in report.get("tasks") or [] if t.get("id") in {"leaf_int", "leaf_str", "leaf_bool"}
    )
    reuse_ok = bool(report.get("reuse_all_passed"))
    return 0 if leaves_ok and reuse_ok and composite_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
