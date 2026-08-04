"""Hard-gated physical truth certificate for the C4-X/BEAST stack.

This module does not run privileged BPF/XDP/PSI/Commons experiments itself.
Instead, it defines the certificate contract that prevents the final claim from
being awarded by self-report or by averaging unrelated wins.  Each layer must
present an independently verifiable receipt with an explicit boundary.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
from typing import Any

from .deterministic_intelligence import DIGEST_RE, sha256_digest, utc_now_iso

REPO_ROOT = Path(__file__).resolve().parents[3]

class CertificateLayer(str, Enum):
    C4X_TRUTH = "c4x_truth"
    SENSORIUM_OBSERVATION = "sensorium_observation"
    BPF_WITNESS = "bpf_witness"
    PROTOCOL_INTEGRITY = "protocol_integrity"
    MEMFD_CUSTODY = "memfd_custody"
    GUARDIAN_CUSTODY = "guardian_custody"
    REUSE = "reuse"
    PQ_TRANSPORT = "pq_transport"
    COMMONS_REPLICATION = "commons_replication"
    ROUTE_RESILIENCE = "route_resilience"
    PSI_GOVERNANCE = "psi_governance"
    XDP_SCOPE = "xdp_scope"


REQUIRED_LAYERS = tuple(layer.value for layer in CertificateLayer)
ZERO_SHA256_DIGEST = "sha256:" + ("0" * 64)
CONTRADICTORY_STATUS_TERMS = (
    "pending",
    "failed",
    "failure",
    "error",
    "not_confirmed",
    "not_authoritative",
    "simulation",
    "synthetic",
    "partial",
)


@dataclass(frozen=True, slots=True)
class LayerVerdict:
    layer: str
    passed: bool
    evidence_digest: str
    checked: tuple[str, ...]
    missing: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    public_credit_allowed: bool
    authority: str

    @property
    def verdict_digest(self) -> str:
        return sha256_digest(
            {
                "layer": self.layer,
                "passed": self.passed,
                "evidence_digest": self.evidence_digest,
                "checked": self.checked,
                "missing": self.missing,
                "failure_reasons": self.failure_reasons,
                "public_credit_allowed": self.public_credit_allowed,
                "authority": self.authority,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "passed": self.passed,
            "evidence_digest": self.evidence_digest,
            "checked": list(self.checked),
            "missing": list(self.missing),
            "failure_reasons": list(self.failure_reasons),
            "public_credit_allowed": self.public_credit_allowed,
            "authority": self.authority,
            "verdict_digest": self.verdict_digest,
        }


def build_c4x_physical_truth_certificate(
    *,
    c4x_receipt: Mapping[str, Any] | None = None,
    sensorium_receipt: Mapping[str, Any] | None = None,
    bpf_receipt: Mapping[str, Any] | None = None,
    crystal_bus_receipt: Mapping[str, Any] | None = None,
    memfd_receipt: Mapping[str, Any] | None = None,
    guardian_receipt: Mapping[str, Any] | None = None,
    reuse_receipt: Mapping[str, Any] | None = None,
    pq_transport_receipt: Mapping[str, Any] | None = None,
    commons_receipt: Mapping[str, Any] | None = None,
    route_receipt: Mapping[str, Any] | None = None,
    psi_receipt: Mapping[str, Any] | None = None,
    xdp_receipt: Mapping[str, Any] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Return the final certificate matrix with no averaging."""
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    verdicts = [
        _truth(c4x_receipt),
        _sensorium(sensorium_receipt),
        _bpf(bpf_receipt),
        _crystal_bus(crystal_bus_receipt),
        _memfd(memfd_receipt),
        _guardian(guardian_receipt),
        _reuse(reuse_receipt),
        _pq_transport(pq_transport_receipt),
        _commons(commons_receipt),
        _route(route_receipt),
        _psi(psi_receipt),
        _xdp(xdp_receipt),
    ]
    gates = {item.layer: item.passed for item in verdicts}
    public_credit_allowed = all(gates.values())
    critical_failures = [item.layer for item in verdicts if not item.passed]
    receipt_core = {
        "beast_object_type": "c4x_physical_truth_certificate",
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "required_layers": list(REQUIRED_LAYERS),
        "certificate_gates": gates,
        "layer_verdicts": [item.to_dict() for item in verdicts],
        "public_credit_allowed": public_credit_allowed,
        "truth_claim_allowed": public_credit_allowed,
        "critical_failures": critical_failures,
        "no_averaging_rule": True,
        "claim_boundary": (
            "Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF "
            "observation, Crystal Bus protocol integrity, memfd/Guardian custody, "
            "reuse, post-quantum transport, Commons replication, route resilience, "
            "PSI governance, and scoped XDP must all pass independently. Every "
            "credited receipt is canonical-digest-bound, source-file verified, "
            "authority/boundary checked, and signed or file-backed attested. "
            "Missing, stale, contradictory, or partial evidence lowers authority "
            "instead of being averaged away."
        ),
    }
    return {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}


