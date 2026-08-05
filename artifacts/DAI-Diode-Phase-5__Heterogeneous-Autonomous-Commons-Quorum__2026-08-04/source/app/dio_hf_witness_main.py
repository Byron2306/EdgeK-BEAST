"""Tiny DIO remote witness service suitable for a Hugging Face Docker Space.

Run with:

    uvicorn app.dio_hf_witness_main:app --host 0.0.0.0 --port 7860

This service has no execution/provider authority. It signs only bounded DIO
attestations and semantic/adversarial vote packets with an Ed25519 key supplied
through environment variables.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest, utc_now_iso
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import (
    DIOAutonomousRemoteWitnessPacket,
    sign_autonomous_remote_witness_packet,
)
from app.kernel.dai.dio_commons_online import (
    DIO_COMMONS_ONLINE_VERSION,
    DIOCommonsCapabilityManifest,
    DIOCommonsChallenge,
    DIOCommonsSpaceIdentity,
    sign_commons_identity,
)


class AttestRequest(BaseModel):
    challenge_nonce: str = Field(min_length=16, max_length=512)


class EvaluateRequest(BaseModel):
    proposal: dict[str, Any]


class ChallengeRequest(BaseModel):
    proposal_digest: str
    evidence_root: str
    world_state_hash: str
    governance_epoch: str
    challenge_nonce: str = ""
    ttl_seconds: int = Field(default=300, ge=1, le=900)


@dataclass(frozen=True, slots=True)
class DIOHFWitnessConfig:
    node_id: str
    role: DIOWitnessRole
    signing_key: Ed25519PrivateKey
    verifier_commit: str
    container_manifest: str
    operator_root: str = "hf:Byron230686"
    governance_epoch: str = "dio-phase4-online-001"
    capability_ids: tuple[str, ...] = ("semantic_vote", "challenge_attestation")
    attestation_class: str = "signed_software_runtime"
    runtime_platform: str = "huggingface-docker-space"
    infrastructure_provider: str = "huggingface"
    maximum_authority: str = HF_SOFTWARE_WITNESS_AUTHORITY


def build_dio_hf_witness_app(config: DIOHFWitnessConfig) -> FastAPI:
    key_b64 = public_key_b64(config.signing_key.public_key())
    fingerprint = public_key_fingerprint(key_b64)
    app = FastAPI(
        title="DIO Remote Witness",
        version="2026-08-04.phase2.1",
        docs_url="/docs" if os.environ.get("BEAST_DIO_WITNESS_ENABLE_DOCS") == "1" else None,
        redoc_url=None,
    )

    def jsonable(value: Any) -> dict[str, Any]:
        return json.loads(canonical_json(value))

    def capability_manifest() -> DIOCommonsCapabilityManifest:
        return DIOCommonsCapabilityManifest(
            beast_object_type="dio_commons_capability_manifest",
            version=DIO_COMMONS_ONLINE_VERSION,
            node_id=config.node_id,
            verifier_digest=config.verifier_commit,
            capability_ids=config.capability_ids,
            maximum_authority=config.maximum_authority,
            persistent_service=True,
        )

    def space_identity() -> DIOCommonsSpaceIdentity:
        manifest = capability_manifest()
        return DIOCommonsSpaceIdentity(
            beast_object_type="dio_commons_space_identity",
            version=DIO_COMMONS_ONLINE_VERSION,
            node_id=config.node_id,
            role=config.role,
            operator_root=config.operator_root,
            runtime_platform=config.runtime_platform,
            infrastructure_provider=config.infrastructure_provider,
            public_signing_key=key_b64,
            key_fingerprint=fingerprint,
            verifier_digest=config.verifier_commit,
            capability_manifest_digest=manifest.manifest_digest,
            attestation_class=config.attestation_class,
            maximum_authority=config.maximum_authority,
            governance_epoch=config.governance_epoch,
        )

    def attestation_subject(challenge_nonce: str) -> dict[str, Any]:
        identity = space_identity()
        manifest = capability_manifest()
        return {
            "beast_object_type": "dio_remote_witness_attestation",
            "node_id": config.node_id,
            "role": config.role.value,
            "verifier_commit": config.verifier_commit,
            "container_manifest": config.container_manifest,
            "identity_digest": identity.identity_digest,
            "capability_manifest_digest": manifest.manifest_digest,
            "attestation_class": config.attestation_class,
            "public_signing_key": key_b64,
            "key_fingerprint": fingerprint,
            "boot_epoch": os.environ.get("BEAST_DIO_WITNESS_BOOT_EPOCH", "hf-space-runtime"),
            "runtime_platform": config.runtime_platform,
            "infrastructure_provider": config.infrastructure_provider,
            "maximum_authority": config.maximum_authority,
            "challenge_nonce": challenge_nonce,
        }

    def signed_attestation(challenge_nonce: str) -> dict[str, Any]:
        subject = attestation_subject(challenge_nonce)
        return {
            **subject,
            "challenge_signature": base64.b64encode(config.signing_key.sign(canonical_json(subject).encode("utf-8"))).decode("ascii"),
        }

    def signed_vote_payload(proposal: DIOProposalPacket) -> dict[str, Any]:
        vote = DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=config.node_id,
            role=config.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=config.verifier_commit,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root,),
            reason_codes=("proposal_packet_well_formed", f"{config.role.value}_jurisdiction_only"),
            issued_at=utc_now_iso(),
            expires_at=proposal.expires_at,
            maximum_authority=config.maximum_authority,
        )
        signed = sign_dio_vote(vote, config.signing_key)
        payload = signed.signing_payload
        payload["vote_signature"] = signed.vote_signature
        payload["vote_digest"] = signed.vote_digest
        return payload

    def autonomous_packet_payload(proposal: DIOProposalPacket) -> dict[str, Any]:
        attestation = signed_attestation(proposal.challenge_nonce)
        attestation_digest = sha256_digest(attestation)
        admission = DIOWitnessAdmission(
            node_id=config.node_id,
            role=config.role,
            runtime_platform=config.runtime_platform,
            infrastructure_provider=config.infrastructure_provider,
            public_key_b64=key_b64,
            key_fingerprint=fingerprint,
            verifier_commit=config.verifier_commit,
            maximum_authority=config.maximum_authority,
            verifier_build_permitted=True,
            remote_runtime=True,
            hardware_rooted_identity=False,
            attestation_digest=attestation_digest,
            container_manifest=config.container_manifest,
            admitted=True,
        )
        vote_payload = signed_vote_payload(proposal)
        vote = DIORemoteWitnessVote(**{field: vote_payload[field] for field in DIORemoteWitnessVote.__dataclass_fields__})
        unsigned_packet = DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=config.node_id,
            role=config.role,
            runtime_platform=config.runtime_platform,
            infrastructure_provider=config.infrastructure_provider,
            public_key_b64=key_b64,
            key_fingerprint=fingerprint,
            verifier_commit=config.verifier_commit,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=(proposal.evidence_root, attestation_digest),
            independently_evaluated=True,
            remote_runtime_observed=True,
            issued_at=vote.issued_at,
            expires_at=vote.expires_at,
            maximum_authority=config.maximum_authority,
        )
        packet = sign_autonomous_remote_witness_packet(unsigned_packet, config.signing_key)
        return {
            "packet": {**jsonable(packet), "packet_digest": packet.packet_digest},
            "admission": {**jsonable(admission), "admission_digest": admission.admission_digest},
            "attestation": attestation,
            "attestation_digest": attestation_digest,
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "dio-remote-witness",
            "node_id": config.node_id,
            "role": config.role.value,
            "maximum_authority": config.maximum_authority,
        }

    @app.get("/identity")
    async def identity() -> dict[str, Any]:
        current = space_identity()
        return {
            **jsonable(current),
            "identity_digest": current.identity_digest,
            "identity_signature": sign_commons_identity(current, config.signing_key),
        }

    @app.get("/manifest")
    async def manifest() -> dict[str, Any]:
        current = capability_manifest()
        return {**jsonable(current), "manifest_digest": current.manifest_digest}

    @app.get("/attestation")
    async def attestation() -> dict[str, Any]:
        return signed_attestation("status-read-only-attestation")

    @app.post("/attest")
    async def attest(request: AttestRequest) -> dict[str, Any]:
        return signed_attestation(request.challenge_nonce)

    @app.post("/v1/refresh-attestation")
    async def refresh_attestation(request: AttestRequest) -> dict[str, Any]:
        return signed_attestation(request.challenge_nonce)

    @app.post("/v1/challenge")
    async def challenge(request: ChallengeRequest) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        nonce = request.challenge_nonce.strip() or secrets.token_urlsafe(32)
        try:
            current = DIOCommonsChallenge(
                beast_object_type="dio_commons_challenge",
                version=DIO_COMMONS_ONLINE_VERSION,
                proposal_digest=request.proposal_digest,
                evidence_root=request.evidence_root,
                world_state_hash=request.world_state_hash,
                governance_epoch=request.governance_epoch,
                challenge_nonce=nonce,
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(seconds=request.ttl_seconds)).isoformat(),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid Commons challenge: {exc}") from exc
        return {
            "challenge": jsonable(current),
            "challenge_digest": current.challenge_digest,
            "attestation": signed_attestation(nonce),
        }

    @app.post("/evaluate")
    async def evaluate(request: EvaluateRequest) -> dict[str, Any]:
        return await vote(request)

    @app.post("/v1/evaluate")
    async def v1_evaluate(request: EvaluateRequest) -> dict[str, Any]:
        return await vote(request)

    @app.post("/v1/vote")
    async def vote(request: EvaluateRequest) -> dict[str, Any]:
        try:
            proposal = DIOProposalPacket(**request.proposal)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid DIO proposal packet: {exc}") from exc
        return signed_vote_payload(proposal)

    @app.post("/v1/autonomous-packet")
    async def autonomous_packet(request: EvaluateRequest) -> dict[str, Any]:
        try:
            proposal = DIOProposalPacket(**request.proposal)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid DIO proposal packet: {exc}") from exc
        return autonomous_packet_payload(proposal)

    return app


def _default_config() -> DIOHFWitnessConfig:
    return DIOHFWitnessConfig(
        node_id=os.environ.get("BEAST_DIO_WITNESS_NODE_ID", "dio:hf:semantic-witness-01"),
        role=DIOWitnessRole(os.environ.get("BEAST_DIO_WITNESS_ROLE", DIOWitnessRole.SEMANTIC.value)),
        signing_key=_load_signing_key(),
        verifier_commit=os.environ.get("BEAST_DIO_WITNESS_VERIFIER_COMMIT", sha256_bytes(Path(__file__).read_bytes())),
        container_manifest=os.environ.get("BEAST_DIO_WITNESS_CONTAINER_MANIFEST", sha256_digest({"entrypoint": "app.dio_hf_witness_main"})),
        operator_root=os.environ.get("BEAST_DIO_WITNESS_OPERATOR_ROOT", "hf:Byron230686"),
        governance_epoch=os.environ.get("BEAST_DIO_WITNESS_GOVERNANCE_EPOCH", "dio-phase4-online-001"),
    )


def _load_signing_key() -> Ed25519PrivateKey:
    raw_b64 = os.environ.get("BEAST_DIO_WITNESS_PRIVATE_KEY_B64", "").strip()
    if raw_b64:
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw_b64, validate=True))
    pem_path = os.environ.get("BEAST_DIO_WITNESS_PRIVATE_KEY_PEM", "").strip()
    if pem_path:
        key = serialization.load_pem_private_key(Path(pem_path).expanduser().read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise RuntimeError("BEAST_DIO_WITNESS_PRIVATE_KEY_PEM must be an Ed25519 key")
        return key
    if os.environ.get("BEAST_DIO_WITNESS_ALLOW_EPHEMERAL_IDENTITY") == "1":
        return Ed25519PrivateKey.generate()
    raise RuntimeError("BEAST_DIO_WITNESS_PRIVATE_KEY_B64 or BEAST_DIO_WITNESS_PRIVATE_KEY_PEM is required")


if os.environ.get("BEAST_DIO_WITNESS_DISABLE_DEFAULT_APP") == "1":
    app = FastAPI()
else:
    try:
        app = build_dio_hf_witness_app(_default_config())
    except RuntimeError as exc:
        app = FastAPI(title="DIO Remote Witness - unconfigured", redoc_url=None)

        @app.get("/health")
        async def unconfigured_health() -> dict[str, Any]:
            return {
                "ok": False,
                "service": "dio-remote-witness",
                "configured": False,
                "error": str(exc),
            }
