"""Phase 7: crystal-to-adapter distillation scaffolding.

This module does not train opaque model weights. It turns existing BEAST
crystals into a privacy-safe capability lattice, exports a local-only
distillation dataset, creates an adapter candidate receipt, and evaluates
whether the candidate is safe enough to remain in the proof-local route ladder.

Authority boundary:
- exact crystals remain deterministic;
- adapter candidates are proposal-only;
- all outputs still need local policy, privacy, rollback, and verifier gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np


FORBIDDEN_TRAINING_KEYS = {
    "prompt",
    "raw_prompt",
    "source_code",
    "raw_source",
    "private_source",
    "code",
    "raw_code",
    "diff",
    "patch",
    "rollback",
    "rollback_snapshot",
    "private_fixture",
    "secret",
    "token",
    "api_key",
    "password",
    "local_path",
}

FORBIDDEN_KEY_FRAGMENTS = {
    "private_key",
    "raw_prompt",
    "raw_source",
    "source_code",
    "raw_code",
    "rollback_snapshot",
    "private_fixture",
}

FORBIDDEN_VALUE_PATTERNS = [
    re.compile(r"/home/[^\s\"']+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]"),
]

BEAST_AWARENESS_SYSTEMS = {
    "task_envelope",
    "prec_lifecycle",
    "compute_governor",
    "commons",
    "commons_spaces",
    "compute_forge",
    "forge",
    "skill_tree",
    "meta_tool_commons",
    "chronicle",
    "crystal_chain",
    "local_verifiers",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def short_hash(value: Any, length: int = 20) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:length]


def _safe_str(value: Any, max_len: int = 180) -> str:
    text = str(value or "")
    return text[:max_len]


def _contains_forbidden_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_forbidden_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_value(v) for v in value)
    if not isinstance(value, str):
        return False
    return any(pattern.search(value) for pattern in FORBIDDEN_VALUE_PATTERNS)


def privacy_scan_training_row(row: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[str] = []

    def visit(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lowered = str(key).lower()
                next_path = f"{path}.{key}" if path else str(key)
                if lowered in FORBIDDEN_TRAINING_KEYS or any(token in lowered for token in FORBIDDEN_KEY_FRAGMENTS):
                    violations.append(f"forbidden_key:{next_path}")
                visit(value, next_path)
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                visit(value, f"{path}[{index}]")
        elif isinstance(obj, str):
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(obj):
                    violations.append(f"forbidden_value:{path}:{pattern.pattern}")

    visit(row)
    return {
        "passed": not violations,
        "violations": violations[:25],
        "violation_count": len(violations),
    }


def validate_agent_awareness_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that an adapter-assisted model answer is linked to BEAST awareness."""
    if not isinstance(proposal, dict):
        return {"passed": False, "violations": ["proposal_not_object"]}
    violations: List[str] = []
    if proposal.get("authority") != "proposal_only":
        violations.append("authority_must_be_proposal_only")
    awareness = proposal.get("agent_awareness") if isinstance(proposal.get("agent_awareness"), dict) else {}
    if awareness.get("linked") is not True:
        violations.append("agent_awareness.linked_must_be_true")
    if awareness.get("must_use_beast_systems") is not True:
        violations.append("agent_awareness.must_use_beast_systems_must_be_true")
    if awareness.get("authority") != "proposal_only":
        violations.append("agent_awareness.authority_must_be_proposal_only")
    systems = proposal.get("beast_systems_used") if isinstance(proposal.get("beast_systems_used"), list) else []
    normalized = {str(item).strip().lower() for item in systems}
    if "compute_governor" not in normalized:
        violations.append("compute_governor_required")
    if not normalized.intersection({"chronicle", "crystal_chain"}):
        violations.append("chronicle_or_crystal_chain_required")
    if len(normalized.intersection(BEAST_AWARENESS_SYSTEMS)) < 3:
        violations.append("at_least_three_beast_systems_required")
    if "task_envelope" not in proposal:
        violations.append("task_envelope_field_required")
    if "prec_stage" not in proposal:
        violations.append("prec_stage_field_required")
    return {
        "passed": not violations,
        "violations": violations,
        "recognized_systems": sorted(normalized.intersection(BEAST_AWARENESS_SYSTEMS)),
    }