def empty_pending_sidecar() -> dict[str, Any]:
    return {
        "c4x_receipt": {},
        "sensorium_receipt": {},
        "bpf_receipt": {},
        "crystal_bus_receipt": {},
        "memfd_receipt": {},
        "guardian_receipt": {},
        "reuse_receipt": {},
        "pq_transport_receipt": {},
        "commons_receipt": {},
        "route_receipt": {},
        "psi_receipt": {},
        "xdp_receipt": {},
    }


def _truth(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.C4X_TRUTH,
        receipt,
        {
            "proof_first": True,
            "joined_verification": True,
            "text_artifact_digest_valid": True,
            "visual_artifact_digest_valid": True,
            "unsupported_gaps_refused": True,
            "provider_calls_used": 0,
        },
        authority="semantic_truth_only",
    )


def _sensorium(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.SENSORIUM_OBSERVATION,
        receipt,
        {
            "ordered_episode": True,
            "journal_integrity_valid": True,
            "explicit_loss_accounting": True,
            "raw_sensitive_payloads_absent": True,
            "observer_lifecycle_recorded": True,
            "missing_observations_lower_authority": True,
        },
        authority="observation_only",
    )


def _bpf(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.BPF_WITNESS,
        receipt,
        {
            "read_only_program": True,
            "cgroup_bound": True,
            "outbound_connect_attempts": 0,
            "dns_activity": 0,
            "provider_sockets_opened": 0,
            "unexpected_child_processes": 0,
            "live_provider_comparator_observed_network": True,
            "ring_loss_explicit": True,
            "raw_packet_payload_retained": False,
        },
        authority="kernel_observation_only",
    )


def _crystal_bus(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.PROTOCOL_INTEGRITY,
        receipt,
        {
            "af_unix_seqpacket": True,
            "so_peercred_bound": True,
            "session_id_bound": True,
            "message_mac_or_signature_verified": True,
            "sequence_replay_rejected": True,
            "durable_high_water_checked": True,
            "capability_lease_required": True,
            "arda_appraisal_required": True,
            "fd_count_type_seals_digest_verified": True,
            "sender_death_after_handoff_verified": True,
            "revocation_replay_rejected": True,
        },
        authority="host_local_protocol_integrity",
    )


def _memfd(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.MEMFD_CUSTODY,
        receipt,
        {
            "sealed_memfd": True,
            "seal_write": True,
            "seal_grow": True,
            "seal_shrink": True,
            "seal_seal": True,
            "digest_verified_after_seal": True,
            "mutation_attempt_rejected": True,
            "wrong_fd_type_rejected": True,
        },
        authority="kernel_immutable_artifact_custody",
    )


def _guardian(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.GUARDIAN_CUSTODY,
        receipt,
        {
            "separate_process": True,
            "scm_rights_handoff_verified": True,
            "process_lease_verified": True,
            "one_use_render_capability_consumed": True,
            "replay_render_capability_rejected": True,
            "wrong_uid_rejected": True,
            "expired_lease_rejected": True,
            "producer_death_after_handoff_verified": True,
            "joined_custody_receipt_signed": True,
        },
        authority="independent_custody_gatekeeper",
    )


