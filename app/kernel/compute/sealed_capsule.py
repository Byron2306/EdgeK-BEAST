"""Sealed memfd crystal payloads with a portable file-backed test fallback."""
from __future__ import annotations

import hashlib
import os
import fcntl
import base64
import time
import json
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class SealedCrystal:
    fd: int
    digest: str
    size: int
    sealed: bool
    signature: str = ""
    authority_ref: str = "beast.local/crystal-forge"
    audience: str = "beast-crystal-executor"
    expires_at: float = 0.0
    capability_ref: str = ""
    appraisal_ref: str = ""

    def signed_envelope(self) -> bytes:
        return json.dumps(
            {
                "appraisal_ref": self.appraisal_ref,
                "audience": self.audience,
                "authority_ref": self.authority_ref,
                "capability_ref": self.capability_ref,
                "expires_at": self.expires_at,
                "payload_digest": self.digest,
                "size": self.size,
                "version": "beast.sealed-crystal.v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class CrystalCapsule:
    def create(self, payload: bytes, *, signer=None, authority_ref: str = "beast.local/crystal-forge", audience: str = "beast-crystal-executor", expires_at: float = 0.0, capability_ref: str = "", appraisal_ref: str = "") -> SealedCrystal:
        if not payload:
            raise ValueError("crystal payload cannot be empty")
        if not hasattr(os, "memfd_create"):
            raise OSError("memfd_create is required for crystal capsules")
        fd = os.memfd_create("beast-crystal", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.write(fd, payload)
        os.lseek(fd, 0, os.SEEK_SET)
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        unsigned = SealedCrystal(fd, digest, len(payload), True, "", authority_ref, audience, expires_at, capability_ref, appraisal_ref)
        signature = base64.b64encode(signer.sign(unsigned.signed_envelope())).decode("ascii") if signer else ""
        return SealedCrystal(fd, digest, len(payload), True, signature, authority_ref, audience, expires_at, capability_ref, appraisal_ref)

    def verify(self, capsule: SealedCrystal, *, verifier=None, expected_authority: str | None = None, expected_audience: str | None = None, capability_ref: str | None = None, appraisal_ref: str | None = None, now: float | None = None) -> bool:
        if expected_authority is not None and capsule.authority_ref != expected_authority:
            return False
        if not capsule.authority_ref:
            return False
        if expected_audience is not None and capsule.audience != expected_audience:
            return False
        if capsule.expires_at and (time.time() if now is None else now) >= capsule.expires_at:
            return False
        if capability_ref is not None and capsule.capability_ref != capability_ref:
            return False
        if appraisal_ref is not None and capsule.appraisal_ref != appraisal_ref:
            return False
        try:
            seals = fcntl.fcntl(capsule.fd, fcntl.F_GET_SEALS)
            required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
            if seals & required != required:
                return False
        except (AttributeError, OSError):
            return False
        if capsule.size <= 0:
            return False
        stat = os.fstat(capsule.fd)
        if stat.st_size != capsule.size:
            return False
        payload = os.pread(capsule.fd, capsule.size, 0)
        if "sha256:" + hashlib.sha256(payload).hexdigest() != capsule.digest:
            return False
        if verifier is not None:
            if not capsule.signature:
                return False
            try:
                verifier.verify(base64.b64decode(capsule.signature, validate=True), capsule.signed_envelope())
            except Exception:
                return False
        return True


import fcntl  # kept below definitions for platforms lacking the module at import time
