"""D7: privacy-filtered, Xet-chunked publication bundles for promoted coding crystals; quarantined import.

Transport-neutral: the production target is BEAST's own Commons (crystal_commons.py).  The HF-dataset publisher
below is an optional, default-off exporter that no CLI or route wires up.

Only privacy-filtered manifests, portable content chunks, compatibility metadata and proofs are
published. Raw/native KV, memfd descriptors, prompts, tool arguments/results, workspace content,
absolute paths and secrets never leave the node. Imported crystals are hypotheses: they land as
``quarantined`` and are promoted only by local held-out reproduction.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.kernel.compute.coding_crystals import (
    CODING_CATALOG_VERSION,
    CRYSTAL_PARAMETERS,
    REVIEWED_TOOLS,
    CodingCrystalCandidate,
    CodingCrystalRegistry,
    coding_catalog_digest,
    replay_candidate,
)
from app.kernel.compute.forge_kv_xet import chunk_bytes
from app.kernel.sensorium.episode_envelope import ENVELOPE_SCHEMA
from app.kernel.sensorium.privacy import SensorPrivacyGate

PUBLICATION_SCHEMA = "beast.crystal_publication.v1"
CHUNK_SIZE = 4096
FORBIDDEN_KEYS = frozenset({
    "prompt", "prompts", "objective", "content", "stdout", "stderr", "arguments", "result", "native_kv", "kv",
    "kv_cache", "memfd", "memfd_fd", "memfd_descriptors", "fd", "fds", "workspace", "workspace_root", "root_path",
    "worktree_root", "workspace_content", "token", "api_key", "secret", "secrets", "password", "private_key",
})
_PATHLIKE = re.compile(r"(^/|^~|/home/|/root/|/data/|/Users/|[A-Za-z]:\\)")
FILE_NAMES = ("manifest.json", "compatibility.json", "proofs.json", "chunks.json")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def assert_publishable(value: Any, *, _path: str = "$") -> None:
    """Fail closed on any forbidden key (unless explicitly False/None), secret pattern or local path."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key).lower()
            if name in FORBIDDEN_KEYS and item not in (False, None):
                raise ValueError(f"publication refused: forbidden field {_path}.{key}")
            assert_publishable(item, _path=f"{_path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_publishable(item, _path=f"{_path}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in SensorPrivacyGate.SECRET_PATTERNS):
            raise ValueError(f"publication refused: secret-like value at {_path}")
        if _PATHLIKE.search(value):
            raise ValueError(f"publication refused: local path at {_path}")


def _bundle_digest(files: Mapping[str, bytes]) -> str:
    return _digest(_canonical({name: _digest(files[name]) for name in FILE_NAMES}))


def build_publication_bundle(record: Mapping[str, Any], signer: Any, *, key_id: str) -> dict[str, Any]:
    if record.get("status") != "promoted" or not (record.get("receipt") or {}).get("promoted"):
        raise PermissionError("only locally promoted crystals with a passing held-out receipt may be published")
    candidate: CodingCrystalCandidate = record.get("candidate_object") or CodingCrystalCandidate.from_dict(record["candidate"])
    candidate.validate()
    candidate_dict = candidate.to_dict()
    assert_publishable(candidate_dict)
    payload = _canonical(candidate_dict)
    chunk_manifest = chunk_bytes(payload, chunk_size=CHUNK_SIZE)
    chunks = {}
    for chunk in chunk_manifest["chunks"]:
        chunks[chunk["digest"]] = payload[chunk["offset"]:chunk["offset"] + chunk["size"]]
    manifest = {
        "schema": PUBLICATION_SCHEMA, "crystal_id": candidate.crystal_id, "task_family": candidate.task_family,
        "candidate_digest": candidate.digest, "steps": [dict(step) for step in candidate.steps],
        "parameters": list(candidate.parameters), "payload_root_digest": chunk_manifest["root_digest"],
        "privacy": {"native_kv": False, "memfd_descriptors": False, "prompts": False, "workspace_content": False,
                    "secrets": False},
        "authority": "hypothesis_only_requires_local_reproduction",
    }
    compatibility = {
        "coding_catalog_version": CODING_CATALOG_VERSION, "opcode_catalog_digest": candidate.opcode_catalog_digest,
        "reviewed_tools": sorted(REVIEWED_TOOLS), "crystal_parameters": list(CRYSTAL_PARAMETERS),
        "envelope_schema": ENVELOPE_SCHEMA,
    }
    receipt = dict(record["receipt"])
    proofs = {
        "heldout_replay": {key: receipt.get(key) for key in ("candidate_id", "attempts", "successes", "promoted", "reason",
                                                             "variant_ids", "variant_results")},
        "source_envelope_digest": candidate.source_envelope_digest, "candidate_digest": candidate.digest,
        "registry_record_digest": record.get("record_digest", ""),
        "learned_budget": dict(candidate.learned_budget), "reuse_count": int(record.get("reuse_count") or 0),
    }
    for item in (manifest, compatibility, proofs, chunk_manifest):
        assert_publishable(item)
    files = {
        "manifest.json": _canonical(manifest), "compatibility.json": _canonical(compatibility),
        "proofs.json": _canonical(proofs), "chunks.json": _canonical(chunk_manifest),
    }
    bundle_digest = _bundle_digest(files)
    signature = base64.b64encode(signer.sign(bundle_digest.encode("ascii"))).decode("ascii")
    files["signature.json"] = _canonical({"algorithm": "ed25519", "key_id": key_id, "bundle_digest": bundle_digest,
                                          "signature": signature})
    return {"crystal_id": candidate.crystal_id, "task_family": candidate.task_family, "files": files,
            "chunks": chunks, "bundle_digest": bundle_digest}


