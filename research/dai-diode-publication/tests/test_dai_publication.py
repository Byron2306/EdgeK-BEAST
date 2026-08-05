from __future__ import annotations

import json
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

import dai_publication as dp


def test_canonical_json_is_order_independent() -> None:
    left = {"b": [2, 1], "a": {"z": False, "x": 1}}
    right = {"a": {"x": 1, "z": False}, "b": [2, 1]}
    assert dp.canonical_json_bytes(left) == dp.canonical_json_bytes(right)
    assert dp.sha256_bytes(dp.canonical_json_bytes(left)) == dp.sha256_bytes(dp.canonical_json_bytes(right))


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(dp.PublicationError, match="duplicate JSON key"):
        dp.load_json_bytes(b'{"x":1,"x":2}', source="test")


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/absolute",
        "a/../b",
        "a\\b",
        "C:/drive",
        "a//b",
        "a/./b",
        "bad\x00path",
        "e\u0301.txt",
    ],
)
def test_noncanonical_paths_are_rejected(path: str) -> None:
    with pytest.raises(dp.PublicationError):
        dp.normalize_relative_path(path)


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", b"no")
    with pytest.raises(dp.PublicationError, match="path"):
        dp.scan_zip(archive)


def test_zip_symlink_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, b"target")
    with pytest.raises(dp.PublicationError, match="symlink"):
        dp.scan_zip(archive)


def _make_key(tmp_path: Path) -> tuple[Path, str]:
    private = tmp_path / "publisher.pem"
    public = tmp_path / "publisher.pub.pem"
    report = dp.generate_key(private, public)
    return private, report["public_key_fingerprint"]


def _build_release(tmp_path: Path) -> tuple[Path, str]:
    candidate = tmp_path / "candidate"
    (candidate / "docs").mkdir(parents=True)
    (candidate / "docs" / "claim.txt").write_text("bounded deterministic intelligence\n", encoding="utf-8")
    private, fingerprint = _make_key(tmp_path)
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
    try:
        report = dp.build_release(
            candidate,
            release_id="DAI-Test-Release",
            private_key_path=private,
            output=tmp_path / "dist",
        )
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    return Path(report["release_zip"]), fingerprint


def test_build_and_verify_release(tmp_path: Path) -> None:
    release, fingerprint = _build_release(tmp_path)
    report = dp.verify_release_zip(release, trusted_fingerprint=fingerprint)
    assert report["verified"] is True
    assert report["production_authority_allowed"] is False
    assert report["execution_authority_allowed"] is False


def test_unpinned_release_is_rejected_by_default(tmp_path: Path) -> None:
    release, _ = _build_release(tmp_path)
    with pytest.raises(dp.PublicationError, match="trusted fingerprint"):
        dp.verify_release_zip(release, trusted_fingerprint=None)


def test_unlisted_file_is_rejected(tmp_path: Path) -> None:
    release, fingerprint = _build_release(tmp_path)
    extracted = tmp_path / "extracted"
    dp.safe_extract_zip(release, extracted)
    (extracted / "UNLISTED.txt").write_text("tamper\n", encoding="utf-8")
    with pytest.raises(dp.PublicationError, match="file-set mismatch"):
        dp.verify_release_directory(extracted, trusted_fingerprint=fingerprint)


def test_tracked_file_mutation_is_rejected(tmp_path: Path) -> None:
    release, fingerprint = _build_release(tmp_path)
    extracted = tmp_path / "extracted"
    dp.safe_extract_zip(release, extracted)
    target = extracted / "docs" / "claim.txt"
    target.write_text("changed\n", encoding="utf-8")
    with pytest.raises(dp.PublicationError, match="digest mismatch"):
        dp.verify_release_directory(extracted, trusted_fingerprint=fingerprint)


def test_wrong_external_fingerprint_is_rejected(tmp_path: Path) -> None:
    release, _ = _build_release(tmp_path)
    with pytest.raises(dp.PublicationError, match="trusted fingerprint mismatch"):
        dp.verify_release_zip(release, trusted_fingerprint="sha256:" + "0" * 64)


