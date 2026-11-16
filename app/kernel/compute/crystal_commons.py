"""D7: publish promoted coding crystals into BEAST's own Commons (not Hugging Face).

promoted crystal -> privacy-filtered publication bundle (crystal_publication) -> Commons Space bundle
(networking.commons_spaces: privacy-scanned, content-addressed, sealed) -> verify_only bucket revision on
lattice-attested remote nodes (node-signed witness receipts, via the 8101 control-plane over its ML-KEM
channel) -> import back as a quarantined hypothesis (CommonsEnterprisePlane custody) -> local held-out
reproduction -> sovereign promotion.  Remote content never gains authority by being published.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.kernel.compute.crystal_publication import CrystalImporter, _chunk_path, assert_publishable
from app.kernel.networking.commons_spaces import (
    MANIFEST_NAME,
    RECEIPT_MARKDOWN_NAME,
    RECEIPT_NAME,
    build_manifest,
    build_reduction_receipt,
    export_space,
    validate_manifest,
    validate_reduction_receipt,
    write_space,
)

OWNER = "beast"
BUCKET = "coding-crystals"
SPACE_TASK_CLASS = "coding_crystal"
REVISION_KIND = "beast.coding_crystal.commons_revision.v1"
DEFAULT_GATEWAY = "http://127.0.0.1:8101"
REMOTE_PREFIX = "/edgek/control-plane/commons/remote"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _short(crystal_id: str) -> str:
    return crystal_id.split(":", 1)[-1][:24]


def revision_name(crystal_id: str) -> str:
    return "cc-" + _short(crystal_id)


def space_id_for(crystal_id: str) -> str:
    return "coding-crystal-" + _short(crystal_id)


def build_crystal_space(bundle: Mapping[str, Any], spaces_root: str | Path, *,
                        economy: Mapping[str, Any] | None = None, parent_manifest_hash: str = "") -> dict[str, Any]:
    """Write the bundle as a Commons Space and export the sealed, content-addressed Space bundle.

    ``economy`` (a CrystalShadowLedger export for this space) attaches the measured reduction receipts and the
    ledger-only shadow entries as artifacts of a successor space revision bound to ``parent_manifest_hash``.
    """
    crystal_id, family = str(bundle["crystal_id"]), str(bundle["task_family"])
    for data in bundle["files"].values():
        assert_publishable(json.loads(data))
    space_id = space_id_for(crystal_id)
    if economy is not None:
        if not parent_manifest_hash:
            raise ValueError("economy attachments must bind to the published parent space manifest")
        space_id += "-e" + _sha(json.dumps(economy, sort_keys=True, default=str).encode())[7:15]
    root = Path(spaces_root) / space_id
    prefix = f"crystals/{family}/{crystal_id}/"
    artifacts = []
    for name, data in sorted(bundle["files"].items()):
        target = root / (prefix + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        artifacts.append({"path": prefix + name, "artifact_type": "crystal_signature" if name == "signature.json" else "crystal_manifest"})
    for digest, payload in sorted(bundle["chunks"].items()):
        target = root / _chunk_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        artifacts.append({"path": _chunk_path(digest), "artifact_type": "portable_chunk"})
    if economy is not None:
        for rel, doc in (("economy/reduction_receipts.json", {"receipts": list(economy.get("receipts") or [])}),
                         ("economy/shadow_ledger.json", {k: v for k, v in economy.items() if k != "receipts"})):
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(doc, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            artifacts.append({"path": rel, "artifact_type": "shadow_economy"})
    proofs = json.loads(bundle["files"]["proofs.json"])
    replay = proofs.get("heldout_replay") or {}
    budget = proofs.get("learned_budget") or {}
    manifest = build_manifest(
        root, space_id=space_id, name=f"Coding crystal {family}", task_class=SPACE_TASK_CLASS, artifacts=artifacts,
        hardware_profile={"gpu_required": False, "model_required_for_reuse": False},
        verifier_bundles=[{"verifier": "heldout_replay", "successes": replay.get("successes"),
                           "attempts": replay.get("attempts"), "variant_ids": replay.get("variant_ids")}],
        reduction_claims={"evidence_class": "local_heldout_replay", "learned_budget": budget},
        safety={"maximum_authority": "verify_only", "reviewed_ops_only": True,
                "remote_import": "quarantined_hypothesis_until_local_reproduction"},
        lineage={"crystal_id": crystal_id, "task_family": family, "bundle_digest": bundle["bundle_digest"],
                 "candidate_digest": proofs.get("candidate_digest"), "parent_manifest_hash": parent_manifest_hash,
                 "shadow_economy": economy is not None},
    )
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={"route_id": "model_planner", "model_turns": budget.get("model_turns")},
        optimized_route={"route_id": "coding_crystal_replay", "model_turns": 0},
        displacement={"provider_calls_avoided": budget.get("model_turns"), "tokens_avoided": budget.get("tokens"),
                      "evidence_class": "observed_on_heldout_replay"},
        verifier={"name": "heldout_replay", "passed": bool(replay.get("promoted"))},
        resource_deltas={"gpu_avoided": True},
        provenance={"source": "beast.coding_crystal", "signature": "signature.json"},
        rollback_available=True, approval_required=True,
    )
    write_space(root, manifest, receipt)
    validation = validate_manifest(root, manifest)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    bundle_path = Path(spaces_root) / "_bundles" / f"{space_id}.beast-space.zip"
    exported = export_space(root, bundle_path)
    return {"space_id": space_id, "space_root": str(root), "manifest": manifest,
            "receipt_validation": validate_reduction_receipt(receipt), "bundle_path": str(bundle_path),
            "bundle_id": exported["bundle_id"], "bundle_sha256": exported["sha256"]}


def revision_manifest(bundle: Mapping[str, Any], space: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Bucket revision manifest (verify_only hypothesis) over every Space file; blobs keyed by digest."""
    root = Path(space["space_root"])
    paths = [MANIFEST_NAME, RECEIPT_NAME, RECEIPT_MARKDOWN_NAME] + [a["path"] for a in space["manifest"]["artifacts"]]
    files, blobs = [], {}
    for rel in dict.fromkeys(paths):
        data = (root / rel).read_bytes()
        digest = _sha(data)
        blobs[digest] = data
        files.append({"path": rel, "digest": digest, "size": len(data)})
    signature = json.loads(bundle["files"]["signature.json"])
    manifest = {
        "authority": "remote_hypothesis", "maximum_authority": "verify_only", "files": files,
        "metadata": {"kind": REVISION_KIND, "crystal_id": bundle["crystal_id"], "task_family": bundle["task_family"],
                     "space_id": space["space_id"], "space_manifest_hash": space["manifest"]["manifest_hash"],
                     "space_bundle_id": space["bundle_id"]},
        "proof": {"bundle_digest": bundle["bundle_digest"], "signer_key_id": signature.get("key_id"),
                  "signature_algorithm": signature.get("algorithm")},
    }
    assert_publishable(manifest)
    return manifest, blobs


