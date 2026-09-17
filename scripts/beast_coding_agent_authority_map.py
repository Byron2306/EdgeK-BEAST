#!/usr/bin/env python3
"""Validate and render the Phase 1 target authority contracts without runtime promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_authority_resolutions(census: dict, responsibility: dict, config: dict) -> dict:
    paths = {item["path"] for item in census.get("components", [])}
    phase1 = set(responsibility.get("phase1_conflicts", []))
    known = {item["id"] for item in responsibility.get("responsibilities", [])}
    entries = config.get("resolutions", [])
    if not isinstance(entries, list):
        raise ValueError("resolutions must be a list")
    ids = [entry.get("id") for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate Phase 1 resolution")
    missing = phase1 - set(ids)
    if missing:
        raise ValueError("missing Phase 1 resolution: " + ", ".join(sorted(missing)))
    if set(ids) != phase1 or not phase1 <= known:
        raise ValueError("unexpected Phase 1 resolution or unknown responsibility")
    missing_paths: set[str] = set()
    allowed_kinds = {"single_authority", "scoped_chain", "advisory_only", "transport_only"}
    for item in entries:
        if item.get("kind") not in allowed_kinds:
            raise ValueError(f"invalid authority kind: {item['id']}")
        contracts = item.get("authority_contracts")
        if not isinstance(contracts, list) or not contracts:
            raise ValueError(f"authority contracts required: {item['id']}")
        scopes = [contract.get("scope") for contract in contracts]
        if not all(isinstance(scope, str) and scope.strip() for scope in scopes):
            raise ValueError(f"empty authority scope: {item['id']}")
        if len(scopes) != len(set(scopes)):
            raise ValueError(f"duplicate authority scope: {item['id']}")
        if item["kind"] != "scoped_chain" and len(scopes) != 1:
            raise ValueError(f"single-scope authority required: {item['id']}")
        for contract in contracts:
            if contract.get("authority") != "authoritative":
                raise ValueError(f"one authoritative owner required per scope: {item['id']}")
            if contract.get("path") not in paths:
                missing_paths.add(str(contract.get("path")))
        for demotion in item.get("demotions", []):
            if demotion.get("path") not in paths:
                missing_paths.add(str(demotion.get("path")))
            if not demotion.get("role"):
                raise ValueError(f"demotion role required: {item['id']}")
        if not item.get("invariant") or not item.get("required_repairs"):
            raise ValueError(f"invariant and repair required: {item['id']}")
        if item.get("runtime_status") not in (None, "target_only_unverified"):
            raise ValueError(f"runtime overclaim: {item['id']}")
    if missing_paths:
        raise ValueError("missing paths: " + ", ".join(sorted(missing_paths)))
    return {"valid": True, "missing_paths": []}


def build_authority_map(census: dict, responsibility: dict, config: dict) -> dict:
    validate_authority_resolutions(census, responsibility, config)
    ids = sorted(responsibility["phase1_conflicts"])
    entries = {item["id"]: item for item in config["resolutions"]}
    resolutions = []
    for ident in ids:
        item = entries[ident]
        resolutions.append({**item, "authority_by_scope": {
            contract["scope"]: contract["path"] for contract in item["authority_contracts"]
        }})
    return {
        "beast_object_type": "beast_coding_agent_phase1_authority_map",
        "version": "1.0",
        "truth_boundary": config.get("truth_boundary", "Target authority does not prove runtime wiring."),
        "phase1_ids": ids,
        "unresolved_phase1_ids": [],
        "summary": {
            "resolution_count": len(resolutions),
            "phase1_conflicts_resolved": len(ids),
            "required_repair_count": sum(len(item["required_repairs"]) for item in resolutions),
            "runtime_promotions": 0,
        },
        "resolutions": resolutions,
    }


def render_authority_markdown(report: dict) -> str:
    lines = ["# BEAST Coding Agent Phase 1 Authority Map", "", report["truth_boundary"], "",
             "| Responsibility | Scope | Target authority | Kind |",
             "|---|---|---|---|"]
    for item in report["resolutions"]:
        for scope, path in item["authority_by_scope"].items():
            lines.append(f"| `{item['id']}` | `{scope}` | `{path}` | `{item['kind']}` |")
    lines.extend(["", "## Phase 2/3 repair queue", ""])
    for item in report["resolutions"]:
        lines.extend([f"### `{item['id']}`", "", item["invariant"], "",
                      "Target status: `target_only_unverified`.", ""])
        lines.extend(f"- `{repair}`" for repair in item["required_repairs"])
        lines.append("")
    lines.extend([
        "## Evidence boundary", "",
        "Phase 1 defines target authority by scope. It does not change the Phase 0 census or establish live wiring. The Phase 0 cross-file completion defect remains open. Desktop ingress, real provider execution, and Sensorium delivery need distinct runtime receipts before promotion. Compressed source and crystal suggestions never grant mutation authority.", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load = lambda path: json.loads((root / path).read_text(encoding="utf-8"))
    report = build_authority_map(
        load("docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json"),
        load("docs/evidence/BEAST_CODING_AGENT_RESPONSIBILITY_CENSUS.json"),
        load("config/beast_coding_agent_authority_resolutions.json"),
    )
    output = root / "docs/BEAST_CODING_AGENT_PHASE1_AUTHORITY_MAP.md"
    text = render_authority_markdown(report)
    if args.check:
        if output.read_text(encoding="utf-8") != text:
            raise SystemExit("Phase 1 authority map Markdown is stale")
    else:
        output.write_text(text, encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
