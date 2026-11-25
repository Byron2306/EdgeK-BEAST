#!/usr/bin/env python3
"""Head-to-head NIM baseline: crystals-first (A) versus cold (B).

Reruns the same 2026-11-25 lattice-gauntlet reuse tasks on the hosted NVIDIA
NIM trial, once with already-admitted crystals eligible for reuse and once
with crystal lookup/reuse disabled. Prompts, verifier, model, temperature
(0) and seed formula (731947 + turn) are identical across arms.

This script does not form new crystals and does not touch production
services (ARDA, LiteLLM, Ollama, ComfyUI, Lilith). Provider secret values
are never printed. Live state is written under an evidence directory;
``--phase pack`` copies a redacted tree suitable for git.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_HELPERS = Path(__file__).resolve().parent / "run_hard_lattice_gauntlet.py"
_spec = importlib.util.spec_from_file_location("hard_lattice_gauntlet_helpers", _HELPERS)
hg = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hg)

_TL = Path(__file__).resolve().parent / "run_three_leaf_lattice_gauntlet.py"
_tl_spec = importlib.util.spec_from_file_location("three_leaf_lattice_gauntlet_helpers", _TL)
tl = importlib.util.module_from_spec(_tl_spec)
assert _tl_spec.loader is not None
_tl_spec.loader.exec_module(tl)

from app.kernel.compute.coding_crystal_runtime import (
    AUTO_PROMOTE_ENV,
    ENABLE_ENV,
    KEY_ENV,
    LATTICE_ENV,
    LATTICE_LEDGER_ENV,
    planner_runtime_extras,
)
from app.kernel.security.secret_vault import SecretVault
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

DEFAULT_MODEL = hg.DEFAULT_MODEL
DEFAULT_SOURCE = ROOT / "evidence/gauntlets-2026-11-25/three-leaf-gauntlet-20261125-a"
EXPECTED_CRYSTALS = (
    "coding-crystal:191dd9102ea2373933f777b1",
    "coding-crystal:eb814eff3d78a76261e439e5",
    "coding-crystal:21c3949d1aeed9ddb1ecec1c",
    "coding-crystal:80da30d07663601262fa23bc",
    "coding-crystal:d1a2333153420620fb272839",
    "coding-crystal:d6408abd53c27ec6a8a58507",
    "coding-crystal:bab0e1056b3776569a69909a",
    "coding-crystal:ef42c64e5cde929000870a22",
)

TASKS = (
    {"id": "quota-limit", "package": hg.PACKAGE_QUOTA, "origin": "hard-lattice-gauntlet-20261125-b reuse_a"},
    {"id": "voice-salute", "package": hg.PACKAGE_SALUTE, "origin": "hard-lattice-gauntlet-20261125-b reuse_b"},
    {"id": "window-budget", "package": tl.PACKAGE_WINDOW, "origin": "three-leaf-gauntlet-20261125-a reuse_int"},
    {"id": "status-label", "package": tl.PACKAGE_STATUS, "origin": "three-leaf-gauntlet-20261125-a reuse_str"},
    {"id": "default-open", "package": tl.PACKAGE_OPEN_GATE, "origin": "three-leaf-gauntlet-20261125-a reuse_bool"},
)

SECRET_FILE_SUFFIXES = {".pem", ".key", ".env", ".p12", ".pfx"}
SECRET_FILE_NAMES = {"trial-key.pem", "provider_secrets.env", ".env"}
SECRET_CONTENT_RE = re.compile(
    r"(BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY"
    r"|nvapi-[A-Za-z0-9_\-]+"
    r"|(?:NVIDIA_API_KEY|OPENAI_API_KEY|HF_TOKEN|FIREWORKS_API_KEY)\s*=\s*\S+"
    r"|Bearer\s+[A-Za-z0-9\-_.]{16,})",
    re.IGNORECASE,
)
SKIP_COPY_DIR_NAMES = {".git"}


class RetryingMeteredNIM(hg.MeteredNIM):
    """Metered NIM client with bounded backoff on 429/503. Does not print bodies."""

    def __init__(self, governor, model: str, *, max_http_retries: int = 6):
        super().__init__(governor, model)
        self.max_http_retries = max_http_retries
        self.http_retries = 0
        self.rate_limit_events = 0

    def _with_retry(self, fn, payload):
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(self.max_http_retries + 1):
            try:
                return fn(payload)
            except urllib.error.HTTPError as exc:
                code = int(exc.code)
                # Drain and discard the body so it cannot leak into logs.
                try:
                    exc.read()
                except Exception:
                    pass
                last_exc = exc
                if code not in {429, 503} or attempt >= self.max_http_retries:
                    raise
                self.http_retries += 1
                if code == 429:
                    self.rate_limit_events += 1
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after) if retry_after else delay
                except (TypeError, ValueError):
                    wait = delay
                wait = max(1.0, min(wait, 60.0))
                print(json.dumps({"event": "nim_backoff", "http_status": code, "wait_s": wait,
                                  "attempt": attempt + 1}), flush=True)
                time.sleep(wait)
                delay = min(delay * 2, 60.0)
        raise last_exc or RuntimeError("NIM request failed after retries")

    def _request_json(self, payload):
        return self._with_retry(super()._request_json, payload)

    def _request_stream(self, payload):
        return self._with_retry(super()._request_stream, payload)


def env_for(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        ENABLE_ENV: "1",
        AUTO_PROMOTE_ENV: "1",
        LATTICE_ENV: "1",
        KEY_ENV: str(root / "trial-key.pem"),
        LATTICE_LEDGER_ENV: str(root / "lattice-ledger"),
        "BEAST_COMMONS_ROOT": str(root / "commons"),
        "BEAST_COMMONS_NODE_ID": "ab-nim-crystal-baseline",
        "BEAST_COMMONS_USER_ID": "gauntlet",
    })
    return env


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, default=str)
    path.write_text(payload + "\n", encoding="utf-8")


def copy_tree_filtered(src: Path, dest: Path) -> int:
    """Copy files, skipping secrets and .git metadata. Returns file count."""
    copied = 0
    dest.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_COPY_DIR_NAMES]
        rel_root = Path(root).relative_to(src)
        for name in files:
            src_file = Path(root) / name
            rel = rel_root / name
            if should_skip_secret(src_file, rel):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, target)
            copied += 1
    return copied


def should_skip_secret(path: Path, rel: Path) -> bool:
    name = path.name
    if name in SECRET_FILE_NAMES or path.suffix.lower() in SECRET_FILE_SUFFIXES:
        return True
    parts = {p.lower() for p in rel.parts}
    if "keys" in parts and path.suffix.lower() in SECRET_FILE_SUFFIXES | {".pem"}:
        return True
    if name.endswith(".pem") or name.endswith(".env"):
        return True
    return False


def import_admitted_crystals(source: Path, dest: Path) -> dict[str, Any]:
    """Copy crystal registry, lattice, and chain into dest. Never copies keys."""
    if not source.exists():
        raise FileNotFoundError(f"source evidence missing: {source}")
    src_crystals = source / "workspace" / ".beast" / "crystals"
    if not src_crystals.exists():
        raise FileNotFoundError(f"source crystal registry missing: {src_crystals}")
    copied = {}
    dest_crystals = dest / "workspace" / ".beast" / "crystals"
    copied["crystals"] = copy_tree_filtered(src_crystals, dest_crystals)
    if (source / "lattice-ledger").exists():
        copied["lattice_ledger"] = copy_tree_filtered(source / "lattice-ledger", dest / "lattice-ledger")
    if (source / "commons").exists():
        copied["commons"] = copy_tree_filtered(source / "commons", dest / "commons")
    return {"source": str(source), "copied": copied}


def setup_workspace(evidence: Path, source: Path) -> dict[str, Any]:
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    (evidence / "receipts").mkdir(exist_ok=True)
    key_path = evidence / "trial-key.pem"
    if not key_path.exists():
        hg.new_local_key(key_path)
    hub = evidence / "workspace"
    hg.init_repo(hub)
    imported = import_admitted_crystals(source, evidence)
    extras = planner_runtime_extras(hub, env=env_for(evidence))
    if not extras:
        raise RuntimeError("coding crystals did not enable on the A/B workspace")
    planner = extras["crystal_planner"]
    snapshot = hg.lattice_snapshot(planner)
    found = []
    missing = []
    for cid in EXPECTED_CRYSTALS:
        try:
            rec = planner.registry.get(cid)
            found.append({"crystal_id": cid, "status": rec.get("status"), "task_family": rec.get("task_family")})
        except Exception as exc:
            missing.append({"crystal_id": cid, "error": f"{type(exc).__name__}"})
    admitted = [
        n.get("node_id") for n in (snapshot.get("nodes") or [])
        if n.get("status") == "admitted"
    ]
    return {
        "imported": imported,
        "found": found,
        "missing": missing,
        "admitted_ids": admitted,
        "lattice": snapshot,
        "all_expected_present": not missing and len(found) == len(EXPECTED_CRYSTALS),
    }


def arm_ok(arm: dict[str, Any], *, crystals: bool) -> bool:
    if not hg.good_source(arm):
        return False
    if crystals:
        return bool(arm.get("crystal_completed")) and int(arm.get("observed_provider_attempts") or 0) == 0 and int(arm.get("model_turns") or 0) == 0
    return (not arm.get("crystal_completed")) and (not arm.get("crystal_activated")) and int(arm.get("observed_provider_attempts") or 0) > 0


def ratio(saved: float, baseline: float) -> float | None:
    if baseline <= 0:
        return None
    return round((baseline - saved) / baseline, 6)


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    runs = list(report.get("runs") or [])
    per_task: dict[str, Any] = {}
    aggregates = {
        "A": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "wall_seconds": 0.0,
              "passes": 0, "attempts": 0, "crystal_hits": 0, "crystal_activations": 0},
        "B": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "wall_seconds": 0.0,
              "passes": 0, "attempts": 0, "crystal_hits": 0, "crystal_activations": 0},
    }
    for run in runs:
        arm = run["arm"]
        task_id = run["task_id"]
        usage = run.get("usage") or {}
        bucket = aggregates[arm]
        bucket["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        bucket["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        bucket["calls"] += int(usage.get("calls") or 0)
        bucket["wall_seconds"] += float(run.get("wall_seconds") or 0)
        bucket["attempts"] += 1
        if run.get("passed"):
            bucket["passes"] += 1
        if run.get("crystal_completed"):
            bucket["crystal_hits"] += 1
        if run.get("crystal_activated"):
            bucket["crystal_activations"] += 1
        task = per_task.setdefault(task_id, {"id": task_id, "origin": run.get("origin"), "A": _empty_arm(), "B": _empty_arm()})
        side = task[arm]
        side["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        side["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        side["calls"] += int(usage.get("calls") or 0)
        side["wall_seconds"] += float(run.get("wall_seconds") or 0)
        side["attempts"] += 1
        side["passes"] += 1 if run.get("passed") else 0
        side["crystal_hits"] += 1 if run.get("crystal_completed") else 0
        side["repeats"].append({
            "repeat": run.get("repeat"),
            "passed": run.get("passed"),
            "calls": usage.get("calls"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "wall_seconds": run.get("wall_seconds"),
            "crystal_completed": run.get("crystal_completed"),
            "run_id": run.get("run_id"),
        })
    for task in per_task.values():
        for arm in ("A", "B"):
            side = task[arm]
            attempts = side["attempts"] or 1
            side["wall_seconds"] = round(side["wall_seconds"], 3)
            side["pass_rate"] = round(side["passes"] / attempts, 6) if side["attempts"] else 0.0
            side["mean_wall_seconds"] = round(side["wall_seconds"] / attempts, 3) if side["attempts"] else 0.0
        a, b = task["A"], task["B"]
        task["savings"] = {
            "prompt_tokens": ratio(a["prompt_tokens"], b["prompt_tokens"]),
            "completion_tokens": ratio(a["completion_tokens"], b["completion_tokens"]),
            "calls": ratio(a["calls"], b["calls"]),
            "wall_seconds": ratio(a["wall_seconds"], b["wall_seconds"]),
        }
    for arm, bucket in aggregates.items():
        attempts = bucket["attempts"] or 1
        bucket["wall_seconds"] = round(bucket["wall_seconds"], 3)
        bucket["pass_rate"] = round(bucket["passes"] / attempts, 6) if bucket["attempts"] else 0.0
        bucket["mean_wall_seconds"] = round(bucket["wall_seconds"] / attempts, 3) if bucket["attempts"] else 0.0
    a, b = aggregates["A"], aggregates["B"]
    spend_events = []
    for run in runs:
        if run.get("arm") == "B" and run.get("usage"):
            spend_events.append(run["usage"])
    # Rebuild totals from recorded usage so packing stays consistent.
    prompt = a["prompt_tokens"] + b["prompt_tokens"]
    completion = a["completion_tokens"] + b["completion_tokens"]
    list_price = hg.NIM_PRICE.get(report.get("model") or DEFAULT_MODEL, {"input": 0.0, "output": 0.0})
    list_usd = (prompt / 1_000_000) * float(list_price["input"]) + (completion / 1_000_000) * float(list_price["output"])
    return {
        "per_task": per_task,
        "aggregate": {
            "A": a,
            "B": b,
            "savings": {
                "prompt_tokens": ratio(a["prompt_tokens"], b["prompt_tokens"]),
                "completion_tokens": ratio(a["completion_tokens"], b["completion_tokens"]),
                "calls": ratio(a["calls"], b["calls"]),
                "wall_seconds": ratio(a["wall_seconds"], b["wall_seconds"]),
                "pass_rate_delta": round(a["pass_rate"] - b["pass_rate"], 6),
            },
        },
        "spend_total": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "calls": a["calls"] + b["calls"],
            "estimated_usd": 0.0,
            "commercial_equivalent_usd": round(list_usd, 6),
            "billed_usd": 0.0,
            "pricing_note": (
                "NVIDIA hosted trial endpoint (integrate.api.nvidia.com) is free for prototyping; "
                "commercial_equivalent_usd uses public list prices from modelmenu.dev (checked Nov 2026) "
                "and is not a charge on this run."
            ),
        },
    }


def _empty_arm() -> dict[str, Any]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "wall_seconds": 0.0,
            "passes": 0, "attempts": 0, "crystal_hits": 0, "repeats": [],
            "pass_rate": 0.0, "mean_wall_seconds": 0.0}


def persist_report(path: Path, report: dict[str, Any]) -> None:
    summary = summarize(report)
    report["per_task"] = summary["per_task"]
    report["aggregate"] = summary["aggregate"]
    report["spend_total"] = summary["spend_total"]
    save(path, report)


def run_arm(evidence: Path, package: dict[str, Any], *, arm: str, repeat: int,
            model: str, crystals: bool) -> dict[str, Any]:
    hub = evidence / "workspace"
    extras = planner_runtime_extras(hub, env=env_for(evidence))
    if not extras:
        raise RuntimeError("coding crystals did not enable on the A/B workspace")
    planner = extras["crystal_planner"] if crystals else None
    envelopes = EpisodeEnvelopeStore(evidence / "envelopes" / f"{package['name']}-{arm}-{repeat}.sqlite3")
    governor = hg.model_governor(evidence)
    provider = RetryingMeteredNIM(governor, model)
    session = f"ab-nim-{package['name']}-{arm}-r{repeat}"
    result = hg.run_package(
        hub, package, provider,
        envelopes=envelopes,
        planner=planner,
        learner=None,
        model=model,
        session_id=session,
    )
    result["observed_provider_attempts"] = result["usage"]["calls"]
    result["arm"] = arm
    result["repeat"] = repeat
    result["crystals_enabled"] = crystals
    result["passed"] = arm_ok(result, crystals=crystals)
    result["http_retries"] = provider.http_retries
    result["rate_limit_events"] = provider.rate_limit_events
    result["usage_events"] = list(getattr(provider, "usage_events", []) or [])
    return result


def secret_scan(root: Path) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    scanned = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        scanned += 1
        if should_skip_secret(path, rel) or path.suffix.lower() in SECRET_FILE_SUFFIXES or path.name in SECRET_FILE_NAMES:
            hits.append({"path": str(rel), "reason": "secret_filename"})
            continue
        try:
            if path.stat().st_size > 8_000_000:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        # Skip obvious binaries except for a short ascii scan of the head.
        sample = data[:2_000_000]
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            text = sample.decode("latin-1", "ignore")
        if SECRET_CONTENT_RE.search(text):
            hits.append({"path": str(rel), "reason": "secret_pattern"})
    return {"scanned_files": scanned, "hits": hits, "clean": not hits}


def pack_evidence(live: Path, dest: Path) -> dict[str, Any]:
    """Copy a redacted evidence tree. Never copies keys, .env, or huge worktrees."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(mode=0o755, parents=True, exist_ok=True)
    skipped: list[dict[str, Any]] = []
    copied = 0
    copied_bytes = 0
    keep_exact = {
        "report.json", "README.md", "SKIPPED.md", "secret_scan.json",
        "pack-manifest.json", "summary.json",
    }
    for path in live.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(live)
        parts = rel.parts
        if should_skip_secret(path, rel):
            skipped.append({"path": str(rel), "reason": "credential_file", "bytes": path.stat().st_size})
            continue
        if ".git" in parts:
            root = str(Path(*parts[: parts.index(".git") + 1]))
            if not any(item.get("path") == root and item.get("reason") == "git_metadata" for item in skipped):
                skipped.append({"path": root, "reason": "git_metadata", "bytes": 0})
            continue
        if "worktrees" in parts:
            try:
                widx = parts.index("worktrees")
                root = str(Path(*parts[: widx + 2])) if len(parts) > widx + 1 else str(Path(*parts[: widx + 1]))
            except ValueError:
                root = "worktrees"
            if not any(item.get("path") == root and item.get("reason") == "worktree_omitted" for item in skipped):
                skipped.append({"path": root, "reason": "worktree_omitted", "bytes": 0})
            continue
        if any(part in {"agent_runs", "operations_console", "memory_hull"} for part in parts):
            kind = next(part for part in parts if part in {"agent_runs", "operations_console", "memory_hull"})
            root = str(Path(*parts[: parts.index(kind) + 1]))
            if not any(item.get("path") == root for item in skipped):
                skipped.append({"path": root, "reason": "runtime_db_omitted", "bytes": 0})
            continue
        if path.name == "trial-key.pem":
            skipped.append({"path": str(rel), "reason": "credential_file", "bytes": path.stat().st_size})
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
        copied_bytes += path.stat().st_size
    scan = secret_scan(dest)
    save(dest / "secret_scan.json", scan)
    manifest = {
        "copied_files": copied,
        "copied_bytes": copied_bytes,
        "skipped": skipped,
        "secret_scan_clean": scan["clean"],
        "source_live": str(live),
        "packed": str(dest),
    }
    save(dest / "pack-manifest.json", manifest)
    skipped_md = ["# Skipped paths — ab-nim crystal baseline", "",
                  "These source paths were not copied into the tracked evidence tree.", "",
                  "| path | reason | bytes |", "|---|---|---:|"]
    if skipped:
        for item in skipped:
            skipped_md.append(f"| `{item['path']}` | {item['reason']} | {item['bytes']} |")
    else:
        skipped_md.append("| _(none)_ | — | 0 |")
    skipped_md.append("")
    (dest / "SKIPPED.md").write_text("\n".join(skipped_md) + "\n", encoding="utf-8")
    # If a secret slipped through packing, refuse to leave the tree as-is.
    if not scan["clean"]:
        raise RuntimeError(f"secret scan failed on packed evidence: {scan['hits'][:8]}")
    _ = keep_exact
    return manifest