def _exists_error(exc: Exception) -> bool:
    return isinstance(exc, FileExistsError) or "already exists" in str(exc)


class CommonsCrystalPublisher:
    def __init__(self, transport: Any, *, owner: str = OWNER, bucket: str = BUCKET):
        self.transport, self.owner, self.bucket = transport, owner, bucket

    def publish(self, bundle: Mapping[str, Any], space: Mapping[str, Any], *, node_ids: Iterable[str],
                quorum: int | None = None) -> dict[str, Any]:
        node_ids = tuple(node_ids)
        manifest, blobs = revision_manifest(bundle, space)
        revision = revision_name(str(bundle["crystal_id"]))
        nodes: dict[str, Any] = {}
        for node_id in node_ids:
            try:
                self.transport.probe(node_id)
                listed = self.transport.list_buckets(node_id).get("buckets") or []
                if f"{self.owner}/{self.bucket}" not in {row.get("bucket_id") for row in listed}:
                    try:
                        self.transport.create_bucket(node_id, {"owner": self.owner, "name": self.bucket,
                                                               "visibility": "private",
                                                               "description": "BEAST promoted coding crystals (verify_only)"})
                    except Exception as exc:
                        if not _exists_error(exc):
                            raise
                for digest, data in blobs.items():
                    stored = self.transport.put_blob(node_id, data)
                    if stored.get("digest", digest) != digest:
                        raise PermissionError("remote node stored a different blob digest")
                try:
                    value = self.transport.commit_revision(node_id, owner=self.owner, name=self.bucket,
                                                           revision=revision, manifest=manifest)
                except Exception as exc:
                    if not _exists_error(exc):
                        raise
                    nodes[node_id] = {"ok": True, "existing": True, "revision": revision}
                    continue
                receipt = dict(value.get("receipt") or {})
                if receipt.get("maximum_authority") != "verify_only" or receipt.get("node_id") != node_id:
                    raise PermissionError("remote witness receipt exceeded verify_only or node binding")
                if receipt.get("manifest_digest") != value.get("manifest_digest"):
                    raise PermissionError("remote witness receipt is not bound to the committed manifest")
                nodes[node_id] = {"ok": True, "revision": revision, "manifest_digest": value.get("manifest_digest"),
                                  "receipt_digest": value.get("receipt_digest"), "receipt": receipt}
            except Exception as exc:  # recorded per node; quorum decides
                nodes[node_id] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        need = len(node_ids) if quorum is None else int(quorum)
        ok = [n for n, r in nodes.items() if r.get("ok")]
        digests = {r["manifest_digest"] for r in nodes.values() if r.get("manifest_digest")}
        status = "published" if len(ok) >= need and len(digests) <= 1 else "incomplete"
        return {"status": status, "quorum": len(ok), "required": need, "bucket": f"{self.owner}/{self.bucket}",
                "revision": revision, "crystal_id": bundle["crystal_id"], "space_id": space["space_id"],
                "space_bundle_id": space["bundle_id"], "blob_count": len(blobs), "nodes": nodes}


