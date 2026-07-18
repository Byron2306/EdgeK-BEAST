"""Gate-of-Night egress and pinned-identity client for remote Commons nodes."""
from __future__ import annotations

import base64
import ipaddress
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import httpx

from app.kernel.integration.signed_decision import verify_appraisal
from .discovery import CommonsDiscoveryCatalog, DISCOVERY_PROTOCOL
from .lattice_trust import CrystalLatticeTrustStore
from .remote_protocol import CommonsRequestSigner, PROTOCOL_VERSION, canonical_json, sha256_bytes


def _safe_segment(value: str) -> str:
    text = str(value or "").strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError("invalid remote Commons path segment")
    return quote(text, safe="._-")


class CommonsEgressGate:
    """Explicit outbound boundary; no request may choose an unregistered target."""

    def __init__(self, *, allowed_hosts: tuple[str, ...] = (), allow_insecure_loopback: bool = True):
        self.allowed_hosts = frozenset(host.lower().rstrip(".") for host in allowed_hosts if host)
        self.allow_insecure_loopback = bool(allow_insecure_loopback)

    def validate_base_url(self, value: str) -> str:
        parsed = urlsplit(str(value or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("remote Commons endpoint must be an origin without credentials, query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("remote Commons endpoint may not contain a path")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        is_loopback = host == "localhost" or bool(address and address.is_loopback)
        if (self.allowed_hosts and host not in self.allowed_hosts) or (not self.allowed_hosts and not is_loopback):
            raise PermissionError("remote Commons endpoint is outside the Gate of Night allowlist")
        if parsed.scheme == "http" and not (is_loopback and self.allow_insecure_loopback):
            raise PermissionError("remote Commons requires HTTPS outside explicit loopback development")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback and self.allow_insecure_loopback):
            raise PermissionError("unsupported remote Commons transport")
        if address and (address.is_private or address.is_link_local or address.is_reserved) and not is_loopback:
            raise PermissionError("private or link-local remote Commons targets are refused")
        port = parsed.port
        rendered_host = f"[{host}]" if address and address.version == 6 else host
        origin = f"{parsed.scheme}://{rendered_host}"
        if port is not None:
            origin += f":{port}"
        return origin


class RemoteCommonsRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS remote_commons_nodes (
                    node_id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL UNIQUE,
                    node_public_key TEXT NOT NULL,
                    expected_workload_digest TEXT NOT NULL,
                    require_arda INTEGER NOT NULL,
                    trust_policy TEXT NOT NULL DEFAULT 'lattice',
                    expected_policy_generation TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_probe_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(remote_commons_nodes)").fetchall()}
            if "trust_policy" not in columns:
                connection.execute("ALTER TABLE remote_commons_nodes ADD COLUMN trust_policy TEXT NOT NULL DEFAULT 'pinned'")
                connection.execute(
                    "UPDATE remote_commons_nodes SET trust_policy=CASE WHEN require_arda=1 THEN 'arda' ELSE 'pinned' END,state='unprobed',last_probe_json='{}'"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def register(
        self, *, node_id: str, endpoint: str, node_public_key: str,
        expected_workload_digest: str = "", require_arda: bool = False,
        expected_policy_generation: str = "", trust_policy: str | None = None,
    ) -> dict[str, Any]:
        try:
            raw_key = base64.b64decode(node_public_key, validate=True)
            Ed25519PublicKey.from_public_bytes(raw_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("remote Commons node pin must be a raw Ed25519 public key") from exc
        if not node_id or len(raw_key) != 32:
            raise ValueError("remote Commons node identity is incomplete")
        if expected_workload_digest and not expected_workload_digest.startswith("sha256:"):
            raise ValueError("expected workload identity must be a sha256 digest")
        trust_policy = str(trust_policy or ("arda" if require_arda else "pinned"))
        if trust_policy not in {"lattice", "arda", "lattice_or_arda", "lattice_and_arda", "pinned"}:
            raise ValueError("invalid remote Commons trust policy")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO remote_commons_nodes(node_id,endpoint,node_public_key,expected_workload_digest,require_arda,trust_policy,expected_policy_generation,state,last_probe_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET endpoint=excluded.endpoint,node_public_key=excluded.node_public_key,expected_workload_digest=excluded.expected_workload_digest,require_arda=excluded.require_arda,trust_policy=excluded.trust_policy,expected_policy_generation=excluded.expected_policy_generation,state='unprobed',last_probe_json='{}',updated_at=excluded.updated_at",
                (node_id, endpoint, node_public_key, expected_workload_digest, int(require_arda), trust_policy, expected_policy_generation, "unprobed", "{}", now, now),
            )
        return self.get(node_id)

    def get(self, node_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM remote_commons_nodes WHERE node_id=?", (node_id,)).fetchone()
        if row is None:
            raise LookupError(f"remote Commons node not registered: {node_id}")
        return self._row(row)

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM remote_commons_nodes ORDER BY node_id").fetchall()
        return [self._row(row) for row in rows]

    def record_probe(self, node_id: str, *, state: str, result: Mapping[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE remote_commons_nodes SET state=?,last_probe_json=?,updated_at=? WHERE node_id=?",
                (state, json.dumps(dict(result), sort_keys=True, separators=(",", ":"), default=str), time.time(), node_id),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "node_id": row["node_id"],
            "endpoint": row["endpoint"],
            "node_public_key": row["node_public_key"],
            "expected_workload_digest": row["expected_workload_digest"],
            "require_arda": bool(row["require_arda"]),
            "trust_policy": row["trust_policy"],
            "expected_policy_generation": row["expected_policy_generation"],
            "state": row["state"],
            "last_probe": json.loads(row["last_probe_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class RemoteCommonsGateway:
    def __init__(
        self, registry: RemoteCommonsRegistry, gate: CommonsEgressGate, *,
        signer: CommonsRequestSigner | None = None,
        arda_public_key: Ed25519PublicKey | None = None,
        lattice_trust_store: CrystalLatticeTrustStore | None = None,
        discovery_catalog: CommonsDiscoveryCatalog | None = None,
        timeout_seconds: float = 8.0,
    ):
        self.registry = registry
        self.gate = gate
        self.signer = signer
        self.arda_public_key = arda_public_key
        self.lattice_trust_store = lattice_trust_store
        self.discovery_catalog = discovery_catalog
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    @classmethod
    def arda_key_from_file(cls, path: str | Path) -> Ed25519PublicKey:
        key = serialization.load_pem_public_key(Path(path).expanduser().read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("remote Commons ARDA key must be Ed25519")
        return key

    def register(self, **values: Any) -> dict[str, Any]:
        values["endpoint"] = self.gate.validate_base_url(str(values.get("endpoint") or ""))
        return self.registry.register(**values)

    async def _request(
        self, node: Mapping[str, Any], method: str, target: str, *,
        body: bytes = b"", content_type: str = "application/json", authenticate: bool = True,
    ) -> httpx.Response:
        endpoint = self.gate.validate_base_url(str(node["endpoint"]))
        headers: dict[str, str] = {"Accept": "application/json"}
        if body:
            headers["Content-Type"] = content_type
        if authenticate:
            if self.signer is None:
                raise PermissionError("remote Commons client signing key is not configured")
            headers.update(self.signer.headers(method=method, target=target, body=body))
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False, trust_env=False) as client:
            return await client.request(method, endpoint + target, content=body or None, headers=headers)

    async def probe(self, node_id: str) -> dict[str, Any]:
        node = self.registry.get(node_id)
        try:
            response = await self._request(node, "GET", "/v1/node", authenticate=False)
            response.raise_for_status()
            value = response.json()
            result = self._verify_node_document(node, value)
            self._enforce_lattice_monotonic(node, result)
            result["checked_at"] = time.time()
            self.registry.record_probe(node_id, state=result["state"], result=result)
            return result
        except (httpx.HTTPError, InvalidSignature, ValueError, TypeError, PermissionError, KeyError, json.JSONDecodeError) as exc:
            result = {"ok": False, "state": "refused", "node_id": node_id, "error": str(exc), "checked_at": time.time()}
            self.registry.record_probe(node_id, state="refused", result=result)
            return result

    def _verify_node_document(self, node: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        descriptor = dict(value.get("descriptor") or {})
        encoded_descriptor = canonical_json(descriptor)
        required_capabilities = {
            "bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests",
        }
        capabilities = descriptor.get("capabilities")
        if (
            len(encoded_descriptor) > 1024 * 1024
            or descriptor.get("beast_object_type") != "remote_commons_node_descriptor"
            or descriptor.get("schema_version") != "1.0"
            or descriptor.get("protocol") != PROTOCOL_VERSION
            or descriptor.get("maximum_authority") != "verify_only"
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(descriptor.get("workload_digest") or ""))
            or not isinstance(capabilities, list)
            or not required_capabilities.issubset({str(item) for item in capabilities})
        ):
            raise PermissionError("remote Commons descriptor violates local protocol invariants")
        node_id = str(node.get("node_id") or "")
        if descriptor.get("node_id") != node_id or descriptor.get("node_public_key") != node["node_public_key"]:
            raise PermissionError("remote Commons node identity pin mismatch")
        if sha256_bytes(encoded_descriptor) != value.get("descriptor_digest"):
            raise PermissionError("remote Commons descriptor digest mismatch")
        subject = {
            key: descriptor.get(key)
            for key in ("node_id", "workload_digest", "node_public_key", "protocol", "capabilities", "maximum_authority")
        }
        subject_digest = sha256_bytes(canonical_json(subject))
        if descriptor.get("attestation_subject_digest") != subject_digest:
            raise PermissionError("remote Commons attestation subject binding mismatch")
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(node["node_public_key"], validate=True))
        public_key.verify(base64.b64decode(str(value.get("node_signature") or ""), validate=True), encoded_descriptor)
        expected_workload = str(node.get("expected_workload_digest") or "")
        if expected_workload and descriptor.get("workload_digest") != expected_workload:
            raise PermissionError("remote Commons workload identity mismatch")
        policy = str(node.get("trust_policy") or ("arda" if node.get("require_arda") else "pinned"))
        appraisal_verified = False
        lattice_verified = False
        lattice_result: dict[str, Any] = {}
        raw_evidence = descriptor.get("trust_evidence") or []
        if not isinstance(raw_evidence, list) or len(raw_evidence) > 16 or any(not isinstance(item, Mapping) for item in raw_evidence):
            raise PermissionError("remote Commons trust evidence shape is invalid")
        evidence_rows = list(raw_evidence)
        if descriptor.get("arda_appraisal") and descriptor.get("arda_appraisal") not in evidence_rows:
            evidence_rows.append(descriptor.get("arda_appraisal"))
        if self.lattice_trust_store is not None:
            for evidence in evidence_rows:
                try:
                    lattice_result = self.lattice_trust_store.verify(evidence, expected_subject=subject)
                    lattice_verified = True
                    break
                except (PermissionError, ValueError, TypeError):
                    continue
        appraisal = dict(descriptor.get("arda_appraisal") or {})
        arda_required = policy in {"arda", "lattice_and_arda"}
        if arda_required or (policy == "lattice_or_arda" and not lattice_verified):
            if self.arda_public_key is None:
                raise PermissionError("ARDA appraisal verification key is not configured")
            verify_appraisal(
                appraisal,
                self.arda_public_key,
                expected_authority="arda",
                expected_audience="beast-commons-node",
                expected_policy_generation=str(node.get("expected_policy_generation") or appraisal.get("policy_generation") or ""),
                expected_appraisal_ref=str(appraisal.get("appraisal_ref") or ""),
                expected_request_digest=subject_digest,
            )
            appraisal_verified = True
        lattice_required = policy in {"lattice", "lattice_and_arda"}
        if lattice_required and not lattice_verified:
            raise PermissionError("trusted crystal lattice attestation is required")
        if policy == "lattice_or_arda" and not (lattice_verified or appraisal_verified):
            raise PermissionError("trusted lattice or ARDA evidence is required")
        state = (
            "lattice_hardware_attested" if lattice_verified and appraisal_verified
            else "lattice_attested" if lattice_verified
            else "hardware_attested" if appraisal_verified
            else "authenticated_unattested"
        )
        return {
            "ok": True,
            "state": state,
            "node_id": node_id,
            "descriptor_digest": value["descriptor_digest"],
            "workload_digest": descriptor.get("workload_digest"),
            "arda_appraisal_verified": appraisal_verified,
            "lattice_attestation_verified": lattice_verified,
            "lattice_attestation": lattice_result,
            "admission_valid_until": min(
                time.time() + 300,
                float(lattice_result.get("expires_at") or time.time() + 300),
            ),
            "trust_policy": policy,
            "storage": descriptor.get("storage") or {},
            "capabilities": descriptor.get("capabilities") or [],
        }

    @staticmethod
    def _enforce_lattice_monotonic(node: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        current = dict(result.get("lattice_attestation") or {})
        previous = dict((node.get("last_probe") or {}).get("lattice_attestation") or {})
        if not current or not previous:
            return
        current_count = int(current.get("checkpoint_count") or 0)
        previous_count = int(previous.get("checkpoint_count") or 0)
        if current_count < previous_count:
            raise PermissionError("crystal lattice rollback detected")
        if (
            current_count == previous_count
            and current.get("lattice_head_hash") != previous.get("lattice_head_hash")
        ):
            raise PermissionError("crystal lattice same-height fork detected")

    def ingest_discovery_document(
        self, *, origin: str, document: Mapping[str, Any], source: str,
        endpoint_proof: Mapping[str, Any] | None = None, expected_nonce: str = "",
        auto_register: bool = False,
    ) -> dict[str, Any]:
        """Verify a source-neutral discovery envelope and optionally admit its node.

        The envelope may arrive over HTTP, DNS-SD, peer exchange, a registry,
        or an offline bootstrap channel. Only a trusted lattice attestation can
        convert the advertised self-key into an admitted registry pin.
        """
        if self.discovery_catalog is None:
            raise RuntimeError("Commons discovery catalog is not configured")
        if document.get("discovery_protocol") != DISCOVERY_PROTOCOL:
            raise ValueError("unsupported Commons discovery protocol")
        endpoint = self.gate.validate_base_url(origin)
        node_document = dict(document.get("node") or {})
        descriptor = dict(node_document.get("descriptor") or {})
        node_id = str(descriptor.get("node_id") or "")
        node_public_key = str(descriptor.get("node_public_key") or "")
        if not node_id or not node_public_key:
            raise ValueError("Commons discovery descriptor is missing node identity")
        candidate = {
            "node_id": node_id,
            "endpoint": endpoint,
            "node_public_key": node_public_key,
            "expected_workload_digest": str(descriptor.get("workload_digest") or ""),
            "require_arda": False,
            "trust_policy": "lattice",
            "expected_policy_generation": "",
        }
        subject_digest = str(descriptor.get("attestation_subject_digest") or "")
        candidate_id = sha256_bytes(canonical_json({
            "protocol": DISCOVERY_PROTOCOL,
            "source": source,
            "origin": endpoint,
            "node_id": node_id,
            "subject_digest": subject_digest,
        }))
        try:
            verification = self._verify_node_document(candidate, node_document)
            if endpoint_proof is not None:
                proof = dict(endpoint_proof.get("proof") or {})
                if (
                    proof.get("beast_object_type") != "commons_discovery_endpoint_proof"
                    or proof.get("schema_version") != "1.0"
                    or proof.get("node_id") != node_id
                    or proof.get("nonce") != expected_nonce
                    or proof.get("descriptor_digest") != node_document.get("descriptor_digest")
                    or proof.get("maximum_authority") != "endpoint_possession_only"
                    or abs(time.time() - float(proof.get("issued_at") or 0)) > 60
                ):
                    raise PermissionError("Commons discovery endpoint proof binding failed")
                public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(node_public_key, validate=True))
                public_key.verify(
                    base64.b64decode(str(endpoint_proof.get("node_signature") or ""), validate=True),
                    canonical_json(proof),
                )
                verification["endpoint_possession_verified"] = True
            state = "trusted_candidate"
            trust = {
                "verified": True,
                "basis": "crystal_lattice_witnessed",
                "verification": verification,
            }
        except (InvalidSignature, PermissionError, ValueError, TypeError, KeyError) as exc:
            state = "observed_untrusted"
            trust = {"verified": False, "error": str(exc), "basis": "none"}
        observed = self.discovery_catalog.observe(
            candidate_id=candidate_id,
            source=source,
            origin=endpoint,
            node_id=node_id,
            subject_digest=subject_digest,
            state=state,
            trust=trust,
            document=document,
        )
        registered = None
        admission = "candidate_only"
        if auto_register and state == "trusted_candidate" and trust["verification"].get("endpoint_possession_verified"):
            try:
                existing = self.registry.get(node_id)
            except LookupError:
                existing = None
            if existing and (
                existing.get("endpoint") != endpoint or existing.get("node_public_key") != node_public_key
            ):
                return {
                    "candidate": observed,
                    "registered": None,
                    "admission": "identity_conflict",
                    "error": "trusted discovery cannot replace an existing node endpoint or key",
                }
            if existing:
                self._enforce_lattice_monotonic(existing, trust["verification"])
            registered = self.registry.register(**candidate)
            verification = dict(trust["verification"])
            verification["checked_at"] = time.time()
            self.registry.record_probe(node_id, state=str(verification["state"]), result=verification)
            registered = self.registry.get(node_id)
            admission = "registered_from_lattice_and_endpoint_proof"
        return {
            "candidate": observed,
            "registered": registered,
            "admission": admission,
        }

    async def discover_origins(
        self, origins: list[str] | tuple[str, ...], *, source: str = "well_known",
        auto_register: bool = True,
    ) -> dict[str, Any]:
        results = []
        for raw_origin in origins:
            try:
                origin = self.gate.validate_base_url(raw_origin)
                response = await self._request(
                    {"endpoint": origin}, "GET", "/.well-known/beast-commons.json", authenticate=False,
                )
                response.raise_for_status()
                document = response.json()
                descriptor_digest = str(((document.get("node") or {}).get("descriptor_digest") or ""))
                nonce = secrets.token_urlsafe(32)
                challenge_body = canonical_json({"nonce": nonce, "descriptor_digest": descriptor_digest})
                challenge = await self._request(
                    {"endpoint": origin}, "POST", "/v1/discovery/challenge",
                    body=challenge_body, authenticate=False,
                )
                challenge.raise_for_status()
                results.append(self.ingest_discovery_document(
                    origin=origin, document=document, source=source,
                    endpoint_proof=challenge.json(), expected_nonce=nonce, auto_register=auto_register,
                ))
            except (httpx.HTTPError, InvalidSignature, PermissionError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                results.append({"origin": str(raw_origin), "error": str(exc), "admission": "refused"})
        return {
            "protocol": DISCOVERY_PROTOCOL,
            "results": results,
            "catalog": self.discovery_catalog.snapshot() if self.discovery_catalog else {},
        }

    def _admitted_node(self, node_id: str, *, write: bool = False) -> dict[str, Any]:
        node = self.registry.get(node_id)
        accepted = {
            "lattice": {"lattice_attested", "lattice_hardware_attested"},
            "arda": {"hardware_attested", "lattice_hardware_attested"},
            "lattice_or_arda": {"lattice_attested", "hardware_attested", "lattice_hardware_attested"},
            "lattice_and_arda": {"lattice_hardware_attested"},
            "pinned": {"authenticated_unattested", "lattice_attested", "hardware_attested", "lattice_hardware_attested"},
        }.get(str(node.get("trust_policy") or "pinned"), set())
        if node.get("state") not in accepted:
            raise PermissionError("remote Commons node must pass a fresh identity probe")
        last = node.get("last_probe") or {}
        if time.time() - float(last.get("checked_at") or 0) > 300:
            raise PermissionError("remote Commons node probe is stale")
        if time.time() >= float(last.get("admission_valid_until") or 0):
            raise PermissionError("remote Commons node trust evidence has expired")
        if write and self.signer is None:
            raise PermissionError("remote Commons write signing key is not configured")
        return node

    async def list_buckets(self, node_id: str) -> dict[str, Any]:
        node = self._admitted_node(node_id)
        target = "/v1/buckets?limit=200"
        response = await self._request(node, "GET", target, authenticate=self.signer is not None)
        response.raise_for_status()
        return response.json()

    async def create_bucket(self, node_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        node = self._admitted_node(node_id, write=True)
        body = canonical_json(payload)
        response = await self._request(node, "POST", "/v1/buckets", body=body)
        if response.status_code >= 400:
            raise RuntimeError(f"remote Commons bucket creation failed ({response.status_code}): {response.text[:300]}")
        return response.json()

    async def list_revisions(self, node_id: str, *, owner: str, name: str) -> dict[str, Any]:
        node = self._admitted_node(node_id)
        target = f"/v1/buckets/{_safe_segment(owner)}/{_safe_segment(name)}/revisions"
        response = await self._request(node, "GET", target, authenticate=self.signer is not None)
        response.raise_for_status()
        return response.json()

    async def put_blob(self, node_id: str, payload: bytes) -> dict[str, Any]:
        node = self._admitted_node(node_id, write=True)
        digest = sha256_bytes(payload)
        target = f"/v1/blobs/{digest}"
        response = await self._request(node, "PUT", target, body=payload, content_type="application/octet-stream")
        if response.status_code >= 400:
            raise RuntimeError(f"remote Commons blob upload failed ({response.status_code}): {response.text[:300]}")
        return response.json()

    async def commit_revision(
        self, node_id: str, *, owner: str, name: str, revision: str,
        manifest: Mapping[str, Any], replace: bool = False,
    ) -> dict[str, Any]:
        node = self._admitted_node(node_id, write=True)
        target = f"/v1/buckets/{_safe_segment(owner)}/{_safe_segment(name)}/revisions/{_safe_segment(revision)}"
        body = canonical_json({"manifest": dict(manifest), "replace": bool(replace)})
        response = await self._request(node, "PUT", target, body=body)
        if response.status_code >= 400:
            raise RuntimeError(f"remote Commons revision commit failed ({response.status_code}): {response.text[:300]}")
        value = response.json()
        self._verify_revision_receipt(node, value)
        return value

    @staticmethod
    def _verify_revision_receipt(node: Mapping[str, Any], value: Mapping[str, Any]) -> None:
        receipt = dict(value.get("receipt") or {})
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(node["node_public_key"], validate=True))
        public_key.verify(base64.b64decode(str(value.get("node_signature") or ""), validate=True), canonical_json(receipt))
        if value.get("receipt_digest") != sha256_bytes(canonical_json(receipt)):
            raise PermissionError("remote Commons revision receipt digest mismatch")
        manifest = dict(value.get("manifest") or {})
        if value.get("manifest_digest") != sha256_bytes(canonical_json(manifest)):
            raise PermissionError("remote Commons revision manifest digest mismatch")
        if receipt.get("manifest_digest") != value.get("manifest_digest") or receipt.get("node_id") != node.get("node_id"):
            raise PermissionError("remote Commons receipt content binding mismatch")

    async def get_revision(
        self, node_id: str, *, owner: str, name: str, revision: str,
    ) -> dict[str, Any]:
        node = self._admitted_node(node_id)
        target = f"/v1/buckets/{_safe_segment(owner)}/{_safe_segment(name)}/revisions/{_safe_segment(revision)}"
        response = await self._request(node, "GET", target, authenticate=self.signer is not None)
        response.raise_for_status()
        value = response.json()
        self._verify_revision_receipt(node, value)
        return value

    async def pull_revision(
        self, node_id: str, *, owner: str, name: str, revision: str,
        maximum_total_bytes: int = 64 * 1024 * 1024,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        node = self._admitted_node(node_id)
        value = await self.get_revision(node_id, owner=owner, name=name, revision=revision)
        manifest = dict(value.get("manifest") or {})
        files = manifest.get("files") or []
        blobs: dict[str, bytes] = {}
        total = 0
        for item in files:
            digest = str((item or {}).get("digest") or "")
            expected_size = int((item or {}).get("size") or 0)
            if digest in blobs:
                continue
            target = f"/v1/blobs/{digest}"
            response = await self._request(node, "GET", target, authenticate=True)
            response.raise_for_status()
            payload = response.content
            total += len(payload)
            if total > maximum_total_bytes:
                raise PermissionError("remote Commons import exceeds local pull budget")
            if len(payload) != expected_size or sha256_bytes(payload) != digest:
                raise PermissionError("remote Commons blob failed size or digest verification")
            blobs[digest] = payload
        return value, blobs

    def snapshot(self) -> dict[str, Any]:
        nodes = self.registry.list()
        return {
            "version": "1.0",
            "mode": "lattice_attested_trust_commons",
            "nodes": nodes,
            "node_count": len(nodes),
            "client_signing_ready": self.signer is not None,
            "arda_verification_ready": self.arda_public_key is not None,
            "lattice_verification_ready": self.lattice_trust_store is not None,
            "lattice_trust": self.lattice_trust_store.snapshot() if self.lattice_trust_store else {},
            "discovery": self.discovery_catalog.snapshot() if self.discovery_catalog else {
                "protocol": DISCOVERY_PROTOCOL, "candidate_count": 0, "configured": False,
            },
            "egress": {
                "policy": "gate_of_night_allowlist",
                "allowed_hosts": sorted(self.gate.allowed_hosts),
                "insecure_loopback_only": self.gate.allow_insecure_loopback,
            },
        }