def test_lineage_cycle_is_rejected() -> None:
    a = "sha256:" + "1" * 64
    b = "sha256:" + "2" * 64
    ledger = {
        "schema": "dai.lineage-ledger.v1",
        "required_phase_sequence": [],
        "nodes": [
            {"digest": a, "phase": "1"},
            {"digest": b, "phase": "2"},
        ],
        "edges": [
            {"source": a, "target": b, "kind": "predecessor"},
            {"source": b, "target": a, "kind": "predecessor"},
        ],
        "conflicts": [],
    }
    with pytest.raises(dp.PublicationError, match="cycle"):
        dp.validate_lineage_ledger(ledger)


def test_required_phase_sequence_needs_exact_edges() -> None:
    one = "sha256:" + "1" * 64
    two = "sha256:" + "2" * 64
    ledger = {
        "schema": "dai.lineage-ledger.v1",
        "required_phase_sequence": ["1", "2"],
        "nodes": [
            {"digest": one, "phase": "1"},
            {"digest": two, "phase": "2"},
        ],
        "edges": [],
        "conflicts": [],
    }
    with pytest.raises(dp.PublicationError, match="missing predecessor edge"):
        dp.validate_lineage_ledger(ledger)


def test_discover_nested_lineage(tmp_path: Path) -> None:
    child = tmp_path / "Phase-1.zip"
    with zipfile.ZipFile(child, "w") as handle:
        handle.writestr("RELEASE_MANIFEST.json", json.dumps({"release_id": "phase-one"}))
    parent = tmp_path / "Phase-2.zip"
    with zipfile.ZipFile(parent, "w") as handle:
        handle.writestr("prior-fossils/Phase-1.zip", child.read_bytes())
        handle.writestr(
            "receipt.json",
            json.dumps({"predecessor_digest": dp.sha256_file(child), "release_id": "phase-two"}),
        )
    ledger = dp.discover_lineage(tmp_path)
    phases = {node["phase"] for node in ledger["nodes"]}
    assert {"1", "2"}.issubset(phases)
    kinds = {edge["kind"] for edge in ledger["edges"]}
    assert "contains" in kinds
    assert "references" in kinds


def test_ablation_adapter_contract(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"capabilities": [{"id": "a"}, {"id": "b"}]}),
        encoding="utf-8",
    )
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "dai.ablation-plan.v1",
                "baseline_input": "baseline.json",
                "variants": [
                    {
                        "id": "baseline",
                        "operations": [],
                        "expected": {"/decision": "answer"},
                    },
                    {
                        "id": "remove-b",
                        "operations": [
                            {
                                "op": "remove_list_item_by_id",
                                "pointer": "/capabilities",
                                "id": "b",
                            }
                        ],
                        "expected": {"/decision": "refuse"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json,sys\n"
        "inp=json.load(open(sys.argv[1],encoding='utf-8'))\n"
        "ids={x['id'] for x in inp['capabilities']}\n"
        "json.dump({'decision':'answer' if {'a','b'} <= ids else 'refuse'},open(sys.argv[2],'w',encoding='utf-8'))\n",
        encoding="utf-8",
    )
    output = tmp_path / "ablation.json"
    report = dp.run_ablation(
        plan,
        adapter=f"{shlex_quote(sys.executable)} {shlex_quote(str(adapter))} {{input}} {{output}}",
        output_path=output,
        timeout=30,
    )
    assert report["passed"] is True
    assert report["passed_count"] == 2


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def test_mutation_suite_rejects_all_cases(tmp_path: Path) -> None:
    release, _ = _build_release(tmp_path)
    report = dp.run_mutation_suite(release, output=tmp_path / "mutation-report")
    assert report["passed"] is True
    assert report["mutation_count"] >= 8
    assert report["passed_count"] == report["mutation_count"]
