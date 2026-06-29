"""Editable BEAST Memory Hull vault.

The Memory Hull writes human-readable Markdown residue plus a signed JSON
sidecar. It complements Chronicle/vector memory by making operational memory
visible, editable, indexed, and tamper-evident.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.security.residue_seal import ResidueSeal, canonical_bytes


VAULT_SECTIONS = [
    "projects",
    "tasks",
    "decisions",
    "provider_receipts",
    "quality_cascade",
    "residue",
    "policies",
]

HULL_VERSION = "2.0"


class MemoryHull:
    """Local editable BEAST vault rooted under ``~/.beast/vault`` by default."""

    def __init__(self, root: Optional[Path] = None, *, seal: Optional[ResidueSeal] = None):
        self.root = (root or Path.home() / ".beast" / "vault").resolve()
        self.seal = seal or ResidueSeal(self.root.parent / "keys" / "residue")
        self.index_dir = self.root / ".index"
        for section in VAULT_SECTIONS:
            (self.root / section).mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def write_residue(
        self,
        *,
        task: str,
        provider: str = "",
        cost_saved: Any = "",
        files_touched: Optional[Iterable[str]] = None,
        decision: str = "",
        evidence: Optional[Dict[str, Any]] = None,
        section: str = "tasks",
        policy_tags: Optional[Iterable[str]] = None,
        caller: str = "spiffe://beast.local/runtime-governor",
        correlation_id: str = "",
    ) -> Dict[str, Any]:
        self._validate_section(section)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "beast_object_type": "memory_hull_residue",
            "version": HULL_VERSION,
            "task": str(task),
            "provider": str(provider),
            "cost_saved": cost_saved,
            "files_touched": [str(item) for item in (files_touched or [])],
            "decision": str(decision),
            "evidence": evidence or {},
            "policy_tags": [str(item) for item in (policy_tags or [])],
            "created_at": now,
            "section": section,
            "caller": str(caller),
            "correlation_id": str(correlation_id),
            "beast_systems": {
                "chronicle_compatible": True,
                "vault_editable": True,
                "residue_sealed": True,
            },
        }
        payload["residue_id"] = "residue_" + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:20]
        markdown = self._render_markdown(payload)
        markdown_hash = self._sha256_text(markdown)
        payload["markdown_sha256"] = markdown_hash
        seal = self.seal.sign(payload, purpose=f"memory_hull_{section}")
        sidecar = {
            "beast_object_type": "memory_hull_sidecar",
            "version": HULL_VERSION,
            "payload": payload,
            "residue_seal": seal,
            "markdown_sha256": markdown_hash,
        }

        target = self._section_path(section) / f"{payload['residue_id']}.md"
        sidecar_path = target.with_suffix(".residue.json")
        self._atomic_write_text(target, markdown)
        self._atomic_write_text(sidecar_path, json.dumps(sidecar, indent=2, sort_keys=True) + "\n")
        verification = self.verify_sidecar(sidecar_path)
        self._upsert_index(payload, target, sidecar_path, verification)
        return {
            "beast_object_type": "memory_hull_write_receipt",
            "version": HULL_VERSION,
            "residue_id": payload["residue_id"],
            "section": section,
            "markdown_path": str(target),
            "sidecar_path": str(sidecar_path),
            "residue_seal": seal,
            "verified": verification["verified"],
            "index_path": str(self._index_path()),
        }

    def verify_sidecar(self, sidecar_path: Path) -> Dict[str, Any]:
        path = self._contained_path(sidecar_path)
        if path.suffix != ".json" or not path.name.endswith(".residue.json"):
            return self._verification(False, str(path), "not_a_residue_sidecar")
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._verification(False, str(path), type(exc).__name__)

        payload = sidecar.get("payload") if isinstance(sidecar.get("payload"), dict) else {}
        seal = sidecar.get("residue_seal") if isinstance(sidecar.get("residue_seal"), dict) else {}
        section = str(payload.get("section") or "")
        if section not in VAULT_SECTIONS:
            return self._verification(False, str(path), "invalid_section")

        markdown_path = self._markdown_path_for_sidecar(path)
        markdown_hash = ""
        markdown_ok = False
        if markdown_path.exists():
            markdown_hash = self._sha256_text(markdown_path.read_text(encoding="utf-8"))
            markdown_ok = (
                sidecar.get("markdown_sha256") == markdown_hash
                and payload.get("markdown_sha256") == markdown_hash
            )

        verification = self.seal.verify(payload, seal, expected_purpose=f"memory_hull_{section}")
        verified = bool(verification.get("verified") and markdown_ok)
        return {
            "beast_object_type": "memory_hull_verification",
            "version": HULL_VERSION,
            "verified": verified,
            "reason": "ok" if verified else "verification_failed",
            "seal": verification,
            "markdown_hash_valid": markdown_ok,
            "markdown_sha256": markdown_hash,
            "sidecar_path": str(path),
            "markdown_path": str(markdown_path),
        }

    def inventory(self, *, verify: bool = False) -> Dict[str, Any]:
        sections = {}
        verified_count = 0
        failed_count = 0
        for section in VAULT_SECTIONS:
            root = self._section_path(section)
            markdown = sorted(root.glob("*.md"))
            sidecars = sorted(root.glob("*.residue.json"))
            section_record = {"markdown": len(markdown), "sidecars": len(sidecars)}
            if verify:
                verifications = [self.verify_sidecar(path) for path in sidecars]
                section_verified = sum(1 for item in verifications if item.get("verified"))
                section_failed = len(verifications) - section_verified
                verified_count += section_verified
                failed_count += section_failed
                section_record["verified"] = section_verified
                section_record["failed"] = section_failed
            sections[section] = section_record
        return {
            "beast_object_type": "memory_hull_inventory",
            "version": HULL_VERSION,
            "root": str(self.root),
            "sections": sections,
            "editable": True,
            "sidecar_sealed": True,
            "index_path": str(self._index_path()),
            "verified_sidecars": verified_count if verify else None,
            "failed_sidecars": failed_count if verify else None,
        }

    def list_residue(self, *, section: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        records = self._read_index().get("records", [])
        if section is not None:
            self._validate_section(section)
            records = [record for record in records if record.get("section") == section]
        return sorted(records, key=lambda record: str(record.get("created_at") or ""), reverse=True)[: max(1, int(limit))]

    def search(self, query: str, *, section: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        needle = str(query or "").lower()
        if not needle:
            return []
        results = []
        for record in self.list_residue(section=section, limit=1000):
            haystack = " ".join(
                str(record.get(key) or "")
                for key in ("residue_id", "task", "provider", "decision", "policy_tags")
            ).lower()
            if needle in haystack:
                results.append(record)
        return results[: max(1, int(limit))]

    @staticmethod
    def _render_markdown(payload: Dict[str, Any]) -> str:
        files = "\n".join(f"- `{item}`" for item in payload.get("files_touched") or []) or "- none"
        evidence = json.dumps(payload.get("evidence") or {}, indent=2, sort_keys=True)
        tags = ", ".join(payload.get("policy_tags") or []) or "none"
        return (
            f"# BEAST Residue: {payload['task']}\n\n"
            f"- Residue ID: `{payload['residue_id']}`\n"
            f"- Created: `{payload['created_at']}`\n"
            f"- Section: `{payload['section']}`\n"
            f"- Caller: `{payload['caller']}`\n"
            f"- Provider: `{payload['provider']}`\n"
            f"- Cost saved: `{payload['cost_saved']}`\n"
            f"- Policy tags: `{tags}`\n\n"
            "## Files touched\n\n"
            f"{files}\n\n"
            "## Decision\n\n"
            f"{payload['decision'] or 'n/a'}\n\n"
            "## Evidence\n\n"
            "```json\n"
            f"{evidence}\n"
            "```\n"
        )

    def _upsert_index(self, payload: Dict[str, Any], markdown_path: Path, sidecar_path: Path, verification: Dict[str, Any]) -> None:
        index = self._read_index()
        records = [record for record in index.get("records", []) if record.get("residue_id") != payload["residue_id"]]
        records.append(
            {
                "residue_id": payload["residue_id"],
                "section": payload["section"],
                "task": payload["task"],
                "provider": payload["provider"],
                "decision": payload["decision"],
                "policy_tags": payload.get("policy_tags") or [],
                "created_at": payload["created_at"],
                "markdown_path": str(markdown_path),
                "sidecar_path": str(sidecar_path),
                "verified": bool(verification.get("verified")),
                "payload_sha256": verification.get("seal", {}).get("payload_sha256"),
            }
        )
        index_payload = {
            "beast_object_type": "memory_hull_index",
            "version": HULL_VERSION,
            "root": str(self.root),
            "record_count": len(records),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": sorted(records, key=lambda record: str(record.get("created_at") or "")),
        }
        index_payload["index_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(index_payload)).hexdigest()
        index_payload["residue_seal"] = self.seal.sign(index_payload, purpose="memory_hull_index")
        self._atomic_write_text(self._index_path(), json.dumps(index_payload, indent=2, sort_keys=True) + "\n")

    def _read_index(self) -> Dict[str, Any]:
        path = self._index_path()
        if not path.exists():
            return {"records": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"records": []}
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        payload["records"] = records
        return payload

    def _section_path(self, section: str) -> Path:
        self._validate_section(section)
        return self.root / section

    def _contained_path(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"path escapes memory hull root: {path}") from exc
        return resolved

    def _index_path(self) -> Path:
        return self.index_dir / "residue_index.json"

    @staticmethod
    def _markdown_path_for_sidecar(path: Path) -> Path:
        name = path.name
        if not name.endswith(".residue.json"):
            return path.with_suffix(".md")
        return path.with_name(name[: -len(".residue.json")] + ".md")

    @staticmethod
    def _validate_section(section: str) -> None:
        if section not in VAULT_SECTIONS:
            raise ValueError(f"unknown memory hull section: {section}")

    @staticmethod
    def _sha256_text(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)

    @staticmethod
    def _verification(verified: bool, sidecar_path: str, reason: str) -> Dict[str, Any]:
        return {
            "beast_object_type": "memory_hull_verification",
            "version": HULL_VERSION,
            "verified": verified,
            "reason": reason,
            "sidecar_path": sidecar_path,
        }


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "residue"
