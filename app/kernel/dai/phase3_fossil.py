"""Operational Phase-3 fossil registry.

Phase 3 starts by treating Phase-2 as an archaeological artifact, not live
mutable code.  A fossil may be referenced by later composition experiments only
if its release manifest, file manifest, exact summary digest, authority
boundary and optional ZIP digest verify.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)


PHASE3_FOSSIL_VERSION = "2026-08-04.phase3.fossil.v1"
PHASE2_RELEASE_ID = "DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04"
PHASE2_EXPECTED_SUMMARY_DIGEST = "sha256:33f5ecc2762faa364ca7c8b8c86288d72ca36a5373aefc13a65147d5fd9f7c44"
PHASE2_EXPECTED_AUTHORITY = "exact_phase2_cgroup_kernel_witness"
PHASE2_FORBIDDEN_FAILURE_FILE = "x2_exact_ring_failure.json"


class Phase3FossilError(ValueError):
    """Raised when a Phase-2 artifact cannot enter Phase-3 composition."""


@dataclass(frozen=True, slots=True)
class Phase3CapabilityFossil:
    beast_object_type: str
    version: str
    fossil_id: str
    release_id: str
    bundle_path: str
    release_manifest_digest: str
    file_manifest_digest: str
    summary_digest: str
    exact_kernel_events_receipt_digest: str
    sensorium_authority_level: str
    correlated_socket_bind_event_count: int
    provider_calls_used: int
    production_authority_allowed: bool
    zip_path: str = ""
    zip_digest: str = ""
    maximum_authority: str = "frozen_capability_reference_only"

    def __post_init__(self) -> None:
        for field_name in (
            "release_manifest_digest",
            "file_manifest_digest",
            "summary_digest",
            "exact_kernel_events_receipt_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.zip_digest:
            require_digest(self.zip_digest, field_name="zip_digest")
        if self.release_id != PHASE2_RELEASE_ID:
            raise Phase3FossilError("unexpected Phase-2 release identity")
        if self.summary_digest != PHASE2_EXPECTED_SUMMARY_DIGEST:
            raise Phase3FossilError("unexpected Phase-2 summary digest")
        if self.sensorium_authority_level != PHASE2_EXPECTED_AUTHORITY:
            raise Phase3FossilError("Phase-2 fossil lacks exact Sensorium authority")
        if self.correlated_socket_bind_event_count != 3:
            raise Phase3FossilError("Phase-2 fossil must bind exactly three socket events")
        if self.provider_calls_used != 0:
            raise Phase3FossilError("Phase-2 fossil must be zero-provider")
        if self.production_authority_allowed:
            raise Phase3FossilError("Phase-2 fossil must not grant production authority")
        if self.maximum_authority != "frozen_capability_reference_only":
            raise Phase3FossilError("Phase-3 fossils cannot grant execution authority")

    @property
    def fossil_digest(self) -> str:
        return sha256_digest(self)


def load_phase2_exact_fossil(bundle_path: str | Path, *, zip_path: str | Path | None = None) -> Phase3CapabilityFossil:
    """Verify and load the frozen Phase-2 exact X2 proof as a Phase-3 fossil."""

    bundle = Path(bundle_path).expanduser().resolve()
    if not bundle.is_dir():
        raise Phase3FossilError(f"Phase-2 bundle directory is missing: {bundle}")

    release_manifest = _read_json(bundle / "RELEASE_MANIFEST.json")
    file_manifest = _read_json(bundle / "SHA256_MANIFEST.json")
    _verify_release_manifest(release_manifest)
    _verify_file_manifest(bundle, file_manifest)

    summary = _summary_from_bundle(bundle)
    if summary != release_manifest.get("summary"):
        raise Phase3FossilError("release manifest summary does not match preserved summary file")
    _verify_phase2_summary(summary)

    forbidden = list(bundle.rglob(PHASE2_FORBIDDEN_FAILURE_FILE))
    if forbidden:
        raise Phase3FossilError("Phase-2 fossil contains stale failure diagnostics")

    zip_digest = ""
    zip_text = ""
    if zip_path is not None:
        zip_source = Path(zip_path).expanduser().resolve()
        if not zip_source.is_file():
            raise Phase3FossilError(f"Phase-2 ZIP is missing: {zip_source}")
        zip_digest = sha256_bytes(zip_source.read_bytes())
        zip_text = str(zip_source)

    return Phase3CapabilityFossil(
        beast_object_type="dai_phase3_capability_fossil",
        version=PHASE3_FOSSIL_VERSION,
        fossil_id="phase3:fossil:phase2-stale-listener-exact-x2:2026-08-04",
        release_id=str(release_manifest["release_id"]),
        bundle_path=str(bundle),
        release_manifest_digest=str(release_manifest["release_manifest_digest"]),
        file_manifest_digest=str(file_manifest["manifest_digest"]),
        summary_digest=str(summary["summary_digest"]),
        exact_kernel_events_receipt_digest=str(summary["x2_exact_kernel_events_receipt_digest"]),
        sensorium_authority_level=str(summary["sensorium_bpf_authority_level"]),
        correlated_socket_bind_event_count=int(summary["correlated_socket_bind_event_count"]),
        provider_calls_used=int(summary["provider_calls_used"]),
        production_authority_allowed=bool(summary["production_authority_allowed"]),
        zip_path=zip_text,
        zip_digest=zip_digest,
    )


def phase3_fossil_receipt(fossil: Phase3CapabilityFossil) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "dai_phase3_capability_fossil_receipt",
        "version": PHASE3_FOSSIL_VERSION,
        "fossil_id": fossil.fossil_id,
        "fossil_digest": fossil.fossil_digest,
        "release_id": fossil.release_id,
        "summary_digest": fossil.summary_digest,
        "zip_digest": fossil.zip_digest,
        "maximum_authority": fossil.maximum_authority,
        "composition_use_allowed": True,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def write_phase3_fossil_receipt(path: str | Path, fossil: Phase3CapabilityFossil) -> dict[str, Any]:
    receipt = phase3_fossil_receipt(fossil)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def _verify_phase2_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("beast_object_type") != "dai_phase2_x2_exact_ring_summary":
        raise Phase3FossilError("unexpected Phase-2 summary object type")
    if summary.get("summary_digest") != PHASE2_EXPECTED_SUMMARY_DIGEST:
        raise Phase3FossilError("Phase-2 summary digest mismatch")
    if summary.get("green") is not True:
        raise Phase3FossilError("Phase-2 summary is not green")
    if summary.get("sensorium_exact_phase2_kernel_events_bound") is not True:
        raise Phase3FossilError("Phase-2 exact kernel events are not bound")
    if summary.get("sensorium_bpf_authority_level") != PHASE2_EXPECTED_AUTHORITY:
        raise Phase3FossilError("Phase-2 summary authority mismatch")
    if summary.get("correlated_socket_bind_event_count") != 3:
        raise Phase3FossilError("Phase-2 summary must include three bind events")
    if summary.get("provider_calls_used") != 0:
        raise Phase3FossilError("Phase-2 summary must be zero-provider")
    if summary.get("production_authority_allowed") is not False:
        raise Phase3FossilError("Phase-2 summary must not grant production authority")


def _verify_release_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("release_id") != PHASE2_RELEASE_ID:
        raise Phase3FossilError("release manifest identity mismatch")
    claimed = str(manifest.get("release_manifest_digest") or "")
    require_digest(claimed, field_name="release_manifest_digest")
    body = dict(manifest)
    body.pop("release_manifest_digest", None)
    recomputed = sha256_digest(body)
    if recomputed != claimed:
        raise Phase3FossilError("release manifest digest does not recompute")
    if manifest.get("expected_summary_digest") != PHASE2_EXPECTED_SUMMARY_DIGEST:
        raise Phase3FossilError("release manifest expected summary digest mismatch")
    authority = manifest.get("authority_boundary")
    if not isinstance(authority, Mapping):
        raise Phase3FossilError("release manifest authority boundary missing")
    if authority.get("production_authority_allowed") is not False:
        raise Phase3FossilError("release manifest grants production authority")
    if authority.get("provider_calls_used") != 0:
        raise Phase3FossilError("release manifest provider boundary mismatch")


def _verify_file_manifest(bundle: Path, manifest: Mapping[str, Any]) -> None:
    if manifest.get("release_id") != PHASE2_RELEASE_ID:
        raise Phase3FossilError("file manifest release identity mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise Phase3FossilError("file manifest has no entries")
    claimed = str(manifest.get("manifest_digest") or "")
    require_digest(claimed, field_name="file_manifest_digest")
    recomputed = sha256_digest(entries)
    if recomputed != claimed:
        raise Phase3FossilError("file manifest digest does not recompute")
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise Phase3FossilError("file manifest entry must be an object")
        rel = str(entry.get("path") or "")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise Phase3FossilError("unsafe file manifest path")
        digest = str(entry.get("sha256") or "")
        require_digest(digest, field_name="file_manifest_entry_sha256")
        path = bundle / rel
        if not path.is_file():
            raise Phase3FossilError(f"file manifest entry missing: {rel}")
        if sha256_bytes(path.read_bytes()) != digest:
            raise Phase3FossilError(f"file manifest digest mismatch: {rel}")


def _summary_from_bundle(bundle: Path) -> dict[str, Any]:
    return _read_json(
        bundle
        / "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring/phase2_x2_exact_ring_summary.json"
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Phase3FossilError(f"missing JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise Phase3FossilError(f"JSON artifact must be an object: {path}")
    return payload
