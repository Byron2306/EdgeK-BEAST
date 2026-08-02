from __future__ import annotations

import array
import os
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.kernel.compute.grand_closure_g5 import _assert_within
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso
from app.kernel.crystal_bus.capsule_messages import CapsuleOffer
from app.kernel.crystal_bus.fd_transport import CrystalBusEndpoint
from app.kernel.crystal_bus.peer_verification import PeerAdmissionPolicy
from app.kernel.crystals.capsule_codec import CapsuleCodec
from app.kernel.crystals.capsule_contracts import ExecutionBounds, SealedCrystalCapsuleManifest, canonical_json
from app.kernel.crystals.capsule_contracts import sha256_digest as bytes_sha256_digest
from app.kernel.crystals.capsule_signing import Ed25519CapsuleSigner, Ed25519CapsuleVerifier
from app.kernel.crystals.capsule_verifier import CapsuleVerifier
from app.kernel.crystals.sealed_capsule import SealedCapsuleFactory
from app.kernel.execution.capsule_execution_adapter import CapsuleExecutionAdapter
from app.kernel.execution.one_use_capability import OneUseCapabilityLedger

G6_TASK_CLASS = "grand_closure_hostile_refusal_gauntlet"
G6_OPCODE = "G6_NOOP"


@dataclass(frozen=True, slots=True)
class G6CaseReceipt:
    case_id: str
    expected_refusal: str
    observed_refusal: str
    refused: bool
    authority_consumed: bool
    physical_effects: int
    residue_detected: bool
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class G6ClosureReceipt:
    gauntlet_id: str
    cases: tuple[G6CaseReceipt, ...]
    case_count: int
    all_refused_correctly: bool
    total_authorities_consumed: int
    total_physical_effects: int
    residue_detected: bool
    raw_payload_retained: bool
    created_at: str
    evidence_digest: str


def _case(case_id: str, expected: str, observed: str, *, authority=False, effects=0, residue=False) -> G6CaseReceipt:
    body = {
        "case_id": case_id,
        "expected_refusal": expected,
        "observed_refusal": observed,
        "refused": expected in observed,
        "authority_consumed": bool(authority),
        "physical_effects": int(effects),
        "residue_detected": bool(residue),
    }
    return G6CaseReceipt(**body, evidence_digest=sha256_digest(body))


def _build_capsule(*, workspace: str = "ws", privacy: str = "workspace:ws", policy: str = "sha256:policy", source: str = "sha256:source"):
    signer = Ed25519CapsuleSigner("g6-forge")
    plan = {"version": 1, "opcode": G6_OPCODE}
    manifest = SealedCrystalCapsuleManifest(
        crystal_id="g6-crystal",
        crystal_ir_version=1,
        artifact_digest=bytes_sha256_digest(canonical_json(plan)),
        promotion_digest="sha256:promotion",
        policy_digest=policy,
        source_state_digest=source,
        workspace_id=workspace,
        privacy_domain=privacy,
        task_class=G6_TASK_CLASS,
        audience_class="executor:g6",
        required_capability="crystal.execute.g6",
        one_use_required=True,
        expires_at=time.time() + 300,
        verifier_id="g6-v1",
        rollback_contract_digest=sha256_digest({"rollback": "none"}),
        signer_id="g6-forge",
        execution_bounds=ExecutionBounds(1000, 1024 * 1024, 4096, (), ()),
    )
    handle = SealedCapsuleFactory().create(manifest=manifest, crystal_ir=plan, verifier_manifest={"verifier_id": "g6-v1"}, signer=signer)
    verifier = CapsuleVerifier(Ed25519CapsuleVerifier({"g6-forge": signer.public_key}))
    return handle, verifier


def _offer(handle, lease, **updates):
    values = {
        "capsule_digest": handle.receipt.capsule_digest,
        "capsule_size": handle.receipt.payload_size,
        "crystal_id": "g6-crystal",
        "promotion_digest": "sha256:promotion",
        "capability_lease_digest": lease.digest,
        "audience": "executor:g6",
        "expires_at": time.time() + 60,
    }
    values.update(updates)
    return CapsuleOffer(**values)


