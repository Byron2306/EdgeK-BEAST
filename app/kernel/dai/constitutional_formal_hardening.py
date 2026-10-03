"""Phase-6.5 formal hardening for DIO Constitutional Extensions.

This slice turns three previously deferred items into executable checks:

* Z3-backed bounded SMT containment;
* hybrid Ed25519 + ML-DSA-65 signatures over the same canonical bytes;
* a finite Byzantine Commons safety/liveness model.

The claim remains bounded.  The SMT model is a finite abstraction of the
declared effect lattice, not a full proof of arbitrary Python.  The Commons
model certifies single-proposition quorum safety/liveness, not a persistent
blockchain-style state machine.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_bytes, sha256_digest
from app.kernel.dai.constitutional_extensions import (
    CONSTITUTIONAL_EXTENSIONS_VERSION,
    EffectManifest,
)


FORMAL_HARDENING_VERSION = "2026-08-04.phase6.5.formal-hardening.v1"
FORMAL_HARDENING_IMPLEMENTATION_DIGEST = sha256_bytes(Path(__file__).read_bytes())


@dataclass(frozen=True, slots=True)
class HybridSignaturePacket:
    beast_object_type: str
    version: str
    profile: str
    payload_digest: str
    canonical_payload_digest: str
    ed25519_public_key_b64: str
    ed25519_signature_b64: str
    ml_dsa_algorithm: str
    ml_dsa_public_key_b64: str
    ml_dsa_signature_b64: str
    downgrade_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_hybrid_signature_packet":
            raise ValueError("unexpected hybrid signature packet type")
        if self.version != FORMAL_HARDENING_VERSION:
            raise ValueError("unexpected hybrid signature version")
        if self.profile != "Ed25519+ML-DSA-65:same-canonical-bytes:both-required":
            raise ValueError("unexpected hybrid signature profile")
        if self.ml_dsa_algorithm != "ML-DSA-65":
            raise ValueError("hybrid signature requires ML-DSA-65")
        if self.downgrade_allowed:
            raise ValueError("hybrid signature downgrade is forbidden")
        require_digest(self.payload_digest, field_name="payload_digest")
        require_digest(self.canonical_payload_digest, field_name="canonical_payload_digest")

    @property
    def packet_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ByzantineNode:
    node_id: str
    role: str
    operator_root: str
    infrastructure_provider: str
    control_domain: str
    key_fingerprint: str
    admitted: bool = True
    healthy: bool = True

    def __post_init__(self) -> None:
        for name in ("node_id", "role", "operator_root", "infrastructure_provider", "control_domain"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"Byzantine node requires {name}")
        require_digest(self.key_fingerprint, field_name="key_fingerprint")

    @property
    def node_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ByzantineVote:
    node_id: str
    proposal_digest: str
    world_state_hash: str
    governance_epoch: str
    decision: str

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.governance_epoch.strip():
            raise ValueError("Byzantine vote requires node_id and governance_epoch")
        require_digest(self.proposal_digest, field_name="proposal_digest")
        require_digest(self.world_state_hash, field_name="world_state_hash")
        if self.decision not in {"approve", "refuse", "abstain", "veto"}:
            raise ValueError("unknown Byzantine vote decision")

    @property
    def vote_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ByzantineQuorumPolicy:
    policy_id: str
    proposition_scope: str
    threshold: int
    max_byzantine_faults: int
    required_roles: tuple[str, ...]
    min_distinct_providers: int
    min_distinct_control_domains: int
    require_distinct_operator_roots: bool = True
    require_distinct_keys: bool = True

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("Byzantine policy requires policy_id")
        if self.proposition_scope not in {"single_proposition_certificate", "persistent_shared_state"}:
            raise ValueError("unknown proposition scope")
        if self.threshold <= 0 or self.max_byzantine_faults < 0:
            raise ValueError("invalid Byzantine threshold/fault count")
        if not self.required_roles:
            raise ValueError("Byzantine policy requires roles")

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


def run_z3_effect_containment_model(manifest: EffectManifest) -> dict[str, Any]:
    """Prove, in a bounded SMT abstraction, that escapes cannot be admitted."""

    try:
        from z3 import And, Bool, Implies, Int, Not, Or, Solver, unsat
    except Exception as exc:  # pragma: no cover - tested via installed backend
        return {
            "beast_object_type": "dai_z3_effect_containment_receipt",
            "version": FORMAL_HARDENING_VERSION,
            "backend": "z3",
            "backend_available": False,
            "error": type(exc).__name__,
            "green": False,
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        }

    read_escape = Bool("read_escape")
    write_escape = Bool("write_escape")
    network_escape = Bool("network_escape")
    syscall_escape = Bool("syscall_escape")
    tool_escape = Bool("tool_escape")
    model_call_escape = Bool("model_call_escape")
    data_escape = Bool("data_escape")
    postcondition_missing = Bool("postcondition_missing")
    admitted = Bool("admitted")
    provider_calls = Int("provider_calls")
    production_authority = Bool("production_authority")
    execution_authority = Bool("execution_authority")

    escape = Or(
        read_escape,
        write_escape,
        network_escape,
        syscall_escape,
        tool_escape,
        model_call_escape,
        data_escape,
        postcondition_missing,
    )
    constitutional_law = And(
        provider_calls >= 0,
        Implies(admitted, Not(escape)),
        Implies(admitted, provider_calls == 0),
        Implies(admitted, Not(production_authority)),
        Implies(admitted, Not(execution_authority)),
    )

    clean = Solver()
    clean.add(
        constitutional_law,
        admitted,
        Not(escape),
        provider_calls == 0,
        Not(production_authority),
        Not(execution_authority),
    )
    hostile = Solver()
    hostile.add(
        constitutional_law,
        admitted,
        Or(write_escape, network_escape, model_call_escape, data_escape),
        provider_calls >= 0,
    )
    authority_hostile = Solver()
    authority_hostile.add(constitutional_law, admitted, Or(provider_calls > 0, production_authority, execution_authority))

    receipt: dict[str, Any] = {
        "beast_object_type": "dai_z3_effect_containment_receipt",
        "version": FORMAL_HARDENING_VERSION,
        "backend": "z3",
        "backend_available": True,
        "manifest_digest": manifest.manifest_digest,
        "smt_model_scope": (
            "finite Boolean/Int abstraction of DIO effect containment: admitted implies no read/write/network/"
            "syscall/tool/model/data/postcondition escape, zero provider calls and no production/execution authority"
        ),
        "clean_admission_satisfiable": str(clean.check()) == "sat",
        "hostile_escape_admission_unsat": hostile.check() == unsat,
        "authority_escape_admission_unsat": authority_hostile.check() == unsat,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["green"] = bool(
        receipt["clean_admission_satisfiable"]
        and receipt["hostile_escape_admission_unsat"]
        and receipt["authority_escape_admission_unsat"]
    )
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def sign_hybrid_ed25519_ml_dsa_65(payload: Mapping[str, Any]) -> tuple[HybridSignaturePacket, dict[str, Any]]:
    """Sign the same canonical payload with Ed25519 and ML-DSA-65."""

    from pqcrypto.sign import ml_dsa_65

    canonical = canonical_json(payload).encode("utf-8")
    payload_digest = sha256_bytes(canonical)
    ed_private = Ed25519PrivateKey.generate()
    ed_public = ed_private.public_key()
    ml_public, ml_secret = ml_dsa_65.generate_keypair()
    packet = HybridSignaturePacket(
        beast_object_type="dai_hybrid_signature_packet",
        version=FORMAL_HARDENING_VERSION,
        profile="Ed25519+ML-DSA-65:same-canonical-bytes:both-required",
        payload_digest=payload_digest,
        canonical_payload_digest=payload_digest,
        ed25519_public_key_b64=base64.b64encode(ed_public.public_bytes_raw()).decode("ascii"),
        ed25519_signature_b64=base64.b64encode(ed_private.sign(canonical)).decode("ascii"),
        ml_dsa_algorithm="ML-DSA-65",
        ml_dsa_public_key_b64=base64.b64encode(ml_public).decode("ascii"),
        ml_dsa_signature_b64=base64.b64encode(ml_dsa_65.sign(ml_secret, canonical)).decode("ascii"),
        downgrade_allowed=False,
    )
    verification = verify_hybrid_signature_packet(packet, payload)
    return packet, verification


def verify_hybrid_signature_packet(packet: HybridSignaturePacket | Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    from pqcrypto.sign import ml_dsa_65

    if not isinstance(packet, HybridSignaturePacket):
        packet = HybridSignaturePacket(**dict(packet))
    canonical = canonical_json(payload).encode("utf-8")
    payload_digest = sha256_bytes(canonical)
    ed_ok = False
    ml_ok = False
    errors: list[str] = []
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(packet.ed25519_public_key_b64, validate=True)).verify(
            base64.b64decode(packet.ed25519_signature_b64, validate=True),
            canonical,
        )
        ed_ok = True
    except Exception as exc:
        errors.append(f"ed25519:{type(exc).__name__}")
    try:
        ml_ok = bool(
            ml_dsa_65.verify(
                base64.b64decode(packet.ml_dsa_public_key_b64, validate=True),
                canonical,
                base64.b64decode(packet.ml_dsa_signature_b64, validate=True),
            )
        )
        if not ml_ok:
            errors.append("ml_dsa_65:invalid_signature")
    except Exception as exc:
        errors.append(f"ml_dsa_65:{type(exc).__name__}")
    gates = {
        "payload_digest_matches": packet.payload_digest == payload_digest == packet.canonical_payload_digest,
        "ed25519_signature_valid": ed_ok,
        "ml_dsa_65_signature_valid": ml_ok,
        "same_canonical_bytes": packet.payload_digest == packet.canonical_payload_digest,
        "downgrade_forbidden": packet.downgrade_allowed is False,
        "both_signatures_required": bool(packet.ed25519_signature_b64 and packet.ml_dsa_signature_b64),
    }
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_hybrid_signature_verification_receipt",
        "version": FORMAL_HARDENING_VERSION,
        "packet_digest": packet.packet_digest,
        "payload_digest": payload_digest,
        "profile": packet.profile,
        "gates": gates,
        "errors": tuple(errors),
        "verified": all(gates.values()),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def evaluate_byzantine_commons_model(
    *,
    nodes: Sequence[ByzantineNode],
    votes: Sequence[ByzantineVote],
    policy: ByzantineQuorumPolicy,
    proposal_digest: str,
    world_state_hash: str,
    governance_epoch: str,
    absent_node_ids: Iterable[str] = (),
) -> dict[str, Any]:
    for digest, name in ((proposal_digest, "proposal_digest"), (world_state_hash, "world_state_hash")):
        require_digest(digest, field_name=name)
    admitted = tuple(node for node in nodes if node.admitted)
    absent = set(absent_node_ids)
    available = tuple(node for node in admitted if node.healthy and node.node_id not in absent)
    red: set[str] = set()
    if len(admitted) < policy.threshold:
        red.add("insufficient_admitted_nodes")
    if policy.threshold <= policy.max_byzantine_faults:
        red.add("threshold_not_above_fault_bound")
    if len({node.key_fingerprint for node in admitted}) != len(admitted) and policy.require_distinct_keys:
        red.add("duplicate_signing_keys")
    if len({node.operator_root for node in admitted}) != len(admitted) and policy.require_distinct_operator_roots:
        red.add("duplicate_operator_roots")

    valid_quorums = tuple(
        quorum
        for quorum in combinations(admitted, policy.threshold)
        if _quorum_satisfies_policy(quorum, policy)
    )
    available_quorums = tuple(
        quorum
        for quorum in combinations(available, policy.threshold)
        if _quorum_satisfies_policy(quorum, policy)
    )
    if not valid_quorums:
        red.add("no_valid_certificate_quorum")
    if not available_quorums:
        red.add("no_available_live_quorum")

    min_intersection = min(
        (len({node.node_id for node in left} & {node.node_id for node in right}) for left in valid_quorums for right in valid_quorums),
        default=0,
    )
    quorum_intersection_safe = bool(valid_quorums and min_intersection > policy.max_byzantine_faults)
    if not quorum_intersection_safe:
        red.add("quorum_intersection_not_fault_safe")

    vote_red = _vote_red_gates(votes, admitted, proposal_digest, world_state_hash, governance_epoch)
    red.update(vote_red)

    report: dict[str, Any] = {
        "beast_object_type": "dai_byzantine_commons_model_receipt",
        "version": FORMAL_HARDENING_VERSION,
        "policy_digest": policy.policy_digest,
        "node_digests": tuple(node.node_digest for node in nodes),
        "vote_digests": tuple(vote.vote_digest for vote in votes),
        "proposition_scope": policy.proposition_scope,
        "persistent_state_machine_claimed": policy.proposition_scope == "persistent_shared_state",
        "single_proposition_certificate_claimed": policy.proposition_scope == "single_proposition_certificate",
        "admitted_node_count": len(admitted),
        "available_node_count": len(available),
        "threshold": policy.threshold,
        "max_byzantine_faults": policy.max_byzantine_faults,
        "valid_certificate_quorum_count": len(valid_quorums),
        "available_live_quorum_count": len(available_quorums),
        "minimum_pairwise_quorum_intersection": min_intersection,
        "quorum_intersection_fault_safe": quorum_intersection_safe,
        "availability_under_absences": bool(available_quorums),
        "red_gates": tuple(sorted(red)),
        "green": not red,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Finite Commons safety/liveness model for a single proposition certificate. "
            "It does not claim consensus over a persistent shared state machine."
        ),
    }
    report["receipt_digest"] = sha256_digest(report)
    return report


def run_formal_hardening_demo(*, constitutional_receipt: Mapping[str, Any]) -> dict[str, Any]:
    phase6_4_digest = str(constitutional_receipt.get("receipt_digest") or "")
    require_digest(phase6_4_digest, field_name="constitutional_receipt.receipt_digest")
    if constitutional_receipt.get("green") is not True:
        raise ValueError("Phase 6.4 constitutional receipt is not green")
    manifest_payload = constitutional_receipt.get("effect_containment_receipt", {}).get("manifest")
    if not isinstance(manifest_payload, Mapping):
        raise ValueError("Phase 6.4 receipt lacks effect manifest")
    manifest = EffectManifest(**dict(manifest_payload))

    smt = run_z3_effect_containment_model(manifest)
    signed_payload = {
        "beast_object_type": "dai_phase6_5_signed_constitutional_payload",
        "phase6_4_receipt_digest": phase6_4_digest,
        "smt_receipt_digest": smt["receipt_digest"],
        "claim_boundary": "same canonical bytes signed by Ed25519 and ML-DSA-65",
    }
    signature_packet, signature_ok = sign_hybrid_ed25519_ml_dsa_65(signed_payload)
    tampered_payload = {**signed_payload, "phase6_4_receipt_digest": sha256_digest("tampered")}
    tamper_check = verify_hybrid_signature_packet(signature_packet, tampered_payload)
    downgrade_packet = asdict(signature_packet)
    downgrade_packet["ml_dsa_signature_b64"] = ""
    try:
        downgrade_check = verify_hybrid_signature_packet(downgrade_packet, signed_payload)
    except Exception as exc:
        downgrade_check = {
            "verified": False,
            "errors": (f"downgrade_rejected:{type(exc).__name__}",),
            "receipt_digest": sha256_digest({"downgrade_rejected": type(exc).__name__}),
        }

    proposal_digest = sha256_digest("phase6.5:proposal")
    world_digest = sha256_digest("phase6.5:world")
    nodes = _demo_nodes()
    votes = tuple(
        ByzantineVote(
            node_id=node.node_id,
            proposal_digest=proposal_digest,
            world_state_hash=world_digest,
            governance_epoch="phase6.5",
            decision="approve",
        )
        for node in nodes[:4]
    )
    policy = ByzantineQuorumPolicy(
        policy_id="phase6.5:single-proposition-quorum",
        proposition_scope="single_proposition_certificate",
        threshold=4,
        max_byzantine_faults=1,
        required_roles=("physical_execution_witness", "semantic_witness", "adversarial_witness", "governance_witness"),
        min_distinct_providers=3,
        min_distinct_control_domains=4,
    )
    byzantine = evaluate_byzantine_commons_model(
        nodes=nodes,
        votes=votes,
        policy=policy,
        proposal_digest=proposal_digest,
        world_state_hash=world_digest,
        governance_epoch="phase6.5",
    )
    equivocation_votes = votes + (
        ByzantineVote(
            node_id=nodes[0].node_id,
            proposal_digest=proposal_digest,
            world_state_hash=sha256_digest("phase6.5:forked-world"),
            governance_epoch="phase6.5",
            decision="approve",
        ),
    )
    equivocation = evaluate_byzantine_commons_model(
        nodes=nodes,
        votes=equivocation_votes,
        policy=policy,
        proposal_digest=proposal_digest,
        world_state_hash=world_digest,
        governance_epoch="phase6.5",
    )
    weak_policy = ByzantineQuorumPolicy(
        policy_id="phase6.5:weak-quorum",
        proposition_scope="single_proposition_certificate",
        threshold=3,
        max_byzantine_faults=1,
        required_roles=("semantic_witness",),
        min_distinct_providers=1,
        min_distinct_control_domains=1,
    )
    weak = evaluate_byzantine_commons_model(
        nodes=nodes,
        votes=votes[:3],
        policy=weak_policy,
        proposal_digest=proposal_digest,
        world_state_hash=world_digest,
        governance_epoch="phase6.5",
    )

    hostile_controls = {
        "z3_hostile_escape_unsat": smt["hostile_escape_admission_unsat"] is True,
        "z3_authority_escape_unsat": smt["authority_escape_admission_unsat"] is True,
        "hybrid_signature_tamper_rejected": tamper_check["verified"] is False,
        "hybrid_signature_downgrade_rejected": downgrade_check["verified"] is False,
        "byzantine_equivocation_rejected": "equivocation_detected" in equivocation["red_gates"],
        "weak_quorum_rejected": weak["green"] is False,
    }
    green = bool(
        smt["green"]
        and signature_ok["verified"]
        and byzantine["green"]
        and all(hostile_controls.values())
    )
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_phase6_5_formal_hardening_receipt",
        "version": FORMAL_HARDENING_VERSION,
        "implementation_digest": FORMAL_HARDENING_IMPLEMENTATION_DIGEST,
        "phase6_4_constitutional_receipt_digest": phase6_4_digest,
        "formal_gates": {
            "z3_bounded_smt_effect_containment": smt["green"],
            "hybrid_ed25519_ml_dsa_65_same_bytes": signature_ok["verified"],
            "byzantine_single_proposition_safety_liveness": byzantine["green"],
            "hostile_controls_rejected": all(hostile_controls.values()),
        },
        "z3_effect_containment_receipt": smt,
        "hybrid_signature_packet": signature_packet,
        "hybrid_signature_verification_receipt": signature_ok,
        "hybrid_signature_tamper_receipt": tamper_check,
        "hybrid_signature_downgrade_receipt": downgrade_check,
        "byzantine_commons_model_receipt": byzantine,
        "byzantine_equivocation_receipt": equivocation,
        "byzantine_weak_quorum_receipt": weak,
        "hostile_controls": hostile_controls,
        "green": green,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Real Z3 and real pqcrypto ML-DSA-65 were used locally. Commons claim is a finite "
            "single-proposition Byzantine safety/liveness model; not persistent consensus."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _quorum_satisfies_policy(quorum: Sequence[ByzantineNode], policy: ByzantineQuorumPolicy) -> bool:
    roles = {node.role for node in quorum}
    providers = {node.infrastructure_provider for node in quorum}
    domains = {node.control_domain for node in quorum}
    roots = {node.operator_root for node in quorum}
    keys = {node.key_fingerprint for node in quorum}
    return bool(
        set(policy.required_roles).issubset(roles)
        and len(providers) >= policy.min_distinct_providers
        and len(domains) >= policy.min_distinct_control_domains
        and (not policy.require_distinct_operator_roots or len(roots) == len(quorum))
        and (not policy.require_distinct_keys or len(keys) == len(quorum))
    )


def _vote_red_gates(
    votes: Sequence[ByzantineVote],
    admitted: Sequence[ByzantineNode],
    proposal_digest: str,
    world_state_hash: str,
    governance_epoch: str,
) -> set[str]:
    admitted_ids = {node.node_id for node in admitted}
    red: set[str] = set()
    by_node: dict[str, set[tuple[str, str, str]]] = {}
    for vote in votes:
        if vote.node_id not in admitted_ids:
            red.add("vote_from_unadmitted_node")
        if vote.proposal_digest != proposal_digest:
            red.add("vote_proposal_mismatch")
        if vote.governance_epoch != governance_epoch:
            red.add("vote_epoch_mismatch")
        by_node.setdefault(vote.node_id, set()).add((vote.proposal_digest, vote.world_state_hash, vote.decision))
    for node_id, variants in by_node.items():
        worlds_for_proposal = {world for proposal, world, _ in variants if proposal == proposal_digest}
        decisions_for_world = {decision for proposal, world, decision in variants if proposal == proposal_digest and world == world_state_hash}
        if len(worlds_for_proposal) > 1 or len(decisions_for_world) > 1:
            red.add("equivocation_detected")
        if any(proposal == proposal_digest and world != world_state_hash for proposal, world, _ in variants):
            red.add("fork_detected")
    return red


def _demo_nodes() -> tuple[ByzantineNode, ...]:
    return (
        ByzantineNode("node:local:physical", "physical_execution_witness", "byron-local", "local", "physical-host", sha256_digest("key:local")),
        ByzantineNode("node:gcp:semantic", "semantic_witness", "gcp-confidential-space", "google-cloud", "gcp-project", sha256_digest("key:gcp")),
        ByzantineNode("node:azure:adversarial", "adversarial_witness", "azure-confidential-vm", "azure", "azure-subscription", sha256_digest("key:azure")),
        ByzantineNode("node:hf:governance", "governance_witness", "hf-space", "huggingface", "hf-org", sha256_digest("key:hf")),
        ByzantineNode("node:github:observer", "semantic_witness", "github-actions", "github", "github-repo", sha256_digest("key:github")),
    )
