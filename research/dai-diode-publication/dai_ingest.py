#!/usr/bin/env python3
"""Safely ingest immutable DAI-Diode ZIP fossils into a publication candidate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any, Sequence

import dai_publication_core as core


class IngestError(core.PublicationError):
    """A fail-closed DAI artifact ingestion error."""


def fail(message: str) -> None:
    raise IngestError(message)


def _epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        fail("SOURCE_DATE_EPOCH is required for a reproducible ingest receipt")
    try:
        value = int(raw)
    except ValueError:
        fail("SOURCE_DATE_EPOCH must be an integer")
    if value < 315532800:
        fail("SOURCE_DATE_EPOCH must be at or after 1980-01-01")
    return value


def _archive_candidates(source: Path, pattern: str) -> list[Path]:
    if source.is_file():
        candidates = [source]
    elif source.is_dir():
        candidates = sorted(source.rglob(pattern), key=lambda path: path.as_posix())
    else:
        fail(f"source does not exist: {source}")
    admitted: list[Path] = []
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            fail(f"artifact source must be a regular non-symlink file: {path}")
        if path.suffix.lower() != ".zip":
            continue
        admitted.append(path)
    return admitted


def ingest(
    sources: Sequence[Path],
    *,
    candidate: Path,
    pattern: str = "DAI-Diode*.zip",
) -> dict[str, Any]:
    core.refuse_optimized_python()
    epoch = _epoch()
    candidate = candidate.resolve()
    artifacts = candidate / "artifacts"
    lineage = candidate / "lineage"
    artifacts.mkdir(parents=True, exist_ok=True)
    lineage.mkdir(parents=True, exist_ok=True)
    existing = core.inventory_directory(artifacts)
    existing_by_name = {record.path: record for record in existing}
    imported: list[dict[str, Any]] = []
    seen_source_digests: set[str] = set()
    for source in sources:
        for path in _archive_candidates(source.resolve(), pattern):
            core.scan_zip(path)
            name = unicodedata.normalize("NFC", path.name)
            if name != path.name:
                fail(f"artifact filename is not NFC-normalized: {path.name!r}")
            canonical_name = core.normalize_relative_path(name)
            digest = core.sha256_file(path)
            if digest in seen_source_digests:
                continue
            seen_source_digests.add(digest)
            destination = artifacts / canonical_name
            existing_record = existing_by_name.get(canonical_name)
            if existing_record is not None:
                if existing_record.sha256 != digest:
                    fail(f"artifact filename collision with different bytes: {canonical_name}")
                status = "already_present_same_digest"
            else:
                if destination.exists():
                    fail(f"destination exists but was not inventoried as a regular file: {destination}")
                shutil.copyfile(path, destination)
                os.chmod(destination, 0o444)
                if core.sha256_file(destination) != digest:
                    fail(f"copy verification failed for {path}")
                existing_by_name[canonical_name] = core.FileRecord(
                    path=canonical_name,
                    size_bytes=destination.stat().st_size,
                    sha256=digest,
                )
                status = "imported"
            imported.append(
                {
                    "source_display_name": path.name,
                    "artifact_path": f"artifacts/{canonical_name}",
                    "size_bytes": path.stat().st_size,
                    "sha256": digest,
                    "status": status,
                }
            )
    if not imported:
        fail("no DAI-Diode ZIP artifacts were admitted")
    imported.sort(key=lambda item: (item["artifact_path"], item["sha256"]))
    receipt = {
        "schema": "dai.artifact-ingest-receipt.v1",
        "source_date_epoch": epoch,
        "artifact_count": len(imported),
        "artifacts": imported,
        "receipt_digest_basis": "canonical JSON excluding this explanatory field only; release manifest supplies final binding",
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt_path = artifacts / "INGEST_RECEIPT.json"
    core.write_canonical_json(receipt_path, receipt)
    discovered = core.discover_lineage(artifacts)
    discovered_path = lineage / "LINEAGE_LEDGER.discovered.json"
    core.write_canonical_json(discovered_path, discovered)
    return {
        "ingested": True,
        "artifact_count": len(imported),
        "ingest_receipt": str(receipt_path),
        "ingest_receipt_sha256": core.sha256_file(receipt_path),
        "discovered_lineage": str(discovered_path),
        "discovered_lineage_sha256": core.sha256_file(discovered_path),
        "lineage_node_count": len(discovered["nodes"]),
        "lineage_conflict_count": len(discovered["conflicts"]),
        "dangling_lineage_reference_count": len(discovered["dangling_lineage_references"]),
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--pattern", default="DAI-Diode*.zip")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = ingest(args.sources, candidate=args.candidate, pattern=args.pattern)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (core.PublicationError, OSError) as exc:
        print(f"DAI ingest failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