def _chunk_path(digest: str) -> str:
    return f"xet/objects/{digest[7:9]}/{digest[9:]}"


DATASET_CARD = (
    "---\nlicense: other\npretty_name: BEAST Coding Crystals\ntags:\n- beast\n- crystal\n---\n\n"
    "# BEAST coding crystals\n\nPrivacy-filtered manifests, Xet-style content chunks, compatibility metadata and "
    "held-out replay proofs for reviewed coding crystals. No native KV, descriptors, prompts, workspace content or "
    "secrets. Every imported crystal is a quarantined hypothesis until reproduced locally.\n"
)


class CrystalPublisher:
    def __init__(self, remote: Any, dataset_id: str):
        if not re.fullmatch(r"[A-Za-z0-9][\w.-]*/[\w.-]+", str(dataset_id or "")):
            raise ValueError("dataset_id must be OWNER/NAME")
        self.remote = remote
        self.dataset_id = dataset_id

    def publish(self, bundle: Mapping[str, Any], *, mode: str = "pr", private: bool = True) -> dict[str, Any]:
        if mode not in {"pr", "commit"}:
            raise ValueError("mode must be 'pr' or 'commit'")
        for data in bundle["files"].values():
            assert_publishable(json.loads(data))
        self.remote.ensure_dataset(self.dataset_id, private=private)
        uploaded = reused = 0
        for digest, payload in sorted(bundle["chunks"].items()):
            if _digest(payload) != digest:
                raise ValueError("chunk digest mismatch before upload")
            if self.remote.has_chunk(self.dataset_id, digest):
                reused += 1
                continue
            self.remote.upload_chunk(self.dataset_id, digest, payload)
            uploaded += 1
        prefix = f"crystals/{bundle['task_family']}/{bundle['crystal_id']}/"
        files = {prefix + name: data for name, data in bundle["files"].items()}
        files["README.md"] = DATASET_CARD.encode("utf-8")
        title = f"Publish coding crystal {bundle['crystal_id']}"
        receipt: dict[str, Any] = {"dataset": self.dataset_id, "crystal_id": bundle["crystal_id"], "mode": mode,
                                   "private": private, "chunks_uploaded": uploaded, "chunks_reused": reused,
                                   "bundle_digest": bundle["bundle_digest"], "paths": sorted(files)}
        if mode == "pr":
            branch = "crystal-" + bundle["crystal_id"].split(":", 1)[-1][:16]
            result = self.remote.create_branch_and_pr(self.dataset_id, files, branch=branch, title=title,
                                                      description="Held-out-replayed coding crystal; import is quarantined.")
            receipt.update({"branch": branch, "commit": result.get("commit", ""), "pull_request": result.get("pull_request", "")})
        else:
            receipt["commit"] = self.remote.commit_files(self.dataset_id, files, message=title)
        return receipt


