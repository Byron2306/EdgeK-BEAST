#!/usr/bin/env python3
"""Compile a deterministic capability FSM from current BEAST inventories.

The compiler treats historical traces as observations, never as execution
authority.  Registry capabilities form the complete base graph; optional chat,
plugin, and Commons artifacts can enrich only the matching transitions.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability.capability_registry import CapabilityRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("beast-fsm-compiler")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _transition(capability: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(capability.get("kind") or "capability")
    capability_id = str(capability["capability_id"])
    approval = bool(capability.get("requires_approval"))
    return {
        "intent": str(capability.get("family") or "general"),
        "context": {
            "roles": [kind],
            "risk_class": str(capability.get("risk_level") or "medium"),
            "read_only": bool(capability.get("read_only", False)),
            "writes_files": bool(capability.get("writes_files", False)),
            "network_access": bool(capability.get("network_access", False)),
        },
        "allowed_tools": [capability_id] if kind in {"mcp_tool", "tool", "plugin"} else [],
        "allowed_skills": [capability_id] if kind == "skill" else [],
        "reasoning_schema": "approval_gated_capability_node" if approval else "capability_node",
        "output_contract": {
            "input": capability.get("input_schema") or {},
            "output": capability.get("output_schema") or {},
        },
        "next_states": ["approval_pending", "success"] if approval else ["success"],
        "reasoning_trace": ["capability_registry"],
    }


def _walk_observations(paths: Iterable[Path]) -> Iterable[Dict[str, Any]]:
    """Yield bounded, schema-agnostic observations from JSON and JSONL files."""
    for path in paths:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        if path.suffix == ".jsonl":
            try:
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
            except (OSError, json.JSONDecodeError):
                continue
        else:
            value = _read_json(path)
            rows = value if isinstance(value, list) else [value]
        for row in rows:
            if isinstance(row, dict):
                yield row


def _observation_ids(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key in ("capability_id", "tool_name", "skill_name", "subject", "name"):
            item = value.get(key)
            if isinstance(item, str) and item:
                yield item
        for key in ("messages", "thoughts", "tools", "skills", "capabilities", "events"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    yield from _observation_ids(item)
        for item in value.values():
            if isinstance(item, dict):
                yield from _observation_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from _observation_ids(item)


def compile_fsm(*, output_path: Path | None = None, observation_roots: Iterable[Path] | None = None) -> Dict[str, Any]:
    """Build and atomically persist the current inventory-derived FSM."""
    output_path = output_path or ROOT / "data" / "fsm_lattice.json"
    inventory = CapabilityRegistry().list_capabilities()
    transitions = {
        str(capability["capability_id"]): _transition(capability)
        for capability in inventory.get("capabilities", [])
        if isinstance(capability, dict) and capability.get("capability_id")
    }
    roots = list(observation_roots or [ROOT / "chat", ROOT / ".claude", ROOT / "data" / "commons_spaces"])
    observed = 0
    for root in roots:
        if not root.is_dir():
            continue
        for row in _walk_observations(path for path in root.rglob("*") if path.suffix in {".json", ".jsonl"}):
            for capability_id in set(_observation_ids(row)):
                transition = transitions.get(capability_id)
                if transition is not None and len(transition["reasoning_trace"]) < 100:
                    transition["reasoning_trace"].append("observed_artifact")
                    observed += 1
    lattice = {
        "beast_object_type": "capability_fsm_lattice",
        "version": "2.0",
        "source": "capability_registry_with_observation_enrichment",
        "capability_count": len(transitions),
        "observation_matches": observed,
        "transitions": transitions,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".fsm-", suffix=".json", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(lattice, handle, indent=2, sort_keys=True)
            handle.write("\n")
        Path(temp_name).replace(output_path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    logger.info("Compiled %s capability transitions (%s observation matches) to %s", len(transitions), observed, output_path)
    return lattice


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "fsm_lattice.json")
    parser.add_argument("--observation-root", action="append", type=Path, default=[])
    args = parser.parse_args()
    compile_fsm(output_path=args.output, observation_roots=args.observation_root or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
