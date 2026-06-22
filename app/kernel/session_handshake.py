"""Canonical BEAST session handshake and agent-awareness packet."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class SessionHandshakeBuilder:
    """Tell an attached agent what BEAST already provides and how to cooperate."""

    def build(
        self,
        objective: str,
        *,
        mode: str = "openclaw",
        workspace_root: str = ".",
        tools: Iterable[str] = (),
        preflight_budget_ms: int = 500,
        scout_budget_ms: int = 300,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        budget_ms = max(25, min(int(preflight_budget_ms), 30_000))
        scout_ms = max(0, min(int(scout_budget_ms), budget_ms))
        packet = {
            "beast_object_type": "beast_session_handshake",
            "version": "1.1",
            "session_id": session_id or f"ses_{uuid.uuid4().hex[:16]}",
            "identity": {
                "runtime": "BEAST",
                "mode": str(mode or "openclaw").lower(),
                "workspace_root": workspace_root,
                "objective": str(objective or "")[:4000],
            },
            "available_help": [
                "local workspace and Chronicle retrieval",
                "Ollama scouting and bounded context ranking",
                "Tool Laziness call suppression",
                "Provider Economist role-aware routing",
                "governed Action IR and local patch compilation",
                "verification, rollback, and Chronicle evidence",
            ],
            "agent_contract": {
                "do": [
                    "Treat BEAST artifacts as the source of truth for local state.",
                    "Use the selected provider for the assigned role, not as a universal model winner.",
                    "Ask cloud providers only for unresolved semantic decisions.",
                    "Prefer local verification, deterministic transforms, and bounded context.",
                    "Respect tool skip recommendations unless the active workflow marks a tool required.",
                ],
                "avoid": [
                    "Do not reload context already present in the context packet.",
                    "Do not repeat low-value tool calls merely because they are available.",
                    "Do not bypass output governance, approval gates, or rollback.",
                    "Do not ask a cloud model to perform deterministic local compilation or verification.",
                ],
            },
            "latency_budget": {
                "preflight_budget_ms": budget_ms,
                "scout_budget_ms": scout_ms,
                "deadline_policy": "skip_optional_phase_before_overrun",
                "cloud_escalation_policy": "escalate_only_unresolved_semantic_work",
            },
            "candidate_tools": sorted({str(item) for item in tools if str(item).strip()}),
            "agent_awareness": self._agent_awareness(workspace_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "handshake_hash": "",
        }
        packet["operating_protocol"] = self._operating_protocol(packet)
        packet["agent_instruction"] = self.render_instruction(packet)
        packet["handshake_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return packet

    @staticmethod
    def render_instruction(packet: Dict[str, Any]) -> str:
        budget = packet.get("latency_budget") or {}
        awareness = packet.get("agent_awareness") if isinstance(packet.get("agent_awareness"), dict) else {}
        crystal = awareness.get("fused_crystal") if isinstance(awareness.get("fused_crystal"), dict) else {}
        commons = awareness.get("commons") if isinstance(awareness.get("commons"), dict) else {}
        return (
            "You are operating inside BEAST. BEAST already supplies local workspace intelligence, Chronicle memory, "
            "Ollama scouting, tool-value history, provider economics, output governance, local patch compilation, "
            "verification, and rollback. You are not a standalone model: act as the intent router, policy follower, "
            "and compact summarizer over BEAST's adopted Commons tools, skills, Swarm recipes, and fused crystals. "
            f"Commons currently reports {commons.get('adopted_count', 0)} adopted candidates and "
            f"{commons.get('evidence_count', 0)} evidence rows. "
            f"The active fused crystal is {crystal.get('fusion_id', 'unavailable')} with "
            f"{crystal.get('crystal_credit_units', 0)} internal credit units. "
            "Do not duplicate work BEAST has already completed. Respect required tools and learned skip recommendations. "
            "Use cloud inference only for unresolved semantic decisions. "
            f"Keep local preflight within {budget.get('preflight_budget_ms', 500)} ms and scout work within "
            f"{budget.get('scout_budget_ms', 300)} ms."
        )

    def _agent_awareness(self, workspace_root: str) -> Dict[str, Any]:
        root = Path(workspace_root or ".").resolve()
        repo_root = Path(__file__).resolve().parents[2]
        awareness: Dict[str, Any] = {
            "knows_it_is_inside_beast": True,
            "tiny_model_role": "intent_router_policy_summarizer",
            "tool_authority": "request_tools_through_beast_never_bypass_gates",
            "crystal_claim_boundary": "system_amplification_not_base_model_weight_change",
        }
        try:
            from app.kernel.meta_tool_commons import MetaToolCommons

            commons = MetaToolCommons()
            state = commons.state()
            plane = commons.evidence_plane()
            awareness["commons"] = {
                "evidence_count": int(state.get("evidence_count") or 0),
                "candidate_count": int(state.get("candidate_count") or 0),
                "adopted_count": int(state.get("adopted_count") or 0),
                "planes": [
                    {
                        "plane": item.get("plane"),
                        "evidence_count": item.get("evidence_count"),
                        "verified_rate": item.get("verified_rate"),
                        "safe_rate": item.get("safe_rate"),
                    }
                    for item in (plane.get("planes") or [])[:8]
                    if isinstance(item, dict)
                ],
                "candidate_summary": plane.get("candidate_summary") or {},
            }
        except Exception as exc:
            awareness["commons"] = {"available": False, "reason": str(exc)[:160]}
        try:
            from app.kernel.capability_registry import CapabilityRegistry

            inventory = CapabilityRegistry().list_capabilities()
            awareness["capability_registry"] = {
                "count": inventory.get("count", 0),
                "kinds": inventory.get("kinds", {}),
                "top_families": dict(list((inventory.get("families") or {}).items())[:12]),
            }
        except Exception as exc:
            awareness["capability_registry"] = {"available": False, "reason": str(exc)[:160]}

        crystal_paths = [
            root / "benchmarks" / "results" / "tiny_llama_crystal_amplification_gauntlet" / "llama_open_mcp_capability_registry_fusion.json",
            repo_root / "benchmarks" / "results" / "tiny_llama_crystal_amplification_gauntlet" / "llama_open_mcp_capability_registry_fusion.json",
            repo_root / "benchmarks" / "results" / "tiny_llama_crystal_amplification_gauntlet" / "llama_opus_style_full_commons_fusion.json",
        ]
        awareness["fused_crystal"] = self._load_fused_crystal_digest(crystal_paths)
        return awareness

    @staticmethod
    def _load_fused_crystal_digest(paths: Iterable[Path]) -> Dict[str, Any]:
        for path in paths:
            try:
                if not path.exists():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                fused = payload.get("fused_inference_crystal") if isinstance(payload.get("fused_inference_crystal"), dict) else payload
                economics = fused.get("economics") if isinstance(fused.get("economics"), dict) else payload.get("economics", {})
                verification = fused.get("seal_verification") if isinstance(fused.get("seal_verification"), dict) else payload.get("seal_verification", {})
                components = payload.get("component_counts") or fused.get("component_counts")
                if not isinstance(components, dict):
                    raw_components = fused.get("components") if isinstance(fused.get("components"), dict) else {}
                    components = {key: len(value) for key, value in raw_components.items() if isinstance(value, list)}
                return {
                    "artifact": str(path),
                    "fusion_id": fused.get("fusion_id"),
                    "name": fused.get("name"),
                    "task_class": fused.get("task_class"),
                    "component_counts": components,
                    "tokens_displaced_estimate": economics.get("tokens_displaced_estimate"),
                    "crystal_credit_units": economics.get("crystal_credit_units"),
                    "seal_verified": bool(verification.get("verified") or verification.get("valid")),
                    "crypto_profile": (fused.get("seal") or {}).get("crypto_profile") if isinstance(fused.get("seal"), dict) else {},
                }
            except Exception:
                continue
        return {"available": False, "reason": "no fused crystal artifact found"}

    @staticmethod
    def _operating_protocol(packet: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "llama_loop": [
                "Classify the task and desired safety posture.",
                "Ask BEAST/Commons which adopted capability or crystal matches the task.",
                "Prefer fused crystals and local tools before cloud calls.",
                "Use ZeroClaw for planning when execution is unsafe or unnecessary.",
                "Use OpenClaw for local inspection and approval-gated patch preparation.",
                "Run verification gates and summarize receipts before claiming success.",
                "Promote repeated successful patterns back into Commons/Forge.",
            ],
            "tool_request_format": {
                "intent": "short task intent",
                "task_class": "routing label",
                "needed_capability": "capability_id_or_role",
                "risk": "low|medium|high",
                "approval_required": "true when writes/network/execution are needed",
            },
            "hard_bounds": [
                "Do not execute tools directly when BEAST requires approval.",
                "Do not treat discovery-only MCP seeds as installed tools.",
                "Do not expose raw secrets, prompts, paths, or source bodies in Commons evidence.",
            ],
        }
