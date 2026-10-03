"""DAI Commons admission bound to Arda attestation and ML-KEM sessions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.contracts import ArdaAttestationSummary, AuthorityScope, WorldStateSnapshot


class CommonsAdmissionError(ValueError):
    """Raised when a Commons node cannot be admitted as a DAI witness."""


@dataclass(frozen=True, slots=True)
class CommonsNodeAdmission:
    node_id: str
    witness_role: str
    world_state_digest: str
    arda_attestation_digest: str
    arda_workload_digest: str
    ml_kem_receipt_digest: str
    ml_kem_algorithm: str
    public_key_digest: str
    transcript_digest: str
    health_digest: str
    admitted: bool
    maximum_authority: AuthorityScope = AuthorityScope.COMMONS_ADMISSION_ONLY

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.witness_role.strip():
            raise ValueError("Commons admission requires node_id and witness_role")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        for field_name in (
            "world_state_digest",
            "arda_attestation_digest",
            "arda_workload_digest",
            "ml_kem_receipt_digest",
            "public_key_digest",
            "transcript_digest",
            "health_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)

    @property
    def admission_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CommonsAdmissionReceipt:
    world_state_digest: str
    admitted_nodes: tuple[CommonsNodeAdmission, ...]
    ml_kem_receipt_digest: str
    arda_attestation_digest: str
    admitted: bool
    red_gates: tuple[str, ...]
    object_type: str = "dai_commons_admission_receipt"
    schema_version: str = "2026-08-04.phase1"
    maximum_authority: AuthorityScope = AuthorityScope.COMMONS_ADMISSION_ONLY

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)

    @property
    def witness_roles(self) -> tuple[str, ...]:
        return tuple(sorted({node.witness_role for node in self.admitted_nodes if node.admitted}))

    def __post_init__(self) -> None:
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        for field_name in ("world_state_digest", "ml_kem_receipt_digest", "arda_attestation_digest"):
            require_digest(getattr(self, field_name), field_name=field_name)


def admit_commons_nodes(
    *,
    ml_kem_receipt: Mapping[str, Any],
    arda_attestation: ArdaAttestationSummary,
    world_state: WorldStateSnapshot,
    role_by_node: Mapping[str, str] | None = None,
    bound_world_state_digest: str | None = None,
) -> CommonsAdmissionReceipt:
    role_by_node = dict(role_by_node or {})
    effective_world_state_digest = bound_world_state_digest or world_state.snapshot_digest
    require_digest(effective_world_state_digest, field_name="bound_world_state_digest")
    nodes = tuple(item for item in (ml_kem_receipt.get("nodes") or ()) if isinstance(item, Mapping))
    ml_kem_digest = str(ml_kem_receipt.get("receipt_digest") or sha256_digest(ml_kem_receipt))
    receipt_body = dict(ml_kem_receipt)
    receipt_body.pop("receipt_digest", None)
    pairwise = tuple(item for item in (ml_kem_receipt.get("pairwise_transcript_matrix") or ()) if isinstance(item, Mapping))
    gates = {
        "ml_kem_object_type": ml_kem_receipt.get("beast_object_type") == "commons_ml_kem_gauntlet_receipt",
        "ml_kem_status_passed": ml_kem_receipt.get("status") == "passed",
        "ml_kem_receipt_digest_recomputes": bool(ml_kem_digest and ml_kem_digest == sha256_digest(receipt_body)),
        "ml_kem_algorithm": str(ml_kem_receipt.get("algorithm") or "") == ML_KEM_ALGORITHM,
        "ml_kem_nodes_present": len(nodes) >= 3,
        "ml_kem_secret_policy": str(ml_kem_receipt.get("secret_storage_policy") or "") == "shared_secret_bytes_never_serialized",
        "ml_kem_pairwise_matrix_present": len(pairwise) >= 6,
        "ml_kem_nodes_requested_present": len(tuple(ml_kem_receipt.get("nodes_requested") or ())) >= 3,
        "arda_measured_identity_present": arda_attestation.measured_identity_present,
        "arda_physical_witness_present": arda_attestation.bpf_or_kernel_witness_present,
        "world_state_current": world_state.is_current(),
    }
    admitted_nodes: list[CommonsNodeAdmission] = []
    for index, node in enumerate(nodes):
        node_id = str(node.get("node_id") or "")
        role = role_by_node.get(node_id) or ("semantic", "physical", "adversarial", "observer")[min(index, 3)]
        node_ok = (
            bool(node_id)
            and node.get("confirmed") is True
            and node.get("secret_exported") is False
            and node.get("health_ok") is True
            and str(node.get("algorithm") or "") == ML_KEM_ALGORITHM
            and str(node.get("public_key_digest") or "").startswith("sha256:")
            and str(node.get("public_key_document_digest") or "").startswith("sha256:")
            and str(node.get("public_key_signature_digest") or "").startswith("sha256:")
            and str(node.get("challenge_confirmation_digest") or "").startswith("sha256:")
            and str(node.get("challenge_signature_digest") or "").startswith("sha256:")
            and str(node.get("ciphertext_digest") or "").startswith("sha256:")
            and str(node.get("transcript_digest") or "").startswith("sha256:")
            and int(node.get("ciphertext_size_bytes") or 0) > 0
            and int(node.get("shared_secret_size_bytes") or 0) == 32
        )
        admitted_nodes.append(
            CommonsNodeAdmission(
                node_id=node_id,
                witness_role=role,
                world_state_digest=effective_world_state_digest,
                arda_attestation_digest=arda_attestation.attestation_digest,
                arda_workload_digest=arda_attestation.workload_digest,
                ml_kem_receipt_digest=ml_kem_digest,
                ml_kem_algorithm=str(node.get("algorithm") or ""),
                public_key_digest=str(node.get("public_key_digest") or ""),
                transcript_digest=str(node.get("transcript_digest") or ""),
                health_digest=str(node.get("health_digest") or ""),
                admitted=node_ok,
            )
        )
    gates["all_nodes_confirmed_and_healthy"] = all(node.admitted for node in admitted_nodes)
    gates["role_diverse_minimum"] = {"semantic", "physical", "adversarial"}.issubset(
        {node.witness_role for node in admitted_nodes if node.admitted}
    )
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    return CommonsAdmissionReceipt(
        world_state_digest=effective_world_state_digest,
        admitted_nodes=tuple(admitted_nodes),
        ml_kem_receipt_digest=ml_kem_digest,
        arda_attestation_digest=arda_attestation.attestation_digest,
        admitted=not red_gates,
        red_gates=red_gates,
    )
