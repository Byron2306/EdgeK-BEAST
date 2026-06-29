"""Canonical evidence packets for BEAST crystallized compute.

This module joins the receipts that used to live separately: request, teacher,
runtime, semantic credit, lattice, capability, route optimizer, Forge, tools,
skills, eval gates, trace, MemoryHull, and negative cases.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def stable_packet_hash(payload: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class UnifiedEvidencePacket:
    """One reviewer-facing packet for a crystallized compute episode."""

    task_class: str
    request: Dict[str, Any] = field(default_factory=dict)
    teacher: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    semantic_credit: Dict[str, Any] = field(default_factory=dict)
    lattice: Dict[str, Any] = field(default_factory=dict)
    capability: Dict[str, Any] = field(default_factory=dict)
    route_optimizer: Dict[str, Any] = field(default_factory=dict)
    forge: Dict[str, Any] = field(default_factory=dict)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[Dict[str, Any]] = field(default_factory=list)
    eval_gate: Dict[str, Any] = field(default_factory=dict)
    trace: Dict[str, Any] = field(default_factory=dict)
    memory_hull: Dict[str, Any] = field(default_factory=dict)
    negative_cases: List[Dict[str, Any]] = field(default_factory=list)
    replay: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "beast_object_type": "unified_crystallized_compute_evidence_packet",
            "version": "1.0",
            "task_class": self.task_class,
            "request": self.request,
            "teacher": self.teacher,
            "runtime": self.runtime,
            "semantic_credit": self.semantic_credit,
            "lattice": self.lattice,
            "capability": self.capability,
            "route_optimizer": self.route_optimizer,
            "forge": self.forge,
            "tools": self.tools,
            "skills": self.skills,
            "eval_gate": self.eval_gate,
            "trace": self.trace,
            "memory_hull": self.memory_hull,
            "negative_cases": self.negative_cases,
            "replay": self.replay,
            "metrics": self.metrics,
            "created_at": self.created_at,
        }
        payload["packet_hash"] = stable_packet_hash(payload)
        return payload


class UnifiedEvidencePacketBuilder:
    """Build canonical packets from existing proof and gauntlet receipts."""

    @staticmethod
    def from_proof(
        proof: Dict[str, Any],
        *,
        gauntlet: Optional[Dict[str, Any]] = None,
        artifact_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        gauntlet = gauntlet or {}
        completion = proof.get("completion") if isinstance(proof.get("completion"), dict) else {}
        decision = completion.get("decision") if isinstance(completion.get("decision"), dict) else {}
        payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        reuse = payload.get("reuse") if isinstance(payload.get("reuse"), dict) else {}
        reuse_payload = reuse.get("payload") if isinstance(reuse.get("payload"), dict) else {}
        training = proof.get("training_receipts") if isinstance(proof.get("training_receipts"), list) else []
        first_training = training[0] if training and isinstance(training[0], dict) else {}
        lineage = proof.get("execution_lineage") if isinstance(proof.get("execution_lineage"), dict) else {}
        route_feedback = first_training.get("route_feedback") if isinstance(first_training.get("route_feedback"), dict) else {}
        live_nim_receipts = gauntlet.get("live_nim_receipts") if isinstance(gauntlet.get("live_nim_receipts"), list) else []
        local_forge_receipts = gauntlet.get("local_forge_receipts") if isinstance(gauntlet.get("local_forge_receipts"), list) else []

        packet = UnifiedEvidencePacket(
            task_class=str(proof.get("capability", {}).get("proof", {}).get("task_class") or request.get("task_class") or ""),
            request=request,
            teacher={
                "engine": lineage.get("teacher_engine"),
                "cloud_used": bool(lineage.get("cloud_used_for_training")),
                "training_observations": proof.get("training_observations"),
                "training_cloud_calls": proof.get("training_cloud_calls"),
                "live_nim_receipts": live_nim_receipts,
                "local_forge_receipts": local_forge_receipts,
            },
            runtime={
                "engine": lineage.get("runtime_engine"),
                "execution_mode": lineage.get("execution_mode"),
                "cloud_used": bool(lineage.get("cloud_used_for_completion")),
                "decision_action": decision.get("action"),
                "route_optimizer_choice": proof.get("route_optimizer_choice"),
            },
            semantic_credit={
                "credit_id": reuse.get("credit_id") or reuse_payload.get("credit_id") or completion.get("basis", {}).get("semantic_credit_id"),
                "replay_type": reuse.get("replay_type"),
                "confidence": reuse.get("confidence") or decision.get("confidence"),
            },
            lattice=proof.get("lattice") if isinstance(proof.get("lattice"), dict) else {},
            capability=proof.get("capability") if isinstance(proof.get("capability"), dict) else {},
            route_optimizer=route_feedback,
            forge={"receipts": local_forge_receipts},
            tools=list((completion.get("basis") or {}).get("tools") or []),
            skills=list((completion.get("basis") or {}).get("skills") or []),
            eval_gate=(reuse_payload.get("metadata") or {}).get("local_eval_gate", {}) if isinstance(reuse_payload.get("metadata"), dict) else {},
            trace={
                "trace_ledger_bytes": proof.get("trace_ledger_bytes"),
                "artifact_path": str(artifact_path) if artifact_path else "",
            },
            memory_hull=proof.get("memory_hull") if isinstance(proof.get("memory_hull"), dict) else {},
            negative_cases=list(gauntlet.get("negative_cases") or []),
            replay={
                "completed_locally": completion.get("completed_locally"),
                "provider_displaced": completion.get("provider_displaced"),
                "cloud_calls_during_completion": completion.get("cloud_calls_during_completion"),
                "answer_hash": stable_packet_hash({"answer": completion.get("answer", "")}),
            },
            metrics=proof.get("metrics") if isinstance(proof.get("metrics"), dict) else {},
        )
        return packet.to_dict()

    @staticmethod
    def write(packet: Dict[str, Any], path: Path) -> Dict[str, Any]:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return {
            "beast_object_type": "unified_evidence_packet_write_receipt",
            "version": "1.0",
            "path": str(target),
            "packet_hash": packet.get("packet_hash"),
        }

    @staticmethod
    def publish_to_beast_evidence_plane(packet: Dict[str, Any], data_dir: Path) -> Dict[str, Any]:
        from app.kernel.compute.crystal_evidence_bridge import CrystalEvidenceBridge

        return CrystalEvidenceBridge(Path(data_dir)).publish(packet)
