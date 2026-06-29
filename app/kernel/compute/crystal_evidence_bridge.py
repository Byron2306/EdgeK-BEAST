"""Bridge crystallized compute packets into BEAST's shared evidence plane."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.evidence_chronicle import EvidenceChronicleWriter
from app.kernel.storage.evidence_envelope import EvidenceEnvelopeFactory
from app.kernel.storage.memory_hull import MemoryHull


def _sha256(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class CrystalEvidenceBridge:
    """Convert a unified crystal packet into Chronicle, Hull, and sealed receipts.

    The bridge intentionally stores hashes, metrics, identities, and verifier
    state instead of raw prompts or source content. The unified packet remains
    the rich artifact; this class publishes the parts other BEAST layers can
    rank, inspect, and verify.
    """

    data_dir: Path
    evidence_factory: Optional[EvidenceEnvelopeFactory] = None
    chronicle: Optional[EvidenceChronicleWriter] = None
    memory_hull: Optional[MemoryHull] = None
    seal: Optional[ResidueSeal] = None

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.evidence_factory = self.evidence_factory or EvidenceEnvelopeFactory()
        self.chronicle = self.chronicle or EvidenceChronicleWriter(str(self.data_dir), enabled=True)
        self.seal = self.seal or ResidueSeal(self.data_dir / "keys" / "residue")
        self.memory_hull = self.memory_hull or MemoryHull(self.data_dir / "vault", seal=self.seal)

    def publish(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        packet_hash = str(packet.get("packet_hash") or _sha256(packet))
        envelopes = self.build_envelopes(packet)
        chronicle_receipts = [
            self.chronicle.write(envelope, reason="crystallized_compute_unified_packet")
            for envelope in envelopes
        ]
        hull_receipt = self.memory_hull.write_residue(
            task=f"Crystallized compute evidence: {packet.get('task_class') or 'unknown_task'}",
            provider=str((packet.get("teacher") or {}).get("engine") or ""),
            cost_saved=(packet.get("metrics") or {}).get("runtime_tokens_avoided", 0),
            decision=str((packet.get("runtime") or {}).get("decision_action") or "crystal_evidence_recorded"),
            evidence=self._residue_evidence(packet, envelopes, chronicle_receipts),
            section="residue",
            policy_tags=[
                "crystallized_compute",
                "unified_evidence_packet",
                "cloud_disabled_replay" if not (packet.get("runtime") or {}).get("cloud_used") else "cloud_training",
            ],
            caller="spiffe://beast.local/runtime-governor/crystal-evidence-bridge",
            correlation_id=packet_hash,
        )
        receipt = {
            "beast_object_type": "crystal_evidence_bridge_receipt",
            "version": "1.0",
            "packet_hash": packet_hash,
            "task_class": packet.get("task_class"),
            "envelope_count": len(envelopes),
            "evidence_ids": [item.get("evidence_id") for item in envelopes],
            "chronicle_receipts": chronicle_receipts,
            "memory_hull": hull_receipt,
            "metrics": self._normalized_metrics(packet),
        }
        receipt["residue_seal"] = self.seal.sign(receipt, purpose="crystal_evidence_bridge_receipt")
        self._write_receipt(packet_hash, receipt)
        return receipt

    def build_envelopes(self, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        confidence = self._confidence(packet)
        task_class = str(packet.get("task_class") or "unknown_task")
        packet_hash = str(packet.get("packet_hash") or _sha256(packet))
        provider = str((packet.get("teacher") or {}).get("engine") or "")
        runtime = packet.get("runtime") if isinstance(packet.get("runtime"), dict) else {}
        metrics = self._normalized_metrics(packet)

        primary = self.evidence_factory.build(
            source_type="crystallized_compute",
            source_uri=packet_hash,
            scope=task_class,
            artifact_type="unified_evidence_packet",
            severity="info",
            confidence=confidence,
            relevance=0.95,
            risk=0.1 if runtime.get("cloud_used") is False else 0.25,
            blast_radius=0.25,
            repeat_count=max(1, int(metrics.get("actual_reuse_count") or metrics.get("reuse_observations") or 1)),
            verification_strength=0.95 if (packet.get("eval_gate") or {}) else 0.8,
            provider=provider,
            signals=self._signals(packet),
            relationships=self._relationships(packet),
            recommended_actions=[
                "publish_to_memory_hull",
                "record_chronicle_event",
                "consider_commons_space_candidate",
                "run_cloud_disabled_replay",
            ],
            recommended_capability_id=str((packet.get("semantic_credit") or {}).get("credit_id") or ""),
            capability_family="crystallized_compute",
            summary=self._summary(packet),
        )

        negative_cases = packet.get("negative_cases") if isinstance(packet.get("negative_cases"), list) else []
        blocked = [case for case in negative_cases if isinstance(case, dict) and case.get("blocked") is True]
        negative = self.evidence_factory.build(
            source_type="crystallized_compute_negative_cases",
            source_uri=f"{packet_hash}#negative_cases",
            scope=task_class,
            artifact_type="reuse_safety_mutations",
            severity="warning" if len(blocked) != len(negative_cases) else "info",
            confidence=1.0 if negative_cases and len(blocked) == len(negative_cases) else 0.55,
            relevance=0.9,
            risk=0.15 if negative_cases and len(blocked) == len(negative_cases) else 0.65,
            blast_radius=0.55,
            repeat_count=max(1, len(negative_cases) or 1),
            verification_strength=0.9 if negative_cases else 0.35,
            provider=provider,
            signals=[f"negative_cases={len(negative_cases)}", f"blocked={len(blocked)}"],
            relationships=[{"type": "derived_from", "target": primary["evidence_id"]}],
            recommended_actions=["keep_reuse_fail_closed", "quarantine_failed_mutations"],
            capability_family="crystallized_compute_safety",
            summary=f"{len(blocked)}/{len(negative_cases)} unsafe crystal reuse mutations blocked.",
        )
        return [primary, negative]

    def _residue_evidence(
        self,
        packet: Dict[str, Any],
        envelopes: Iterable[Dict[str, Any]],
        chronicle_receipts: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "packet_hash": packet.get("packet_hash"),
            "task_class": packet.get("task_class"),
            "teacher": self._safe_subset(packet.get("teacher") or {}, ["engine", "cloud_used", "training_cloud_calls"]),
            "runtime": self._safe_subset(
                packet.get("runtime") or {},
                ["engine", "execution_mode", "cloud_used", "decision_action"],
            ),
            "semantic_credit": self._safe_subset(packet.get("semantic_credit") or {}, ["credit_id", "confidence", "replay_type"]),
            "metrics": self._normalized_metrics(packet),
            "evidence_ids": [item.get("evidence_id") for item in envelopes],
            "chronicle_written": [bool(item.get("written")) for item in chronicle_receipts],
            "negative_case_count": len(packet.get("negative_cases") or []),
        }

    def _normalized_metrics(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        metrics = packet.get("metrics") if isinstance(packet.get("metrics"), dict) else {}
        replay = packet.get("replay") if isinstance(packet.get("replay"), dict) else {}
        return {
            "training_tokens_observed": int(metrics.get("training_tokens_observed") or 0),
            "runtime_tokens_avoided": int(metrics.get("runtime_tokens_avoided") or metrics.get("tokens_displaced") or 0),
            "fused_crystal_estimate": int(metrics.get("fused_crystal_estimate") or 0),
            "actual_reuse_count": int(metrics.get("actual_reuse_count") or 0),
            "unique_crystals": int(metrics.get("unique_crystals") or (1 if (packet.get("semantic_credit") or {}).get("credit_id") else 0)),
            "reuse_observations": int(metrics.get("reuse_observations") or metrics.get("actual_reuse_count") or 0),
            "cloud_calls_during_completion": int(replay.get("cloud_calls_during_completion") or 0),
        }

    def _signals(self, packet: Dict[str, Any]) -> List[str]:
        runtime = packet.get("runtime") if isinstance(packet.get("runtime"), dict) else {}
        metrics = self._normalized_metrics(packet)
        return [
            f"runtime_engine={runtime.get('engine') or ''}",
            f"decision_action={runtime.get('decision_action') or ''}",
            f"cloud_used_for_completion={bool(runtime.get('cloud_used'))}",
            f"runtime_tokens_avoided={metrics['runtime_tokens_avoided']}",
            f"unique_crystals={metrics['unique_crystals']}",
        ]

    def _relationships(self, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        relationships: List[Dict[str, Any]] = []
        credit_id = (packet.get("semantic_credit") or {}).get("credit_id")
        if credit_id:
            relationships.append({"type": "semantic_credit", "target": str(credit_id)})
        lattice_hash = (packet.get("lattice") or {}).get("lattice_hash")
        if lattice_hash:
            relationships.append({"type": "lattice", "target": str(lattice_hash)})
        capability_id = (packet.get("capability") or {}).get("capability_id")
        if capability_id:
            relationships.append({"type": "capability", "target": str(capability_id)})
        return relationships

    def _summary(self, packet: Dict[str, Any]) -> str:
        runtime = packet.get("runtime") if isinstance(packet.get("runtime"), dict) else {}
        metrics = self._normalized_metrics(packet)
        return (
            f"Crystallized compute packet for {packet.get('task_class') or 'unknown task'} "
            f"using runtime {runtime.get('engine') or 'unknown'}; "
            f"cloud completion used={bool(runtime.get('cloud_used'))}; "
            f"runtime tokens avoided={metrics['runtime_tokens_avoided']}."
        )

    def _confidence(self, packet: Dict[str, Any]) -> float:
        semantic = packet.get("semantic_credit") if isinstance(packet.get("semantic_credit"), dict) else {}
        capability = packet.get("capability") if isinstance(packet.get("capability"), dict) else {}
        for value in (semantic.get("confidence"), capability.get("confidence")):
            if value is not None:
                return max(0.0, min(1.0, float(value)))
        return 0.85

    @staticmethod
    def _safe_subset(payload: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
        return {key: payload.get(key) for key in keys if key in payload}

    def _write_receipt(self, packet_hash: str, receipt: Dict[str, Any]) -> None:
        receipt_dir = self.data_dir / "crystal_evidence_bridge"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        safe_name = packet_hash.replace("sha256:", "")
        (receipt_dir / f"{safe_name}.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
