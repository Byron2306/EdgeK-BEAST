from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.kernel.compute.residual_contracts import canonical_json, sha256_digest
from app.kernel.crystal_bus.capsule_messages import CapsuleOffer
from app.kernel.registry.provider_registry import ProviderRecord

from .sealed_capsule import CrystalCapsule


class GenerationExecutionMode(str, Enum):
    EXACT = "exact"
    TEMPLATE = "template"
    LEXICALIZE = "lexicalize"
    LOCAL_REASON = "local_reason"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class GenerationCrystalIR:
    request_digest: str
    modality: str
    execution_mode: GenerationExecutionMode
    prompt_digest: str
    provider_id: str
    provider_mode: str
    model: str
    render_contract: Mapping[str, Any]
    model_contract: Mapping[str, Any]
    reuse_contract: Mapping[str, Any]
    proof_contract: Mapping[str, Any]
    commons_capability: Mapping[str, Any]
    socket_guardian_binding: Mapping[str, Any]
    sanitized_metadata: Mapping[str, Any]

    @property
    def crystal_digest(self) -> str:
        return sha256_digest(self)


def seal_generation_provider_request(
    request: Any,
    record: ProviderRecord,
    *,
    readiness: Mapping[str, Any],
    output_digest: str = "",
    final_status: str = "",
    services_path: str | Path = ".byron/services.yaml",
) -> dict[str, Any]:
    """Build and seal a provider-boundary Generation Crystal IR.

    The capsule deliberately carries prompt digests and bounded contracts, not
    raw prompt text.  It is a transport/proof artifact, not authority to execute.
    """
    request_mode = str(getattr(request.mode, "value", request.mode))
    request_modality = str(getattr(request.modality, "value", request.modality))
    execution_mode = GenerationExecutionMode.ESCALATE if request_mode == "live" else GenerationExecutionMode.LOCAL_REASON
    guardian = _socket_guardian_binding(services_path)
    commons = _commons_capability(record, readiness=readiness)
    proof_contract = {
        "readiness_digest": str(readiness.get("readiness_digest") or ""),
        "approval_receipt_digest": sha256_digest({"approval_receipt": request.approval_receipt}),
        "output_digest": output_digest,
        "final_status": final_status,
        "policy_digest": sha256_digest({"policy": "generation-provider-boundary.v2"}),
    }
    ir = GenerationCrystalIR(
        request_digest=request.request_digest,
        modality=request_modality,
        execution_mode=execution_mode,
        prompt_digest=request.prompt_digest,
        provider_id=record.provider_id,
        provider_mode=request_mode,
        model=request.model or record.default_model or record.provider_id,
        render_contract={
            "format": "text" if request_modality == "text" else "rgba_region_or_image_bytes",
            "maximum_authority": "render_only" if request_modality == "image" else "read_verified",
            "do_not_invent": True,
        },
        model_contract={
            "provider_backend": record.backend,
            "model_digest": sha256_digest({"provider": record.provider_id, "model": request.model or record.default_model or ""}),
            "live_execution": request_mode == "live",
        },
        reuse_contract={
            "cache_class": "digest_bound_generation_crystal",
            "allow_exact_replay": True,
            "portable_raw_kv": False,
            "native_context_allowed": False,
        },
        proof_contract=proof_contract,
        commons_capability=commons,
        socket_guardian_binding=guardian,
        sanitized_metadata=_sanitize_metadata(request.metadata),
    )
    payload_text = canonical_json({
        "beast_object_type": "generation_crystal_ir",
        "version": "1.0",
        **_dataclass_dict(ir),
        "crystal_digest": ir.crystal_digest,
    })
    capsule_report = _seal_payload(payload_text.encode("utf-8"), ir)
    return {
        "beast_object_type": "generation_synthesis_capsule_receipt",
        "version": "1.0",
        "execution_mode": execution_mode.value,
        "crystal_digest": ir.crystal_digest,
        "payload_digest": sha256_digest(payload_text),
        "prompt_digest": request.prompt_digest,
        "request_digest": request.request_digest,
        "commons_capability_digest": sha256_digest(commons),
        "socket_guardian_binding_digest": sha256_digest(guardian),
        "sealed_capsule": capsule_report,
        "raw_prompt_stored": False,
    }


def _dataclass_dict(ir: GenerationCrystalIR) -> dict[str, Any]:
    return {
        "request_digest": ir.request_digest,
        "modality": ir.modality,
        "execution_mode": ir.execution_mode.value,
        "prompt_digest": ir.prompt_digest,
        "provider_id": ir.provider_id,
        "provider_mode": ir.provider_mode,
        "model": ir.model,
        "render_contract": dict(ir.render_contract),
        "model_contract": dict(ir.model_contract),
        "reuse_contract": dict(ir.reuse_contract),
        "proof_contract": dict(ir.proof_contract),
        "commons_capability": dict(ir.commons_capability),
        "socket_guardian_binding": dict(ir.socket_guardian_binding),
        "sanitized_metadata": dict(ir.sanitized_metadata),
    }