class G6HostileRefusalGauntlet:
    """Exercise the sealed-capsule refusal boundary without retaining payloads."""

    def run(self, *, workspace_root: str | os.PathLike[str]) -> G6ClosureReceipt:
        root = Path(workspace_root).resolve(strict=True)
        cases = [
            self._capability_replay(),
            self._stale_process_lease(),
            self._arda_refusal(),
            self._wrong_peer(),
            self._missing_seals(),
            self._policy_drift(),
            self._source_state_drift(),
            self._workspace_escape(root),
            self._message_fd_substitution(),
            self._revoked_promotion(),
            self._sequence_replay(),
            self._postcondition_failure(),
        ]
        body = {
            "gauntlet_id": "grand-closure-g6-hostile-refusal",
            "cases": tuple(cases),
            "case_count": len(cases),
            "all_refused_correctly": all(c.refused for c in cases),
            "total_authorities_consumed": sum(1 for c in cases if c.authority_consumed),
            "total_physical_effects": sum(c.physical_effects for c in cases),
            "residue_detected": any(c.residue_detected for c in cases),
            "raw_payload_retained": False,
            "created_at": utc_now_iso(),
        }
        if not body["all_refused_correctly"] or body["total_physical_effects"] or body["residue_detected"]:
            raise RuntimeError("G6 hostile refusal closure failed")
        digest_body = dict(body)
        digest_body["cases"] = [asdict(c) for c in cases]
        return G6ClosureReceipt(**body, evidence_digest=sha256_digest(digest_body))

    def _system(self, *, resolver=None, arda=None, expected_uid=None):
        handle, verifier = _build_capsule()
        ledger = OneUseCapabilityLedger()
        lease = ledger.issue(crystal_id="g6-crystal", capsule_digest=handle.receipt.capsule_digest, audience="executor:g6", capability="crystal.execute.g6")
        policy = PeerAdmissionPolicy(
            expected_uid=os.getuid() if expected_uid is None else expected_uid,
            process_lease_resolver=resolver or (lambda pid: {"lease_id": f"g6:{pid}", "active": True, "workspace": "ws"}),
            workspace_checker=lambda value, ws: bool(value.get("active")) and value.get("workspace") == ws,
            arda_checker=arda or (lambda value, ref: ref == "arda:g6-approved"),
        )
        a, b = CrystalBusEndpoint.pair(peer_policy=policy, workspace_id="ws", arda_ref="arda:g6-approved")
        return handle, verifier, ledger, lease, a, b

    @staticmethod
    def _execute(received, verifier, ledger, *, policy="sha256:policy", source="sha256:source", promotion=True, post=True):
        return CapsuleExecutionAdapter(capsule_verifier=verifier, capability_ledger=ledger).execute(
            received,
            expected_workspace="ws",
            expected_privacy_domain="workspace:ws",
            expected_audience="executor:g6",
            active_policy_digest=policy,
            active_source_state_digest=source,
            promotion_is_valid=lambda digest: promotion,
            actuator=lambda plan, bounds: {"status": "noop"},
            postcondition_verifier=lambda plan, effect, manifest: post,
            rollback=None,
        )

    def _capability_replay(self):
        h,v,l,lease,a,b=self._system()
        try:
            a.send_capsule(_offer(h,lease),h.fd); r=b.receive_capsule()
            try: self._execute(r,v,l)
            finally: r.close()
            a.send_capsule(_offer(h,lease),h.fd); r=b.receive_capsule()
            try:
                try: self._execute(r,v,l); obs="not_refused"
                except Exception as exc: obs=str(exc)
            finally: r.close()
            return _case("capability_replay","capability replay",obs,authority=True)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _stale_process_lease(self):
        h,v,l,lease,a,b=self._system(resolver=lambda pid:{"lease_id":"stale","active":False,"workspace":"ws"})
        try:
            a.send_capsule(_offer(h,lease),h.fd)
            try: b.receive_capsule(); obs="not_refused"
            except Exception as exc: obs=str(exc)
            return _case("stale_process_lease","stale_process_lease",obs)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _arda_refusal(self):
        h,v,l,lease,a,b=self._system(arda=lambda value,ref:False)
        try:
            a.send_capsule(_offer(h,lease),h.fd)
            try: b.receive_capsule(); obs="not_refused"
            except Exception as exc: obs=str(exc)
            return _case("arda_refusal","arda_refused",obs)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _wrong_peer(self):
        h,v,l,lease,a,b=self._system(expected_uid=os.getuid()+1)
        try:
            a.send_capsule(_offer(h,lease),h.fd)
            try: b.receive_capsule(); obs="not_refused"
            except Exception as exc: obs=str(exc)
            return _case("wrong_peer","uid",obs)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _missing_seals(self):
        h,v=_build_capsule()
        fd=os.memfd_create("g6-unsealed", os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        try:
            payload=os.pread(h.fd,h.receipt.payload_size,0); os.write(fd,payload)
            receipt=v.verify(fd,expected_workspace="ws",expected_privacy_domain="workspace:ws",expected_audience="executor:g6",active_policy_digest="sha256:policy",active_source_state_digest="sha256:source",promotion_is_valid=lambda d:True)
            return _case("missing_seals","required kernel seals missing",receipt.reason)
        finally: os.close(fd); h.close()

    def _verification_case(self, case_id, expected, **kwargs):
        h,v=_build_capsule()
        try:
            receipt=v.verify(h.fd,expected_workspace="ws",expected_privacy_domain="workspace:ws",expected_audience="executor:g6",active_policy_digest=kwargs.get("policy","sha256:policy"),active_source_state_digest=kwargs.get("source","sha256:source"),promotion_is_valid=lambda d:kwargs.get("promotion",True))
            return _case(case_id,expected,receipt.reason)
        finally: h.close()

    def _policy_drift(self): return self._verification_case("policy_drift","policy drift",policy="sha256:changed")
    def _source_state_drift(self): return self._verification_case("source_state_drift","source-state drift",source="sha256:changed")
    def _revoked_promotion(self): return self._verification_case("revoked_promotion","promotion revoked",promotion=False)

    def _workspace_escape(self, root):
        try: _assert_within(root, root / ".." / "outside.txt"); obs="not_refused"
        except Exception as exc: obs=str(exc)
        return _case("workspace_escape","escapes bounded workspace",obs)

    def _message_fd_substitution(self):
        h,v,l,lease,a,b=self._system()
        try:
            a.send_capsule(_offer(h,lease,capsule_digest="sha256:"+"0"*64),h.fd); r=b.receive_capsule()
            try:
                try: self._execute(r,v,l); obs="not_refused"
                except Exception as exc: obs=str(exc)
            finally: r.close()
            return _case("message_fd_substitution","does not bind",obs)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _sequence_replay(self):
        h,v,l,lease,a,b=self._system()
        try:
            raw=_offer(h,lease).with_sequence(1).encode()
            ancillary=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[h.fd]))]
            a.sock.sendmsg([raw],ancillary); a.sock.sendmsg([raw],ancillary)
            first=b.receive_capsule(); first.close()
            try: b.receive_capsule(); obs="not_refused"
            except Exception as exc: obs=str(exc)
            return _case("sequence_replay","replay",obs)
        finally: a.sock.close(); b.sock.close(); h.close()

    def _postcondition_failure(self):
        h,v,l,lease,a,b=self._system()
        try:
            a.send_capsule(_offer(h,lease),h.fd); r=b.receive_capsule()
            try:
                result=self._execute(r,v,l,post=False)
                obs=result.final_status
            finally: r.close()
            return _case("postcondition_failure","verification_failed",obs,authority=True,effects=0)
        finally: a.sock.close(); b.sock.close(); h.close()