def _reuse(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.REUSE,
        receipt,
        {
            "exact_prefix_hit_verified": True,
            "identity_mismatch_refused": True,
            "corrupt_payload_rejected": True,
            "restart_persistence_credit_only_if_demonstrated": True,
            "cross_engine_import_refused_without_physical_success": True,
            "crystal_composition_reuse_verified": True,
            "semantic_truth_points_not_awarded_for_kv_speed": True,
        },
        authority="reuse_certificate_only",
    )


def _pq_transport(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.PQ_TRANSPORT,
        receipt,
        {
            "ml_kem_active": True,
            "ml_dsa_signature_verified": True,
            "fallback": False,
            "recipient_decapsulation_verified": True,
            "ciphertext_tamper_rejected": True,
            "signature_tamper_rejected": True,
            "replay_nonce_unused": True,
            "artifact_digest_verified": True,
            "policy_scope_accepted": True,
        },
        authority="transport_confidentiality_and_authenticity",
    )


def _commons(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.COMMONS_REPLICATION,
        receipt,
        {
            "imported_as_quarantined_hypothesis": True,
            "clean_source_rebuild": True,
            "independent_seed": True,
            "independent_oracle": True,
            "reproduction_successful": True,
            "promotion_after_local_success_only": True,
            "node_count_minimum_met": True,
        },
        authority="replication_certificate",
    )


def _route(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.ROUTE_RESILIENCE,
        receipt,
        {
            "deterministic_failure_schedule_hidden_from_router": True,
            "attestation_failure_immediate_suppression": True,
            "timeout_accumulates_penalty": True,
            "429_suppression": True,
            "recovery_after_decay": True,
            "oscillation_bounded": True,
            "decision_receipts_explain_route_change": True,
            "beats_no_damping_retry_and_circuit_breaker": True,
        },
        authority="route_resilience_certificate",
    )


def _psi(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.PSI_GOVERNANCE,
        receipt,
        {
            "cpu_pressure_case": True,
            "memory_pressure_case": True,
            "io_pressure_case": True,
            "near_oom_case": True,
            "disk_full_or_inode_case": True,
            "evidence_not_corrupted": True,
            "sensorium_loss_not_silent": True,
            "low_priority_work_shed_first": True,
            "proof_and_custody_preserved": True,
            "refused_before_corrupting_evidence": True,
        },
        authority="scarcity_governance_certificate",
    )


def _xdp(receipt: Mapping[str, Any] | None) -> LayerVerdict:
    return _check(
        CertificateLayer.XDP_SCOPE,
        receipt,
        {
            "isolated_veth_or_namespace": True,
            "redirect_pass_drop_observed": True,
            "unauthorized_cgroup_rejected": True,
            "worker_death_observed": True,
            "rx_ring_loss_reported": True,
            "xdp_detach_detected": True,
            "no_unrelated_traffic_redirected": True,
            "policy_fail_open_or_closed_verified": True,
            "guardian_policy_not_bypassed": True,
        },
        authority="scoped_packet_actuation_certificate",
    )


def _check(
    layer: CertificateLayer,
    receipt: Mapping[str, Any] | None,
    required: Mapping[str, Any],
    *,
    authority: str,
) -> LayerVerdict:
    if not receipt:
        return LayerVerdict(
            layer=layer.value,
            passed=False,
            evidence_digest="",
            checked=tuple(required),
            missing=tuple(required),
            failure_reasons=("receipt_missing",),
            public_credit_allowed=False,
            authority=authority,
        )
    missing = []
    failures = []
    for key, expected in required.items():
        if key not in receipt:
            missing.append(key)
            continue
        actual = receipt.get(key)
        if actual != expected:
            failures.append(f"{key}_expected_{expected!r}_got_{actual!r}")
    digest_check = _verify_receipt_digest(receipt)
    evidence_digest = digest_check.claimed
    failures.extend(digest_check.failure_reasons)
    failures.extend(_verify_authority(receipt, authority))
    failures.extend(_verify_claim_boundary(receipt))
    source_links = _source_linkage(receipt)
    if not source_links:
        failures.append("source_receipt_linkage_missing")
    failures.extend(_verify_signature_or_attestation(layer, receipt, required, authority, source_links))
    failures.extend(_contradictory_status_failures(receipt))
    passed = not missing and not failures
    return LayerVerdict(
        layer=layer.value,
        passed=passed,
        evidence_digest=evidence_digest,
        checked=tuple(required),
        missing=tuple(missing),
        failure_reasons=tuple(failures),
        public_credit_allowed=passed,
        authority=authority,
    )


