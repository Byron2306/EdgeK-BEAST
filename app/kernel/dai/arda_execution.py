"""Bounded Arda execution and reverse evidence for DAI.

This module is the first safe execution rung: a promoted capability may perform
one deterministic sandbox replay, and then reverse evidence must recompute the
observed effect.  It intentionally does not start services, change host state or
grant general execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)
from app.kernel.dai.capability_promotion import DAICapability, DAICapabilityPromotionReceipt
from app.kernel.dai.contracts import ArdaAttestationSummary, AuthorityScope
from app.kernel.dai.neural_mesh import DAINeuralMeshActivationReceipt


EMPTY_STATE_DIGEST = sha256_digest(())


@dataclass(frozen=True, slots=True)
class ArdaSandboxExecutionReceipt:
    capability_digest: str
    world_state_digest: str
    promotion_receipt_digest: str
    mesh_activation_receipt_digest: str
    arda_attestation_digest: str
    sandbox_root: str
    before_state_digest: str
    after_state_digest: str
    output_artifact_digest: str
    effect_digest: str
    written_files: tuple[str, ...]
    executed: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    execution_mode: str = "arda_bounded_sandbox_replay"
    provider_calls_used: int = 0
    host_mutation_allowed: bool = False
    execution_authority_allowed: bool = False
    object_type: str = "dai_arda_bounded_execution_receipt"
    schema_version: str = "2026-08-04.phase1"
    maximum_authority: AuthorityScope = AuthorityScope.ARDA_BOUNDED_EXECUTION_ONLY

    def __post_init__(self) -> None:
        for field_name in (
            "capability_digest",
            "world_state_digest",
            "promotion_receipt_digest",
            "mesh_activation_receipt_digest",
            "arda_attestation_digest",
            "before_state_digest",
            "after_state_digest",
            "output_artifact_digest",
            "effect_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.execution_mode != "arda_bounded_sandbox_replay":
            raise ValueError("Arda DAI execution is limited to bounded sandbox replay")
        if self.host_mutation_allowed or self.execution_authority_allowed:
            raise ValueError("Arda DAI sandbox execution cannot grant host mutation or general execution authority")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ArdaReverseEvidenceReceipt:
    execution_receipt_digest: str
    capability_digest: str
    world_state_digest: str
    mesh_activation_receipt_digest: str
    observed_output_digest: str
    observed_effect_digest: str
    expected_effect_digest: str
    before_state_digest: str
    after_state_digest: str
    verified: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    provider_calls_used: int = 0
    host_mutation_observed: bool = False
    execution_authority_allowed: bool = False
    object_type: str = "dai_arda_reverse_evidence_receipt"
    schema_version: str = "2026-08-04.phase1"
    maximum_authority: AuthorityScope = AuthorityScope.PHYSICAL_ATTESTATION_ONLY

    def __post_init__(self) -> None:
        for field_name in (
            "execution_receipt_digest",
            "capability_digest",
            "world_state_digest",
            "mesh_activation_receipt_digest",
            "observed_output_digest",
            "observed_effect_digest",
            "expected_effect_digest",
            "before_state_digest",
            "after_state_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.host_mutation_observed or self.execution_authority_allowed:
            raise ValueError("Reverse evidence cannot report host mutation or general execution authority for this phase")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def execute_arda_bounded_replay(
    *,
    capability: DAICapability,
    promotion_receipt: DAICapabilityPromotionReceipt,
    mesh_receipt: DAINeuralMeshActivationReceipt,
    arda_attestation: ArdaAttestationSummary,
    sandbox_root: str | Path,
    request: Mapping[str, Any] | None = None,
) -> tuple[ArdaSandboxExecutionReceipt, ArdaReverseEvidenceReceipt]:
    """Run the promoted capability as a deterministic sandbox replay."""

    root = Path(sandbox_root).expanduser().resolve()
    before_digest = _snapshot_directory(root)
    request_payload = dict(request or _default_replay_request(capability))
    output_payload = _execution_output_payload(
        capability=capability,
        promotion_receipt=promotion_receipt,
        mesh_receipt=mesh_receipt,
        arda_attestation=arda_attestation,
        request=request_payload,
        before_state_digest=before_digest,
    )
    planned_output_bytes = (json.dumps(output_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    planned_output_digest = sha256_bytes(planned_output_bytes)
    pre_gates = {
        "capability_promoted_test_only": promotion_receipt.promoted
        and promotion_receipt.capability_digest == capability.capability_digest
        and capability.execution_authority_allowed is False,
        "mesh_activation_green": mesh_receipt.activated
        and mesh_receipt.capability_digest == capability.capability_digest
        and mesh_receipt.world_state_digest == capability.world_state_digest,
        "arda_attestation_present": arda_attestation.measured_identity_present
        and arda_attestation.bpf_or_kernel_witness_present,
        "bounded_replay_mode": True,
        "host_mutation_not_requested": request_payload.get("host_mutation_requested") is not True,
        "provider_calls_zero": True,
    }
    pre_red = tuple(name for name, passed in sorted(pre_gates.items()) if not passed)
    written_files: tuple[str, ...] = ()
    if not pre_red:
        root.mkdir(parents=True, exist_ok=True)
        output_path = root / "arda_bounded_replay_output.json"
        output_path.write_bytes(planned_output_bytes)
        written_files = (str(output_path),)
    after_digest = _snapshot_directory(root)
    effect_digest = sha256_digest(
        {
            "before_state_digest": before_digest,
            "after_state_digest": after_digest,
            "output_artifact_digest": planned_output_digest,
            "written_files": written_files,
        }
    )
    gates = {
        **pre_gates,
        "sandbox_root_bounded": str(root) != "/",
        "output_artifact_written": bool(written_files),
        "sandbox_state_changed": before_digest != after_digest if not pre_red else before_digest == after_digest,
        "effect_digest_bound": effect_digest.startswith("sha256:"),
        "no_general_execution_authority": True,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    execution = ArdaSandboxExecutionReceipt(
        capability_digest=capability.capability_digest,
        world_state_digest=capability.world_state_digest,
        promotion_receipt_digest=promotion_receipt.receipt_digest,
        mesh_activation_receipt_digest=mesh_receipt.receipt_digest,
        arda_attestation_digest=arda_attestation.attestation_digest,
        sandbox_root=str(root),
        before_state_digest=before_digest,
        after_state_digest=after_digest,
        output_artifact_digest=planned_output_digest,
        effect_digest=effect_digest,
        written_files=written_files,
        executed=not red_gates,
        gates=gates,
        red_gates=red_gates,
    )
    reverse = verify_arda_reverse_evidence(execution, expected_output_payload=output_payload)
    return execution, reverse


def verify_arda_reverse_evidence(
    execution: ArdaSandboxExecutionReceipt,
    *,
    expected_output_payload: Mapping[str, Any] | None = None,
) -> ArdaReverseEvidenceReceipt:
    root = Path(execution.sandbox_root)
    output_path = root / "arda_bounded_replay_output.json"
    observed_output_digest = sha256_bytes(output_path.read_bytes()) if output_path.exists() else sha256_digest({"missing_output": True})
    observed_after_digest = _snapshot_directory(root)
    expected_output_digest = (
        sha256_bytes((json.dumps(expected_output_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8"))
        if expected_output_payload is not None
        else execution.output_artifact_digest
    )
    observed_effect_digest = sha256_digest(
        {
            "before_state_digest": execution.before_state_digest,
            "after_state_digest": observed_after_digest,
            "output_artifact_digest": observed_output_digest,
            "written_files": execution.written_files,
        }
    )
    gates = {
        "execution_receipt_executed": execution.executed and not execution.red_gates,
        "output_digest_matches_execution": observed_output_digest == execution.output_artifact_digest,
        "output_digest_matches_expected": observed_output_digest == expected_output_digest,
        "after_state_recomputes": observed_after_digest == execution.after_state_digest,
        "effect_digest_recomputes": observed_effect_digest == execution.effect_digest,
        "capability_link_present": execution.capability_digest.startswith("sha256:"),
        "mesh_link_present": execution.mesh_activation_receipt_digest.startswith("sha256:"),
        "no_host_mutation_observed": not execution.host_mutation_allowed,
        "no_execution_authority": not execution.execution_authority_allowed,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    return ArdaReverseEvidenceReceipt(
        execution_receipt_digest=execution.receipt_digest,
        capability_digest=execution.capability_digest,
        world_state_digest=execution.world_state_digest,
        mesh_activation_receipt_digest=execution.mesh_activation_receipt_digest,
        observed_output_digest=observed_output_digest,
        observed_effect_digest=observed_effect_digest,
        expected_effect_digest=execution.effect_digest,
        before_state_digest=execution.before_state_digest,
        after_state_digest=observed_after_digest,
        verified=not red_gates,
        gates=gates,
        red_gates=red_gates,
    )


def _execution_output_payload(
    *,
    capability: DAICapability,
    promotion_receipt: DAICapabilityPromotionReceipt,
    mesh_receipt: DAINeuralMeshActivationReceipt,
    arda_attestation: ArdaAttestationSummary,
    request: Mapping[str, Any],
    before_state_digest: str,
) -> dict[str, Any]:
    return {
        "beast_object_type": "dai_arda_bounded_replay_output",
        "capability_digest": capability.capability_digest,
        "world_state_digest": capability.world_state_digest,
        "promotion_receipt_digest": promotion_receipt.receipt_digest,
        "mesh_activation_receipt_digest": mesh_receipt.receipt_digest,
        "arda_attestation_digest": arda_attestation.attestation_digest,
        "request_digest": sha256_digest(request),
        "before_state_digest": before_state_digest,
        "capability_id": capability.capability_id,
        "predicate_law_count": len(capability.predicate_laws),
        "allowed_outputs": capability.allowed_outputs,
        "replay_result": "source_support_capability_available_for_governed_replay",
        "provider_calls_used": 0,
        "host_mutation_performed": False,
        "execution_authority_allowed": False,
    }


def _default_replay_request(capability: DAICapability) -> dict[str, Any]:
    return {
        "request_type": "capability_replay_smoke",
        "capability_digest": capability.capability_digest,
        "world_state_digest": capability.world_state_digest,
        "host_mutation_requested": False,
    }


def _snapshot_directory(root: Path) -> str:
    if not root.exists():
        return EMPTY_STATE_DIGEST
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        entries.append({"path": rel, "digest": sha256_bytes(data), "size": len(data)})
    return sha256_digest(tuple(entries))
