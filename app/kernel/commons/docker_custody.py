"""Signed custody records for Commons nodes running in Docker (Phase 3 ruling D3.3: observe-and-attest).

Docker keeps socket ownership; the Guardian/Sensorium only *attests* that the topology-contract port
``127.0.0.1:811x`` maps to a container whose node descriptor was freshly verified (signed descriptor digest from a
live probe, not container metadata alone). Records are Ed25519-signed, expire, and grant nothing: Commons stays
``verify_only``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCHEMA = "beast.commons.docker_custody.v1"
FRESH_SECONDS = 300.0
RECORD_TTL_SECONDS = 300.0


class CustodyRefused(ValueError):  # noqa: N818 - public name used by callers/tests
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _body(record: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in {"signature", "record_digest"}}


def default_container(node_id: str) -> str:
    return f"compose:{node_id}"


class DockerCustodyAttestor:
    def __init__(self, signer: Ed25519PrivateKey, *, signer_id: str, topology: Any,
                 container_resolver: Callable[[str, int], str] | None = None,
                 fresh_seconds: float = FRESH_SECONDS, ttl_seconds: float = RECORD_TTL_SECONDS):
        if not signer_id:
            raise ValueError("custody signer id required")
        self._signer = signer
        self.signer_id = signer_id
        self.topology = topology
        self.container_resolver = container_resolver or (lambda node_id, _port: default_container(node_id))
        self.fresh_seconds = float(fresh_seconds)
        self.ttl_seconds = float(ttl_seconds)

    def attest(self, row: Mapping[str, Any], *, container: str = "", now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else float(now)
        node_id = str(row.get("node_id") or "")
        parsed = urlsplit(str(row.get("endpoint") or ""))
        port = parsed.port
        contract = dict(self.topology.commons_nodes)
        if node_id not in contract or port != int(contract[node_id]) or parsed.hostname != "127.0.0.1":
            raise CustodyRefused("published_port_outside_topology_contract")
        digest = str(row.get("descriptor_digest") or "")
        age = now - float(row.get("checked_at") or 0)
        if row.get("status") != "healthy" or not digest.startswith("sha256:") or age > self.fresh_seconds:
            raise CustodyRefused("descriptor_not_freshly_verified")
        record = {
            "schema": SCHEMA,
            "node_id": node_id,
            "binding": f"127.0.0.1:{port}",
            "container": container or self.container_resolver(node_id, port),
            "descriptor_digest": digest,
            "descriptor_verified_at": float(row.get("checked_at")),
            "topology_digest": self.topology.topology_digest,
            "socket_owner": "docker",
            "custody": "observe_and_attest",
            "authority": "verify_only",
            "signer_id": self.signer_id,
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
        }
        payload = _canonical(record)
        record["record_digest"] = "sha256:" + hashlib.sha256(payload).hexdigest()
        record["signature"] = base64.b64encode(self._signer.sign(payload)).decode("ascii")
        return record


def verify_custody_record(record: Mapping[str, Any], public_key: Ed25519PublicKey, *,
                          now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else float(now)
    body = _body(record)
    payload = _canonical(body)
    reasons = []
    if record.get("schema") != SCHEMA:
        reasons.append("schema")
    if record.get("record_digest") != "sha256:" + hashlib.sha256(payload).hexdigest():
        reasons.append("digest")
    try:
        public_key.verify(base64.b64decode(str(record.get("signature") or ""), validate=True), payload)
    except (InvalidSignature, ValueError):
        reasons.append("signature")
    if float(record.get("expires_at") or 0) < now:
        reasons.append("expired")
    if record.get("authority") != "verify_only":
        reasons.append("authority")
    return {"valid": not reasons, "reasons": reasons}


KEY_ENV = "BEAST_COMMONS_CUSTODY_SIGNING_KEY"


def attestor_from_environment(env: Mapping[str, str] | None = None) -> DockerCustodyAttestor | None:
    """Default off: only when ``BEAST_COMMONS_CUSTODY_SIGNING_KEY`` names an existing 0600 Ed25519 key (normally the
    Guardian receipt key ``~/.config/beast/guardian-receipt-ed25519.pem`` provisioned under D3.1)."""
    import os
    import stat
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization

    from app.kernel.networking.fabric_topology import FabricTopology

    env = os.environ if env is None else env
    raw = str(env.get(KEY_ENV) or "").strip()
    if not raw:
        return None
    path = Path(os.path.expandvars(raw)).expanduser()
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("custody signing key must be a regular 0600 file")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("custody signing key must be Ed25519")
    root = Path(__file__).resolve().parents[3]
    topology = FabricTopology.load(
        services_path=Path(env.get("BEAST_GUARDIAN_SERVICE_REGISTRY") or root / ".byron" / "services.yaml"),
        lab_manifest_path=Path(env.get("BEAST_GUARDIAN_LAB_MANIFEST")
                               or root / ".beast" / "remote-commons-lab" / "manifest.json"),
        compose_base_path=Path(env.get("BEAST_GUARDIAN_COMPOSE_BASE") or root / "docker-compose.commons-lab.yml"),
    )
    topology.require_consistent()
    return DockerCustodyAttestor(key, signer_id=str(env.get("BEAST_COMMONS_CUSTODY_SIGNER_ID")
                                                    or "beast.socket-guardian.v1:receipt"), topology=topology)


__all__ = ["CustodyRefused", "DockerCustodyAttestor", "SCHEMA", "attestor_from_environment",
           "verify_custody_record"]