class _CustodyReader:
    """Read-only view over locally quarantined custody bytes, addressed by revision path."""

    def __init__(self, blobs_by_path: Mapping[str, bytes]):
        self.blobs = dict(blobs_by_path)

    def read_file(self, dataset_id: str, path: str, *, revision: str = "main") -> bytes:
        if path not in self.blobs:
            raise ValueError(f"quarantined custody is missing {path}")
        return self.blobs[path]


class CommonsCrystalImporter:
    def __init__(self, transport: Any, registry: Any, *, owner: str = OWNER, bucket: str = BUCKET):
        self.transport, self.registry, self.owner, self.bucket = transport, registry, owner, bucket

    def pull(self, node_id: str, crystal_id: str, *, trusted_keys: Mapping[str, Any]) -> dict[str, Any]:
        revision = revision_name(crystal_id)
        self.transport.probe(node_id)
        result = self.transport.import_revision(node_id, owner=self.owner, name=self.bucket, revision=revision)
        admission = dict(result.get("admission") or {})
        if (result.get("status") != "quarantined_hypothesis" or admission.get("status") != "quarantined_hypothesis"
                or admission.get("maximum_authority") != "verify_only" or not admission.get("local_reproduction_required")):
            raise PermissionError("Commons import did not land as a verify_only quarantined hypothesis")
        blobs = {}
        for item in admission.get("custody") or ():
            data = bytes(self.transport.read_custody(str(item["digest"])))
            if _sha(data) != item["digest"]:
                raise ValueError("quarantined custody failed digest verification")
            blobs[str(item["path"])] = data
        families = {p.split("/")[1] for p in blobs if p.startswith("crystals/") and p.endswith(f"/{crystal_id}/manifest.json")}
        if len(families) != 1:
            raise ValueError("Commons revision does not carry exactly one manifest for this crystal")
        dataset = f"commons:{node_id}/{self.owner}/{self.bucket}"
        record = CrystalImporter(_CustodyReader(blobs), dataset, self.registry).pull(
            families.pop(), crystal_id, trusted_keys=trusted_keys, revision=revision)
        space_doc = json.loads(blobs.get(MANIFEST_NAME, b"{}") or b"{}")
        record.setdefault("provenance", {})["commons"] = {
            "space_id": space_doc.get("space_id"), "space_manifest_hash": space_doc.get("manifest_hash"),
            "node_id": node_id, "bucket": f"{self.owner}/{self.bucket}", "revision": revision,
            "admission_digest": admission.get("admission_digest"), "manifest_digest": admission.get("manifest_digest"),
            "remote_receipt_digest": admission.get("remote_receipt_digest"),
            "local_reproduction_required": True,
        }
        return record


