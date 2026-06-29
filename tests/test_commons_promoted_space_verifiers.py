"""Portable evidence-contract verifier for promoted benchmark Commons Spaces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = sorted((ROOT / "data" / "commons_spaces").glob("bench_*/live_verifier_contract.json"))


@pytest.mark.parametrize("contract_path", CONTRACTS, ids=lambda path: path.parent.name)
def test_promoted_space_contract(contract_path: Path) -> None:
    """Validate the Space's own archive evidence rather than a global smoke test."""
    space_root = contract_path.parent
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    manifest = json.loads((space_root / "beast_space.json").read_text(encoding="utf-8"))

    assert contract["beast_object_type"] == "commons_live_verifier_contract"
    assert contract["space_id"] == space_root.name == manifest["space_id"]
    assert contract["workload_boundary"] == "local_benchmark_evidence_reuse"
    assert contract["raw_private_data_required"] is False

    declared = {item["path"]: item for item in manifest["artifacts"]}
    for relative in contract["required_artifacts"]:
        path = space_root / relative
        assert path.is_file(), relative
        assert relative in declared
        body = path.read_bytes()
        assert declared[relative]["bytes"] == len(body)
        assert declared[relative]["sha256"] == "sha256:" + hashlib.sha256(body).hexdigest()
        if path.suffix == ".json":
            assert isinstance(json.loads(body), dict)

    integrity = json.loads((space_root / "integrity_manifest.json").read_text(encoding="utf-8"))
    assert integrity["algorithm"] == "sha256"
    archived = {item["path"]: item for item in integrity["files"]}
    for relative in contract["integrity_targets"]:
        body = (space_root / relative).read_bytes()
        assert archived[relative]["bytes"] == len(body)
        assert archived[relative]["sha256"] == hashlib.sha256(body).hexdigest()

    run_manifest = json.loads((space_root / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["beast_object_type"] == "definitive_mega_test_report"
    assert isinstance(run_manifest.get("acceptance_status"), dict)

