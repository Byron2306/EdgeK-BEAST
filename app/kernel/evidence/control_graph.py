"""Content-addressed control evidence graph for DevSecOps receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import fcntl
import base64
from typing import Any, Dict, Tuple, Optional
from pathlib import Path


@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    node_type: str
    receipt: Dict[str, Any]
    digest: str


class ControlEvidenceGraph:
    RELATIONS = frozenset({
        "PRODUCES", "DERIVED_FROM", "VERIFIED_BY", "APPROVED_BY",
        "DEPLOYED_AS", "OBSERVED_BY", "ROLLED_BACK_BY", "SUPERSEDES",
        "ATTESTED_BY", "EXECUTED_ON", "USES", "TRIGGERED",
    })

    def __init__(self, path: Optional[str | Path] = None, *, checkpoint_path: Optional[str | Path] = None,
                 head_signer=None, head_verifier=None):
        self.nodes: Dict[str, EvidenceNode] = {}
        self.links: list[Tuple[str, str, str]] = []
        self.path = Path(path) if path else None
        self.checkpoint_path = (
            Path(checkpoint_path) if checkpoint_path else
            (self.path.with_name(self.path.name + ".head.json") if self.path else None)
        )
        self.head_signer = head_signer
        self.head_verifier = head_verifier
        self.integrity_ok = True
        self._last_record_hash = ""
        self.quarantined_records: list[Dict[str, Any]] = []
        self.integrity_fracture: Dict[str, Any] | None = None
        if self.path and self.path.exists(): self.reconstruct()

    def add(self, node_type: str, receipt: Dict[str, Any]) -> EvidenceNode:
        receipt = {**receipt, "issuer": receipt.get("issuer", "beast"), "policy_generation": receipt.get("policy_generation", "unknown")}
        body = {"node_type": node_type, "receipt": receipt}
        digest = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        node = EvidenceNode(digest, node_type, dict(receipt), digest)
        self._persist({"kind":"node","node_type":node_type,"receipt":receipt})
        self.nodes[digest] = node
        return node

    def link(self, source: EvidenceNode, relation: str, target: EvidenceNode) -> None:
        if relation not in self.RELATIONS:
            raise ValueError(f"unsupported evidence relation: {relation}")
        if source.node_id not in self.nodes or target.node_id not in self.nodes:
            raise ValueError("evidence nodes must be registered before linking")
        edge = (source.node_id, relation, target.node_id)
        if edge in self.links:
            return
        self._persist({"kind":"link","source":source.node_id,"relation":relation,"target":target.node_id})
        self.links.append(edge)

    def query(self, node_type: str) -> tuple[EvidenceNode, ...]:
        return tuple(node for node in self.nodes.values() if node.node_type == node_type)

    def _persist(self, record: Dict[str, Any]) -> None:
        if not self.path: return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            existing_lines = handle.read().splitlines()
            last_hash, valid = self._validated_head(existing_lines)
            if not valid:
                raise RuntimeError("refusing to append after evidence integrity fracture")
            if not self._checkpoint_matches(last_hash, len(existing_lines)):
                raise RuntimeError("refusing to append after evidence head checkpoint mismatch")
            persisted = {
                **record,
                "prev_hash": last_hash,
                "record_hash": "sha256:" + hashlib.sha256((last_hash + canonical).encode()).hexdigest(),
            }
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(persisted, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            self._last_record_hash = persisted["record_hash"]
            self._write_checkpoint(self._last_record_hash, len(existing_lines) + 1)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _checkpoint_body(record_hash: str, record_count: int) -> bytes:
        return json.dumps(
            {"record_count": record_count, "record_hash": record_hash, "version": "beast.evidence-head.v1"},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")

    def _write_checkpoint(self, record_hash: str, record_count: int) -> None:
        if self.checkpoint_path is None:
            return
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        body = self._checkpoint_body(record_hash, record_count)
        signature = base64.b64encode(self.head_signer.sign(body)).decode("ascii") if self.head_signer else ""
        payload = {"record_count": record_count, "record_hash": record_hash,
                   "version": "beast.evidence-head.v1", "signature": signature}
        temporary = self.checkpoint_path.with_name(self.checkpoint_path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.checkpoint_path)
        directory_fd = os.open(self.checkpoint_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _checkpoint_matches(self, record_hash: str, record_count: int) -> bool:
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return True
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            if payload.get("record_hash") != record_hash or payload.get("record_count") != record_count:
                return False
            if self.head_verifier is not None:
                signature = base64.b64decode(str(payload.get("signature") or ""), validate=True)
                self.head_verifier.verify(signature, self._checkpoint_body(record_hash, record_count))
            return True
        except Exception:
            return False

    @staticmethod
    def _validated_head(lines: list[str]) -> tuple[str, bool]:
        head = ""
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return head, False
            supplied = record.pop("record_hash", "")
            previous = record.pop("prev_hash", "")
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
            calculated = "sha256:" + hashlib.sha256((previous + canonical).encode()).hexdigest()
            if not supplied or previous != head or supplied != calculated:
                return head, False
            head = supplied
        return head, True

    def reconstruct(self) -> Dict[str, int]:
        self.nodes.clear(); self.links.clear(); self.integrity_ok = True; self._last_record_hash = ""
        self.quarantined_records.clear(); self.integrity_fracture = None
        if not self.path or not self.path.exists(): return {"nodes":0,"links":0}
        with self.path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            lines = handle.read().splitlines()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        fractured = False
        for line_number, line in enumerate(lines, 1):
            if fractured:
                self.quarantined_records.append({"line": line_number, "raw": line})
                continue
            try:
                record=json.loads(line)
            except json.JSONDecodeError:
                self.integrity_ok = False; fractured = True
                self.integrity_fracture = {"line": line_number, "reason": "malformed_json"}
                self.quarantined_records.append({"line": line_number, "raw": line})
                continue
            supplied_hash = record.pop("record_hash", "")
            previous = record.pop("prev_hash", "")
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
            calculated = "sha256:" + hashlib.sha256((previous + canonical).encode()).hexdigest()
            if not supplied_hash or previous != self._last_record_hash or supplied_hash != calculated:
                self.integrity_ok = False; fractured = True
                self.integrity_fracture = {"line": line_number, "reason": "hash_chain_mismatch"}
                self.quarantined_records.append({"line": line_number, "record": record})
                continue
            self._last_record_hash = supplied_hash
            if record.get("kind")=="node":
                node_type=record.get("node_type","unknown"); receipt=record.get("receipt") or {}
                body={"node_type":node_type,"receipt":receipt}; digest="sha256:"+hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
                self.nodes[digest]=EvidenceNode(digest,node_type,dict(receipt),digest)
            elif (record.get("kind")=="link" and record.get("relation") in self.RELATIONS
                  and record.get("source") in self.nodes and record.get("target") in self.nodes):
                edge=(record["source"],record["relation"],record["target"])
                if edge not in self.links: self.links.append(edge)
            else:
                self.integrity_ok = False; fractured = True
                self.integrity_fracture = {"line": line_number, "reason": "invalid_record_contract"}
                self.quarantined_records.append({"line": line_number, "record": record})
        if self.integrity_ok and not self._checkpoint_matches(self._last_record_hash, len(lines)):
            self.integrity_ok = False
            self.integrity_fracture = {"line": len(lines) + 1, "reason": "head_checkpoint_mismatch"}
        return {"nodes":len(self.nodes),"links":len(self.links)}
