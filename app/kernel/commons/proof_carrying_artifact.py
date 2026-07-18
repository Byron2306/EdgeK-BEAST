"""Commons admission and sovereign node-local reproduction for crystals."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.commons.artifact_vault import ArtifactVault
from app.kernel.commons.chunk_store import ChunkStore
from app.kernel.compute.displacement_economics import DisplacementEconomics
from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.sensorium.contracts_hash import content_hash


FORBIDDEN_EXPORT_KEYS = frozenset({
    "sensor_events", "raw_sensor_events", "live_descriptors", "capability", "capabilities",
    "authority_bearer", "authority_bearers", "host_identity", "hostname", "workspace_root",
    "process_id", "pid", "socket_fd", "secret", "credentials",
})
_HOST_PATH = re.compile(r"(?:^|[\s\"'])/(?:home|root|Users|proc|sys|dev|run)/")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass(frozen=True)
class CommonsAdmission:
    artifact_digest: str
    manifest_digest: str
    chunk_digests: tuple[str, ...]
    signature: str
    appraisal_ref: str
    space_id: str
    authority: str = "remote_hypothesis"
    maximum_authority: str = "verify_only"
    evidence_node_id: str = ""
    manifest: Mapping[str, Any] = field(default_factory=dict)
    signer_public_key: str = ""


class ProofArtifactAdmission:
    REQUIRED = ("crystal", "opcode_catalog", "applicability_contract", "negative_boundaries",
                "replay_corpus_summary", "displacement_receipt", "provenance", "privacy_projection",
                "policy_attestation_requirements", "decay_rules")

    def __init__(self, root: Path, signer: Ed25519PrivateKey, *, graph: ControlEvidenceGraph | None = None,
                 privacy_scanner: Callable[[Mapping[str, Any]], bool] | None = None,
                 arda_appraiser: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None):
        self.root = Path(root); self.vault = ArtifactVault(self.root / "vault")
        self.chunks = ChunkStore(self.root / "chunks"); self.signer = signer
        self.verifier = signer.public_key(); self.graph = graph or ControlEvidenceGraph(self.root / "evidence.jsonl")
        self.privacy_scanner = privacy_scanner or self._default_privacy_scan
        self.arda_appraiser = arda_appraiser

    def admit(self, bundle: Mapping[str, Any], *, space_id: str, explicit_space_admission: bool) -> CommonsAdmission:
        if not explicit_space_admission or not space_id:
            raise PermissionError("explicit Commons Space admission is required")
        missing = [key for key in self.REQUIRED if key not in bundle]
        if missing:
            raise ValueError("incomplete Commons proof bundle: " + ", ".join(missing))
        DisplacementEconomics.validate(bundle["displacement_receipt"])
        if not self.privacy_scanner(bundle):
            raise PermissionError("Commons privacy projection rejected export")
        projected = {key: bundle[key] for key in self.REQUIRED}
        payload = _canonical(projected); artifact_digest = self.vault.put(payload)
        chunk_manifest = self.chunks.put(payload)
        if chunk_manifest.artifact_digest != artifact_digest or self.chunks.get(chunk_manifest) != payload:
            raise RuntimeError("immutable Commons custody validation failed")
        manifest = {
            "beast_object_type": "commons_proof_carrying_crystal_manifest", "version": "1.0",
            "artifact_digest": artifact_digest, "artifact_size": len(payload),
            "chunks": list(chunk_manifest.chunks), "space_id": space_id,
            "authority": "remote_hypothesis", "maximum_authority": "verify_only",
            "privacy_projection_digest": content_hash(projected["privacy_projection"]),
            "policy_attestation_requirements": projected["policy_attestation_requirements"],
            "decay_rules": projected["decay_rules"],
        }
        appraisal = dict(self.arda_appraiser(manifest)) if self.arda_appraiser else {}
        appraisal_ref = str(appraisal.get("appraisal_ref") or "")
        if not appraisal_ref or appraisal.get("allowed") is not True:
            raise PermissionError("positive ARDA appraisal is required")
        manifest["appraisal_ref"] = appraisal_ref
        manifest_digest = content_hash(manifest)
        signature = base64.b64encode(self.signer.sign(_canonical(manifest))).decode()
        self.verifier.verify(base64.b64decode(signature), _canonical(manifest))
        node = self.graph.add("commons_artifact_admission", {
            **manifest, "manifest_digest": manifest_digest, "signature": signature,
            "custody": {"vault": artifact_digest, "chunks": list(chunk_manifest.chunks)},
        })
        public_key = base64.b64encode(self.verifier.public_bytes_raw()).decode()
        return CommonsAdmission(artifact_digest, manifest_digest, chunk_manifest.chunks, signature,
                                appraisal_ref, space_id, evidence_node_id=node.node_id,
                                manifest=manifest, signer_public_key=public_key)

    @staticmethod
    def _default_privacy_scan(bundle: Mapping[str, Any]) -> bool:
        def walk(value: Any) -> bool:
            if isinstance(value, Mapping):
                return all(str(key).lower() not in FORBIDDEN_EXPORT_KEYS and walk(item)
                           for key, item in value.items())
            if isinstance(value, (list, tuple)):
                return all(walk(item) for item in value)
            return not (isinstance(value, str) and _HOST_PATH.search(value))
        projection = bundle.get("privacy_projection") or {}
        return bool(isinstance(projection, Mapping) and projection.get("raw_sensitive_events_exported") is False
                    and projection.get("ambient_authority_exported") is False and walk(bundle))


class CommonsFederation:
    """Receiving nodes reproduce hypotheses; advertised claims never count."""

    def __init__(self, graph: ControlEvidenceGraph | None = None):
        self.graph = graph or ControlEvidenceGraph(); self._nodes: dict[str, dict[str, Any]] = {}
        self._revoked_contributors: set[str] = set(); self._last_route: dict[str, str] = {}

    def reproduce(self, admission: CommonsAdmission, *, node_id: str, contributor_id: str,
                  node_attestation: Mapping[str, Any], local_context: Mapping[str, Any],
                  heldout_results: Sequence[Mapping[str, Any]], displacement_receipt: Mapping[str, Any],
                  expected_verifier_digest: str, expected_policy_generation: str) -> dict[str, Any]:
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", admission.artifact_digest)
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", admission.manifest_digest)
                or not admission.signature or not admission.appraisal_ref or not admission.space_id
                or not admission.manifest or not admission.signer_public_key):
            raise PermissionError("malicious or incomplete manifest refused")
        try:
            manifest = dict(admission.manifest)
            if (content_hash(manifest) != admission.manifest_digest
                    or manifest.get("artifact_digest") != admission.artifact_digest
                    or manifest.get("space_id") != admission.space_id
                    or manifest.get("appraisal_ref") != admission.appraisal_ref
                    or manifest.get("authority") != admission.authority
                    or manifest.get("maximum_authority") != admission.maximum_authority
                    or tuple(manifest.get("chunks") or ()) != admission.chunk_digests):
                raise PermissionError("Commons manifest content binding failed")
            verifier = Ed25519PublicKey.from_public_bytes(base64.b64decode(admission.signer_public_key, validate=True))
            verifier.verify(base64.b64decode(admission.signature, validate=True), _canonical(manifest))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise PermissionError("Commons manifest signature verification failed") from exc
        if contributor_id in self._revoked_contributors:
            raise PermissionError("contributor is revoked")
        if admission.authority != "remote_hypothesis" or admission.maximum_authority != "verify_only":
            raise PermissionError("incoming artifact exceeded hypothesis authority")
        now = datetime.now(timezone.utc).timestamp()
        if node_attestation.get("verified") is not True or float(node_attestation.get("expires_at") or 0) <= now:
            raise PermissionError("fresh verified node attestation is required")
        if str(local_context.get("policy_generation") or "") != expected_policy_generation:
            raise PermissionError("local policy mismatch")
        if str(local_context.get("verifier_digest") or "") != expected_verifier_digest:
            raise PermissionError("verifier substitution refused")
        if not heldout_results or not all(item.get("verified") is True and item.get("negative_boundary_preserved") is True
                                          for item in heldout_results):
            raise PermissionError("local held-out reproduction failed")
        DisplacementEconomics.validate(displacement_receipt)
        measurement_scope = displacement_receipt.get("measurement_scope") or {}
        if (measurement_scope.get("node_id") != node_id
                or measurement_scope.get("origin") != "node_local"):
            raise PermissionError("displacement receipt is not node-local")
        previous = self._last_route.get(node_id)
        route = admission.artifact_digest
        if previous and previous != route and local_context.get("route_change_approved") is not True:
            raise PermissionError("route flapping refused")
        self._last_route[node_id] = route
        receipt = {
            "beast_object_type": "commons_node_local_reproduction_receipt", "node_id": node_id,
            "contributor_id": contributor_id, "manifest_digest": admission.manifest_digest,
            "artifact_digest": admission.artifact_digest, "node_attestation_digest": content_hash(node_attestation),
            "local_policy_generation": expected_policy_generation, "local_verifier_digest": expected_verifier_digest,
            "heldout_count": len(heldout_results), "displacement_receipt_digest": displacement_receipt["receipt_digest"],
            "provider_calls_avoided": displacement_receipt["provider_calls_avoided"],
            "authority": {"applicability": "node_local", "promotion": "node_local", "execution": "node_local"},
            "status": "locally_reproduced", "revoked": False,
        }
        receipt["receipt_digest"] = content_hash(receipt)
        node = self.graph.add("commons_node_local_reproduction", receipt)
        receipt["evidence_node_id"] = node.node_id; self._nodes[node_id] = receipt
        return receipt

    def revoke_contributor(self, contributor_id: str, *, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("revocation requires a reason")
        self._revoked_contributors.add(contributor_id)
        affected = []
        for node_id, receipt in self._nodes.items():
            if receipt["contributor_id"] == contributor_id:
                receipt["revoked"] = True; receipt["status"] = "revoked"; affected.append(node_id)
        node = self.graph.add("commons_contributor_revocation", {
            "contributor_id": contributor_id, "reason": reason, "affected_nodes": sorted(affected)})
        return {"revoked": True, "affected_nodes": sorted(affected), "evidence_node_id": node.node_id}

    def aggregate_verified_displacement(self) -> dict[str, Any]:
        receipts = [item for item in self._nodes.values()
                    if item.get("status") == "locally_reproduced" and not item.get("revoked")]
        result = {
            "beast_object_type": "federated_verified_displacement_aggregate",
            "independent_node_count": len({item["node_id"] for item in receipts}),
            "provider_calls_avoided": sum(int(item["provider_calls_avoided"]) for item in receipts),
            "receipt_digests": sorted(item["receipt_digest"] for item in receipts),
            "advertised_claims_counted": 0,
        }
        result["aggregate_digest"] = content_hash(result)
        return result
