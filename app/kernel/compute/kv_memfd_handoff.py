"""Experimental Task 4: zero-copy KV handoff between local processes (IEI v0.9 §7.12 Table 14, Phase 9).

Default-off behind BEAST_ZERO_COPY_KV. A KV payload plus its manifest is written once into a sealed memfd
(F_SEAL_SHRINK|GROW|WRITE|SEAL) and handed to a peer process over the D4 ConsolidatedCrystalBus
(AF_UNIX SOCK_SEQPACKET + SCM_RIGHTS: strict SO_PEERCRED, sequence ledger, one-use lease, signed custody chain).
The receiver mmaps it read-only and gets a zero-copy ``memoryview`` of the payload region.

Gates: Governor admit before every send; manifest privacy must be ``host_local`` and ``publishable`` false;
engine identity (model/tokenizer/engine/version/precision) must match exactly at the receiver; ``reuse_allowed``
stays false until a caller-supplied restore check passes. ``publish`` always refuses: KV never leaves the host.

Claim boundary: transport only. No inference engine exports/imports KV through this path yet; payloads in tests and
benchmarks are synthetic bytes. Restore correctness is the caller's verifier, not a claim made here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import mmap
import os
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

KV_ENV = "BEAST_ZERO_COPY_KV"
SCHEMA = "beast.zero_copy_kv.manifest.v1"
IDENTITY_KEYS = ("model", "tokenizer", "engine", "engine_version", "precision")
SEALS = fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL
HEADER = struct.Struct(">Q")
AUDIENCE = "beast.zero_copy_kv.local"


def kv_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(KV_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass
class KVHandoff:
    manifest: dict[str, Any]
    fd: int
    view: memoryview
    custody_receipt: dict[str, Any]
    _map: Any = field(default=None, repr=False)
    _base: Any = field(default=None, repr=False)

    def close(self) -> None:
        for item in (self.view, self._base):
            if item is not None:
                item.release()
        if self._map is not None:
            self._map.close()
            self._map = None
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class ZeroCopyKVTransport:
    def __init__(self, *, governor: Any = None, env: Mapping[str, str] | None = None, signer: Any = None,
                 signer_id: str = "beast-zero-copy-kv", workspace_id: str = "host-local", authority: Any = None):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from app.kernel.crystal_bus.bus import CustodyChain, OneUseAuthority
        from app.kernel.governance.governor_spine import ComputeGovernorSpine

        self.governor = governor if governor is not None else ComputeGovernorSpine()
        self.env = dict(os.environ if env is None else env)
        self._signer = signer or Ed25519PrivateKey.generate()  # ephemeral, in-memory only; never written to disk
        self.signer_id = signer_id
        self.workspace_id = workspace_id
        self.authority = authority or OneUseAuthority()
        self.custody = CustodyChain(self._signer, signer_id)

    def _require(self) -> None:
        if not kv_enabled(self.env):
            raise PermissionError(f"zero-copy KV transport is disabled (set {KV_ENV}=1)")

    # -- manifest ----------------------------------------------------------------------------------
    def manifest(self, identity: Mapping[str, str], *, system_prompt: str, prompt_prefix: str,
                 payload: bytes) -> dict[str, Any]:
        self._require()
        missing = [k for k in IDENTITY_KEYS if not str(identity.get(k) or "")]
        if missing:
            raise ValueError(f"engine identity incomplete: {missing}")
        body = {"schema": SCHEMA, "engine_identity": {k: str(identity[k]) for k in IDENTITY_KEYS},
                "system_prompt_sha256": _sha(system_prompt.encode()), "prefix_sha256": _sha(prompt_prefix.encode()),
                "payload_sha256": _sha(payload), "payload_bytes": len(payload), "privacy": "host_local",
                "publishable": False, "reuse_allowed": False, "restore_check": {"passed": False},
                "created_at": time.time()}
        body["manifest_digest"] = _sha(_canon(body))
        return body

    @staticmethod
    def _check_manifest(manifest: Mapping[str, Any]) -> None:
        body = {k: v for k, v in manifest.items() if k != "manifest_digest"}
        if manifest.get("privacy") != "host_local" or manifest.get("publishable") is not False:
            raise PermissionError("KV manifest must be host_local and unpublishable")
        if _sha(_canon(body)) != manifest.get("manifest_digest"):
            raise PermissionError("KV manifest digest mismatch")

    def publish(self, manifest: Mapping[str, Any], *_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("zero-copy KV is never published: host-local only (IEI v0.9 §7.12, Phase 9)")

    # -- transport -----------------------------------------------------------------------------------
    def pair(self):
        from app.kernel.crystal_bus import PeerAdmissionPolicy
        from app.kernel.crystal_bus.bus import ConsolidatedCrystalBus

        return ConsolidatedCrystalBus.pair(peer_policy=PeerAdmissionPolicy(expected_uid=os.getuid()),
                                           workspace_id=self.workspace_id, signer=self._signer,
                                           signer_id=self.signer_id, authority=self.authority,
                                           expected_audience=AUDIENCE, custody=self.custody)

    def _seal(self, manifest: Mapping[str, Any], payload: bytes) -> int:
        header = _canon(dict(manifest))
        fd = os.memfd_create("beast-kv", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
        try:
            view = memoryview(HEADER.pack(len(header)) + header)
            os.write(fd, view)
            written = 0
            data = memoryview(payload)
            while written < len(data):
                written += os.write(fd, data[written:])
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
            return fd
        except Exception:
            os.close(fd)
            raise

    def send(self, bus: Any, manifest: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
        from app.kernel.crystal_bus import CapsuleOffer
        from app.kernel.crystal_bus.bus import content_digest
        from app.kernel.governance.governor_spine import Episode, Proposal

        self._require()
        self._check_manifest(manifest)
        if _sha(payload) != manifest["payload_sha256"] or len(payload) != manifest["payload_bytes"]:
            raise ValueError("KV payload does not match its manifest")
        proposal = Proposal(kind="deterministic_tool", tool_id="zero_copy_kv:handoff", targets=("host_local",),
                            signature_material={"manifest": manifest["manifest_digest"]},
                            estimate={"tool_calls": 1.0})
        decision = self.governor.admit(Episode(run_id=f"zero-copy-kv:{manifest['manifest_digest'][7:23]}"), proposal)

        def run() -> dict[str, Any]:
            fd = self._seal(manifest, payload)
            try:
                offer = CapsuleOffer(capsule_digest=content_digest(fd), capsule_size=os.fstat(fd).st_size,
                                     crystal_id="kv:" + manifest["manifest_digest"][7:31],
                                     promotion_digest=manifest["manifest_digest"],
                                     capability_lease_digest=decision.receipt_hash or _sha(decision.receipt_id.encode()),
                                     audience=AUDIENCE, expires_at=time.time() + 30)
                wire = bus.send_capsule(offer, fd)
            finally:
                os.close(fd)  # the peer now holds its own reference to the sealed memfd
            return {"offer": wire, "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id}}

        return self.governor.run_admitted(decision, proposal, run)

    def receive(self, bus: Any, *, expected_identity: Mapping[str, str]) -> KVHandoff:
        self._require()
        transfer = bus.receive_capsule()  # peer creds, sequence, seals, digest, one-use lease, custody
        fd = transfer.fd
        try:
            mapped = mmap.mmap(fd, os.fstat(fd).st_size, access=mmap.ACCESS_READ)
        except Exception:
            transfer.close()
            raise
        base = memoryview(mapped)
        try:
            (length,) = HEADER.unpack(base[:HEADER.size])
            manifest = json.loads(bytes(base[HEADER.size:HEADER.size + length]))
            self._check_manifest(manifest)
            if manifest["manifest_digest"] != transfer.offer.promotion_digest:
                raise PermissionError("KV manifest is not the one offered")
            expected = {k: str(expected_identity.get(k) or "") for k in IDENTITY_KEYS}
            if manifest["engine_identity"] != expected:
                raise PermissionError("KV engine identity mismatch; refusing restore")
            view = base[HEADER.size + length:]
            if view.nbytes != manifest["payload_bytes"]:
                raise ValueError("KV payload size mismatch")
        except Exception:
            base.release()
            mapped.close()
            transfer.close()
            raise
        return KVHandoff(manifest, fd, view, transfer.custody_receipt, mapped, base)

    def verify_restore(self, handoff: KVHandoff, restore_check: Callable[[memoryview], bool]) -> dict[str, Any]:
        passed = bool(restore_check(handoff.view))
        manifest = {k: v for k, v in handoff.manifest.items() if k != "manifest_digest"}
        manifest["reuse_allowed"] = passed
        manifest["restore_check"] = {"passed": passed, "checked_at": time.time(),
                                     "source_manifest_digest": handoff.manifest["manifest_digest"]}
        manifest["manifest_digest"] = _sha(_canon(manifest))
        return manifest

    def verify_custody(self) -> bool:
        from app.kernel.crystal_bus.bus import verify_custody_chain

        return verify_custody_chain(self.custody.receipts, self._signer.public_key())


__all__ = ["KV_ENV", "KVHandoff", "ZeroCopyKVTransport", "kv_enabled"]