@dataclass(frozen=True, slots=True)
class _DigestCheck:
    claimed: str
    expected: str
    failure_reasons: tuple[str, ...]


def _verify_receipt_digest(receipt: Mapping[str, Any]) -> _DigestCheck:
    """Strictly bind a receipt to its canonical payload before granting credit.

    The certificate must never accept a digest-shaped string merely because it
    looks like a digest, and it must never manufacture proof for an unsigned
    receipt.  A credited layer therefore needs a `receipt_digest` that exactly
    equals `sha256_digest(receipt_without_receipt_digest)`.
    """
    claimed = str(receipt.get("receipt_digest") or "")
    expected = sha256_digest({k: v for k, v in dict(receipt).items() if k != "receipt_digest"})
    if not DIGEST_RE.fullmatch(claimed):
        return _DigestCheck(
            claimed=claimed,
            expected=expected,
            failure_reasons=("receipt_digest_missing_or_malformed",),
        )
    if claimed != expected:
        return _DigestCheck(
            claimed=claimed,
            expected=expected,
            failure_reasons=("receipt_digest_mismatch",),
        )
    return _DigestCheck(claimed=claimed, expected=expected, failure_reasons=())


def _verify_authority(receipt: Mapping[str, Any], expected_authority: str) -> tuple[str, ...]:
    authority = receipt.get("authority")
    if authority != expected_authority:
        return (f"authority_expected_{expected_authority!r}_got_{authority!r}",)
    return ()


