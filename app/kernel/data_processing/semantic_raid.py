"""Semantic RAID and artifact fossil layers for Crystal Compute."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")


def _sha(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class SemanticRaidShard:
    shard_id: str
    artifact_type: str
    digest: str
    primary_ref: str
    mirror_refs: List[str]
    index_refs: List[str]
    value_score: float
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["beast_object_type"] = "semantic_raid_shard"
        payload["version"] = "1.0"
        return payload


class SemanticRaidStore:
    """Redundant content-addressed storage for high-value compute evidence."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.primary = self.root / "primary"
        self.mirrors = [self.root / "mirror_a", self.root / "mirror_b"]
        self.indexes = [self.root / "index_a", self.root / "index_b"]
        self.manifest_path = self.root / "semantic_raid_manifest.json"
        for path in [self.primary, *self.mirrors, *self.indexes]:
            path.mkdir(parents=True, exist_ok=True)

    def store_shard(self, artifact_type: str, payload: Dict[str, Any], *, value_score: float = 0.5) -> SemanticRaidShard:
        digest = _sha(payload)
        stem = digest.removeprefix("sha256:")
        envelope = {
            "beast_object_type": "semantic_raid_payload",
            "version": "1.0",
            "artifact_type": artifact_type,
            "digest": digest,
            "payload": payload,
            "created_at": _now(),
        }
        primary_path = self.primary / f"{stem}.json"
        mirror_paths = [path / f"{stem}.json" for path in self.mirrors]
        for path in [primary_path, *mirror_paths]:
            _atomic_json(path, envelope)
        index_payload = {
            "beast_object_type": "semantic_raid_index_entry",
            "version": "1.0",
            "digest": digest,
            "artifact_type": artifact_type,
            "value_score": max(0.0, min(1.0, float(value_score))),
            "payload_ref": str(primary_path.relative_to(self.root)),
        }
        index_paths = [path / f"{stem}.index.json" for path in self.indexes]
        for path in index_paths:
            _atomic_json(path, index_payload)
        shard = SemanticRaidShard(
            shard_id="raid_" + stem[:20],
            artifact_type=artifact_type,
            digest=digest,
            primary_ref=str(primary_path.relative_to(self.root)),
            mirror_refs=[str(path.relative_to(self.root)) for path in mirror_paths],
            index_refs=[str(path.relative_to(self.root)) for path in index_paths],
            value_score=max(0.0, min(1.0, float(value_score))),
            created_at=_now(),
        )
        manifest = self._manifest()
        manifest["shards"][shard.shard_id] = shard.to_dict()
        _atomic_json(self.manifest_path, manifest)
        return shard

    def integrity_report(self) -> Dict[str, Any]:
        manifest = self._manifest()
        corrupt: List[Dict[str, str]] = []
        missing: List[Dict[str, str]] = []
        for shard in manifest["shards"].values():
            refs = [shard["primary_ref"], *shard["mirror_refs"]]
            for ref in refs:
                state = self._payload_state(ref, shard["digest"])
                if state == "missing":
                    missing.append({"shard_id": shard["shard_id"], "ref": ref})
                elif state == "corrupt":
                    corrupt.append({"shard_id": shard["shard_id"], "ref": ref})
            for ref in shard["index_refs"]:
                if not (self.root / ref).is_file():
                    missing.append({"shard_id": shard["shard_id"], "ref": ref})
        total_refs = sum(1 + len(row["mirror_refs"]) + len(row["index_refs"]) for row in manifest["shards"].values())
        bad = len(corrupt) + len(missing)
        return {
            "beast_object_type": "semantic_raid_integrity_report",
            "version": "1.0",
            "shards": len(manifest["shards"]),
            "total_refs": total_refs,
            "corrupt_refs": corrupt,
            "missing_refs": missing,
            "artifact_integrity_rate": round((total_refs - bad) / total_refs, 6) if total_refs else 1.0,
            "ok": bad == 0,
        }

    def reconstruct(self) -> Dict[str, Any]:
        manifest = self._manifest()
        repaired = 0
        unrecoverable: List[str] = []
        for shard in manifest["shards"].values():
            refs = [shard["primary_ref"], *shard["mirror_refs"]]
            good_payload = None
            for ref in refs:
                if self._payload_state(ref, shard["digest"]) == "ok":
                    good_payload = json.loads((self.root / ref).read_text(encoding="utf-8"))
                    break
            if good_payload is None:
                unrecoverable.append(shard["shard_id"])
                continue
            for ref in refs:
                if self._payload_state(ref, shard["digest"]) != "ok":
                    _atomic_json(self.root / ref, good_payload)
                    repaired += 1
        return {
            "beast_object_type": "semantic_raid_reconstruction_report",
            "version": "1.0",
            "repaired_refs": repaired,
            "unrecoverable": unrecoverable,
            "ok": not unrecoverable,
        }

    def garbage_collect(self, *, min_value_score: float = 0.0) -> Dict[str, Any]:
        manifest = self._manifest()
        retained = {}
        collected = 0
        for shard_id, shard in manifest["shards"].items():
            if float(shard.get("value_score") or 0.0) >= min_value_score:
                retained[shard_id] = shard
            else:
                collected += 1
        manifest["shards"] = retained
        _atomic_json(self.manifest_path, manifest)
        return {
            "beast_object_type": "semantic_raid_gc_report",
            "version": "1.0",
            "retained": len(retained),
            "collected": collected,
        }

    def _payload_state(self, ref: str, digest: str) -> str:
        path = self.root / ref
        if not path.is_file():
            return "missing"
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            actual = _sha(envelope.get("payload"))
            return "ok" if actual == digest == envelope.get("digest") else "corrupt"
        except (OSError, json.JSONDecodeError, TypeError):
            return "corrupt"

    def _manifest(self) -> Dict[str, Any]:
        if self.manifest_path.is_file():
            try:
                payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(payload.get("shards"), dict):
                    return payload
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        return {
            "beast_object_type": "semantic_raid_manifest",
            "version": "1.0",
            "shards": {},
            "created_at": _now(),
        }


