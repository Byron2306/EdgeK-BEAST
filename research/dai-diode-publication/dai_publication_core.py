#!/usr/bin/env python3
"""Fail-closed DAI-Diode publication, lineage, mutation, and ablation harness.

This module does not execute BEAST or grant authority. It verifies and packages
immutable research evidence. All integrity failures raise PublicationError and
all CLI failures exit non-zero.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


RELEASE_MANIFEST = "RELEASE_MANIFEST.json"
RELEASE_SIGNATURE = "RELEASE_MANIFEST.sig.json"
PUBLISHER_PUBLIC_KEY = "publisher.ed25519.pub.pem"
EXACT_UNSIGNED_METADATA = frozenset({RELEASE_MANIFEST, RELEASE_SIGNATURE})
SHA256_RE = re.compile(r"sha256:([0-9a-f]{64})\b")
PHASE_RE = re.compile(r"Phase[-_ ](?P<phase>[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
LINEAGE_KEY_RE = re.compile(
    r"(?:predecessor|prior|parent|ancestor|fossil|release_zip|artifact)_?.*(?:digest|sha256)|"
    r"(?:predecessor|prior|parent|ancestor|fossil)",
    re.IGNORECASE,
)
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
MAX_ZIP_ENTRIES = 100_000
MAX_COMPRESSION_RATIO = 250
MAX_LINEAGE_NODES = 512
MAX_LINEAGE_DEPTH = 12


class PublicationError(RuntimeError):
    """A fail-closed publication validation error."""


class DuplicateKeyError(PublicationError):
    """Raised when JSON contains duplicate object keys."""


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ZipRecord:
    path: str
    size_bytes: int
    compressed_size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "compressed_size": self.compressed_size,
            "sha256": self.sha256,
        }


def fail(message: str) -> None:
    raise PublicationError(message)


def refuse_optimized_python() -> None:
    if sys.flags.optimize:
        fail("optimized Python is forbidden for the publication verifier")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _object_pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json_bytes(data: bytes, *, source: str) -> Any:
    if len(data) > MAX_JSON_BYTES:
        fail(f"JSON object exceeds limit: {source}")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_object_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        fail(f"invalid JSON in {source}: {exc}")


def load_json_file(path: Path) -> Any:
    return load_json_bytes(path.read_bytes(), source=str(path))


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def normalize_relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        fail("path must be a non-empty string")
    if "\x00" in raw:
        fail(f"NUL byte in path: {raw!r}")
    if "\\" in raw:
        fail(f"backslash is forbidden in canonical paths: {raw!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        fail(f"control character in path: {raw!r}")
    normalized = unicodedata.normalize("NFC", raw)
    if normalized != raw:
        fail(f"path is not Unicode NFC-normalized: {raw!r}")
    pure = PurePosixPath(raw)
    if pure.is_absolute():
        fail(f"absolute path is forbidden: {raw!r}")
    parts = pure.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail(f"non-canonical path component: {raw!r}")
    if parts[0].endswith(":"):
        fail(f"drive-qualified path is forbidden: {raw!r}")
    canonical = pure.as_posix()
    if canonical != raw:
        fail(f"path is not canonical: {raw!r} != {canonical!r}")
    return canonical


def _check_collision_sets(
    path: str,
    exact: set[str],
    casefolded: dict[str, str],
    normalized: dict[str, str],
) -> None:
    if path in exact:
        fail(f"duplicate path: {path}")
    folded = path.casefold()
    if folded in casefolded and casefolded[folded] != path:
        fail(f"case-fold path collision: {casefolded[folded]!r} vs {path!r}")
    nfc = unicodedata.normalize("NFC", path)
    if nfc in normalized and normalized[nfc] != path:
        fail(f"Unicode-normalization path collision: {normalized[nfc]!r} vs {path!r}")
    exact.add(path)
    casefolded[folded] = path
    normalized[nfc] = path


def inventory_directory(root: Path) -> list[FileRecord]:
    root = root.resolve()
    if not root.is_dir():
        fail(f"not a directory: {root}")
    exact: set[str] = set()
    casefolded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    records: list[FileRecord] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        canonical = normalize_relative_path(relative)
        _check_collision_sets(canonical, exact, casefolded, normalized)
        if path.is_symlink():
            fail(f"symlink is forbidden: {canonical}")
        mode = path.lstat().st_mode
        if path.is_dir():
            continue
        if not stat.S_ISREG(mode):
            fail(f"non-regular file is forbidden: {canonical}")
        records.append(
            FileRecord(
                path=canonical,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return records


def _zip_entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return bool(unix_mode and stat.S_ISLNK(unix_mode))


def _zip_entry_is_special(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if not unix_mode:
        return False
    return not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode))


def scan_zip(path: Path) -> list[ZipRecord]:
    if not path.is_file():
        fail(f"ZIP does not exist: {path}")
    exact: set[str] = set()
    casefolded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    total_uncompressed = 0
    records: list[ZipRecord] = []
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                fail(f"ZIP entry count exceeds limit: {len(infos)}")
            for info in infos:
                raw_name = info.filename.rstrip("/") if info.is_dir() else info.filename
                canonical = normalize_relative_path(raw_name)
                _check_collision_sets(canonical, exact, casefolded, normalized)
                if info.flag_bits & 0x1:
                    fail(f"encrypted ZIP member is forbidden: {canonical}")
                if _zip_entry_is_symlink(info):
                    fail(f"ZIP symlink is forbidden: {canonical}")
                if _zip_entry_is_special(info):
                    fail(f"ZIP special file is forbidden: {canonical}")
                if info.is_dir():
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    fail(f"ZIP member exceeds size limit: {canonical}")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
                    fail("ZIP total uncompressed size exceeds limit")
                compressed = max(1, info.compress_size)
                if info.file_size / compressed > MAX_COMPRESSION_RATIO:
                    fail(f"ZIP compression ratio exceeds limit: {canonical}")
                digest = hashlib.sha256()
                with archive.open(info, "r") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                records.append(
                    ZipRecord(
                        path=canonical,
                        size_bytes=info.file_size,
                        compressed_size=info.compress_size,
                        sha256="sha256:" + digest.hexdigest(),
                    )
                )
    except zipfile.BadZipFile as exc:
        fail(f"invalid ZIP: {path}: {exc}")
    return records


def safe_extract_zip(path: Path, destination: Path) -> None:
    records = scan_zip(path)
    allowed = {record.path for record in records}
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            canonical = normalize_relative_path(info.filename)
            if canonical not in allowed:
                fail(f"ZIP extraction path was not admitted: {canonical}")
            output = destination.joinpath(*PurePosixPath(canonical).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, output.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=1024 * 1024)
            os.chmod(output, 0o644)


def _entry_map(entries: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, list):
        fail("manifest entries must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            fail(f"manifest entry {index} is not an object")
        path = normalize_relative_path(raw.get("path"))
        if path in result:
            fail(f"duplicate manifest entry: {path}")
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            fail(f"invalid manifest digest for {path}: {digest!r}")
        size = raw.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            fail(f"invalid manifest size for {path}: {size!r}")
        result[path] = raw
    return result


def public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256_bytes(raw)


def load_ed25519_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        fail("publisher private key is not Ed25519")
    return key


def load_ed25519_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        fail("publisher public key is not Ed25519")
    return key


def _validate_release_manifest_shape(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        fail("release manifest must be an object")
    if manifest.get("schema") != "dai.release-manifest.v1":
        fail(f"unsupported release manifest schema: {manifest.get('schema')!r}")
    release_id = manifest.get("release_id")
    if not isinstance(release_id, str) or not release_id or "/" in release_id or "\\" in release_id:
        fail("release_id must be a non-empty filesystem-safe string")
    epoch = manifest.get("source_date_epoch")
    if not isinstance(epoch, int) or epoch < 315532800:
        fail("source_date_epoch must be an integer at or after 1980-01-01")
    authority = manifest.get("authority")
    if authority != {"execution_authority_allowed": False, "production_authority_allowed": False}:
        fail("release authority boundary must explicitly deny execution and production authority")
    entries = _entry_map(manifest.get("entries"))
    if manifest.get("entry_count") != len(entries):
        fail("manifest entry_count mismatch")
    total = sum(int(entry["size_bytes"]) for entry in entries.values())
    if manifest.get("total_size_bytes") != total:
        fail("manifest total_size_bytes mismatch")
    return manifest


def validate_lineage_ledger(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict):
        fail("lineage ledger must be an object")
    if ledger.get("schema") != "dai.lineage-ledger.v1":
        fail(f"unsupported lineage schema: {ledger.get('schema')!r}")
    nodes = ledger.get("nodes")
    edges = ledger.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        fail("lineage nodes and edges must be lists")
    node_map: dict[str, dict[str, Any]] = {}
    phase_map: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            fail("lineage node is not an object")
        digest = node.get("digest")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            fail(f"invalid lineage node digest: {digest!r}")
        if digest in node_map:
            fail(f"duplicate lineage node digest: {digest}")
        node_map[digest] = node
        phase = node.get("phase")
        if phase is not None:
            if not isinstance(phase, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", phase):
                fail(f"invalid lineage phase: {phase!r}")
            phase_map.setdefault(phase, []).append(digest)
    adjacency: dict[str, set[str]] = {digest: set() for digest in node_map}
    predecessor_kinds = {"predecessor", "declared_predecessor"}
    for edge in edges:
        if not isinstance(edge, dict):
            fail("lineage edge is not an object")
        source = edge.get("source")
        target = edge.get("target")
        kind = edge.get("kind")
        if source not in node_map or target not in node_map:
            fail(f"lineage edge references unknown node: {source!r} -> {target!r}")
        if source == target:
            fail("lineage self-edge is forbidden")
        if not isinstance(kind, str) or not kind:
            fail("lineage edge kind is missing")
        if kind in predecessor_kinds:
            adjacency[source].add(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            fail(f"cycle in predecessor lineage at {node}")
        if node in visited:
            return
        visiting.add(node)
        for parent in adjacency[node]:
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for digest in node_map:
        visit(digest)
    sequence = ledger.get("required_phase_sequence", [])
    if sequence:
        if not isinstance(sequence, list) or any(not isinstance(item, str) for item in sequence):
            fail("required_phase_sequence must be a list of phase strings")
        for phase in sequence:
            matches = phase_map.get(phase, [])
            if len(matches) != 1:
                fail(f"phase {phase} must resolve to exactly one artifact, found {len(matches)}")
        edge_pairs = {(edge["source"], edge["target"]) for edge in edges if edge["kind"] in predecessor_kinds}
        for newer, older in zip(sequence[1:], sequence[:-1]):
            newer_digest = phase_map[newer][0]
            older_digest = phase_map[older][0]
            if (newer_digest, older_digest) not in edge_pairs:
                fail(f"missing predecessor edge: phase {newer} -> phase {older}")
    conflicts = ledger.get("conflicts", [])
    if conflicts:
        fail(f"lineage ledger contains unresolved conflicts: {conflicts}")
    return ledger


def verify_release_directory(
    root: Path,
    *,
    trusted_fingerprint: str | None,
    allow_unpinned: bool = False,
) -> dict[str, Any]:
    refuse_optimized_python()
    root = root.resolve()
    records = inventory_directory(root)
    record_map = {record.path: record for record in records}
    if RELEASE_MANIFEST not in record_map or RELEASE_SIGNATURE not in record_map:
        fail("release manifest or detached signature is missing")
    manifest = _validate_release_manifest_shape(load_json_file(root / RELEASE_MANIFEST))
    declared = _entry_map(manifest["entries"])
    actual_signed_paths = set(record_map) - set(EXACT_UNSIGNED_METADATA)
    if set(declared) != actual_signed_paths:
        missing = sorted(set(declared) - actual_signed_paths)
        unlisted = sorted(actual_signed_paths - set(declared))
        fail(f"exact file-set mismatch; missing={missing}, unlisted={unlisted}")
    for path, entry in declared.items():
        record = record_map[path]
        if record.size_bytes != entry["size_bytes"]:
            fail(f"size mismatch for {path}")
        if record.sha256 != entry["sha256"]:
            fail(f"digest mismatch for {path}")
    signature_packet = load_json_file(root / RELEASE_SIGNATURE)
    if not isinstance(signature_packet, dict):
        fail("signature packet must be an object")
    expected_packet = {
        "schema": "dai.detached-signature.v1",
        "algorithm": "Ed25519",
        "signed_object": RELEASE_MANIFEST,
    }
    for key, value in expected_packet.items():
        if signature_packet.get(key) != value:
            fail(f"signature packet {key} mismatch")
    signed_digest = sha256_bytes(canonical_json_bytes(manifest))
    if signature_packet.get("signed_object_sha256") != signed_digest:
        fail("signature packet signed-object digest mismatch")
    public_key_path = signature_packet.get("public_key_path")
    if public_key_path != PUBLISHER_PUBLIC_KEY:
        fail("signature packet must use the exact top-level publisher key path")
    if PUBLISHER_PUBLIC_KEY not in declared:
        fail("publisher public key is not covered by the signed inventory")
    public_key = load_ed25519_public_key(root / PUBLISHER_PUBLIC_KEY)
    fingerprint = public_key_fingerprint(public_key)
    if signature_packet.get("public_key_fingerprint") != fingerprint:
        fail("signature packet public-key fingerprint mismatch")
    if trusted_fingerprint is None:
        if not allow_unpinned:
            fail("an externally published trusted fingerprint is required")
    elif trusted_fingerprint != fingerprint:
        fail(f"trusted fingerprint mismatch: expected {trusted_fingerprint}, got {fingerprint}")
    signature_b64 = signature_packet.get("signature_base64")
    if not isinstance(signature_b64, str):
        fail("signature_base64 is missing")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:
        fail(f"invalid base64 signature: {exc}")
    try:
        public_key.verify(signature, canonical_json_bytes(manifest))
    except InvalidSignature:
        fail("Ed25519 signature verification failed")
    lineage_path = root / "lineage" / "LINEAGE_LEDGER.json"
    if lineage_path.exists():
        validate_lineage_ledger(load_json_file(lineage_path))
    return {
        "verified": True,
        "release_id": manifest["release_id"],
        "entry_count": manifest["entry_count"],
        "manifest_digest": signed_digest,
        "publisher_fingerprint": fingerprint,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def verify_release_zip(
    path: Path,
    *,
    trusted_fingerprint: str | None,
    allow_unpinned: bool = False,
) -> dict[str, Any]:
    refuse_optimized_python()
    scan_zip(path)
    with tempfile.TemporaryDirectory(prefix="dai-release-verify-") as temporary:
        extracted = Path(temporary) / "release"
        safe_extract_zip(path, extracted)
        report = verify_release_directory(
            extracted,
            trusted_fingerprint=trusted_fingerprint,
            allow_unpinned=allow_unpinned,
        )
    report["outer_zip_sha256"] = sha256_file(path)
    return report


def _copy_candidate(candidate: Path, destination: Path) -> None:
    inventory_directory(candidate)
    shutil.copytree(candidate, destination, symlinks=False)
    for reserved in EXACT_UNSIGNED_METADATA | {PUBLISHER_PUBLIC_KEY}:
        path = destination / reserved
        if path.exists():
            fail(f"candidate may not supply reserved top-level file: {reserved}")


def _source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        fail("SOURCE_DATE_EPOCH must be set for a reproducible publication build")
    try:
        value = int(raw)
    except ValueError:
        fail("SOURCE_DATE_EPOCH must be an integer")
    if value < 315532800:
        fail("SOURCE_DATE_EPOCH must be at or after 1980-01-01")
    return value


def deterministic_zip(source: Path, output: Path, source_date_epoch: int) -> None:
    dt = datetime.fromtimestamp(source_date_epoch, tz=timezone.utc)
    year = min(max(dt.year, 1980), 2107)
    timestamp = (year, dt.month, dt.day, dt.hour, dt.minute, dt.second - dt.second % 2)
    records = inventory_directory(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for record in records:
            data = (source / record.path).read_bytes()
            info = zipfile.ZipInfo(record.path, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits |= 0x800
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_release(
    candidate: Path,
    *,
    release_id: str,
    private_key_path: Path,
    output: Path,
) -> dict[str, Any]:
    refuse_optimized_python()
    epoch = _source_date_epoch()
    output.mkdir(parents=True, exist_ok=True)
    release_dir = output / release_id
    if release_dir.exists():
        fail(f"release output already exists: {release_dir}")
    _copy_candidate(candidate, release_dir)
    private_key = load_ed25519_private_key(private_key_path)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (release_dir / PUBLISHER_PUBLIC_KEY).write_bytes(public_pem)
    os.chmod(release_dir / PUBLISHER_PUBLIC_KEY, 0o644)
    records = [record for record in inventory_directory(release_dir) if record.path not in EXACT_UNSIGNED_METADATA]
    manifest = {
        "schema": "dai.release-manifest.v1",
        "release_id": release_id,
        "source_date_epoch": epoch,
        "created_at_utc": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "authority": {
            "execution_authority_allowed": False,
            "production_authority_allowed": False,
        },
        "entry_count": len(records),
        "total_size_bytes": sum(record.size_bytes for record in records),
        "entries": [record.as_dict() for record in sorted(records, key=lambda item: item.path)],
    }
    write_canonical_json(release_dir / RELEASE_MANIFEST, manifest)
    signature = private_key.sign(canonical_json_bytes(manifest))
    packet = {
        "schema": "dai.detached-signature.v1",
        "algorithm": "Ed25519",
        "signed_object": RELEASE_MANIFEST,
        "signed_object_sha256": sha256_bytes(canonical_json_bytes(manifest)),
        "public_key_path": PUBLISHER_PUBLIC_KEY,
        "public_key_fingerprint": public_key_fingerprint(public_key),
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_canonical_json(release_dir / RELEASE_SIGNATURE, packet)
    verification = verify_release_directory(
        release_dir,
        trusted_fingerprint=packet["public_key_fingerprint"],
    )
    zip_path = output / f"{release_id}.zip"
    deterministic_zip(release_dir, zip_path, epoch)
    zip_verification = verify_release_zip(
        zip_path,
        trusted_fingerprint=packet["public_key_fingerprint"],
    )
    sidecar = output / f"{release_id}.zip.sha256"
    sidecar.write_text(f"{sha256_file(zip_path).removeprefix('sha256:')}  {zip_path.name}\n", encoding="utf-8")
    return {
        "built": True,
        "release_directory": str(release_dir),
        "release_zip": str(zip_path),
        "release_zip_sha256": sha256_file(zip_path),
        "publisher_fingerprint": packet["public_key_fingerprint"],
        "directory_verification": verification,
        "zip_verification": zip_verification,
    }


def _collect_json_values(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            yield child_path, child
            yield from _collect_json_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}/{index}"
            yield child_path, child
            yield from _collect_json_values(child, child_path)


def _phase_from_name(name: str) -> str | None:
    match = PHASE_RE.search(name)
    return match.group("phase") if match else None


def _discover_zip_node(
    data: bytes,
    *,
    display_name: str,
    depth: int,
    nodes: MutableMapping[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    lineage_refs: list[dict[str, Any]],
) -> str:
    if depth > MAX_LINEAGE_DEPTH:
        fail("nested lineage ZIP depth exceeds limit")
    digest = sha256_bytes(data)
    if digest in nodes:
        return digest
    if len(nodes) >= MAX_LINEAGE_NODES:
        fail("lineage node count exceeds limit")
    with tempfile.NamedTemporaryFile(prefix="dai-lineage-", suffix=".zip", delete=False) as handle:
        handle.write(data)
        temporary_path = Path(handle.name)
    try:
        records = scan_zip(temporary_path)
        inventory_digest = sha256_bytes(canonical_json_bytes([record.as_dict() for record in records]))
        release_ids: set[str] = set()
        json_refs: list[dict[str, Any]] = []
        nested_members: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(temporary_path, "r") as archive:
            for record in records:
                if record.path.lower().endswith(".zip") and record.size_bytes <= MAX_MEMBER_BYTES:
                    nested_members.append((record.path, archive.read(record.path)))
                if not record.path.lower().endswith((".json", ".md", ".txt")):
                    continue
                if record.size_bytes > MAX_JSON_BYTES:
                    continue
                raw = archive.read(record.path)
                if record.path.lower().endswith(".json"):
                    try:
                        parsed = load_json_bytes(raw, source=f"{display_name}:{record.path}")
                    except PublicationError:
                        continue
                    for json_path, value in _collect_json_values(parsed):
                        key = json_path.rsplit("/", 1)[-1]
                        if key in {"release_id", "artifact_id", "capsule_id"} and isinstance(value, str):
                            release_ids.add(value)
                        if isinstance(value, str):
                            for match in SHA256_RE.finditer(value):
                                json_refs.append(
                                    {
                                        "source_member": record.path,
                                        "json_path": json_path,
                                        "digest": "sha256:" + match.group(1),
                                        "lineage_like": bool(LINEAGE_KEY_RE.search(key)),
                                    }
                                )
                else:
                    text = raw.decode("utf-8", errors="ignore")
                    for match in SHA256_RE.finditer(text):
                        json_refs.append(
                            {
                                "source_member": record.path,
                                "json_path": None,
                                "digest": "sha256:" + match.group(1),
                                "lineage_like": bool(re.search(r"predecessor|prior|parent|fossil", text[max(0, match.start()-80):match.end()+80], re.IGNORECASE)),
                            }
                        )
        node = {
            "digest": digest,
            "display_name": display_name,
            "size_bytes": len(data),
            "phase": _phase_from_name(display_name),
            "release_ids": sorted(release_ids),
            "zip_inventory_digest": inventory_digest,
            "zip_entry_count": len(records),
        }
        nodes[digest] = node
        lineage_refs.extend({"source": digest, **reference} for reference in json_refs)
        for member_name, nested_data in nested_members:
            child_digest = _discover_zip_node(
                nested_data,
                display_name=f"{display_name}!/{member_name}",
                depth=depth + 1,
                nodes=nodes,
                edges=edges,
                lineage_refs=lineage_refs,
            )
            edges.append(
                {
                    "source": digest,
                    "target": child_digest,
                    "kind": "contains",
                    "evidence": member_name,
                }
            )
        return digest
    finally:
        temporary_path.unlink(missing_ok=True)


def discover_lineage(artifacts: Path) -> dict[str, Any]:
    refuse_optimized_python()
    artifacts = artifacts.resolve()
    if not artifacts.is_dir():
        fail(f"artifact directory does not exist: {artifacts}")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    for path in sorted(artifacts.rglob("*.zip"), key=lambda item: item.as_posix()):
        if path.is_symlink() or not path.is_file():
            fail(f"invalid artifact path: {path}")
        _discover_zip_node(
            path.read_bytes(),
            display_name=path.relative_to(artifacts).as_posix(),
            depth=0,
            nodes=nodes,
            edges=edges,
            lineage_refs=references,
        )
    node_digests = set(nodes)
    for reference in references:
        target = reference["digest"]
        if target in node_digests and target != reference["source"]:
            edges.append(
                {
                    "source": reference["source"],
                    "target": target,
                    "kind": "references",
                    "evidence": {
                        "member": reference["source_member"],
                        "json_path": reference["json_path"],
                    },
                }
            )
    conflicts: list[dict[str, Any]] = []
    phase_map: dict[str, list[str]] = {}
    for digest, node in nodes.items():
        if node["phase"]:
            phase_map.setdefault(node["phase"], []).append(digest)
    for phase, digests in sorted(phase_map.items()):
        top_level = [digest for digest in digests if "!/" not in nodes[digest]["display_name"]]
        if len(top_level) > 1:
            conflicts.append({"type": "multiple_top_level_artifacts_for_phase", "phase": phase, "digests": sorted(top_level)})
    dangling = [
        reference
        for reference in references
        if reference["lineage_like"] and reference["digest"] not in node_digests
    ]
    unique_edges = {
        canonical_json_bytes(edge): edge
        for edge in edges
        if edge["source"] != edge["target"]
    }
    return {
        "schema": "dai.lineage-ledger.v1",
        "required_phase_sequence": [],
        "nodes": sorted(nodes.values(), key=lambda node: (node.get("phase") or "", node["display_name"], node["digest"])),
        "edges": sorted(unique_edges.values(), key=lambda edge: (edge["source"], edge["target"], edge["kind"])),
        "dangling_lineage_references": sorted(dangling, key=lambda item: (item["source"], item["digest"], item["source_member"])),
        "conflicts": conflicts,
        "review_required": True,
        "review_instructions": [
            "Set required_phase_sequence to the exact published lineage, for example 1, 2, 2.1, 3, 3.1, 4, 5, 6.2.",
            "Add declared_predecessor edges only after opening and verifying both artifacts.",
            "Resolve every conflict and every lineage-like dangling digest before final publication.",
            "Do not infer historical priority from containment alone.",
        ],
    }


def _require_report(path: Path, *, result_keys: Sequence[str] = ("verified", "passed", "result")) -> dict[str, Any]:
    if not path.is_file():
        fail(f"required report is missing: {path}")
    value = load_json_file(path)
    if not isinstance(value, dict):
        fail(f"report must be an object: {path}")
    positive = False
    for key in result_keys:
        if key not in value:
            continue
        raw = value[key]
        positive = raw is True or (isinstance(raw, str) and raw.lower() in {"pass", "passed", "green", "verified"})
        if positive:
            break
    if not positive:
        fail(f"report is not green: {path}")
    return value


def validate_candidate(candidate: Path, *, stage: str) -> dict[str, Any]:
    refuse_optimized_python()
    records = inventory_directory(candidate)
    paths = {record.path for record in records}
    required_rc = {
        "lineage/LINEAGE_LEDGER.json",
        "docs/CLAIMS_REGISTRY.json",
        "docs/BDI_VALIDITY_CRITERIA.json",
        "arena/ABLATION_PLAN.json",
    }
    missing_rc = sorted(required_rc - paths)
    if missing_rc:
        fail(f"candidate is missing required RC files: {missing_rc}")
    ledger = validate_lineage_ledger(load_json_file(candidate / "lineage" / "LINEAGE_LEDGER.json"))
    if ledger.get("review_required") is not False:
        fail("lineage ledger must record review_required=false after manual review")
    if ledger.get("dangling_lineage_references"):
        fail("lineage ledger has dangling lineage references")
    if stage == "final":
        reports = {
            "mutation": candidate / "reports" / "MUTATION_REPORT.json",
            "ablation": candidate / "reports" / "ABLATION_REPORT.json",
            "offline": candidate / "reports" / "NETWORK_DENIAL_WITNESS.json",
        }
        for path in reports.values():
            _require_report(path)
        reproduction_dir = candidate / "reports" / "reproductions"
        reproduction_reports = sorted(reproduction_dir.glob("*.json")) if reproduction_dir.is_dir() else []
        if len(reproduction_reports) < 2:
            fail("final candidate requires at least two independent reproduction reports")
        operators: set[str] = set()
        keys: set[str] = set()
        for path in reproduction_reports:
            report = _require_report(path)
            operator = report.get("operator_id")
            key = report.get("operator_key_fingerprint")
            if not isinstance(operator, str) or not operator:
                fail(f"reproduction report lacks operator_id: {path}")
            if not isinstance(key, str) or not SHA256_RE.fullmatch(key):
                fail(f"reproduction report lacks valid operator key fingerprint: {path}")
            operators.add(operator)
            keys.add(key)
        if len(operators) < 2 or len(keys) < 2:
            fail("independent reproductions must use distinct operators and keys")
        quorum_dir = candidate / "evidence" / "quorum"
        packets = sorted(quorum_dir.glob("*.json")) if quorum_dir.is_dir() else []
        if len(packets) < 3:
            fail("final candidate requires at least three quorum witness packets")
        providers: set[str] = set()
        quorum_keys: set[str] = set()
        operators_q: set[str] = set()
        proposal_digests: set[str] = set()
        for path in packets:
            packet = load_json_file(path)
            if not isinstance(packet, dict):
                fail(f"quorum packet must be an object: {path}")
            for field in ("proposal_digest", "evidence_root", "world_state_hash", "challenge_nonce", "governance_epoch"):
                if field not in packet:
                    fail(f"quorum packet lacks {field}: {path}")
            proposal_digests.add(str(packet["proposal_digest"]))
            providers.add(str(packet.get("infrastructure_provider")))
            quorum_keys.add(str(packet.get("signing_key_fingerprint")))
            operators_q.add(str(packet.get("operator_id")))
        if len(proposal_digests) != 1:
            fail("quorum packets do not bind to one exact proposal digest")
        if min(len(providers), len(quorum_keys), len(operators_q)) < 3:
            fail("final quorum requires three distinct providers, keys, and operators")
    return {
        "verified": True,
        "stage": stage,
        "file_count": len(records),
        "lineage_node_count": len(ledger["nodes"]),
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def _json_pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        fail(f"invalid JSON pointer: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def json_pointer_get(document: Any, pointer: str) -> Any:
    current = document
    for part in _json_pointer_parts(pointer):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                fail(f"JSON pointer does not resolve: {pointer}")
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            fail(f"JSON pointer does not resolve: {pointer}")
    return current


def json_pointer_remove(document: Any, pointer: str) -> None:
    parts = _json_pointer_parts(pointer)
    if not parts:
        fail("cannot remove the document root")
    parent_pointer = "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts[:-1]) if len(parts) > 1 else ""
    parent = json_pointer_get(document, parent_pointer)
    key = parts[-1]
    if isinstance(parent, list):
        try:
            del parent[int(key)]
        except (ValueError, IndexError):
            fail(f"JSON pointer does not resolve: {pointer}")
    elif isinstance(parent, dict) and key in parent:
        del parent[key]
    else:
        fail(f"JSON pointer does not resolve: {pointer}")


def json_pointer_set(document: Any, pointer: str, value: Any) -> None:
    parts = _json_pointer_parts(pointer)
    if not parts:
        fail("cannot replace the document root")
    parent_pointer = "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts[:-1]) if len(parts) > 1 else ""
    parent = json_pointer_get(document, parent_pointer)
    key = parts[-1]
    if isinstance(parent, list):
        try:
            parent[int(key)] = value
        except (ValueError, IndexError):
            fail(f"JSON pointer does not resolve: {pointer}")
    elif isinstance(parent, dict):
        parent[key] = value
    else:
        fail(f"JSON pointer parent is not mutable: {pointer}")


def _apply_ablation_operations(document: Any, operations: Any) -> Any:
    result = copy.deepcopy(document)
    if not isinstance(operations, list):
        fail("ablation operations must be a list")
    for operation in operations:
        if not isinstance(operation, dict):
            fail("ablation operation must be an object")
        op = operation.get("op")
        pointer = operation.get("pointer")
        if op == "remove_json_pointer":
            json_pointer_remove(result, pointer)
        elif op == "set_json_pointer":
            json_pointer_set(result, pointer, operation.get("value"))
        elif op == "remove_list_item_by_id":
            target = json_pointer_get(result, pointer)
            if not isinstance(target, list):
                fail("remove_list_item_by_id target must be a list")
            identifier_field = operation.get("id_field", "id")
            identifier = operation.get("id")
            filtered = [item for item in target if not (isinstance(item, dict) and item.get(identifier_field) == identifier)]
            if len(filtered) == len(target):
                fail(f"ablation item not found: {identifier}")
            target[:] = filtered
        else:
            fail(f"unsupported ablation operation: {op!r}")
    return result


def _compare_expected(output: Any, expected: Any) -> list[str]:
    if not isinstance(expected, dict):
        fail("ablation expected contract must be an object mapping JSON pointers to values")
    failures: list[str] = []
    for pointer, value in expected.items():
        try:
            actual = json_pointer_get(output, pointer)
        except PublicationError as exc:
            failures.append(str(exc))
            continue
        if actual != value:
            failures.append(f"{pointer}: expected {value!r}, got {actual!r}")
    return failures


def run_ablation(plan_path: Path, *, adapter: str, output_path: Path, timeout: int) -> dict[str, Any]:
    refuse_optimized_python()
    plan = load_json_file(plan_path)
    if not isinstance(plan, dict) or plan.get("schema") != "dai.ablation-plan.v1":
        fail("unsupported ablation plan schema")
    baseline_path = (plan_path.parent / plan.get("baseline_input", "")).resolve()
    baseline = load_json_file(baseline_path)
    variants = plan.get("variants")
    if not isinstance(variants, list) or not variants:
        fail("ablation plan must contain variants")
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="dai-ablation-") as temporary:
        temp = Path(temporary)
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                fail("ablation variant must be an object")
            variant_id = variant.get("id")
            if not isinstance(variant_id, str) or not variant_id:
                fail("ablation variant id is missing")
            mutated = _apply_ablation_operations(baseline, variant.get("operations", []))
            input_file = temp / f"{index:04d}-{variant_id}-input.json"
            output_file = temp / f"{index:04d}-{variant_id}-output.json"
            write_canonical_json(input_file, mutated)
            command = adapter.replace("{input}", str(input_file)).replace("{output}", str(output_file))
            args = shlex.split(command)
            if not args:
                fail("adapter command is empty")
            environment = os.environ.copy()
            environment["DAI_ABLATION_INPUT"] = str(input_file)
            environment["DAI_ABLATION_OUTPUT"] = str(output_file)
            started = time.monotonic()
            completed = subprocess.run(
                args,
                cwd=str(plan_path.parent),
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if completed.returncode != 0:
                results.append(
                    {
                        "id": variant_id,
                        "passed": False,
                        "reason": "adapter_nonzero_exit",
                        "returncode": completed.returncode,
                        "stderr_tail": completed.stderr[-4000:],
                        "elapsed_ms": elapsed_ms,
                    }
                )
                continue
            if not output_file.is_file():
                results.append(
                    {
                        "id": variant_id,
                        "passed": False,
                        "reason": "adapter_output_missing",
                        "elapsed_ms": elapsed_ms,
                    }
                )
                continue
            adapter_output = load_json_file(output_file)
            failures = _compare_expected(adapter_output, variant.get("expected", {}))
            results.append(
                {
                    "id": variant_id,
                    "passed": not failures,
                    "failures": failures,
                    "input_digest": sha256_file(input_file),
                    "output_digest": sha256_file(output_file),
                    "elapsed_ms": elapsed_ms,
                }
            )
    report = {
        "schema": "dai.ablation-report.v1",
        "passed": all(item["passed"] for item in results),
        "variant_count": len(results),
        "passed_count": sum(1 for item in results if item["passed"]),
        "results": results,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    write_canonical_json(output_path, report)
    if not report["passed"]:
        fail(f"ablation suite failed; see {output_path}")
    return report


def _mutate_directory_copy(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def run_mutation_suite(release_zip: Path, *, output: Path) -> dict[str, Any]:
    refuse_optimized_python()
    output.mkdir(parents=True, exist_ok=True)
    baseline = verify_release_zip(release_zip, trusted_fingerprint=None, allow_unpinned=True)
    mutations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="dai-mutation-") as temporary:
        temp = Path(temporary)
        pristine = temp / "pristine"
        safe_extract_zip(release_zip, pristine)
        manifest = load_json_file(pristine / RELEASE_MANIFEST)
        entries = _entry_map(manifest["entries"])
        mutable_paths = [path for path in sorted(entries) if path != PUBLISHER_PUBLIC_KEY]
        if not mutable_paths:
            fail("release has no mutable tracked file for mutation tests")

        def expect_rejection(name: str, mutate: Any) -> None:
            case = temp / name
            _mutate_directory_copy(pristine, case)
            mutate(case)
            try:
                verify_release_directory(case, trusted_fingerprint=None, allow_unpinned=True)
            except PublicationError as exc:
                mutations.append({"id": name, "passed": True, "rejection": str(exc)})
            else:
                mutations.append({"id": name, "passed": False, "rejection": None})

        tracked = mutable_paths[0]
        expect_rejection(
            "tracked-byte-flip",
            lambda root: (root / tracked).write_bytes((root / tracked).read_bytes() + b"\nMUTATION\n"),
        )
        expect_rejection(
            "unlisted-file",
            lambda root: (root / "UNLISTED.txt").write_text("must reject\n", encoding="utf-8"),
        )
        expect_rejection(
            "nested-reserved-basename",
            lambda root: ((root / "nested").mkdir(), (root / "nested" / RELEASE_MANIFEST).write_text("{}\n", encoding="utf-8")),
        )
        expect_rejection("missing-tracked-file", lambda root: (root / tracked).unlink())

        def mutate_entry_count(root: Path) -> None:
            value = load_json_file(root / RELEASE_MANIFEST)
            value["entry_count"] += 1
            write_canonical_json(root / RELEASE_MANIFEST, value)

        expect_rejection("manifest-entry-count", mutate_entry_count)

        def mutate_signature(root: Path) -> None:
            value = load_json_file(root / RELEASE_SIGNATURE)
            signature = bytearray(base64.b64decode(value["signature_base64"]))
            signature[0] ^= 0x01
            value["signature_base64"] = base64.b64encode(bytes(signature)).decode("ascii")
            write_canonical_json(root / RELEASE_SIGNATURE, value)

        expect_rejection("signature-bit-flip", mutate_signature)

        def add_case_collision(root: Path) -> None:
            (root / "CaseCollision.txt").write_text("A\n", encoding="utf-8")
            (root / "casecollision.txt").write_text("B\n", encoding="utf-8")

        expect_rejection("casefold-collision", add_case_collision)

        if hasattr(os, "symlink"):
            def add_symlink(root: Path) -> None:
                os.symlink(tracked, root / "forbidden-link")
            expect_rejection("symlink", add_symlink)

        malicious_zip = temp / "path-traversal.zip"
        with zipfile.ZipFile(malicious_zip, "w") as archive:
            archive.writestr("../escape.txt", b"forbidden")
        try:
            verify_release_zip(malicious_zip, trusted_fingerprint=None, allow_unpinned=True)
        except PublicationError as exc:
            mutations.append({"id": "zip-path-traversal", "passed": True, "rejection": str(exc)})
        else:
            mutations.append({"id": "zip-path-traversal", "passed": False, "rejection": None})

        optimized = subprocess.run(
            [sys.executable, "-O", str(Path(__file__).resolve()), "verify", str(release_zip), "--allow-unpinned"],
            capture_output=True,
            text=True,
            check=False,
        )
        mutations.append(
            {
                "id": "optimized-python-refusal",
                "passed": optimized.returncode != 0 and "optimized Python is forbidden" in (optimized.stderr + optimized.stdout),
                "returncode": optimized.returncode,
                "output_tail": (optimized.stderr + optimized.stdout)[-2000:],
            }
        )
    report = {
        "schema": "dai.mutation-report.v1",
        "passed": all(item["passed"] for item in mutations),
        "baseline": baseline,
        "mutation_count": len(mutations),
        "passed_count": sum(1 for item in mutations if item["passed"]),
        "mutations": mutations,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    write_canonical_json(output / "MUTATION_REPORT.json", report)
    if not report["passed"]:
        fail(f"mutation suite failed; see {output / 'MUTATION_REPORT.json'}")
    return report


def generate_key(private_path: Path, public_path: Path) -> dict[str, Any]:
    if private_path.exists() or public_path.exists():
        fail("refusing to overwrite an existing key")
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(private_path, 0o600)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_bytes(
        public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    os.chmod(public_path, 0o644)
    return {"generated": True, "public_key_fingerprint": public_key_fingerprint(public)}


def selftest() -> dict[str, Any]:
    refuse_optimized_python()
    with tempfile.TemporaryDirectory(prefix="dai-selftest-") as temporary:
        root = Path(temporary)
        candidate = root / "candidate"
        (candidate / "docs").mkdir(parents=True)
        (candidate / "docs" / "example.txt").write_text("deterministic evidence\n", encoding="utf-8")
        private_path = root / "publisher.pem"
        public_path = root / "publisher.pub.pem"
        key_report = generate_key(private_path, public_path)
        os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
        build_report = build_release(
            candidate,
            release_id="DAI-Selftest",
            private_key_path=private_path,
            output=root / "dist",
        )
        mutation_report = run_mutation_suite(Path(build_report["release_zip"]), output=root / "mutations")
        return {
            "passed": True,
            "key": key_report,
            "build": build_report,
            "mutation": mutation_report,
        }


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify", help="verify a final release directory or ZIP")
    verify_parser.add_argument("release", type=Path)
    verify_parser.add_argument("--trusted-fingerprint")
    verify_parser.add_argument("--allow-unpinned", action="store_true")

    build_parser_ = subparsers.add_parser("build", help="build and sign a deterministic release")
    build_parser_.add_argument("candidate", type=Path)
    build_parser_.add_argument("--release-id", required=True)
    build_parser_.add_argument("--private-key", type=Path, required=True)
    build_parser_.add_argument("--output", type=Path, required=True)

    lineage_parser = subparsers.add_parser("discover-lineage", help="discover nested ZIP lineage evidence")
    lineage_parser.add_argument("artifacts", type=Path)
    lineage_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate-candidate", help="validate an RC or final candidate")
    validate_parser.add_argument("candidate", type=Path)
    validate_parser.add_argument("--stage", choices=("rc", "final"), default="rc")

    mutation_parser = subparsers.add_parser("mutate", help="run the defensive mutation suite")
    mutation_parser.add_argument("release", type=Path)
    mutation_parser.add_argument("--output", type=Path, required=True)

    ablation_parser = subparsers.add_parser("ablate", help="run a system-specific ablation matrix")
    ablation_parser.add_argument("plan", type=Path)
    ablation_parser.add_argument("--adapter", required=True)
    ablation_parser.add_argument("--output", type=Path, required=True)
    ablation_parser.add_argument("--timeout", type=int, default=120)

    key_parser = subparsers.add_parser("generate-key", help="generate an offline Ed25519 release key")
    key_parser.add_argument("--private-key", type=Path, required=True)
    key_parser.add_argument("--public-key", type=Path, required=True)

    subparsers.add_parser("selftest", help="build, verify, and mutate a synthetic release")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            if args.release.is_dir():
                result = verify_release_directory(
                    args.release,
                    trusted_fingerprint=args.trusted_fingerprint,
                    allow_unpinned=args.allow_unpinned,
                )
            else:
                result = verify_release_zip(
                    args.release,
                    trusted_fingerprint=args.trusted_fingerprint,
                    allow_unpinned=args.allow_unpinned,
                )
        elif args.command == "build":
            result = build_release(
                args.candidate,
                release_id=args.release_id,
                private_key_path=args.private_key,
                output=args.output,
            )
        elif args.command == "discover-lineage":
            result = discover_lineage(args.artifacts)
            write_canonical_json(args.output, result)
        elif args.command == "validate-candidate":
            result = validate_candidate(args.candidate, stage=args.stage)
        elif args.command == "mutate":
            result = run_mutation_suite(args.release, output=args.output)
        elif args.command == "ablate":
            result = run_ablation(
                args.plan,
                adapter=args.adapter,
                output_path=args.output,
                timeout=args.timeout,
            )
        elif args.command == "generate-key":
            result = generate_key(args.private_key, args.public_key)
        elif args.command == "selftest":
            result = selftest()
        else:
            parser.error(f"unknown command: {args.command}")
            return 2
        _print_json(result)
        return 0
    except (PublicationError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"DAI publication failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
