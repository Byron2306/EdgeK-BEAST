#!/usr/bin/env python3
"""Validate and render the BEAST coding-agent responsibility census.

The full-system census answers what exists. This module answers which existing
components currently claim a coding-agent responsibility, what evidence backs
that claim, and which ownership questions must pass to Phase 1.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {
    "observed_authoritative",
    "static_authoritative",
    "supporting_only",
    "unresolved_conflict",
    "dormant_or_stranded",
}
ALLOWED_ROLES = {
    "current_authority",
    "candidate_authority",
    "supporting",
    "dormant_candidate",
    "compatibility",
}
ALLOWED_DISPOSITIONS = {
    "online_authoritative",
    "online_supporting",
    "supervised_offline",
    "dormant_gated",
    "stranded",
    "duplicate_candidate",
    "compatibility_shim",
    "retired",
}
ALLOWED_RELEVANCE = {"direct", "supporting"}
ALLOWED_EVIDENCE = {
    "observed_runtime",
    "static_contract",
    "existing_disposition_registry",
    "historical_proof",
    "not_runtime_proven",
}


def _component_paths(census: dict[str, Any]) -> set[str]:
    return {
        str(item.get("path") or "")
        for item in census.get("components") or []
        if isinstance(item, dict) and str(item.get("path") or "")
    }


def validate_responsibility_config(census: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    paths = _component_paths(census)
    responsibilities = config.get("responsibilities")
    if not isinstance(responsibilities, list):
        raise ValueError("responsibility config requires responsibilities list")

    seen_ids: set[str] = set()
    missing_paths: list[str] = []
    claimant_paths: set[str] = set()

    for responsibility in responsibilities:
        if not isinstance(responsibility, dict):
            raise ValueError("responsibility entry must be an object")
        responsibility_id = str(responsibility.get("id") or "").strip()
        if not responsibility_id:
            raise ValueError("responsibility id is required")
        if responsibility_id in seen_ids:
            raise ValueError(f"duplicate responsibility id: {responsibility_id}")
        seen_ids.add(responsibility_id)

        status = str(responsibility.get("status") or "").strip()
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"invalid responsibility status for {responsibility_id}: {status}")
        claimants = responsibility.get("claimants")
        if not isinstance(claimants, list) or not claimants:
            raise ValueError(f"responsibility {responsibility_id} requires claimants")

        authorities: list[str] = []
        for claimant in claimants:
            if not isinstance(claimant, dict):
                raise ValueError(f"claimant for {responsibility_id} must be an object")
            path = str(claimant.get("path") or "").strip()
            if path not in paths:
                missing_paths.append(path or "<empty>")
            claimant_paths.add(path)

            role = str(claimant.get("role") or "").strip()
            if role not in ALLOWED_ROLES:
                raise ValueError(f"invalid claimant role for {responsibility_id}: {role}")
            disposition = str(claimant.get("disposition") or "").strip()
            if disposition == "unclassified":
                raise ValueError(
                    f"coding-agent-relevant claimant remains unclassified: {path}"
                )
            if disposition not in ALLOWED_DISPOSITIONS:
                raise ValueError(
                    f"invalid claimant disposition for {responsibility_id}: {disposition}"
                )
            relevance = str(claimant.get("agent_relevance") or "").strip()
            if relevance not in ALLOWED_RELEVANCE:
                raise ValueError(f"invalid agent relevance for {responsibility_id}: {relevance}")
            evidence = str(claimant.get("evidence") or "").strip()
            if evidence not in ALLOWED_EVIDENCE:
                raise ValueError(f"invalid claimant evidence for {responsibility_id}: {evidence}")
            if role == "current_authority":
                authorities.append(path)

        if len(authorities) > 1 and status != "unresolved_conflict":
            raise ValueError(
                f"multiple current authorities for {responsibility_id}: {', '.join(authorities)}"
            )

    if missing_paths:
        raise ValueError("missing claimant path: " + ", ".join(sorted(set(missing_paths))))

    return {
        "valid": True,
        "responsibility_count": len(responsibilities),
        "claimant_count": sum(len(item.get("claimants") or []) for item in responsibilities),
        "unique_claimant_count": len(claimant_paths),
        "missing_paths": [],
    }


def build_responsibility_report(census: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    validation = validate_responsibility_config(census, config)
    responsibilities: list[dict[str, Any]] = []
    phase1_conflicts: list[str] = []

    for source in config.get("responsibilities") or []:
        item = dict(source)
        claimants = [dict(claimant) for claimant in source.get("claimants") or []]
        item["claimants"] = claimants
        item["current_authorities"] = sorted(
            claimant["path"]
            for claimant in claimants
            if claimant.get("role") == "current_authority"
        )
        item["candidate_authorities"] = sorted(
            claimant["path"]
            for claimant in claimants
            if claimant.get("role") == "candidate_authority"
        )
        item["claimant_count"] = len(claimants)
        if item.get("phase1_required") is True or item.get("status") == "unresolved_conflict":
            phase1_conflicts.append(str(item["id"]))
        responsibilities.append(item)

    status_counts: dict[str, int] = {}
    for item in responsibilities:
        status = str(item.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "beast_object_type": "beast_coding_agent_responsibility_census",
        "version": "1.0",
        "truth_rule": (
            "A responsibility claim identifies current ownership pressure; it does not promote "
            "runtime participation unless the claimant evidence is observed_runtime."
        ),
        "summary": {
            "responsibility_count": len(responsibilities),
            "claimant_count": validation["claimant_count"],
            "unique_claimant_count": validation["unique_claimant_count"],
            "unresolved_conflict_count": sum(
                item.get("status") == "unresolved_conflict" for item in responsibilities
            ),
            "phase1_conflict_count": len(sorted(set(phase1_conflicts))),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "phase1_conflicts": sorted(set(phase1_conflicts)),
        "responsibilities": responsibilities,
    }


def render_responsibility_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# BEAST Coding Agent Responsibility Census",
        "",
        "## Truth boundary",
        "",
        report["truth_rule"],
        "",
        f"Responsibilities: **{summary['responsibility_count']}**  ",
        f"Unique claimants: **{summary['unique_claimant_count']}**  ",
        f"Unresolved conflicts: **{summary['unresolved_conflict_count']}**  ",
        f"Phase 1 ownership conflicts: **{summary['phase1_conflict_count']}**",
        "",
        "## Responsibility map",
        "",
        "| Responsibility | Status | Current authority | Candidate/supporting claimants | Evidence |",
        "|---|---|---|---|---|",
    ]
    for item in report["responsibilities"]:
        authorities = ", ".join(f"`{path}`" for path in item["current_authorities"]) or "none proven"
        others = [
            claimant for claimant in item["claimants"]
            if claimant.get("role") != "current_authority"
        ]
        claimant_text = ", ".join(
            f"`{claimant['path']}` ({claimant['role']})" for claimant in others
        ) or "none"
        evidence = ", ".join(sorted({str(c.get("evidence") or "") for c in item["claimants"]}))
        lines.append(
            f"| `{item['id']}` | `{item['status']}` | {authorities} | {claimant_text} | {evidence} |"
        )

    lines.extend(["", "## Phase 1 ownership conflicts", ""])
    for responsibility_id in report["phase1_conflicts"]:
        item = next(entry for entry in report["responsibilities"] if entry["id"] == responsibility_id)
        lines.append(f"### `{responsibility_id}`")
        lines.append("")
        lines.append(str(item.get("finding") or "Ownership requires Phase 1 resolution."))
        lines.append("")
        for claimant in item["claimants"]:
            lines.append(
                f"- `{claimant['path']}`: role `{claimant['role']}`, disposition "
                f"`{claimant['disposition']}`, evidence `{claimant['evidence']}`."
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    census = _load_json(args.census)
    config = _load_json(args.config)
    report = build_responsibility_report(census, config)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.md_out.write_text(render_responsibility_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
