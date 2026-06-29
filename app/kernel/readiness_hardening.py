"""Executable hardening gates for BEAST production-readiness hurdles.

The goal of this module is deliberately narrower than "declare production
ready."  It turns the remaining readiness blockers into repeatable gates with
receipts:

- federation durability and abuse controls;
- cross-profile adoption/reproduction;
- workload-frequency evidence;
- large-scale anti-gaming evidence;
- production-ops readiness;
- loaded LoRA/adapter proof boundaries.

Where a gate needs external evidence that a local test cannot honestly provide
(for example true cross-OS machines or internet adversaries), the gate returns
``needs_external_evidence`` instead of fabricating a pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.networking.commons_anti_gaming import CommonsAntiGaming
from app.kernel.networking.commons_spaces import package_tiny_llama_case
from app.kernel.networking.federated_commons import FederatedCommons
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "benchmarks" / "results"
CASE_ROOT = RESULTS_ROOT / "tiny_llama_opus_case_study_qwen25_05b"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": type(exc).__name__, "_path": str(path), "_message": str(exc)}


def _hash_payload(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _status(ok: bool, *, external: bool = False) -> str:
    if ok:
        return "satisfied"
    return "needs_external_evidence" if external else "blocked"


class ProductionReadinessHardeningGauntlet:
    """Run local readiness-hardening gates and write a durable receipt."""

    def __init__(self, output_root: Optional[Path] = None):
        self.output_root = (output_root or RESULTS_ROOT).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        federation = self.federation_durability_gate()
        workload = self.workload_frequency_gate()
        anti_gaming = self.anti_gaming_gate()
        ops = self.production_ops_gate()
        adapter = self.adapter_proof_gate()
        gates = {
            "federation_durability": federation,
            "workload_frequency": workload,
            "large_scale_anti_gaming": anti_gaming,
            "production_ops": ops,
            "adapter_weight_level_improvement": adapter,
        }
        summary = self._summarize(gates)
        report = {
            "beast_object_type": "beast_production_readiness_hardening_gauntlet",
            "version": "1.0",
            "generated_at": _utc_now(),
            "gates": gates,
            "summary": summary,
            "promotion_boundary": (
                "A local hardening gate may satisfy lab readiness. Public production/marketplace "
                "claims still require external cross-machine, internet-federation, and workload evidence."
            ),
        }
        report["receipt_hash"] = _hash_payload(report)
        latest = self.output_root / "production_readiness_hardening_latest.json"
        latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    def federation_durability_gate(self) -> Dict[str, Any]:
        """Exercise signed federation, churn, duplicates, revocation, and reputation."""

        events: List[Dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="beast-readiness-fed-") as temp:
            root = Path(temp)
            source_registry = CommonsSpaceRegistry(root / "node_a" / "spaces")
            target_registry = CommonsSpaceRegistry(root / "node_b" / "spaces")
            package_tiny_llama_case(CASE_ROOT, source_registry.root / "tiny_llama_opus_gateway_repair")
            package_tiny_llama_case(CASE_ROOT, target_registry.root / "tiny_llama_opus_gateway_repair")
            source_fed = FederatedCommons(source_registry, root / "node_a" / "federation")
            target_fed = FederatedCommons(target_registry, root / "node_b" / "federation")

            envelope = source_fed.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_alpha", ttl_days=7)
            try:
                target_fed.ingest(envelope)
            except Exception as exc:
                events.append({"event": "non_allowlisted_rejected", "ok": "allowlisted" in str(exc) or "allowlisted" in type(exc).__name__.lower(), "message": str(exc)})

            target_fed.allow_contributor(
                "node_alpha",
                public_key_hash=envelope["signature"]["public_key_hash"],
                approved=True,
                reason="readiness hardening test node",
            )
            ingested = target_fed.ingest(envelope)
            duplicate = target_fed.ingest(envelope)
            replay = target_registry.replay("tiny_llama_opus_gateway_repair", contributor_id="node_alpha")
            reproduced = target_fed.record_reproduction(envelope["envelope_id"], replay)
            reproduced_duplicate = target_fed.record_reproduction(envelope["envelope_id"], replay)

            tampered = dict(envelope)
            tampered["space_id"] = "tampered_space"
            tampered["envelope_id"] = "fed_tampered_" + hashlib.sha256(b"readiness-tamper").hexdigest()[:24]
            try:
                target_fed.ingest(tampered)
            except Exception as exc:
                events.append({"event": "tampered_signature_rejected", "ok": "signature" in str(exc).lower(), "message": str(exc)})

            revoked = target_fed.revoke(
                envelope["envelope_id"],
                approved=True,
                reason="readiness churn retirement",
                approved_by="readiness_gauntlet",
            )
            state = target_fed.state()

        checks = {
            "non_allowlisted_rejected": any(item["event"] == "non_allowlisted_rejected" and item["ok"] for item in events),
            "signed_envelope_ingested_as_quarantine": ingested.get("state") == "quarantined_hypothesis",
            "duplicate_suppressed": bool(duplicate.get("duplicate")),
            "local_reproduction_recorded": bool(reproduced.get("reproduced")),
            "reputation_incremented_once": (reproduced.get("reputation") or {}).get("successful_reproductions") == 1,
            "duplicate_reproduction_suppressed": bool(reproduced_duplicate.get("duplicate")),
            "tampered_signature_rejected": any(item["event"] == "tampered_signature_rejected" and item["ok"] for item in events),
            "revocation_recorded": bool(revoked.get("revoked")),
            "abuse_controls_present": bool((state.get("abuse_controls") or {}).get("max_ttl_days")),
        }
        return {
            "beast_object_type": "federation_durability_hardening_gate",
            "status": _status(all(checks.values())),
            "checks": checks,
            "reputation": reproduced.get("reputation"),
            "events": events,
            "claim_boundary": (
                "This is a local two-node durability/churn simulation. It does not prove public internet federation."
            ),
        }

    def federation_soak_gate(self, *, nodes: int = 3, cycles: int = 3) -> Dict[str, Any]:
        """Run a bounded multi-node federation churn/replay soak."""
        nodes = max(2, min(int(nodes or 3), 5))
        cycles = max(1, min(int(cycles or 3), 12))
        events: List[Dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="beast-readiness-fed-soak-") as temp:
            root = Path(temp)
            registries = [CommonsSpaceRegistry(root / f"node_{idx}" / "spaces") for idx in range(nodes)]
            federations = [FederatedCommons(reg, root / f"node_{idx}" / "federation") for idx, reg in enumerate(registries)]
            for reg in registries:
                package_tiny_llama_case(CASE_ROOT, reg.root / "tiny_llama_opus_gateway_repair")
            for cycle in range(cycles):
                source_idx = cycle % nodes
                target_idx = (cycle + 1) % nodes
                source = federations[source_idx]
                target = federations[target_idx]
                contributor = f"node_{source_idx}"
                envelope = source.prepare("tiny_llama_opus_gateway_repair", contributor_id=contributor, ttl_days=7)
                target.allow_contributor(
                    contributor,
                    public_key_hash=envelope["signature"]["public_key_hash"],
                    approved=True,
                    reason="bounded federation soak",
                )
                ingested = target.ingest(envelope)
                duplicate = target.ingest(envelope)
                replay = registries[target_idx].replay("tiny_llama_opus_gateway_repair", contributor_id=contributor)
                reproduced = target.record_reproduction(envelope["envelope_id"], replay)
                if cycle % 2 == 1:
                    target.revoke(envelope["envelope_id"], approved=True, reason="soak churn", approved_by="readiness_soak")
                events.append(
                    {
                        "cycle": cycle,
                        "source": contributor,
                        "target": f"node_{target_idx}",
                        "ingested_state": ingested.get("state"),
                        "duplicate_suppressed": bool(duplicate.get("duplicate")),
                        "reproduced": bool(reproduced.get("reproduced")),
                    }
                )
        checks = {
            "node_count_at_least_three": nodes >= 3,
            "cycles_completed": len(events) == cycles,
            "duplicates_suppressed": all(item["duplicate_suppressed"] for item in events),
            "replay_reproduced": all(item["reproduced"] for item in events),
            "churn_exercised": cycles >= 2,
        }
        receipt = {
            "beast_object_type": "federation_soak_hardening_gate",
            "version": "1.0",
            "generated_at": _utc_now(),
            "status": _status(all(checks.values())),
            "nodes": nodes,
            "cycles": cycles,
            "checks": checks,
            "events": events,
            "claim_boundary": "Bounded local multi-node soak. Public internet federation still needs external soak evidence.",
        }
        receipt["receipt_hash"] = _hash_payload(receipt)
        (self.output_root / "federation_soak_latest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt

    def workload_frequency_gate(self) -> Dict[str, Any]:
        """Aggregate current local workload-match receipts."""

        receipts = []
        for path in sorted(RESULTS_ROOT.glob("live_commons_displacement_harness*.json")):
            data = _read_json(path)
            if data.get("_read_error"):
                continue
            observed = data.get("observed") if isinstance(data.get("observed"), dict) else {}
            receipts.append({
                "path": str(path.relative_to(PROJECT_ROOT)),
                "space_id": data.get("space_id") or (data.get("manifest") or {}).get("space_id"),
                "repeated_matches": int(observed.get("repeated_matches") or data.get("repeated_matches") or 0),
                "cloud_api_calls_avoided": int(observed.get("cloud_api_calls_avoided") or observed.get("cloud_calls_avoided") or 0),
                "adopted": bool((data.get("adoption") or {}).get("adopted")),
            })
        semantic_receipts = list((RESULTS_ROOT / "semantic_compute_pages" / "receipts").glob("*.json"))
        semantic_count = len(semantic_receipts)
        total_matches = sum(item["repeated_matches"] for item in receipts) + semantic_count
        total_avoided = sum(item["cloud_api_calls_avoided"] for item in receipts)
        spaces_with_matches = len({item["space_id"] for item in receipts if item["space_id"] and item["repeated_matches"] > 0})
        pilot = _read_json(RESULTS_ROOT / "workload_frequency_pilot_latest.json")
        checks = {
            "at_least_30_local_displacements_or_semantic_reuse_receipts": total_matches >= 30,
            "at_least_10_local_receipt_sources": len(receipts) + semantic_count >= 10,
            "adoption_receipts_present": any(item["adopted"] for item in receipts),
        }
        external_checks = {
            "thirty_day_production_traffic_window": float(pilot.get("window_days_equivalent") or 0) >= 30,
            "false_reuse_rate_measured": pilot.get("false_reuse_rate") is not None,
        }
        return {
            "beast_object_type": "workload_frequency_hardening_gate",
            "status": _status(all(checks.values()) and all(external_checks.values()), external=all(checks.values())),
            "lab_status": _status(all(checks.values())),
            "checks": checks,
            "external_checks": external_checks,
            "observed": {
                "receipt_count": len(receipts),
                "semantic_compute_reuse_receipts": semantic_count,
                "spaces_with_live_matches": spaces_with_matches,
                "total_local_matches_or_reuse_receipts": total_matches,
                "cloud_api_calls_avoided_from_live_receipts": total_avoided,
                "pilot_receipt": None if pilot.get("_read_error") else "benchmarks/results/workload_frequency_pilot_latest.json",
            },
            "claim_boundary": (
                "Local receipts show repeatable displacement/reuse. A production frequency claim still requires "
                "a real traffic window and false-reuse measurement."
            ),
        }

    def workload_frequency_receipt(self, *, window_days: int = 7) -> Dict[str, Any]:
        """Emit a 7/30-day style workload-frequency receipt from local evidence."""
        window_days = 30 if int(window_days or 7) >= 30 else 7
        gate = self.workload_frequency_gate()
        observed = gate.get("observed") if isinstance(gate.get("observed"), dict) else {}
        receipt = {
            "beast_object_type": "workload_frequency_window_receipt",
            "version": "1.0",
            "generated_at": _utc_now(),
            "window_days": window_days,
            "source_gate_status": gate.get("status"),
            "lab_status": gate.get("lab_status"),
            "observed": observed,
            "frequency": {
                "local_matches_per_day": round(float(observed.get("total_local_matches_or_reuse_receipts") or 0) / float(window_days), 4),
                "avoided_cloud_calls_per_day": round(float(observed.get("cloud_api_calls_avoided_from_live_receipts") or 0) / float(window_days), 4),
                "receipt_sources_per_day": round(float(observed.get("receipt_count") or 0) / float(window_days), 4),
            },
            "gates": {
                "has_false_reuse_measurement": bool((gate.get("external_checks") or {}).get("false_reuse_rate_measured")),
                "has_traffic_window": bool((gate.get("external_checks") or {}).get("thirty_day_production_traffic_window")),
            },
            "claim_boundary": "This receipt normalizes current evidence into a window; it is production-grade only after real traffic fills the window.",
        }
        receipt["receipt_hash"] = _hash_payload(receipt)
        (self.output_root / f"workload_frequency_{window_days}d_latest.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    def anti_gaming_gate(self) -> Dict[str, Any]:
        """Validate large synthetic anti-gaming pressure and invariant controls."""

        latest = _read_json(RESULTS_ROOT / "commons_anti_gaming_stress_latest.json")
        if latest.get("_read_error"):
            generated = self._generate_anti_gaming_pressure()
        else:
            generated = latest
        identities = int(generated.get("identities_analyzed") or 0)
        flagged = len(generated.get("flagged_accounts") or [])
        balanced = bool(generated.get("ledger_balanced"))
        risk_counts = generated.get("risk_counts") or {}
        checks = {
            "ten_thousand_identities_analyzed": identities >= 10_000,
            "malicious_accounts_flagged": flagged >= 1 or int(risk_counts.get("freeze") or 0) >= 1,
            "ledger_balanced": balanced,
            "hard_actions_present": int(risk_counts.get("freeze") or 0) >= 1 or any((row.get("action") == "freeze") for row in generated.get("flagged_accounts") or []),
        }
        return {
            "beast_object_type": "large_scale_anti_gaming_hardening_gate",
            "status": _status(all(checks.values())),
            "checks": checks,
            "observed": {
                "identities_analyzed": identities,
                "flagged_accounts": flagged,
                "risk_counts": risk_counts,
                "global_action": generated.get("global_action"),
            },
            "claim_boundary": "Synthetic pressure validates controls, not internet-scale adversarial behavior.",
        }

    def production_ops_gate(self) -> Dict[str, Any]:
        """Check local operational surfaces needed before a durable pilot."""

        files = {
            "docker_compose_commons_lab": PROJECT_ROOT / "docker-compose.commons-lab.yml",
            "commons_node_dockerfile": PROJECT_ROOT / "Dockerfile.commons-node",
            "readiness_assessment": PROJECT_ROOT / "docs" / "beast-system-readiness-assessment-2026-06-28.md",
            "api_docs": PROJECT_ROOT / "docs" / "api.md",
            "edge_runtime_setup": PROJECT_ROOT / "docs" / "edge_runtime_setup.md",
        }
        ports = {
            "gateway_8000": self._port_open("127.0.0.1", 8000),
            "mcp_8001": self._port_open("127.0.0.1", 8001),
            "ollama_11434": self._port_open("127.0.0.1", 11434),
        }
        checks = {
            "deployment_artifacts_present": all(path.exists() for path in files.values()),
            "readiness_doc_present": files["readiness_assessment"].exists(),
            "local_core_ports_observable": any(ports.values()),
            "result_directory_writable": os.access(str(self.output_root), os.W_OK),
        }
        ops_drill = _read_json(RESULTS_ROOT / "ops" / "production_ops_drill_latest.json")
        external_checks = {
            "service_supervision_installed": bool(ops_drill.get("service_supervision_ready")),
            "backup_restore_drill_recorded": bool(ops_drill.get("backup_restore_drill_recorded")),
            "migration_policy_exercised": bool(ops_drill.get("migration_policy_exercised")),
        }
        return {
            "beast_object_type": "production_ops_hardening_gate",
            "status": _status(all(checks.values()) and all(external_checks.values()), external=all(checks.values())),
            "lab_status": _status(all(checks.values())),
            "checks": checks,
            "external_checks": external_checks,
            "files": {name: str(path.relative_to(PROJECT_ROOT)) for name, path in files.items()},
            "ports": ports,
            "ops_drill_receipt": None if ops_drill.get("_read_error") else "benchmarks/results/ops/production_ops_drill_latest.json",
            "claim_boundary": (
                "Local operational artifacts exist. Production ops still requires supervised services, "
                "backup/restore drills, migration rehearsals, and observability SLOs."
            ),
        }

    def adapter_proof_gate(self) -> Dict[str, Any]:
        """Evaluate the current adapter/LoRA proof boundary from receipts."""

        comparison = self._freshest_json([
            RESULTS_ROOT / "adapter_comparison" / "heldout_adapter_comparison_latest.json",
            RESULTS_ROOT / "adapter_comparison" / "heldout_adapter_comparison_live_latest.json",
            RESULTS_ROOT / "adapter_comparison" / "heldout_adapter_comparison_offline_latest.json",
        ])
        summary = comparison.get("summary") if isinstance(comparison.get("summary"), dict) else {}
        baseline = summary.get("baseline_qwen_05b") or {}
        wrapper = summary.get("beast_modelfile_wrapper") or {}
        lora = summary.get("trained_beast_lora_adapter") or {}
        crystal = summary.get("crystal_only_route") or {}
        package_paths = [
            RESULTS_ROOT / "crystal_to_adapter_distillation" / "qwen_lora_fast_smoke" / "adapter_model.safetensors",
            RESULTS_ROOT / "crystal_to_adapter_distillation" / "micro_lora_adapter_latest" / "adapter" / "adapter_model.safetensors",
        ]
        checks = {
            "adapter_artifact_present": any(path.exists() for path in package_paths),
            "crystal_only_hidden_verifier_passes": float(crystal.get("hidden_verifier_pass") or 0.0) >= 0.95,
            "adapter_remains_proposal_only": all(
                not bool((comparison.get("promotion_verdict") or {}).get(lane, {}).get("promote_to_execution"))
                for lane in ("trained_beast_lora_adapter", "beast_modelfile_wrapper", "crystal_only_route")
            ),
        }
        improvement_checks = {
            "loaded_lora_lane_measured": "measured" in set(lora.get("statuses") or []),
            "lora_schema_validity_beats_baseline": float(lora.get("schema_validity") or 0.0) > float(baseline.get("schema_validity") or 0.0),
            "lora_hidden_verifier_passes": float(lora.get("hidden_verifier_pass") or 0.0) >= 0.95,
        }
        return {
            "beast_object_type": "adapter_weight_level_hardening_gate",
            "status": _status(all(checks.values()) and all(improvement_checks.values())),
            "artifact_status": _status(all(checks.values())),
            "checks": checks,
            "improvement_checks": improvement_checks,
            "lane_summary": {
                "baseline_qwen_05b": baseline,
                "beast_modelfile_wrapper": wrapper,
                "trained_beast_lora_adapter": lora,
                "crystal_only_route": crystal,
            },
            "claim_boundary": (
                "Adapter artifacts and loaded runtime are tracked as proposal-only. This gate proves a safe "
                "loaded-adapter proposal lane, not autonomous execution or pure raw-weight superiority."
            ),
        }

    def _generate_anti_gaming_pressure(self) -> Dict[str, Any]:
        signup_events = []
        swaps = []
        claims = []
        for i in range(10_000):
            user = f"user_{i:05d}"
            source = f"source_{i // 5:04d}" if i < 250 else f"source_unique_{i:05d}"
            signup_events.append({"user_id": user, "source_hash": source})
            if i < 250:
                for j in range(24):
                    swaps.append({
                        "user_id": user,
                        "amount_in": 600 + (j % 11),
                        "from_asset": "BEASTCOIN" if j % 2 == 0 else "CRYSTAL",
                    })
        return CommonsAntiGaming().analyze(signup_events=signup_events, swaps=swaps, claims=claims, ledger_balanced=True)

    @staticmethod
    def _freshest_json(paths: Iterable[Path]) -> Dict[str, Any]:
        existing = [path for path in paths if path.is_file()]
        if not existing:
            return {"_read_error": "FileNotFoundError", "_path": ",".join(str(path) for path in paths)}
        return _read_json(max(existing, key=lambda path: path.stat().st_mtime))

    @staticmethod
    def _port_open(host: str, port: int, timeout: float = 0.1) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _summarize(gates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        statuses = {name: gate.get("status") for name, gate in gates.items()}
        lab_statuses = {name: gate.get("lab_status", gate.get("artifact_status", gate.get("status"))) for name, gate in gates.items()}
        return {
            "statuses": statuses,
            "lab_statuses": lab_statuses,
            "local_lab_hardened": all(value == "satisfied" for value in lab_statuses.values()),
            "production_claim_ready": all(value == "satisfied" for value in statuses.values()),
            "needs_external_evidence": sorted(name for name, value in statuses.items() if value == "needs_external_evidence"),
            "blocked": sorted(name for name, value in statuses.items() if value == "blocked"),
        }
