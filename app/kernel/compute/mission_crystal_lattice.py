"""Proof-carrying mission lattice for SourcePlan edit evidence.

The lattice is intentionally advisory. It records verified edit situations as
hash-only mission cells and can later tell BEAST whether a new SourcePlan looks
like a previously verified mission. It never applies edits by itself.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bucket(value: int, buckets: Iterable[int] = (0, 1, 3, 5, 10, 25, 50)) -> str:
    value = max(0, int(value or 0))
    previous = 0
    for limit in buckets:
        if value <= limit:
            return f"{previous}-{limit}" if previous != limit else str(limit)
        previous = limit + 1
    return f"{previous}+"


def _objective_terms(text: str) -> List[str]:
    words = []
    for raw in str(text or "").lower().replace("_", " ").replace("-", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if len(token) >= 4 and token not in {"sourceplan", "update", "change", "repair"}:
            words.append(token)
    return sorted(dict.fromkeys(words))[:12]


class MissionCrystalLattice:
    """Store and query verified mission edit cells."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "compute" / "mission_lattice"
        self.cells_path = self.store_dir / "cells.json"

    def fingerprint_sourceplan(self, plan: Dict[str, Any], scorecard: Dict[str, Any] | None = None) -> Dict[str, Any]:
        scorecard = scorecard if isinstance(scorecard, dict) else {}
        graph = scorecard.get("graph_impact") if isinstance(scorecard.get("graph_impact"), dict) else {}
        mode_route = scorecard.get("mode_route") if isinstance(scorecard.get("mode_route"), dict) else {}
        spec = scorecard.get("spec_covenant") if isinstance(scorecard.get("spec_covenant"), dict) else {}
        safety = scorecard.get("safety_governor") if isinstance(scorecard.get("safety_governor"), dict) else {}
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        selected_ids = set(str(item) for item in (plan.get("selected_operations") or []))
        selected_ops = [
            op for index, op in enumerate(operations)
            if isinstance(op, dict)
            and (not selected_ids or str(op.get("op_id") or op.get("id") or f"op_{index+1:03d}") in selected_ids)
            and op.get("selected", True) is not False
        ]
        paths = [
            str(op.get("path") or "")
            for op in selected_ops
            if str(op.get("path") or "") and "::" not in str(op.get("path") or "")
        ]
        extensions = sorted(dict.fromkeys(Path(path).suffix.lower() or "<none>" for path in paths))
        op_types = sorted(dict.fromkeys(str(op.get("op") or op.get("action") or "unknown") for op in selected_ops))
        action_ir_types = sorted(dict.fromkeys(str(op.get("action_ir_type") or "") for op in selected_ops if op.get("action_ir_type")))
        touched_symbols = graph.get("touched_symbols") if isinstance(graph.get("touched_symbols"), list) else []
        code_cortex = graph.get("code_cortex") if isinstance(graph.get("code_cortex"), dict) else {}
        fingerprint = {
            "beast_object_type": "mission_crystal_fingerprint",
            "version": "1.0",
            "task_family": "sourceplan_edit",
            "objective_terms": _objective_terms(str(plan.get("objective") or "")),
            "risk_level": str(scorecard.get("risk_level") or plan.get("risk_level") or "unknown"),
            "decision": str(scorecard.get("decision") or ""),
            "mode": str(mode_route.get("selected_mode") or ""),
            "spec_covenant_hash": str(spec.get("covenant_hash") or ""),
            "safety_decision": str(safety.get("decision") or ""),
            "operation_shape": {
                "operation_types": op_types,
                "action_ir_types": action_ir_types,
                "file_count_bucket": _bucket(len(paths), (0, 1, 2, 3, 5, 10)),
                "extensions": extensions,
            },
            "graph_shape": {
                "dependent_count_bucket": _bucket(int(graph.get("dependent_count") or 0)),
                "route_count_bucket": _bucket(int(graph.get("route_count") or 0)),
                "touched_symbol_bucket": _bucket(len(touched_symbols)),
                "code_cortex_adapter": str(code_cortex.get("active_adapter") or ""),
                "code_cortex_dependent_bucket": _bucket(int(code_cortex.get("dependent_count") or 0)),
            },
            "verification_shape": {
                "suggested_test_count_bucket": _bucket(len(scorecard.get("suggested_tests") or []), (0, 1, 2, 4, 8)),
                "policy_verification_required": bool(((scorecard.get("policy_gates") or {}) if isinstance(scorecard.get("policy_gates"), dict) else {}).get("verification_required", True)),
            },
        }
        fingerprint["fingerprint_hash"] = _stable_hash(fingerprint)
        return fingerprint

    def lookup(self, plan: Dict[str, Any], scorecard: Dict[str, Any] | None = None, limit: int = 5) -> Dict[str, Any]:
        fingerprint = self.fingerprint_sourceplan(plan, scorecard)
        cells = self._load_cells()
        scored = []
        blockers: List[str] = []
        for cell in cells:
            cell_fp = cell.get("fingerprint") if isinstance(cell.get("fingerprint"), dict) else {}
            score, reasons, cell_blockers = self._score(fingerprint, cell_fp)
            if score > 0:
                row = {
                    "cell_id": cell.get("cell_id"),
                    "score": round(score, 4),
                    "match_reasons": reasons,
                    "blockers": cell_blockers,
                    "plan_id": cell.get("plan_id"),
                    "evidence_hash": cell.get("evidence_hash"),
                    "verification_ok": bool(cell.get("verification_ok")),
                    "promotion_candidate": bool(cell.get("promotion_candidate")),
                    "created_at": cell.get("created_at"),
                }
                scored.append(row)
                blockers.extend(cell_blockers)
        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        best = scored[0] if scored else {}
        best_score = float(best.get("score") or 0.0)
        if best_score >= 0.88 and not best.get("blockers"):
            reuse_mode = "sourceplan_replay_candidate"
        elif best_score >= 0.55:
            reuse_mode = "strategy_scaffold"
        elif scored:
            reuse_mode = "context_hint_only"
        else:
            reuse_mode = "no_match"
        return {
            "beast_object_type": "mission_crystal_lattice_lookup",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "fingerprint": fingerprint,
            "cell_count": len(cells),
            "match_strength": round(best_score, 4),
            "reuse_mode": reuse_mode,
            "best_match": best,
            "matches": scored[: max(1, int(limit or 1))],
            "blockers": sorted(dict.fromkeys(blockers)),
            "advisory_only": True,
        }

    def replay_scaffold(
        self,
        plan: Dict[str, Any],
        scorecard: Dict[str, Any] | None = None,
        *,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Build a non-applying replay scaffold from the strongest lattice match."""
        lookup = self.lookup(plan, scorecard=scorecard, limit=limit)
        best = lookup.get("best_match") if isinstance(lookup.get("best_match"), dict) else {}
        match_strength = float(lookup.get("match_strength") or 0.0)
        blockers = lookup.get("blockers") if isinstance(lookup.get("blockers"), list) else []
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        selected_operations = plan.get("selected_operations") if isinstance(plan.get("selected_operations"), list) else []
        if not selected_operations:
            selected_operations = [
                str(op.get("op_id") or op.get("id") or f"op_{index+1:03d}")
                for index, op in enumerate(operations)
                if isinstance(op, dict) and op.get("selected", True) is not False
            ]
        if match_strength >= 0.88 and not blockers:
            gate_status = "replay_candidate_requires_policy_and_verification"
        elif match_strength >= 0.55:
            gate_status = "strategy_scaffold_requires_operator_review"
        else:
            gate_status = "insufficient_match"
        scaffold_plan = {
            **plan,
            "plan_id": str(plan.get("plan_id") or "sourceplan") + "_lattice_replay",
            "selected_operations": selected_operations,
            "mission_lattice_replay": {
                "cell_id": best.get("cell_id") or "",
                "source_plan_id": best.get("plan_id") or "",
                "evidence_hash": best.get("evidence_hash") or "",
                "match_strength": round(match_strength, 4),
                "reuse_mode": lookup.get("reuse_mode"),
                "gate_status": gate_status,
                "blockers": blockers,
                "no_auto_apply": True,
            },
        }
        return {
            "beast_object_type": "mission_lattice_replay_scaffold",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "lookup": lookup,
            "scaffold_plan": scaffold_plan,
            "gate_status": gate_status,
            "no_auto_apply": True,
            "workflow": [
                "lattice_match",
                "sourceplan_scaffold",
                "policy_gate",
                "verification",
                "evidence_closure",
            ],
        }

    def record_from_packet(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        scorecard = packet.get("scorecard") if isinstance(packet.get("scorecard"), dict) else {}
        plan = {
            "plan_id": packet.get("plan_id"),
            "objective": packet.get("objective"),
            "provider": packet.get("provider"),
            "operations": packet.get("operations") if isinstance(packet.get("operations"), list) else [],
            "selected_operations": [
                str(op.get("op_id") or op.get("id") or "")
                for op in packet.get("operations") or []
                if isinstance(op, dict) and op.get("selected")
            ],
        }
        fingerprint = self.fingerprint_sourceplan(plan, scorecard)
        verification = packet.get("verification") if isinstance(packet.get("verification"), dict) else {}
        cell = {
            "beast_object_type": "mission_crystal_lattice_cell",
            "version": "1.0",
            "cell_id": "mcl_" + hashlib.sha1(fingerprint["fingerprint_hash"].encode("utf-8")).hexdigest()[:16],
            "plan_id": packet.get("plan_id"),
            "objective_terms": fingerprint.get("objective_terms") or [],
            "provider": packet.get("provider") or "",
            "fingerprint": fingerprint,
            "fingerprint_hash": fingerprint.get("fingerprint_hash"),
            "evidence_hash": packet.get("evidence_hash") or "",
            "evidence_packet_path": packet.get("evidence_packet_path") or "",
            "verification_ok": bool(verification.get("ok")),
            "promotion_candidate": bool(packet.get("promotion_candidate")),
            "applied_files_count": len(packet.get("applied_files") or []),
            "created_at": int(time.time()),
            "privacy": {
                "raw_source_content": False,
                "hashes_and_shapes_only": True,
            },
        }
        cells = self._load_cells()
        existing = {str(item.get("cell_id") or ""): item for item in cells if isinstance(item, dict)}
        current = existing.get(cell["cell_id"], {})
        occurrences = current.get("occurrences") if isinstance(current.get("occurrences"), list) else []
        occurrence = {
            "plan_id": cell.get("plan_id"),
            "evidence_hash": cell.get("evidence_hash"),
            "provider": cell.get("provider"),
            "created_at": cell.get("created_at"),
        }
        if occurrence.get("plan_id") not in {item.get("plan_id") for item in occurrences if isinstance(item, dict)}:
            occurrences.append(occurrence)
        if current:
            cell["first_seen"] = current.get("first_seen") or current.get("created_at") or cell["created_at"]
        else:
            cell["first_seen"] = cell["created_at"]
        cell["occurrences"] = occurrences[-20:]
        cell["occurrence_count"] = len(cell["occurrences"])
        existing[cell["cell_id"]] = cell
        saved = sorted(existing.values(), key=lambda item: int(item.get("created_at") or 0), reverse=True)[:500]
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.cells_path.write_text(json.dumps(saved, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        try:
            from app.kernel.evidence.evidence_bus import EvidenceBus

            EvidenceBus(self.workspace_root).register_mission_lattice_cell(cell, cells_path=self.cells_path)
        except Exception:
            pass
        return {
            "beast_object_type": "mission_crystal_lattice_record",
            "version": "1.0",
            "recorded": True,
            "cell_id": cell["cell_id"],
            "fingerprint_hash": cell["fingerprint_hash"],
            "occurrence_count": cell["occurrence_count"],
            "cell_path": str(self.cells_path),
            "advisory_only": True,
        }

    def summary(self, limit: int = 8) -> Dict[str, Any]:
        cells = self._load_cells()
        return {
            "beast_object_type": "mission_crystal_lattice_summary",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "cell_count": len(cells),
            "verified_cell_count": sum(1 for cell in cells if cell.get("verification_ok")),
            "promotion_cell_count": sum(1 for cell in cells if cell.get("promotion_candidate")),
            "cells": cells[: max(1, int(limit or 1))],
            "advisory_only": True,
        }

    def _score(self, wanted: Dict[str, Any], candidate: Dict[str, Any]) -> tuple[float, List[str], List[str]]:
        weights = [
            ("task_family", 0.12),
            ("risk_level", 0.10),
            ("mode", 0.12),
            ("spec_covenant_hash", 0.16),
            ("safety_decision", 0.08),
            ("operation_shape.operation_types", 0.14),
            ("operation_shape.extensions", 0.08),
            ("operation_shape.file_count_bucket", 0.05),
            ("graph_shape.dependent_count_bucket", 0.06),
            ("graph_shape.route_count_bucket", 0.04),
            ("graph_shape.touched_symbol_bucket", 0.05),
        ]
        score = 0.0
        reasons: List[str] = []
        blockers: List[str] = []
        for path, weight in weights:
            left = self._get(wanted, path)
            right = self._get(candidate, path)
            if left in ("", [], None) or right in ("", [], None):
                continue
            if isinstance(left, list) or isinstance(right, list):
                left_set = set(left if isinstance(left, list) else [left])
                right_set = set(right if isinstance(right, list) else [right])
                overlap = len(left_set.intersection(right_set)) / max(1, len(left_set.union(right_set)))
                if overlap:
                    score += weight * overlap
                    reasons.append(path)
            elif left == right:
                score += weight
                reasons.append(path)
        if wanted.get("spec_covenant_hash") and candidate.get("spec_covenant_hash") and wanted.get("spec_covenant_hash") != candidate.get("spec_covenant_hash"):
            blockers.append("spec_covenant_hash_changed")
        if wanted.get("safety_decision") != candidate.get("safety_decision") and wanted.get("safety_decision") in {"block", "require_approval", "sandbox/worktree_only"}:
            blockers.append("safety_posture_changed")
        return min(1.0, score), reasons, blockers

    def _get(self, row: Dict[str, Any], path: str) -> Any:
        current: Any = row
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _load_cells(self) -> List[Dict[str, Any]]:
        try:
            payload = json.loads(self.cells_path.read_text(encoding="utf-8"))
        except Exception:
            payload = []
        return [item for item in payload if isinstance(item, dict)]