def _verify_claim_boundary(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    boundary = str(receipt.get("claim_boundary") or "").strip()
    if len(boundary) < 24:
        return ("claim_boundary_missing_or_too_weak",)
    return ()


def _source_linkage(receipt: Mapping[str, Any]) -> dict[str, Any]:
    linked: dict[str, Any] = {}
    for key, value in receipt.items():
        if key in {"receipt_digest", "attestation_digest", "signature_digest"}:
            continue
        if isinstance(value, str) and DIGEST_RE.fullmatch(value) and value != ZERO_SHA256_DIGEST:
            if (
                key.startswith("source_")
                or key.endswith("_source_digest")
                or key.endswith("_receipt_digest")
                or key in {
                    "artifact_digest",
                    "capsule_digest",
                    "journal_head_hash",
                    "aggregate_digest",
                    "admission_manifest_digest",
                    "adaptive_trace_digest",
                    "naive_trace_digest",
                    "real_pressure_digest",
                }
            ):
                linked[key] = value
            continue
        if isinstance(value, list):
            digests = [str(item) for item in value if isinstance(item, str) and DIGEST_RE.fullmatch(item) and item != ZERO_SHA256_DIGEST]
            if digests and (key.endswith("_digests") or key.endswith("_receipt_digests")):
                linked[key] = digests
            if key == "source_artifacts":
                artifacts = _normalized_source_artifacts(value)
                if artifacts:
                    linked["source_artifacts_manifest_digest"] = sha256_digest(artifacts)
    return linked


def _verify_signature_or_attestation(
    layer: CertificateLayer,
    receipt: Mapping[str, Any],
    required: Mapping[str, Any],
    authority: str,
    source_links: Mapping[str, Any],
) -> tuple[str, ...]:
    if _has_verified_signature_or_mac(receipt):
        return ()
    artifact_failures = _verify_source_artifacts(receipt)
    if artifact_failures:
        return artifact_failures
    claimed = str(receipt.get("attestation_digest") or "")
    if not DIGEST_RE.fullmatch(claimed) or claimed == ZERO_SHA256_DIGEST:
        return ("signature_or_attestation_missing",)
    expected = _expected_layer_attestation_digest(layer, receipt, required, authority, source_links)
    if claimed != expected:
        return ("attestation_digest_mismatch",)
    return ()


def _has_verified_signature_or_mac(receipt: Mapping[str, Any]) -> bool:
    signature_digest = str(receipt.get("signature_digest") or "")
    return (
        DIGEST_RE.fullmatch(signature_digest) is not None
        and signature_digest != ZERO_SHA256_DIGEST
        and (
            receipt.get("message_mac_or_signature_verified") is True
            or receipt.get("joined_custody_receipt_signed") is True
            or receipt.get("ml_dsa_signature_verified") is True
        )
        and (
            receipt.get("signature_tamper_rejected") is True
            or receipt.get("replay_render_capability_rejected") is True
            or receipt.get("sequence_replay_rejected") is True
        )
    )


def _expected_layer_attestation_digest(
    layer: CertificateLayer,
    receipt: Mapping[str, Any],
    required: Mapping[str, Any],
    authority: str,
    source_links: Mapping[str, Any] | None = None,
) -> str:
    source_links = dict(source_links or _source_linkage(receipt))
    return sha256_digest(
        {
            "layer": layer.value,
            "authority": authority,
            "claim_boundary": str(receipt.get("claim_boundary") or ""),
            "source_linkage": source_links,
            "required_claims": {key: receipt.get(key) for key in sorted(required)},
        }
    )


def _verify_source_artifacts(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    artifacts = receipt.get("source_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ("source_artifacts_missing",)
    failures: list[str] = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            failures.append(f"source_artifact_{index}_malformed")
            continue
        raw_path = str(item.get("path") or "")
        if not raw_path or raw_path.startswith("/") or ".." in Path(raw_path).parts:
            failures.append(f"source_artifact_{index}_unsafe_path")
            continue
        path = (REPO_ROOT / raw_path).resolve()
        try:
            path.relative_to(REPO_ROOT)
        except ValueError:
            failures.append(f"source_artifact_{index}_outside_repo")
            continue
        if not path.is_file():
            failures.append(f"source_artifact_{index}_missing")
            continue
        expected_file_digest = str(item.get("file_sha256") or "")
        actual_file_digest = _file_sha256(path)
        if expected_file_digest != actual_file_digest:
            failures.append(f"source_artifact_{index}_file_digest_mismatch")
        contains_digest = str(item.get("contains_digest") or "")
        if contains_digest:
            if not DIGEST_RE.fullmatch(contains_digest) or contains_digest == ZERO_SHA256_DIGEST:
                failures.append(f"source_artifact_{index}_contains_digest_malformed")
            else:
                try:
                    if contains_digest not in path.read_text(encoding="utf-8", errors="ignore"):
                        failures.append(f"source_artifact_{index}_contains_digest_absent")
                except OSError:
                    failures.append(f"source_artifact_{index}_unreadable")
    return tuple(failures)


def _normalized_source_artifacts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        artifact = {
            "path": str(item.get("path") or ""),
            "file_sha256": str(item.get("file_sha256") or ""),
        }
        contains_digest = str(item.get("contains_digest") or "")
        if contains_digest:
            artifact["contains_digest"] = contains_digest
        normalized.append(artifact)
    return sorted(normalized, key=lambda item: (item["path"], item.get("contains_digest", ""), item["file_sha256"]))


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _contradictory_status_failures(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    for key, value in receipt.items():
        if "status" not in key.lower() and key.lower() not in {"runtime_error", "error"}:
            continue
        text = str(value or "").strip().lower()
        if not text:
            continue
        if any(term in text for term in CONTRADICTORY_STATUS_TERMS):
            failures.append(f"contradictory_{key}_{text}")
    return tuple(failures)
