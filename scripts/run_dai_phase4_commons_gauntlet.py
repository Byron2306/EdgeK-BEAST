#!/usr/bin/env python3
"""Hostile gauntlet for the Phase-4 mixed online/offline Commons coordinator."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_commons_adapters import DIOCommonsSpaceAdapterReport
from app.kernel.dai.dio_commons_coordinator import mint_phase4_proposal, run_commons_coordinator_session
from app.kernel.dai.dio_commons_online import DIOCommonsCapabilityManifest, DIOCommonsSpaceIdentity, sign_commons_identity
from app.kernel.dai.dio_distributed_quorum import (
    DIORemoteWitnessVote,
    DIOVoteDecision,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    sign_dio_vote,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase4-commons-gauntlet"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    receipt = run(out=args.out)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


def run(*, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Callable[[], bool]] = {
        "duplicate_adapter_vote_key_rejected": _duplicate_adapter_vote_key_rejected,
        "duplicate_adapter_operator_rejected": _duplicate_adapter_operator_rejected,
        "stale_epoch_rejected": _stale_epoch_rejected,
        "expired_challenge_rejected": _expired_challenge_rejected,
        "wrong_manifest_rejected": _wrong_manifest_rejected,
        "wrong_verifier_rejected": _wrong_verifier_rejected,
        "attestation_downgrade_rejected": _attestation_downgrade_rejected,
        "replayed_challenge_rejected": _replayed_challenge_rejected,
        "role_collision_rejected": _role_collision_rejected,
        "authenticated_veto_blocks_quorum": _authenticated_veto_blocks_quorum,
        "adapter_persistence_inflation_rejected": _adapter_persistence_inflation_rejected,
    }
    results = {name: check() for name, check in cases.items()}
    receipt = {
        "beast_object_type": "dio_phase4_commons_gauntlet_receipt",
        "version": "2026-08-04.phase4.commons-gauntlet.v1",
        "case_count": len(results),
        "blocked_count": sum(1 for passed in results.values() if passed),
        "case_results": results,
        "green": all(results.values()),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    (out / "dio_phase4_commons_gauntlet_receipt.json").write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def _fixture():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    pub = _public_key_b64(hf_key)
    verifier = sha256_digest({"verifier": "phase4-gauntlet-hf"})
    manifest = DIOCommonsCapabilityManifest(
        "dio_commons_capability_manifest",
        "1.0",
        "dio:hf:semantic-witness-01",
        verifier,
        ("semantic_vote", "challenge_attestation"),
        HF_SOFTWARE_WITNESS_AUTHORITY,
        True,
    )
    identity = DIOCommonsSpaceIdentity(
        "dio_commons_space_identity",
        "1.0",
        manifest.node_id,
        "semantic_witness",
        "hf:Byron230686",
        "huggingface-docker-space",
        "huggingface",
        pub,
        _public_key_fingerprint(pub),
        verifier,
        manifest.manifest_digest,
        "signed_software_runtime",
        HF_SOFTWARE_WITNESS_AUTHORITY,
        "dio-phase4-online-001",
    )
    proposal, challenge = mint_phase4_proposal(
        proposal_digest=sha256_digest({"proposal": "phase4-gauntlet"}),
        capability_digest=sha256_digest({"capability": "phase4-gauntlet"}),
        evidence_root=sha256_digest({"evidence": "phase4-gauntlet"}),
        world_state_hash=sha256_digest({"world": "phase4-gauntlet"}),
        governance_epoch=identity.governance_epoch,
        challenge_nonce="phase4-gauntlet-shared-" + "x" * 24,
        now=now,
    )
    adapters = (
        _adapter("dio:arda:local-physical-01", "physical_execution_witness", "local_physical_witness", "physical_execution_witness_only", "local", "arda:operator"),
        _adapter("dio:aws:tee-governance-01", "governance_witness", "provider_hardware_attestation", "hardware_rooted_governance_vote_only", "aws", "aws:operator"),
    )
    adapter_keys = {adapter.node_id: Ed25519PrivateKey.generate() for adapter in adapters}
    online_vote = _online_vote(identity, proposal, hf_key, now=now)
    return now, hf_key, coordinator_key, identity, manifest, proposal, challenge, adapters, adapter_keys, online_vote


def _run_with(**changes):
    now, hf_key, coordinator_key, identity, manifest, proposal, challenge, adapters, adapter_keys, online_vote = _fixture()
    identity = changes.get("identity", identity)
    manifest = changes.get("manifest", manifest)
    proposal = changes.get("proposal", proposal)
    challenge = changes.get("challenge", challenge)
    adapters = changes.get("adapters", adapters)
    adapter_keys = changes.get("adapter_keys", adapter_keys)
    online_vote = changes.get("online_vote", online_vote)
    signature = changes.get("identity_signature", sign_commons_identity(identity, hf_key))
    now = changes.get("now", now)
    return run_commons_coordinator_session(
        online_identity=identity,
        online_identity_signature=signature,
        online_manifest=manifest,
        adapter_reports=adapters,
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys=adapter_keys,
        online_votes=(online_vote,),
    )


def _duplicate_adapter_vote_key_rejected() -> bool:
    now, _hf_key, _coordinator, _identity, _manifest, _proposal, _challenge, adapters, _keys, _vote = _fixture()
    shared = Ed25519PrivateKey.generate()
    session, _quorum = _run_with(adapter_keys={adapters[0].node_id: shared, adapters[1].node_id: shared})
    return "distinct_signing_keys" in session.red_gates and not session.quorum_available


def _duplicate_adapter_operator_rejected() -> bool:
    *_prefix, adapters, _keys, _vote = _fixture()
    duplicated = replace(adapters[1], operator_root=adapters[0].operator_root)
    session, _quorum = _run_with(adapters=(adapters[0], duplicated))
    return "adapter_operator_roots_distinct" in session.red_gates and not session.quorum_available


def _stale_epoch_rejected() -> bool:
    now, hf_key, _coordinator, identity, _manifest, _proposal, _challenge, _adapters, _keys, _vote = _fixture()
    stale_identity = replace(identity, governance_epoch="stale-epoch")
    session, _quorum = _run_with(identity=stale_identity, identity_signature=sign_commons_identity(stale_identity, hf_key))
    return "online_hf_admission" in session.red_gates and not session.online_lease_digests


def _expired_challenge_rejected() -> bool:
    now, *_rest = _fixture()
    proposal, challenge = mint_phase4_proposal(
        proposal_digest=sha256_digest({"proposal": "expired"}),
        capability_digest=sha256_digest({"capability": "expired"}),
        evidence_root=sha256_digest({"evidence": "expired"}),
        world_state_hash=sha256_digest({"world": "expired"}),
        governance_epoch="dio-phase4-online-001",
        challenge_nonce="expired-challenge-" + "x" * 24,
        now=now - timedelta(minutes=10),
        ttl_seconds=60,
    )
    session, _quorum = _run_with(proposal=proposal, challenge=challenge, now=now)
    return "online_hf_admission" in session.red_gates and "proposal_not_fresh" in session.red_gates


def _wrong_manifest_rejected() -> bool:
    _now, _hf_key, _coordinator, _identity, manifest, *_rest = _fixture()
    wrong = replace(manifest, capability_ids=("wrong",))
    session, _quorum = _run_with(manifest=wrong)
    return "online_hf_admission" in session.red_gates and not session.online_lease_digests


def _wrong_verifier_rejected() -> bool:
    _now, _hf_key, _coordinator, _identity, manifest, *_rest = _fixture()
    wrong = replace(manifest, verifier_digest=sha256_digest({"verifier": "wrong"}))
    session, _quorum = _run_with(manifest=wrong)
    return "online_hf_admission" in session.red_gates and not session.online_lease_digests


def _attestation_downgrade_rejected() -> bool:
    now, hf_key, _coordinator, identity, _manifest, *_rest = _fixture()
    downgraded = replace(identity, attestation_class="provider_hardware_attestation")
    session, _quorum = _run_with(identity=downgraded, identity_signature=sign_commons_identity(downgraded, hf_key))
    return "online_hf_admission" in session.red_gates and not session.online_lease_digests


def _replayed_challenge_rejected() -> bool:
    now, hf_key, _coordinator, identity, manifest, proposal, challenge, adapters, keys, online_vote = _fixture()
    replayed_proposal, _fresh_challenge = mint_phase4_proposal(
        proposal_digest=proposal.proposal_digest,
        capability_digest=proposal.capability_digest,
        evidence_root=proposal.evidence_root,
        world_state_hash=sha256_digest({"world": "different"}),
        governance_epoch=proposal.governance_epoch,
        challenge_nonce=proposal.challenge_nonce,
        now=now,
    )
    session, _quorum = _run_with(proposal=replayed_proposal, challenge=challenge)
    return "proposal_challenge_binding" in session.red_gates and not session.quorum_available


def _role_collision_rejected() -> bool:
    *_prefix, adapters, _keys, _vote = _fixture()
    collision = replace(adapters[1], role=adapters[0].role)
    session, _quorum = _run_with(adapters=(adapters[0], collision))
    return "governance_witness_required" in session.red_gates and not session.quorum_available


def _authenticated_veto_blocks_quorum() -> bool:
    now, hf_key, _coordinator, identity, manifest, proposal, challenge, adapters, keys, _vote = _fixture()
    veto = sign_dio_vote(
        replace(_online_vote(identity, proposal, hf_key, now=now), decision=DIOVoteDecision.VETO, vote_signature=""),
        hf_key,
    )
    session, _quorum = _run_with(
        identity=identity,
        identity_signature=sign_commons_identity(identity, hf_key),
        manifest=manifest,
        proposal=proposal,
        challenge=challenge,
        adapters=adapters,
        adapter_keys=keys,
        online_vote=veto,
        now=now,
    )
    return "authenticated_veto_blocks_execution" in session.red_gates and not session.quorum_available


def _adapter_persistence_inflation_rejected() -> bool:
    *_prefix, adapters, _keys, _vote = _fixture()
    try:
        replace(adapters[0], persistent_service=True, online_protocol_ready=True, identity_signature_present=False, challenge_endpoint_present=False)
    except ValueError:
        return True
    return False


def _adapter(node_id: str, role: str, attestation_class: str, authority: str, provider: str, operator: str) -> DIOCommonsSpaceAdapterReport:
    return DIOCommonsSpaceAdapterReport(
        beast_object_type="dio_commons_space_adapter_report",
        version="2026-08-04.phase4.commons-adapter.v1",
        adapter_kind="arda_local_physical" if provider == "local" else "aws_nitro_tpm",
        node_id=node_id,
        role=role,
        operator_root=operator,
        runtime_platform=f"{provider}:runtime",
        infrastructure_provider=provider,
        attestation_class=attestation_class,
        maximum_authority=authority,
        capability_manifest_digest=sha256_digest({"manifest": node_id}),
        source_receipt_digest=sha256_digest({"receipt": node_id}),
        source_verification_digest=sha256_digest({"verification": node_id}),
        persistent_service=False,
        online_protocol_ready=False,
        identity_signature_present=False,
        challenge_endpoint_present=False,
        red_gates=(),
        adapted=True,
    )


def _online_vote(identity: DIOCommonsSpaceIdentity, proposal, key: Ed25519PrivateKey, *, now: datetime) -> DIORemoteWitnessVote:
    return sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=identity.node_id,
            role=identity.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=identity.verifier_digest,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root,),
            reason_codes=("phase4_gauntlet_online_vote",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HF_SOFTWARE_WITNESS_AUTHORITY,
        ),
        key,
    )


def _public_key_b64(key: Ed25519PrivateKey) -> str:
    from app.kernel.dai.dio_distributed_quorum import public_key_b64
    return public_key_b64(key.public_key())


def _public_key_fingerprint(public_key: str) -> str:
    from app.kernel.dai.dio_distributed_quorum import public_key_fingerprint
    return public_key_fingerprint(public_key)


if __name__ == "__main__":
    raise SystemExit(main())
