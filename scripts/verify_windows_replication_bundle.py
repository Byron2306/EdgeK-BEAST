#!/usr/bin/env python3
"""Independently verify the Windows port and Ollama replication bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def canonical_digest(value: dict) -> str:
    body = dict(value)
    body.pop("receipt_digest", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_mcnemar(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if not n:
        return 1.0
    k = min(left_only, right_only)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2**n))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify(port_path: Path, uplift_path: Path, manifest_path: Path) -> dict:
    port, uplift, manifest = load(port_path), load(uplift_path), load(manifest_path)
    require(manifest.get("object_type") == "beast_windows_replication_manifest", "wrong manifest type")
    require(manifest.get("port_receipt") == raw_digest(port_path), "port raw hash mismatch")
    require(manifest.get("uplift_receipt") == raw_digest(uplift_path), "uplift raw hash mismatch")
    require(port.get("receipt_digest") == canonical_digest(port), "port canonical digest mismatch")
    require(uplift.get("receipt_digest") == canonical_digest(uplift), "uplift canonical digest mismatch")
    for name, receipt in (("port", port), ("uplift", uplift)):
        require(str(receipt.get("physical_domain", "")).startswith("windows"), f"{name} is not Windows evidence")
        require(receipt.get("self_test") is False, f"{name} is self-test evidence")
        require(receipt.get("verified") is True, f"{name} is not verified")
        require(receipt.get("machine") == manifest.get("machine"), f"{name} machine mismatch")

    heldout = port.get("heldout_trials", [])
    require(len(heldout) >= 4 and all(t.get("verified") for t in heldout), "port held-out trials failed")
    require(any(t.get("negative") for t in heldout), "port negative case missing")
    require(port.get("provider_calls") == 0, "port replay made provider calls")
    require(port.get("provider_disabled_recurrence") is True, "port provider-disabled recurrence failed")
    require(port.get("stale_process_refused") is True, "port staleness refusal failed")

    trials = uplift.get("trials", [])
    require(uplift.get("held_out") is True and uplift.get("blinded") is True, "uplift was not held-out and blinded")
    require(len(trials) >= 8, "uplift sample is too small")
    require(all(t.get("assisted_passed") for t in trials), "an assisted trial failed")
    baseline = sum(bool(t.get("baseline_passed")) for t in trials)
    assisted = sum(bool(t.get("assisted_passed")) for t in trials)
    require((baseline, assisted) == (uplift.get("baseline_successes"), uplift.get("assisted_successes")), "success totals mismatch")
    left = sum(bool(t.get("baseline_passed")) and not bool(t.get("assisted_passed")) for t in trials)
    right = sum(bool(t.get("assisted_passed")) and not bool(t.get("baseline_passed")) for t in trials)
    reported_p = exact_mcnemar(left, right)
    require(math.isclose(reported_p, float(uplift.get("exact_mcnemar_p")), abs_tol=1e-15), "McNemar result mismatch")
    require(uplift.get("negative_cases_passed") == uplift.get("negative_cases_total") == 2, "negative controls failed")
    require(uplift.get("provider_calls_assisted") == 0, "assisted replay called Ollama")
    require(uplift.get("provider_calls_avoided") == len(trials), "avoided-call count mismatch")
    require(uplift.get("provider_disabled_replay_passed") is True, "provider-disabled replay failed")
    require(uplift.get("model") == manifest.get("model"), "model mismatch")

    # Repeated observations of one held-out value are not independent. Collapse
    # by task_id and report a conservative paired test across unique tasks.
    grouped: dict[str, list[dict]] = {}
    for trial in trials:
        grouped.setdefault(str(trial.get("task_id")), []).append(trial)
    require(all(len(group) >= 1 for group in grouped.values()), "empty task group")
    unique_left = sum(all(t.get("baseline_passed") for t in group) and not all(t.get("assisted_passed") for t in group) for group in grouped.values())
    unique_right = sum(all(t.get("assisted_passed") for t in group) and not all(t.get("baseline_passed") for t in group) for group in grouped.values())
    conservative_p = exact_mcnemar(unique_left, unique_right)
    require(conservative_p < 0.05, "uplift is not significant after collapsing repeated tasks")

    return {
        "bundle_verified": True,
        "machine": manifest["machine"],
        "model": uplift["model"],
        "port_receipt_digest": port["receipt_digest"],
        "uplift_receipt_digest": uplift["receipt_digest"],
        "baseline_successes": baseline,
        "assisted_successes": assisted,
        "trials": len(trials),
        "unique_tasks": len(grouped),
        "reported_exact_mcnemar_p": reported_p,
        "conservative_unique_task_p": conservative_p,
        "negative_cases": uplift["negative_cases_passed"],
        "assisted_provider_calls": uplift["provider_calls_assisted"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=Path)
    parser.add_argument("uplift", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.port, args.uplift, args.manifest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
