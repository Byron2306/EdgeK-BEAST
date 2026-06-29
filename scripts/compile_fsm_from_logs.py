#!/usr/bin/env python3
"""
BEAST Finite State Machine (FSM) Compiler (Compound State Bundle Edition)

Compiles a unified, deterministic FSM lattice by ingesting Capability registries
AND augmenting with contextual reasoning traces from historical chat logs.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

# Root for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ingestion Stubs
def get_capability_registry():
    from app.kernel.capability.capability_registry import CapabilityRegistry
    return CapabilityRegistry().list_capabilities()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("beast-fsm-compiler")

def compile_fsm():
    output_path = ROOT / "data" / "fsm_lattice.json"
    logger.info("Compiling Unified Compound State FSM bundle...")

    # 1. Base Layer: Registry Ingestion & Bundling
    capability_inventory = get_capability_registry()
    fsm_lattice = {"transitions": {}}
    for cap in capability_inventory.get("capabilities", []):
        cap_id = cap["capability_id"]
        
        # Compound State Bundle
        fsm_lattice["transitions"][cap_id] = {
            "intent": cap.get("family", "general"),
            "context": {
                "roles": [cap.get("family", "general")],
                "risk_class": cap.get("risk_level", "medium")
            },
            "allowed_tools": [cap_id] if cap.get("kind") == "mcp_tool" else [],
            "allowed_skills": [cap_id] if cap.get("kind") == "skill" else [],
            "reasoning_schema": "procedural_verification_node",
            "output_contract": {
                "input": cap.get("input_schema", {}),
                "output": cap.get("output_schema", {})
            },
            "next_states": ["success"],
            "reasoning_trace": []
        }

    # 2. Augmentation Layer: Logs and Claude Context
    chat_dir = ROOT / "chat"
    claude_dir = ROOT / ".claude"
    
    for log_file in chat_dir.glob("*.jsonl"):
        _augment_from_log(log_file, fsm_lattice)
        
    for config_file in claude_dir.rglob("*.json*"):
        _augment_from_context(config_file, fsm_lattice)
        
    # 3. Augmentation Layer: Manually inject swarm/browser capabilities
    for manual_id in ["skill:swarm_orchestration", "skill:browser_automation"]:
        if manual_id not in fsm_lattice["transitions"]:
            fsm_lattice["transitions"][manual_id] = {
                "intent": "skill",
                "context": {"roles": ["orchestrator", "browser"]},
                "allowed_tools": ["mcp_playwright_inspect"],
                "allowed_skills": [manual_id],
                "reasoning_schema": "procedural_verification_node",
                "output_contract": {"input": {}, "output": {}},
                "next_states": ["success"],
                "reasoning_trace": ["manually_injected_deterministic_skill"]
            }

    # 5. Augmentation Layer: Ingest Commons Spaces
    commons_dir = ROOT / "data" / "commons_spaces"
    for space_dir in commons_dir.iterdir():
        if space_dir.is_dir():
            # Scan for manifest files
            for manifest in space_dir.rglob("*.json"):
                try:
                    content = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
                    space_id = f"space:{space_dir.name}"
                    if space_id not in fsm_lattice["transitions"]:
                        fsm_lattice["transitions"][space_id] = {
                            "intent": "compute_space",
                            "context": {"roles": ["compute_node"], "manifest": content},
                            "allowed_tools": [],
                            "allowed_skills": [],
                            "reasoning_schema": "procedural_verification_node",
                            "output_contract": {},
                            "next_states": ["success"],
                            "reasoning_trace": ["ingested_from_commons_spaces"]
                        }
                except: continue

    # 3. Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fsm_lattice, indent=2), encoding="utf-8")
    logger.info(f"Successfully compiled Unified FSM with {len(fsm_lattice['transitions'])} compound state bundles to: {output_path}")

def _augment_from_context(file_path: Path, lattice: Dict[str, Any]):
    """Ingests plugin/skill context from Claude configuration."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)
        # Identify relevant skills or tool definitions
        if "tools" in data or "skills" in data:
            # Map tools/skills to corresponding capability transitions
            for tool_name in data.get("tools", []):
                if tool_name in lattice["transitions"]:
                    lattice["transitions"][tool_name]["allowed_tools"].append("claude_plugin")
    except:
        pass

def _augment_from_log(file_path: Path, lattice: Dict[str, Any]):
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        try:
            data = json.loads(line)
            # Find tool use or reasoning steps
            messages = data.get("$set", {}).get("messages", [])
            for msg in messages:
                if msg.get("type") == "gemini":
                    for thought in msg.get("thoughts", []):
                        subject = thought.get("subject")
                        if subject in lattice["transitions"]:
                            lattice["transitions"][subject]["reasoning_trace"].append(thought.get("description"))
        except: continue

if __name__ == "__main__":
    compile_fsm()