class CrystalImporter:
    def __init__(self, remote: Any, dataset_id: str, registry: CodingCrystalRegistry):
        self.remote = remote
        self.dataset_id = dataset_id
        self.registry = registry

    def pull(self, task_family: str, crystal_id: str, *, trusted_keys: Mapping[str, Any], revision: str = "main") -> dict[str, Any]:
        prefix = f"crystals/{task_family}/{crystal_id}/"
        files = {name: bytes(self.remote.read_file(self.dataset_id, prefix + name, revision=revision))
                 for name in (*FILE_NAMES, "signature.json")}
        docs = {name: json.loads(data) for name, data in files.items()}
        for doc in docs.values():
            assert_publishable(doc)
        manifest, compatibility, chunk_manifest = docs["manifest.json"], docs["compatibility.json"], docs["chunks.json"]
        if manifest.get("schema") != PUBLICATION_SCHEMA or manifest.get("crystal_id") != crystal_id:
            raise ValueError("publication manifest does not match the requested crystal")
        if compatibility.get("opcode_catalog_digest") != coding_catalog_digest():
            raise ValueError("crystal compiled against an incompatible opcode catalog")
        if set(compatibility.get("reviewed_tools") or []) - REVIEWED_TOOLS:
            raise ValueError("crystal declares unreviewed tools")
        payload = b""
        for chunk in sorted(chunk_manifest.get("chunks") or [], key=lambda c: int(c["index"])):
            data = bytes(self.remote.read_file(self.dataset_id, _chunk_path(chunk["digest"]), revision=revision))
            if _digest(data) != chunk["digest"] or len(data) != int(chunk["size"]) or len(payload) != int(chunk["offset"]):
                raise ValueError("portable chunk failed digest verification")
            payload += data
        if chunk_bytes(payload, chunk_size=CHUNK_SIZE)["root_digest"] != manifest.get("payload_root_digest"):
            raise ValueError("portable chunk root mismatch")
        candidate = CodingCrystalCandidate.from_dict(json.loads(payload))  # structural validation: reviewed ops only
        if candidate.crystal_id != crystal_id or candidate.digest != manifest.get("candidate_digest"):
            raise ValueError("candidate digest does not match the publication manifest")
        signature_doc = docs["signature.json"]
        bundle_digest = _bundle_digest(files)
        if signature_doc.get("bundle_digest") != bundle_digest:
            raise ValueError("publication bundle digest mismatch")
        key_id = str(signature_doc.get("key_id") or "")
        signer_trusted = False
        if key_id in trusted_keys:
            try:
                trusted_keys[key_id].verify(base64.b64decode(signature_doc.get("signature") or "", validate=True),
                                            bundle_digest.encode("ascii"))
            except Exception as exc:
                raise ValueError("publication signature invalid for a trusted key") from exc
            signer_trusted = True
        provenance = {"dataset": self.dataset_id, "revision": revision, "signer_key_id": key_id,
                      "signer_trusted": signer_trusted, "bundle_digest": bundle_digest,
                      "remote_proofs": docs["proofs.json"]}
        return self.registry.add_quarantined(candidate, provenance=provenance)


def reproduce_quarantined(registry: CodingCrystalRegistry, crystal_id: str, variants: Sequence[Any], run_variant: Any,
                          *, promote: bool = True) -> Any:
    """Local held-out reproduction; only this can promote an imported crystal."""
    record = registry.get(crystal_id)
    if record["status"] not in {"quarantined", "promoted"}:
        raise PermissionError("only quarantined crystals are reproduced here")
    provenance = record.get("provenance") or {}
    reproduction = {"mode": "reproduce", "prior_status": record["status"],
                    "bundle_digest": provenance.get("bundle_digest", ""), "dataset": provenance.get("dataset", ""),
                    "revision": provenance.get("revision", ""), "signer_key_id": provenance.get("signer_key_id", "")}
    return replay_candidate(registry, record["candidate_object"], variants, run_variant, promote=promote,
                            reproduction=reproduction)


__all__ = ["CrystalImporter", "CrystalPublisher", "assert_publishable", "build_publication_bundle",
           "reproduce_quarantined"]