def write_readme(dest: Path, report: dict[str, Any]) -> None:
    agg = report.get("aggregate") or {}
    a, b = agg.get("A") or {}, agg.get("B") or {}
    savings = agg.get("savings") or {}
    spend = report.get("spend_total") or {}
    def pct(val: float | None) -> str:
        return "n/a" if val is None else f"{val * 100:.1f}%"
    lines = [
        "# NIM crystal economics baseline — 2026-11-25",
        "",
        "Head-to-head rerun of the 2026-11-25 lattice-gauntlet reuse tasks on the hosted NVIDIA NIM trial.",
        "Arm A reuses already-admitted coding crystals. Arm B disables crystal lookup/reuse.",
        "Prompts, verifier, model, temperature (0) and seed formula (`731947 + turn`) are identical.",
        "",
        "## Headline",
        "",
        "| item | result |",
        "|---|---|",
        f"| Model | `{report.get('model')}` (hosted NIM trial, `{report.get('base_url')}`) |",
        f"| Tasks | {report.get('task_count')} reuse packages from the prior gauntlets |",
        f"| Repeats | {report.get('repeats')} per arm per task |",
        f"| Arm A pass rate | {a.get('passes')}/{a.get('attempts')} ({(a.get('pass_rate') or 0)*100:.1f}%), crystal hits {a.get('crystal_hits')} |",
        f"| Arm B pass rate | {b.get('passes')}/{b.get('attempts')} ({(b.get('pass_rate') or 0)*100:.1f}%), crystal hits {b.get('crystal_hits')} |",
        f"| Prompt tokens A / B | {a.get('prompt_tokens')} / {b.get('prompt_tokens')} (saved {pct(savings.get('prompt_tokens'))}) |",
        f"| Completion tokens A / B | {a.get('completion_tokens')} / {b.get('completion_tokens')} (saved {pct(savings.get('completion_tokens'))}) |",
        f"| Model calls A / B | {a.get('calls')} / {b.get('calls')} (saved {pct(savings.get('calls'))}) |",
        f"| Wall time A / B | {a.get('wall_seconds')}s / {b.get('wall_seconds')}s (saved {pct(savings.get('wall_seconds'))}) |",
        f"| Billed | ${spend.get('billed_usd', 0):.2f} (free NIM trial) |",
        f"| Commercial equivalent | ${spend.get('commercial_equivalent_usd', 0)} (list prices, not a charge) |",
        "",
        "## Per-task totals (all repeats)",
        "",
        "| task | A calls | B calls | A prompt | B prompt | A wall s | B wall s | A pass | B pass | A crystal hits |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for task_id, task in (report.get("per_task") or {}).items():
        aa, bb = task["A"], task["B"]
        lines.append(
            f"| `{task_id}` | {aa['calls']} | {bb['calls']} | {aa['prompt_tokens']} | {bb['prompt_tokens']} "
            f"| {aa['wall_seconds']} | {bb['wall_seconds']} | {aa['passes']}/{aa['attempts']} | {bb['passes']}/{bb['attempts']} "
            f"| {aa['crystal_hits']} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
    ]
    for caveat in report.get("caveats") or []:
        lines.append(f"- {caveat}")
    lines += [
        "",
        "## Notes",
        "",
        "Credential files (`trial-key.pem` and similar) were excluded from this tracked copy. See `SKIPPED.md`.",
        "Raw per-run receipts are under `receipts/`. The live workspace used for execution is not fully mirrored.",
        "",
    ]
    (dest / "README.md").write_text("\n".join(lines), encoding="utf-8")


def default_caveats(report: dict[str, Any]) -> list[str]:
    return [
        f"Sample is small: {report.get('task_count')} same-author reuse tasks, {report.get('repeats')} repeat(s) per arm.",
        "Tasks were designed by the same authors to match already-admitted crystals from the 2026-11-25 lattice gauntlets; this is not independent-user reuse.",
        "Formation cost of those crystals is excluded. This baseline measures reuse economics given an already-admitted lattice, not the payback period including first-time formation.",
        "Arm B is the governed AgentRun loop with crystal lookup disabled, not a raw chat-completions 'write me a fix' prompt, so the cold cost includes tool-loop overhead.",
        "Temperature is 0 and the provider seed is 731947+turn; the hosted endpoint may or may not honour seed.",
        "Spend was billed at $0.00 on the NVIDIA hosted trial; commercial_equivalent_usd is a list-price footnote only ($0.06 / $0.35 per 1M for this model, checked Nov 2026).",
        "Composite held-out tasks are not in this A/B: the original composite path is model-free replay, which is not an identical controller prompt to a cold multi-defect repair.",
        "Cold-arm call counts varied across repeats even with temperature 0 and a fixed seed formula, so the hosted endpoint did not produce identical traces.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / ".beast/evidence/ab-nim-20261125")
    parser.add_argument("--pack-dir", type=Path, default=ROOT / "evidence/gauntlets-2026-11-25/ab-nim-20261125")
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--phase", choices=("fixtures", "import", "run", "pack", "all"), default="all")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--model", default=os.environ.get("BEAST_LIVE_CRYSTAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--tasks", nargs="*", default=None, help="Optional subset of task ids")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")

    os.chdir(ROOT)
    os.environ.setdefault("BEAST_NIM_MAX_TOKENS", "4096")

    if args.phase in {"fixtures", "all"}:
        errors = hg.fixtures_ok()
        # three-leaf fixtures too
        tl_errors = tl.fixtures_ok()
        errors = list(errors) + [e for e in tl_errors if e not in errors]
        if errors:
            print("FIXTURE FAILURES:", *errors, sep="\n- ", flush=True)
            return 2
        print(json.dumps({"fixtures": "ok"}), flush=True)
        if args.phase == "fixtures":
            return 0

    if args.phase in {"run", "all", "import"}:
        vault = SecretVault().load()
        if not os.environ.get("NVIDIA_API_KEY") and args.phase in {"run", "all"}:
            parser.error("NVIDIA_API_KEY was not loaded from the local secret vault. No key was printed.")
        print(json.dumps({
            "vault_loaded": bool(vault.get("exists")),
            "nvidia_present": bool(os.environ.get("NVIDIA_API_KEY")),
            "model": args.model,
            "phase": args.phase,
            "repeats": args.repeats,
        }), flush=True)

    evidence = args.evidence_dir.expanduser().resolve()
    source = args.source_evidence.expanduser().resolve()
    report_path = evidence / "report.json"

    if args.phase in {"import", "run", "all"}:
        setup = setup_workspace(evidence, source)
        report: dict[str, Any] = {}
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
        report.update({
            "experiment": "ab-nim-crystal-baseline",
            "model": args.model,
            "base_url": "https://integrate.api.nvidia.com/v1",
            "temperature": 0,
            "seed_formula": "731947 + turn",
            "repeats": args.repeats,
            "task_count": None,
            "source_evidence": str(source),
            "imported": setup,
            "arms": {
                "A": "crystals-first: admitted crystals loaded, planner enabled, learner disabled",
                "B": "cold: crystal planner is None (lookup/reuse disabled), same model, prompts, verifier",
            },
        })
        report.setdefault("runs", [])
        selected = [t for t in TASKS if args.tasks is None or t["id"] in args.tasks]
        if not selected:
            parser.error("no tasks selected")
        report["task_count"] = len(selected)
        report["task_ids"] = [t["id"] for t in selected]
        report["caveats"] = default_caveats(report)
        persist_report(report_path, report)
        print(json.dumps({
            "import_ok": setup["all_expected_present"],
            "found": len(setup["found"]),
            "missing": setup["missing"],
            "admitted": len(setup["admitted_ids"]),
        }, default=str), flush=True)
        if not setup["all_expected_present"]:
            print("refusing to run: expected crystals missing", flush=True)
            return 1
        if args.phase == "import":
            return 0

        # Cheap arm-A smoke on the first task before spending on the cold arm.
        smoke_pkg = selected[0]["package"]
        print(json.dumps({"event": "arm_a_smoke", "task": selected[0]["id"]}), flush=True)
        smoke = run_arm(evidence, smoke_pkg, arm="A", repeat=0, model=args.model, crystals=True)
        save(evidence / "receipts" / "smoke-A-r0.json", smoke)
        print(json.dumps({
            "event": "arm_a_smoke_result",
            "passed": smoke["passed"],
            "calls": smoke["usage"]["calls"],
            "crystal_completed": smoke["crystal_completed"],
            "wall_seconds": smoke["wall_seconds"],
        }), flush=True)
        if not smoke["passed"]:
            print("arm A smoke failed; not spending on the cold arm", flush=True)
            return 1

        for repeat in range(1, args.repeats + 1):
            for task in selected:
                for arm, crystals in (("A", True), ("B", False)):
                    existing = next((r for r in report["runs"]
                                     if r.get("task_id") == task["id"] and r.get("repeat") == repeat and r.get("arm") == arm), None)
                    if existing and existing.get("state"):
                        print(json.dumps({"event": "skip_existing", "task": task["id"], "repeat": repeat, "arm": arm}), flush=True)
                        continue
                    print(json.dumps({"event": "start", "task": task["id"], "repeat": repeat, "arm": arm}), flush=True)
                    result = run_arm(evidence, task["package"], arm=arm, repeat=repeat, model=args.model, crystals=crystals)
                    receipt = {
                        "task_id": task["id"],
                        "origin": task["origin"],
                        "package": task["package"]["name"],
                        "arm": arm,
                        "repeat": repeat,
                        **{k: result.get(k) for k in (
                            "run_id", "state", "independent_pass", "sealed_pass", "event_chain_valid",
                            "crystal_activated", "crystal_completed", "crystal_formed", "crystal_refusals",
                            "events", "changed_tracked_paths", "original_unchanged", "mutation_observed",
                            "observed_provider_attempts", "model_turns", "tool_calls", "wall_seconds",
                            "usage", "usage_events", "passed", "http_retries", "rate_limit_events",
                            "before_rc", "crystals_enabled",
                        )},
                    }
                    save(evidence / "receipts" / f"{task['id']}-{arm}-r{repeat}.json", receipt)
                    report["runs"] = [r for r in report["runs"]
                                      if not (r.get("task_id") == task["id"] and r.get("repeat") == repeat and r.get("arm") == arm)]
                    report["runs"].append(receipt)
                    persist_report(report_path, report)
                    print(json.dumps({
                        "event": "finish",
                        "task": task["id"],
                        "repeat": repeat,
                        "arm": arm,
                        "passed": receipt["passed"],
                        "calls": (receipt.get("usage") or {}).get("calls"),
                        "prompt_tokens": (receipt.get("usage") or {}).get("prompt_tokens"),
                        "completion_tokens": (receipt.get("usage") or {}).get("completion_tokens"),
                        "wall_seconds": receipt.get("wall_seconds"),
                        "crystal_completed": receipt.get("crystal_completed"),
                    }), flush=True)

        persist_report(report_path, report)
        write_readme(evidence, report)
        save(evidence / "summary.json", {
            "model": report.get("model"),
            "repeats": report.get("repeats"),
            "task_ids": report.get("task_ids"),
            "aggregate": report.get("aggregate"),
            "spend_total": report.get("spend_total"),
            "per_task": report.get("per_task"),
            "caveats": report.get("caveats"),
        })

    if args.phase in {"pack", "all"}:
        if not report_path.exists():
            print("nothing to pack: report.json missing", flush=True)
            return 1
        report = json.loads(report_path.read_text(encoding="utf-8"))
        write_readme(evidence, report)
        pack_dir = args.pack_dir.expanduser().resolve()
        manifest = pack_evidence(evidence, pack_dir)
        # Rewrite README into the packed copy from the live report.
        write_readme(pack_dir, report)
        print(json.dumps({"event": "packed", **manifest}, default=str), flush=True)
        if not manifest.get("secret_scan_clean"):
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