class GatewayCommonsTransport:
    """Talks to the running BEAST gateway's control-plane routes (loopback operator boundary only).

    The gateway owns the client signing key and the ML-KEM channel to the nodes; this class never touches keys.
    Imported custody bytes are read from the gateway's local immutable vault.
    """

    def __init__(self, base_url: str = DEFAULT_GATEWAY, *, vault_root: str | Path, timeout: float = 60.0):
        import httpx

        from app.kernel.commons.artifact_vault import ArtifactVault

        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            raise PermissionError("Commons crystal publishing only talks to a loopback BEAST gateway")
        self.client = httpx.Client(base_url=base_url, timeout=timeout)
        self.vault = ArtifactVault(Path(vault_root))

    def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.request(method, REMOTE_PREFIX + path, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:400]
            if "already exists" in detail:
                raise FileExistsError(detail)
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {detail}")
        return response.json()

    def probe(self, node_id: str) -> dict[str, Any]:
        return self._call("POST", f"/nodes/{node_id}/probe")

    def list_buckets(self, node_id: str) -> dict[str, Any]:
        return self._call("GET", f"/nodes/{node_id}/buckets")

    def create_bucket(self, node_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", f"/nodes/{node_id}/buckets", json=dict(payload))

    def put_blob(self, node_id: str, payload: bytes) -> dict[str, Any]:
        return self._call("POST", f"/nodes/{node_id}/blobs", json={"content_b64": base64.b64encode(payload).decode("ascii")})

    def commit_revision(self, node_id: str, *, owner: str, name: str, revision: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("PUT", f"/nodes/{node_id}/buckets/{owner}/{name}/revisions/{revision}",
                          json={"manifest": dict(manifest), "replace": False})

    def import_revision(self, node_id: str, *, owner: str, name: str, revision: str) -> dict[str, Any]:
        return self._call("POST", f"/nodes/{node_id}/buckets/{owner}/{name}/revisions/{revision}/import")

    def read_custody(self, digest: str) -> bytes:
        return self.vault.get(digest)

    def register_space(self, bundle_path: str | Path) -> dict[str, Any]:
        """Import the Space bundle into the gateway's local Commons registry (workspace-scoped route)."""
        response = self.client.post("/edgek/commons-spaces/import",
                                    json={"bundle_path": str(bundle_path), "approved": True, "dry_run": False})
        if response.status_code >= 400:
            raise RuntimeError(f"Commons space import -> {response.status_code}: {response.text[:400]}")
        return response.json()


__all__ = ["BUCKET", "OWNER", "CommonsCrystalImporter", "CommonsCrystalPublisher", "GatewayCommonsTransport",
           "build_crystal_space", "revision_manifest", "revision_name", "space_id_for"]
