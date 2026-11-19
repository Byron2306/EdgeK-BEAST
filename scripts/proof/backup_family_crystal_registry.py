"""Create and audit a durable, private copy of an existing family-crystal registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from app.kernel.compute.family_crystals import FamilyRegistry


def _read(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(db.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=10)


def _sha(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _sync(path: Path):
    with path.open("rb") as file:
        os.fsync(file.fileno())


def _sync_dir(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def backup_registry(source: Path, target: Path, expected: dict[str, str | None]):
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    # These are private snapshots. Do not send the database or register new promotions.
    with closing(_read(source)) as src:
        if src.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("source registry failed SQLite integrity check")
        ids = {row[0] for row in src.execute("SELECT crystal_id FROM family_crystals")}
        if missing := sorted(set(expected) - ids):
            raise LookupError("expected crystal IDs not present: " + ", ".join(missing))
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".family-custody-", dir=target.parent) as temp:
            bundle = Path(temp) / "bundle"
            bundle.mkdir(mode=0o700)
            db = bundle / "family_crystals.sqlite3"
            with closing(sqlite3.connect(db)) as dest:
                src.backup(dest)
            db.chmod(0o600)
            registry = FamilyRegistry(db)
            with closing(_read(db)) as restored:
                if restored.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("backup failed SQLite integrity check")
                rows = restored.execute("SELECT crystal_id, status FROM family_crystals ORDER BY crystal_id").fetchall()
                negative_count = restored.execute("SELECT COUNT(*) FROM family_negatives").fetchone()[0]
            records = {}
            for crystal_id, status in rows:
                row = registry.get(crystal_id)
                crystal = row["crystal_object"]
                if row["crystal_id"] != crystal_id or row["status"] != status or crystal.crystal_id != crystal_id:
                    raise ValueError(f"inconsistent registry index for {crystal_id}")
                records[crystal_id] = {
                    "id": crystal_id, "family": crystal.task_family, "status": status, "digest": crystal.digest,
                    "record_digest": row["record_digest"], "children": list(crystal.component_ids),
                }
            for crystal_id, digest in expected.items():
                row = records[crystal_id]
                if row["status"] != "promoted" or (digest is not None and row["digest"] != digest):
                    raise ValueError(f"expected promotion or digest not verified: {crystal_id}")
            for row in records.values():
                if row["status"] == "promoted":
                    if any(records.get(child, {}).get("status") != "promoted" for child in row["children"]):
                        raise ValueError(f"missing promoted child: {row['id']}")
            inventory = {"schema": "beast.family-crystal.custody.v1", "registry_sha256": _sha(db),
                         "crystals": list(records.values()), "negative_receipts": negative_count,
                         "expected_ids": sorted(expected), "sqlite_integrity": "ok",
                         "claim_boundary": "Verified snapshot and registry validation, not replay or replication."}
            report = bundle / "inventory.json"
            report.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
            manifest = bundle / "SHA256SUMS"
            manifest.write_text("".join(f"{_sha(p)}  {p.name}\n" for p in (db, report)))
            for file in (db, report, manifest):
                _sync(file)
            _sync_dir(bundle)
            os.rename(bundle, target)
            _sync_dir(target.parent)
    return inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expect", action="append", default=[], metavar="CRYSTAL_ID[=DIGEST]")
    args = parser.parse_args(argv)
    expect = {}
    for item in args.expect:
        crystal_id, _, digest = item.partition("=")
        expect[crystal_id] = digest or None
    inventory = backup_registry(args.db, args.out, expect)
    print(f"CRYSTALS={len(inventory['crystals'])}\nCUSTODY={args.out}")


if __name__ == "__main__":
    main()