class ArtifactFossilLayerStore:
    """Differential lifecycle checkpoints with deterministic replay hashes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "artifact_fossil_layers.json"

    def checkpoint(
        self,
        artifact_id: str,
        state: Dict[str, Any],
        *,
        decision: str,
        evidence_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        history = self._history()
        previous = history[-1] if history else None
        parent_hash = str((previous or {}).get("checkpoint_hash") or "")
        diff = self._diff((previous or {}).get("state") if previous else {}, state)
        payload = {
            "beast_object_type": "artifact_fossil_checkpoint",
            "version": "1.0",
            "artifact_id": artifact_id,
            "parent_hash": parent_hash,
            "decision": decision,
            "evidence_ids": list(evidence_ids or []),
            "diff": diff,
            "state": state,
            "created_at": _now(),
        }
        payload["checkpoint_hash"] = _sha({
            "artifact_id": artifact_id,
            "parent_hash": parent_hash,
            "decision": decision,
            "evidence_ids": payload["evidence_ids"],
            "diff": diff,
        })
        history.append(payload)
        _atomic_json(self.path, {"beast_object_type": "artifact_fossil_layers", "version": "1.0", "checkpoints": history})
        return payload

    def replay(self) -> Dict[str, Any]:
        history = self._history()
        state: Dict[str, Any] = {}
        decisions: List[str] = []
        valid = True
        parent_hash = ""
        for checkpoint in history:
            expected = _sha({
                "artifact_id": checkpoint.get("artifact_id"),
                "parent_hash": parent_hash,
                "decision": checkpoint.get("decision"),
                "evidence_ids": checkpoint.get("evidence_ids") or [],
                "diff": checkpoint.get("diff") or {},
            })
            if checkpoint.get("checkpoint_hash") != expected:
                valid = False
            parent_hash = str(checkpoint.get("checkpoint_hash") or "")
            state = dict(checkpoint.get("state") or {})
            decisions.append(str(checkpoint.get("decision") or ""))
        replay_hash = _sha({"decisions": decisions, "state": state})
        return {
            "beast_object_type": "artifact_fossil_replay",
            "version": "1.0",
            "checkpoint_count": len(history),
            "valid_lineage": valid,
            "decisions": decisions,
            "final_state": state,
            "replay_hash": replay_hash,
        }

    def _history(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            checkpoints = payload.get("checkpoints") if isinstance(payload, dict) else []
            return [item for item in checkpoints if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _diff(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        diff = {}
        keys = set(previous) | set(current)
        for key in sorted(keys):
            if previous.get(key) != current.get(key):
                diff[key] = {"before": previous.get(key), "after": current.get(key)}
        return diff
