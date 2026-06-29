"""Local-first BEAST Compute Space manifests and reduction receipts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload, verify_crystal_seal
from app.kernel.networking.commons_privacy import CommonsPrivacyScrubber


SPACE_VERSION = "1.0"
RECEIPT_VERSION = "1.0"
MANIFEST_NAME = "beast_space.json"
RECEIPT_NAME = "compute_reduction_receipt.json"
RECEIPT_MARKDOWN_NAME = "compute_reduction_receipt.md"
BUNDLE_MANIFEST_NAME = "beast_bundle_manifest.json"

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+[a-z0-9._-]+|password|secret|token)\s*[:=]"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _relative_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"artifact path must be local and relative: {value}")
    return str(path)


def _privacy_scan(path: Path) -> List[str]:
    if CommonsPrivacyScrubber.looks_like_private_key_path(str(path)):
        return ["private_key_file"]
    forbidden_reason = CommonsPrivacyScrubber.forbidden_export_path_reason(str(path))
    if forbidden_reason:
        return [forbidden_reason]
    try:
        prefix = path.read_bytes()[:16_384]
        if b"-----BEGIN " in prefix and b"PRIVATE KEY-----" in prefix:
            return ["private_key_material"]
    except OSError:
        return ["unreadable_artifact"]
    if path.suffix.lower() not in {".json", ".md", ".txt", ".yaml", ".yml", ".toml"}:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = []
    if _SECRET_PATTERN.search(text):
        findings.append("possible_secret_material")
    if re.search(r"(?m)(?:^|[\s\"'])/(?:home|Users|workspace|private|tmp)/", text):
        findings.append("absolute_workspace_path")
    return findings


def artifact_record(root: Path, relative_path: str, artifact_type: str) -> Dict[str, Any]:
    rel = _relative_path(relative_path)
    path = (root / rel).resolve()
    if not path.is_file() or root.resolve() not in path.parents:
        raise ValueError(f"artifact does not exist inside Space root: {rel}")
    findings = _privacy_scan(path)
    if findings:
        raise ValueError(f"privacy scan failed for {rel}: {', '.join(findings)}")
    body = path.read_bytes()
    return {
        "path": rel,
        "artifact_type": artifact_type,
        "sha256": _sha256_bytes(body),
        "bytes": len(body),
    }


def build_manifest(
    root: Path,
    *,
    space_id: str,
    name: str,
    task_class: str,
    artifacts: Iterable[Dict[str, str]],
    hardware_profile: Dict[str, Any],
    verifier_bundles: List[Dict[str, Any]],
    reduction_claims: Dict[str, Any],
    safety: Dict[str, Any],
    lineage: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    records = [
        artifact_record(root, item["path"], item.get("artifact_type") or "evidence")
        for item in artifacts
    ]
    manifest = {
        "beast_object_type": "beast_compute_space",
        "version": SPACE_VERSION,
        "space_id": space_id,
        "name": name,
        "task_class": task_class,
        "created_at": created_at or _utc_now(),
        "authority": "advisory",
        "artifacts": records,
        "hardware_profile": hardware_profile,
        "verifier_bundles": verifier_bundles,
        "reduction_claims": reduction_claims,
        "safety": safety,
        "lineage": lineage or {},
        "privacy": {
            "local_only": True,
            "contains_raw_prompts": False,
            "contains_secrets": False,
            "contains_private_paths": False,
            "contains_source_code": False,
            "content_fingerprints_only": True,
        },
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = _sha256_bytes(canonical_bytes(manifest))
    return manifest


def validate_manifest(root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    required = {
        "beast_object_type",
        "version",
        "space_id",
        "name",
        "task_class",
        "artifacts",
        "hardware_profile",
        "verifier_bundles",
        "reduction_claims",
        "safety",
        "privacy",
        "manifest_hash",
    }
    missing = sorted(required - set(manifest))
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
    if manifest.get("beast_object_type") != "beast_compute_space":
        errors.append("invalid beast_object_type")
    expected_hash_payload = dict(manifest)
    expected_hash_payload["manifest_hash"] = ""
    expected_hash = _sha256_bytes(canonical_bytes(expected_hash_payload))
    if manifest.get("manifest_hash") != expected_hash:
        errors.append("manifest hash mismatch")
    for item in manifest.get("artifacts") or []:
        try:
            rel = _relative_path(str(item.get("path") or ""))
            path = (root / rel).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                errors.append(f"missing artifact: {rel}")
                continue
            if _sha256_bytes(path.read_bytes()) != item.get("sha256"):
                errors.append(f"artifact hash mismatch: {rel}")
            findings = _privacy_scan(path)
            if findings:
                errors.append(f"privacy scan failed: {rel} ({', '.join(findings)})")
        except ValueError as exc:
            errors.append(str(exc))
    privacy = manifest.get("privacy") or {}
    if not privacy.get("local_only"):
        errors.append("Space must be local_only")
    for field in ("contains_raw_prompts", "contains_secrets", "contains_private_paths", "contains_source_code"):
        if privacy.get(field) is not False:
            errors.append(f"privacy.{field} must be false")
    return {
        "beast_object_type": "beast_compute_space_validation",
        "version": SPACE_VERSION,
        "space_id": manifest.get("space_id"),
        "valid": not errors,
        "errors": errors,
        "artifact_count": len(manifest.get("artifacts") or []),
    }


def build_reduction_receipt(
    *,
    space_manifest: Dict[str, Any],
    baseline_route: Dict[str, Any],
    optimized_route: Dict[str, Any],
    displacement: Dict[str, Any],
    verifier: Dict[str, Any],
    resource_deltas: Dict[str, Any],
    provenance: Dict[str, Any],
    rollback_available: bool,
    approval_required: bool,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "beast_object_type": "compute_reduction_receipt",
        "version": RECEIPT_VERSION,
        "receipt_id": "",
        "space_id": space_manifest["space_id"],
        "space_manifest_hash": space_manifest["manifest_hash"],
        "created_at": created_at or _utc_now(),
        "baseline_route": baseline_route,
        "optimized_route": optimized_route,
        "displacement": displacement,
        "resource_deltas": resource_deltas,
        "verifier": verifier,
        "rollback_available": rollback_available,
        "approval_required": approval_required,
        "privacy_policy": "local_only_fingerprints_no_raw_workspace_data",
        "provenance": provenance,
        "fingerprint_hash": "",
    }
    payload["fingerprint_hash"] = _sha256_bytes(canonical_bytes(payload))
    payload["receipt_id"] = "space_receipt_" + payload["fingerprint_hash"].split(":", 1)[1][:20]
    seal_payload = dict(payload)
    payload["local_seal"] = seal_crystal_payload(
        seal_payload,
        purpose="beast_compute_reduction_receipt",
    )
    return payload


def validate_reduction_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    seal = receipt.get("local_seal") or {}
    payload = dict(receipt)
    payload.pop("local_seal", None)
    seal_result = verify_crystal_seal(payload, seal)
    fingerprint_payload = dict(payload)
    fingerprint_payload["fingerprint_hash"] = ""
    fingerprint_payload["receipt_id"] = ""
    expected = _sha256_bytes(canonical_bytes(fingerprint_payload))
    fingerprint_ok = payload.get("fingerprint_hash") == expected
    return {
        "beast_object_type": "compute_reduction_receipt_validation",
        "version": RECEIPT_VERSION,
        "receipt_id": receipt.get("receipt_id"),
        "fingerprint_ok": fingerprint_ok,
        "seal": seal_result,
        "valid": bool(fingerprint_ok and seal_result.get("verified")),
    }


def render_reduction_receipt_markdown(receipt: Dict[str, Any]) -> str:
    displacement = receipt.get("displacement") or {}
    verifier = receipt.get("verifier") or {}
    resources = receipt.get("resource_deltas") or {}
    return "\n".join([
        f"# Compute Reduction Receipt: {receipt.get('space_id', '')}",
        "",
        f"- Receipt: `{receipt.get('receipt_id', '')}`",
        f"- Baseline route: `{(receipt.get('baseline_route') or {}).get('route_id', '')}`",
        f"- Optimized route: `{(receipt.get('optimized_route') or {}).get('route_id', '')}`",
        f"- Provider calls avoided: `{displacement.get('provider_calls_avoided')}`",
        f"- Tokens avoided: `{displacement.get('tokens_avoided')}`",
        f"- Optimized latency: `{(receipt.get('optimized_route') or {}).get('latency_ms')} ms`",
        f"- GPU avoided: `{resources.get('gpu_avoided')}`",
        f"- Verifier passed: `{verifier.get('passed')}`",
        f"- Evidence class: `{displacement.get('evidence_class')}`",
        f"- Local seal: `{(receipt.get('local_seal') or {}).get('payload_hash', '')}`",
        "",
        "Claims marked counterfactual or unknown are not treated as observed savings.",
        "",
    ])


def write_space(root: Path, manifest: Dict[str, Any], receipt: Optional[Dict[str, Any]] = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if receipt:
        (root / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (root / RECEIPT_MARKDOWN_NAME).write_text(render_reduction_receipt_markdown(receipt), encoding="utf-8")


def export_space(root: Path, destination: Path) -> Dict[str, Any]:
    manifest = _read_json(root / MANIFEST_NAME)
    validation = validate_manifest(root, manifest)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    included = [MANIFEST_NAME, RECEIPT_NAME, RECEIPT_MARKDOWN_NAME]
    included.extend(item["path"] for item in manifest["artifacts"])
    included = list(dict.fromkeys(rel for rel in included if (root / rel).is_file()))
    privacy = CommonsPrivacyScrubber().scan_space(root, included)
    if not privacy["safe"]:
        raise ValueError("bundle privacy scan failed: " + json.dumps(privacy["findings"], sort_keys=True))
    bundle_manifest = {
        "beast_object_type": "beast_content_addressed_space_bundle",
        "version": SPACE_VERSION,
        "bundle_id": "",
        "space_id": manifest["space_id"],
        "space_manifest_hash": manifest["manifest_hash"],
        "entries": [
            {
                "path": rel,
                "sha256": _sha256_bytes((root / rel).read_bytes()),
                "bytes": (root / rel).stat().st_size,
            }
            for rel in sorted(included)
        ],
        "privacy_scan": {
            "safe": True,
            "files_scanned": privacy["files_scanned"],
        },
    }
    bundle_manifest["bundle_id"] = "bundle_" + hashlib.sha256(canonical_bytes(bundle_manifest)).hexdigest()
    seal_payload = dict(bundle_manifest)
    bundle_manifest["seal"] = seal_crystal_payload(seal_payload, purpose="beast_content_addressed_space_bundle")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in included:
            path = root / rel
            archive.write(path, arcname=rel)
        archive.writestr(BUNDLE_MANIFEST_NAME, json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n")
    return {
        "beast_object_type": "beast_compute_space_export",
        "version": SPACE_VERSION,
        "space_id": manifest["space_id"],
        "local_only": True,
        "path": str(destination),
        "bundle_id": bundle_manifest["bundle_id"],
        "entry_count": len(included),
        "privacy_scan": privacy,
        "sha256": _sha256_bytes(destination.read_bytes()),
    }


def import_space(bundle: Path, destination_root: Path, *, approved: bool, dry_run: bool = True) -> Dict[str, Any]:
    privacy = CommonsPrivacyScrubber().scan_bundle(bundle)
    if not privacy["safe"]:
        reasons = {item.get("reason") for item in privacy["findings"]}
        prefix = "bundle paths must be local and relative; " if "unsafe_archive_path" in reasons else ""
        raise ValueError(prefix + "bundle privacy or safety scan failed: " + json.dumps(privacy["findings"], sort_keys=True))
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        for name in names:
            _relative_path(name)
        if MANIFEST_NAME not in names:
            raise ValueError(f"bundle is missing {MANIFEST_NAME}")
        if BUNDLE_MANIFEST_NAME not in names:
            raise ValueError(f"bundle is missing {BUNDLE_MANIFEST_NAME}")
        bundle_manifest = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
        seal_payload = dict(bundle_manifest)
        seal = seal_payload.pop("seal", {})
        seal_validation = verify_crystal_seal(seal_payload, seal)
        if not seal_validation["verified"]:
            raise ValueError("bundle manifest signature did not verify")
        declared = {str(item.get("path") or ""): item for item in bundle_manifest.get("entries") or []}
        actual = set(names) - {BUNDLE_MANIFEST_NAME}
        if set(declared) != actual:
            raise ValueError("bundle entries do not match the content manifest")
        for rel, item in declared.items():
            body = archive.read(rel)
            if _sha256_bytes(body) != item.get("sha256") or len(body) != item.get("bytes"):
                raise ValueError(f"bundle entry integrity failed: {rel}")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        space_id = str(manifest.get("space_id") or "")
        target = destination_root / space_id
        result = {
            "beast_object_type": "beast_compute_space_import",
            "version": SPACE_VERSION,
            "space_id": space_id,
            "approved": approved,
            "dry_run": dry_run,
            "target": str(target),
            "imported": False,
            "bundle_id": bundle_manifest.get("bundle_id"),
            "bundle_validation": {
                "content_addressed": True,
                "signature": seal_validation,
                "entries_valid": True,
                "privacy": privacy,
            },
        }
        if dry_run or not approved:
            result["reason"] = "dry_run" if dry_run else "approval_required"
            return result
        if target.exists():
            existing_manifest = target / MANIFEST_NAME
            if existing_manifest.is_file():
                try:
                    existing_hash = _read_json(existing_manifest).get("manifest_hash")
                except (OSError, ValueError, json.JSONDecodeError):
                    existing_hash = None
                if existing_hash == manifest.get("manifest_hash"):
                    result["duplicate"] = True
                    result["reason"] = "space_already_imported_same_manifest_hash"
                    return result
            raise ValueError(f"Space already exists with different content: {target}")
        target.mkdir(parents=True)
        archive.extractall(target)
    validation = validate_manifest(target, _read_json(target / MANIFEST_NAME))
    if not validation["valid"]:
        shutil.rmtree(target)
        raise ValueError("; ".join(validation["errors"]))
    result["imported"] = True
    result["validation"] = validation
    return result


def package_tiny_llama_case(source: Path, destination: Path) -> Dict[str, Any]:
    report = _read_json(source / "opus_case_report.json")
    destination.mkdir(parents=True, exist_ok=True)
    subsystems = report.get("subsystems") if isinstance(report.get("subsystems"), dict) else {}
    patch_result = subsystems.get("patch_result") if isinstance(subsystems.get("patch_result"), dict) else {}
    optimized = report.get("verification") or subsystems.get("verification") or {}
    task = report.get("task") if isinstance(report.get("task"), dict) else {}
    derived = {
        "prompt_fingerprint.json": {
            "beast_object_type": "space_prompt_fingerprint",
            "version": "1.0",
            "task_id": task.get("task_id") or "opus_case_gateway_repair",
            "task_class": task.get("task_class") or "hard_gateway_repair",
            "task_hash": (report.get("receipts") or {}).get("task_hash"),
            "raw_prompt_exported": False,
        },
        "patch_plan.json": {
            "beast_object_type": "space_patch_plan_receipt",
            "version": "1.0",
            "files_changed": patch_result.get("files_changed") or [],
            "before_hash": patch_result.get("before_hash"),
            "after_hash": patch_result.get("after_hash"),
            "patch_hash": patch_result.get("patch_hash"),
            "source_code_exported": False,
        },
        "verifier_results.json": {
            "beast_object_type": "space_verifier_result",
            "version": "1.0",
            "command": ["python", "-m", "pytest", "tests", "-q"],
            "passed": bool(optimized.get("passed")),
            "returncode": optimized.get("returncode"),
            "latency_ms": optimized.get("latency_ms"),
            "stdout_hash": "sha256:" + hashlib.sha256(str(optimized.get("stdout_tail") or "").encode()).hexdigest(),
            "stderr_hash": "sha256:" + hashlib.sha256(str(optimized.get("stderr_tail") or "").encode()).hexdigest(),
            "raw_output_exported": False,
        },
        "rollback_receipt.json": {
            "beast_object_type": "space_rollback_receipt",
            "version": "1.0",
            "available": bool(patch_result.get("before_hash")),
            "restore_fingerprint": patch_result.get("before_hash"),
            "post_patch_fingerprint": patch_result.get("after_hash"),
            "approval_receipt": (report.get("receipts") or {}).get("approval_receipt"),
            "raw_snapshot_exported": False,
        },
        "promotion_candidate.json": subsystems.get("promotion_candidate") or {},
        "commons_evidence.json": subsystems.get("commons_rank") or {},
    }
    for rel, payload in derived.items():
        (destination / rel).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selected = {
        "README.md": "case_study_summary",
        "prompt_fingerprint.json": "prompt_fingerprint",
        "normalized_orchestration_plan.json": "orchestration_plan",
        "patch_plan.json": "patch_plan",
        "verifier_results.json": "verifier_result",
        "rollback_receipt.json": "rollback_receipt",
        "promotion_candidate.json": "promotion_candidate",
        "commons_evidence.json": "commons_evidence",
        "receipts.json": "lineage_receipts",
    }
    for rel in selected.keys() - derived.keys():
        shutil.copy2(source / rel, destination / rel)
    manifest = build_manifest(
        destination,
        space_id="tiny_llama_opus_gateway_repair",
        name="Tiny Llama Opus Gateway Repair",
        task_class="hard_gateway_repair",
        artifacts=[{"path": path, "artifact_type": kind} for path, kind in selected.items()],
        hardware_profile={
            "execution_class": "cpu_only_local",
            "local_model": (report.get("live_ollama") or {}).get("model"),
            "gpu_required": False,
            "ram_bytes": None,
            "disk_bytes": None,
        },
        verifier_bundles=[{
            "bundle_id": "gateway_pytest",
            "commands": ["python -m pytest tests -q"],
            "expected_returncode": 0,
            "artifact_scope": "isolated_case_repo",
        }],
        reduction_claims={
            "cloud_calls_avoided": 1,
            "cloud_calls_evidence": "counterfactual_no_cloud_route",
            "tokens_avoided": None,
            "gpu_avoided": True,
            "capability_preserved": bool(report.get("passed")),
        },
        safety={
            "risk": "high",
            "approval_required": True,
            "rollback_required": True,
            "promotion_state": "candidate",
            "adoption_mode": "advisory",
        },
        lineage={
            "case_study": "tiny_llama_opus_case_study_qwen25_05b",
            "promotion_candidate_id": (report.get("receipts") or {}).get("promotion_candidate_id"),
            "source_report_hash": report.get("report_hash"),
        },
        created_at=report.get("generated_at"),
    )
    baseline = report.get("baseline") or {}
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={
            "route_id": "unassisted_local_baseline",
            "provider": "local_python",
            "model": None,
            "status": "failed",
            "provider_calls": 0,
            "tokens": None,
            "latency_ms": baseline.get("latency_ms"),
        },
        optimized_route={
            "route_id": "tiny_local_model_beast_orchestration",
            "provider": "ollama",
            "model": (report.get("live_ollama") or {}).get("model"),
            "status": "verified",
            "provider_calls": 1,
            "cloud_provider_calls": 0,
            "tokens": None,
            "latency_ms": round(
                float((report.get("live_ollama") or {}).get("latency_ms") or 0)
                + float(optimized.get("latency_ms") or 0),
                3,
            ),
        },
        displacement={
            "provider_calls_avoided": 1,
            "tokens_avoided": None,
            "latency_avoided_ms": None,
            "evidence_class": "mixed_observed_and_counterfactual",
            "counterfactual": True,
            "notes": "No cloud call was used. One avoided cloud escalation is a route-policy counterfactual, not a metered baseline call.",
        },
        verifier={
            "passed": bool(optimized.get("passed")),
            "returncode": optimized.get("returncode"),
            "command": optimized.get("command"),
            "latency_ms": optimized.get("latency_ms"),
        },
        resource_deltas={
            "gpu_avoided": True,
            "ram_bytes_delta": None,
            "disk_bytes_delta": None,
            "network_bytes_avoided": None,
            "measurement_status": "gpu_observed_other_resources_unknown",
        },
        provenance={
            "case_study_report_hash": report.get("report_hash"),
            "approval_receipt": (report.get("receipts") or {}).get("approval_receipt"),
            "patch_hash": (report.get("receipts") or {}).get("patch_hash"),
            "verification_receipt": (report.get("receipts") or {}).get("receipt_hash"),
        },
        rollback_available=True,
        approval_required=True,
        created_at=report.get("generated_at"),
    )
    write_space(destination, manifest, receipt)
    return {
        "beast_object_type": "beast_compute_space_package",
        "version": SPACE_VERSION,
        "space_id": manifest["space_id"],
        "path": str(destination),
        "manifest": validate_manifest(destination, manifest),
        "receipt": validate_reduction_receipt(receipt),
    }
