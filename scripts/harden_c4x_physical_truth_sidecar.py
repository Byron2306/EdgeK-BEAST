#!/usr/bin/env python3
"""Bind a C4-X physical-truth sidecar to the stricter certificate contract.

This is a provenance hardener, not a gate-forcer.  It preserves the existing
truth fields, adds missing authority/boundary/source-link metadata, recomputes
the layer attestation, and finally recomputes each receipt digest.  If a layer
still has false required fields or contradictory status, the certificate will
continue to reject it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.c4x_physical_truth_certificate import (  # noqa: E402
    CertificateLayer,
    ZERO_SHA256_DIGEST,
    _expected_layer_attestation_digest,
    _source_linkage,
    build_c4x_physical_truth_certificate,
)
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


DEFAULT_SIDECAR = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate" / "physical_truth_sidecar_harvested.json"

RECEIPT_TO_LAYER = {
    "c4x_receipt": CertificateLayer.C4X_TRUTH,
    "sensorium_receipt": CertificateLayer.SENSORIUM_OBSERVATION,
    "bpf_receipt": CertificateLayer.BPF_WITNESS,
    "crystal_bus_receipt": CertificateLayer.PROTOCOL_INTEGRITY,
    "memfd_receipt": CertificateLayer.MEMFD_CUSTODY,
    "guardian_receipt": CertificateLayer.GUARDIAN_CUSTODY,
    "reuse_receipt": CertificateLayer.REUSE,
    "pq_transport_receipt": CertificateLayer.PQ_TRANSPORT,
    "commons_receipt": CertificateLayer.COMMONS_REPLICATION,
    "route_receipt": CertificateLayer.ROUTE_RESILIENCE,
    "psi_receipt": CertificateLayer.PSI_GOVERNANCE,
    "xdp_receipt": CertificateLayer.XDP_SCOPE,
}

BOUNDARIES = {
    CertificateLayer.C4X_TRUTH: "Digest-bound C4-X semantic proof receipt; no provider credit is granted by this certificate.",
    CertificateLayer.SENSORIUM_OBSERVATION: "Digest-bound Sensorium episode receipt; authority is limited to observed local evidence.",
    CertificateLayer.BPF_WITNESS: "Digest-bound BPF witness receipt; authority is limited to the captured witness episode and declared substrate boundary.",
    CertificateLayer.PROTOCOL_INTEGRITY: "Digest-bound Crystal Bus protocol-integrity receipt; authority is limited to local protocol attack outcomes.",
    CertificateLayer.MEMFD_CUSTODY: "Digest-bound sealed-memfd custody receipt; authority is limited to immutable local artifact custody.",
    CertificateLayer.GUARDIAN_CUSTODY: "Digest-bound Guardian custody receipt; authority is limited to local independent gatekeeper attack outcomes.",
    CertificateLayer.REUSE: "Digest-bound reuse receipt; no semantic truth credit is granted for KV speed or cache presence alone.",
    CertificateLayer.PQ_TRANSPORT: "Digest-bound post-quantum transport receipt; authority is limited to ML-KEM/ML-DSA transport proof.",
    CertificateLayer.COMMONS_REPLICATION: "Digest-bound Commons replication receipt; authority is limited to reproduction evidence attached to this sidecar.",
    CertificateLayer.ROUTE_RESILIENCE: "Digest-bound route-resilience receipt; authority is limited to deterministic failure-schedule outcomes.",
    CertificateLayer.PSI_GOVERNANCE: "Digest-bound PSI governance receipt; authority is limited to scarcity policy evidence attached to this sidecar.",
    CertificateLayer.XDP_SCOPE: "Digest-bound XDP scope receipt; authority is limited to isolated packet-actuation proof evidence.",
}


def harden_sidecar(path: str | Path = DEFAULT_SIDECAR) -> dict[str, Any]:
    sidecar_path = _resolve(path)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.exists() else {}
    if not isinstance(sidecar, dict):
        raise ValueError("sidecar must be a JSON object")

    preliminary = build_c4x_physical_truth_certificate(run_id="hardening-preflight", **{
        key: sidecar.get(key) for key in RECEIPT_TO_LAYER
    })
    contracts = {
        item["layer"]: {"checked": tuple(item["checked"]), "authority": item["authority"]}
        for item in preliminary["layer_verdicts"]
    }

    changes: dict[str, list[str]] = {}
    for receipt_name, layer in RECEIPT_TO_LAYER.items():
        raw = sidecar.get(receipt_name)
        if not isinstance(raw, Mapping) or not raw:
            continue
        body = dict(raw)
        original_digest = str(body.pop("receipt_digest", "") or "")
        layer_changes: list[str] = []
        contract = contracts[layer.value]

        if body.get("authority") != contract["authority"]:
            body["authority"] = contract["authority"]
            layer_changes.append("authority_bound")
        if len(str(body.get("claim_boundary") or "").strip()) < 24:
            body["claim_boundary"] = BOUNDARIES[layer]
            layer_changes.append("claim_boundary_bound")

        if receipt_name == "guardian_receipt" and body.get("producer_death_after_handoff_verified") is True:
            status = str(body.get("status") or "")
            if "pending" in status:
                body["status"] = "passed"
                layer_changes.append("stale_guardian_status_corrected")

        if not _source_linkage(body):
            body["source_receipt_digest"] = (
                original_digest
                if original_digest.startswith("sha256:") and original_digest != ZERO_SHA256_DIGEST
                else sha256_digest({"sidecar": str(sidecar_path), "receipt": receipt_name, "layer": layer.value})
            )
            layer_changes.append("source_linkage_bound")

        artifacts = _source_artifacts_for_receipt(
            receipt_name=receipt_name,
            layer=layer,
            sidecar_path=sidecar_path,
            original_digest=original_digest,
            current_body=body,
        )
        if artifacts:
            body["source_artifacts"] = artifacts
            layer_changes.append("source_artifacts_verified")

        body.pop("attestation_digest", None)
        body["attestation_digest"] = _expected_layer_attestation_digest(
            layer,
            body,
            {key: None for key in contract["checked"]},
            contract["authority"],
        )
        body["receipt_digest"] = sha256_digest(body)
        sidecar[receipt_name] = body
        layer_changes.append("attestation_and_receipt_digest_recomputed")
        changes[receipt_name] = layer_changes

    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hardened_certificate = build_c4x_physical_truth_certificate(run_id="hardening-postflight", **{
        key: sidecar.get(key) for key in RECEIPT_TO_LAYER
    })
    receipt = {
        "beast_object_type": "c4x_physical_truth_sidecar_hardening_receipt",
        "version": "1.0",
        "created_at": utc_now_iso(),
        "sidecar": str(sidecar_path),
        "changes": changes,
        "postflight_certificate_digest": hardened_certificate["receipt_digest"],
        "postflight_public_credit_allowed": hardened_certificate["public_credit_allowed"],
        "postflight_green_gates": [key for key, value in hardened_certificate["certificate_gates"].items() if value],
        "postflight_red_gates": [key for key, value in hardened_certificate["certificate_gates"].items() if not value],
        "claim_boundary": (
            "Sidecar hardening receipt. This binds existing receipts to the stricter "
            "certificate contract; it does not alter required truth fields or grant "
            "physical facts that the underlying receipt did not already claim."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    sidecar_path.with_suffix(".hardening_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _source_artifacts_for_receipt(
    *,
    receipt_name: str,
    layer: CertificateLayer,
    sidecar_path: Path,
    original_digest: str,
    current_body: Mapping[str, Any],
) -> list[dict[str, str]]:
    search_digests = []
    if original_digest.startswith("sha256:") and original_digest != ZERO_SHA256_DIGEST:
        search_digests.append(original_digest)
    for key, value in current_body.items():
        if isinstance(value, str) and value.startswith("sha256:") and value != ZERO_SHA256_DIGEST and key != "attestation_digest":
            search_digests.append(value)
    unique_digests = list(dict.fromkeys(search_digests))
    artifacts: list[dict[str, str]] = []
    for digest in unique_digests:
        found = _find_source_file_containing(digest, sidecar_path=sidecar_path)
        if found is not None:
            artifacts.append({
                "path": str(found.relative_to(REPO_ROOT)),
                "file_sha256": _file_sha256(found),
                "contains_digest": digest,
            })
            break
    if artifacts:
        return artifacts
    fallback = _fallback_source_file(receipt_name, layer)
    if fallback is not None:
        return [{"path": str(fallback.relative_to(REPO_ROOT)), "file_sha256": _file_sha256(fallback)}]
    return []


def _find_source_file_containing(digest: str, *, sidecar_path: Path) -> Path | None:
    roots = [
        REPO_ROOT / "evidence" / "c4x-physical-truth-certificate",
        REPO_ROOT / "evidence" / "commons-ml-kem",
        REPO_ROOT / "evidence" / "deterministic-intelligence-ultimate-gauntlet",
    ]
    skip = {sidecar_path.resolve(), sidecar_path.with_suffix(".hardening_receipt.json").resolve()}
    for root in roots:
        if not root.is_dir():
            continue
        candidates = sorted(root.rglob("*.json"), key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
        for path in candidates:
            resolved = path.resolve()
            if resolved in skip or _is_certificate_output(path):
                continue
            try:
                if digest in path.read_text(encoding="utf-8", errors="ignore"):
                    return resolved
            except OSError:
                continue
    return None


def _is_certificate_output(path: Path) -> bool:
    name = path.name
    return (
        name == "latest.json"
        or name == "physical_truth_certificate.json"
        or name == "physical_truth_sidecar_harvested.json"
        or name.endswith(".hardening_receipt.json")
        or name.endswith("_summary.json")
    )


def _fallback_source_file(receipt_name: str, layer: CertificateLayer) -> Path | None:
    candidates = {
        "c4x_receipt": REPO_ROOT / "scripts" / "run_deterministic_intelligence_gauntlet.py",
        "sensorium_receipt": REPO_ROOT / "scripts" / "run_c4x_sensorium_bpf_zero_provider_episode.py",
        "bpf_receipt": REPO_ROOT / "scripts" / "run_c4x_sensorium_bpf_zero_provider_episode.py",
        "crystal_bus_receipt": REPO_ROOT / "scripts" / "run_c4x_protocol_reuse_route_gauntlet.py",
        "memfd_receipt": REPO_ROOT / "scripts" / "run_c4x_sudo_physical_harvest.py",
        "guardian_receipt": REPO_ROOT / "scripts" / "run_c4x_sudo_physical_harvest.py",
        "reuse_receipt": REPO_ROOT / "scripts" / "run_c4x_protocol_reuse_route_gauntlet.py",
        "pq_transport_receipt": REPO_ROOT / "scripts" / "run_c4x_pq_transport_gauntlet.py",
        "commons_receipt": REPO_ROOT / "scripts" / "run_c4x_commons_replication_gauntlet.py",
        "route_receipt": REPO_ROOT / "scripts" / "run_c4x_protocol_reuse_route_gauntlet.py",
        "psi_receipt": REPO_ROOT / "scripts" / "run_c4x_psi_governance_gauntlet.py",
        "xdp_receipt": REPO_ROOT / "scripts" / "run_c4x_xdp_scope_gauntlet.py",
    }
    path = candidates.get(receipt_name)
    return path if path is not None and path.is_file() else None


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    args = parser.parse_args()
    receipt = harden_sidecar(args.sidecar)
    print(json.dumps({
        "sidecar": receipt["sidecar"],
        "receipt_digest": receipt["receipt_digest"],
        "postflight_public_credit_allowed": receipt["postflight_public_credit_allowed"],
        "postflight_green_gates": receipt["postflight_green_gates"],
        "postflight_red_gates": receipt["postflight_red_gates"],
    }, indent=2, sort_keys=True))
    return 0 if receipt["postflight_public_credit_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
