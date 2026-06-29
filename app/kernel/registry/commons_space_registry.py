"""Local registry and approval ledger for BEAST Compute Spaces."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.networking.commons_spaces import (
    MANIFEST_NAME,
    BUNDLE_MANIFEST_NAME,
    RECEIPT_NAME,
    export_space,
    import_space,
    validate_manifest,
    validate_reduction_receipt,
)
from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload
from app.kernel.networking.commons_replay import CommonsReplayEngine
from app.kernel.security.crystal_chain import CrystalChainLedger


class CommonsSpaceRegistry:
    """Discover local Spaces and record explicit, metadata-only adoptions."""

    def __init__(self, root: Optional[Path] = None, *, crystal_chain: Optional[CrystalChainLedger] = None):
        project_root = Path(__file__).resolve().parents[3]
        env_root = os.environ.get("BEAST_COMMONS_ROOT")
        selected_root = root or (Path(env_root) if env_root else project_root / "data" / "commons_spaces")
        self.root = selected_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.adoptions_dir = self.root / "adoptions"
        self.crystal_chain = crystal_chain or CrystalChainLedger(
            self.root / ".crystal_chain" / "blocks.jsonl", node_id=os.environ.get("BEAST_COMMONS_NODE_ID", "local-commons")
        )
        self.replay_engine = CommonsReplayEngine(self, workspace_root=project_root)

    def list_spaces(self) -> Dict[str, Any]:
        spaces = []
        for manifest_path in sorted(self.root.glob(f"*/{MANIFEST_NAME}")):
            try:
                spaces.append(self._summary(manifest_path.parent))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                spaces.append({
                    "space_id": manifest_path.parent.name,
                    "valid": False,
                    "errors": [str(exc)],
                    "path": str(manifest_path.parent),
                })
        artifact_types = Counter(
            item
            for space in spaces
            for item in (space.get("artifact_types") or [])
        )
        source_classes = Counter(str(space.get("source_class") or "unknown") for space in spaces)
        valid_spaces = [item for item in spaces if item.get("valid")]
        scoreboard = {
            "spaces": len(spaces),
            "valid_spaces": len(valid_spaces),
            "verified_spaces": sum(1 for item in valid_spaces if item.get("verifier_passed") is True),
            "provider_calls_avoided": sum(int(item.get("provider_calls_avoided") or 0) for item in valid_spaces),
            "tokens_avoided_observed": sum(int(item.get("tokens_avoided") or 0) for item in valid_spaces if item.get("tokens_evidence") == "observed"),
            "gpu_avoided_spaces": sum(1 for item in valid_spaces if item.get("gpu_avoided") is True),
            "adoptions": len(self.adoptions()),
            "reproductions": len(self.replay_engine.list_reproductions()),
        }
        return {
            "beast_object_type": "commons_space_registry",
            "version": "1.0",
            "authority": "local_advisory",
            "count": len(spaces),
            "spaces": spaces,
            "scoreboard": scoreboard,
            "artifact_sources": {
                "artifact_types": dict(sorted(artifact_types.items())),
                "source_classes": dict(sorted(source_classes.items())),
            },
        }

    def public_registry(self) -> Dict[str, Any]:
        """Project local Spaces into a cloud-safe hypothesis catalog.

        The public registry intentionally publishes metadata, hashes, verifier
        descriptions, reduction claims, reproduction status, and import
        instructions. It never publishes artifact bytes or treats remote claims
        as local authority.
        """
        cards = []
        for manifest_path in sorted(self.root.glob(f"*/{MANIFEST_NAME}")):
            try:
                cards.append(self.public_space_card(manifest_path.parent.name))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return {
            "beast_object_type": "public_commons_registry",
            "version": "1.0",
            "authority": "public_hypothesis_catalog",
            "count": len(cards),
            "primary_action": "import_as_quarantined_hypothesis",
            "local_adoption_engine_required": True,
            "spaces": cards,
            "cloud_boundary": self._public_cloud_boundary(),
        }

    def scale_readiness(self) -> Dict[str, Any]:
        """Summarize whether Commons evidence is ready to scale beyond demos."""
        registry = self.list_spaces()
        spaces = registry.get("spaces") or []
        scoreboard = registry.get("scoreboard") or {}
        states = Counter(str(item.get("adoption_state") or "unknown") for item in spaces)
        lifecycle = Counter(str(item.get("promotion_state") or "unknown") for item in spaces)
        reproductions = self.replay_engine.list_reproductions()
        live_reproductions = [item for item in reproductions if item.get("live_verifier_passed")]
        corpus_size = int(registry.get("count") or 0)
        milestones = [
            {"target": 10, "label": "first repeatable corpus", "met": corpus_size >= 10},
            {"target": 100, "label": "task-boundary match study", "met": corpus_size >= 100},
            {"target": 1000, "label": "lifecycle pressure test", "met": corpus_size >= 1000},
            {"target": 10000, "label": "infrastructure-grade registry", "met": corpus_size >= 10000},
        ]
        unknowns = []
        if corpus_size < 10:
            unknowns.append("case_study_scale")
        if not live_reproductions:
            unknowns.append("cross_machine_reproduction")
        if not any(item.get("reproduction_count") for item in spaces):
            unknowns.append("reuse_frequency")
        if not any(item.get("promotion_state") in {"promoted", "expired", "demoted"} for item in spaces):
            unknowns.append("space_lifecycle_churn")
        return {
            "beast_object_type": "commons_scale_readiness",
            "version": "1.0",
            "corpus": {
                "spaces": corpus_size,
                "valid_spaces": scoreboard.get("valid_spaces"),
                "verified_spaces": scoreboard.get("verified_spaces"),
                "adoption_states": dict(sorted(states.items())),
                "lifecycle_states": dict(sorted(lifecycle.items())),
            },
            "reproduction": {
                "receipts": len(reproductions),
                "live_verifier_reproductions": len(live_reproductions),
                "cross_machine_status": "not_proven" if not live_reproductions else "local_live_replay_observed",
            },
            "workload_match": {
                "status": "unknown_until_production_traffic",
                "required_measurements": [
                    "task_boundary_match_rate",
                    "reuse_frequency",
                    "actual_cloud_calls_displaced",
                    "false_reuse_rate",
                ],
            },
            "latency_interpretation": {
                "baseline_ms": 648,
                "optimized_ms": 15900,
                "delta_multiplier": 24.6,
                "comparison": "broken_vs_working",
                "baseline_status": "capability_failure",
                "optimized_status": "verification_passed",
            },
            "milestones": milestones,
            "unknowns": unknowns,
            "next_actions": [
                "generate_10_spaces_from_existing_benchmark_artifacts",
                "run_replay_matrix_across_hardware_os_ollama_versions",
                "measure_production_task_boundary_match_rate",
                "track_promote_demote_expire_lifecycle",
                "federate_signed_manifests_between_two_allowlisted_nodes",
            ],
        }

    def registration_candidates(self, *, limit: int = 50) -> Dict[str, Any]:
        """Find local benchmark result folders that could become new Spaces."""
        project_root = Path(__file__).resolve().parents[3]
        results_root = project_root / "benchmarks" / "results"
        registered_lineage = {
            str(((self.get(str(space.get("space_id"))) if space.get("valid") else {}).get("manifest") or {}).get("lineage", {}).get("case_study") or "")
            for space in (self.list_spaces().get("spaces") or [])
            if space.get("space_id")
        }
        candidates: List[Dict[str, Any]] = []
        if results_root.exists():
            for path in sorted(item for item in results_root.iterdir() if item.is_dir()):
                files = {child.name for child in path.iterdir() if child.is_file()}
                signals = []
                if "integrity_manifest.json" in files:
                    signals.append("integrity_manifest")
                if "normalized_orchestration_plan.json" in files:
                    signals.append("orchestration_plan")
                if "subsystem_results.json" in files:
                    signals.append("subsystem_results")
                if "provider_fitness.json" in files:
                    signals.append("provider_fitness")
                if "run_manifest.json" in files:
                    signals.append("run_manifest")
                if "README.md" in files:
                    signals.append("readme")
                if not signals:
                    continue
                score = len(signals)
                if {"orchestration_plan", "subsystem_results"} <= set(signals):
                    score += 3
                if {"integrity_manifest", "readme"} <= set(signals):
                    score += 1
                candidates.append({
                    "name": path.name,
                    "path": str(path.relative_to(project_root)),
                    "source": "benchmarks/results",
                    "candidate_kind": "benchmark_result_space",
                    "signals": signals,
                    "registration_score": score,
                    "already_registered": path.name in registered_lineage,
                    "recommended_next_step": "privacy_scrub_then_package_as_quarantined_space",
                })
        forge_root = project_root / "data" / "forge_nodes"
        forge_candidate_count = 0
        if forge_root.exists():
            for snapshot_path in sorted(forge_root.glob("*.json")):
                try:
                    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                feed = snapshot.get("commons_candidate_feed") if isinstance(snapshot, dict) else {}
                feed_candidates = feed.get("candidates") if isinstance(feed, dict) else []
                if not isinstance(feed_candidates, list):
                    continue
                for item in feed_candidates:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or item.get("artifact_id") or snapshot_path.stem)
                    signals = [str(signal) for signal in (item.get("signals") or [])]
                    if not signals:
                        signals = ["forge_snapshot"]
                    candidates.append({
                        "name": name,
                        "path": str(item.get("path") or f"data/forge_nodes/{snapshot_path.name}"),
                        "source": "compute_forge",
                        "candidate_kind": str(item.get("candidate_kind") or "forge_candidate"),
                        "artifact_id": item.get("artifact_id"),
                        "task_class": item.get("task_class"),
                        "signals": signals,
                        "registration_score": int(item.get("registration_score") or 1),
                        "already_registered": False,
                        "recommended_next_step": str(item.get("recommended_next_step") or "package_forge_candidate_as_quarantined_space"),
                    })
                    forge_candidate_count += 1
        candidates.sort(key=lambda item: (item["already_registered"], -int(item["registration_score"]), item["name"]))
        limited = candidates[: max(1, min(int(limit), 500))]
        return {
            "beast_object_type": "commons_registration_candidates",
            "version": "1.0",
            "source": "benchmarks/results + data/forge_nodes",
            "count": len(candidates),
            "returned": len(limited),
            "forge_candidate_count": forge_candidate_count,
            "candidates": limited,
            "registration_pipeline": [
                "discover_candidate_artifacts",
                "privacy_scrub",
                "build_beast_space_manifest",
                "hash_artifacts",
                "sign_receipts",
                "local_replay",
                "operator_approval",
                "adopt_or_reject",
            ],
            "forge_pipeline": [
                "grind_idle_cpu_for_fingerprints_local_inference_and_verifiers",
                "mine_crystals_meta_tools_skills_and_fusions",
                "generate_mutation_ablation_oracles",
                "stage_as_commons_registration_candidates",
                "package_only_after_privacy_scan_and_local_replay",
            ],
        }

    def public_space_card(self, space_id: str) -> Dict[str, Any]:
        detail = self.get(space_id)
        manifest = detail["manifest"]
        receipt = detail.get("reduction_receipt") or {}
        displacement = receipt.get("displacement") or {}
        resources = receipt.get("resource_deltas") or {}
        verifier = receipt.get("verifier") or {}
        reproductions = detail.get("reproductions") or []
        successful = [row for row in reproductions if row.get("reproduced")]
        failed = [row for row in reproductions if not row.get("reproduced")]
        artifacts = [
            {
                "path": item.get("path"),
                "artifact_type": item.get("artifact_type"),
                "sha256": item.get("sha256"),
                "bytes": item.get("bytes"),
            }
            for item in manifest.get("artifacts") or []
        ]
        optimized = receipt.get("optimized_route") or {}
        provider_card = {
            "provider": optimized.get("provider"),
            "model": optimized.get("model"),
            "route_id": optimized.get("route_id"),
            "task_class": manifest.get("task_class"),
            "hardware_profile": manifest.get("hardware_profile") or {},
            "verifier_passed": verifier.get("passed"),
        }
        return {
            "beast_object_type": "public_commons_space_card",
            "version": "1.0",
            "space_id": manifest.get("space_id"),
            "name": manifest.get("name"),
            "task_class": manifest.get("task_class"),
            "authority": "advisory_remote_hypothesis",
            "manifest_hash": manifest.get("manifest_hash"),
            "manifest": {
                "version": manifest.get("version"),
                "created_at": manifest.get("created_at"),
                "artifacts": artifacts,
                "hardware_profile": manifest.get("hardware_profile") or {},
                "verifier_bundles": manifest.get("verifier_bundles") or [],
                "safety": manifest.get("safety") or {},
                "privacy": manifest.get("privacy") or {},
                "lineage": manifest.get("lineage") or {},
            },
            "signed_receipts": [{
                "receipt_id": receipt.get("receipt_id"),
                "fingerprint_hash": receipt.get("fingerprint_hash"),
                "space_manifest_hash": receipt.get("space_manifest_hash"),
                "local_seal": receipt.get("local_seal"),
            }] if receipt else [],
            "provider_fitness_cards": [provider_card],
            "reduction_claims": {
                "manifest_claims": manifest.get("reduction_claims") or {},
                "provider_calls_avoided": displacement.get("provider_calls_avoided"),
                "tokens_avoided": displacement.get("tokens_avoided"),
                "latency_avoided_ms": displacement.get("latency_avoided_ms"),
                "gpu_avoided": resources.get("gpu_avoided"),
                "evidence_class": displacement.get("evidence_class"),
                "counterfactual": bool(displacement.get("counterfactual")),
            },
            "reproduction_status": {
                "successful": len(successful),
                "failed": len(failed),
                "local_trust_score": max((float(row.get("trust_score") or 0.0) for row in reproductions), default=0.0),
            },
            "risk_approval": {
                "risk": (manifest.get("safety") or {}).get("risk"),
                "approval_required": (manifest.get("safety") or {}).get("approval_required"),
                "adoption_state": self.adoption_state(space_id, detail=detail),
            },
            "primary_action": "import_as_quarantined_hypothesis",
            "local_adoption_engine": {
                "required": True,
                "steps": [
                    "download_import_manifest",
                    "quarantine_artifact",
                    "verify_hashes_and_signature",
                    "dry_run_replay",
                    "run_local_verifier",
                    "compare_local_fingerprints",
                    "ask_for_approval",
                    "adopt_into_local_commons",
                    "promote_to_crystal_compute_after_local_proof",
                ],
            },
            "excluded_from_public_card": [
                "raw_private_prompts",
                "private_source_code",
                "secrets",
                "absolute_local_paths",
                "private_rollback_snapshots",
                "raw_company_data",
                "private_test_fixtures",
                "artifact_payload_bytes",
            ],
        }

    def adoption_state(self, space_id: str, *, detail: Optional[Dict[str, Any]] = None) -> str:
        detail = detail or self.get(space_id)
        manifest = detail.get("manifest") or {}
        safety = manifest.get("safety") or {}
        if safety.get("promotion_state") == "promoted":
            return "promoted"
        if any(item.get("adopted") for item in detail.get("adoptions") or []):
            return "adopted"
        reproductions = detail.get("reproductions") or []
        if any(item.get("reproduced") and float(item.get("trust_score") or 0.0) >= 1.0 for item in reproductions):
            return "approved_candidate"
        if any(item.get("reproduced") for item in reproductions):
            return "reproduced"
        return "quarantined_hypothesis"

    def get(self, space_id: str) -> Dict[str, Any]:
        root = self._space_root(space_id)
        manifest = self._read(root / MANIFEST_NAME)
        validation = validate_manifest(root, manifest)
        receipt = self._read(root / RECEIPT_NAME) if (root / RECEIPT_NAME).is_file() else {}
        receipt_validation = validate_reduction_receipt(receipt) if receipt else {}
        return {
            "beast_object_type": "commons_space_detail",
            "version": "1.0",
            "space_id": space_id,
            "manifest": manifest,
            "manifest_validation": validation,
            "reduction_receipt": receipt,
            "receipt_validation": receipt_validation,
            "adoptions": [item for item in self.adoptions() if item.get("space_id") == space_id],
            "reproductions": self.replay_engine.list_reproductions(space_id),
        }

    def replay(
        self,
        space_id: str,
        *,
        target: Optional[Path] = None,
        deterministic_only: bool = True,
        approved: bool = False,
        timeout_seconds: int = 120,
        contributor_id: str = "local",
    ) -> Dict[str, Any]:
        return self.replay_engine.replay(
            space_id,
            target=target,
            deterministic_only=deterministic_only,
            approved=approved,
            timeout_seconds=timeout_seconds,
            contributor_id=contributor_id,
        )

    def import_bundle(
        self,
        bundle: Path,
        *,
        approved: bool,
        dry_run: bool = True,
        workspace_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        bundle = bundle.resolve()
        allowed_root = (workspace_root or Path(__file__).resolve().parents[2]).resolve()
        if allowed_root != bundle and allowed_root not in bundle.parents:
            raise ValueError("bundle_path must be inside the local workspace")
        return import_space(bundle, self.root, approved=approved, dry_run=dry_run)

    def export_bundle(self, space_id: str, *, destination: Optional[Path] = None) -> Dict[str, Any]:
        detail = self.get(space_id)
        bundle_dir = self.root / "_bundles"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        target = destination or bundle_dir / f"{space_id}.beast-space.zip"
        if destination is None and target.is_file():
            try:
                with zipfile.ZipFile(target) as archive:
                    bundle_manifest = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
                if bundle_manifest.get("space_manifest_hash") == detail["manifest"].get("manifest_hash"):
                    return {
                        "beast_object_type": "beast_compute_space_export", "version": "1.0",
                        "space_id": space_id, "local_only": True, "path": str(target),
                        "bundle_id": bundle_manifest.get("bundle_id"),
                        "entry_count": len(bundle_manifest.get("entries") or []),
                        "privacy_scan": bundle_manifest.get("privacy_scan") or {"safe": True},
                        "sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
                        "cached": True,
                    }
            except (OSError, KeyError, ValueError, json.JSONDecodeError, zipfile.BadZipFile):
                pass
        return export_space(self._space_root(space_id), target)

    def import_untrusted_bundle(
        self,
        bundle: Path,
        *,
        approved: bool,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Import a bundle already downloaded from a remote node.

        This bypasses the local-workspace path restriction used by manual
        imports, but it still goes through the normal content-addressed bundle,
        signature, privacy, traversal, manifest, and artifact hash checks.
        """
        return import_space(bundle.resolve(), self.root, approved=approved, dry_run=dry_run)

    def adopt(
        self,
        space_id: str,
        *,
        artifact_paths: Optional[List[str]] = None,
        approved: bool,
        dry_run: bool = True,
        approved_by: str = "operator",
        reason: str = "",
    ) -> Dict[str, Any]:
        detail = self.get(space_id)
        if not detail["manifest_validation"].get("valid") or not detail["receipt_validation"].get("valid"):
            raise ValueError("Space manifest and reduction receipt must validate before adoption")
        artifacts = detail["manifest"].get("artifacts") or []
        selected = set(artifact_paths or [str(item.get("path") or "") for item in artifacts])
        unknown = selected - {str(item.get("path") or "") for item in artifacts}
        if unknown:
            raise ValueError("unknown artifact paths: " + ", ".join(sorted(unknown)))
        references = [
            {
                "path": item["path"],
                "artifact_type": item["artifact_type"],
                "sha256": item["sha256"],
            }
            for item in artifacts
            if item.get("path") in selected
        ]
        result = {
            "beast_object_type": "commons_space_adoption",
            "version": "1.0",
            "space_id": space_id,
            "manifest_hash": detail["manifest"].get("manifest_hash"),
            "artifact_references": references,
            "authority": "local_operator",
            "approved": bool(approved),
            "dry_run": bool(dry_run),
            "approved_by": approved_by,
            "reason": reason,
            "adopted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if dry_run or not approved:
            result["status"] = "dry_run" if dry_run else "approval_required"
            return result
        if not reason.strip():
            raise ValueError("an operator reason is required for adoption")
        result["adopted"] = True
        result["status"] = "adopted"
        result["adoption_id"] = "adopt_" + hashlib.sha256(canonical_bytes(result)).hexdigest()[:20]
        result["local_seal"] = seal_crystal_payload(result, purpose="commons_space_adoption")
        chain_block = self.crystal_chain.append("commons_space_adopted", result["adoption_id"], result)
        result["crystal_chain_block_hash"] = chain_block["block_hash"]
        self.adoptions_dir.mkdir(parents=True, exist_ok=True)
        path = self.adoptions_dir / f"{result['adoption_id']}.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["receipt_path"] = str(path)
        return result

    def adoptions(self) -> List[Dict[str, Any]]:
        rows = []
        for path in sorted(self.adoptions_dir.glob("*.json")) if self.adoptions_dir.exists() else []:
            try:
                rows.append(self._read(path))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return rows

    def _summary(self, root: Path) -> Dict[str, Any]:
        manifest = self._read(root / MANIFEST_NAME)
        validation = validate_manifest(root, manifest)
        receipt = self._read(root / RECEIPT_NAME) if (root / RECEIPT_NAME).is_file() else {}
        receipt_validation = validate_reduction_receipt(receipt) if receipt else {"valid": False}
        displacement = receipt.get("displacement") or {}
        resources = receipt.get("resource_deltas") or {}
        verifier = receipt.get("verifier") or {}
        reproductions = [
            item for item in self.replay_engine.list_reproductions(str(manifest.get("space_id") or ""))
            if item.get("manifest_hash") == manifest.get("manifest_hash")
        ]
        trust_score = max((float(item.get("trust_score") or 0.0) for item in reproductions), default=0.0)
        source_class = str((manifest.get("lineage") or {}).get("case_study") or "local_space")
        evidence_class = str(displacement.get("evidence_class") or "unknown")
        return {
            "space_id": manifest.get("space_id"),
            "name": manifest.get("name"),
            "task_class": manifest.get("task_class"),
            "authority": manifest.get("authority"),
            "valid": bool(validation.get("valid") and receipt_validation.get("valid")),
            "artifact_count": len(manifest.get("artifacts") or []),
            "artifact_types": sorted({str(item.get("artifact_type") or "unknown") for item in manifest.get("artifacts") or []}),
            "source_class": source_class,
            "provider_calls_avoided": displacement.get("provider_calls_avoided"),
            "tokens_avoided": displacement.get("tokens_avoided"),
            "tokens_evidence": "counterfactual" if displacement.get("counterfactual") else "observed",
            "gpu_avoided": resources.get("gpu_avoided"),
            "verifier_passed": verifier.get("passed"),
            "evidence_class": evidence_class,
            "approval_required": manifest.get("safety", {}).get("approval_required"),
            "promotion_state": manifest.get("safety", {}).get("promotion_state"),
            "adoption_state": self.adoption_state(str(manifest.get("space_id") or ""), detail={
                "manifest": manifest,
                "adoptions": [item for item in self.adoptions() if item.get("space_id") == manifest.get("space_id")],
                "reproductions": reproductions,
            }),
            "reproduction_count": len(reproductions),
            "local_trust_score": trust_score,
            "path": str(root),
        }

    @staticmethod
    def _public_cloud_boundary() -> Dict[str, Any]:
        return {
            "hosts": [
                "compute_space_manifests",
                "artifact_hashes",
                "signed_receipts",
                "verifier_bundle_descriptions",
                "provider_fitness_cards",
                "reduction_claims",
                "reproduction_status",
                "risk_approval_metadata",
                "public_documentation",
            ],
            "does_not_host": [
                "raw_private_prompts",
                "private_source_code",
                "secrets",
                "local_paths",
                "private_rollback_snapshots",
                "raw_company_data",
                "private_test_fixtures",
            ],
            "trust_rule": "Cloud entries are hypotheses; only the local BEAST adoption engine can make them trusted capability.",
        }

    def _space_root(self, space_id: str) -> Path:
        if not space_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in space_id):
            raise ValueError("invalid space_id")
        root = (self.root / space_id).resolve()
        if self.root != root and self.root not in root.parents:
            raise ValueError("invalid space_id")
        if not (root / MANIFEST_NAME).is_file():
            raise ValueError(f"Compute Space not found: {space_id}")
        return root

    @staticmethod
    def _read(path: Path) -> Dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"expected JSON object: {path}")
        return payload
