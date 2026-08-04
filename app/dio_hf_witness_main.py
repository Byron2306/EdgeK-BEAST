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
import os
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest, utc_now_iso
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessRole,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)


class AttestRequest(BaseModel):
    challenge_nonce: str = Field(min_length=16, max_length=512)


class EvaluateRequest(BaseModel):
    proposal: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DIOHFWitnessConfig:
    node_id: str
    role: DIOWitnessRole
    signing_key: Ed25519PrivateKey
    verifier_commit: str
    container_manifest: str
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

    def attestation_subject(challenge_nonce: str) -> dict[str, Any]:
        return {
            "beast_object_type": "dio_remote_witness_attestation",
            "node_id": config.node_id,
            "role": config.role.value,
            "verifier_commit": config.verifier_commit,
            "container_manifest": config.container_manifest,
            "public_signing_key": key_b64,
            "key_fingerprint": fingerprint,
            "boot_epoch": os.environ.get("BEAST_DIO_WITNESS_BOOT_EPOCH", "hf-space-runtime"),
            "runtime_platform": config.runtime_platform,
            "infrastructure_provider": config.infrastructure_provider,
            "maximum_authority": config.maximum_authority,
            "challenge_nonce": challenge_nonce,
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

    @app.post("/attest")
    async def attest(request: AttestRequest) -> dict[str, Any]:
        subject = attestation_subject(request.challenge_nonce)
        return {
            **subject,
            "challenge_signature": base64.b64encode(config.signing_key.sign(canonical_json(subject).encode("utf-8"))).decode("ascii"),
        }

    @app.post("/evaluate")
    async def evaluate(request: EvaluateRequest) -> dict[str, Any]:
        try:
            proposal = DIOProposalPacket(**request.proposal)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid DIO proposal packet: {exc}") from exc
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

    return app


def _default_config() -> DIOHFWitnessConfig:
    return DIOHFWitnessConfig(
        node_id=os.environ.get("BEAST_DIO_WITNESS_NODE_ID", "dio:hf:semantic-witness-01"),
        role=DIOWitnessRole(os.environ.get("BEAST_DIO_WITNESS_ROLE", DIOWitnessRole.SEMANTIC.value)),
        signing_key=_load_signing_key(),
        verifier_commit=os.environ.get("BEAST_DIO_WITNESS_VERIFIER_COMMIT", sha256_bytes(Path(__file__).read_bytes())),
        container_manifest=os.environ.get("BEAST_DIO_WITNESS_CONTAINER_MANIFEST", sha256_digest({"entrypoint": "app.dio_hf_witness_main"})),
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