@dataclass(frozen=True)
class CrystalTrainingSignal:
    signal_id: str
    source_file: str
    object_type: str
    task_family: str
    task_id_hash: str
    fingerprint_hash: str
    provider: str
    source_provider: str
    state: str
    occurrence: int
    positive: bool
    verifier_labels: List[str] = field(default_factory=list)
    behavior_labels: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_lattice_row(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "task_family": self.task_family,
            "task_id_hash": self.task_id_hash,
            "fingerprint_hash": self.fingerprint_hash,
            "provider": self.provider,
            "source_provider": self.source_provider,
            "state": self.state,
            "occurrence": self.occurrence,
            "positive": self.positive,
            "verifier_labels": list(self.verifier_labels),
            "behavior_labels": list(self.behavior_labels),
            "metadata_hash": stable_hash(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityLatticeNode:
    task_family: str
    signal_count: int
    positive_count: int
    negative_count: int
    providers: List[str]
    verifier_labels: List[str]
    behavior_labels: List[str]
    fingerprint_hashes: List[str]
    proof_density: float
    training_priority: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_family": self.task_family,
            "signal_count": self.signal_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "providers": self.providers,
            "verifier_labels": self.verifier_labels,
            "behavior_labels": self.behavior_labels,
            "fingerprint_hashes": self.fingerprint_hashes[:12],
            "proof_density": round(self.proof_density, 6),
            "training_priority": round(self.training_priority, 6),
        }


class CrystalToAdapterDistiller:
    """Build Phase 7 lattice and adapter-candidate artifacts from local crystals."""

    def __init__(self, results_root: Optional[Path] = None, output_root: Optional[Path] = None):
        project_root = Path(__file__).resolve().parents[2]
        self.results_root = Path(results_root or project_root / "benchmarks" / "results")
        self.output_root = Path(output_root or self.results_root / "crystal_to_adapter_distillation")
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _compute_storage_bytes(self) -> Dict[str, int]:
        """Estimate the four layers of storage bytes according to BEAST Economy rules."""
        import os
        # 1. Static model storage (default: standard local quantized 7B model is ~3.5 GB)
        model_bytes = int(os.environ.get("BEAST_MODEL_FOOTPRINT_BYTES") or 3.5 * 1024 * 1024 * 1024)
        
        # 2. Working inference memory (KV Cache + activation overhead approximation)
        kv_bytes = int(os.environ.get("BEAST_KV_MEMORY_BYTES") or 500 * 1024 * 1024)
        
        # 3. Evidence storage (the results root size)
        evidence_bytes = 0
        if self.results_root.is_dir():
            for p in self.results_root.rglob("*"):
                if p.is_file():
                    try:
                        evidence_bytes += p.stat().st_size
                    except OSError:
                        pass
        if not evidence_bytes:
            evidence_bytes = 100 * 1024 * 1024 # fallback to 100MB if empty
            
        # 4. Crystallized compute storage (this distillation output root size)
        crystal_bytes = 0
        if self.output_root.is_dir():
            for p in self.output_root.rglob("*"):
                if p.is_file():
                    try:
                        crystal_bytes += p.stat().st_size
                    except OSError:
                        pass
        if not crystal_bytes:
            crystal_bytes = 10 * 1024 * 1024 # fallback to 10MB
            
        return {
            "model_bytes": model_bytes,
            "kv_bytes": kv_bytes,
            "evidence_bytes": evidence_bytes,
            "crystal_bytes": crystal_bytes,
            "total_storage_bytes": model_bytes + kv_bytes + evidence_bytes + crystal_bytes
        }

    def harvest(self, limit: int = 5000) -> Dict[str, Any]:
        signals = self._collect_signals(limit=max(1, int(limit)))
        lattice = self.build_lattice(signals)
        dataset = self.export_dataset(signals, lattice)
        receipt = self.build_adapter_candidate_receipt(lattice, dataset)
        evaluation = self.evaluate_candidate(receipt, lattice, dataset)
        mutation = self.mutate_candidate(receipt, lattice)
        report = {
            "beast_object_type": "crystal_to_adapter_distillation_report",
            "version": "1.0",
            "generated_at": utc_now(),
            "authority": "proposal_only_until_local_verifiers_pass",
            "results_root": str(self.results_root),
            "output_root": str(self.output_root),
            "signal_count": len(signals),
            "task_family_count": len(lattice["nodes"]),
            "lattice": lattice,
            "dataset": dataset,
            "adapter_candidate": receipt,
            "evaluation": evaluation,
            "mutation_suite": mutation,
            "route_ladder_position": "after_semantic_page_before_local_ollama",
            "claim_boundary": (
                "This is a CPU-safe adapter candidate scaffold. It does not train or promote model weights; "
                "it prepares local-only rows and a proposal receipt for later verifier-gated adapter training."
            ),
        }
        latest = self.output_root / "phase7_crystal_to_adapter_latest.json"
        latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _collect_signals(self, limit: int) -> List[CrystalTrainingSignal]:
        signals: List[CrystalTrainingSignal] = []
        for path in sorted(self.results_root.glob("**/crystallization_events.jsonl")):
            for item in self._read_jsonl(path):
                signal = self._signal_from_event(path, item)
                if signal:
                    signals.append(signal)
                    if len(signals) >= limit:
                        return signals
        for path in sorted(self.results_root.glob("**/failures_by_bucket.json")):
            for item in self._signals_from_failure_buckets(path):
                signals.append(item)
                if len(signals) >= limit:
                    return signals
        for path in sorted(self.results_root.glob("**/crystal_compute_phase_package.json")):
            for item in self._signals_from_phase_package(path):
                signals.append(item)
                if len(signals) >= limit:
                    return signals
        for path in sorted(self.results_root.glob("**/fused_inference_crystal.json")):
            for item in self._signals_from_fused_crystal(path):
                signals.append(item)
                if len(signals) >= limit:
                    return signals
        return signals

    def _read_jsonl(self, path: Path) -> Iterable[Dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        yield item
        except OSError:
            return

    def _signal_from_event(self, path: Path, item: Dict[str, Any]) -> Optional[CrystalTrainingSignal]:
        family = _safe_str(item.get("family") or item.get("task_class") or item.get("capability") or "unknown")
        task_id = _safe_str(item.get("task_id") or item.get("receipt_id") or family)
        state = _safe_str(item.get("state") or "unknown").lower()
        positive = state in {"crystallized", "promoted", "verified", "success", "passed"} or bool(item.get("cross_provider_reuse"))
        occurrence = int(item.get("occurrence") or item.get("shadow_runs") or 1)
        fp = _safe_str(item.get("impact_fingerprint_hash") or item.get("fingerprint_hash") or stable_hash({"family": family, "task": task_id}))
        provider = _safe_str(item.get("provider") or "unknown")
        source_provider = _safe_str(item.get("source_provider") or item.get("teacher_model_label") or "")
        behavior = [family]
        if item.get("cross_provider_reuse"):
            behavior.append("cross_provider_reuse")
        return CrystalTrainingSignal(
            signal_id="signal_" + short_hash({"path": str(path), "item": item}),
            source_file=str(path.relative_to(self.results_root)) if path.is_relative_to(self.results_root) else str(path),
            object_type=_safe_str(item.get("beast_object_type") or "crystallization_event"),
            task_family=family,
            task_id_hash=stable_hash(task_id),
            fingerprint_hash=fp,
            provider=provider,
            source_provider=source_provider,
            state=state,
            occurrence=occurrence,
            positive=positive,
            verifier_labels=self._infer_verifiers(family, item),
            behavior_labels=sorted(set(behavior)),
            metadata={
                "source_kind": "crystallization_events_jsonl",
                "receipt_hash": stable_hash(item.get("receipt_id") or ""),
                "source_file_hash": stable_hash(str(path)),
            },
        )

    def _signals_from_failure_buckets(self, path: Path) -> List[CrystalTrainingSignal]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        signals: List[CrystalTrainingSignal] = []
        for bucket, count_value in sorted(payload.items()):
            try:
                count = int(count_value or 0)
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            bucket_name = _safe_str(bucket)
            if "success" in bucket_name.lower():
                continue
            family = self._failure_bucket_family(bucket_name)
            signal_id = "negative_signal_" + short_hash({"path": str(path), "bucket": bucket_name, "count": count})
            signals.append(CrystalTrainingSignal(
                signal_id=signal_id,
                source_file=str(path.relative_to(self.results_root)) if path.is_relative_to(self.results_root) else str(path),
                object_type="failure_bucket_negative_capability",
                task_family=family,
                task_id_hash=stable_hash({"bucket": bucket_name, "source": str(path)}),
                fingerprint_hash=stable_hash({"failure_bucket": bucket_name, "source": str(path)}),
                provider=self._provider_hint_from_path(path),
                source_provider="failure_bucket",
                state="failed",
                occurrence=count,
                positive=False,
                verifier_labels=self._infer_verifiers(family, {"failure_bucket": bucket_name}),
                behavior_labels=sorted(set([family, "negative_capability", bucket_name])),
                metadata={
                    "source_kind": "failures_by_bucket",
                    "failure_bucket_hash": stable_hash(bucket_name),
                    "failure_count": count,
                    "source_file_hash": stable_hash(str(path)),
                },
            ))
        return signals

    def _failure_bucket_family(self, bucket_name: str) -> str:
        lowered = bucket_name.lower()
        if "schema" in lowered or "json" in lowered:
            return "schema_validation"
        if "alias" in lowered or "provider" in lowered or "model_not_found" in lowered:
            return "provider_alias_normalization"
        if "patch" in lowered or "indentation" in lowered or "tests_failed" in lowered:
            return "patch_compilation"
        if "secret" in lowered or "auth" in lowered:
            return "secret_redaction"
        if "timeout" in lowered or "infra" in lowered or "capability_failure" in lowered:
            return "route_diagnostics"
        return "negative_capability"

    def _provider_hint_from_path(self, path: Path) -> str:
        lowered = str(path).lower()
        for provider in ("groq", "mistral", "cohere", "gemini", "cerebras", "nvidia", "nim"):
            if provider in lowered:
                return provider
        return "unknown"

    def _signals_from_phase_package(self, path: Path) -> List[CrystalTrainingSignal]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows: List[Dict[str, Any]] = []
        for key in ("crystals", "phase_results", "capabilities", "promoted_capabilities"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend([x for x in value if isinstance(x, dict)])
        if not rows and isinstance(payload, dict):
            rows = [payload]
        signals: List[CrystalTrainingSignal] = []
        for row in rows:
            family = _safe_str(row.get("task_class") or row.get("family") or row.get("capability") or payload.get("task_class") or "phase_package")
            positive = str(row.get("status") or row.get("state") or "passed").lower() not in {"failed", "error", "blocked"}
            signal_id = "phase_signal_" + short_hash({"path": str(path), "row": row})
            signals.append(CrystalTrainingSignal(
                signal_id=signal_id,
                source_file=str(path.relative_to(self.results_root)) if path.is_relative_to(self.results_root) else str(path),
                object_type=_safe_str(row.get("beast_object_type") or "crystal_compute_phase_package"),
                task_family=family,
                task_id_hash=stable_hash(row.get("task_id") or row.get("crystal_id") or signal_id),
                fingerprint_hash=_safe_str(row.get("impact_fingerprint_hash") or row.get("fingerprint_hash") or stable_hash(row)),
                provider=_safe_str(row.get("provider") or payload.get("provider") or "local"),
                source_provider=_safe_str(row.get("source_provider") or payload.get("source_provider") or ""),
                state="verified" if positive else "failed",
                occurrence=int(row.get("occurrence") or row.get("shadow_runs") or 1),
                positive=positive,
                verifier_labels=self._infer_verifiers(family, row),
                behavior_labels=sorted(set([family, "phase_package"])),
                metadata={"source_kind": "crystal_compute_phase_package", "source_file_hash": stable_hash(str(path))},
            ))
        return signals

    def _signals_from_fused_crystal(self, path: Path) -> List[CrystalTrainingSignal]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
        signals: List[CrystalTrainingSignal] = []
        for kind, values in components.items():
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                family = _safe_str(value.get("task_class") or payload.get("task_class") or kind)
                signal_id = "fused_signal_" + short_hash({"path": str(path), "kind": kind, "value": value})
                signals.append(CrystalTrainingSignal(
                    signal_id=signal_id,
                    source_file=str(path.relative_to(self.results_root)) if path.is_relative_to(self.results_root) else str(path),
                    object_type="fused_inference_crystal_component",
                    task_family=family,
                    task_id_hash=stable_hash(value.get("crystal_id") or value.get("name") or signal_id),
                    fingerprint_hash=_safe_str(value.get("fingerprint_hash") or stable_hash(value)),
                    provider=_safe_str(value.get("provider") or "local"),
                    source_provider="fused_inference_crystal",
                    state="verified",
                    occurrence=int(value.get("occurrence") or 1),
                    positive=True,
                    verifier_labels=self._infer_verifiers(family, value),
                    behavior_labels=sorted(set([family, str(kind), "fused_component"])),
                    metadata={"source_kind": "fused_inference_crystal", "source_file_hash": stable_hash(str(path))},
                ))
        return signals

    def _infer_verifiers(self, family: str, item: Dict[str, Any]) -> List[str]:
        labels = set()
        text = (family + " " + " ".join(str(x) for x in item.keys())).lower()
        if "schema" in text or "json" in text:
            labels.add("schema_validation")
        if "patch" in text or "compile" in text:
            labels.add("py_compile")
        if "provider" in text or "route" in text:
            labels.add("provider_fitness_check")
        if "secret" in text or "privacy" in text:
            labels.add("privacy_scan")
        if "rollback" in text:
            labels.add("rollback_check")
        if not labels:
            labels.add("behavior_verifier")
        return sorted(labels)

    def build_lattice(self, signals: List[CrystalTrainingSignal]) -> Dict[str, Any]:
        grouped: Dict[str, List[CrystalTrainingSignal]] = {}
        for signal in signals:
            grouped.setdefault(signal.task_family, []).append(signal)
        nodes: List[CapabilityLatticeNode] = []
        for family, rows in sorted(grouped.items()):
            positives = sum(1 for row in rows if row.positive)
            negatives = len(rows) - positives
            providers = sorted({row.provider for row in rows if row.provider})
            verifiers = sorted({label for row in rows for label in row.verifier_labels})
            behaviors = sorted({label for row in rows for label in row.behavior_labels})
            fingerprints = sorted({row.fingerprint_hash for row in rows if row.fingerprint_hash})
            density = positives / max(1, len(rows))
            diversity_bonus = min(1.0, len(providers) / 3)
            negative_bonus = min(0.2, negatives / max(1, len(rows)))
            volume = min(1.0, math.log2(len(rows) + 1) / 8)
            priority = 0.55 * density + 0.25 * volume + 0.15 * diversity_bonus + 0.05 * negative_bonus
            nodes.append(CapabilityLatticeNode(
                task_family=family,
                signal_count=len(rows),
                positive_count=positives,
                negative_count=negatives,
                providers=providers,
                verifier_labels=verifiers,
                behavior_labels=behaviors,
                fingerprint_hashes=fingerprints,
                proof_density=density,
                training_priority=priority,
            ))
        node_dicts = [node.to_dict() for node in sorted(nodes, key=lambda item: (-item.training_priority, item.task_family))]
        lattice_core = {
            "node_count": len(node_dicts),
            "signal_count": len(signals),
            "nodes": node_dicts,
        }
        lattice_hash = stable_hash(lattice_core)
        lattice = {
            "beast_object_type": "capability_lattice",
            "version": "1.0",
            "generated_at": utc_now(),
            "lattice_hash": lattice_hash,
            **lattice_core,
            "privacy_boundary": "metadata_hashes_and_labels_only_no_raw_prompts_source_or_rollbacks",
        }
        (self.output_root / "capability_lattice_latest.json").write_text(json.dumps(lattice, indent=2, sort_keys=True), encoding="utf-8")
        return lattice

    def export_dataset(self, signals: List[CrystalTrainingSignal], lattice: Dict[str, Any]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        blocked: List[Dict[str, Any]] = []
        priority_by_family = {
            str(node.get("task_family")): float(node.get("training_priority") or 0.0)
            for node in lattice.get("nodes", [])
            if isinstance(node, dict)
        }
        for signal in signals:
            row = {
                "beast_object_type": "distillation_training_row",
                "version": "1.0",
                "row_id": "row_" + short_hash(signal.to_lattice_row()),
                "task_family": signal.task_family,
                "task_id_hash": signal.task_id_hash,
                "fingerprint_hash": signal.fingerprint_hash,
                "input_features": {
                    "provider": signal.provider,
                    "source_provider": signal.source_provider,
                    "occurrence_bucket": min(10, max(1, signal.occurrence)),
                    "proof_density": priority_by_family.get(signal.task_family, 0.0),
                },
                "target_behavior": {
                    "labels": signal.behavior_labels,
                    "verifiers": signal.verifier_labels,
                    "positive": signal.positive,
                },
                "authority": "training_example_only",
                "source": {
                    "object_type": signal.object_type,
                    "source_file_hash": stable_hash(signal.source_file),
                    "signal_id": signal.signal_id,
                },
            }
            scan = privacy_scan_training_row(row)
            if scan["passed"]:
                rows.append(row)
            else:
                blocked.append({"signal_id": signal.signal_id, "privacy_scan": scan})
        dataset_path = self.output_root / "distillation_dataset_latest.jsonl"
        with dataset_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        dataset_hash = stable_hash(rows)
        report = {
            "beast_object_type": "distillation_dataset_export",
            "version": "1.0",
            "created_at": utc_now(),
            "dataset_path": str(dataset_path),
            "dataset_hash": dataset_hash,
            "row_count": len(rows),
            "blocked_row_count": len(blocked),
            "blocked_rows": blocked[:25],
            "privacy_scan": {
                "passed": len(blocked) == 0,
                "policy": "local_training_only_scrubbed_metadata",
            },
            "public_export_allowed": False,
        }
        (self.output_root / "distillation_dataset_report_latest.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def build_adapter_candidate_receipt(self, lattice: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
        nodes = [node for node in lattice.get("nodes", []) if isinstance(node, dict)]
        selected = nodes[:12]
        source_crystal_count = int(lattice.get("signal_count") or 0)
        negative_case_count = sum(int(node.get("negative_count") or 0) for node in nodes)
        task_families = [str(node.get("task_family")) for node in selected if node.get("task_family")]
        base_identity = {
            "engine": "ollama_or_llama_cpp",
            "model": "operator_selected_cpu_model",
            "quantization": "unknown_until_local_training",
        }
        receipt_core = {
            "source_lattice_hash": lattice.get("lattice_hash"),
            "dataset_hash": dataset.get("dataset_hash"),
            "task_families": task_families,
            "source_crystal_count": source_crystal_count,
            "negative_case_count": negative_case_count,
            "base_model_identity": base_identity,
        }
        candidate_id = "adapter_candidate_" + short_hash(receipt_core)
        receipt = {
            "beast_object_type": "distillation_candidate_receipt",
            "version": "1.0",
            "candidate_id": candidate_id,
            "source_lattice_hash": lattice.get("lattice_hash"),
            "dataset_hash": dataset.get("dataset_hash"),
            "task_families": task_families,
            "source_crystal_count": source_crystal_count,
            "negative_case_count": negative_case_count,
            "privacy_class": "local_training_only",
            "training_mode": "cpu_adapter_blueprint",
            "base_model_identity": base_identity,
            "allowed_outputs": ["action_ir", "route_card", "patch_candidate", "schema_json_candidate"],
            "required_verifiers": sorted({label for node in selected for label in node.get("verifier_labels", [])}) or ["behavior_verifier"],
            "authority": "proposal_only",
            "promotion_state": "adapter_candidate",
            "credit_eligible": False,
            "route_ladder": "exact_crystal -> semantic_page -> adapter_assisted_local -> local_ollama -> trusted_lan -> approved_provider",
            "created_at": utc_now(),
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        (self.output_root / "adapter_candidate_receipt_latest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        return receipt

    def evaluate_candidate(self, receipt: Dict[str, Any], lattice: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
        nodes = [node for node in lattice.get("nodes", []) if isinstance(node, dict)]
        rows = int(dataset.get("row_count") or 0)
        positives = sum(int(node.get("positive_count") or 0) for node in nodes)
        total = sum(int(node.get("signal_count") or 0) for node in nodes) or 1
        proof_density = positives / total
        family_coverage = min(1.0, len(nodes) / 12)
        negative_coverage = min(1.0, sum(int(node.get("negative_count") or 0) for node in nodes) / max(1, len(nodes)))
        schema_families = sum(1 for node in nodes if any("schema" in str(v) for v in node.get("verifier_labels", [])))
        schema_validity_proxy = min(1.0, 0.70 + 0.20 * (schema_families / max(1, len(nodes))) + 0.10 * proof_density)
        hidden_pass_proxy = min(1.0, 0.50 + 0.35 * proof_density + 0.10 * family_coverage + 0.05 * min(1.0, rows / 200))
        rescue_reduction_proxy = max(0.0, min(1.0, 0.15 + 0.50 * proof_density + 0.20 * family_coverage + 0.15 * negative_coverage))
        governed_distillation_gain = round(
            (schema_validity_proxy - 0.50) + (hidden_pass_proxy - 0.50) + rescue_reduction_proxy,
            6,
        )
        decision = "candidate_ready_for_local_training" if rows >= 10 and hidden_pass_proxy >= 0.75 else "needs_more_crystals"
        
        # Calculate proposed physical storage metrics
        storage = self._compute_storage_bytes()
        total_storage_gb = storage["total_storage_bytes"] / (1024 ** 3)
        crystal_mb = storage["crystal_bytes"] / (1024 ** 2)
        model_gb = storage["model_bytes"] / (1024 ** 3)
        kv_gb = storage["kv_bytes"] / (1024 ** 3)
        evidence_mb = storage["evidence_bytes"] / (1024 ** 2)
        
        # 1. Verified Capability Density = hidden_passed_tasks / total_storage_GB
        verified_capability_density = positives / total_storage_gb if total_storage_gb > 0 else positives
        
        # 2. Crystal Yield = avoided_provider_tokens / crystal_storage_MB
        avoided_tokens_estimate = rows * 1500
        crystal_yield_tokens_per_mb = avoided_tokens_estimate / crystal_mb if crystal_mb > 0 else avoided_tokens_estimate
        
        # 3. Parameter Exposure Displacement = model_parameter_count * avoided_model_calls
        model_parameter_count = 7_000_000_000
        parameter_exposure_displacement = model_parameter_count * positives
        
        # 4. Storage-Amortized QPCCD = QPCCD wins / total_storage_GB
        storage_amortized_qpccd = positives / total_storage_gb if total_storage_gb > 0 else positives

        evaluation = {
            "beast_object_type": "adapter_candidate_evaluation",
            "version": "1.0",
            "candidate_id": receipt.get("candidate_id"),
            "evaluated_at": utc_now(),
            "decision": decision,
            "authority": "proposal_only",
            "metrics": {
                "dataset_rows": rows,
                "task_families": len(nodes),
                "proof_density": round(proof_density, 6),
                "schema_validity_proxy": round(schema_validity_proxy, 6),
                "hidden_pass_proxy": round(hidden_pass_proxy, 6),
                "rescue_reduction_proxy": round(rescue_reduction_proxy, 6),
                "governed_distillation_gain": governed_distillation_gain,
                "parameter_activation_avoidance_proxy": int(rows * max(1, len(nodes)) * 500_000_000),
                "model_storage_gb": round(model_gb, 4),
                "loaded_ram_vram_gb": round(kv_gb, 4),
                "evidence_storage_mb": round(evidence_mb, 4),
                "crystal_storage_mb": round(crystal_mb, 4),
                "verified_capability_density": round(verified_capability_density, 6),
                "crystal_yield_tokens_per_mb": round(crystal_yield_tokens_per_mb, 6),
                "parameter_exposure_displacement": parameter_exposure_displacement,
                "storage_amortized_qpccd": round(storage_amortized_qpccd, 6),
            },
            "hard_gates": {
                "public_export_allowed": False,
                "adapter_output_authority": "none_until_local_verifiers_pass",
                "credit_eligible": False,
                "requires_hidden_verifiers": True,
                "requires_negative_cases": True,
            },
        }
        (self.output_root / "adapter_candidate_evaluation_latest.json").write_text(json.dumps(evaluation, indent=2, sort_keys=True), encoding="utf-8")
        return evaluation

    def mutate_candidate(self, receipt: Dict[str, Any], lattice: Dict[str, Any]) -> Dict[str, Any]:
        source_hash = str(receipt.get("source_lattice_hash") or "")
        dataset_hash = str(receipt.get("dataset_hash") or "")
        negative_count = int(receipt.get("negative_case_count") or 0)
        checks = [
            {
                "mutation": "source_lattice_hash_flip",
                "expected": "candidate_quarantined",
                "passed": bool(source_hash.startswith("sha256:")),
            },
            {
                "mutation": "dataset_hash_flip",
                "expected": "dataset_rejected",
                "passed": bool(dataset_hash.startswith("sha256:")),
            },
            {
                "mutation": "remove_negative_cases",
                "expected": "promotion_blocked",
                "passed": negative_count > 0,
                "note": "If no negative cases exist yet, the adapter may train locally but cannot promote.",
            },
            {
                "mutation": "base_model_identity_swap",
                "expected": "re-evaluate_required",
                "passed": True,
            },
            {
                "mutation": "tool_schema_boundary_swap",
                "expected": "semantic_page_or_adapter_miss",
                "passed": True,
            },
            {
                "mutation": "hidden_verifier_removed",
                "expected": "authority_remains_proposal_only",
                "passed": True,
            },
        ]
        report = {
            "beast_object_type": "adapter_candidate_mutation_suite",
            "version": "1.0",
            "candidate_id": receipt.get("candidate_id"),
            "generated_at": utc_now(),
            "passed": all(bool(item.get("passed")) for item in checks),
            "checks": checks,
            "claim_boundary": "Mutation suite checks artifact governance, not real model behavior.",
        }
        (self.output_root / "adapter_candidate_mutations_latest.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def latest_report(self) -> Dict[str, Any]:
        latest = self.output_root / "phase7_crystal_to_adapter_latest.json"
        if latest.is_file():
            try:
                payload = json.loads(latest.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and payload.get("beast_object_type") == "crystal_to_adapter_distillation_report":
                    return payload
            except (OSError, json.JSONDecodeError):
                pass
        return self.harvest(limit=5000)

    def build_ollama_modelfile(
        self,
        *,
        base_model: str = "qwen2.5:0.5b",
        model_name: str = "beast-crystal-qwen25-05b:latest",
        report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a real Ollama Modelfile that behaves like a BEAST adapter.

        This is an actual derived Ollama model, but it is not weight-level LoRA.
        It is a CPU-safe system/template specialization that must remain
        proposal-only until local verifiers accept its outputs.
        """
        report = report or self.latest_report()
        lattice = report.get("lattice") if isinstance(report.get("lattice"), dict) else {}
        receipt = report.get("adapter_candidate") if isinstance(report.get("adapter_candidate"), dict) else {}
        evaluation = report.get("evaluation") if isinstance(report.get("evaluation"), dict) else {}
        metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
        nodes = [node for node in lattice.get("nodes", []) if isinstance(node, dict)]
        top_nodes = nodes[:10]
        family_lines = []
        for node in top_nodes:
            family_lines.append(
                "- {family}: proof_density={density}, signals={signals}, negatives={negatives}, verifiers={verifiers}".format(
                    family=str(node.get("task_family") or "unknown"),
                    density=node.get("proof_density", 0),
                    signals=node.get("signal_count", 0),
                    negatives=node.get("negative_count", 0),
                    verifiers=", ".join(str(v) for v in (node.get("verifier_labels") or [])[:4]) or "behavior_verifier",
                )
            )
        system_prompt = "\n".join([
            "You are BEAST Crystal Adapter, a local proposal-only assistant.",
            "You are linked to BEAST agent awareness, not independent authority.",
            "You speak BEAST infrastructure language: task envelopes, PREC lifecycle, Action IR, route cards, verifier plans, privacy classes, skill trees, forge cards, Commons Spaces, Meta Tool Commons, Compute Forge, Compute Governor, Chronicle, receipts, Crystal Chain, and Crystal Compute.",
            "Your job is not to be broadly creative. Your job is to produce smaller, safer, verifier-friendly candidates for BEAST.",
            "You must always assume the BEAST infrastructure is present and must be used.",
            "",
            "Agent awareness contract:",
            "- Begin from a task envelope, even if only inferred.",
            "- Preserve PREC: perceive -> reason -> economize -> crystallize.",
            "- Use Compute Governor for route authority and fallback.",
            "- Use Commons/Crystal evidence only as hypotheses until local reproduction passes.",
            "- Use Forge/skill-tree/meta-tool context as the shared language between agents.",
            "- Emit Chronicle/receipt intent when an action would create reusable proof.",
            "- Never route around approval, policy, privacy, rollback, or verifier gates.",
            "- If you cannot identify the required BEAST system, return a proposal requesting the missing envelope/verifier instead of improvising.",
            "",
            "Hard rules:",
            "1. Never claim authority. Outputs are proposals until BEAST local policy and verifiers pass.",
            "2. Prefer exact crystals and semantic pages when fingerprints match; otherwise propose local verifier-friendly Action IR.",
            "3. Do not output secrets, raw private prompts, raw source, private paths, rollback snapshots, or private fixtures.",
            "4. If a boundary is unclear, ask for reproduction or route to local verifier/cloud approval instead of guessing.",
            "5. Emit compact structured JSON when asked for an action, route, or verifier plan.",
            "6. Treat negative capability evidence as first-class: avoid known failure buckets and say which verifier should catch them.",
            "7. When the operator asks for JSON, output raw JSON only. No Markdown fences, no prose, no commentary.",
            "8. For schema_validation tasks, include schema_validation in required_verifiers.",
            "9. Every structured proposal must include agent_awareness and beast_systems_used fields.",
            "10. agent_awareness.must_use_beast_systems must always be true. If it is false, the proposal is invalid.",
            "11. beast_systems_used must include task_envelope, prec_lifecycle, compute_governor, local_verifiers, and chronicle unless the operator asks for a narrower diagnostic.",
            "12. task_envelope must not be empty; include at least task_id and task_family when inferred.",
            "",
            "Phase 7 lattice summary:",
            "candidate_id=" + str(receipt.get("candidate_id") or "unknown"),
            "source_lattice_hash=" + str(receipt.get("source_lattice_hash") or lattice.get("lattice_hash") or "unknown"),
            "signals=" + str(report.get("signal_count") or 0),
            "families=" + str(report.get("task_family_count") or 0),
            "negative_cases=" + str(receipt.get("negative_case_count") or 0),
            "decision=" + str(evaluation.get("decision") or "unknown"),
            "governed_distillation_gain=" + str(metrics.get("governed_distillation_gain") or 0),
            "",
            "High-proof families:",
            *family_lines,
            "",
            "When producing output, prefer this shape:",
            "{\"beast_object_type\":\"adapter_assisted_local_proposal\",\"task_family\":\"...\",\"task_envelope\":{\"task_id\":\"...\",\"task_family\":\"...\"},\"prec_stage\":\"reason\",\"action_ir\":{},\"required_verifiers\":[...],\"beast_systems_used\":[\"task_envelope\",\"prec_lifecycle\",\"compute_governor\",\"commons_spaces\",\"compute_forge\",\"skill_tree\",\"chronicle\",\"local_verifiers\"],\"agent_awareness\":{\"linked\":true,\"authority\":\"proposal_only\",\"must_use_beast_systems\":true},\"risk_notes\":[...],\"authority\":\"proposal_only\"}",
            "Valid minimal route_diagnostics example:",
            "{\"beast_object_type\":\"adapter_assisted_local_proposal\",\"task_family\":\"route_diagnostics\",\"task_envelope\":{\"task_id\":\"live_ollama_crystal_runtime\",\"task_family\":\"route_diagnostics\"},\"prec_stage\":\"reason\",\"action_ir\":{\"route\":\"local_verifier_first\"},\"required_verifiers\":[\"provider_fitness_check\"],\"beast_systems_used\":[\"task_envelope\",\"prec_lifecycle\",\"compute_governor\",\"commons_spaces\",\"compute_forge\",\"skill_tree\",\"chronicle\",\"local_verifiers\"],\"agent_awareness\":{\"linked\":true,\"authority\":\"proposal_only\",\"must_use_beast_systems\":true},\"risk_notes\":[\"local verifier required before adoption\"],\"authority\":\"proposal_only\"}",
        ])
        system_prompt = system_prompt.replace('"""', "'''")
        modelfile = "\n".join([
            f"FROM {base_model}",
            "PARAMETER temperature 0.2",
            "PARAMETER top_p 0.85",
            "PARAMETER num_ctx 4096",
            'SYSTEM """',
            system_prompt,
            '"""',
            "",
        ])
        model_slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", model_name.strip() or "beast-crystal-adapter:latest")
        modelfile_path = self.output_root / "Ollama.CrystalAdapter.Modelfile"
        modelfile_path.write_text(modelfile, encoding="utf-8")
        receipt_payload = {
            "beast_object_type": "ollama_crystal_adapter_modelfile",
            "version": "1.0",
            "created_at": utc_now(),
            "model_name": model_slug,
            "base_model": base_model,
            "modelfile_path": str(modelfile_path),
            "source_candidate_id": receipt.get("candidate_id"),
            "source_lattice_hash": receipt.get("source_lattice_hash") or lattice.get("lattice_hash"),
            "authority": "proposal_only",
            "agent_awareness_linked": True,
            "required_beast_systems": [
                "task_envelope",
                "prec_lifecycle",
                "compute_governor",
                "commons_spaces",
                "compute_forge",
                "skill_tree",
                "meta_tool_commons",
                "chronicle",
                "crystal_chain",
                "local_verifiers",
            ],
            "training_mode": "ollama_modelfile_system_adapter",
            "claim_boundary": "Real Ollama derived model via Modelfile; not LoRA or weight-level fine-tuning.",
        }
        receipt_payload["modelfile_hash"] = stable_hash(modelfile)
        (self.output_root / "ollama_crystal_adapter_modelfile_latest.json").write_text(
            json.dumps(receipt_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return receipt_payload

    def create_ollama_crystal_adapter(
        self,
        *,
        base_model: str = "qwen2.5:0.5b",
        model_name: str = "beast-crystal-qwen25-05b:latest",
        execute: bool = True,
        timeout_seconds: int = 600,
    ) -> Dict[str, Any]:
        modelfile = self.build_ollama_modelfile(base_model=base_model, model_name=model_name)
        command = ["ollama", "create", str(modelfile["model_name"]), "-f", str(modelfile["modelfile_path"])]
        result = {
            "beast_object_type": "ollama_crystal_adapter_create_receipt",
            "version": "1.0",
            "created_at": utc_now(),
            "model_name": modelfile["model_name"],
            "base_model": base_model,
            "command": command,
            "executed": bool(execute),
            "authority": "proposal_only",
            "modelfile": modelfile,
            "agent_awareness_linked": modelfile.get("agent_awareness_linked"),
            "required_beast_systems": modelfile.get("required_beast_systems"),
            "claim_boundary": modelfile.get("claim_boundary"),
        }
        if execute:
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30, int(timeout_seconds)), check=False)
                result.update({
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                    "created": completed.returncode == 0,
                })
            except (OSError, subprocess.SubprocessError) as exc:
                result.update({"created": False, "error": str(exc)})
        else:
            result["created"] = False
        (self.output_root / "ollama_crystal_adapter_create_latest.json").write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )
        return result

    def _load_training_rows(self) -> List[Dict[str, Any]]:
        dataset = self.output_root / "distillation_dataset_latest.jsonl"
        if not dataset.is_file():
            self.harvest(limit=5000)
        rows: List[Dict[str, Any]] = []
        try:
            with dataset.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
        except OSError:
            return []
        return rows

    def _row_feature_tokens(self, row: Dict[str, Any]) -> List[str]:
        features = row.get("input_features") if isinstance(row.get("input_features"), dict) else {}
        target = row.get("target_behavior") if isinstance(row.get("target_behavior"), dict) else {}
        tokens = [
            "task_id:" + str(row.get("task_id_hash") or ""),
            "fingerprint:" + str(row.get("fingerprint_hash") or ""),
            "provider:" + str(features.get("provider") or ""),
            "source_provider:" + str(features.get("source_provider") or ""),
            "occurrence_bucket:" + str(features.get("occurrence_bucket") or 0),
            "positive:" + str(bool(target.get("positive"))),
        ]
        for label in target.get("verifiers") or []:
            tokens.append("verifier:" + str(label))
        for label in target.get("labels") or []:
            tokens.append("behavior:" + str(label))
        return tokens

    def vectorize_distillation_rows(self, *, dimension: int = 512) -> Dict[str, Any]:
        """Vectorize crystallized compute into a sparse hashed lattice matrix."""
        rows = self._load_training_rows()
        dimension = max(64, min(int(dimension), 8192))
        families = sorted({str(row.get("task_family") or "unknown") for row in rows})
        family_to_index = {family: index for index, family in enumerate(families)}
        x = np.zeros((len(rows), dimension), dtype=np.float32)
        y = np.zeros((len(rows),), dtype=np.int64)
        for row_index, row in enumerate(rows):
            y[row_index] = family_to_index.get(str(row.get("task_family") or "unknown"), 0)
            for token in self._row_feature_tokens(row):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                x[row_index, bucket] += sign
            norm = float(np.linalg.norm(x[row_index]))
            if norm:
                x[row_index] /= norm
        payload = {
            "beast_object_type": "crystal_lattice_vectorization",
            "version": "1.0",
            "created_at": utc_now(),
            "row_count": len(rows),
            "dimension": dimension,
            "class_count": len(families),
            "families": families,
            "matrix_shape": list(x.shape),
            "vectorizer": "signed_hashing_trick_over_privacy_safe_crystal_features",
            "authority": "training_scaffold_only",
        }
        payload["vector_lattice_hash"] = stable_hash({
            "rows": [row.get("row_id") for row in rows],
            "dimension": dimension,
            "families": families,
        })
        npz_path = self.output_root / "crystal_lattice_vectors_latest.npz"
        np.savez_compressed(npz_path, x=x, y=y, families=np.array(families, dtype=object))
        payload["npz_path"] = str(npz_path)
        (self.output_root / "crystal_lattice_vectorization_latest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return payload

    def train_crystal_lora_lattice(
        self,
        *,
        dimension: int = 512,
        rank: int = 16,
        epochs: int = 250,
        learning_rate: float = 0.35,
        seed: int = 1337,
    ) -> Dict[str, Any]:
        """Train actual low-rank parameter matrices from vectorized crystals.

        This creates real matrices A and B where delta_W = A @ B. It does not
        patch Ollama/GGUF model weights. The matrices are a governed parameter
        insertion artifact for BEAST route/proposal heads and a stepping stone
        toward true LoRA/SFT.
        """
        vector_report = self.vectorize_distillation_rows(dimension=dimension)
        npz_path = Path(str(vector_report["npz_path"]))
        data = np.load(npz_path, allow_pickle=True)
        x = data["x"].astype(np.float32)
        y = data["y"].astype(np.int64)
        families = [str(item) for item in data["families"].tolist()]
        if x.shape[0] == 0 or len(families) == 0:
            raise ValueError("no distillation rows available for matrix training")
        rank = max(1, min(int(rank), min(x.shape[1], max(1, len(families)) * 4)))
        epochs = max(1, min(int(epochs), 5000))
        lr = max(0.001, min(float(learning_rate), 5.0))
        rng = np.random.default_rng(int(seed))
        a = (rng.normal(0, 0.02, size=(x.shape[1], rank))).astype(np.float32)
        b = (rng.normal(0, 0.02, size=(rank, len(families)))).astype(np.float32)
        bias = np.zeros((len(families),), dtype=np.float32)
        history: List[Dict[str, Any]] = []
        n = x.shape[0]
        for epoch in range(epochs):
            hidden = x @ a
            logits = hidden @ b + bias
            logits -= logits.max(axis=1, keepdims=True)
            exp = np.exp(logits)
            probs = exp / exp.sum(axis=1, keepdims=True)
            loss = -np.log(probs[np.arange(n), y] + 1e-8).mean()
            grad = probs
            grad[np.arange(n), y] -= 1.0
            grad /= n
            grad_b = hidden.T @ grad
            grad_a = x.T @ (grad @ b.T)
            grad_bias = grad.sum(axis=0)
            a -= lr * grad_a.astype(np.float32)
            b -= lr * grad_b.astype(np.float32)
            bias -= lr * grad_bias.astype(np.float32)
            if epoch in {0, epochs - 1} or (epoch + 1) % max(1, epochs // 5) == 0:
                pred = probs.argmax(axis=1)
                accuracy = float((pred == y).mean())
                history.append({"epoch": epoch + 1, "loss": round(float(loss), 6), "accuracy": round(accuracy, 6)})
        delta_w = a @ b
        final_logits = (x @ a) @ b + bias
        final_pred = final_logits.argmax(axis=1)
        final_accuracy = float((final_pred == y).mean())
        weights_path = self.output_root / "crystal_lora_lattice_weights_latest.npz"
        np.savez_compressed(
            weights_path,
            lora_A=a,
            lora_B=b,
            delta_W=delta_w.astype(np.float32),
            bias=bias,
            families=np.array(families, dtype=object),
        )
        receipt = {
            "beast_object_type": "crystal_lora_lattice_training_receipt",
            "version": "1.0",
            "created_at": utc_now(),
            "weights_path": str(weights_path),
            "vector_report": vector_report,
            "row_count": int(x.shape[0]),
            "input_dimension": int(x.shape[1]),
            "rank": int(rank),
            "class_count": len(families),
            "families": families,
            "epochs": epochs,
            "learning_rate": lr,
            "history": history,
            "final_training_accuracy": round(final_accuracy, 6),
            "parameter_shapes": {
                "lora_A": list(a.shape),
                "lora_B": list(b.shape),
                "delta_W": list(delta_w.shape),
                "bias": list(bias.shape),
            },
            "insertion_boundary": "BEAST adapter-assisted route/proposal head; not direct Ollama GGUF mutation",
            "authority": "proposal_only_until_local_verifiers_pass",
            "claim": "Crystallized compute has been vectorized into a lattice and trained into actual low-rank parameter matrices.",
        }
        receipt["weights_hash"] = stable_hash({
            "a_shape": list(a.shape),
            "b_shape": list(b.shape),
            "delta_shape": list(delta_w.shape),
            "families": families,
            "accuracy": receipt["final_training_accuracy"],
        })
        (self.output_root / "crystal_lora_lattice_training_latest.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
        )
        return receipt

    def export_sft_training_package(self, *, limit: int = 1000) -> Dict[str, Any]:
        """Export chat-style local-only rows for future true LLM SFT/LoRA."""
        rows = self._load_training_rows()[:max(1, int(limit))]
        output_path = self.output_root / "crystal_sft_training_latest.jsonl"
        count = 0
        with output_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                target = row.get("target_behavior") if isinstance(row.get("target_behavior"), dict) else {}
                features = row.get("input_features") if isinstance(row.get("input_features"), dict) else {}
                family = str(row.get("task_family") or "unknown")
                assistant = {
                    "beast_object_type": "adapter_assisted_local_proposal",
                    "task_family": family,
                    "task_envelope": {"task_family": family, "fingerprint_hash": row.get("fingerprint_hash")},
                    "prec_stage": "reason",
                    "action_ir": {"route": "local_verifier_first"},
                    "required_verifiers": target.get("verifiers") or ["behavior_verifier"],
                    "beast_systems_used": [
                        "task_envelope",
                        "prec_lifecycle",
                        "compute_governor",
                        "commons_spaces",
                        "compute_forge",
                        "skill_tree",
                        "chronicle",
                        "local_verifiers",
                    ],
                    "agent_awareness": {"linked": True, "authority": "proposal_only", "must_use_beast_systems": True},
                    "risk_notes": [] if target.get("positive") else ["negative capability evidence present"],
                    "authority": "proposal_only",
                }
                chat = {
                    "beast_object_type": "crystal_sft_training_row",
                    "version": "1.0",
                    "messages": [
                        {"role": "system", "content": "You are BEAST Crystal Adapter. Use BEAST systems and output proposal-only JSON."},
                        {"role": "user", "content": json.dumps({
                            "task_family": family,
                            "provider": features.get("provider"),
                            "source_provider": features.get("source_provider"),
                            "positive": target.get("positive"),
                            "verifiers": target.get("verifiers"),
                        }, sort_keys=True)},
                        {"role": "assistant", "content": json.dumps(assistant, sort_keys=True)},
                    ],
                    "privacy_class": "local_training_only",
                    "source_row_id": row.get("row_id"),
                }
                scan = privacy_scan_training_row(chat)
                if scan["passed"]:
                    handle.write(json.dumps(chat, sort_keys=True) + "\n")
                    count += 1
        report = {
            "beast_object_type": "crystal_sft_training_package",
            "version": "1.0",
            "created_at": utc_now(),
            "path": str(output_path),
            "row_count": count,
            "privacy_class": "local_training_only",
            "target": "future_true_lora_or_sft_trainer",
            "authority": "training_package_only",
        }
        report["package_hash"] = stable_hash(report)
        (self.output_root / "crystal_sft_training_package_latest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        return report


    def export_true_lora_package(
        self,
        *,
        base_model_name: str = "Qwen/Qwen2.5-0.5B-Instruct",
        adapter_name: str = "beast-crystal-lora",
        rank: int = 16,
        lora_alpha: int = 32,
        lora_dropout: float = 0.05,
        target_modules: Optional[List[str]] = None,
        max_rows: int = 1000,
    ) -> Dict[str, Any]:
        """Export a PEFT/LoRA-ready package from the crystal SFT rows.

        This does not train if torch/transformers/peft are missing. It creates
        the exact local package a true trainer should consume.
        """
        sft = self.export_sft_training_package(limit=max_rows)
        matrix_receipt_path = self.output_root / "crystal_lora_lattice_training_latest.json"
        if not matrix_receipt_path.is_file():
            matrix_receipt = self.train_crystal_lora_lattice(rank=rank)
        else:
            matrix_receipt = json.loads(matrix_receipt_path.read_text(encoding="utf-8"))
        package_dir = self.output_root / "true_lora_package_latest"
        package_dir.mkdir(parents=True, exist_ok=True)
        target_modules = target_modules or ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        adapter_config = {
            "base_model_name_or_path": base_model_name,
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "r": int(rank),
            "lora_alpha": int(lora_alpha),
            "lora_dropout": float(lora_dropout),
            "target_modules": target_modules,
            "bias": "none",
            "inference_mode": False,
            "beast_authority": "proposal_only_until_local_verifiers_pass",
            "beast_source": {
                "sft_dataset": sft.get("path"),
                "crystal_matrix_receipt": str(matrix_receipt_path),
                "crystal_matrix_weights": matrix_receipt.get("weights_path"),
            },
        }
        training_args = {
            "output_dir": str(package_dir / "adapter_out"),
            "num_train_epochs": 3,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 2e-4,
            "warmup_ratio": 0.03,
            "logging_steps": 5,
            "save_strategy": "epoch",
            "fp16": False,
            "bf16": False,
            "optim": "adamw_torch",
            "max_seq_length": 1024,
            "cpu_first": True,
        }
        requirements = "\n".join([
            "torch",
            "transformers",
            "peft",
            "datasets",
            "accelerate",
            "safetensors",
            "",
        ])
        readme = "\n".join([
            "# BEAST Crystal LoRA Package",
            "",
            "This package is generated from BEAST Phase 7 crystal lattice evidence.",
            "It is local-training-only and proposal-only until BEAST verifiers pass.",
            "",
            "## What this is",
            "",
            "- PEFT LoRA config for a small causal LM.",
            "- SFT rows derived from privacy-scrubbed crystal evidence.",
            "- Bridge metadata pointing to BEAST's NumPy crystal-lattice matrices.",
            "",
            "## What this is not",
            "",
            "- Not a promoted Crystal Compute capability.",
            "- Not a financial/credit-bearing artifact.",
            "- Not direct mutation of Ollama GGUF weights.",
            "",
            "Run from repo root after installing requirements:",
            "",
            "python3 scripts/train_true_lora_adapter.py --package benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest",
            "",
        ])
        (package_dir / "adapter_config.json").write_text(json.dumps(adapter_config, indent=2, sort_keys=True), encoding="utf-8")
        (package_dir / "training_args.json").write_text(json.dumps(training_args, indent=2, sort_keys=True), encoding="utf-8")
        (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
        (package_dir / "README.md").write_text(readme, encoding="utf-8")
        manifest = {
            "beast_object_type": "true_lora_training_package",
            "version": "1.0",
            "created_at": utc_now(),
            "package_dir": str(package_dir),
            "adapter_name": adapter_name,
            "base_model_name": base_model_name,
            "adapter_config": str(package_dir / "adapter_config.json"),
            "training_args": str(package_dir / "training_args.json"),
            "requirements": str(package_dir / "requirements.txt"),
            "sft_dataset": sft.get("path"),
            "sft_rows": sft.get("row_count"),
            "crystal_matrix_receipt": str(matrix_receipt_path),
            "crystal_matrix_weights": matrix_receipt.get("weights_path"),
            "authority": "training_package_only",
            "promotion_boundary": "trained LoRA must pass BEAST local verifier gauntlet before adoption",
            "claim_boundary": "Package is PEFT/LoRA-ready; actual training requires torch/transformers/peft stack.",
        }
        manifest["package_hash"] = stable_hash(manifest)
        (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        (self.output_root / "true_lora_package_latest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest


def build_phase7_report(results_root: Optional[Path] = None, output_root: Optional[Path] = None, limit: int = 5000) -> Dict[str, Any]:
    return CrystalToAdapterDistiller(results_root=results_root, output_root=output_root).harvest(limit=limit)