def _seal_payload(payload: bytes, ir: GenerationCrystalIR) -> dict[str, Any]:
    if not hasattr(os, "memfd_create"):
        return {
            "sealed_memfd": False,
            "capsule_verified": False,
            "reason": "memfd_unavailable",
        }
    capsule = None
    try:
        capsule = CrystalCapsule().create(
            payload,
            authority_ref="beast.generation-synthesis-plane",
            audience="beast-generation-provider-boundary",
            capability_ref="generation_provider_boundary",
            appraisal_ref=ir.crystal_digest,
        )
        verified = CrystalCapsule().verify(
            capsule,
            expected_authority="beast.generation-synthesis-plane",
            expected_audience="beast-generation-provider-boundary",
            capability_ref="generation_provider_boundary",
            appraisal_ref=ir.crystal_digest,
        )
        lease_digest = sha256_digest({
            "capability": "generation_provider_boundary",
            "provider_id": ir.provider_id,
            "modality": ir.modality,
        })
        offer = CapsuleOffer(
            capsule_digest=capsule.digest,
            capsule_size=capsule.size,
            crystal_id=ir.crystal_digest,
            promotion_digest=ir.crystal_digest,
            capability_lease_digest=lease_digest,
            audience=capsule.audience,
            expires_at=capsule.expires_at,
        )
        guardian_handoff = _socket_guardian_handoff(capsule, ir)
        return {
            "sealed_memfd": bool(capsule.sealed),
            "capsule_digest": capsule.digest,
            "capsule_size": capsule.size,
            "capsule_verified": bool(verified),
            "capsule_offer_digest": offer.control_digest,
            "capability_lease_digest": lease_digest,
            "fd_transport": "memfd+SCM_RIGHTS_eligible",
            "socket_guardian_handoff": guardian_handoff,
        }
    except Exception as exc:
        return {
            "sealed_memfd": False,
            "capsule_verified": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if capsule is not None:
            try:
                os.close(capsule.fd)
            except OSError:
                pass


def _socket_guardian_handoff(capsule: Any, ir: GenerationCrystalIR) -> dict[str, Any]:
    socket_path = os.environ.get("BEAST_GENERATION_SOCKET_GUARDIAN", "").strip()
    if not socket_path:
        return {
            "attempted": False,
            "verified": False,
            "reason": "BEAST_GENERATION_SOCKET_GUARDIAN_not_configured",
        }
    try:
        from app.kernel.execution.socket_guardian import SocketGuardianClient

        client = SocketGuardianClient(socket_path, require_signed_receipts=False)
        receipt = client.verify_capsule(
            capsule.fd,
            expected_capsule_digest=capsule.digest,
            authority_ref=capsule.authority_ref,
            audience=capsule.audience,
            capability_ref=capsule.capability_ref,
            appraisal_ref=capsule.appraisal_ref,
            workspace_id="generation-provider-boundary",
            policy_generation="generation-provider-boundary.v2",
        )
        return {
            "attempted": True,
            "verified": bool(receipt.get("verified")),
            "guardian_id": str(receipt.get("guardian_id") or ""),
            "receipt_digest": str(receipt.get("receipt_digest") or ""),
            "fd_transport": str(receipt.get("fd_transport") or ""),
            "capsule_digest": str(receipt.get("capsule_digest") or ""),
        }
    except Exception as exc:
        return {
            "attempted": True,
            "verified": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def _sanitize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(metadata or {})
    blocked = {"prompt", "input", "text", "messages", "raw_prompt"}
    sanitized = {
        key: value
        for key, value in raw.items()
        if key not in blocked and _is_safe_metadata_value(value)
    }
    sanitized["raw_prompt_present"] = any(key in raw for key in blocked)
    sanitized["metadata_digest"] = sha256_digest(raw)
    return sanitized


def _is_safe_metadata_value(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return not (isinstance(value, str) and len(value) > 160)
    if isinstance(value, (list, tuple)):
        return len(value) <= 12 and all(_is_safe_metadata_value(item) for item in value)
    if isinstance(value, Mapping):
        return len(value) <= 12 and all(isinstance(key, str) and key not in {"prompt", "input", "text", "messages", "raw_prompt"} and _is_safe_metadata_value(item) for key, item in value.items())
    return False


def _commons_capability(record: ProviderRecord, *, readiness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "beast_object_type": "commons_generation_capability_snapshot",
        "version": "1.0",
        "node_id": os.environ.get("BEAST_COMMONS_NODE_ID", "local-beast-provider-boundary"),
        "provider_id": record.provider_id,
        "backend": record.backend,
        "env_ready": bool(readiness.get("env_ready")),
        "supported_modality": str(readiness.get("modality") or ""),
        "resident": False,
        "scheduler_preference": "exact_replay_before_provider",
        "pressure": {
            "cpu": "unreported",
            "memory": "unreported",
            "thermal": "unreported",
        },
        "capabilities": [
            "generation_crystal_capsule_accept",
            "digest_bound_replay",
            "provider_escalation_boundary",
        ],
    }


def _socket_guardian_binding(services_path: str | Path) -> dict[str, Any]:
    path = Path(services_path)
    payload: dict[str, Any] = {}
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = payload.get("services") if isinstance(payload, Mapping) else {}
    guarded = []
    if isinstance(services, Mapping):
        for name, value in sorted(services.items()):
            if isinstance(value, Mapping) and value.get("socket_guardian") is True:
                guarded.append({
                    "service": str(name),
                    "port": int(value.get("port") or 0),
                    "upstream": str(value.get("upstream") or ""),
                    "health_path": str(value.get("health_path") or ""),
                    "trust_domain": str(value.get("trust_domain") or ""),
                })
    return {
        "beast_object_type": "socket_guardian_generation_binding",
        "version": "1.0",
        "services_registry_path": str(path),
        "services_registry_digest": sha256_digest(payload),
        "guardian_enabled_services": tuple(guarded),
        "descriptor_handoff": "SCM_RIGHTS_eligible",
        "provider_boundary_requires_registry_owned_endpoint": True,
    }
